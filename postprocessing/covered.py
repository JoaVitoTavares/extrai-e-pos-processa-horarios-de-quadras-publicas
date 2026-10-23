"""Preenche a coluna quadra_coberta pelo nome da quadra e por uma tabela manual."""

import argparse
import csv
import os
from collections import defaultdict

import pandas as pd

from extrator.courts_collector import COVERED_PATTERN, FUTSAL_PATTERN, UNCOVERED_PATTERN
from extrator.persistencia import sem_acento
from postprocessing.prices import _court_key, _extraction_files, clean_court_name


def _covered_by_name(court: str, court_type: str) -> str:
    name = sem_acento(court)
    if UNCOVERED_PATTERN.search(name):
        return "false"
    if COVERED_PATTERN.search(name) or FUTSAL_PATTERN.search(name + " " + sem_acento(court_type)):
        return "true"
    return ""


def _read_table(path: str) -> dict[tuple[str, str], str]:
    with open(path, newline="", encoding="utf-8") as table:
        return {(row["arena_pasta"], row["quadra"]): row["coberta"] for row in csv.DictReader(table)}


class CoveredFiller:
    def __init__(self, target_dir: str, table: dict[tuple[str, str], str]) -> None:
        self.target_dir = target_dir
        self.table = table

    def apply(self) -> dict[tuple[str, str], dict[str, int]]:
        report = defaultdict(lambda: defaultdict(int))
        for path in _extraction_files(self.target_dir):
            arena, court_file = _court_key(path, self.target_dir)
            court = clean_court_name(court_file)
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            court_type = df["tipo_quadra"].iloc[0] if len(df) else ""
            by_name = _covered_by_name(court, court_type)
            by_table = self.table.get((arena, court), "")
            if by_name and by_table and by_name != by_table:
                report[(arena, court)]["divergente (nome x tabela)"] += len(df)
                continue
            expected, source = (by_name, "pelo nome") if by_name else (by_table, "pela tabela")
            empty = df["quadra_coberta"] == ""
            filled = df.loc[~empty, "quadra_coberta"]
            report[(arena, court)]["já tinha valor"] += len(filled)
            report[(arena, court)]["divergente (já tinha valor)"] += int(
                (filled != expected).sum() if expected else 0
            )
            if not empty.any():
                continue
            if not expected:
                report[(arena, court)]["sem informação"] += int(empty.sum())
                continue
            df.loc[empty, "quadra_coberta"] = expected
            report[(arena, court)][f"preenchida {source} ({expected})"] += int(empty.sum())
            df.to_csv(path, index=False)
        return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preenche quadra_coberta vazia pelo nome da quadra e por uma tabela manual."
    )
    parser.add_argument("destino", help="extração cuja coluna quadra_coberta será preenchida")
    parser.add_argument("--tabela", required=True, help="CSV com arena_pasta,quadra,coberta")
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.destino):
        parser.error(f"diretório não encontrado: {arguments.destino}")
    if not os.path.isfile(arguments.tabela):
        parser.error(f"tabela não encontrada: {arguments.tabela}")

    report = CoveredFiller(arguments.destino, _read_table(arguments.tabela)).apply()
    totals = defaultdict(int)
    for (arena, court), counts in sorted(report.items()):
        details = ", ".join(f"{count} {label}" for label, count in counts.items() if count)
        print(f"{arena}/{court}: {details}")
        for label, count in counts.items():
            totals[label] += count
    print("total: " + ", ".join(f"{count} {label}" for label, count in sorted(totals.items()) if count))


if __name__ == "__main__":
    main()
