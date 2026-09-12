"""Testes da troca de período, que é sincronizada pelo realce do botão."""

import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from extrator import courts_collector

ESPERA_CURTA_MS = 2_000


def _texto(pagina) -> str:
    return pagina.locator("body").inner_text()


def test_periodo_ja_escolhido_e_aceito_sem_troca_de_conteudo(carregar_fixture):
    pagina = carregar_fixture("periodos.html")

    lido = courts_collector._select_period(pagina, "Noite", _texto(pagina), ESPERA_CURTA_MS)

    assert "19:00 - Indisponível" in lido


def test_periodo_sem_horario_a_venda_troca_o_realce(carregar_fixture):
    pagina = carregar_fixture("periodos.html")

    courts_collector._select_period(pagina, "Manhã", _texto(pagina), ESPERA_CURTA_MS)

    assert courts_collector._period_selected(pagina, "Manhã")
    assert not courts_collector._period_selected(pagina, "Noite")


def test_conteudo_que_nao_troca_deixa_o_periodo_de_fora(carregar_fixture):
    pagina = carregar_fixture("periodos.html")
    courts_collector._select_period(pagina, "Manhã", _texto(pagina), ESPERA_CURTA_MS)
    texto_da_manha = _texto(pagina)

    with pytest.raises(PWTimeout):
        courts_collector._select_period(pagina, "Tarde", texto_da_manha, ESPERA_CURTA_MS)


def test_periodo_realcado_e_o_que_o_site_esta_mostrando(carregar_fixture):
    pagina = carregar_fixture("periodos.html")

    assert courts_collector._period_selected(pagina, "Noite")
    assert not courts_collector._period_selected(pagina, "Manhã")
    assert not courts_collector._period_selected(pagina, "Tarde")
