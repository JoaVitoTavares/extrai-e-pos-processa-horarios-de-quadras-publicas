"""Coleta as condições atuais na arena pela API Open-Meteo."""

import os
import pandas as pd
import requests
from datetime import datetime

from config import (
    API_CLIMA,
    DIAS_A_FRENTE,
    DIRETORIO_EXTRACOES,
    FUSO_HORARIO,
    LATITUDE,
    LONGITUDE,
)
from persistencia import anexar_linha

CAMPOS_ATUAIS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,"
    "weather_code,wind_speed_10m,wind_direction_10m"
)
CAMPOS_PREVISAO = (
    "temperature_2m,relative_humidity_2m,precipitation,precipitation_probability,"
    "weather_code,wind_speed_10m"
)
ARQUIVO_CLIMA = "clima-leituras.csv"
ARQUIVO_PREVISAO = "clima-previsoes.csv"
COLUNAS_CLIMA = [
    "data_hora", "coletado_em", "clima", "codigo_clima", "temperatura",
    "sensacao_termica", "umidade", "precipitacao", "velocidade_vento",
    "direcao_vento", "latitude", "longitude",
]
COLUNAS_PREVISAO = [
    "data_hora", "coletado_em", "clima", "codigo_clima", "temperatura", "umidade",
    "precipitacao", "probabilidade_chuva", "velocidade_vento", "latitude", "longitude",
]
CODIGOS_CLIMA = {
    0: "Céu limpo",
    1: "Predomínio de sol",
    2: "Parcialmente nublado",
    3: "Encoberto",
    45: "Nevoeiro",
    48: "Nevoeiro com gelo",
    51: "Garoa fraca",
    53: "Garoa moderada",
    55: "Garoa densa",
    61: "Chuva fraca",
    63: "Chuva moderada",
    65: "Chuva forte",
    71: "Neve fraca",
    73: "Neve moderada",
    75: "Neve forte",
    80: "Pancadas de chuva fracas",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva fortes",
    95: "Trovoada",
    96: "Trovoada com granizo",
    99: "Trovoada com granizo forte",
}


def descrever_codigo(codigo) -> str:
    """Traduz o weather_code da Open-Meteo para o texto em português que vai ao CSV. Um
    código fora do mapa devolve vazio em vez de um rótulo inventado: o número bruto
    continua gravado em codigo_clima, então nada se perde e um código novo da API
    aparece como lacuna a investigar, não como clima errado."""
    try:
        return CODIGOS_CLIMA[int(codigo)]
    except (KeyError, TypeError, ValueError):
        return ""


def consultar_clima(
    latitude: float = LATITUDE, longitude: float = LONGITUDE, timeout: int = 30
) -> dict:
    """Busca as condições atuais na Open-Meteo e devolve o bloco `current` do JSON. Uma
    resposta sem esse bloco levanta ValueError em vez de estourar KeyError cru ou
    devolver dicionário vazio, seguindo a mesma regra de listar_esportes: num coletor
    agendado, gravar nada em silêncio custa mais caro do que falhar alto."""
    resposta = requests.get(
        API_CLIMA,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": CAMPOS_ATUAIS,
            "timezone": FUSO_HORARIO,
        },
        timeout=timeout,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    atual = dados.get("current") if isinstance(dados, dict) else None
    if not isinstance(atual, dict):
        raise ValueError(f"{API_CLIMA} devolveu JSON em formato inesperado: sem o bloco 'current'")
    return atual


def _linha_de_clima(atual: dict, agora: datetime, latitude: float, longitude: float) -> dict:
    """Converte o bloco `current` da API na linha do CSV de clima, já com o weather_code
    traduzido — a tradução acontece na extração para o histórico nascer legível e o
    tratamento não precisar do mapa. O horário vem da API, que o arredonda no balde de
    quinze minutos; `coletado_em` guarda quando a chamada foi feita."""
    return {
        "data_hora": atual.get("time", ""),
        "coletado_em": agora.isoformat(timespec="seconds"),
        "clima": descrever_codigo(atual.get("weather_code")),
        "codigo_clima": atual.get("weather_code", ""),
        "temperatura": atual.get("temperature_2m", ""),
        "sensacao_termica": atual.get("apparent_temperature", ""),
        "umidade": atual.get("relative_humidity_2m", ""),
        "precipitacao": atual.get("precipitation", ""),
        "velocidade_vento": atual.get("wind_speed_10m", ""),
        "direcao_vento": atual.get("wind_direction_10m", ""),
        "latitude": latitude,
        "longitude": longitude,
    }


