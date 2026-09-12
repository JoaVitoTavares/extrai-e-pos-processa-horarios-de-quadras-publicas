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
        (courts_collector, "CAMINHO_API_INIT"),
        (courts_collector, "TIPOS_QUADRA"),
        (courts_collector, "PERIODOS_PADRAO"),
        (courts_collector, "TIMEOUT_NAVEGACAO_MS"),
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
