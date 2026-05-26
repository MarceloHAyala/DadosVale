"""
15_ablation_grupos.py - Ablation por grupo de features no LightGBM v3.

Retreina v3 com hiperparametros FIXOS (best do Optuna, sem re-tuning)
removendo cada GRUPO de features para medir queda de AUC-PR e Recall no test.
Resposta direta para "qual familia carrega o modelo".

GRUPOS (alinhados com PLANEJAMENTO W6):
  G1 — Temporais:        hora_dia, dia_semana, turno, mes
  G2 — Rolling counts:   count_{critico,nao_critico,total}_{1h,2h,4h,8h,24h} (15)
  G3 — Recencia:         horas_desde_ultimo_critico (1, v3 nao tem horas_DG)
  G4 — Operador:         taxa_DG_operador_30d, n_bypasses_operador_7d, operador_freq
  G5 — Regra de negocio: qtd_alarmes_nivel_muito_alto_360min
  G6 — Categoricas codif: tag_freq, frota_793D_2S/3S/4S/5S, tipo_caminhao,
                          estado_pre_evento, valor_disponivel
  G7 — Regimal (Familia 4): razao_alarme_7d_vs_30d_anterior,
                            razao_severidade_14d_vs_60d

OBS: nao re-roda Optuna em cada ablation (usaria 6 x 25min = 2.5h apenas para tuning).
Usa os best hiperparametros do v3 fixos. Isso e a abordagem padrao de ablation
estudies — ceteris paribus, so muda o feature set.

Entradas:
  - dados/features/v3.parquet
  - relatorio/tabelas/lightgbm_v2_no_cascade_hiperparametros.csv (best params v3)

Saidas:
  - relatorio/tabelas/ablation_grupos.csv (7 grupos + linha "todas as features")
  - relatorio/figuras/figExE_ablation_grupos.png (bar chart de delta_AUC-PR)

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/15_ablation_grupos.py
"""
from pathlib import Path
import time
import warnings

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score, recall_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")
warnings.filterwarnings("ignore", category=FutureWarning)


ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "ablation_grupos.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExE_ablation_grupos.png"


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
CAT_FEATURES = ["turno", "estado_pre_evento"]
TARGET = "target_4h"

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

GRUPOS = {
    "G1_temporais": ["hora_dia", "dia_semana", "turno", "mes"],
    "G2_rolling": [
        "count_critico_1h", "count_critico_2h", "count_critico_4h",
        "count_critico_8h", "count_critico_24h",
        "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
        "count_nao_critico_8h", "count_nao_critico_24h",
        "count_total_1h", "count_total_2h", "count_total_4h",
        "count_total_8h", "count_total_24h",
    ],
    "G3_recencia": ["horas_desde_ultimo_critico"],
    "G4_operador": ["taxa_DG_operador_30d", "n_bypasses_operador_7d", "operador_freq"],
    "G5_regra_negocio": ["qtd_alarmes_nivel_muito_alto_360min"],
    "G6_categoricas": ["tag_freq", "frota_793D_2S", "frota_793D_3S",
                        "frota_793D_4S", "frota_793D_5S", "tipo_caminhao",
                        "estado_pre_evento", "valor_disponivel"],
    "G7_regimal": ["razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d"],
}


def preparar_X(df: pl.DataFrame, features: list[str]):
    import pandas as pd
    pdf = df.select(features + [TARGET]).to_pandas()
    y = pdf[TARGET].to_numpy().astype(np.int8)
    X = pdf[features].copy()
    for c in features:
        if c in CAT_FEATURES:
            X[c] = X[c].astype("category")
    if "valor_disponivel" in features and X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return X, y


def treinar_e_avaliar(df: pl.DataFrame, features: list[str], nome: str) -> dict:
    train = df.filter(pl.col("split") == "train")
    val = df.filter(pl.col("split") == "val")
    test = df.filter(pl.col("split") == "test")

    X_tr, y_tr = preparar_X(train, features)
    X_val, y_val = preparar_X(val, features)
    X_te, y_te = preparar_X(test, features)

    t0 = time.time()
    booster = lgb.LGBMClassifier(**BEST_PARAMS)
    booster.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                categorical_feature=[f for f in features if f in CAT_FEATURES])
    elapsed = time.time() - t0

    p_val = booster.predict_proba(X_val)[:, 1]
    p_test = booster.predict_proba(X_te)[:, 1]

    auc_pr_val = float(average_precision_score(y_val, p_val))
    auc_pr_test = float(average_precision_score(y_te, p_test))
    # Recall em threshold 0.5
    recall_test = float(recall_score(y_te, (p_test >= 0.5).astype(np.int8)))

    return {
        "configuracao": nome,
        "n_features": len(features),
        "auc_pr_val": round(auc_pr_val, 4),
        "auc_pr_test": round(auc_pr_test, 4),
        "recall_test_thr05": round(recall_test, 4),
        "tempo_s": round(elapsed, 1),
    }