def salvar_leitura(
    atual: dict,
    diretorio: str = DIRETORIO_EXTRACOES,
    agora=None,
    latitude: float = LATITUDE,
    longitude: float = LONGITUDE,
) -> str:
    """Grava a leitura no CSV único de clima dentro de `diretorio`, com upsert por
    data_hora: duas coletas caindo no mesmo balde de quinze minutos atualizam a mesma
    linha em vez de duplicá-la. As coordenadas vão na linha para o histórico continuar
    legível depois que alguém editar o config. Devolve o caminho gravado."""
    agora = agora or datetime.now()
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    caminho_csv = os.path.join(diretorio, ARQUIVO_CLIMA)
    linha = _linha_de_clima(atual, agora, latitude, longitude)
    anexar_linha(caminho_csv, linha, COLUNAS_CLIMA, "data_hora")
    return caminho_csv


def coletar_clima(diretorio: str = DIRETORIO_EXTRACOES, agora=None) -> str:
    """Consulta a API e grava a leitura, devolvendo o caminho do CSV de clima. É a
    fachada que o gerenciador chama: quem orquestra não precisa saber que existem duas
    etapas nem qual delas falhou."""
    return salvar_leitura(consultar_clima(), diretorio, agora)


def consultar_previsao(
    latitude: float = LATITUDE,
    longitude: float = LONGITUDE,
    dias_a_frente: int = DIAS_A_FRENTE,
    timeout: int = 30,
) -> dict:
    """Busca a previsão hora a hora para os dias que a coleta de quadras percorre e
    devolve o bloco `hourly` do JSON. O horizonte acompanha DIAS_A_FRENTE: uma reserva só
    é vista nascer dentro da janela que o coletor visita, e é para essas que faz sentido
    haver previsão. Resposta sem o bloco levanta ValueError, como em consultar_clima."""
    resposta = requests.get(
        API_CLIMA,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "hourly": CAMPOS_PREVISAO,
            "forecast_days": dias_a_frente + 1,
            "timezone": FUSO_HORARIO,
        },
        timeout=timeout,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    horas = dados.get("hourly") if isinstance(dados, dict) else None
    if not isinstance(horas, dict) or "time" not in horas:
        raise ValueError(f"{API_CLIMA} devolveu JSON em formato inesperado: sem o bloco 'hourly'")
    return horas


def _linhas_de_previsao(horas: dict, agora: datetime, latitude: float, longitude: float) -> list[dict]:
    """Transpõe o bloco `hourly` — que vem como uma lista por campo — em uma linha por
    hora prevista, com o weather_code já traduzido. Um campo que a API deixe de devolver
    vira coluna vazia, em vez de derrubar a transposição inteira."""
    def valor(campo: str, indice: int):
        """Lê o campo na hora pedida, devolvendo vazio quando a lista não vem ou é curta."""
        valores = horas.get(campo) or []
        return valores[indice] if indice < len(valores) else ""

    return [
        {
            "data_hora": data_hora,
            "coletado_em": agora.isoformat(timespec="seconds"),
            "clima": descrever_codigo(valor("weather_code", i)),
            "codigo_clima": valor("weather_code", i),
            "temperatura": valor("temperature_2m", i),
            "umidade": valor("relative_humidity_2m", i),
            "precipitacao": valor("precipitation", i),
            "probabilidade_chuva": valor("precipitation_probability", i),
            "velocidade_vento": valor("wind_speed_10m", i),
            "latitude": latitude,
            "longitude": longitude,
        }
        for i, data_hora in enumerate(horas["time"])
    ]


def salvar_previsao(
    horas: dict,
    diretorio: str = DIRETORIO_EXTRACOES,
    agora=None,
    latitude: float = LATITUDE,
    longitude: float = LONGITUDE,
) -> str:
    """Reescreve por inteiro o CSV de previsão dentro de `diretorio`. Aqui não há upsert
    nem histórico: a previsão de uma hora só vale a mais recente, e a versão que importa
    guardar — a que estava publicada quando a reserva foi feita — o tratamento congela na
    própria linha da reserva. Devolve o caminho gravado."""
    agora = agora or datetime.now()
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    caminho_csv = os.path.join(diretorio, ARQUIVO_PREVISAO)
    linhas = _linhas_de_previsao(horas, agora, latitude, longitude)
    pd.DataFrame(linhas).reindex(columns=COLUNAS_PREVISAO, fill_value="").to_csv(
        caminho_csv, index=False
    )
    return caminho_csv


def coletar_previsao(diretorio: str = DIRETORIO_EXTRACOES, agora=None) -> str:
    """Consulta a previsão e grava a tabela, devolvendo o caminho do CSV. É a fachada
    irmã de coletar_clima: uma responde o que está acontecendo agora, a outra o que se
    espera para os horários que ainda podem ser reservados."""
    return salvar_previsao(consultar_previsao(), diretorio, agora)
