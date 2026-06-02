# -*- coding: utf-8 -*-
"""
19_drift_semanal_junho.py - Drift de performance ao longo de junho/2025 (W7).

Como o test set é apenas junho/2025, "drift mensal" no test não se aplica
literalmente. Adaptamos para **drift semanal** dentro de junho:

  - Semana 1: 01-07/jun
  - Semana 2: 08-14/jun
  - Semana 3: 15-21/jun
  - Semana 4: 22-30/jun

Para cada semana, calcula:
  - AUC-PR do v3 (canônico)
  - Precision/Recall no threshold operacional (0,30)
  - n eventos, n DGs, prevalência

Material para CM 5.2 (estabilidade dentro do regime de teste) e CM 6.2
(refinamento das limitações L4 + L10 já documentadas — agora com granularidade
intra-mês).

Entradas:
  - dados/features/v3.parquet
  - modelos/lightgbm_v2_no_cascade.txt

Saídas:
  - relatorio/tabelas/drift_semanal_junho.csv
  - relatorio/figuras/figExI_drift_semanal_junho.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/19_drift_semanal_junho.py
"""
from pathlib import Path

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score, precision_recall_fscore_support

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"

ARQ_TAB = ROOT / "relatorio" / "tabelas" / "drift_semanal_junho.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExI_drift_semanal_junho.png"

THRESHOLD_OP = 0.30

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
    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    X = df_test.select(FEATURES_V3).to_pandas()
    for c in ["turno", "estado_pre_evento"]:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return booster.predict(X)


