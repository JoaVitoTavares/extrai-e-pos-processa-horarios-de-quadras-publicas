"""Preenche as colunas de clima das reservas a partir do histórico coletado."""

import glob
import os
import pandas as pd
from datetime import datetime, timedelta

from extrator.config import (
    DIRETORIO_EXTRACOES,
    HORAS_ANTES_DA_RESERVA,
    HORAS_ATE_A_RESERVA,
    TOLERANCIA_LEITURA_CLIMA_MIN,
)
from extrator.persistencia import (
    COLUNAS_CSV,
    COLUNAS_DA_PREVISAO,
    COLUNAS_DE_CLIMA,
    COLUNAS_DO_CLIMA_ANTES_DO_JOGO,
    COLUNAS_DO_CLIMA_NA_RESERVA,
    SUFIXO_CSV,
)
from extrator.weather_collector import WEATHER_FILE, FORECAST_FILE

FORMATO_DATA_HORA = "%Y-%m-%dT%H:%M"
FORMATO_CARIMBO = "%Y-%m-%dT%H:%M:%S"


def _para_datetime(texto: str, formato: str) -> datetime | None:
    try:
        return datetime.strptime(texto, formato)
    except (TypeError, ValueError):
        return None


def _hora_cheia(data: str, horario_inicio: str) -> str:
    inicio = _para_datetime(f"{data}T{horario_inicio}", FORMATO_DATA_HORA)
    return "" if inicio is None else inicio.strftime("%Y-%m-%dT%H:00")


class TratamentoDeDados:
    """Casa o clima com as reservas de cada quadra: a observação mais recente nas linhas
    que estão na janela que antecede o jogo, e — nas linhas que acabaram de ser
    reservadas — o clima que fazia no instante da virada e a previsão do horário."""

    def __init__(
        self,
        diretorio: str = DIRETORIO_EXTRACOES,
        horas_antes: float = HORAS_ANTES_DA_RESERVA,
        horas_ate: float = HORAS_ATE_A_RESERVA,
        tolerancia_min: int = TOLERANCIA_LEITURA_CLIMA_MIN,
    ) -> None:
        self.diretorio = diretorio
        self.horas_antes = horas_antes
        self.horas_ate = horas_ate
        self.tolerancia_min = tolerancia_min

    def aplicar(self, agora=None) -> list[str]:
        agora = agora or datetime.now()
        historico = self._historico_de_clima()
        previsoes = self._previsoes()
        if not historico and not previsoes:
            return []

        leitura = self._leitura_mais_recente(historico, agora)
        alterados = []
        for caminho_csv in sorted(glob.glob(os.path.join(self.diretorio, "*" + SUFIXO_CSV))):
            df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
            df = df.reindex(columns=COLUNAS_CSV, fill_value="")
            gravadas = (
                self._enriquecer(df, leitura, agora)
                + self._congelar_clima_da_reserva(df, historico)
                + self._congelar_previsao(df, previsoes)
            )
            if gravadas:
                df.to_csv(caminho_csv, index=False)
                alterados.append(caminho_csv)
        return alterados

    def _historico_de_clima(self) -> list[tuple[datetime, dict]]:
        caminho_csv = os.path.join(self.diretorio, WEATHER_FILE)
        if not os.path.exists(caminho_csv):
            return []

        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
        datadas = []
        for _, linha in df.iterrows():
            momento = _para_datetime(linha["data_hora"], FORMATO_DATA_HORA)
            if momento is not None:
                datadas.append((momento, linha.to_dict()))
        return datadas

    def _leitura_mais_recente(self, historico: list, agora: datetime) -> dict | None:
        passadas = [par for par in historico if par[0] <= agora]
        if not passadas:
            return None

        momento, linha = max(passadas, key=lambda par: par[0])
        if agora - momento > timedelta(minutes=self.tolerancia_min):
            return None
        return linha

    def _leitura_junto_de(self, historico: list, momento: datetime) -> dict | None:
        marca, linha = min(historico, key=lambda par: abs(par[0] - momento))
        if abs(marca - momento) > timedelta(minutes=self.tolerancia_min):
            return None
        return linha

    def _previsoes(self) -> dict:
        caminho_csv = os.path.join(self.diretorio, FORECAST_FILE)
        if not os.path.exists(caminho_csv):
            return {}

        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
        return {linha["data_hora"]: linha.to_dict() for _, linha in df.iterrows()}

    def _congelar_clima_da_reserva(self, df, historico: list) -> int:
        if df.empty or not historico:
            return 0

        pendentes = (df["reservado_em"] != "") & (df[COLUNAS_DO_CLIMA_NA_RESERVA[0]] == "")
        gravadas = 0
        for indice in df.index[pendentes]:
            momento = _para_datetime(df.at[indice, "reservado_em"], FORMATO_CARIMBO)
            observada = None if momento is None else self._leitura_junto_de(historico, momento)
            if observada is None:
                continue
            df.loc[indice, COLUNAS_DO_CLIMA_NA_RESERVA] = [
                observada[coluna] for coluna in COLUNAS_DE_CLIMA
            ]
            gravadas += 1
        return gravadas

    def _congelar_previsao(self, df, previsoes: dict) -> int:
        if df.empty or not previsoes:
            return 0

        pendentes = (df["reservado_em"] != "") & (df[COLUNAS_DA_PREVISAO[0]] == "")
        gravadas = 0
        for indice in df.index[pendentes]:
            prevista = previsoes.get(
                _hora_cheia(df.at[indice, "data"], df.at[indice, "horario_inicio"])
            )
            if prevista is None:
                continue
            df.loc[indice, COLUNAS_DA_PREVISAO] = [prevista[coluna] for coluna in COLUNAS_DE_CLIMA]
            gravadas += 1
        return gravadas

    def _dentro_da_janela(self, data: str, horario_inicio: str, agora: datetime) -> bool:
        inicio = _para_datetime(f"{data}T{horario_inicio}", FORMATO_DATA_HORA)
        if inicio is None:
            return False
        return (
            inicio - timedelta(hours=self.horas_antes)
            <= agora
            <= inicio - timedelta(hours=self.horas_ate)
        )

    def _enriquecer(self, df, leitura: dict | None, agora: datetime) -> int:
        if leitura is None:
            return 0
        na_janela = df.apply(
            lambda linha: self._dentro_da_janela(linha["data"], linha["horario_inicio"], agora),
            axis=1,
        )
        if df.empty or not na_janela.any():
            return 0
        df.loc[na_janela, COLUNAS_DO_CLIMA_ANTES_DO_JOGO] = [
            leitura[coluna] for coluna in COLUNAS_DE_CLIMA
        ]
        return int(na_janela.sum())
