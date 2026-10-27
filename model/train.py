"""Treina o modelo de ocupação das quadras a partir de clima e horário."""

import argparse
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, mean_absolute_error, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupKFold

from postprocessing.prices import _court_key, _extraction_files

NUMERIC_FEATURES = ["hora", "dia_semana", "temperatura", "umidade", "precipitacao", "velocidade_vento"]
CATEGORICAL_FEATURES = ["periodo", "clima", "tipo_quadra", "quadra_coberta"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
UNAVAILABLE_PREFIX = "Indispon"
FOLDS = 5
OCCUPIED_THRESHOLD = 0.5


def load_extraction(extraction_dir: str, excluded: set[str]) -> pd.DataFrame:
    """Lê as quadras da extração em uma tabela só, pulando as arenas de `excluded`
    e guardando a pasta da arena e o arquivo da quadra de cada linha."""
    frames = []
    for path in _extraction_files(extraction_dir):
        arena, court_file = _court_key(path, extraction_dir)
        if arena in excluded:
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df["arena_pasta"] = arena
        df["quadra_arquivo"] = court_file
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria hora e dia da semana, converte clima para número ou categoria e calcula
    o alvo: quanto o horário ficou acima ou abaixo da ocupação normal da sua quadra."""
    df = df.copy()
    df["ocupado"] = df["status"].str.startswith(UNAVAILABLE_PREFIX).astype(int)
    hours, minutes = df["horario_inicio"].str.split(":", expand=True).astype(int).T.values
    df["hora"] = hours + minutes / 60
    df["dia_semana"] = pd.to_datetime(df["data"]).dt.dayofweek
    for column in ["temperatura", "umidade", "precipitacao", "velocidade_vento"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        df[column] = df[column].replace("", np.nan).astype("category")
    df["normal_da_quadra"] = df.groupby(["arena_pasta", "quadra_arquivo"])["ocupado"].transform("mean")
    df["alvo"] = df["ocupado"] - df["normal_da_quadra"]
    return df


def new_model() -> HistGradientBoostingRegressor:
    """Cria o regressor de gradient boosting que lida sozinho com categorias e
    valores de clima ausentes."""
    return HistGradientBoostingRegressor(categorical_features="from_dtype", random_state=0)


def evaluate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Valida com GroupKFold por arena, testando sempre em arenas que o modelo não
    viu, e devolve as métricas de cada rodada e a importância média de cada coluna."""
    rows, importances = [], []
    for fold, (train, test) in enumerate(GroupKFold(FOLDS).split(df, groups=df["arena_pasta"]), 1):
        train_df, test_df = df.iloc[train], df.iloc[test]
        model = new_model().fit(train_df[FEATURES], train_df["alvo"])
        predicted = model.predict(test_df[FEATURES])
        with_model = np.clip(test_df["normal_da_quadra"] + predicted, 0, 1)
        rows.append({
            "rodada": fold,
            "arenas_teste": test_df["arena_pasta"].nunique(),
            "linhas_teste": len(test_df),
            "erro_sem_modelo": mean_absolute_error(test_df["alvo"], np.zeros(len(test_df))),
            "erro_com_modelo": mean_absolute_error(test_df["alvo"], predicted),
            "auc_so_normal": roc_auc_score(test_df["ocupado"], test_df["normal_da_quadra"]),
            "auc_com_modelo": roc_auc_score(test_df["ocupado"], with_model),
        })
        result = permutation_importance(model, test_df[FEATURES], test_df["alvo"],
                                        scoring="neg_mean_absolute_error", n_repeats=5, random_state=0)
        importances.append(pd.Series(result.importances_mean, index=FEATURES))
    return pd.DataFrame(rows), pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False)


