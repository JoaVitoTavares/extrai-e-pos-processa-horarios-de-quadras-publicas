"""Testes da troca de período, que é sincronizada pelo realce do botão."""

from datetime import date

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


class _Pagina:
    def locator(self, seletor):
        return self

    def inner_text(self):
        return "texto"


def _coletar_com_manha_travada(monkeypatch, com_preco):
    precos = []
    monkeypatch.setattr(courts_collector, "_wait_for_courts", lambda page, **kwargs: None)
    monkeypatch.setattr(
        courts_collector, "_collect_prices", lambda root, horarios: precos.append(root)
    )

    def selecionar(page, period, previous, timeout_ms=6_000):
        if period == "Manhã":
            raise PWTimeout("período")
        return "ok"

    def extrair(page, sport, period, day, types=None):
        return [{
            "periodo": period,
            "quadra": "Areia 1",
            "horarios": [{"hora": "10:00", "status": "Livre"}],
            "aviso": None,
            "raiz": f"raiz-{period}",
        }]

    monkeypatch.setattr(courts_collector, "_select_period", selecionar)
    monkeypatch.setattr(courts_collector, "_extract_courts", extrair)
    coletado = courts_collector._collect_day(
        _Pagina(), "Vôlei de praia", date(2026, 8, 7),
        ["Manhã", "Tarde", "Noite"], com_preco, ["Vôlei de praia"],
    )
    return coletado, precos


def test_periodo_que_nao_responde_deixa_os_outros_e_so_le_preco_quando_pedido(monkeypatch):
    com_preco, precos = _coletar_com_manha_travada(monkeypatch, True)
    sem_preco, precos_vazios = _coletar_com_manha_travada(monkeypatch, False)

    assert [item["periodo"] for item in com_preco] == ["Tarde", "Noite"]
    assert "raiz" not in com_preco[0]
    assert precos == ["raiz-Tarde", "raiz-Noite"]
    assert [item["periodo"] for item in sem_preco] == ["Tarde", "Noite"]
    assert precos_vazios == []
