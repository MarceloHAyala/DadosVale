# -*- coding: utf-8 -*-
"""
13_curvas_comparativas.py - Fig 9: Curvas ROC + Precision-Recall comparativas.

Compara visualmente os 3 modelos finais no test set (jun/2025):
  - Baseline heurístico (count_critico_4h >= threshold)
  - LightGBM v3 (modelo canônico, alerta operacional 4h)
  - Weibull AFT (sobrevivência, P(T <= 4h))

Material para CM 5.1 do relatório (Resultados).

Entradas:
  - dados/features/v3.parquet (test set + target_4h + count_critico_4h)
  - modelos/lightgbm_v2_no_cascade.txt (v3 canonico)
  - modelos/sobrevivencia.joblib (Weibull AFT)

Saidas:
  - relatorio/figuras/fig09_curvas_comparativas.png (2 paineis: ROC + PR)
  - relatorio/tabelas/comparacao_modelos_test.csv (3 modelos x AUC-ROC/AUC-PR)

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/13_curvas_comparativas.py
"""
from pathlib import Path
import warnings

import joblib
import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

warnings.filterwarnings("ignore")


ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_LGB = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"
ARQ_SURV = ROOT / "modelos" / "sobrevivencia.joblib"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "fig09_curvas_comparativas.png"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "comparacao_modelos_test.csv"

FEATURES_V3 = [
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


def predizer_v3(df_test: pl.DataFrame) -> np.ndarray:
    """Predict probabilities from LightGBM v3 on test."""
    booster = lgb.Booster(model_file=str(ARQ_LGB))
    X = df_test.select(FEATURES_V3).to_pandas()
    for c in ["turno", "estado_pre_evento"]:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return booster.predict(X)


def predizer_weibull(df_test: pl.DataFrame) -> np.ndarray:
    """Predict P(T <= 4h) from Weibull AFT on test."""
    art = joblib.load(ARQ_SURV)
    modelo, scaler, features, imputacao = (
        art["modelo"], art["scaler"], art["features"], art["imputacao"]
    )
    pdf = df_test.to_pandas()
    pdf["valor_disponivel"] = pdf["valor_disponivel"].astype(np.int8)
    for col, val in imputacao.items():
        pdf[col] = pdf[col].fillna(val)
    pdf = pdf.fillna(0)
    dummies = pd.get_dummies(pdf[["turno", "estado_pre_evento"]],
                              prefix=["turno", "estado_pre_evento"],
                              drop_first=True, dtype=np.int8)
    pdf = pd.concat([pdf.drop(columns=["turno", "estado_pre_evento"]), dummies], axis=1)
    for col in features:
        if col not in pdf.columns:
            pdf[col] = 0
    # Continuous features (mesmas detectadas no 09) sao escaladas
    continuas = [c for c in features
                 if not set(pdf[c].dropna().unique()).issubset({0, 1})]
    pdf_scaled = pdf[features].copy()
    pdf_scaled[continuas] = scaler.transform(pdf[continuas])
    surv_4h = modelo.predict_survival_function(pdf_scaled, times=[4.0]).iloc[0].values
    return 1.0 - surv_4h


def main() -> None:
    print("=" * 70)
    print("13_curvas_comparativas.py - Fig 9: ROC + PR comparativas (test)")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    test = df.filter(pl.col("split") == "test")
    y = test["target_4h"].to_numpy()
    n_test = len(y)
    n_pos = int(y.sum())
    prev = n_pos / n_test
    print(f"  Test set: n={n_test:,}  positivos (target_4h)={n_pos:,}  prevalencia={prev*100:.2f}%")

    print()
    print("  Coletando predicoes dos 3 modelos...")
    # 1. Baseline: count_critico_4h como score raw
    score_baseline = test["count_critico_4h"].to_numpy().astype(float)
    print(f"    [1/3] Baseline (count_critico_4h): OK")

    # 2. LightGBM v3
    score_v3 = predizer_v3(test)
    print(f"    [2/3] LightGBM v3 (canonico): OK")

    # 3. Weibull AFT — P(T <= 4h)
    score_weibull = predizer_weibull(test)
    print(f"    [3/3] Weibull AFT: OK")

    # Metricas agregadas
    print()
    print("  Metricas agregadas no test:")
    linhas = []
    modelos = [
        ("Baseline (count_critico_4h)", score_baseline, "C0"),
        ("LightGBM v3 (canonico)", score_v3, "C3"),
        ("Weibull AFT", score_weibull, "C2"),
    ]
    print(f"  {'modelo':<32s} | {'AUC-ROC':>8s} | {'AUC-PR':>8s}")
    print(f"  {'-'*32} | {'-'*8} | {'-'*8}")
    for nome, score, _ in modelos:
        auc_roc = roc_auc_score(y, score)
        auc_pr = average_precision_score(y, score)
        linhas.append({
            "modelo": nome,
            "auc_roc": round(float(auc_roc), 4),
            "auc_pr": round(float(auc_pr), 4),
            "n_test": n_test,
            "n_positivos": n_pos,
            "prevalencia": round(prev, 4),
        })
        print(f"  {nome:<32s} | {auc_roc:>8.4f} | {auc_pr:>8.4f}")

    pl.from_dicts(linhas).write_csv(ARQ_TAB)
    print()
    print(f"  Salvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # Figura: 2 paineis
    print()
    print("  Gerando Fig 9 (2 paineis, figsize=(16,7), dpi=150)...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Painel A — ROC
    ax = axes[0]
    for nome, score, cor in modelos:
        fpr, tpr, _ = roc_curve(y, score)
        auc = roc_auc_score(y, score)
        ax.plot(fpr, tpr, color=cor, linewidth=2.5,
                label=f"{nome}  (AUC = {auc:.4f})")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1.2, alpha=0.5, label="Aleatório (AUC=0,5)")
    ax.set_xlabel("Taxa de Falsos Positivos (FPR)", fontsize=13)
    ax.set_ylabel("Taxa de Verdadeiros Positivos (Recall)", fontsize=13)
    ax.set_title("(a) Curva ROC", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=11, framealpha=0.95)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=11)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)

    # Painel B — PR
    ax = axes[1]
    for nome, score, cor in modelos:
        p, r, _ = precision_recall_curve(y, score)
        ap = average_precision_score(y, score)
        ax.plot(r, p, color=cor, linewidth=2.5,
                label=f"{nome}  (AUC-PR = {ap:.4f})")
    ax.axhline(prev, color="gray", linestyle="--", linewidth=1.2, alpha=0.6,
               label=f"Aleatório (Prevalência = {prev:.3f})")
    ax.set_xlabel("Recall", fontsize=13)
    ax.set_ylabel("Precisão", fontsize=13)
    ax.set_title("(b) Curva Precisão-Recall", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=11, framealpha=0.95)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=11)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)

    fig.suptitle(
        "Figura 9 — Comparativo dos 3 modelos no test set (jun/2025)\n"
        f"n = {n_test:,} eventos | DGs reais (target_4h=1) = {n_pos:,} ({prev*100:.2f}%)",
        fontsize=15, fontweight="bold", y=1.00,
    )
    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
