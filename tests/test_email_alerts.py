"""Testes do aviso por e-mail em captcha e falhas, sem SMTP real."""

import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from extrator import arena_extractor
from extrator import courts_collector
from extrator import email_config
import main
from test_main import ARENA


def test_sends_one_email_with_the_env_settings(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port):
            sent.append({"host": host, "port": port})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent.append("starttls")

        def login(self, user, password):
            sent.append({"user": user, "password": password})

        def send_message(self, message):
            sent.append({"to": message["To"], "subject": message["Subject"], "body": message.get_content()})

    monkeypatch.setattr(email_config.smtplib, "SMTP", FakeSMTP)
    email_config.send_alert(
        "subject",
        "body",
        settings={
            "host": "smtp.exemplo.com",
            "port": 587,
            "user": "aviso@exemplo.com",
            "password": "segredo",
            "recipient": "destino@exemplo.com",
        },
    )

    assert sent[0] == {"host": "smtp.exemplo.com", "port": 587}
    assert {"user": "aviso@exemplo.com", "password": "segredo"} in sent
    assert sent[-1]["to"] == "destino@exemplo.com"
    assert sent[-1]["subject"] == "subject"
    assert "body" in sent[-1]["body"]


def test_without_a_configured_server_it_does_not_send():
    email_config.send_alert(
        "x", "y",
        settings={"host": "", "port": 587, "user": "", "password": "", "recipient": "a@b.c"},
    )


def test_non_numeric_port_does_not_open_smtp(monkeypatch):
    opened = []

    class FakeSMTP:
        def __init__(self, host, port):
            opened.append(port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(email_config.smtplib, "SMTP", FakeSMTP)

    email_config.send_alert(
        "assunto",
        "corpo",
        settings={
            "host": "smtp.exemplo.com",
            "port": "smtp",
            "user": "",
            "password": "",
            "recipient": "destino@exemplo.com",
        },
    )

    assert opened == []


def test_captcha_triggers_one_email(monkeypatch):
    alerts = []
    monkeypatch.setattr(courts_collector, "send_alert", lambda *a, **k: alerts.append(a))
    monkeypatch.setattr(courts_collector, "captcha_detected", lambda page: True)
    monkeypatch.setattr(courts_collector, "wait_between_accesses", lambda: None)
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", False)

    class Browser:
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
            return Browser()

    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: Playwright())
    monkeypatch.setattr(courts_collector, "_choose_sport", lambda *a, **k: False)
    monkeypatch.setattr(courts_collector, "engage_captcha_pause", lambda: None)

    with pytest.raises(courts_collector.CaptchaPause):
        courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    assert len(alerts) == 1
    assert "captcha" in alerts[0][0].lower()


def test_arena_exception_triggers_one_email(monkeypatch):
    alerts = []
    monkeypatch.setattr(arena_extractor, "send_alert", lambda *a, **k: alerts.append(a))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: (_ for _ in ()).throw(PWTimeout("timeout")),
    )
    extractor = arena_extractor.ArenaExtractor(main.normalize_arena_info(ARENA))

    extractor.extract_isolating_failures()

    assert len(alerts) == 1
    assert "timeout" in alerts[0][1].lower() or "timeout" in alerts[0][0].lower()
