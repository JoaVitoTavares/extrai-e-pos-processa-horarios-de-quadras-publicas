"""Logs de depuração, ligados por EXTRATOR_DEBUG."""

import os
import sys
import threading
from datetime import datetime

DEBUG_ENABLED = os.environ.get("EXTRATOR_DEBUG", "") not in ("", "0")

_CONTEXT = threading.local()


def set_context(name: str) -> None:
    _CONTEXT.name = name


def debug(message: str) -> None:
    if not DEBUG_ENABLED:
        return
    moment = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    name = getattr(_CONTEXT, "name", "-")
    print(f"[{moment}] [{name}] {message}", file=sys.stderr, flush=True)
