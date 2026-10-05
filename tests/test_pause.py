"""Testes da trava persistente de pausa após captcha."""

from datetime import date, datetime, timedelta
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


def test_invalid_lock_text_does_not_pause(tmp_path, monkeypatch):
    path = tmp_path / "lock"
    path.write_text("nao-e-uma-data", encoding="utf-8")
    monkeypatch.setattr(pause, "pause_lock_path", lambda: str(path))

    assert pause.is_paused(datetime(2026, 10, 3, 10, 0, tzinfo=ZONE)) is False


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


def test_pause_between_days_stops_before_the_next_day(monkeypatch):
    selected = []
    checks = {"count": 0}

    def is_paused(moment=None):
        checks["count"] += 1
        return checks["count"] >= 3

    class Browser:
        def launch(self, **kwargs):
            return self

        def new_context(self, **kwargs):
            return self

        def new_page(self):
            return self

        def goto(self, *args, **kwargs):
            return None

        def locator(self, selector):
            return self

        def close(self):
            return None

    class Playwright:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def chromium(self):
            return Browser()

    monkeypatch.setattr(courts_collector, "is_paused", is_paused)
    monkeypatch.setattr(courts_collector, "wait_between_accesses", lambda: None)
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", False)
    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: Playwright())
    monkeypatch.setattr(courts_collector, "captcha_detected", lambda page: False)
    monkeypatch.setattr(courts_collector, "_choose_sport", lambda *args, **kwargs: True)
    monkeypatch.setattr(courts_collector, "simulate_human_failure", lambda *args, **kwargs: None)
    monkeypatch.setattr(courts_collector, "extract_address", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        courts_collector, "collection_days",
        lambda *args, **kwargs: [date(2026, 10, 3), date(2026, 10, 4)],
    )
    monkeypatch.setattr(
        courts_collector, "_select_day",
        lambda page, day, **kwargs: selected.append(day),
    )
    monkeypatch.setattr(
        courts_collector, "_collect_day",
        lambda *args, **kwargs: [{"quadra": "Areia 1"}],
    )

    with pytest.raises(pause.CaptchaPause, match="coleta pausada por captcha"):
        courts_collector.collect_schedules("Grama 5", "https://webarena.app/arena/x")

    assert selected == [date(2026, 10, 3)]
