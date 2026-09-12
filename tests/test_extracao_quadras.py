"""Testes da extração quadra a quadra, contra o HTML real congelado em fixtures."""

from datetime import date, timedelta

import pytest

from extrator import courts_collector

DIA = date(2026, 8, 7)
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
    pagina = carregar_fixture("quatro_quadras_volei.html")
    return courts_collector._extract_courts(pagina, "Vôlei de praia", "Noite", DIA)


def test_uma_entrada_por_quadra(quadras_volei):
    assert len(quadras_volei) == 4


def test_nomes_das_quadras_na_ordem_da_tela(quadras_volei):
    nomes = [q["quadra"] for q in quadras_volei]
    assert nomes == ["Areia 1 - Interna", "Areia 2 - Interna", "Areia 3 - Interna", "Areia 4 - EXTERNA"]


def test_cobertura_classificada_por_quadra(quadras_volei):
    assert [q["quadra_coberta"] for q in quadras_volei] == ["true", "true", "true", "false"]


def test_tipo_quadra_vem_do_esporte_selecionado(quadras_volei):
    assert {q["tipo_quadra"] for q in quadras_volei} == {"Vôlei de praia"}


@pytest.mark.parametrize("nome", list(HORARIOS_ESPERADOS))
def test_horarios_de_cada_quadra(quadras_volei, nome):
    quadra = next(q for q in quadras_volei if q["quadra"] == nome)
    obtidos = [(h["hora"], h["status"]) for h in quadra["horarios"]]
    assert obtidos == HORARIOS_ESPERADOS[nome]


def test_horarios_nao_vazam_entre_quadras(quadras_volei):
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
    for quadra in quadras_volei:
        assert quadra["esporte"] == "Vôlei de praia"
        assert quadra["periodo"] == "Noite"
        assert quadra["data"] == "2026-08-07"
        assert quadra["coletado_em"]
        assert quadra["aviso"] is None


def test_data_vem_do_calendario_e_nao_do_relogio(carregar_fixture):
    pagina = carregar_fixture("quatro_quadras_volei.html")
    amanha = DIA + timedelta(days=1)
    quadras = courts_collector._extract_courts(pagina, "Vôlei de praia", "Noite", amanha)

    assert {quadra["data"] for quadra in quadras} == {"2026-08-08"}


def test_raiz_da_quadra_permite_escopar_o_clique(quadras_volei):
    for quadra in quadras_volei:
        assert quadra["raiz"].count() == 1


def test_quadra_unica_continua_funcionando(carregar_fixture):
    pagina = carregar_fixture("quadra_unica_grama7.html")
    quadras = courts_collector._extract_courts(pagina, "Grama 7", "Noite", DIA)

    assert len(quadras) == 1
    assert quadras[0]["quadra"] == "GRAMA 7 - EXTERNA"
    assert quadras[0]["quadra_coberta"] == "false"
    assert quadras[0]["tipo_quadra"] == "Grama 7"
    assert len(quadras[0]["horarios"]) == 6
    assert [h["hora"] for h in quadras[0]["horarios"] if h["status"] == "Livre"] == ["22:30"]


def test_pagina_sem_quadras_devolve_aviso(pagina):
    pagina.set_content("<div></div>")
    quadras = courts_collector._extract_courts(pagina, "Futebol de salão", "Manhã", DIA)

    assert len(quadras) == 1
    assert quadras[0]["quadra"] is None
    assert quadras[0]["horarios"] == []
    assert quadras[0]["aviso"]
    assert quadras[0]["data"] == "2026-08-07"
