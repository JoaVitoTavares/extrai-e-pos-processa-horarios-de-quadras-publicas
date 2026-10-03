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

FUSO = ZoneInfo("America/Sao_Paulo")


def _momento(hora, minuto=0, dia=3):
    return datetime(2026, 10, dia, hora, minuto, tzinfo=FUSO)


@pytest.mark.parametrize("hora", [0, 3])
def test_madrugada_libera_um_acesso_a_cada_tres_horas(hora):
    assert access_windows.night_access_allowed(_momento(hora)) is True


@pytest.mark.parametrize("hora", [1, 2, 4, 5])
def test_madrugada_bloqueia_as_horas_fora_do_ciclo_de_tres(hora):
    assert access_windows.night_access_allowed(_momento(hora)) is False


@pytest.mark.parametrize("hora", [6, 7, 12, 18, 23])
def test_fora_da_madrugada_o_acesso_segue_liberado(hora):
    assert access_windows.night_access_allowed(_momento(hora)) is True


def test_madrugada_usa_o_fuso_de_sao_paulo_nao_utc():
    utc = datetime(2026, 10, 3, 4, 0, tzinfo=ZoneInfo("UTC"))
    assert utc.astimezone(FUSO).hour == 1
    assert access_windows.night_access_allowed(utc) is False


def test_janela_da_madrugada_e_meia_noite_as_seis():
    assert config.NIGHT_START_HOUR == 0
    assert config.NIGHT_END_HOUR == 6
    assert config.NIGHT_ACCESS_EVERY_H == 3


def test_rodada_na_madrugada_fora_do_ciclo_nao_acessa_o_site(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "night_access_allowed", lambda agora=None: False)
    acessou = []
    monkeypatch.setattr(main, "wait_between_accesses", lambda: acessou.append("espera"))
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor,
        "_collect_courts",
        lambda self: acessou.append("quadras") or [quadra()],
    )

    main.main()

    assert acessou == []
    assert "madrugada" in capsys.readouterr().out.lower()


def test_rodada_na_madrugada_no_ciclo_acessa_o_site(monkeypatch, tmp_path):
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
        type("T", (), {"__init__": lambda self, *a, **k: None, "aplicar": lambda self, agora=None: ["um.csv"]}),
    )
    monkeypatch.setattr(main, "night_access_allowed", lambda agora=None: True)
    monkeypatch.setattr(main, "wait_between_accesses", lambda: None)
    chamou = []
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor,
        "_collect_courts",
        lambda self: chamou.append("quadras") or [quadra()],
    )

    main.main()

    assert chamou == ["quadras"]
