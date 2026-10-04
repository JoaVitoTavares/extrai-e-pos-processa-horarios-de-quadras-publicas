"""Testes da trava persistente de pausa após captcha."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from extrator import pause
from extrator import courts_collector
from extrator import arena_extractor
import main
from test_main import ARENA, quadra

ZONE = ZoneInfo("America/Sao_Paulo")


def test_lock_lasts_two_hours_in_the_sao_paulo_timezone(tmp_path, monkeypatch):
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(tmp_path / "lock"))
    now = datetime(2026, 10, 3, 10, 0, tzinfo=ZONE)
    pause.engage_captcha_pause(now)

    assert pause.is_paused(now) is True
    assert pause.is_paused(now + timedelta(hours=2) - timedelta(seconds=1)) is True
    assert pause.is_paused(now + timedelta(hours=2)) is False


def test_without_a_lock_file_it_is_not_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(tmp_path / "missing"))
    assert pause.is_paused(datetime(2026, 10, 3, 10, 0, tzinfo=ZONE)) is False


def test_blank_lock_file_is_not_paused(tmp_path, monkeypatch):
    path = tmp_path / "lock"
    path.write_text("  \n", encoding="utf-8")
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(path))

    assert pause.is_paused(datetime(2026, 10, 3, 10, 0, tzinfo=ZONE)) is False


def test_naive_lock_is_read_in_sao_paulo_time(tmp_path, monkeypatch):
    path = tmp_path / "lock"
    path.write_text("2026-10-03T12:00:00", encoding="utf-8")
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(path))

    assert pause.is_paused(datetime(2026, 10, 3, 11, 59, tzinfo=ZONE)) is True
    assert pause.is_paused(datetime(2026, 10, 3, 12, 0, tzinfo=ZONE)) is False


def test_utc_lock_is_compared_in_sao_paulo_time(tmp_path, monkeypatch):
    path = tmp_path / "lock"
    path.write_text("2026-10-03T15:00:00+00:00", encoding="utf-8")
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(path))

    assert pause.is_paused(datetime(2026, 10, 3, 11, 59, tzinfo=ZONE)) is True
    assert pause.is_paused(datetime(2026, 10, 3, 12, 0, tzinfo=ZONE)) is False


def test_paused_collection_does_not_open_the_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(courts_collector, "is_paused", lambda moment=None: True)
    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: opened.append("browser"))

    with pytest.raises(pause.CaptchaPause):
        courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    assert opened == []


def test_round_stops_while_the_lock_is_still_active(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main, "is_paused", lambda moment=None: True)
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    accessed = []
    monkeypatch.setattr(main, "wait_between_accesses", lambda: accessed.append("wait"))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: accessed.append("courts") or [quadra()],
    )

    main.main()

    assert accessed == []
    assert "pausad" in capsys.readouterr().out.lower()


def test_captcha_writes_the_two_hour_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(tmp_path / "lock"))
    monkeypatch.setattr(courts_collector, "engage_captcha_pause", pause.engage_captcha_pause)
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

    with pytest.raises(pause.CaptchaPause):
        courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    until = datetime.fromisoformat((tmp_path / "lock").read_text().strip())
    assert until.tzinfo is not None
    now = datetime.now(ZONE)
    assert timedelta(hours=1, minutes=50) <= (until - now) <= timedelta(hours=2, minutes=1)
