"""Testes da técnica de API JSON, com a resposta HTTP substituída por um dublê."""

import pytest
import requests

from extrator import courts_collector
from conftest import RespostaFalsa

ARENA = "https://webarena.app/arena/sp-sports"
ESPORTES = ["Beach Tennis", "Futebol de salão", "Grama 5", "Grama 7", "Handebol", "Vôlei de praia"]


@pytest.mark.parametrize(
    "url_arena, esperado",
    [
        ("https://webarena.app/arena/sp-sports", "https://webarena.app/api/1.1/init/data"),
        ("https://webarena.app/arena/outra-quadra/", "https://webarena.app/api/1.1/init/data"),
        ("https://outro-site.com.br/arena/x", "https://outro-site.com.br/api/1.1/init/data"),
    ],
)
def test_api_json_sai_da_url_da_arena(url_arena, esperado):
    assert courts_collector.api_init_url(url_arena) == esperado


def test_devolve_a_lista_do_json(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])

    assert courts_collector.list_sports(ARENA) == ESPORTES


def test_espaco_das_pontas_do_nome_do_esporte_cai(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": [" Futebol society "]}}])

    assert courts_collector.list_sports(ARENA) == ["Futebol society"]


def test_chama_a_api_com_a_arena_e_timeout(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])
    courts_collector.list_sports(ARENA)

    url, kwargs = chamadas[0]
    assert url == "https://webarena.app/api/1.1/init/data"
    assert kwargs["params"] == {"location": ARENA}
    assert kwargs["timeout"] > 0


def test_propaga_erro_http(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(None, erro=requests.HTTPError("500"))

    with pytest.raises(requests.HTTPError):
        courts_collector.list_sports(ARENA)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [{"data": {}}],
        [{"outra_coisa": {}}],
        {"data": {"esportes_list_text": ESPORTES}},
    ],
)
def test_json_em_formato_inesperado_falha_explicitamente(respostas, payload):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(payload)

    with pytest.raises(ValueError, match="formato inesperado"):
        courts_collector.list_sports(ARENA)


def test_esportes_alvo_filtra_os_tipos_de_interesse():
    assert courts_collector.filter_target_sports(ESPORTES) == [
        "Futebol de salão", "Grama 5", "Grama 7", "Vôlei de praia"
    ]


def test_esportes_alvo_devolve_o_nome_como_o_site_escreve():
    assert courts_collector.filter_target_sports(["Volei de praia", "GRAMA 7"]) == ["Volei de praia", "GRAMA 7"]


@pytest.mark.parametrize(
    "do_site, esperado",
    [
        ([], []),
        (["Handebol", "Beach Tennis"], []),
        (["Handebol", "Grama 5"], ["Grama 5"]),
    ],
)
def test_esportes_alvo_ignora_o_que_nao_interessa(do_site, esperado):
    assert courts_collector.filter_target_sports(do_site) == esperado


def test_tipos_ausentes_lista_o_que_sumiu_do_site():
    assert courts_collector.missing_court_types(courts_collector.COURT_TYPES) == []
    assert courts_collector.missing_court_types(["Grama 5", "Grama 7"]) == [
        "Vôlei de praia", "Futebol de salão"
    ]


def test_tipos_ausentes_reconhece_o_nome_sem_acento():
    assert "Vôlei de praia" not in courts_collector.missing_court_types(["Volei de praia"])


@pytest.mark.parametrize(
    "do_site, tipos, esperado",
    [
        (["Futebol society"], ["Futebol society"], ["Futebol society"]),
        (["Futebol Society"], ["Futebol society"], ["Futebol Society"]),
        (["Futsal", "Vôlei", "Basquete"], ["Futebol de salão"], ["Futsal"]),
        (["Beach Tennis", "Futevôlei", "Vôlei de Praia"], ["Vôlei de praia"], ["Vôlei de Praia"]),
        (ESPORTES, ["Grama 7"], ["Grama 7"]),
    ],
)
def test_esportes_alvo_usa_o_catalogo_da_arena(do_site, tipos, esperado):
    assert courts_collector.filter_target_sports(do_site, tipos) == esperado


def test_tipos_ausentes_pergunta_pelo_catalogo_da_arena():
    assert courts_collector.missing_court_types(["Futebol society"], ["Futebol society"]) == []
    assert courts_collector.missing_court_types([], ["Futebol society"]) == ["Futebol society"]
