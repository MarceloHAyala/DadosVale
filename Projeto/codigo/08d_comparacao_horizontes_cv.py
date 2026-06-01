# -*- coding: utf-8 -*-
"""
08d_comparacao_horizontes_cv.py - Profundidade 1 rigorosa (T2 vs T4 vs T8 via CV).

Treina 3 modelos v3 com hiperparâmetros IDÊNTICOS (best Optuna do v3),
mudando apenas o target:
  - T2:  target_2h
  - T4:  target_4h (canônico)
  - T8:  target_8h

Cada modelo é avaliado via TimeSeriesSplit CV de 4 folds expandidos (mesma
estrutura da Mitigação 1), reportando AUC-PR média ± desvio padrão.

Resposta empírica para:
  - Cenário 1: T2 ≈ T4 indistinguíveis → mantém T4 canônico
  - Cenário 2: T2 > T4 com significância (> 2σ) → Insight CM 6.1
  - Cenário 3: T4 > T2 com significância → confirma escolha do CM 1.2

Entradas:
  - dados/features/v3.parquet

Saídas:
  - relatorio/tabelas/comparacao_horizontes_cv.csv (3 horizontes × média + std)

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/08d_comparacao_horizontes_cv.py
"""
from pathlib import Path
import time
import warnings

import lightgbm as lgb
import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")
warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "comparacao_horizontes_cv.csv"

# Best hyperparams do v3 (lightgbm_v2_no_cascade — trial #41)
BEST_PARAMS = {
    "objective": "binary",
    "metric": "average_precision",
    "n_estimators": 301,
    "learning_rate": 0.011750409866019435,
    "num_leaves": 69,
    "min_child_samples": 50,
    "scale_pos_weight": 2.400711223647736,
    "lambda_l1": 0.1966545804632781,
    "lambda_l2": 1.1830097418431307,
    "deterministic": True,
    "force_col_wise": True,
    "random_state": 42,
    "verbose": -1,
}

FEATURES = [
    "hora_dia", "dia_semana", "turno", "mes", "valor_disponivel",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    "horas_desde_ultimo_critico",
    "estado_pre_evento",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
]
CAT_FEATURES = ["turno", "estado_pre_evento"]


def preparar_X_y(df, target_col):
    pdf = df.select(FEATURES + [target_col]).to_pandas()
    pdf["valor_disponivel"] = pdf["valor_disponivel"].astype(np.int8)
    for c in CAT_FEATURES:
        pdf[c] = pdf[c].astype("category")
    X = pdf[FEATURES]
    y = pdf[target_col].astype(np.int8).values
    return X, y


def main():
    t_start = time.time()
    print("=" * 70)
    print("08d_comparacao_horizontes_cv.py - T2 vs T4 vs T8 via TimeSeriesSplit CV")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    train = df.filter(pl.col("split") == "train")
    print(f"\nTrain: n={train.height:,}")
    print(f"Hyperparams fixos: best Optuna do v3 (n_estimators=301, scale_pos_weight=2.4)")
    print(f"TimeSeriesSplit CV de 4 folds expandidos\n")

    horizontes = [
        ("T2", "target_2h"),
        ("T4", "target_4h"),
        ("T8", "target_8h"),
    ]

    resultados = []
    for nome, target_col in horizontes:
        print(f"=== Horizonte {nome} ({target_col}) ===")
        X, y = preparar_X_y(train, target_col)
        print(f"  Positivos: {y.sum():,} ({100*y.sum()/len(y):.2f}%)")

        tscv = TimeSeriesSplit(n_splits=4)
        aucs = []
        for fold_idx, (tr_idx, va_idx) in enumerate(tscv.split(X), start=1):
            t0 = time.time()
            booster = lgb.LGBMClassifier(**BEST_PARAMS)
            booster.fit(
                X.iloc[tr_idx], y[tr_idx],
                eval_set=[(X.iloc[va_idx], y[va_idx])],
                categorical_feature=CAT_FEATURES,
            )
            p = booster.predict_proba(X.iloc[va_idx])[:, 1]
            auc = average_precision_score(y[va_idx], p)
            aucs.append(auc)
            print(f"  fold {fold_idx}: AUC-PR = {auc:.4f}  ({time.time()-t0:.1f}s)")

        media = float(np.mean(aucs))
        std = float(np.std(aucs))
        n_pos_total = int(y.sum())
        resultados.append({
            "horizonte": nome,
            "target_col": target_col,
            "n_positivos_train": n_pos_total,
            "prevalencia_train": round(100*n_pos_total/len(y), 4),
            "auc_pr_fold1": round(aucs[0], 4),
            "auc_pr_fold2": round(aucs[1], 4),
            "auc_pr_fold3": round(aucs[2], 4),
            "auc_pr_fold4": round(aucs[3], 4),
            "auc_pr_media": round(media, 4),
            "auc_pr_std": round(std, 4),
        })
        print(f"  → Média ± std: {media:.4f} ± {std:.4f}\n")

    df_res = pl.from_dicts(resultados)
    df_res.write_csv(ARQ_TAB)
    print(f"Salvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # Síntese comparativa
    print("\n" + "=" * 70)
    print("SÍNTESE COMPARATIVA")
    print("=" * 70)
    print(f"\n{'Horiz':>6s} | {'Prevalência':>12s} | {'AUC-PR média':>14s} | {'± std':>10s}")
    print(f"{'-'*6} | {'-'*12} | {'-'*14} | {'-'*10}")
    for r in resultados:
        print(f"{r['horizonte']:>6s} | {r['prevalencia_train']:>11.2f}% | "
              f"{r['auc_pr_media']:>14.4f} | ± {r['auc_pr_std']:>7.4f}")

    # Comparação T2 vs T4 (com regra de >2σ)
    print()
    t2, t4, t8 = resultados[0], resultados[1], resultados[2]
    delta_t2_t4 = t2["auc_pr_media"] - t4["auc_pr_media"]
    sigma_combined = np.sqrt(t2["auc_pr_std"]**2 + t4["auc_pr_std"]**2)
    print(f"Comparação T2 vs T4:")
    print(f"  Δ = {delta_t2_t4:+.4f}  σ_combined = {sigma_combined:.4f}  "
          f"(Δ / σ = {abs(delta_t2_t4)/sigma_combined:.2f})")
    if abs(delta_t2_t4) > 2 * sigma_combined:
        if delta_t2_t4 > 0:
            print("  → Cenário 2: T2 supera T4 com significância > 2σ. Insight CM 6.1.")
        else:
            print("  → Cenário 3: T4 supera T2 com significância > 2σ. Confirma CM 1.2.")
    else:
        print("  → Cenário 1: T2 ≈ T4 indistinguíveis. Mantém T4 canônico.")

    elapsed = time.time() - t_start
    print(f"\nTempo total: {elapsed:.1f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
