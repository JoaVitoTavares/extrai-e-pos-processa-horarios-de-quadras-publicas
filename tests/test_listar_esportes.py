"""Testes da técnica de API JSON, com a resposta HTTP substituída por um dublê."""

import pytest
import requests

import coletor

ESPORTES = ["Beach Tennis", "Futebol de salão", "Grama 5", "Grama 7", "Handebol", "Vôlei de praia"]


class RespostaFalsa:
    """Dublê de resposta do requests: expõe só o que listar_esportes consome, que é
    raise_for_status e json. Aqui não há motor CSS envolvido, só desserialização, então
    o dublê cobre o contrato inteiro."""

    def __init__(self, payload, erro=None):
        self.payload = payload
        self.erro = erro

    def raise_for_status(self):
        if self.erro:
            raise self.erro

    def json(self):
        return self.payload


@pytest.fixture
def respostas(monkeypatch):
    """Troca requests.get por um dublê e devolve a lista onde as chamadas ficam
    registradas, para os testes checarem também como a API foi chamada."""
    chamadas = []

    def get_falso(url, **kwargs):
        chamadas.append((url, kwargs))
        return get_falso.resposta

    monkeypatch.setattr(coletor.requests, "get", get_falso)
    return chamadas, get_falso


def test_devolve_a_lista_do_json(respostas):
    """Resposta bem formada entrega a lista de esportes tal como veio."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])

    assert coletor.listar_esportes() == ESPORTES


def test_chama_a_api_com_a_arena_e_timeout(respostas):
    """A chamada aponta para a arena certa e não fica pendurada sem timeout."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])
    coletor.listar_esportes()

    url, kwargs = chamadas[0]
    assert url == coletor.API_INIT
    assert kwargs["params"] == {"location": coletor.URL_ARENA}
    assert kwargs["timeout"] > 0


def test_propaga_erro_http(respostas):
    """Erro HTTP sobe em vez de virar lista vazia, senão o cron gravaria nada em
    silêncio e o buraco no dataset só apareceria semanas depois."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(None, erro=requests.HTTPError("500"))

    with pytest.raises(requests.HTTPError):
        coletor.listar_esportes()


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
    """Formato diferente do esperado levanta ValueError dizendo o que houve, em vez de
    estourar um KeyError cru ou devolver [] mudo."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa(payload)

    with pytest.raises(ValueError, match="formato inesperado"):
        coletor.listar_esportes()


def test_esportes_alvo_filtra_os_tipos_de_interesse():
    """A coleta percorre os quatro tipos de quadra que interessam ao TCC; Beach Tennis e
    Handebol existem no site mas ficam de fora."""
    assert coletor._esportes_alvo(ESPORTES) == [
        "Futebol de salão", "Grama 5", "Grama 7", "Vôlei de praia"
    ]


def test_esportes_alvo_devolve_o_nome_como_o_site_escreve():
    """O nome volta exatamente como veio da API, porque é ele que o clique procura na
    tela; a comparação é que ignora acento e caixa."""
    assert coletor._esportes_alvo(["Volei de praia", "GRAMA 7"]) == ["Volei de praia", "GRAMA 7"]


@pytest.mark.parametrize(
    "do_site, esperado",
    [
        ([], []),
        (["Handebol", "Beach Tennis"], []),
        (["Handebol", "Grama 5"], ["Grama 5"]),
    ],
)
def test_esportes_alvo_ignora_o_que_nao_interessa(do_site, esperado):
    """Um site sem alguns dos tipos devolve só os presentes, sem estourar."""
    assert coletor._esportes_alvo(do_site) == esperado
