"""Remove as linhas repetidas de uma mesma arena, quadra, data e horário."""

import argparse
import os
from collections import defaultdict

import pandas as pd

from postprocessing.covered import clean_court_name
from postprocessing.prices import _court_key, _extraction_files

SLOT_KEY = ["arena_pasta", "quadra", "data", "horario_inicio"]


def _normalized_status(status: pd.Series) -> pd.Series:
    return status.str.replace(r"\d+$", "", regex=True)


class DuplicateRemover:
    def __init__(self, target_dir: str) -> None:
        self.target_dir = target_dir

    def apply(self) -> dict[tuple[str, str], dict[str, int]]:
        frames = {}
        for path in _extraction_files(self.target_dir):
            arena, court_file = _court_key(path, self.target_dir)
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            frames[path] = df.assign(
                arena_pasta=arena, quadra=clean_court_name(court_file), arquivo=path, linha=df.index
            )
        rows = pd.concat(frames.values(), ignore_index=True)
        repeated = rows[rows.duplicated(SLOT_KEY, keep=False)]
        kept = repeated.sort_values("ultima_atualizacao", kind="stable").drop_duplicates(
            SLOT_KEY, keep="last"
        )
        removed = repeated.drop(kept.index)

        report = defaultdict(lambda: defaultdict(int))
        for (arena, court), group in repeated.groupby(["arena_pasta", "quadra"]):
            statuses = _normalized_status(group["status"]).groupby(
                [group["data"], group["horario_inicio"]]
            ).nunique()
            report[(arena, court)]["horários repetidos"] = len(statuses)
            report[(arena, court)]["com status divergente"] = int((statuses > 1).sum())
            report[(arena, court)]["linhas removidas"] = int(
                (removed["arena_pasta"].eq(arena) & removed["quadra"].eq(court)).sum()
            )

        for path, lines in removed.groupby("arquivo")["linha"]:
            frames[path].drop(index=lines).drop(
                columns=["arena_pasta", "quadra", "arquivo", "linha"]
            ).to_csv(path, index=False)
        return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove as linhas repetidas de uma mesma arena, quadra, data e horário."
    )
    parser.add_argument("destino", help="extração da qual as linhas repetidas serão removidas")
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.destino):
        parser.error(f"diretório não encontrado: {arguments.destino}")

    report = DuplicateRemover(arguments.destino).apply()
    if not report:
        print("total: nenhum horário repetido")
        return
    totals = defaultdict(int)
    for (arena, court), counts in sorted(report.items()):
        print(f"{arena}/{court}: " + ", ".join(f"{count} {label}" for label, count in counts.items()))
        for label, count in counts.items():
            totals[label] += count
    print("total: " + ", ".join(f"{count} {label}" for label, count in totals.items()))


if __name__ == "__main__":
    main()
