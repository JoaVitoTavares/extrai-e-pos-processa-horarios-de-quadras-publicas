"""Preenche as colunas de clima das reservas a partir do histórico coletado."""

import glob
import os
import pandas as pd
from datetime import datetime, timedelta

from config import (
    DIRETORIO_EXTRACOES,
    HORAS_ANTES_DA_RESERVA,
    HORAS_ATE_A_RESERVA,
    TOLERANCIA_LEITURA_CLIMA_MIN,
)
from persistencia import COLUNAS_CSV, SUFIXO_CSV
from weather_collector import ARQUIVO_CLIMA

COLUNAS_DE_CLIMA = ["clima", "temperatura", "umidade", "precipitacao", "velocidade_vento"]
FORMATO_DATA_HORA = "%Y-%m-%dT%H:%M"


def _para_datetime(texto: str, formato: str) -> datetime | None:
    """Converte texto em datetime devolvendo None quando o formato não bate, para uma
    linha corrompida no CSV ser ignorada em vez de derrubar o tratamento inteiro."""
    try:
        return datetime.strptime(texto, formato)
    except (TypeError, ValueError):
        return None


class TratamentoDeDados:
    """Casa a última leitura de clima com as reservas de cada quadra, escrevendo as
    colunas ambientais só nas linhas cujo horário está dentro da janela que antecede a
    reserva."""

    def __init__(
        self,
        diretorio: str = DIRETORIO_EXTRACOES,
        horas_antes: float = HORAS_ANTES_DA_RESERVA,
        horas_ate: float = HORAS_ATE_A_RESERVA,
        tolerancia_min: int = TOLERANCIA_LEITURA_CLIMA_MIN,
    ) -> None:
        """Guarda o diretório das extrações e os limites da janela, expostos como
        parâmetros para os testes fixarem o intervalo sem depender do config."""
        self.diretorio = diretorio
        self.horas_antes = horas_antes
        self.horas_ate = horas_ate
        self.tolerancia_min = tolerancia_min

    def aplicar(self, agora=None) -> list[str]:
        """Percorre os CSVs de quadra do diretório e grava neles a leitura de clima mais
        recente, apenas nas linhas em que a reserva está dentro da janela. Sem leitura
        utilizável nenhum arquivo é tocado. Devolve os caminhos efetivamente alterados,
        para o gerenciador relatar o que mudou."""
        agora = agora or datetime.now()
        leitura = self._leitura_mais_recente(agora)
        if leitura is None:
            return []

        alterados = []
        for caminho_csv in sorted(glob.glob(os.path.join(self.diretorio, "*" + SUFIXO_CSV))):
            df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
            df = df.reindex(columns=COLUNAS_CSV, fill_value="")
            if self._enriquecer(df, leitura, agora):
                df.to_csv(caminho_csv, index=False)
                alterados.append(caminho_csv)
        return alterados

    def _leitura_mais_recente(self, agora: datetime) -> dict | None:
        """Devolve a última leitura do CSV de clima que não seja futura em relação a
        `agora`, ou None se o arquivo não existe, está vazio ou a leitura é velha demais.
        Descartar leitura futura protege de relógio desalinhado; descartar leitura velha
        evita carimbar numa reserva um clima de horas atrás, pior que deixar a lacuna."""
        caminho_csv = os.path.join(self.diretorio, ARQUIVO_CLIMA)
        if not os.path.exists(caminho_csv):
            return None

        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
        candidatas = []
        for _, linha in df.iterrows():
            momento = _para_datetime(linha["data_hora"], FORMATO_DATA_HORA)
            if momento is not None and momento <= agora:
                candidatas.append((momento, linha))
        if not candidatas:
            return None

        momento, linha = max(candidatas, key=lambda par: par[0])
        if agora - momento > timedelta(minutes=self.tolerancia_min):
            return None
        return linha.to_dict()

    def _dentro_da_janela(self, data: str, horario_inicio: str, agora: datetime) -> bool:
        """Diz se a reserva está no intervalo em que o clima ainda vale a pena: de
        `horas_antes` até `horas_ate` antes do início, com as duas pontas incluídas.
        Antes disso a observação envelheceria até o jogo; depois, o registro já entrou na
        janela morta em que nada mais se observa."""
        inicio = _para_datetime(f"{data}T{horario_inicio}", FORMATO_DATA_HORA)
        if inicio is None:
            return False
        return (
            inicio - timedelta(hours=self.horas_antes)
            <= agora
            <= inicio - timedelta(hours=self.horas_ate)
        )

    def _enriquecer(self, df, leitura: dict, agora: datetime) -> int:
        """Escreve as cinco colunas de clima nas linhas do DataFrame que estão na janela,
        sobrescrevendo o que houver — cada rodada vale mais que a anterior, e a última,
        a de uma hora antes da reserva, é a que fica. Devolve quantas linhas mudaram."""
        na_janela = df.apply(
            lambda linha: self._dentro_da_janela(linha["data"], linha["horario_inicio"], agora),
            axis=1,
        )
        if df.empty or not na_janela.any():
            return 0
        df.loc[na_janela, COLUNAS_DE_CLIMA] = [leitura[coluna] for coluna in COLUNAS_DE_CLIMA]
        return int(na_janela.sum())
