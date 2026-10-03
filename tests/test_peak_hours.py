"""Testes dos horários de pico do dia seguinte, sem acessar o site real."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from extrator import access_windows
from extrator import arena_extractor
from extrator import config
from extrator import weather_collector
import main
from test_main import ARENA, LOCAL, quadra

ZONE = ZoneInfo("America/Sao_Paulo")
DAY = date(2026, 10, 3)


def _moment(hour, minute=0):
    return datetime(2026, 10, 3, hour, minute, tzinfo=ZONE)


def test_broken_time_stays_inside_the_window_and_off_the_hour():
    rand_num_gen = __import__("random").Random(0)
    for _ in range(200):
        morning = access_windows.broken_time_in_window(7, 9, rand_num_gen)
        evening = access_windows.broken_time_in_window(17, 20, rand_num_gen)
        assert time(7, 1) <= morning < time(9, 0)
        assert morning.minute != 0
        assert time(17, 1) <= evening < time(20, 0)
        assert evening.minute != 0


def test_arenas_draw_different_peak_times():
    morning_a, evening_a = access_windows.peak_times_for_arena("sp-sports", DAY)
    morning_b, evening_b = access_windows.peak_times_for_arena("parobe", DAY)

    assert (morning_a, evening_a) != (morning_b, evening_b)


def test_same_arena_on_the_same_day_repeats_the_time():
    assert access_windows.peak_times_for_arena("sp-sports", DAY) == (
        access_windows.peak_times_for_arena("sp-sports", DAY)
    )


def test_peak_window_is_morning_and_evening():
    assert access_windows.current_peak_window(_moment(7, 0)) == "morning"
    assert access_windows.current_peak_window(_moment(8, 59)) == "morning"
    assert access_windows.current_peak_window(_moment(9, 0)) is None
    assert access_windows.current_peak_window(_moment(17, 0)) == "evening"
    assert access_windows.current_peak_window(_moment(19, 59)) == "evening"
    assert access_windows.current_peak_window(_moment(20, 0)) is None
    assert access_windows.current_peak_window(_moment(12, 0)) is None


def test_peak_window_constants():
    assert (config.PEAK_MORNING_START_HOUR, config.PEAK_MORNING_END_HOUR) == (7, 9)
    assert (config.PEAK_EVENING_START_HOUR, config.PEAK_EVENING_END_HOUR) == (17, 20)


def test_next_day_extraction_outside_peak_does_not_access(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr("sys.argv", ["main.py", "--de", "1", "--ate", "5"])
    monkeypatch.setattr(main, "current_peak_window", lambda moment=None: None)
    accessed = []
    monkeypatch.setattr(main, "wait_between_accesses", lambda: accessed.append("wait"))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: accessed.append("courts") or [quadra()],
    )

    main.main()

    assert accessed == []
    assert "pico" in capsys.readouterr().out.lower()


def test_today_extraction_does_not_wait_for_peak_window(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 1)
    monkeypatch.setattr("sys.argv", ["main.py", "--de", "0", "--ate", "0"])
    monkeypatch.setattr(main, "current_peak_window", lambda moment=None: None)
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda *a, **k: LOCAL)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda *a, **k: ["um.csv"])
    monkeypatch.setattr(weather_collector, "collect_weather", lambda *a, **k: "clima.csv")
    monkeypatch.setattr(weather_collector, "collect_forecast", lambda *a, **k: "previsao.csv")
    monkeypatch.setattr(
        arena_extractor, "TratamentoDeDados",
        type("T", (), {"__init__": lambda self, *a, **k: None, "aplicar": lambda self, now=None: ["um.csv"]}),
    )
    monkeypatch.setattr(main, "wait_between_accesses", lambda: None)
    called = []
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: called.append("courts") or [quadra()],
    )

    main.main()

    assert called == ["courts"]


def test_next_day_waits_until_the_arenas_broken_time(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 1)
    monkeypatch.setattr("sys.argv", ["main.py", "--de", "1", "--ate", "5"])
    now = _moment(7, 0)
    target = time(7, 18)
    monkeypatch.setattr(main, "current_peak_window", lambda moment=None: "morning")
    monkeypatch.setattr(
        main, "peak_times_for_arena",
        lambda arena_key, day, rand_num_gen=None: (target, time(17, 22)),
    )
    monkeypatch.setattr(main, "local_now", lambda moment=None: now)
    sleeps = []
    monkeypatch.setattr(main, "sleep_seconds", sleeps.append)
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda *a, **k: LOCAL)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda *a, **k: ["um.csv"])
    monkeypatch.setattr(weather_collector, "collect_weather", lambda *a, **k: "clima.csv")
    monkeypatch.setattr(weather_collector, "collect_forecast", lambda *a, **k: "previsao.csv")
    monkeypatch.setattr(
        arena_extractor, "TratamentoDeDados",
        type("T", (), {"__init__": lambda self, *a, **k: None, "aplicar": lambda self, now=None: ["um.csv"]}),
    )
    monkeypatch.setattr(main, "wait_between_accesses", lambda: None)
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: [quadra()],
    )

    main.main()

    assert sleeps == [18 * 60]
