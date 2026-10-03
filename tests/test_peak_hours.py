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

FUSO = ZoneInfo("America/Sao_Paulo")
DIA = date(2026, 10, 3)


def _momento(hora, minuto=0):
    return datetime(2026, 10, 3, hora, minuto, tzinfo=FUSO)


def test_horario_quebrado_fica_dentro_da_janela_e_fora_da_hora_cheia():
    rng = __import__("random").Random(0)
    for _ in range(200):
        manha = access_windows.broken_time_in_window(7, 9, rng)
        noite = access_windows.broken_time_in_window(17, 20, rng)
        assert time(7, 1) <= manha < time(9, 0)
        assert manha.minute != 0
        assert time(17, 1) <= noite < time(20, 0)
        assert noite.minute != 0


def test_arenas_sorteiam_horarios_de_pico_diferentes():
    manha_a, noite_a = access_windows.peak_times_for_arena("sp-sports", DIA)
    manha_b, noite_b = access_windows.peak_times_for_arena("parobe", DIA)

    assert (manha_a, noite_a) != (manha_b, noite_b)


def test_mesma_arena_no_mesmo_dia_repete_o_horario():
    assert access_windows.peak_times_for_arena("sp-sports", DIA) == (
        access_windows.peak_times_for_arena("sp-sports", DIA)
    )


def test_janela_de_pico_manha_e_noite():
    assert access_windows.current_peak_window(_momento(7, 0)) == "morning"
    assert access_windows.current_peak_window(_momento(8, 59)) == "morning"
    assert access_windows.current_peak_window(_momento(9, 0)) is None
    assert access_windows.current_peak_window(_momento(17, 0)) == "evening"
    assert access_windows.current_peak_window(_momento(19, 59)) == "evening"
    assert access_windows.current_peak_window(_momento(20, 0)) is None
    assert access_windows.current_peak_window(_momento(12, 0)) is None


def test_constantes_das_janelas_de_pico():
    assert (config.PEAK_MORNING_START_HOUR, config.PEAK_MORNING_END_HOUR) == (7, 9)
    assert (config.PEAK_EVENING_START_HOUR, config.PEAK_EVENING_END_HOUR) == (17, 20)


def test_extracao_do_dia_seguinte_fora_do_pico_nao_acessa(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr("sys.argv", ["main.py", "--de", "1", "--ate", "5"])
    monkeypatch.setattr(main, "current_peak_window", lambda agora=None: None)
    acessou = []
    monkeypatch.setattr(main, "wait_between_accesses", lambda: acessou.append("espera"))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: acessou.append("quadras") or [quadra()],
    )

    main.main()

    assert acessou == []
    assert "pico" in capsys.readouterr().out.lower()


def test_extracao_de_hoje_nao_espera_janela_de_pico(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 1)
    monkeypatch.setattr("sys.argv", ["main.py", "--de", "0", "--ate", "0"])
    monkeypatch.setattr(main, "current_peak_window", lambda agora=None: None)
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda *a, **k: LOCAL)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda *a, **k: ["um.csv"])
    monkeypatch.setattr(weather_collector, "collect_weather", lambda *a, **k: "clima.csv")
    monkeypatch.setattr(weather_collector, "collect_forecast", lambda *a, **k: "previsao.csv")
    monkeypatch.setattr(
        arena_extractor, "TratamentoDeDados",
        type("T", (), {"__init__": lambda self, *a, **k: None, "aplicar": lambda self, agora=None: ["um.csv"]}),
    )
    monkeypatch.setattr(main, "wait_between_accesses", lambda: None)
    chamou = []
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: chamou.append("quadras") or [quadra()],
    )

    main.main()

    assert chamou == ["quadras"]


def test_dia_seguinte_espera_ate_o_horario_quebrado_da_arena(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 1)
    monkeypatch.setattr("sys.argv", ["main.py", "--de", "1", "--ate", "5"])
    agora = _momento(7, 0)
    alvo = time(7, 18)
    monkeypatch.setattr(main, "current_peak_window", lambda moment=None: "morning")
    monkeypatch.setattr(
        main, "peak_times_for_arena",
        lambda chave, dia, rng=None: (alvo, time(17, 22)),
    )
    monkeypatch.setattr(main, "local_now", lambda moment=None: agora)
    sleeps = []
    monkeypatch.setattr(main, "sleep_seconds", sleeps.append)
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda *a, **k: LOCAL)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda *a, **k: ["um.csv"])
    monkeypatch.setattr(weather_collector, "collect_weather", lambda *a, **k: "clima.csv")
    monkeypatch.setattr(weather_collector, "collect_forecast", lambda *a, **k: "previsao.csv")
    monkeypatch.setattr(
        arena_extractor, "TratamentoDeDados",
        type("T", (), {"__init__": lambda self, *a, **k: None, "aplicar": lambda self, agora=None: ["um.csv"]}),
    )
    monkeypatch.setattr(main, "wait_between_accesses", lambda: None)
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor, "_collect_courts",
        lambda self: [quadra()],
    )

    main.main()

    assert sleeps == [18 * 60]
