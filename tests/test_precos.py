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


class _NoSlot:
    def __init__(self, hour, fail):
        self.hour = hour
        self.fail = fail

    @property
    def first(self):
        return self

    def locator(self, xpath):
        if self.fail and "ancestor" in xpath:
            raise PWTimeout("sem o slot")
        return self

    def click(self, **kwargs):
        if self.fail:
            raise PWTimeout("clique")

    def wait_for(self, **kwargs):
        return None

    def all_text_contents(self):
        return ["60 min. R$ 80,00"]

    def text_content(self):
        return ""


class _PriceRoot:
    def get_by_text(self, hour, exact=True):
        return _NoSlot(hour, fail=hour == "17:00")


def test_clique_que_estoura_o_tempo_nao_impede_o_proximo_preco():
    horarios = [
        {"hora": "17:00", "status": "Livre"},
        {"hora": "18:00", "status": "Livre"},
    ]

    courts_collector._collect_prices(_PriceRoot(), horarios)

    assert "valor" not in horarios[0]
    assert horarios[1]["valor"] == 80.0


class _Hoje(date):
    @classmethod
    def today(cls):
        return date(2026, 8, 7)


class _Browser:
    def launch(self, **kwargs):
        return self

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self

    def goto(self, *args, **kwargs):
        return None

    def locator(self, selector):
        return self

    def close(self):
        return None


class _Playwright:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def chromium(self):
        return _Browser()


def test_preco_so_no_dia_de_hoje_e_dia_perdido_nao_apaga_os_outros(monkeypatch):
    chamadas = []
    monkeypatch.setattr(courts_collector, "date", _Hoje)
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", False)
    monkeypatch.setattr(courts_collector, "captcha_detected", lambda page: False)
    monkeypatch.setattr(courts_collector, "_choose_sport", lambda *args, **kwargs: True)
    monkeypatch.setattr(courts_collector, "simulate_human_failure", lambda *args, **kwargs: None)
    monkeypatch.setattr(courts_collector, "extract_address", lambda *args, **kwargs: "Rua 1, Canoas")
    monkeypatch.setattr(courts_collector, "sync_playwright", lambda: _Playwright())

    def selecionar_dia(page, day, timeout_ms=30_000, attempts=3):
        if day == date(2026, 8, 8):
            raise PWTimeout("calendário")

    def coletar_dia(page, sport, day, periods, with_price, types):
        chamadas.append((day, with_price, periods))
        return [{"quadra": "Areia 1", "horarios": [], "aviso": None, "data": day.isoformat()}]

    monkeypatch.setattr(courts_collector, "_select_day", selecionar_dia)
    monkeypatch.setattr(courts_collector, "_collect_day", coletar_dia)

    resultados = courts_collector.collect_schedules(
        "Vôlei de praia",
        "https://webarena.app/arena/x",
        period="Noite",
        days_from=0,
        days_ahead=2,
    )

    assert chamadas == [
        (date(2026, 8, 7), True, ["Noite"]),
        (date(2026, 8, 9), False, ["Noite"]),
    ]
    assert [item["data"] for item in resultados] == ["2026-08-07", "2026-08-09"]
    assert {item["endereco"] for item in resultados} == {"Rua 1, Canoas"}
