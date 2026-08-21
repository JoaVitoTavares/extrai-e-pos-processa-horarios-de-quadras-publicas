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
from persistencia import (
    COLUNAS_CSV,
    COLUNAS_DA_PREVISAO,
    COLUNAS_DE_CLIMA,
    SUFIXO_CSV,
)
from weather_collector import ARQUIVO_CLIMA, ARQUIVO_PREVISAO

FORMATO_DATA_HORA = "%Y-%m-%dT%H:%M"


def _para_datetime(texto: str, formato: str) -> datetime | None:
    """Converte texto em datetime devolvendo None quando o formato não bate, para uma
    linha corrompida no CSV ser ignorada em vez de derrubar o tratamento inteiro."""
    try:
        return datetime.strptime(texto, formato)
    except (TypeError, ValueError):
        return None


def _hora_cheia(data: str, horario_inicio: str) -> str:
    """Devolve a chave da previsão para uma reserva: a hora cheia em que ela começa, já
    que a Open-Meteo prevê de hora em hora e o site vende slots de meia em meia. A
    reserva das 17:30 pega a previsão das 17:00, a hora em que o jogo acontece."""
    inicio = _para_datetime(f"{data}T{horario_inicio}", FORMATO_DATA_HORA)
    return "" if inicio is None else inicio.strftime("%Y-%m-%dT%H:00")


class TratamentoDeDados:
    """Casa o clima com as reservas de cada quadra: a observação mais recente nas linhas
    que estão na janela que antecede o jogo, e a previsão do horário nas linhas que
    acabaram de ser reservadas."""

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
        """Percorre os CSVs de quadra do diretório e escreve neles as duas leituras de
        clima: a observação mais recente nas linhas que estão na janela, e a previsão do
        horário nas reservas recém-detectadas. Sem observação utilizável nem previsão
        nenhum arquivo é tocado. Devolve os caminhos efetivamente alterados, para o
        gerenciador relatar o que mudou."""
        agora = agora or datetime.now()
        leitura = self._leitura_mais_recente(agora)
        previsoes = self._previsoes()
        if leitura is None and not previsoes:
            return []

        alterados = []
        for caminho_csv in sorted(glob.glob(os.path.join(self.diretorio, "*" + SUFIXO_CSV))):
            df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
            df = df.reindex(columns=COLUNAS_CSV, fill_value="")
            if self._enriquecer(df, leitura, agora) + self._congelar_previsao(df, previsoes):
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

    def _previsoes(self) -> dict:
        """Lê o CSV de previsão e devolve as horas previstas indexadas por data_hora, ou
        um dicionário vazio quando o arquivo não existe. É a tabela vigente, reescrita a
        cada rodada: quem precisa da versão antiga já a tem congelada na linha da
        reserva."""
        caminho_csv = os.path.join(self.diretorio, ARQUIVO_PREVISAO)
        if not os.path.exists(caminho_csv):
            return {}

        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
        return {linha["data_hora"]: linha.to_dict() for _, linha in df.iterrows()}

    def _congelar_previsao(self, df, previsoes: dict) -> int:
        """Grava nas reservas recém-detectadas a previsão que estava publicada para o
        horário do jogo, e só nelas: escreve uma vez, quando `reservado_em` já existe e a
        previsão ainda está vazia, e nunca reescreve. É esse congelamento que responde ao
        que se sabia do tempo na hora de reservar — a observação de uma hora antes do jogo
        chega tarde demais para explicar uma reserva feita dois dias antes."""
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

    def _enriquecer(self, df, leitura: dict | None, agora: datetime) -> int:
        """Escreve as cinco colunas de clima observado nas linhas do DataFrame que estão
        na janela, sobrescrevendo o que houver — cada rodada vale mais que a anterior, e a
        última, a de uma hora antes da reserva, é a que fica. Sem leitura utilizável não
        escreve nada. Devolve quantas linhas mudaram."""
        if leitura is None:
            return 0
        na_janela = df.apply(
            lambda linha: self._dentro_da_janela(linha["data"], linha["horario_inicio"], agora),
            axis=1,
        )
        if df.empty or not na_janela.any():
            return 0
        df.loc[na_janela, COLUNAS_DE_CLIMA] = [leitura[coluna] for coluna in COLUNAS_DE_CLIMA]
        return int(na_janela.sum())
