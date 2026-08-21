"""Testes do coletor de clima, com a resposta da Open-Meteo substituída por um dublê."""

import fnmatch
import os
from datetime import datetime

import pandas as pd
import pytest
import requests

import config
import persistencia
import weather_collector
from conftest import RespostaFalsa

AGORA = datetime(2026, 8, 16, 16, 47, 0)
LATITUDE, LONGITUDE = -29.9048885, -51.1612496
ATUAL = {
    "time": "2026-08-16T16:45",
    "interval": 900,
    "temperature_2m": 24.4,
    "apparent_temperature": 26.3,
    "relative_humidity_2m": 76,
    "precipitation": 0.0,
    "weather_code": 3,
    "wind_speed_10m": 13.1,
    "wind_direction_10m": 99,
}
PAYLOAD = {
    "latitude": -29.912127,
    "longitude": -51.23398,
    "timezone": "America/Sao_Paulo",
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
    "current": ATUAL,
}
HORARIA = {
    "time": ["2026-08-16T20:00", "2026-08-16T21:00"],
    "temperature_2m": [18.9, 17.5],
    "relative_humidity_2m": [88, 90],
    "precipitation": [2.4, 0.0],
    "precipitation_probability": [70, 20],
    "weather_code": [63, 0],
    "wind_speed_10m": [19.4, 12.0],
}
PAYLOAD_PREVISAO = {
    "latitude": -29.912127,
    "longitude": -51.23398,
    "timezone": "America/Sao_Paulo",
    "hourly_units": {"temperature_2m": "°C", "precipitation": "mm"},
    "hourly": HORARIA,
}


@pytest.mark.parametrize(
    "codigo, esperado",
    [
        (0, "Céu limpo"),
        (3, "Encoberto"),
        (45, "Nevoeiro"),
        (51, "Garoa fraca"),
        (61, "Chuva fraca"),
        (71, "Neve fraca"),
        (80, "Pancadas de chuva fracas"),
        (95, "Trovoada"),
        (99, "Trovoada com granizo forte"),
    ],
)
def test_traduz_o_codigo_para_texto(codigo, esperado):
    assert weather_collector.descrever_codigo(codigo) == esperado


@pytest.mark.parametrize("codigo", [77, 4, None, "", "abc", -1])
def test_codigo_desconhecido_fica_vazio(codigo):
    assert weather_collector.descrever_codigo(codigo) == ""


def test_codigo_desconhecido_ainda_e_gravado_em_bruto():
    linha = weather_collector._linha_de_clima({"weather_code": 77}, AGORA, 0.0, 0.0)

    assert linha["clima"] == ""
    assert linha["codigo_clima"] == 77


