"""Intervalo aleatório entre acessos ao site de reservas."""

import random
import time

from extrator.config import ACCESS_INTERVAL_MAX_S, ACCESS_INTERVAL_MIN_S


def random_access_interval_s(rng=None) -> float:
    """Sorteia a pausa entre requisições, de alguns segundos até no máximo 3 minutos."""
    generator = rng if rng is not None else random
    return generator.uniform(ACCESS_INTERVAL_MIN_S, ACCESS_INTERVAL_MAX_S)


def wait_between_accesses(sleeper=None, rng=None) -> float:
    """Espera o intervalo aleatório entre requisições e devolve os segundos de pausa."""
    seconds = random_access_interval_s(rng)
    (sleeper or time.sleep)(seconds)
    return seconds


def wait_between_clicks(sleeper=None, rng=None) -> float:
    """Pausa entre cliques e interações com o mesmo intervalo sorteado entre requisições."""
    return wait_between_accesses(sleeper=sleeper, rng=rng)
