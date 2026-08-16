"""Testes de que os parâmetros ajustáveis vêm todos do config."""

import pytest

import coletor
import config


@pytest.mark.parametrize(
    "nome",
    [
        "URL_ARENA",
        "API_INIT",
        "TIPOS_QUADRA",
        "PERIODOS_PADRAO",
        "TIMEOUT_NAVEGACAO_MS",
        "DIRETORIO_EXTRACOES",
    ],
)
def test_coletor_reexporta_o_valor_do_config(nome):
    """Editar o config tem que bastar: o coletor importa esses nomes em vez de manter
    cópias próprias, e o teste falha no dia em que alguém redefinir um deles no módulo
    do coletor e as duas versões começarem a divergir em silêncio."""
    assert getattr(coletor, nome) is getattr(config, nome)


def test_coordenadas_sao_numeros():
    """A latitude e a longitude entram como parâmetro de consulta na API de clima, que
    espera número: guardá-las como texto no config passaria despercebido até a primeira
    chamada real."""
    assert isinstance(config.LATITUDE, float)
    assert isinstance(config.LONGITUDE, float)


def test_janela_do_clima_e_um_intervalo_valido():
    """A coleta começa antes de terminar: horas_antes maior que horas_ate, senão a
    janela do tratamento nasce vazia e nenhuma reserva receberia clima."""
    assert config.HORAS_ANTES_DA_RESERVA > config.HORAS_ATE_A_RESERVA > 0
