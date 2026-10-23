"""Preenche os preços vazios de uma extração com os preços de outra."""

import argparse
import glob
import os
import re
from collections import defaultdict
from datetime import date

import pandas as pd

from extrator.persistencia import SUFIXO_CSV

SCHEDULE_IN_NAME_PATTERN = re.compile(r"(sem-horarios-cadastrados|\d{2}-\d{2}-(livre|indisponivel)).*$")
DAY_TYPES = ["weekday"] * 5 + ["saturday", "sunday"]


def clean_court_name(court_file: str) -> str:
    return SCHEDULE_IN_NAME_PATTERN.sub("", court_file.removesuffix(SUFIXO_CSV))


def _parse_day(day: str) -> date | None:
    try:
        return date.fromisoformat(day)
    except ValueError:
        return None


def _day_type(day: date) -> str:
    return DAY_TYPES[day.weekday()]


def _extraction_files(directory: str) -> list[str]:
    return sorted(glob.glob(os.path.join(directory, "*", "*" + SUFIXO_CSV)))


def _court_key(path: str, directory: str) -> tuple[str, str]:
    arena, court_file = os.path.relpath(path, directory).split(os.sep)
    return arena, court_file


def _nearest_prices(candidates: list[tuple[date, str]], day: date) -> set[str]:
    if not candidates:
        return set()
    distance = min(abs((candidate - day).days) for candidate, _ in candidates)
    return {price for candidate, price in candidates if abs((candidate - day).days) == distance}


class PriceFiller:
    def __init__(self, source_dir: str, target_dir: str) -> None:
        self.source_dir = source_dir
        self.target_dir = target_dir

    def apply(self) -> dict[str, dict[str, int]]:
        prices = self._source_prices()
        report = defaultdict(lambda: {"preenchidas": 0, "vazias": 0, "divergentes": 0})
        for path in _extraction_files(self.target_dir):
            arena, court_file = _court_key(path, self.target_dir)
            court = clean_court_name(court_file)
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            changed = False
            for index, row in df[df["valor_horario"] == ""].iterrows():
                day = _parse_day(row["data"])
                found = set()
                if day is not None:
                    candidates = prices.get((arena, court, _day_type(day), row["horario_inicio"]), [])
                    found = _nearest_prices(candidates, day)
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

    def _source_prices(self) -> dict[tuple[str, str, str, str], list[tuple[date, str]]]:
        prices = defaultdict(list)
        for path in _extraction_files(self.source_dir):
            arena, court_file = _court_key(path, self.source_dir)
            court = clean_court_name(court_file)
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            for _, row in df[(df["valor_horario"] != "") & (df["status"] == "Livre")].iterrows():
                day = _parse_day(row["data"])
                if day is not None:
                    prices[(arena, court, _day_type(day), row["horario_inicio"])].append(
                        (day, row["valor_horario"])
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
