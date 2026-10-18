"""Testes da leitura de preço de um slot e do escopo dessa leitura à quadra certa."""

from datetime import date

import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from extrator import courts_collector

DIA = date(2026, 8, 7)


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("1.500,00", 1500.0),
        ("1.500,50", 1500.5),
        ("150", 150.0),
        ("89,90", 89.9),
        ("", None),
        ("grátis", None),
    ],
)
def test_preco_para_float(bruto, esperado):
    assert courts_collector._price_to_float(bruto) == esperado


def test_preco_do_slot_prefere_sessenta_minutos():
    assert courts_collector._slot_price(["30 min. R$80", "60 min. R$150"]) == 150.0


def test_preco_com_milhar_e_centavos_prefere_sessenta_minutos():
    assert courts_collector._slot_price(
        ["30 min. R$ 90,00", "60 min. R$ 1.500,50"]
    ) == 1500.5


def test_preco_do_slot_usa_a_primeira_com_preco_sem_sessenta():
    assert courts_collector._slot_price(["90 min. R$200", "120 min. R$260"]) == 200.0


@pytest.mark.parametrize("textos", [["sem preço"], []])
def test_preco_do_slot_sem_candidato(textos):
    assert courts_collector._slot_price(textos) is None


@pytest.fixture
def quadras_com_precos(carregar_fixture):
    pagina = carregar_fixture("slot_com_precos.html")
    return courts_collector._extract_courts(pagina, "Futebol de salão", "Tarde", DIA)


@pytest.mark.parametrize("indice, esperado", [(0, 150.0), (1, 90.0)])
def test_preco_vem_da_quadra_escopada(quadras_com_precos, indice, esperado):
    quadra = quadras_com_precos[indice]
    horarios = quadra["horarios"]
    courts_collector._collect_prices(quadra["raiz"], horarios)

    livre = next(h for h in horarios if h["status"] == "Livre")
    assert livre["valor"] == esperado


def test_indisponivel_fica_sem_valor(quadras_com_precos):
    quadra = quadras_com_precos[0]
    courts_collector._collect_prices(quadra["raiz"], quadra["horarios"])

    indisponivel = next(h for h in quadra["horarios"] if h["status"] == "Indisponível")
    assert "valor" not in indisponivel


class _PricePanel:
    def __init__(self, texts, times_out):
        self.texts = texts
        self.times_out = times_out
        self.first = self

    def wait_for(self, **kwargs):
        if self.times_out:
            raise PWTimeout("painel")

    def all_text_contents(self):
        return self.texts


class _PriceHeader:
    def __init__(self, text, panel_texts, times_out):
        self.text = text
        self.panel = _PricePanel(panel_texts, times_out)

    def locator(self, xpath):
        return self.panel

    def click(self, **kwargs):
        return None

    def text_content(self):
        return self.text


class _PriceHour:
    def __init__(self, header):
        self.first = self
        self.header = header

    def locator(self, xpath):
        return self.header


class _PriceRoot:
    def __init__(self, headers):
        self.headers = headers

    def get_by_text(self, hour, exact=True):
        return _PriceHour(self.headers[hour])


def test_painel_que_nao_abre_ainda_le_o_preco_do_cabecalho():
    horarios = [
        {"hora": "17:00", "status": "Livre"},
        {"hora": "18:00", "status": "Livre"},
    ]
    raiz = _PriceRoot({
        "17:00": _PriceHeader("17:00 - Livre\n60 min. R$ 120,00", [], True),
        "18:00": _PriceHeader("", ["60 min. R$ 80"], False),
    })

    courts_collector._collect_prices(raiz, horarios)

    assert horarios[0]["valor"] == 120.0
    assert horarios[1]["valor"] == 80.0