def evaluate_holdout(df: pd.DataFrame, test_fraction: float) -> tuple[pd.DataFrame, ...]:
    """Treina com os dias mais antigos e valida nos mais recentes, cortando por dia inteiro
    em `test_fraction` das linhas, e devolve a separação, as métricas contra chutar sempre
    Livre e contra só o normal da quadra, a matriz de confusão e o resultado por período."""
    df = df.sort_values(["data", "horario_inicio"], ignore_index=True)
    cut = df["data"].iloc[int(len(df) * (1 - test_fraction))]
    train, test = df[df["data"] < cut].copy(), df[df["data"] >= cut].copy()
    court = ["arena_pasta", "quadra_arquivo"]
    normal = train.groupby(court)["ocupado"].mean().rename("normal_treino")
    train, test = train.join(normal, on=court), test.join(normal, on=court)
    test["normal_treino"] = test["normal_treino"].fillna(train["ocupado"].mean())
    model = new_model().fit(train[FEATURES], train["ocupado"] - train["normal_treino"])
    test["probabilidade"] = np.clip(test["normal_treino"] + model.predict(test[FEATURES]), 0, 1)
    test["previsto"] = (test["probabilidade"] >= OCCUPIED_THRESHOLD).astype(int)

    split = pd.DataFrame([
        {"conjunto": name, "inicio": part["data"].min(), "fim": part["data"].max(),
         "linhas": len(part), "fracao": len(part) / len(df)}
        for name, part in [("treino", train), ("validacao", test)]
    ])
    rows = []
    for name, probability in [("sempre Livre", pd.Series(0.0, index=test.index)),
                              ("so normal da quadra", test["normal_treino"]),
                              ("modelo", test["probabilidade"])]:
        predicted = (probability >= OCCUPIED_THRESHOLD).astype(int)
        rows.append({
            "abordagem": name,
            "acerto": accuracy_score(test["ocupado"], predicted),
            "auc": roc_auc_score(test["ocupado"], probability),
            "precisao": precision_score(test["ocupado"], predicted, zero_division=0),
            "recall": recall_score(test["ocupado"], predicted),
        })
    confusion = pd.crosstab(test["ocupado"].map({0: "real Livre", 1: "real Ocupado"}),
                            test["previsto"].map({0: "previu Livre", 1: "previu Ocupado"}))
    by_period = test.assign(acertou=test["previsto"] == test["ocupado"]).groupby("periodo", observed=True).agg(
        linhas=("acertou", "size"),
        acerto=("acertou", "mean"),
        ocupacao_real=("ocupado", "mean"),
        ocupacao_prevista=("probabilidade", "mean"),
    )
    return split, pd.DataFrame(rows), confusion, by_period


def main() -> None:
    """Lê a extração, as arenas excluídas e a fração de teste da linha de comando, valida o
    modelo por arena e, se pedido, pelos dias mais recentes, e salva o modelo treinado."""
    parser = argparse.ArgumentParser(
        description="Treina o modelo de ocupação das quadras a partir de clima e horário."
    )
    parser.add_argument("extracao", help="pasta da extração, por exemplo .extracoes-ate-27-09-2026-pos-processamento")
    parser.add_argument("--saida", required=True, help="arquivo do modelo, por exemplo .modelo/ocupacao.joblib")
    parser.add_argument("--excluir", nargs="*", default=[], help="pastas de arena que ficam de fora")
    parser.add_argument("--teste", type=float,
                        help="fração das linhas, nos dias mais recentes, usada para validar; por exemplo 0.1")
    arguments = parser.parse_args()
    if not os.path.isdir(arguments.extracao):
        parser.error(f"diretório não encontrado: {arguments.extracao}")
    unknown = [arena for arena in arguments.excluir
               if not os.path.isdir(os.path.join(arguments.extracao, arena))]
    if unknown:
        parser.error(f"arena não encontrada na extração: {', '.join(unknown)}")
    if arguments.teste is not None and not 0 < arguments.teste < 1:
        parser.error("--teste deve estar entre 0 e 1")

    df = build_features(load_extraction(arguments.extracao, set(arguments.excluir)))
    print(f"dados: {len(df)} linhas, {df.groupby(['arena_pasta', 'quadra_arquivo']).ngroups} quadras, "
          f"{df['arena_pasta'].nunique()} arenas, cidades: {', '.join(sorted(df['cidade'].unique()))}")
    metrics, importance = evaluate(df)
    print(metrics.round(4).to_string(index=False))
    print("média:\n" + metrics.drop(columns="rodada").mean().round(4).to_string())
    print("importância (quanto o erro piora sem a coluna):\n" + importance.round(4).to_string())

    if arguments.teste is not None:
        split, holdout, confusion, by_period = evaluate_holdout(df, arguments.teste)
        print(f"\nvalidação nos dias mais recentes ({arguments.teste:.0%}):")
        print(split.round(4).to_string(index=False))
        print(holdout.round(4).to_string(index=False))
        print(confusion.to_string())
        print(by_period.round(4).to_string())

    model = new_model().fit(df[FEATURES], df["alvo"])
    os.makedirs(os.path.dirname(arguments.saida) or ".", exist_ok=True)
    joblib.dump({"modelo": model, "colunas": FEATURES}, arguments.saida)
    print(f"modelo treinado com {len(df)} linhas de {df['arena_pasta'].nunique()} arenas -> {arguments.saida}")


if __name__ == "__main__":
    main()
