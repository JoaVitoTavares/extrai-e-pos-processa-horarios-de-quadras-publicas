"""Testes do detector da frase de captcha, sem acessar o site real."""

from extrator import captcha
from extrator import courts_collector


class PaginaFalsa:
    def __init__(self, texto):
        self.texto = texto

    def locator(self, seletor):
        return self

    def inner_text(self):
        return self.texto


def test_detecta_a_frase_nao_sou_um_robo():
    assert captcha.captcha_detected(PaginaFalsa('Marque a caixa "Não sou um robô"')) is True


def test_detecta_a_frase_mesmo_em_caixa_baixa():
    assert captcha.captcha_detected(PaginaFalsa("não sou um robô")) is True


def test_pagina_comum_nao_e_captcha():
    assert captcha.captcha_detected(PaginaFalsa("Horários disponíveis para a quadra")) is False


class _Navegador:
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
        return _Navegador()


def test_coleta_consulta_o_detector_ao_abrir_a_pagina(monkeypatch):
    ordem = []
    monkeypatch.setattr(courts_collector, "wait_between_accesses", lambda: None)
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", False)
    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: _Playwright())
    monkeypatch.setattr(
        courts_collector, "captcha_detected",
        lambda page: ordem.append("captcha") or False,
    )
    monkeypatch.setattr(
        courts_collector, "_choose_sport",
        lambda *a, **k: ordem.append("esporte") or False,
    )

    def goto_falso(*args, **kwargs):
        ordem.append("goto")

    monkeypatch.setattr(_Navegador, "goto", goto_falso)
    courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    assert ordem[:2] == ["goto", "captcha"]
