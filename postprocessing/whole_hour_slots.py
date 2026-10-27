"""Remove os horários de meia hora que se sobrepõem aos de hora cheia."""

import argparse
import os

import pandas as pd

from extrator.persistencia import SUFIXO_CSV
from postprocessing.half_hour_slots import _minutes, _overlaps
from postprocessing.prices import _court_key, _extraction_files

FREE_STATUS = "Livre"


def _interval(start: str, end: str) -> tuple[int, int]:
    """Devolve início e fim em minutos, somando um dia ao fim quando o horário
    passa da meia-noite."""
    begin, finish = _minutes(start), _minutes(end)
    return begin, finish + (1440 if finish <= begin else 0)


def _resolve_day(day: pd.DataFrame) -> tuple[dict[int, str], list[int]]:
    """Compara cada H:00 com o H:30 do mesmo dia, marcando o H:00 como indisponível
    quando um dos dois estiver, e lista os H:30 que se sobrepõem a algum H:00."""
    whole = day[day["horario_inicio"].str.endswith(":00")]
    half = day[day["horario_inicio"].str.endswith(":30")]
    half_by_start = dict(zip(half["horario_inicio"], half.index))
    new_status = {}
    for index, row in whole.iterrows():
        pair = half_by_start.get(row["horario_inicio"][:3] + "30")
        if pair is None:
            continue
        statuses = [row["status"], day.at[pair, "status"]]
        unavailable = [status for status in statuses if status != FREE_STATUS]
        if unavailable and row["status"] == FREE_STATUS:
            new_status[index] = unavailable[0]
    whole_intervals = [_interval(s, e) for s, e in zip(whole["horario_inicio"], whole["horario_fim"])]
    to_remove = []
    for index, row in half.iterrows():
        start, end = _interval(row["horario_inicio"], row["horario_fim"])
        if any(start < other_end and other_start < end for other_start, other_end in whole_intervals):
            to_remove.append(index)
    return new_status, to_remove


class WholeHourResolver:
    def __init__(self, target_dir: str, arenas: list[str], courts: list[str] | None) -> None:
        self.target_dir = target_dir
        self.arenas = arenas
        self.courts = courts

    def apply(self) -> dict[tuple[str, str], dict[str, int]]:
        """Aplica a prioridade do indisponível e remove os H:30 sobrepostos em cada
        quadra das arenas informadas, devolvendo por quadra os status alterados,
        as linhas removidas e as sobreposições antes e depois."""
        report = {}
        for path in _extraction_files(self.target_dir):
            arena, court_file = _court_key(path, self.target_dir)
            if arena not in self.arenas:
                continue
            if self.courts and court_file[:-len(SUFIXO_CSV)] not in self.courts:
                continue
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            before = _overlaps(df)
            new_status, to_remove = {}, []
            for _, day in df.groupby("data"):
                day_status, day_remove = _resolve_day(day)
                new_status.update(day_status)
                to_remove.extend(day_remove)
            for index, status in new_status.items():
                df.at[index, "status"] = status
            df = df.drop(index=to_remove)
            report[(arena, court_file)] = {
                "status alterados para indisponível": len(new_status),
                "linhas de meia hora removidas": len(to_remove),
                "sobreposições antes": before,
                "sobreposições depois": _overlaps(df),
            }
            if new_status or to_remove:
                df.to_csv(path, index=False)
        return report


def main() -> None:
    """Lê a extração, as arenas e as quadras da linha de comando, resolve os
    horários sobrepostos e imprime o relatório por quadra e o total."""
    parser = argparse.ArgumentParser(
        description="Remove os horários de meia hora que se sobrepõem aos de hora cheia."
    )
    parser.add_argument("destino", help="extração cujos horários serão ajustados")
    parser.add_argument("--arena", action="append", required=True,
                        help="pasta da arena a ajustar; pode ser repetida")
    parser.add_argument("--quadra", action="append",
                        help="quadra a ajustar, sem o sufixo -extracoes.csv; pode ser repetida")
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.destino):
        parser.error(f"diretório não encontrado: {arguments.destino}")
    for arena in arguments.arena:
        if not os.path.isdir(os.path.join(arguments.destino, arena)):
            parser.error(f"arena não encontrada: {arena}")

    report = WholeHourResolver(arguments.destino, arguments.arena, arguments.quadra).apply()
    totals = {}
    for (arena, court), counts in sorted(report.items()):
        print(f"{arena}/{court}: " + ", ".join(f"{count} {label}" for label, count in counts.items()))
        for label, count in counts.items():
            totals[label] = totals.get(label, 0) + count
    print("total: " + ", ".join(f"{count} {label}" for label, count in totals.items()))


if __name__ == "__main__":
    main()