def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("15_ablation_grupos.py - Ablation por grupo de features (v3)")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    print(f"  v3.parquet: {df.shape}")
    print(f"  Features totais: {len(FEATURES_V3)}")
    print(f"  Grupos definidos: {len(GRUPOS)}")
    print()

    linhas = []

    # Baseline: todas as features (v3 canonico re-treinado com mesmos params)
    print(f"  [0/{len(GRUPOS)+1}] Baseline: todas as features (replicar v3)...")
    r = treinar_e_avaliar(df, FEATURES_V3, "todas_as_features")
    print(f"      AUC-PR test: {r['auc_pr_test']:.4f} ({r['tempo_s']:.1f}s)")
    linhas.append(r)
    auc_test_baseline = r["auc_pr_test"]

    # Ablations
    for i, (nome_grupo, feats_remover) in enumerate(GRUPOS.items(), 1):
        feats_kept = [f for f in FEATURES_V3 if f not in feats_remover]
        print(f"  [{i}/{len(GRUPOS)}] Sem {nome_grupo} ({len(feats_remover)} features removidas)...")
        r = treinar_e_avaliar(df, feats_kept, f"sem_{nome_grupo}")
        delta = r["auc_pr_test"] - auc_test_baseline
        r["delta_auc_pr_test_vs_baseline"] = round(delta, 4)
        r["features_removidas"] = ", ".join(feats_remover)
        print(f"      AUC-PR test: {r['auc_pr_test']:.4f} "
              f"(delta {delta:+.4f}, {r['tempo_s']:.1f}s)")
        linhas.append(r)

    # Tabela
    print()
    df_abl = pl.from_dicts(linhas)
    df_abl.write_csv(ARQ_TAB)
    print(f"  Tabela salva: {ARQ_TAB.relative_to(ROOT.parent)}")

    # Figura — bar chart ordenado por delta absoluto
    print()
    print("  Gerando Fig Extra E (ablation por grupo)...")
    ablations = df_abl.filter(pl.col("configuracao") != "todas_as_features").sort(
        "delta_auc_pr_test_vs_baseline"
    )
    nomes = [c.replace("sem_", "").replace("_", "\n", 1)
             for c in ablations["configuracao"].to_list()]
    deltas = [float(d) for d in ablations["delta_auc_pr_test_vs_baseline"].to_list()]
    cores = ["C3" if d < -0.01 else "C1" if d < 0 else "C2" for d in deltas]

    fig, ax = plt.subplots(figsize=(11, 6))
    bars = ax.barh(range(len(nomes)), deltas, color=cores,
                   edgecolor="black", linewidth=0.5)
    ax.set_yticks(range(len(nomes)))
    ax.set_yticklabels(nomes, fontsize=10)
    ax.axvline(0, color="black", linewidth=1)

    for bar, d in zip(bars, deltas):
        xpos = bar.get_width()
        align = "right" if xpos < 0 else "left"
        offset = -0.001 if xpos < 0 else 0.001
        ax.text(xpos + offset, bar.get_y() + bar.get_height() / 2,
                f"{d:+.4f}", va="center", ha=align, fontsize=10, fontweight="bold")

    ax.set_xlabel(r"$\Delta$ AUC-PR (test) vs baseline v3 (todas as features)",
                  fontsize=11)
    ax.set_title(
        f"Figura Extra E - Ablation por grupo de features (v3 com hiperparams fixos)\n"
        f"Baseline: todas as 34 features, AUC-PR test = {auc_test_baseline:.4f}.\n"
        f"Barras NEGATIVAS = grupo era importante (queda ao remover).",
        fontsize=11, fontweight="bold",
    )
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")

    # Sintese final
    print()
    print("=" * 70)
    print("SINTESE — qual grupo carrega o modelo v3?")
    print("=" * 70)
    print()
    print(f"  {'grupo':<20s} | {'delta AUC-PR':>14s} | {'AUC-PR sem':>11s} | {'queda %':>8s}")
    print(f"  {'-'*20} | {'-'*14} | {'-'*11} | {'-'*8}")
    for row in df_abl.filter(pl.col("configuracao") != "todas_as_features").sort(
        "delta_auc_pr_test_vs_baseline"
    ).iter_rows(named=True):
        grupo = row["configuracao"].replace("sem_", "")
        delta = row["delta_auc_pr_test_vs_baseline"]
        auc_sem = row["auc_pr_test"]
        queda_pct = 100.0 * delta / auc_test_baseline
        print(f"  {grupo:<20s} | {delta:>+14.4f} | {auc_sem:>11.4f} | {queda_pct:>+7.2f}%")

    elapsed = time.time() - t_start
    print()
    print(f"  Tempo total: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
