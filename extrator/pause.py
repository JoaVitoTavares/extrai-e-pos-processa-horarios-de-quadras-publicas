"""Trava persistente que pausa extrações por duas horas após um captcha."""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from extrator.access_windows import local_now
from extrator.config import DIRETORIO_LOGS, FUSO_HORARIO

CAPTCHA_PAUSE_HOURS = 2
PAUSE_LOCK_NAME = "captcha-pausado-ate"


class CaptchaPause(Exception):
    """Sinaliza que o captcha apareceu e as extrações devem parar."""


def pause_lock_path() -> str:
    """Caminho do arquivo com o instante até o qual a coleta fica pausada."""
    os.makedirs(DIRETORIO_LOGS, exist_ok=True)
    return os.path.join(DIRETORIO_LOGS, PAUSE_LOCK_NAME)


def engage_captcha_pause(moment: datetime | None = None) -> datetime:
    """Grava a trava 'pausado até agora + 2 horas' no fuso America/Sao_Paulo."""
    until = local_now(moment) + timedelta(hours=CAPTCHA_PAUSE_HOURS)
    with open(pause_lock_path(), "w", encoding="utf-8") as arquivo:
        arquivo.write(until.isoformat())
    return until


def is_paused(moment: datetime | None = None) -> bool:
    """Diz se a trava ainda está dentro da janela de duas horas."""
    path = pause_lock_path()
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as arquivo:
        texto = arquivo.read().strip()
    if not texto:
        return False
    until = datetime.fromisoformat(texto)
    if until.tzinfo is None:
        until = until.replace(tzinfo=ZoneInfo(FUSO_HORARIO))
    return local_now(moment) < until
