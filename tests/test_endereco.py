"""Testes da leitura do endereço que a arena publica, contra o cabeçalho da página."""

from extrator import courts_collector

ESPORTE = "Vôlei de praia"
ENDERECO = "20 de Junho 54, Parobé"


def test_le_o_endereco_entre_o_esporte_e_a_data(carregar_fixture):
    pagina = carregar_fixture("cabecalho_com_endereco.html")

    assert courts_collector.extract_address(pagina, ESPORTE) == ENDERECO


def test_ignora_o_que_esta_acima_do_esporte(carregar_fixture):
    pagina = carregar_fixture("cabecalho_com_endereco.html")

    assert "visitante" not in courts_collector.extract_address(pagina, ESPORTE)


def test_rotulo_da_data_nao_passa_por_endereco(carregar_fixture):
    pagina = carregar_fixture("cabecalho_com_endereco.html")
    pagina.locator(".baTaRaAd").evaluate("elemento => elemento.remove()")

    assert courts_collector.extract_address(pagina, ESPORTE) == ""


def test_sem_o_esporte_na_tela_nao_chuta_endereco(carregar_fixture):
    pagina = carregar_fixture("cabecalho_com_endereco.html")

    assert courts_collector.extract_address(pagina, "Handebol") == ""


def test_pagina_sem_campo_de_data_devolve_vazio(pagina):
    pagina.set_content("<div>Escolha uma opção de esporte</div>")

    assert courts_collector.extract_address(pagina, ESPORTE, timeout_ms=200) == ""
