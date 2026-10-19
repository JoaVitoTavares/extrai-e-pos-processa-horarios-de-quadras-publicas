"""Preenche os preços vazios de uma extração com os preços de outra."""

import argparse
import glob
import os
from collections import defaultdict
from datetime import date

import pandas as pd

from extrator.persistencia import SUFIXO_CSV


def _day_type(day: str) -> str | None:
    try:
        weekday = date.fromisoformat(day).weekday()
    except ValueError:
        return None
    return "weekend" if weekday >= 5 else "weekday"


def _extraction_files(directory: str) -> list[str]:
    return sorted(glob.glob(os.path.join(directory, "*", "*" + SUFIXO_CSV)))


def _court_key(path: str, directory: str) -> tuple[str, str]:
    arena, court_file = os.path.relpath(path, directory).split(os.sep)
    return arena, court_file


class PriceFiller:
    def __init__(self, source_dir: str, target_dir: str) -> None:
        self.source_dir = source_dir
        self.target_dir = target_dir

    def apply(self) -> dict[str, dict[str, int]]:
        prices = self._source_prices()
        report = defaultdict(lambda: {"preenchidas": 0, "vazias": 0, "divergentes": 0})
        for path in _extraction_files(self.target_dir):
            arena, court_file = _court_key(path, self.target_dir)
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            changed = False
            for index, row in df[df["valor_horario"] == ""].iterrows():
                found = prices.get(
                    (arena, court_file, _day_type(row["data"]), row["horario_inicio"]), set()
                )
                if len(found) == 1:
                    df.at[index, "valor_horario"] = next(iter(found))
                    report[arena]["preenchidas"] += 1
                    changed = True
                else:
                    report[arena]["vazias"] += 1
                    if len(found) > 1:
                        report[arena]["divergentes"] += 1
            if changed:
                df.to_csv(path, index=False)
        return dict(report)

    def _source_prices(self) -> dict[tuple[str, str, str, str], set[str]]:
        prices = defaultdict(set)
        for path in _extraction_files(self.source_dir):
            arena, court_file = _court_key(path, self.source_dir)
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            for _, row in df[df["valor_horario"] != ""].iterrows():
                day_type = _day_type(row["data"])
                if day_type is not None:
                    prices[(arena, court_file, day_type, row["horario_inicio"])].add(
                        row["valor_horario"]
                    )
        return prices


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preenche os preços vazios do destino com os preços da origem."
    )
    parser.add_argument("origem", help="extração com os preços, por exemplo .extracoes")
    parser.add_argument("destino", help="extração cujos preços vazios serão preenchidos")
    arguments = parser.parse_args()
    for directory in (arguments.origem, arguments.destino):
        if not os.path.isdir(directory):
            parser.error(f"diretório não encontrado: {directory}")

    report = PriceFiller(arguments.origem, arguments.destino).apply()
    for arena, counts in sorted(report.items()):
        print(f"{arena}: {counts['preenchidas']} preenchidas, {counts['vazias']} vazias "
              f"({counts['divergentes']} por preço divergente)")
    print(f"total: {sum(c['preenchidas'] for c in report.values())} preenchidas, "
          f"{sum(c['vazias'] for c in report.values())} vazias")


if __name__ == "__main__":
    main()
