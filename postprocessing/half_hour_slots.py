"""Converte os horários das arenas informadas para blocos de 30 minutos."""

import argparse
import os
from datetime import datetime, timedelta

import pandas as pd

from postprocessing.prices import _court_key, _extraction_files

SLOT_MINUTES = 30


def _minutes(time: str) -> int:
    """Converte um horário no formato HH:MM para minutos desde a meia-noite."""
    hours, minutes = time.split(":")
    return int(hours) * 60 + int(minutes)


def _half_hour_end(start: str) -> str:
    """Devolve o horário de fim de um bloco de 30 minutos que começa em `start`,
    virando para 00:00 quando o bloco termina na meia-noite."""
    end = datetime.strptime(start, "%H:%M") + timedelta(minutes=SLOT_MINUTES)
    return end.strftime("%H:%M")


def _overlaps(df: pd.DataFrame) -> int:
    """Conta, em cada data, os pares de horários consecutivos em que o próximo
    começa antes de o anterior terminar, tratando fim <= início como meia-noite."""
    total = 0
    for _, day in df.groupby("data"):
        slots = sorted(
            (_minutes(start), _minutes(end) + (1440 if _minutes(end) <= _minutes(start) else 0))
            for start, end in zip(day["horario_inicio"], day["horario_fim"])
        )
        total += sum(1 for current, following in zip(slots, slots[1:]) if following[0] < current[1])
    return total


class HalfHourConverter:
    def __init__(self, target_dir: str, arenas: list[str]) -> None:
        self.target_dir = target_dir
        self.arenas = arenas

    def apply(self) -> dict[tuple[str, str], dict[str, int]]:
        """Reescreve o horario_fim de cada quadra das arenas informadas como início
        mais 30 minutos e devolve, por quadra, as linhas convertidas e as
        sobreposições antes e depois."""
        report = {}
        for path in _extraction_files(self.target_dir):
            arena, court_file = _court_key(path, self.target_dir)
            if arena not in self.arenas:
                continue
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            before = _overlaps(df)
            new_end = df["horario_inicio"].map(_half_hour_end)
            changed = df["horario_fim"] != new_end
            df["horario_fim"] = new_end
            report[(arena, court_file)] = {
                "linhas convertidas": int(changed.sum()),
                "sobreposições antes": before,
                "sobreposições depois": _overlaps(df),
            }
            if changed.any():
                df.to_csv(path, index=False)
        return report


def main() -> None:
    """Lê a extração e as arenas da linha de comando, converte os horários e
    imprime o relatório por quadra e o total."""
    parser = argparse.ArgumentParser(
        description="Converte os horários das arenas informadas para blocos de 30 minutos."
    )
    parser.add_argument("destino", help="extração cujos horários serão convertidos")
    parser.add_argument("--arena", action="append", required=True,
                        help="pasta da arena a converter; pode ser repetida")
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.destino):
        parser.error(f"diretório não encontrado: {arguments.destino}")
    for arena in arguments.arena:
        if not os.path.isdir(os.path.join(arguments.destino, arena)):
            parser.error(f"arena não encontrada: {arena}")

    report = HalfHourConverter(arguments.destino, arguments.arena).apply()
    totals = {}
    for (arena, court), counts in sorted(report.items()):
        print(f"{arena}/{court}: " + ", ".join(f"{count} {label}" for label, count in counts.items()))
        for label, count in counts.items():
            totals[label] = totals.get(label, 0) + count
    print("total: " + ", ".join(f"{count} {label}" for label, count in totals.items()))


if __name__ == "__main__":
    main()
