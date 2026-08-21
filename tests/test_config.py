"""Testes de que os parâmetros ajustáveis vêm todos do config."""

import pytest

import config
import courts_collector
import persistencia


@pytest.mark.parametrize(
    "modulo, nome",
    [
        (courts_collector, "URL_ARENA"),
        (courts_collector, "API_INIT"),
        (courts_collector, "TIPOS_QUADRA"),
        (courts_collector, "PERIODOS_PADRAO"),
        (courts_collector, "TIMEOUT_NAVEGACAO_MS"),
        (persistencia, "DIRETORIO_EXTRACOES"),
    ],
)
def test_modulo_reexporta_o_valor_do_config(modulo, nome):
    assert getattr(modulo, nome) is getattr(config, nome)


def test_coordenadas_sao_numeros():
    assert isinstance(config.LATITUDE, float)
    assert isinstance(config.LONGITUDE, float)


def test_janela_do_clima_e_um_intervalo_valido():
    assert config.HORAS_ANTES_DA_RESERVA > config.HORAS_ATE_A_RESERVA > 0
