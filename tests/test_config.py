"""Testes de que os parâmetros ajustáveis vêm todos do config."""

import pytest

from extrator import config
from extrator import courts_collector
from extrator import localizacao
import main
from extrator import persistencia


@pytest.mark.parametrize(
    "modulo, nome",
    [
        (courts_collector, "API_INIT_PATH"),
        (courts_collector, "COURT_TYPES"),
        (courts_collector, "DEFAULT_PERIODS"),
        (courts_collector, "NAVIGATION_TIMEOUT_MS"),
        (localizacao, "API_GEOCODIFICACAO"),
        (localizacao, "IDENTIFICACAO_GEOCODIFICACAO"),
        (persistencia, "DIRETORIO_EXTRACOES"),
    ],
)
def test_modulo_reexporta_o_valor_do_config(modulo, nome):
    assert getattr(modulo, nome) is getattr(config, nome)


def test_toda_arena_tem_url():
    assert config.ARENAS
    for arena in config.ARENAS:
        assert arena["url"].startswith("http")


def test_arenas_nao_repetem_o_diretorio():
    diretorios = [main.normalize_arena_info(arena)["diretorio"] for arena in config.ARENAS]
    assert len(set(diretorios)) == len(diretorios)


def test_toda_arena_procura_algum_tipo_de_quadra():
    for arena in config.ARENAS:
        assert main.normalize_arena_info(arena)["tipos"]


def test_janela_do_clima_e_um_intervalo_valido():
    assert config.HORAS_ANTES_DA_RESERVA > config.HORAS_ATE_A_RESERVA > 0


def test_pausas_da_rodada_cabem_na_folga_do_cron():
    workers = config.ARENAS_EM_PARALELO
    arenas = len(config.ARENAS)
    sports = sum(len(arena.get("tipos") or config.COURT_TYPES) for arena in config.ARENAS)
    per_worker_arenas = (arenas + workers - 1) // workers
    per_worker_sports = (sports + workers - 1) // workers
    days = config.DAYS_AHEAD + 1
    clicks_per_sport = 1 + days * (3 + len(config.DEFAULT_PERIODS)) + 80
    access_waits = 1 + per_worker_arenas + per_worker_sports
    click_waits = per_worker_sports * (clicks_per_sport + 2)
    worst = (
        access_waits * config.ACCESS_INTERVAL_MAX_S
        + click_waits * config.CLICK_INTERVAL_MAX_S
    )

    assert 0 < config.ACCESS_INTERVAL_MIN_S < config.ACCESS_INTERVAL_MAX_S
    assert 0 < config.CLICK_INTERVAL_MIN_S < config.CLICK_INTERVAL_MAX_S
    assert worst < 90