def main():
    print("=" * 70)
    print("19_drift_semanal_junho.py - Estabilidade do v3 dentro do test (jun/2025)")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    test = df.filter(pl.col("split") == "test")
    print(f"\nTest set: n={test.height:,}")

    # Predições
    print("Gerando predições do v3...")
    p = predizer_v3(test)
    test = test.with_columns(pl.Series("p_v3", p))

    # Atribuir semana ao test (1-4)
    test = test.with_columns(
        pl.col("Data_Evento").dt.day().alias("dia"),
    )
    test = test.with_columns(
        pl.when(pl.col("dia") <= 7).then(pl.lit("S1 (01-07)"))
        .when(pl.col("dia") <= 14).then(pl.lit("S2 (08-14)"))
        .when(pl.col("dia") <= 21).then(pl.lit("S3 (15-21)"))
        .otherwise(pl.lit("S4 (22-30)"))
        .alias("semana_junho")
    )

    # Análise por semana
    print("\nAnálise por semana de junho/2025 (threshold operacional = 0,30):")
    linhas = []
    for semana in ["S1 (01-07)", "S2 (08-14)", "S3 (15-21)", "S4 (22-30)"]:
        sub = test.filter(pl.col("semana_junho") == semana)
        y = sub["target_4h"].to_numpy().astype(np.int8)
        p_sub = sub["p_v3"].to_numpy()
        n = len(y)
        n_dg = int(y.sum())
        prev = n_dg / n if n > 0 else 0
        auc_pr = float(average_precision_score(y, p_sub)) if n_dg > 0 else None
        y_pred = (p_sub >= THRESHOLD_OP).astype(np.int8)
        if n_dg > 0:
            precision, recall, _, _ = precision_recall_fscore_support(
                y, y_pred, average="binary", zero_division=0
            )
        else:
            precision, recall = 0.0, 0.0

        linha = {
            "semana": semana,
            "n_eventos": n,
            "n_DG_real": n_dg,
            "prevalencia_pct": round(100 * prev, 2),
            "auc_pr": round(auc_pr, 4) if auc_pr is not None else None,
            "precision_thr_op": round(float(precision), 4),
            "recall_thr_op": round(float(recall), 4),
            "n_alertas_thr_op": int(y_pred.sum()),
        }
        linhas.append(linha)
        auc_str = f"{auc_pr:.4f}" if auc_pr is not None else "N/A"
        print(f"  {semana}: n={n:>6,} | DG={n_dg:>5,} ({prev*100:5.2f}%) | "
              f"AUC-PR={auc_str} | "
              f"P={precision:.3f} R={recall:.3f} | "
              f"alertas={int(y_pred.sum()):,}")

    df_drift = pl.from_dicts(linhas)
    df_drift.write_csv(ARQ_TAB)
    print(f"\nSalvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # Figura — 2 painéis
    print("\nGerando figura (2 painéis: AUC-PR e prevalência por semana)...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    semanas = [l["semana"] for l in linhas]
    aucs = [l["auc_pr"] for l in linhas]
    precisions = [l["precision_thr_op"] for l in linhas]
    recalls = [l["recall_thr_op"] for l in linhas]
    prevs = [l["prevalencia_pct"] for l in linhas]
    n_dgs = [l["n_DG_real"] for l in linhas]

    # Painel A — AUC-PR + Precision + Recall por semana
    x = list(range(4))
    ax1.plot(x, aucs, "o-", color="#1976d2", linewidth=2.5, markersize=10,
             label="AUC-PR")
    ax1.plot(x, precisions, "s-", color="#c62828", linewidth=2, markersize=8,
             label=f"Precision @ thr={THRESHOLD_OP}")
    ax1.plot(x, recalls, "^-", color="#2e7d32", linewidth=2, markersize=8,
             label=f"Recall @ thr={THRESHOLD_OP}")

    # Anotar valores
    for i, v in enumerate(aucs):
        ax1.text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=10,
                 fontweight="bold", color="#1976d2")

    ax1.set_xticks(x)
    ax1.set_xticklabels(semanas, fontsize=10)
    ax1.set_ylabel("Métrica", fontsize=12)
    ax1.set_title("(a) Performance do v3 ao longo de junho/2025\n"
                  f"(threshold operacional = {THRESHOLD_OP})",
                  fontsize=12, fontweight="bold")
    ax1.legend(loc="lower left", fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 1.05)
    ax1.tick_params(axis="both", labelsize=10)

    # Painel B — Prevalência de DG + volume por semana
    ax2_twin = ax2.twinx()
    bars = ax2.bar(x, prevs, color="#ff8f00", alpha=0.7, edgecolor="white",
                    label="Prevalência DG (%)", width=0.5)
    line = ax2_twin.plot(x, n_dgs, "ko-", linewidth=2, markersize=8,
                         label="n DGs reais")

    for i, (p, n) in enumerate(zip(prevs, n_dgs)):
        ax2.text(i, p + 0.5, f"{p:.1f}%", ha="center", fontsize=10,
                 fontweight="bold", color="#ff8f00")
        ax2_twin.text(i, n + 100, f"{n:,}", ha="center", fontsize=10,
                       fontweight="bold")

    ax2.set_xticks(x)
    ax2.set_xticklabels(semanas, fontsize=10)
    ax2.set_ylabel("Prevalência DG (%)", fontsize=12, color="#ff8f00")
    ax2_twin.set_ylabel("n DGs reais (absoluto)", fontsize=12)
    ax2.set_title("(b) Volume e prevalência de DG por semana\n"
                  "Mostra concentração na S4 (22-30/jun, pico do CA65926)",
                  fontsize=12, fontweight="bold")
    ax2.tick_params(axis="y", labelcolor="#ff8f00", labelsize=10)
    ax2_twin.tick_params(labelsize=10)
    ax2.grid(True, alpha=0.3, axis="y")

    # Legenda combinada
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=10)

    fig.suptitle(
        "Figura Extra I — Drift semanal do v3 em junho/2025 (test set)\n"
        "Performance e prevalência variam ao longo do mês com o CA65926 dominando S4",
        fontsize=13, fontweight="bold", y=1.00,
    )

    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")

    print()
    print("=" * 70)
    print("SÍNTESE — drift intra-mês no test")
    print("=" * 70)
    auc_max = max(a for a in aucs if a is not None)
    auc_min = min(a for a in aucs if a is not None)
    if auc_min < 0.7 or (auc_max - auc_min) > 0.15:
        print(f"  AUC-PR varia entre {auc_min:.4f} (mínimo) e {auc_max:.4f} (máximo)")
        print(f"  Amplitude = {auc_max - auc_min:.4f} pp — variação significativa intra-mês")
    else:
        print(f"  AUC-PR estável: {auc_min:.4f} - {auc_max:.4f} (amplitude {auc_max - auc_min:.4f})")
    print()


if __name__ == "__main__":
    main()
