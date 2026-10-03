"""Testes das falhas humanas simuladas, com uma página dublê."""

import random

from extrator import human


class Alvo:
    def __init__(self, nome, log):
        self.nome = nome
        self.log = log

    def click(self, **kwargs):
        self.log.append(f"click:{self.nome}")

    def hover(self):
        self.log.append(f"hover:{self.nome}")


class Mouse:
    def __init__(self, log):
        self.log = log

    def wheel(self, x, y):
        self.log.append(("wheel", x, y))


class PaginaFalsa:
    def __init__(self):
        self.log = []
        self.mouse = Mouse(self.log)

    def go_back(self):
        self.log.append("back")


def test_falhas_humanas_sorteiam_as_quatro_variantes(monkeypatch):
    vistas = set()
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    for i in range(40):
        pagina = PaginaFalsa()
        intended = Alvo("certo", pagina.log)
        distractor = Alvo("errado", pagina.log)
        vistas.add(
            human.simulate_human_failure(
                pagina, intended, distractor, rng=random.Random(i)
            )
        )
    assert vistas == {"wrong_click", "redo", "hover_hesitate", "overscroll"}


def test_clique_errado_volta_e_pausa_entre_os_passos(monkeypatch):
    pausas = []
    monkeypatch.setattr(human, "wait_between_clicks", lambda: pausas.append("pausa"))
    pagina = PaginaFalsa()
    intended = Alvo("certo", pagina.log)
    distractor = Alvo("errado", pagina.log)

    tipo = human.simulate_human_failure(
        pagina, intended, distractor, rng=_rng_fixo("wrong_click")
    )

    assert tipo == "wrong_click"
    assert pagina.log == ["click:errado", "back"]
    assert len(pausas) >= 2


def test_refazer_volta_e_repete_o_alvo(monkeypatch):
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    pagina = PaginaFalsa()
    intended = Alvo("certo", pagina.log)

    tipo = human.simulate_human_failure(
        pagina, intended, rng=_rng_fixo("redo")
    )

    assert tipo == "redo"
    assert pagina.log == ["back", "click:certo"]


def test_hesita_no_alvo_sem_clicar(monkeypatch):
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    pagina = PaginaFalsa()
    intended = Alvo("certo", pagina.log)

    tipo = human.simulate_human_failure(
        pagina, intended, rng=_rng_fixo("hover_hesitate")
    )

    assert tipo == "hover_hesitate"
    assert pagina.log == ["hover:certo"]
    assert "click:certo" not in pagina.log


def test_rola_alem_e_volta(monkeypatch):
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    pagina = PaginaFalsa()

    tipo = human.simulate_human_failure(pagina, rng=_rng_fixo("overscroll"))

    assert tipo == "overscroll"
    assert pagina.log[0][0] == "wheel"
    assert pagina.log[0][2] > 0
    assert pagina.log[1][0] == "wheel"
    assert pagina.log[1][2] < 0


class _rng_fixo:
    def __init__(self, escolhido):
        self.escolhido = escolhido

    def choice(self, opcoes):
        return self.escolhido
