"""Testes das regras que derivam slug, tipo e cobertura a partir do nome da quadra."""

import os

import pytest

from extrator import courts_collector
from extrator import persistencia


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("Areia 4 - EXTERNA", "areia-4-externa"),
        ("FUTSAL - Interna", "futsal-interna"),
        ("GRAMA 7 - EXTERNA", "grama-7-externa"),
        ("Vôlei de praia", "volei-de-praia"),
        ("Areia 1  -  Interna ", "areia-1-interna"),
    ],
)
def test_slug_normaliza_nome_da_quadra(nome, esperado):
    assert persistencia.slug(nome) == esperado


def test_caminho_csv_usa_o_slug_e_o_sufixo():
    assert persistencia.caminho_csv_da_quadra("Areia 4 - EXTERNA") == "areia-4-externa-extracoes.csv"


def test_caminho_csv_respeita_o_diretorio():
    caminho = persistencia.caminho_csv_da_quadra("FUTSAL - Interna", "/tmp/extracoes")
    assert caminho == os.path.join("/tmp/extracoes", "futsal-interna-extracoes.csv")


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("Areia 1 - Interna", "true"),
        ("FUTSAL - Interna", "true"),
        ("Quadra coberta 2", "true"),
        ("Ginásio 51 99870-1500", "true"),
        ("Ginásio Externo", "false"),
        ("GRAMA 7 - EXTERNA", "false"),
        ("Areia 4 - EXTERNA", "false"),
        ("Quadra descoberta 2", "false"),
        ("Quadra 1", ""),
        (None, ""),
    ],
)
def test_quadra_coberta_classifica_pelo_nome(nome, esperado):
    quadra = courts_collector.Court(nome, "Vôlei de praia", courts_collector.COURT_TYPES)
    assert quadra.covered == esperado


@pytest.mark.parametrize(
    "esporte, nome, esperado",
    [
        ("Futebol de salão", "FUTSAL - Interna", "Futebol de salão"),
        ("Vôlei de praia", "Areia 1 - Interna", "Vôlei de praia"),
        ("Grama 7", "GRAMA 7 - EXTERNA", "Grama 7"),
        ("Grama 5", "GRAMA 5 - Interna", "Grama 5"),
        ("Volei de praia", "Areia 2 - Interna", "Vôlei de praia"),
        ("Handebol", "Quadra 1", "Handebol"),
        ("Esporte novo", "FUTSAL - Interna", "Futebol de salão"),
    ],
)
def test_tipo_quadra_canoniza_o_esporte(esporte, nome, esperado):
    quadra = courts_collector.Court(nome, esporte, courts_collector.COURT_TYPES)
    assert quadra.court_type == esperado


@pytest.mark.parametrize(
    "esporte, tipos, esperado",
    [
        ("Futebol Society", ["Futebol society"], "Futebol society"),
        ("Futebol society", ["Futebol society"], "Futebol society"),
        ("Futsal", ["Futebol de salão"], "Futebol de salão"),
        ("Vôlei de Praia", ["Vôlei de praia"], "Vôlei de praia"),
    ],
)
def test_tipo_quadra_grava_a_grafia_do_config(esporte, tipos, esperado):
    assert courts_collector.Court(None, esporte, tipos).court_type == esperado
