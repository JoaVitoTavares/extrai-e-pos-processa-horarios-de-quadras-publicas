"""Testes da leitura de preço de um slot e do escopo dessa leitura à quadra certa."""

import pytest

import coletor


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("1.500,00", 1500.0),
        ("150", 150.0),
        ("89,90", 89.9),
        ("", None),
        ("grátis", None),
    ],
)
def test_preco_para_float(bruto, esperado):
    """O ponto é separador de milhar e a vírgula é decimal; sem dígito nenhum sobra
    None em vez de estourar."""
    assert coletor._preco_para_float(bruto) == esperado


def test_preco_do_slot_prefere_sessenta_minutos():
    """Com várias durações abertas, a hora cheia é a que interessa ao CSV."""
    assert coletor._preco_do_slot(["30 min. R$80", "60 min. R$150"]) == 150.0


def test_preco_do_slot_usa_a_primeira_com_preco_sem_sessenta():
    """Sem opção de 60 min, vale a primeira duração que traga preço."""
    assert coletor._preco_do_slot(["90 min. R$200", "120 min. R$260"]) == 200.0


@pytest.mark.parametrize("textos", [["sem preço"], []])
def test_preco_do_slot_sem_candidato(textos):
    """Slot cujo preço não abriu devolve None, e não um zero que mentiria no CSV."""
    assert coletor._preco_do_slot(textos) is None


@pytest.fixture
def quadras_com_precos(carregar_fixture):
    """Carrega a fixture de duas quadras que compartilham o horário 17:00 com preços
    diferentes, que é o cenário onde o escopo importa."""
    pagina = carregar_fixture("slot_com_precos.html")
    return coletor._extrair_quadras(pagina, "Futebol de salão", "Tarde")


@pytest.mark.parametrize("indice, esperado", [(0, 150.0), (1, 90.0)])
def test_preco_vem_da_quadra_escopada(quadras_com_precos, indice, esperado):
    """Regressão do preço trocado: as duas quadras têm um 17:00 Livre, e buscar o
    horário na página inteira devolveria sempre o preço da primeira. Escopando a busca
    ao bloco da quadra, cada uma fica com o seu."""
    quadra = quadras_com_precos[indice]
    horarios = quadra["horarios"]
    coletor._coletar_precos(quadra["raiz"], horarios)

    livre = next(h for h in horarios if h["status"] == "Livre")
    assert livre["valor"] == esperado


def test_indisponivel_fica_sem_valor(quadras_com_precos):
    """Slot indisponível não tem preço para abrir, então não ganha a chave `valor`."""
    quadra = quadras_com_precos[0]
    coletor._coletar_precos(quadra["raiz"], quadra["horarios"])

    indisponivel = next(h for h in quadra["horarios"] if h["status"] == "Indisponível")
    assert "valor" not in indisponivel
