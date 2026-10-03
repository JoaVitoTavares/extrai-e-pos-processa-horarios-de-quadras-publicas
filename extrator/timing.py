"""Intervalo aleatório entre acessos ao site de reservas."""

import random
import time

from extrator.config import ACCESS_INTERVAL_MAX_S, ACCESS_INTERVAL_MIN_S


def random_access_interval_s(rand_num_gen=None) -> float:
    """Sorteia a pausa entre requisições, de alguns segundos até no máximo 3 minutos."""
    generator = rand_num_gen if rand_num_gen is not None else random
    return generator.uniform(ACCESS_INTERVAL_MIN_S, ACCESS_INTERVAL_MAX_S)


def wait_between_accesses(sleeper=None, rand_num_gen=None) -> float:
    """Espera o intervalo aleatório entre requisições e devolve os segundos de pausa."""
    seconds = random_access_interval_s(rand_num_gen)
    (sleeper or time.sleep)(seconds)
    return seconds


def wait_between_clicks(sleeper=None, rand_num_gen=None) -> float:
    """Pausa entre cliques e interações com o mesmo intervalo sorteado entre requisições."""
    return wait_between_accesses(sleeper=sleeper, rand_num_gen=rand_num_gen)
