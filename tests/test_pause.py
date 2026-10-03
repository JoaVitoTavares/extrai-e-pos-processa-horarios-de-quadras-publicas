"""Testes da trava persistente de pausa após captcha."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from extrator import pause
from extrator import courts_collector
from extrator import arena_extractor
import main
from test_main import ARENA, quadra

FUSO = ZoneInfo("America/Sao_Paulo")


def test_trava_dura_duas_horas_no_fuso_de_sao_paulo(tmp_path, monkeypatch):
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(tmp_path / "trava"))
    agora = datetime(2026, 10, 3, 10, 0, tzinfo=FUSO)
    pause.engage_captcha_pause(agora)

    assert pause.is_paused(agora) is True
    assert pause.is_paused(agora + timedelta(hours=2) - timedelta(seconds=1)) is True
    assert pause.is_paused(agora + timedelta(hours=2)) is False


def test_sem_arquivo_de_trava_nao_esta_pausado(tmp_path, monkeypatch):
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(tmp_path / "inexistente"))
    assert pause.is_paused(datetime(2026, 10, 3, 10, 0, tzinfo=FUSO)) is False


def test_rodada_encerra_se_a_trava_ainda_vale(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main, "is_paused", lambda moment=None: True)
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    acessou = []
    monkeypatch.setattr(main, "wait_between_accesses", lambda: acessou.append("espera"))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: acessou.append("quadras") or [quadra()],
    )

    main.main()

    assert acessou == []
    assert "pausad" in capsys.readouterr().out.lower()


def test_captcha_grava_a_trava_de_duas_horas(monkeypatch, tmp_path):
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(tmp_path / "trava"))
    monkeypatch.setattr(courts_collector, "engage_captcha_pause", pause.engage_captcha_pause)
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

    with pytest.raises(pause.CaptchaPause):
        courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    ate = datetime.fromisoformat((tmp_path / "trava").read_text().strip())
    assert ate.tzinfo is not None
    agora = datetime.now(FUSO)
    assert timedelta(hours=1, minutes=50) <= (ate - agora) <= timedelta(hours=2, minutes=1)
