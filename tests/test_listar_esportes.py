"""Testes da técnica de API JSON, com a resposta HTTP substituída por um dublê."""

import pytest
import requests

import courts_collector
from conftest import RespostaFalsa

ESPORTES = ["Beach Tennis", "Futebol de salão", "Grama 5", "Grama 7", "Handebol", "Vôlei de praia"]


def test_devolve_a_lista_do_json(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])

    assert courts_collector.listar_esportes() == ESPORTES


def test_chama_a_api_com_a_arena_e_timeout(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])
    courts_collector.listar_esportes()

    url, kwargs = chamadas[0]
    assert url == courts_collector.API_INIT
    assert kwargs["params"] == {"location": courts_collector.URL_ARENA}
    assert kwargs["timeout"] > 0


def test_propaga_erro_http(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(None, erro=requests.HTTPError("500"))

    with pytest.raises(requests.HTTPError):
        courts_collector.listar_esportes()


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
        courts_collector.listar_esportes()


def test_esportes_alvo_filtra_os_tipos_de_interesse():
    assert courts_collector.esportes_alvo(ESPORTES) == [
        "Futebol de salão", "Grama 5", "Grama 7", "Vôlei de praia"
    ]


def test_esportes_alvo_devolve_o_nome_como_o_site_escreve():
    """O nome volta exatamente como veio da API, porque é ele que o clique procura na
    tela; a comparação é que ignora acento e caixa."""
    assert courts_collector.esportes_alvo(["Volei de praia", "GRAMA 7"]) == ["Volei de praia", "GRAMA 7"]


@pytest.mark.parametrize(
    "do_site, esperado",
    [
        ([], []),
        (["Handebol", "Beach Tennis"], []),
        (["Handebol", "Grama 5"], ["Grama 5"]),
    ],
)
def test_esportes_alvo_ignora_o_que_nao_interessa(do_site, esperado):
    assert courts_collector.esportes_alvo(do_site) == esperado


def test_tipos_ausentes_lista_o_que_sumiu_do_site():
    assert courts_collector.tipos_ausentes(courts_collector.TIPOS_QUADRA) == []
    assert courts_collector.tipos_ausentes(["Grama 5", "Grama 7"]) == [
        "Vôlei de praia", "Futebol de salão"
    ]


def test_tipos_ausentes_reconhece_o_nome_sem_acento():
    assert "Vôlei de praia" not in courts_collector.tipos_ausentes(["Volei de praia"])
