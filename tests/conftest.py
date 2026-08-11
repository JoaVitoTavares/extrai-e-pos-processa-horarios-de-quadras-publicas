"""Fixtures compartilhadas pelos testes do coletor."""

import os

import pytest
from playwright.sync_api import sync_playwright

DIRETORIO_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


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
