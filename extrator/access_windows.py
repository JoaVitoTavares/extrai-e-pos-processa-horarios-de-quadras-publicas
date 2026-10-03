"""Janelas de horário em que o extrator pode acessar o site."""

import random
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from extrator.config import (
    FUSO_HORARIO,
    NIGHT_ACCESS_EVERY_H,
    NIGHT_END_HOUR,
    NIGHT_START_HOUR,
    PEAK_EVENING_END_HOUR,
    PEAK_EVENING_START_HOUR,
    PEAK_MORNING_END_HOUR,
    PEAK_MORNING_START_HOUR,
)


def local_now(moment: datetime | None = None) -> datetime:
    """Devolve o instante no fuso America/Sao_Paulo, usando agora quando nada é passado."""
    zone = ZoneInfo(FUSO_HORARIO)
    if moment is None:
        moment = datetime.now(zone)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=zone)
    return moment.astimezone(zone)


def night_access_allowed(moment: datetime | None = None) -> bool:
    """Na madrugada (00:00–06:00) libera um acesso a cada 3 horas; no restante do dia, sempre."""
    local = local_now(moment)
    if not (NIGHT_START_HOUR <= local.hour < NIGHT_END_HOUR):
        return True
    return (local.hour - NIGHT_START_HOUR) % NIGHT_ACCESS_EVERY_H == 0


def broken_time_in_window(start_hour: int, end_hour: int, rng=None) -> time:
    """Sorteia um horário quebrado (minuto diferente de zero) dentro de [start_hour, end_hour)."""
    generator = rng if rng is not None else random
    hour = generator.randrange(start_hour, end_hour)
    minute = generator.randint(1, 59)
    return time(hour, minute)


def peak_times_for_arena(arena_key: str, day: date, rng=None) -> tuple[time, time]:
    """Sorteia os dois horários de pico do dia para uma arena, estáveis no mesmo dia."""
    generator = rng if rng is not None else random.Random(f"{arena_key}:{day.isoformat()}")
    morning = broken_time_in_window(PEAK_MORNING_START_HOUR, PEAK_MORNING_END_HOUR, generator)
    evening = broken_time_in_window(PEAK_EVENING_START_HOUR, PEAK_EVENING_END_HOUR, generator)
    return morning, evening


def current_peak_window(moment: datetime | None = None) -> str | None:
    """Identifica se o instante cai na janela da manhã, da noite, ou em nenhuma das duas."""
    local = local_now(moment)
    if PEAK_MORNING_START_HOUR <= local.hour < PEAK_MORNING_END_HOUR:
        return "morning"
    if PEAK_EVENING_START_HOUR <= local.hour < PEAK_EVENING_END_HOUR:
        return "evening"
    return None
