"""Testes das regras que derivam slug, tipo e cobertura a partir do nome da quadra."""

import os

import pytest

import courts_collector
import persistencia


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
    """O slug vira minúsculo, perde acento e colapsa qualquer pontuação ou espaço em
    hífens únicos, sem sobrar hífen nas pontas."""
    assert persistencia.slug(nome) == esperado


def test_caminho_csv_usa_o_slug_e_o_sufixo():
    """Cada quadra tem seu próprio arquivo, nomeado a partir do slug."""
    assert persistencia.caminho_csv_da_quadra("Areia 4 - EXTERNA") == "areia-4-externa-extracoes.csv"


def test_caminho_csv_respeita_o_diretorio():
    """Com diretório informado, o caminho é montado por os.path.join."""
    caminho = persistencia.caminho_csv_da_quadra("FUTSAL - Interna", "/tmp/extracoes")
    assert caminho == os.path.join("/tmp/extracoes", "futsal-interna-extracoes.csv")


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("Areia 1 - Interna", "true"),
        ("FUTSAL - Interna", "true"),
        ("Quadra coberta 2", "true"),
        ("GRAMA 7 - EXTERNA", "false"),
        ("Areia 4 - EXTERNA", "false"),
        ("Quadra descoberta 2", "false"),
        ("Quadra 1", ""),
        (None, ""),
    ],
)
def test_quadra_coberta_classifica_pelo_nome(nome, esperado):
    """Interna ou coberta viram true, externa ou descoberta viram false, e um nome sem
    palavra-chave fica vazio em vez de afirmar um false que não foi observado. O caso
    'descoberta' é o que exige testar descoberta antes de coberta, já que uma contém a
    outra."""
    assert courts_collector._quadra_coberta(nome) == esperado


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
    """O tipo sai do esporte selecionado, canonizado para os quatro tipos de interesse
    mesmo sem acento; futsal no nome da quadra resolve o caso em que o esporte não é
    reconhecido, e um esporte fora da lista é devolvido como veio, sem perder dado."""
    assert courts_collector._tipo_quadra(esporte, nome) == esperado
