"""Canário: confere no site real que a página ainda tem a forma que o coletor espera.

Afirma forma, nunca valores — horário, status e preço mudam de hora em hora, e um teste
que os assertasse seria falso-positivo garantido. É o único arquivo que acessa a rede,
por isso fica atrás do marcador `rede` e não roda no `pytest` padrão.
"""

from datetime import date

import pytest

from extrator import config
from extrator import courts_collector
import main

pytestmark = pytest.mark.rede

ESPORTE = "Vôlei de praia"
PERIODO = "Noite"
TIMEOUT_PERIODO_MS = 30_000
HOJE = date.today()
ARENA = config.ARENAS[0]["url"]


@pytest.fixture(scope="module")
def esportes_do_site():
    return courts_collector.listar_esportes(ARENA)


@pytest.fixture(scope="module")
def endereco_do_site(navegador):
    pagina = navegador.new_page()
    pagina.goto(ARENA, wait_until="networkidle", timeout=60_000)
    courts_collector._escolher_esporte(pagina, ESPORTE, timeout_ms=15_000)
    endereco = courts_collector.extrair_endereco(pagina, ESPORTE, timeout_ms=15_000)
    pagina.close()
    return endereco


@pytest.fixture(scope="module")
def pagina_no_periodo(navegador):
    pagina = navegador.new_page()
    pagina.goto(ARENA, wait_until="networkidle", timeout=60_000)
    courts_collector._escolher_esporte(pagina, ESPORTE, timeout_ms=15_000)
    courts_collector._selecionar_dia(pagina, HOJE, timeout_ms=15_000)
    courts_collector._selecionar_periodo(
        pagina, PERIODO, pagina.locator("body").inner_text(), timeout_ms=TIMEOUT_PERIODO_MS
    )
    courts_collector._esperar_quadras(pagina)
    yield pagina
    pagina.close()


@pytest.fixture(scope="module")
def quadras_do_site(pagina_no_periodo):
    return courts_collector._extrair_quadras(pagina_no_periodo, ESPORTE, PERIODO, HOJE)


def test_api_ainda_lista_esportes(esportes_do_site):
    assert esportes_do_site


@pytest.mark.parametrize("configurada", config.ARENAS, ids=lambda arena: arena["url"])
def test_toda_arena_ainda_oferece_os_tipos_que_declara(configurada):
    arena = main.normalize_arena_info(configurada)
    alvos = courts_collector.esportes_alvo(
        courts_collector.listar_esportes(arena["url"]), arena["tipos"]
    )

    assert courts_collector.tipos_ausentes(alvos, arena["tipos"]) == []


def test_a_arena_ainda_publica_o_endereco(endereco_do_site):
    assert "," in endereco_do_site


def test_endereco_nao_e_o_rotulo_da_tela(endereco_do_site):
    assert "Escolha" not in endereco_do_site
    assert ESPORTE not in endereco_do_site


def test_calendario_ainda_libera_os_dias_a_frente(pagina_no_periodo):
    na_grade = 0
    for dia in courts_collector.dias_de_coleta(HOJE):
        rotulo = dia.strftime(courts_collector.FORMATO_DIA_NO_CALENDARIO)
        if not pagina_no_periodo.locator(f".picker__day[aria-label^='{rotulo}']").count():
            continue
        seletor = f".picker__day[aria-label^='{rotulo}']:not(.picker__day--disabled)"
        assert pagina_no_periodo.locator(seletor).count() == 1, f"dia indisponível: {rotulo}"
        na_grade += 1

    assert na_grade, "nenhum dia do horizonte se identifica por aria-label na grade aberta"
    assert pagina_no_periodo.locator(".picker__nav--next").count() == 1


def test_dia_selecionado_e_reconhecivel(pagina_no_periodo):
    selecionado = pagina_no_periodo.locator(".picker__day--selected")

    assert selecionado.count() == 1
    assert selecionado.first.get_attribute("aria-label").startswith(
        HOJE.strftime(courts_collector.FORMATO_DIA_NO_CALENDARIO)
    )


def test_periodo_escolhido_continua_realcado(pagina_no_periodo):
    assert courts_collector._periodo_escolhido(pagina_no_periodo, PERIODO)
    assert not courts_collector._periodo_escolhido(pagina_no_periodo, "Manhã")


def test_seletor_ainda_encontra_quadras(quadras_do_site):
    assert quadras_do_site
    assert quadras_do_site[0]["quadra"] is not None


def test_toda_quadra_tem_nome(quadras_do_site):
    for quadra in quadras_do_site:
        assert quadra["quadra"].strip()


def test_alguma_quadra_tem_horario(quadras_do_site):
    assert any(quadra["horarios"] for quadra in quadras_do_site)


def test_pagina_ja_estabilizou_quando_a_extracao_roda(pagina_no_periodo, quadras_do_site):
    antes = [len(quadra["horarios"]) for quadra in quadras_do_site]
    pagina_no_periodo.wait_for_timeout(1_500)
    depois = [
        len(quadra["horarios"])
        for quadra in courts_collector._extrair_quadras(pagina_no_periodo, ESPORTE, PERIODO, HOJE)
    ]

    assert antes == depois


def test_nomenclatura_de_cobertura_continua_reconhecivel(quadras_do_site):
    sem_classificacao = [
        quadra["quadra"] for quadra in quadras_do_site if not quadra["quadra_coberta"]
    ]
    assert sem_classificacao == []
