"""Testes do detector da frase de captcha, sem acessar o site real."""

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


def test_blank_page_is_not_captcha():
    assert captcha.captcha_detected(FakePage("")) is False
    assert captcha.captcha_detected(FakePage(None)) is False


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
