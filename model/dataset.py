"""Junta as quadras de uma extração em um arquivo só, o dataset do modelo."""

import argparse
import os

import pandas as pd

from postprocessing.covered import clean_court_name
from postprocessing.prices import _court_key, _extraction_files


def build_dataset(extraction_dir: str, excluded: set[str]) -> pd.DataFrame:
    frames = []
    for path in _extraction_files(extraction_dir):
        arena, court_file = _court_key(path, extraction_dir)
        if arena in excluded:
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df.insert(1, "arena_pasta", arena)
        df.insert(2, "quadra", clean_court_name(court_file))
        frames.append(df)
    dataset = pd.concat(frames, ignore_index=True)
    dataset["status"] = dataset["status"].str.replace(r"\d+$", "", regex=True)
    return dataset.sort_values(["arena_pasta", "quadra", "data", "horario_inicio"], ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Junta as quadras de uma extração em um arquivo só, o dataset do modelo."
    )
    parser.add_argument("extracao", help="pasta da extração, por exemplo .extracoes-ate-27-09-2026-pos-processamento")
    parser.add_argument("--saida", required=True, help="CSV a gerar, por exemplo .dataset/base.csv")
    parser.add_argument("--excluir", nargs="*", default=[], help="pastas de arena que ficam de fora")
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.extracao):
        parser.error(f"diretório não encontrado: {arguments.extracao}")
    unknown = [arena for arena in arguments.excluir
               if not os.path.isdir(os.path.join(arguments.extracao, arena))]
    if unknown:
        parser.error(f"arena não encontrada na extração: {', '.join(unknown)}")

    dataset = build_dataset(arguments.extracao, set(arguments.excluir))
    os.makedirs(os.path.dirname(arguments.saida) or ".", exist_ok=True)
    dataset.to_csv(arguments.saida, index=False)

    summary = dataset.groupby("arena_pasta").agg(
        quadras=("quadra", "nunique"),
        linhas=("status", "size"),
        indisponiveis=("status", lambda status: (status == "Indisponível").sum()),
        dias=("data", "nunique"),
    )
    print(summary.to_string())
    print(f"total: {len(dataset)} linhas, {summary['quadras'].sum()} quadras, "
          f"{dataset['arena_pasta'].nunique()} arenas -> {arguments.saida}")


if __name__ == "__main__":
    main()
