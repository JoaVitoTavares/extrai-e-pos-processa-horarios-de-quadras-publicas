"""Fixtures compartilhadas pelos testes do coletor."""

import os

import pytest
import requests
from playwright.sync_api import sync_playwright

DIRETORIO_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class RespostaFalsa:
    """Dublê de resposta do requests: expõe só o que os coletores consomem, que é
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
    registradas, para os testes checarem também como a API foi chamada. O patch é no
    módulo requests, então serve a qualquer coletor que o importe."""
    chamadas = []

    def get_falso(url, **kwargs):
        chamadas.append((url, kwargs))
        return get_falso.resposta

    monkeypatch.setattr(requests, "get", get_falso)
    return chamadas, get_falso


def carregar_html(pagina, nome_arquivo: str):
    """Lê um arquivo de tests/fixtures e o injeta na página via set_content, sem tocar
    na rede. Devolve a própria página, pronta para os seletores do coletor rodarem
    contra um DOM de verdade."""
    caminho = os.path.join(DIRETORIO_FIXTURES, nome_arquivo)
    with open(caminho, encoding="utf-8") as arquivo:
        pagina.set_content(arquivo.read())
    return pagina


@pytest.fixture(scope="session")
def navegador():
    """Sobe um Chromium único para toda a sessão: abrir um navegador por teste
    dominaria o tempo da suíte."""
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=True)
        yield navegador
        navegador.close()


@pytest.fixture
def pagina(navegador):
    """Abre uma aba nova por teste, isolando o DOM de um teste do outro."""
    pagina = navegador.new_page()
    yield pagina
    pagina.close()


@pytest.fixture
def carregar_fixture(pagina):
    """Entrega um atalho que injeta um arquivo de tests/fixtures na aba do teste, já
    amarrado à página desta execução."""
    return lambda nome_arquivo: carregar_html(pagina, nome_arquivo)
