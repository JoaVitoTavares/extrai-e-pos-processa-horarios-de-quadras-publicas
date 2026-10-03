"""Janelas de horário em que o extrator pode acessar o site."""

from datetime import datetime
from zoneinfo import ZoneInfo

from extrator.config import (
    FUSO_HORARIO,
    NIGHT_ACCESS_EVERY_H,
    NIGHT_END_HOUR,
    NIGHT_START_HOUR,
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
