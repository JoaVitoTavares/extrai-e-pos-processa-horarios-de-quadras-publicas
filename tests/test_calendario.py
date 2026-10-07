"""Testes da fixação do dia no calendário, inclusive quando ele está no mês seguinte."""

from extrator import courts_collector

ESPERA_CURTA_MS = 2_000


def _cliques_no_proximo(pagina) -> str:
    return pagina.locator("#cliques-no-proximo").inner_text()


def test_dia_do_mes_aberto_nao_avanca_o_calendario(carregar_fixture):
    pagina = carregar_fixture("calendario.html")

    assert courts_collector._try_day(pagina, "07/10/26", ESPERA_CURTA_MS)
    assert pagina.locator(".picker__input").input_value().startswith("07/10/26")
    assert _cliques_no_proximo(pagina) == "0"


def test_dia_do_mes_seguinte_so_aparece_depois_de_avancar(carregar_fixture):
    pagina = carregar_fixture("calendario.html")

    assert courts_collector._try_day(pagina, "01/11/26", ESPERA_CURTA_MS)
    assert pagina.locator(".picker__input").input_value().startswith("01/11/26")
    assert _cliques_no_proximo(pagina) == "1"


def test_dia_desabilitado_nao_e_fixado(carregar_fixture):
    pagina = carregar_fixture("calendario.html")

    assert courts_collector._try_day(pagina, "08/10/26", ESPERA_CURTA_MS) is False
    assert pagina.locator(".picker__input").input_value() == ""


def test_clique_que_nao_grava_o_rotulo_nao_conta_como_dia_fixado(carregar_fixture):
    pagina = carregar_fixture("calendario.html")

    assert courts_collector._try_day(pagina, "09/10/26", ESPERA_CURTA_MS) is False
    assert not pagina.locator(".picker__input").input_value().startswith("09/10/26")
