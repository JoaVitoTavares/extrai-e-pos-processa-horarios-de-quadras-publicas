"""Testes do aviso por e-mail em captcha e falhas, sem SMTP real."""

import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from extrator import arena_extractor
from extrator import courts_collector
from extrator import email_config
import main
from test_main import ARENA


def test_envia_um_email_com_os_dados_do_env(monkeypatch):
    enviados = []

    class SMTPFalso:
        def __init__(self, host, port):
            enviados.append({"host": host, "port": port})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            enviados.append("starttls")

        def login(self, user, password):
            enviados.append({"user": user, "password": password})

        def send_message(self, message):
            enviados.append({"to": message["To"], "subject": message["Subject"], "body": message.get_content()})

    monkeypatch.setattr(email_config.smtplib, "SMTP", SMTPFalso)
    email_config.send_alert(
        "assunto",
        "corpo",
        settings={
            "host": "smtp.exemplo.com",
            "port": 587,
            "user": "aviso@exemplo.com",
            "password": "segredo",
            "recipient": "destino@exemplo.com",
        },
    )

    assert enviados[0] == {"host": "smtp.exemplo.com", "port": 587}
    assert {"user": "aviso@exemplo.com", "password": "segredo"} in enviados
    assert enviados[-1]["to"] == "destino@exemplo.com"
    assert enviados[-1]["subject"] == "assunto"
    assert "corpo" in enviados[-1]["body"]


def test_sem_servidor_configurado_nao_tenta_enviar():
    email_config.send_alert(
        "x", "y",
        settings={"host": "", "port": 587, "user": "", "password": "", "recipient": "a@b.c"},
    )


def test_captcha_dispara_um_email(monkeypatch):
    avisos = []
    monkeypatch.setattr(courts_collector, "send_alert", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(courts_collector, "captcha_detected", lambda page: True)
    monkeypatch.setattr(courts_collector, "wait_between_accesses", lambda: None)
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", False)

    class Navegador:
        def launch(self, **kwargs):
            return self
        def new_context(self, **kwargs):
            return self
        def new_page(self):
            return self
        def goto(self, *a, **k):
            return None
        def close(self):
            return None
        def locator(self, sel):
            return self
        def inner_text(self):
            return ""

    class Playwright:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        @property
        def chromium(self):
            return Navegador()

    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: Playwright())
    monkeypatch.setattr(courts_collector, "_choose_sport", lambda *a, **k: False)
    monkeypatch.setattr(courts_collector, "engage_captcha_pause", lambda: None)

    with pytest.raises(courts_collector.CaptchaPause):
        courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    assert len(avisos) == 1
    assert "captcha" in avisos[0][0].lower()


def test_excecao_da_arena_dispara_um_email(monkeypatch):
    avisos = []
    monkeypatch.setattr(arena_extractor, "send_alert", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: (_ for _ in ()).throw(PWTimeout("tempo")),
    )
    extractor = arena_extractor.ArenaExtractor(main.normalize_arena_info(ARENA))

    extractor.extract_isolating_failures()

    assert len(avisos) == 1
    assert "tempo" in avisos[0][1].lower() or "tempo" in avisos[0][0].lower()
