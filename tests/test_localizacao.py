"""Testes da resolução do endereço da arena em coordenadas, com o Nominatim dublado."""

import fnmatch
import json

import pytest
import requests

from extrator import config
from extrator import localizacao
from extrator import persistencia
from conftest import RespostaFalsa

ENDERECO = "20 de Junho 54, Parobé"
ACHADO = {
    "lat": "-29.6509717",
    "lon": "-50.8169235",
    "category": "highway",
    "display_name": "Rua 20 de Junho, Parobé, Rio Grande do Sul, Brasil",
    "address": {"road": "Rua 20 de Junho", "town": "Parobé", "state": "Rio Grande do Sul"},
}


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(localizacao.time, "sleep", lambda segundos: None)


def quadra(endereco):
    return {"quadra": "Areia 1", "endereco": endereco}


def test_endereco_observado_fica_com_o_mais_repetido():
    resultados = [quadra(ENDERECO), quadra(""), quadra(ENDERECO), quadra("Outro 1, Canoas")]

    assert localizacao.endereco_observado(resultados) == ENDERECO


def test_endereco_observado_sem_nenhuma_leitura():
    assert localizacao.endereco_observado([quadra(""), {"quadra": "Areia 2"}]) == ""


def test_endereco_em_branco_nao_entra_na_contagem():
    assert localizacao.endereco_observado([quadra("   "), quadra(ENDERECO)]) == ENDERECO


def test_endereco_empatado_fica_com_o_primeiro_visto():
    outro = "Boqueirão 2710, Canoas"
    resultados = [quadra(outro), quadra(ENDERECO), quadra(outro), quadra(ENDERECO)]

    assert localizacao.endereco_observado(resultados) == outro


@pytest.mark.parametrize(
    "endereco, esperado",
    [
        ("20 de Junho 54, Parobé", ["20 de Junho 54, Parobé", "20 de Junho, Parobé", "Parobé"]),
        ("Boqueirão 2710, Canoas", ["Boqueirão 2710, Canoas", "Boqueirão, Canoas", "Canoas"]),
        ("Av. Brasil, 1200, Canoas", ["Av. Brasil, 1200, Canoas", "Av. Brasil, Canoas", "Canoas"]),
        ("Parobé", ["Parobé"]),
    ],
)
def test_variacoes_descem_do_especifico_para_o_generico(endereco, esperado):
    assert localizacao.variacoes_da_consulta(endereco) == esperado


def test_consulta_identifica_a_aplicacao_e_filtra_o_pais(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.consultar_geocodificacao(ENDERECO)

    url, kwargs = chamadas[0]
    assert url == config.API_GEOCODIFICACAO
    assert kwargs["params"]["q"] == ENDERECO
    assert kwargs["params"]["countrycodes"] == config.PAIS_DAS_ARENAS
    assert kwargs["headers"]["User-Agent"] == config.IDENTIFICACAO_GEOCODIFICACAO
    assert kwargs["timeout"] > 0


def test_geocodifica_endereco_em_coordenadas_e_cidade(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    local = localizacao.geocodificar(ENDERECO)

    assert (local["latitude"], local["longitude"]) == (-29.6509717, -50.8169235)
    assert local["cidade"] == "Parobé"
    assert local["endereco"] == ENDERECO


def test_desce_para_a_consulta_seguinte_quando_nao_ha_resultado(monkeypatch):
    consultas = []

    def get_falso(url, **kwargs):
        consultas.append(kwargs["params"]["q"])
        return RespostaFalsa([ACHADO] if consultas[-1] == "Parobé" else [])

    monkeypatch.setattr(requests, "get", get_falso)
    local = localizacao.geocodificar(ENDERECO)

    assert consultas == ["20 de Junho 54, Parobé", "20 de Junho, Parobé", "Parobé"]
    assert local["origem"] == "Parobé"


def test_endereco_que_nenhuma_consulta_resolve_devolve_none(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([])

    assert localizacao.geocodificar(ENDERECO) is None


def test_resposta_sem_coordenada_falha_alto(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"display_name": "sem lat nem lon"}])

    with pytest.raises(ValueError, match="formato inesperado"):
        localizacao.geocodificar(ENDERECO)


def test_json_que_nao_e_lista_nao_e_um_achado(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa({"error": "Unable to geocode"})

    assert localizacao.consultar_geocodificacao(ENDERECO) is None


def test_erro_na_primeira_consulta_tenta_a_seguinte(monkeypatch):
    consultas = []

    def get_falso(url, **kwargs):
        consultas.append(kwargs["params"]["q"])
        if len(consultas) == 1:
            return RespostaFalsa({"error": "Unable to geocode"})
        return RespostaFalsa([ACHADO])

    monkeypatch.setattr(requests, "get", get_falso)
    local = localizacao.geocodificar(ENDERECO)

    assert consultas[0] == ENDERECO
    assert local["origem"] == "20 de Junho, Parobé"
    assert local["cidade"] == "Parobé"


def test_erro_http_sobe(respostas):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO], erro=requests.HTTPError("500"))

    with pytest.raises(requests.HTTPError):
        localizacao.geocodificar(ENDERECO)


def test_resolver_grava_o_local_no_diretorio_da_arena(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    gravado = json.loads((tmp_path / localizacao.ARQUIVO_LOCAL).read_text(encoding="utf-8"))

    assert gravado["endereco"] == ENDERECO
    assert gravado["cidade"] == "Parobé"
    assert gravado["resolvido_em"]


def test_endereco_ja_conhecido_nao_consulta_de_novo(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    local = localizacao.resolver_local(ENDERECO, str(tmp_path))

    assert len(chamadas) == 1
    assert local["cidade"] == "Parobé"


def test_rodada_sem_endereco_legivel_fica_com_o_local_conhecido(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    local = localizacao.resolver_local("", str(tmp_path))

    assert len(chamadas) == 1
    assert local["latitude"] == -29.6509717


def test_endereco_novo_que_o_mapa_recusa_nao_herda_o_antigo(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    get_falso.resposta = RespostaFalsa([])

    assert localizacao.resolver_local("Outro Lugar 9, Canoas", str(tmp_path)) is None


def test_coordenadas_do_config_dispensam_o_geocodificador(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    local = localizacao.resolver_local(ENDERECO, str(tmp_path), coordenadas=(-29.65, -50.81))

    assert chamadas == []
    assert (local["latitude"], local["longitude"]) == (-29.65, -50.81)
    assert local["origem"] == "config"


def test_sem_endereco_e_sem_cache_devolve_none(tmp_path):
    assert localizacao.resolver_local("", str(tmp_path)) is None


def test_local_corrompido_conta_como_cache_vazio(respostas, tmp_path):
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    (tmp_path / localizacao.ARQUIVO_LOCAL).write_text('{"endereco": "20 de J', encoding="utf-8")
    local = localizacao.resolver_local(ENDERECO, str(tmp_path))

    assert len(chamadas) == 1
    assert local["cidade"] == "Parobé"


def test_arquivo_do_local_nao_casa_com_o_glob_das_quadras():
    assert not fnmatch.fnmatch(localizacao.ARQUIVO_LOCAL, "*" + persistencia.SUFIXO_CSV)
