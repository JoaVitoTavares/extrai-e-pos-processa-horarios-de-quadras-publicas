"""Simulação de falhas humanas entre as interações na página."""

import random

from extrator.timing import wait_between_clicks

HUMAN_FAILURES = ("wrong_click", "redo", "hover_hesitate", "overscroll")
ON_PAGE_FAILURES = ("hover_hesitate", "overscroll")


def simulate_human_failure(
    page, intended=None, distractor=None, rand_num_gen=None, stay_on_page=False
) -> str:
    """Sorteia uma falha humana e executa, com pausas entre os passos. Com
    `stay_on_page`, limita o sorteio a hesitação e rolagem, sem voltar no
    histórico da página."""
    generator = rand_num_gen if rand_num_gen is not None else random
    options = ON_PAGE_FAILURES if stay_on_page else HUMAN_FAILURES
    kind = generator.choice(options)
    if kind == "wrong_click":
        _click_wrong_and_back(page, distractor)
    elif kind == "redo":
        _redo_same_action(page, intended)
    elif kind == "hover_hesitate":
        _hover_and_hesitate(intended)
    else:
        _overscroll_and_back(page)
    return kind


def _click_wrong_and_back(page, distractor) -> None:
    """Clica em um item errado e volta."""
    wait_between_clicks()
    if distractor is not None:
        distractor.click()
    wait_between_clicks()
    page.go_back()


def _redo_same_action(page, intended) -> None:
    """Volta e refaz a mesma operação no alvo pretendido."""
    wait_between_clicks()
    page.go_back()
    wait_between_clicks()
    if intended is not None:
        intended.click()


def _hover_and_hesitate(intended) -> None:
    """Passa o mouse sobre o elemento e hesita sem clicar."""
    wait_between_clicks()
    if intended is not None:
        intended.hover()
    wait_between_clicks()


def _overscroll_and_back(page) -> None:
    """Rola a página além do necessário e depois retorna."""
    wait_between_clicks()
    page.mouse.wheel(0, 900)
    wait_between_clicks()
    page.mouse.wheel(0, -900)
