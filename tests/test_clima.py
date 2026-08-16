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
    """Cada código da Open-Meteo vira a descrição em português que vai ao CSV."""
    assert weather_collector.descrever_codigo(codigo) == esperado


@pytest.mark.parametrize("codigo", [77, 4, None, "", "abc", -1])
def test_codigo_desconhecido_fica_vazio(codigo):
    """Um código fora do mapa não inventa rótulo: devolve vazio, do mesmo jeito que a
    cobertura da quadra não afirma um false que não foi observado."""
    assert weather_collector.descrever_codigo(codigo) == ""


def test_codigo_desconhecido_ainda_e_gravado_em_bruto():
    """A lacuna na descrição não pode virar perda de dado: o número continua na linha,
    então um código novo da API é investigável depois."""
    linha = weather_collector._linha_de_clima({"weather_code": 77}, AGORA, 0.0, 0.0)

    assert linha["clima"] == ""
    assert linha["codigo_clima"] == 77


def test_chama_a_api_com_as_coordenadas_do_config(respostas):
    """A consulta usa a URL e as coordenadas do config, pede os sete campos atuais, fixa
    o fuso e não fica pendurada sem timeout."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD)
    weather_collector.consultar_clima()

    url, kwargs = chamadas[0]
    assert url == config.API_CLIMA
    assert kwargs["params"]["latitude"] == config.LATITUDE
    assert kwargs["params"]["longitude"] == config.LONGITUDE
    assert kwargs["params"]["timezone"] == config.FUSO_HORARIO
    assert kwargs["params"]["current"].split(",") == [
        "temperature_2m", "apparent_temperature", "relative_humidity_2m",
        "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m",
    ]
    assert kwargs["timeout"] > 0


def test_devolve_o_bloco_atual(respostas):
    """Resposta bem formada entrega o bloco `current` tal como veio."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD)

    assert weather_collector.consultar_clima() == ATUAL


@pytest.mark.parametrize("payload", [{}, {"current": None}, {"current": []}, [], "erro"])
def test_json_sem_o_bloco_atual_levanta_erro(respostas, payload):
    """JSON fora do formato falha alto em vez de devolver dicionário vazio: numa coleta
    agendada, gravar nada em silêncio custa mais caro do que quebrar."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(payload)

    with pytest.raises(ValueError, match="formato inesperado"):
        weather_collector.consultar_clima()


def test_erro_http_sobe(respostas):
    """Um 500 da Open-Meteo não é engolido: quem chamou decide o que fazer."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD, erro=requests.HTTPError("500"))

    with pytest.raises(requests.HTTPError):
        weather_collector.consultar_clima()


def test_linha_carrega_todos_os_campos_da_api():
    """Cada campo da API cai na sua coluna, e as coordenadas usadas na consulta vão
    junto, para o histórico continuar legível depois que alguém editar o config."""
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
    """O CSV de clima nasce com as colunas de COLUNAS_CLIMA, na ordem declarada."""
    caminho = weather_collector.salvar_leitura(ATUAL, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df.columns) == weather_collector.COLUNAS_CLIMA
    assert df.loc[0, "clima"] == "Encoberto"
    assert df.loc[0, "temperatura"] == "24.4"


def test_cria_o_diretorio_se_nao_existir(tmp_path):
    """A primeira coleta numa máquina nova cria o diretório, em vez de estourar."""
    destino = tmp_path / "ainda-nao-existe"
    caminho = weather_collector.salvar_leitura(ATUAL, str(destino), AGORA)

    assert destino.is_dir()
    assert os.path.exists(caminho)


def test_mesmo_balde_de_quinze_minutos_nao_duplica(tmp_path):
    """Duas coletas dentro do mesmo balde de quinze minutos leem o mesmo instante da
    API, então atualizam a linha em vez de repetir: o coletado_em passa a ser o da
    segunda, e o histórico não incha com leituras idênticas."""
    weather_collector.salvar_leitura(ATUAL, str(tmp_path), AGORA)
    caminho = weather_collector.salvar_leitura(
        dict(ATUAL, temperature_2m=25.1), str(tmp_path), datetime(2026, 8, 16, 16, 58, 0)
    )
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "temperatura"] == "25.1"
    assert df.loc[0, "coletado_em"] == "2026-08-16T16:58:00"


def test_baldes_diferentes_viram_duas_linhas(tmp_path):
    """Virado o balde, a leitura nova entra como registro próprio: é o histórico que o
    tratamento vai consultar para achar a observação mais próxima de cada reserva."""
    weather_collector.salvar_leitura(ATUAL, str(tmp_path), AGORA)
    caminho = weather_collector.salvar_leitura(
        dict(ATUAL, time="2026-08-16T17:00"), str(tmp_path), datetime(2026, 8, 16, 17, 2, 0)
    )
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df["data_hora"]) == ["2026-08-16T16:45", "2026-08-16T17:00"]


def test_arquivo_de_clima_nao_casa_com_o_glob_das_quadras():
    """O sufixo do arquivo de clima é diferente de propósito: o tratamento varre as
    quadras por padrão de nome, e um clima-extracoes.csv seria tratado como quadra."""
    assert not fnmatch.fnmatch(weather_collector.ARQUIVO_CLIMA, "*" + persistencia.SUFIXO_CSV)


def test_coletar_clima_consulta_e_grava(respostas, tmp_path):
    """A fachada que o gerenciador chama faz as duas etapas: quem orquestra não precisa
    saber que existem uma consulta e uma gravação."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(PAYLOAD)
    caminho = weather_collector.coletar_clima(str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert os.path.basename(caminho) == weather_collector.ARQUIVO_CLIMA
    assert df.loc[0, "data_hora"] == "2026-08-16T16:45"
