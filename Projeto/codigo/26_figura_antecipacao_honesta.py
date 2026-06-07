# -*- coding: utf-8 -*-
"""
26_figura_antecipacao_honesta.py - Figura honesta: antecipacao inclusiva (com cascata) vs estrita (pura).

Produz UMA figura que mostra as duas linhas de AUC-ROC lado a lado:
  - INCLUSIVO: alvo "existe DG em [t+L, t+4h]" (permite DG iminente antes de L) -> inflado por cascata.
  - ESTRITO:   alvo "proximo DG em [L, 4h], nada iminente" -> antecipacao pura.

O vao entre as duas linhas E' a contaminacao de cascata. O estrito e' a manchete honesta.

Entradas: v3.parquet + lightgbm_v2_no_cascade.txt
Saidas:
  - Projeto/relatorio/figuras/figExK_antecipacao_honesta.png
  - Projeto/relatorio/tabelas/antecipacao_inclusivo_vs_estrito.csv

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/26_figura_antecipacao_honesta.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.metrics import roc_auc_score, average_precision_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExK_antecipacao_honesta.png"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "antecipacao_inclusivo_vs_estrito.csv"

N_TEST = 71_089
LEADS = [0, 30, 60, 90, 120]

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


def main():
    print("=" * 80)
    print("26_figura_antecipacao_honesta.py - inclusivo (cascata) vs estrito (puro)")
    print("=" * 80)

    df = pl.read_parquet(ARQ_V3)
    test = df.filter(pl.col("split") == "test")
    assert test.height == N_TEST
    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    X = test.select(FEATURES).to_pandas()
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    p_all = booster.predict(X)

    base = test.select(["TAG", "Data_Evento"]).with_columns(pl.Series("p", p_all)).sort("Data_Evento")
    dgs = (test.filter(pl.col("Is_Dont_Go") == 1)
           .select(["TAG", pl.col("Data_Evento").alias("dg_time")]).sort("dg_time"))

    # lead = tempo (h) ate o proximo DG (>= t); NaN se nao ha
    jl = base.join_asof(dgs, left_on="Data_Evento", right_on="dg_time", by="TAG", strategy="forward")
    lead = jl.with_columns(
        ((pl.col("dg_time") - pl.col("Data_Evento")).dt.total_seconds() / 3600.0).alias("lead_h")
    )["lead_h"].to_numpy()
    lead_f = np.where(np.isnan(lead), np.inf, lead)
    p = base["p"].to_numpy()

    rows, incl_auc, estr_auc, estr_lift = [], [], [], []
    print(f"\n{'L(min)':>6} | {'incl AUC-ROC':>12} | {'estrito AUC-ROC':>15} | {'estrito lift':>12} | {'gap (cascata)':>13}")
    print("-" * 80)
    for L in LEADS:
        Lh = L / 60.0
        # inclusivo: existe DG em [t+L, t+4h]
        ev = base.with_columns((pl.col("Data_Evento") + pl.duration(minutes=L)).alias("key")).sort("key")
        ji = ev.join_asof(dgs, left_on="key", right_on="dg_time", by="TAG", strategy="forward")
        ji = ji.with_columns(
            (pl.col("dg_time").is_not_null()
             & (pl.col("dg_time") <= pl.col("Data_Evento") + pl.duration(hours=4))).cast(pl.Int8).alias("t")
        )
        t_incl = ji["t"].to_numpy()
        p_incl = ji["p"].to_numpy()
        auc_incl = roc_auc_score(t_incl, p_incl)

        # estrito: proximo DG em [L, 4h]; exclui iminente (lead<L)
        pos = (lead_f >= Lh) & (lead_f <= 4.0)
        neg = (lead_f > 4.0)
        keep = pos | neg
        auc_estr = roc_auc_score(pos[keep].astype(np.int8), p[keep])
        prev_estr = pos[keep].mean()
        ap_estr = average_precision_score(pos[keep].astype(np.int8), p[keep])
        lift_estr = ap_estr / prev_estr if prev_estr > 0 else None

        incl_auc.append(auc_incl); estr_auc.append(auc_estr); estr_lift.append(lift_estr)
        rows.append({"lead_min": L, "auc_roc_inclusivo": round(auc_incl, 4),
                     "auc_roc_estrito": round(auc_estr, 4),
                     "auc_pr_estrito": round(ap_estr, 4),
                     "prev_estrito": round(prev_estr, 4),
                     "lift_estrito": round(lift_estr, 2) if lift_estr else None,
                     "gap_cascata": round(auc_incl - auc_estr, 4)})
        print(f"{L:>6} | {auc_incl:>12.4f} | {auc_estr:>15.4f} | "
              f"{lift_estr:>12.2f} | {auc_incl-auc_estr:>13.4f}")
    print("-" * 80)
    pl.from_dicts(rows).write_csv(ARQ_TAB)
    print(f"Salvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # --- figura ---
    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    ax.fill_between(LEADS, estr_auc, incl_auc, color="#ffcc80", alpha=0.45,
                    label="vão = acerto por DG mais próximo (não antecipação)")
    ax.plot(LEADS, incl_auc, "o--", color="#9e9e9e", linewidth=2.0, markersize=8,
            label="INCLUSIVO (permite DG mais próximo na janela) — inflado")
    ax.plot(LEADS, estr_auc, "o-", color="#1565c0", linewidth=3.0, markersize=10,
            label="ESTRITO (antecipação pura, nada iminente) — honesto")
    for x, y in zip(LEADS, incl_auc):
        ax.text(x, y + 0.012, f"{y:.3f}", ha="center", fontsize=9, color="#757575")
    for x, y in zip(LEADS, estr_auc):
        ax.text(x, y - 0.03, f"{y:.3f}", ha="center", fontsize=9.5, color="#1565c0", fontweight="bold")
    ax.axhline(0.5, color="#c62828", linestyle=":", linewidth=1.3, alpha=0.7)
    ax.text(118, 0.515, "0,5 = aleatório", fontsize=9, color="#c62828", ha="right")
    ax.axvline(90, color="#2e7d32", linestyle=":", linewidth=1.4, alpha=0.7)
    ax.text(91, 0.56, "90 min\n(mobilização)", fontsize=9, color="#2e7d32")
    ax.set_xlabel("Tempo mínimo de antecedência exigido, L (minutos)", fontsize=12)
    ax.set_ylabel("AUC-ROC no test (jun/2025)", fontsize=12)
    ax.set_title(
        "Figura Extra K — Antecipação real do v3: pura vs inflada por DG mais próximo\n"
        "A linha azul (estrito) é a capacidade honesta; o vão até a cinza é acerto por um DG mais próximo na janela.",
        fontsize=12, fontweight="bold")
    ax.set_xticks(LEADS)
    ax.set_ylim(0.45, 1.0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower center", fontsize=10)
    plt.tight_layout()
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")

    print()
    print("=" * 80)
    e90 = next(r for r in rows if r["lead_min"] == 90)
    print(f"  Manchete honesta (L=90min, estrito): AUC-ROC={e90['auc_roc_estrito']:.4f}, "
          f"lift={e90['lift_estrito']:.2f}x. Inflado era {e90['auc_roc_inclusivo']:.4f} "
          f"(gap de cascata = {e90['gap_cascata']:.4f}).")
    print("=" * 80)


if __name__ == "__main__":
    main()
