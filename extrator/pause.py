import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from extrator.access_windows import local_now
from extrator.config import DIRETORIO_LOGS, FUSO_HORARIO

CAPTCHA_PAUSE_HOURS = 2
PAUSE_LOCK_NAME = "captcha-paused-until"


class CaptchaPause(Exception):
    """Sinaliza que o captcha apareceu e as extrações devem parar."""


def pause_lock_path() -> str:
    """Caminho do arquivo com o instante até o qual a coleta fica pausada."""
    os.makedirs(DIRETORIO_LOGS, exist_ok=True)
    return os.path.join(DIRETORIO_LOGS, PAUSE_LOCK_NAME)


def engage_captcha_pause(moment: datetime | None = None) -> datetime:
    until = local_now(moment) + timedelta(hours=CAPTCHA_PAUSE_HOURS)
    with open(pause_lock_path(), "w", encoding="utf-8") as lock_file:
        lock_file.write(until.isoformat())
    return until


def is_paused(moment: datetime | None = None) -> bool:
    path = pause_lock_path()
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as lock_file:
        text = lock_file.read().strip()
    if not text:
        return False
    until = datetime.fromisoformat(text)
    if until.tzinfo is None:
        until = until.replace(tzinfo=ZoneInfo(FUSO_HORARIO))
    return local_now(moment) < until
