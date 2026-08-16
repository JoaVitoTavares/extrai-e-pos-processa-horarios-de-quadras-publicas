"""Canário: confere no site real que a página ainda tem a forma que o coletor espera.

Afirma forma, nunca valores — horário, status e preço mudam de hora em hora, e um teste
que os assertasse seria falso-positivo garantido. É o único arquivo que acessa a rede,
por isso fica atrás do marcador `rede` e não roda no `pytest` padrão.
"""

import pytest

import courts_collector

pytestmark = pytest.mark.rede

ESPORTE = "Vôlei de praia"
PERIODO = "Noite"
TIMEOUT_PERIODO_MS = 30_000


@pytest.fixture(scope="module")
def esportes_do_site():
    """Chama a API JSON de verdade uma vez por execução do módulo."""
    return courts_collector.listar_esportes()


@pytest.fixture(scope="module")
def pagina_no_periodo(navegador):
    """Navega no site real até um esporte e um período, uma vez por execução do módulo,
    repetindo a mesma sequência que coletar_horarios usa — inclusive a espera pelas
    quadras assíncronas — para o canário exercitar o caminho de produção."""
    pagina = navegador.new_page()
    pagina.goto(courts_collector.URL_ARENA, wait_until="networkidle", timeout=60_000)
    pagina.get_by_text(ESPORTE, exact=True).first.click()

    hoje = pagina.locator(".picker__day--today").first
    hoje.wait_for(state="visible", timeout=15_000)
    hoje.click()

    pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=15_000)
    courts_collector._selecionar_periodo(
        pagina, PERIODO, pagina.locator("body").inner_text(), timeout_ms=TIMEOUT_PERIODO_MS
    )
    courts_collector._esperar_quadras(pagina)
    yield pagina
    pagina.close()


@pytest.fixture(scope="module")
def quadras_do_site(pagina_no_periodo):
    """Extrai as quadras da página já carregada."""
    return courts_collector._extrair_quadras(pagina_no_periodo, ESPORTE, PERIODO)


def test_api_ainda_lista_esportes(esportes_do_site):
    """A técnica sem navegador continua devolvendo uma lista de esportes."""
    assert esportes_do_site


def test_api_ainda_traz_os_tipos_de_interesse(esportes_do_site):
    """Os quatro tipos de quadra que o CSV normaliza continuam existindo no site; se um
    sumir ou for renomeado, TIPOS_QUADRA precisa acompanhar."""
    assert set(courts_collector.TIPOS_QUADRA) <= set(esportes_do_site)


def test_seletor_ainda_encontra_quadras(quadras_do_site):
    """O anchor estrutural do Bubble ainda casa com o RepeatingGroup de quadras. Este é
    o teste que fica vermelho quando o site é republicado e as classes mudam."""
    assert quadras_do_site
    assert quadras_do_site[0]["quadra"] is not None


def test_toda_quadra_tem_nome(quadras_do_site):
    """O nome sai da primeira linha do bloco; um bloco sem nome significaria que o
    layout do item mudou de ordem."""
    for quadra in quadras_do_site:
        assert quadra["quadra"].strip()


def test_alguma_quadra_tem_horario(quadras_do_site):
    """O período da noite tem horários, então PADRAO_HORARIO ainda casa com o texto do
    slot. Nada é afirmado sobre quais horários, nem sobre estarem livres."""
    assert any(quadra["horarios"] for quadra in quadras_do_site)


def test_pagina_ja_estabilizou_quando_a_extracao_roda(pagina_no_periodo, quadras_do_site):
    """Regressão da corrida entre as quadras: os RepeatingGroups internos são preenchidos
    de forma assíncrona, e sem esperar a página estabilizar as últimas quadras saíam com
    zero horários — virando CSV vazio sem erro nenhum. Uma releitura depois de uma pausa
    tem que devolver exatamente a mesma contagem de horários por quadra."""
    antes = [len(quadra["horarios"]) for quadra in quadras_do_site]
    pagina_no_periodo.wait_for_timeout(1_500)
    depois = [
        len(quadra["horarios"])
        for quadra in courts_collector._extrair_quadras(pagina_no_periodo, ESPORTE, PERIODO)
    ]

    assert antes == depois


def test_nomenclatura_de_cobertura_continua_reconhecivel(quadras_do_site):
    """Toda quadra ainda se classifica como coberta ou descoberta. Uma quadra nova com
    nomenclatura fora do padrão cai aqui, antes de virar coluna vazia no CSV."""
    sem_classificacao = [
        quadra["quadra"] for quadra in quadras_do_site if not quadra["quadra_coberta"]
    ]
    assert sem_classificacao == []
