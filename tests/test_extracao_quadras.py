"""Testes da extração quadra a quadra, contra o HTML real congelado em fixtures."""

import pytest

import coletor

HORARIOS_ESPERADOS = {
    "Areia 1 - Interna": [
        ("17:00", "Indisponível"), ("18:00", "Indisponível"), ("19:00", "Indisponível"),
        ("20:00", "Indisponível"), ("21:00", "Indisponível"), ("22:00", "Indisponível"),
        ("23:00", "Indisponível"),
    ],
    "Areia 2 - Interna": [
        ("17:00", "Indisponível"), ("18:00", "Indisponível"), ("19:00", "Indisponível"),
        ("20:00", "Indisponível"), ("21:00", "Indisponível"), ("22:00", "Indisponível"),
        ("23:00", "Livre"),
    ],
    "Areia 3 - Interna": [
        ("17:30", "Livre"), ("18:30", "Indisponível"), ("19:30", "Indisponível"),
        ("20:30", "Indisponível"), ("21:30", "Indisponível"), ("22:30", "Indisponível"),
    ],
    "Areia 4 - EXTERNA": [
        ("17:30", "Livre"), ("18:30", "Livre"), ("19:30", "Livre"),
        ("20:30", "Indisponível"), ("21:30", "Indisponível"), ("22:30", "Livre"),
    ],
}


@pytest.fixture
def quadras_volei(carregar_fixture):
    """Extrai as quatro quadras de vôlei da fixture, ponto de partida da maior parte
    dos testes deste arquivo."""
    pagina = carregar_fixture("quatro_quadras_volei.html")
    return coletor._extrair_quadras(pagina, "Vôlei de praia", "Noite")


def test_uma_entrada_por_quadra(quadras_volei):
    """O RepeatingGroup externo tem uma quadra por group-item, então quatro quadras
    viram quatro itens — e não um amontoado só."""
    assert len(quadras_volei) == 4


def test_nomes_das_quadras_na_ordem_da_tela(quadras_volei):
    """O nome de cada quadra sai da primeira linha do seu bloco, preservando a ordem em
    que a tela lista as quadras."""
    nomes = [q["quadra"] for q in quadras_volei]
    assert nomes == ["Areia 1 - Interna", "Areia 2 - Interna", "Areia 3 - Interna", "Areia 4 - EXTERNA"]


def test_cobertura_classificada_por_quadra(quadras_volei):
    """As três primeiras areias são internas e a quarta é externa, então a cobertura
    varia dentro do mesmo esporte."""
    assert [q["quadra_coberta"] for q in quadras_volei] == ["true", "true", "true", "false"]


def test_tipo_quadra_vem_do_esporte_selecionado(quadras_volei):
    """Todas as quadras do vôlei recebem o mesmo tipo, canonizado a partir do esporte."""
    assert {q["tipo_quadra"] for q in quadras_volei} == {"Vôlei de praia"}


@pytest.mark.parametrize("nome", list(HORARIOS_ESPERADOS))
def test_horarios_de_cada_quadra(quadras_volei, nome):
    """Cada quadra carrega exatamente os horários e status do seu próprio bloco."""
    quadra = next(q for q in quadras_volei if q["quadra"] == nome)
    obtidos = [(h["hora"], h["status"]) for h in quadra["horarios"]]
    assert obtidos == HORARIOS_ESPERADOS[nome]


def test_horarios_nao_vazam_entre_quadras(quadras_volei):
    """Regressão do bug que motivou a refatoração: lendo o texto da página inteira, os
    26 horários das quatro quadras se misturavam. As areias 1 e 2 têm horários cheios e
    as areias 3 e 4 têm meias horas — nenhum dos dois conjuntos pode aparecer no bloco
    do outro."""
    por_quadra = {q["quadra"]: {h["hora"] for h in q["horarios"]} for q in quadras_volei}

    assert "17:00" in por_quadra["Areia 1 - Interna"]
    assert "17:00" in por_quadra["Areia 2 - Interna"]
    assert "17:00" not in por_quadra["Areia 3 - Interna"]
    assert "17:00" not in por_quadra["Areia 4 - EXTERNA"]

    assert "17:30" in por_quadra["Areia 3 - Interna"]
    assert "17:30" in por_quadra["Areia 4 - EXTERNA"]
    assert "17:30" not in por_quadra["Areia 1 - Interna"]
    assert "17:30" not in por_quadra["Areia 2 - Interna"]


def test_metadados_do_periodo_em_cada_quadra(quadras_volei):
    """Esporte, período e horário da coleta acompanham cada quadra, porque a linha do
    CSV é montada a partir do item da quadra, não do período."""
    for quadra in quadras_volei:
        assert quadra["esporte"] == "Vôlei de praia"
        assert quadra["periodo"] == "Noite"
        assert quadra["coletado_em"]
        assert quadra["aviso"] is None


def test_raiz_da_quadra_permite_escopar_o_clique(quadras_volei):
    """Cada quadra leva junto o seu locator, que é o que vai escopar a coleta de preços
    ao bloco certo em vez de pegar sempre o primeiro horário da página."""
    for quadra in quadras_volei:
        assert quadra["raiz"].count() == 1


def test_quadra_unica_continua_funcionando(carregar_fixture):
    """O caso de um esporte com uma quadra só — como o futsal de hoje — não regride."""
    pagina = carregar_fixture("quadra_unica_grama7.html")
    quadras = coletor._extrair_quadras(pagina, "Grama 7", "Noite")

    assert len(quadras) == 1
    assert quadras[0]["quadra"] == "GRAMA 7 - EXTERNA"
    assert quadras[0]["quadra_coberta"] == "false"
    assert quadras[0]["tipo_quadra"] == "Grama 7"
    assert len(quadras[0]["horarios"]) == 6
    assert [h["hora"] for h in quadras[0]["horarios"] if h["status"] == "Livre"] == ["22:30"]


def test_pagina_sem_quadras_devolve_aviso(pagina):
    """Sem nenhum bloco de quadra na tela, o período vira um item único com aviso — o
    mesmo comportamento de hoje para período que não carregou."""
    pagina.set_content("<div></div>")
    quadras = coletor._extrair_quadras(pagina, "Futebol de salão", "Manhã")

    assert len(quadras) == 1
    assert quadras[0]["quadra"] is None
    assert quadras[0]["horarios"] == []
    assert quadras[0]["aviso"]
