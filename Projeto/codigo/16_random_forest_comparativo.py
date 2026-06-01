# -*- coding: utf-8 -*-
"""
16_random_forest_comparativo.py - RF comparativo com mesma config rigorosa do v3.

Treina Random Forest com:
  - Mesmas 34 features alinhadas ao v3 canônico
  - Mesma estratégia de tuning (Optuna 50 trials)
  - Mesma TimeSeriesSplit CV de 4 folds expandidos
  - Mesma métrica de objetivo (AUC-PR média da CV)
  - Mesma seed (42)

Objetivo: comparação empírica honesta entre LightGBM v3 (canônico) e
Random Forest tunado, validando que o diferencial deste estudo NÃO é
o algoritmo (família de gradient boosting / ensemble de árvores) mas
sim a metodologia (descoberta do cascade via SHAP, triangulação, auditoria
do label, recomendações operacionais quantificadas).

Refere ao Diferencial #1 da seção "Diferenciais metodológicos do trabalho".

Entradas:
  - dados/features/v3.parquet

Saídas:
  - modelos/random_forest_comparativo.joblib
  - modelos/optuna_study_rf.pkl
  - relatorio/tabelas/rf_metricas.csv
  - relatorio/tabelas/rf_hiperparametros.csv

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/16_random_forest_comparativo.py
"""
from pathlib import Path
import time
import warnings

import joblib
import numpy as np
import optuna
import pandas as pd
import polars as pl
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, recall_score

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)


ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "random_forest_comparativo.joblib"
ARQ_STUDY = ROOT / "modelos" / "optuna_study_rf.pkl"
ARQ_METRICAS = ROOT / "relatorio" / "tabelas" / "rf_metricas.csv"
ARQ_HIPER = ROOT / "relatorio" / "tabelas" / "rf_hiperparametros.csv"

SEED = 42
N_TRIALS = 50
TARGET = "target_4h"

FEATURES = [
    "hora_dia", "dia_semana", "mes", "valor_disponivel",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    "horas_desde_ultimo_critico",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
    # turno e estado_pre_evento serão one-hot
]
CAT_FEATURES = ["turno", "estado_pre_evento"]


def preparar_dados():
    print("Etapa 1/4 - Carregando v3.parquet...")
    df = pl.read_parquet(ARQ_V3)
    print(f"  Shape: {df.shape}")

    # Selecionar colunas
    cols = FEATURES + CAT_FEATURES + [TARGET, "split"]
    pdf = df.select(cols).to_pandas()

    # Bool -> int8
    pdf["valor_disponivel"] = pdf["valor_disponivel"].astype(np.int8)

    # Imputação NaN (mesma estratégia do 09_sobrevivencia/14_calibracao)
    for col in ["razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d"]:
        pdf[col] = pdf[col].fillna(1.0)
    train_mask = pdf["split"] == "train"
    pdf["taxa_DG_operador_30d"] = pdf["taxa_DG_operador_30d"].fillna(
        float(pdf.loc[train_mask, "taxa_DG_operador_30d"].median())
    )
    pdf["horas_desde_ultimo_critico"] = pdf["horas_desde_ultimo_critico"].fillna(
        float(pdf.loc[train_mask, "horas_desde_ultimo_critico"].max())
    )
    # Garantir sem NaN
    pdf[FEATURES] = pdf[FEATURES].fillna(0)

    # One-hot encoding das categóricas (drop_first=True igual ao 09)
    dummies = pd.get_dummies(pdf[CAT_FEATURES], prefix=CAT_FEATURES,
                              drop_first=True, dtype=np.int8)
    pdf = pd.concat([pdf.drop(columns=CAT_FEATURES), dummies], axis=1)

    features_finais = FEATURES + list(dummies.columns)
    print(f"  Features finais (incluindo one-hot): {len(features_finais)}")

    train = pdf[pdf["split"] == "train"]
    val = pdf[pdf["split"] == "val"]
    test = pdf[pdf["split"] == "test"]
    X_train = train[features_finais].values
    y_train = train[TARGET].values.astype(np.int8)
    X_val = val[features_finais].values
    y_val = val[TARGET].values.astype(np.int8)
    X_test = test[features_finais].values
    y_test = test[TARGET].values.astype(np.int8)

    print(f"  Train: {X_train.shape}, positivos = {y_train.sum():,}")
    print(f"  Val:   {X_val.shape}, positivos = {y_val.sum():,}")
    print(f"  Test:  {X_test.shape}, positivos = {y_test.sum():,}")
    return X_train, y_train, X_val, y_val, X_test, y_test, features_finais


def gerar_folds(n_train: int):
    """4 folds expandidos walk-forward (mesma estrutura do 08b_lightgbm_v2)."""
    # Aproximação simples: dividir o train em 5 partes contíguas, expandir.
    # Não recria exatamente a estrutura do 08b porque não temos os timestamps
    # aqui (usamos só X, y). Mas a estrutura "expandida" é equivalente.
    # Para uso justo, usamos sklearn TimeSeriesSplit que faz exatamente isso.
    from sklearn.model_selection import TimeSeriesSplit
    return TimeSeriesSplit(n_splits=4)