def test_chama_a_api_nas_coordenadas_recebidas(respostas):
    """A consulta usa a URL do config e as coordenadas que vêm de fora — as da arena que
    está sendo coletada, e não um ponto fixo —, pede os sete campos atuais, fixa o fuso e
    não fica pendurada sem timeout."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD)
    weather_collector.consultar_clima(LATITUDE, LONGITUDE)

    url, kwargs = chamadas[0]
    assert url == config.API_CLIMA
    assert kwargs["params"]["latitude"] == LATITUDE
    assert kwargs["params"]["longitude"] == LONGITUDE
    assert kwargs["params"]["timezone"] == config.FUSO_HORARIO
    assert kwargs["params"]["current"].split(",") == [
        "temperature_2m", "apparent_temperature", "relative_humidity_2m",
        "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m",
    ]
    assert kwargs["timeout"] > 0


def test_devolve_o_bloco_atual(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD)

    assert weather_collector.consultar_clima(LATITUDE, LONGITUDE) == ATUAL


@pytest.mark.parametrize("payload", [{}, {"current": None}, {"current": []}, [], "erro"])
def test_json_sem_o_bloco_atual_levanta_erro(respostas, payload):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(payload)

    with pytest.raises(ValueError, match="formato inesperado"):
        weather_collector.consultar_clima(LATITUDE, LONGITUDE)


def test_erro_http_sobe(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD, erro=requests.HTTPError("500"))

    with pytest.raises(requests.HTTPError):
        weather_collector.consultar_clima(LATITUDE, LONGITUDE)


def test_linha_carrega_todos_os_campos_da_api():
    linha = weather_collector._linha_de_clima(ATUAL, AGORA, -29.9128, -51.1836)

    assert linha["data_hora"] == "2026-08-16T16:45"
    assert linha["coletado_em"] == "2026-08-16T16:47:00"
    assert linha["clima"] == "Encoberto"
    assert linha["temperatura"] == 24.4
    assert linha["sensacao_termica"] == 26.3
    assert linha["umidade"] == 76
    assert linha["precipitacao"] == 0.0
    assert linha["velocidade_vento"] == 13.1
    assert linha["direcao_vento"] == 99
    assert (linha["latitude"], linha["longitude"]) == (-29.9128, -51.1836)


def test_cabecalho_do_csv_de_clima(tmp_path):
    caminho = weather_collector.salvar_leitura(ATUAL, LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df.columns) == weather_collector.COLUNAS_CLIMA
    assert df.loc[0, "clima"] == "Encoberto"
    assert df.loc[0, "temperatura"] == "24.4"


def test_cria_o_diretorio_se_nao_existir(tmp_path):
    destino = tmp_path / "ainda-nao-existe"
    caminho = weather_collector.salvar_leitura(ATUAL, LATITUDE, LONGITUDE, str(destino), AGORA)

    assert destino.is_dir()
    assert os.path.exists(caminho)


def test_mesmo_balde_de_quinze_minutos_nao_duplica(tmp_path):
    weather_collector.salvar_leitura(ATUAL, LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    caminho = weather_collector.salvar_leitura(
        dict(ATUAL, temperature_2m=25.1), LATITUDE, LONGITUDE, str(tmp_path),
        datetime(2026, 8, 16, 16, 58, 0),
    )
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "temperatura"] == "25.1"
    assert df.loc[0, "coletado_em"] == "2026-08-16T16:58:00"


def test_baldes_diferentes_viram_duas_linhas(tmp_path):
    weather_collector.salvar_leitura(ATUAL, LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    caminho = weather_collector.salvar_leitura(
        dict(ATUAL, time="2026-08-16T17:00"), LATITUDE, LONGITUDE, str(tmp_path),
        datetime(2026, 8, 16, 17, 2, 0),
    )
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df["data_hora"]) == ["2026-08-16T16:45", "2026-08-16T17:00"]


def test_arquivo_de_clima_nao_casa_com_o_glob_das_quadras():
    """O sufixo do arquivo de clima é diferente de propósito: o tratamento varre as
    quadras por padrão de nome, e um clima-extracoes.csv seria tratado como quadra."""
    assert not fnmatch.fnmatch(weather_collector.ARQUIVO_CLIMA, "*" + persistencia.SUFIXO_CSV)


def test_coletar_clima_consulta_e_grava(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD)
    caminho = weather_collector.coletar_clima(LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert os.path.basename(caminho) == weather_collector.ARQUIVO_CLIMA
    assert df.loc[0, "data_hora"] == "2026-08-16T16:45"


def test_previsao_pede_as_horas_do_horizonte_da_coleta(respostas):
    """A previsão cobre os mesmos dias que o coletor de quadras percorre: reserva só é
    vista nascer dentro dessa janela, e é para ela que existe previsão a congelar. Hoje
    conta junto com os dias à frente, daí o +1."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD_PREVISAO)
    weather_collector.consultar_previsao(LATITUDE, LONGITUDE)

    url, kwargs = chamadas[0]
    assert url == config.API_CLIMA
    assert kwargs["params"]["forecast_days"] == config.DIAS_A_FRENTE + 1
    assert kwargs["params"]["timezone"] == config.FUSO_HORARIO
    assert kwargs["params"]["hourly"].split(",") == [
        "temperature_2m", "relative_humidity_2m", "precipitation",
        "precipitation_probability", "weather_code", "wind_speed_10m",
    ]
    assert kwargs["timeout"] > 0


@pytest.mark.parametrize("payload", [{}, {"hourly": None}, {"hourly": {}}, [], "erro"])
def test_json_sem_o_bloco_horario_levanta_erro(respostas, payload):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(payload)

    with pytest.raises(ValueError, match="formato inesperado"):
        weather_collector.consultar_previsao(LATITUDE, LONGITUDE)


def test_previsao_vira_uma_linha_por_hora(tmp_path):
    caminho = weather_collector.salvar_previsao(HORARIA, LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df.columns) == weather_collector.COLUNAS_PREVISAO
    assert list(df["data_hora"]) == ["2026-08-16T20:00", "2026-08-16T21:00"]
    assert df.loc[0, "clima"] == "Chuva moderada"
    assert df.loc[0, "temperatura"] == "18.9"
    assert df.loc[0, "probabilidade_chuva"] == "70"
    assert df.loc[1, "clima"] == "Céu limpo"


def test_campo_que_a_api_deixar_de_mandar_vira_coluna_vazia(tmp_path):
    sem_vento = {chave: valor for chave, valor in HORARIA.items() if chave != "wind_speed_10m"}
    caminho = weather_collector.salvar_previsao(sem_vento, LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 2
    assert list(df["velocidade_vento"]) == ["", ""]
    assert df.loc[0, "temperatura"] == "18.9"


def test_rodada_nova_substitui_a_previsao_inteira(tmp_path):
    weather_collector.salvar_previsao(HORARIA, LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    revisada = dict(HORARIA, time=["2026-08-16T22:00"], weather_code=[95],
                    temperature_2m=[16.0], relative_humidity_2m=[95], precipitation=[8.0],
                    precipitation_probability=[90], wind_speed_10m=[30.0])
    caminho = weather_collector.salvar_previsao(revisada, LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df["data_hora"]) == ["2026-08-16T22:00"]


def test_arquivo_de_previsao_nao_casa_com_o_glob_das_quadras():
    assert not fnmatch.fnmatch(weather_collector.ARQUIVO_PREVISAO, "*" + persistencia.SUFIXO_CSV)


def test_coletar_previsao_consulta_e_grava(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD_PREVISAO)
    caminho = weather_collector.coletar_previsao(LATITUDE, LONGITUDE, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert os.path.basename(caminho) == weather_collector.ARQUIVO_PREVISAO
    assert df.loc[0, "data_hora"] == "2026-08-16T20:00"
