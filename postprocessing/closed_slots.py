"""Remove os horários em que a arena está fechada, a partir de uma tabela manual."""

import argparse
import csv
import os
from collections import defaultdict

import pandas as pd

from postprocessing.prices import _court_key, _day_type, _extraction_files, _parse_day, clean_court_name

ALL_COURTS = "*"


def _read_table(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as table:
        return list(csv.DictReader(table))


def _is_closed(rules: list[dict[str, str]], day: str, start: str) -> bool:
    parsed = _parse_day(day)
    if parsed is None:
        return False
    day_type = _day_type(parsed)
    return any(rule["tipo_dia"] == day_type and rule["inicio"] <= start < rule["fim"] for rule in rules)


class ClosedSlotRemover:
    def __init__(self, target_dir: str, table: list[dict[str, str]]) -> None:
        self.target_dir = target_dir
        self.table = table

    def apply(self) -> dict[tuple[str, str], int]:
        report = {}
        for path in _extraction_files(self.target_dir):
            arena, court_file = _court_key(path, self.target_dir)
            court = clean_court_name(court_file)
            rules = [rule for rule in self.table
                     if rule["arena_pasta"] == arena and rule["quadra"] in (ALL_COURTS, court)]
            if not rules:
                continue
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            closed = df.apply(lambda row: _is_closed(rules, row["data"], row["horario_inicio"]), axis=1)
            report[(arena, court)] = int(closed.sum())
            if closed.any():
                df[~closed].to_csv(path, index=False)
        return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove os horários em que a arena está fechada, a partir de uma tabela manual."
    )
    parser.add_argument("destino", help="extração da qual os horários fechados serão removidos")
    parser.add_argument("--tabela", required=True, help="CSV com arena_pasta,quadra,tipo_dia,inicio,fim")
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.destino):
        parser.error(f"diretório não encontrado: {arguments.destino}")
    if not os.path.isfile(arguments.tabela):
        parser.error(f"tabela não encontrada: {arguments.tabela}")

    report = ClosedSlotRemover(arguments.destino, _read_table(arguments.tabela)).apply()
    for (arena, court), count in sorted(report.items()):
        print(f"{arena}/{court}: {count} linhas removidas")
    print(f"total: {sum(report.values())} linhas removidas")


if __name__ == "__main__":
    main()
