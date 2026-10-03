"""Fixtures compartilhadas pelos testes do coletor."""

import os
import sys

import pytest
import requests
from playwright.sync_api import sync_playwright

DIRETORIO_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class RespostaFalsa:
    def __init__(self, payload, erro=None):
        self.payload = payload
        self.erro = erro

    def raise_for_status(self):
        if self.erro:
            raise self.erro

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def argv_sem_os_argumentos_do_pytest(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])


@pytest.fixture(autouse=True)
def sem_pausa_real_entre_acessos(monkeypatch):
    """Evita que os testes esperem o intervalo aleatório de verdade."""
    monkeypatch.setattr("extrator.timing.time.sleep", lambda segundos: None)


@pytest.fixture(autouse=True)
def night_access_allowed_in_tests(monkeypatch):
    """Mantém as rodadas de teste fora da trava da madrugada, salvo quando o teste a exercita."""
    monkeypatch.setattr("main.night_access_allowed", lambda moment=None: True)


@pytest.fixture(autouse=True)
def no_captcha_pause_lock(monkeypatch, request):
    """Evita que uma trava de captcha residual derrube a suíte, salvo nos testes da própria trava."""
    if request.module.__name__.endswith("test_pause"):
        return
    monkeypatch.setattr("extrator.pause.is_paused", lambda moment=None: False)
    monkeypatch.setattr("extrator.courts_collector.is_paused", lambda moment=None: False)
    monkeypatch.setattr("main.is_paused", lambda moment=None: False)


@pytest.fixture
def respostas(monkeypatch):
    chamadas = []

    def get_falso(url, **kwargs):
        chamadas.append((url, kwargs))
        return get_falso.resposta

    monkeypatch.setattr(requests, "get", get_falso)
    return chamadas, get_falso


def carregar_html(pagina, nome_arquivo: str):
    caminho = os.path.join(DIRETORIO_FIXTURES, nome_arquivo)
    with open(caminho, encoding="utf-8") as arquivo:
        pagina.set_content(arquivo.read())
    return pagina


@pytest.fixture(scope="session")
def navegador():
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=True)
        yield navegador
        navegador.close()


@pytest.fixture
def pagina(navegador):
    pagina = navegador.new_page()
    yield pagina
    pagina.close()


@pytest.fixture
def carregar_fixture(pagina):
    return lambda nome_arquivo: carregar_html(pagina, nome_arquivo)
