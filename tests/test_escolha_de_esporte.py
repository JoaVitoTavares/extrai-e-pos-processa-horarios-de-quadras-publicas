"""Testes da entrada na arena: escolher o esporte e reconhecer quem não vende pela web."""

import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from extrator import courts_collector

ESPERA_CURTA_MS = 2_000


def test_arena_com_lista_de_esportes_clica_no_pedido(carregar_fixture):
    pagina = carregar_fixture("escolha_de_esporte.html")

    assert courts_collector._escolher_esporte(pagina, "Vôlei de praia", ESPERA_CURTA_MS)
    assert pagina.locator(courts_collector.SELETOR_CAMPO_DE_DATA).first.is_visible()


def test_arena_de_um_esporte_so_dispensa_o_clique(carregar_fixture):
    pagina = carregar_fixture("esporte_unico_ja_escolhido.html")

    assert courts_collector._escolher_esporte(pagina, "Futebol society", ESPERA_CURTA_MS)


def test_arena_sem_agenda_na_web_volta_sem_horarios(carregar_fixture):
    pagina = carregar_fixture("sem_agenda_na_web.html")

    assert courts_collector._escolher_esporte(pagina, "Beach Tennis", ESPERA_CURTA_MS) is False


def test_esporte_fora_da_tela_estoura_o_tempo(carregar_fixture):
    pagina = carregar_fixture("escolha_de_esporte.html")

    with pytest.raises(PWTimeout):
        courts_collector._escolher_esporte(pagina, "Handebol", ESPERA_CURTA_MS)