def objective_rf(trial, X_train, y_train, tscv):
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "max_depth": trial.suggest_int("max_depth", 5, 30),
        "min_samples_split": trial.suggest_int("min_samples_split", 2, 50),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 20),
        "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5]),
        "class_weight": trial.suggest_categorical(
            "class_weight", [None, "balanced", "balanced_subsample"]
        ),
        "random_state": SEED,
        "n_jobs": -1,
    }

    auc_prs = []
    for fold_train_idx, fold_val_idx in tscv.split(X_train):
        rf = RandomForestClassifier(**params)
        rf.fit(X_train[fold_train_idx], y_train[fold_train_idx])
        p = rf.predict_proba(X_train[fold_val_idx])[:, 1]
        auc_prs.append(average_precision_score(y_train[fold_val_idx], p))
    return float(np.mean(auc_prs))


def main():
    t_start = time.time()
    print("=" * 70)
    print("16_random_forest_comparativo.py - RF tunado vs LightGBM v3")
    print("=" * 70)

    X_train, y_train, X_val, y_val, X_test, y_test, features = preparar_dados()

    print()
    print(f"Etapa 2/4 - Optuna RF ({N_TRIALS} trials, TimeSeriesSplit 4 folds)...")
    tscv = gerar_folds(len(X_train))
    sampler = optuna.samplers.TPESampler(seed=SEED)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(
        lambda t: objective_rf(t, X_train, y_train, tscv),
        n_trials=N_TRIALS,
        show_progress_bar=False,
    )
    elapsed_opt = time.time() - t_start
    print(f"  Concluído em {elapsed_opt:.1f}s ({elapsed_opt/60:.1f} min)")
    print(f"  Best AUC-PR (CV): {study.best_value:.4f}")
    print(f"  Best trial: #{study.best_trial.number}")
    print(f"  Best params:")
    for k, v in study.best_params.items():
        print(f"    {k:<22s}: {v}")

    joblib.dump(study, ARQ_STUDY, compress=3)

    print()
    print("Etapa 3/4 - Treinando RF final com best params...")
    t0 = time.time()
    best = {**study.best_params, "random_state": SEED, "n_jobs": -1}
    rf_final = RandomForestClassifier(**best)
    rf_final.fit(X_train, y_train)
    print(f"  Tempo treino final: {time.time() - t0:.1f}s")

    # Métricas
    p_train = rf_final.predict_proba(X_train)[:, 1]
    p_val = rf_final.predict_proba(X_val)[:, 1]
    p_test = rf_final.predict_proba(X_test)[:, 1]

    metricas = []
    for nome, y, p in [("train", y_train, p_train),
                       ("val", y_val, p_val),
                       ("test", y_test, p_test)]:
        auc_pr = average_precision_score(y, p)
        recall_05 = recall_score(y, (p >= 0.5).astype(np.int8))
        metricas.append({
            "split": nome,
            "n_eventos": len(y),
            "n_positivos": int(y.sum()),
            "auc_pr": round(float(auc_pr), 4),
            "recall_thr_05": round(float(recall_05), 4),
        })
        print(f"  {nome:<6s}: AUC-PR = {auc_pr:.4f}  Recall@0.5 = {recall_05:.4f}")

    pl.from_dicts(metricas).write_csv(ARQ_METRICAS)
    pl.from_dicts([{"hiperparametro": k, "best_value": str(v)}
                    for k, v in study.best_params.items()]).write_csv(ARQ_HIPER)

    print()
    print("Etapa 4/4 - Salvando modelo final...")
    joblib.dump({"modelo": rf_final, "features": features,
                 "best_params": study.best_params,
                 "best_cv_auc_pr": study.best_value},
                 ARQ_MODELO, compress=3)
    mb = ARQ_MODELO.stat().st_size / 1024 / 1024
    print(f"  Salvo: {ARQ_MODELO.relative_to(ROOT.parent)} ({mb:.1f} MB)")

    print()
    print("=" * 70)
    print("COMPARAÇÃO FINAL — RF (tunado) vs LightGBM v3 (canônico)")
    print("=" * 70)
    print(f"{'Métrica':<20s} | {'RF tunado':>10s} | {'v3 canônico':>12s} | {'Δ':>8s}")
    print(f"{'-'*20} | {'-'*10} | {'-'*12} | {'-'*8}")
    v3_test_auc_pr = 0.8556
    v3_test_recall = 0.7527
    rf_test_auc_pr = metricas[2]["auc_pr"]
    rf_test_recall = metricas[2]["recall_thr_05"]
    print(f"{'AUC-PR test':<20s} | {rf_test_auc_pr:>10.4f} | {v3_test_auc_pr:>12.4f} | "
          f"{rf_test_auc_pr - v3_test_auc_pr:>+8.4f}")
    print(f"{'Recall@0.5 test':<20s} | {rf_test_recall:>10.4f} | {v3_test_recall:>12.4f} | "
          f"{rf_test_recall - v3_test_recall:>+8.4f}")

    elapsed_total = time.time() - t_start
    print()
    print(f"Tempo total: {elapsed_total:.1f}s ({elapsed_total/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
