"""Intervalo aleatório entre acessos ao site de reservas."""

import random
import time

from extrator.config import (
    ACCESS_INTERVAL_MAX_S,
    ACCESS_INTERVAL_MIN_S,
    CLICK_INTERVAL_MAX_S,
    CLICK_INTERVAL_MIN_S,
)


def random_access_interval_s(rand_num_gen=None) -> float:
    """Sorteia a pausa entre requisições ao site, curta o bastante para a rodada
    caber na folga do cron de 15 minutos."""
    generator = rand_num_gen if rand_num_gen is not None else random
    return generator.uniform(ACCESS_INTERVAL_MIN_S, ACCESS_INTERVAL_MAX_S)


def wait_between_accesses(sleeper=None, rand_num_gen=None) -> float:
    """Espera o intervalo entre requisições e devolve os segundos de pausa."""
    seconds = random_access_interval_s(rand_num_gen)
    (sleeper or time.sleep)(seconds)
    return seconds


def random_click_interval_s(rand_num_gen=None) -> float:
    """Sorteia a pausa entre cliques na mesma página, em fração de segundo."""
    generator = rand_num_gen if rand_num_gen is not None else random
    return generator.uniform(CLICK_INTERVAL_MIN_S, CLICK_INTERVAL_MAX_S)


def wait_between_clicks(sleeper=None, rand_num_gen=None) -> float:
    """Espera a pausa entre cliques e devolve os segundos."""
    seconds = random_click_interval_s(rand_num_gen)
    (sleeper or time.sleep)(seconds)
    return seconds
