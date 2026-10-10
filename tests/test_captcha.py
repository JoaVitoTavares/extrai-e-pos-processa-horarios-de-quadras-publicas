"""Testes do detector da frase de captcha, sem acessar o site real."""

import pytest

from extrator import captcha
from extrator import courts_collector


class FakePage:
    def __init__(self, text):
        self.text = text

    def locator(self, selector):
        return self

    def inner_text(self):
        return self.text


def test_detects_the_not_a_robot_phrase():
    assert captcha.captcha_detected(FakePage('Marque a caixa "Não sou um robô"')) is True


def test_detects_the_phrase_in_lowercase():
    assert captcha.captcha_detected(FakePage("não sou um robô")) is True


def test_ordinary_page_is_not_captcha():
    assert captcha.captcha_detected(FakePage("Horários disponíveis para a quadra")) is False


class _Browser:
    def launch(self, **kwargs):
        return self

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self

    def goto(self, *args, **kwargs):
        return None

    def close(self):
        return None

    def locator(self, selector):
        return self


class _Playwright:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def chromium(self):
        return _Browser()


def test_collection_checks_the_detector_when_the_page_opens(monkeypatch):
    order = []
    monkeypatch.setattr(courts_collector, "wait_between_accesses", lambda: None)
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", False)
    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: _Playwright())
    monkeypatch.setattr(
        courts_collector, "captcha_detected",
        lambda page: order.append("captcha") or False,
    )
    monkeypatch.setattr(
        courts_collector, "_choose_sport",
        lambda *a, **k: order.append("sport") or False,
    )

    def fake_goto(*args, **kwargs):
        order.append("goto")

    monkeypatch.setattr(_Browser, "goto", fake_goto)
    courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    assert order[:2] == ["goto", "captcha"]


def _collect_with_pause_after(monkeypatch, pause_at):
    """Abre um navegador falso e liga a pausa a partir da enésima consulta."""
    checks = {"n": 0}
    collected = []

    def is_paused(moment=None):
        checks["n"] += 1
        return checks["n"] >= pause_at

    def collect_day(page, sport, day, periods, with_price, types):
        collected.append(day)
        return [{
            "quadra": "Quadra 1",
            "data": day.isoformat(),
            "horarios": [{"hora": "20:00", "status": "Livre"}],
            "aviso": None,
        }]

    monkeypatch.setattr(courts_collector, "is_paused", is_paused)
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", False)
    monkeypatch.setattr(courts_collector, "simulate_human_failure", lambda *args, **kwargs: None)
    monkeypatch.setattr(courts_collector, "_choose_sport", lambda *args, **kwargs: True)
    monkeypatch.setattr(courts_collector, "extract_address", lambda *args, **kwargs: "Rua 1, Cidade")
    monkeypatch.setattr(courts_collector, "captcha_detected", lambda page: False)
    monkeypatch.setattr(courts_collector, "_select_day", lambda *args, **kwargs: None)
    monkeypatch.setattr(courts_collector, "_collect_day", collect_day)
    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: _Playwright())
    return collected


def test_pause_between_days_keeps_the_days_already_read(monkeypatch):
    collected = _collect_with_pause_after(monkeypatch, pause_at=3)

    results = courts_collector.collect_schedules(
        "Grama 5", "https://webarena.app/arena/x", days_ahead=1, days_from=0
    )

    assert len(collected) == 1
    assert len(results) == 1
    assert results[0]["data"] == collected[0].isoformat()
    assert results[0]["endereco"] == "Rua 1, Cidade"
    assert results[0]["horarios"][0]["status"] == "Livre"


def test_pause_before_any_day_still_aborts_the_sport(monkeypatch):
    _collect_with_pause_after(monkeypatch, pause_at=2)

    with pytest.raises(courts_collector.CaptchaPause):
        courts_collector.collect_schedules(
            "Grama 5", "https://webarena.app/arena/x", days_ahead=1, days_from=0
        )
