"""Testes da leitura do endereço que a arena publica, contra o cabeçalho da página."""

import courts_collector

ESPORTE = "Vôlei de praia"
ENDERECO = "20 de Junho 54, Parobé"


def test_le_o_endereco_entre_o_esporte_e_a_data(carregar_fixture):
    """O endereço é o texto que fica abaixo do esporte escolhido e acima do campo de
    data. A busca é pela posição na tela, e não pela ordem do DOM: o Bubble publica os
    blocos fora de ordem e os coloca no lugar com `order` do CSS, então ler o HTML de
    cima para baixo devolveria o rótulo errado."""
    pagina = carregar_fixture("cabecalho_com_endereco.html")

    assert courts_collector.extrair_endereco(pagina, ESPORTE) == ENDERECO


def test_ignora_o_que_esta_acima_do_esporte(carregar_fixture):
    """A barra de topo também tem vírgula, e vem antes na tela: a leitura começa depois
    do nome do esporte, senão a saudação ao visitante viraria o endereço da arena."""
    pagina = carregar_fixture("cabecalho_com_endereco.html")

    assert "visitante" not in courts_collector.extrair_endereco(pagina, ESPORTE)


def test_rotulo_da_data_nao_passa_por_endereco(carregar_fixture):
    """Sem o endereço na tela, a leitura devolve vazio em vez do rótulo logo abaixo dele:
    é a vírgula que separa rua e cidade que distingue um do outro, e 'Escolha uma data.'
    não tem nenhuma. Endereço vazio deixa a arena com o local que já conhecia."""
    pagina = carregar_fixture("cabecalho_com_endereco.html")
    pagina.locator(".baTaRaAd").evaluate("elemento => elemento.remove()")

    assert courts_collector.extrair_endereco(pagina, ESPORTE) == ""


def test_sem_o_esporte_na_tela_nao_chuta_endereco(carregar_fixture):
    """Sem achar o esporte escolhido, a leitura para em vez de ficar com o primeiro texto
    com vírgula que encontrar: a saudação ao visitante tem uma, e virar endereço mandaria
    o clima da arena para o outro lado do mapa. Vazio aqui devolve a arena ao local que
    ela já conhecia — o dia em que o site mudar esse bloco, quem acusa é o canário."""
    pagina = carregar_fixture("cabecalho_com_endereco.html")

    assert courts_collector.extrair_endereco(pagina, "Handebol") == ""


def test_pagina_sem_campo_de_data_devolve_vazio(pagina):
    """A página que nem chegou a montar o bloco de reserva não tem endereço para ler, e a
    espera não pode segurar a coleta: passado o tempo, devolve vazio e a arena segue com
    o local que já conhecia."""
    pagina.set_content("<div>Escolha uma opção de esporte</div>")

    assert courts_collector.extrair_endereco(pagina, ESPORTE, timeout_ms=200) == ""
