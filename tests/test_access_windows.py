"""Testes da redução de acessos na madrugada, no fuso America/Sao_Paulo."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from extrator import access_windows
from extrator import arena_extractor
from extrator import config
from extrator import weather_collector
import main
from test_main import ARENA, LOCAL, quadra

ZONE = ZoneInfo("America/Sao_Paulo")


def _moment(hour, minute=0, day=3):
    return datetime(2026, 10, day, hour, minute, tzinfo=ZONE)


@pytest.mark.parametrize("hour", [0, 3])
def test_night_allows_one_access_every_three_hours(hour):
    assert access_windows.night_access_allowed(_moment(hour)) is True


@pytest.mark.parametrize("hour", [1, 2, 4, 5])
def test_night_blocks_hours_outside_the_three_hour_cycle(hour):
    assert access_windows.night_access_allowed(_moment(hour)) is False


@pytest.mark.parametrize("hour", [6, 7, 12, 18, 23])
def test_outside_night_access_stays_allowed(hour):
    assert access_windows.night_access_allowed(_moment(hour)) is True


def test_night_uses_sao_paulo_timezone_not_utc():
    utc = datetime(2026, 10, 3, 4, 0, tzinfo=ZoneInfo("UTC"))
    assert utc.astimezone(ZONE).hour == 1
    assert access_windows.night_access_allowed(utc) is False


def test_night_window_is_midnight_to_six():
    assert config.NIGHT_START_HOUR == 0
    assert config.NIGHT_END_HOUR == 6
    assert config.NIGHT_ACCESS_EVERY_H == 3


def test_night_round_outside_cycle_does_not_access_the_site(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "night_access_allowed", lambda moment=None: False)
    accessed = []
    monkeypatch.setattr(main, "wait_between_accesses", lambda: accessed.append("wait"))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor,
        "_collect_courts",
        lambda self: accessed.append("courts") or [quadra()],
    )

    main.main()

    assert accessed == []
    assert "madrugada" in capsys.readouterr().out.lower()


def test_night_round_on_cycle_accesses_the_site(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 1)
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda *a, **k: LOCAL)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda *a, **k: ["um.csv"])
    monkeypatch.setattr(weather_collector, "collect_weather", lambda *a, **k: "clima.csv")
    monkeypatch.setattr(weather_collector, "collect_forecast", lambda *a, **k: "previsao.csv")
    monkeypatch.setattr(
        arena_extractor, "TratamentoDeDados",
        type("T", (), {"__init__": lambda self, *a, **k: None, "aplicar": lambda self, now=None: ["um.csv"]}),
    )
    monkeypatch.setattr(main, "night_access_allowed", lambda moment=None: True)
    monkeypatch.setattr(main, "wait_between_accesses", lambda: None)
    called = []
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor,
        "_collect_courts",
        lambda self: called.append("courts") or [quadra()],
    )

    main.main()

    assert called == ["courts"]
