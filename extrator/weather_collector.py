"""Coleta as condições atuais na arena pela API Open-Meteo."""

import os
import sys
import pandas as pd
import requests
from datetime import datetime

from extrator.config import API_CLIMA, DIAS_A_FRENTE, DIRETORIO_EXTRACOES, FUSO_HORARIO
from extrator.persistencia import anexar_linha

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
    try:
        return CODIGOS_CLIMA[int(codigo)]
    except (KeyError, TypeError, ValueError):
        return ""


def consultar_clima(latitude: float, longitude: float, timeout: int = 30) -> dict:
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
    latitude: float,
    longitude: float,
    diretorio: str = DIRETORIO_EXTRACOES,
    agora=None,
) -> str:
    agora = agora or datetime.now()
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    caminho_csv = os.path.join(diretorio, ARQUIVO_CLIMA)
    linha = _linha_de_clima(atual, agora, latitude, longitude)
    anexar_linha(caminho_csv, linha, COLUNAS_CLIMA, "data_hora")
    return caminho_csv


def coletar_clima(
    latitude: float, longitude: float, diretorio: str = DIRETORIO_EXTRACOES, agora=None
) -> str:
    return salvar_leitura(
        consultar_clima(latitude, longitude), latitude, longitude, diretorio, agora
    )


def consultar_previsao(
    latitude: float,
    longitude: float,
    dias_a_frente: int = DIAS_A_FRENTE,
    timeout: int = 30,
) -> dict:
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
    def valor(campo: str, indice: int):
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
    latitude: float,
    longitude: float,
    diretorio: str = DIRETORIO_EXTRACOES,
    agora=None,
) -> str:
    agora = agora or datetime.now()
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    caminho_csv = os.path.join(diretorio, ARQUIVO_PREVISAO)
    linhas = _linhas_de_previsao(horas, agora, latitude, longitude)
    pd.DataFrame(linhas).reindex(columns=COLUNAS_PREVISAO, fill_value="").to_csv(
        caminho_csv, index=False
    )
    return caminho_csv


def coletar_previsao(
    latitude: float, longitude: float, diretorio: str = DIRETORIO_EXTRACOES, agora=None
) -> str:
    return salvar_previsao(
        consultar_previsao(latitude, longitude), latitude, longitude, diretorio, agora
    )


def record_weather(
    location: dict, directory: str, output=None, arena_name: str = ""
) -> str | None:
    """Grava as condições atuais do ponto da arena. Falha de rede vira aviso e None."""
    output = output or sys.stdout
    print("\n>> CLIMA (API Open-Meteo): condições atuais na arena...", file=output)
    try:
        path = coletar_clima(location["latitude"], location["longitude"], directory)
    except (requests.RequestException, ValueError) as error:
        print(f"[AVISO] {arena_name}: clima não coletado: {error}", file=sys.stderr)
        return None
    print(f"   registrado em {path}", file=output)
    return path


def record_forecast(
    location: dict, directory: str, output=None, arena_name: str = ""
) -> str | None:
    """Grava a previsão hora a hora do ponto da arena. Falha de rede vira aviso e None."""
    output = output or sys.stdout
    print("\n>> PREVISÃO (API Open-Meteo): horas à frente na arena...", file=output)
    try:
        path = coletar_previsao(location["latitude"], location["longitude"], directory)
    except (requests.RequestException, ValueError) as error:
        print(f"[AVISO] {arena_name}: previsão não coletada: {error}", file=sys.stderr)
        return None
    print(f"   registrada em {path}", file=output)
    return path
