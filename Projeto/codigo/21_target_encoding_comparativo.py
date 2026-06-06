# -*- coding: utf-8 -*-
"""
21_target_encoding_comparativo.py - Refinamento opcional de W5 (CM 3.2).

Implementa o item adiado de W5: substituir o *frequency encoding* (`tag_freq`,
`operador_freq`, Familia 7) por **target encoding com KFold temporal** nas duas
categoricas de alta cardinalidade (TAG: 35 valores; Nome_Operador_Anon: ~394),
e comparar de forma rigorosa contra o v3 canonico.

PROTOCOLO (conforme PLANEJAMENTO.md W5):
  - KFold temporal por MES dentro do treino (jan/fev/mar/abr = folds 1-4).
  - Para cada mes-fold, codifica usando os OUTROS 3 meses (out-of-fold) -> sem
    leakage do proprio fold.
  - Smoothing: enc = (soma_y_cat + alpha*media_global) / (n_cat + alpha), alpha=10.
    Categorias raras puxadas para a media global; categorias nunca vistas -> media
    global (o smoothing trata naturalmente: n_cat=0 -> enc=media_global).
  - val (mai) e test (jun): ajuste sobre o TREINO COMPLETO (jan-abr), sem KFold.
  - Comparacao apples-to-apples: hiperparametros FIXOS do v3 (mesma metodologia do
    ablation 15), variando SOMENTE o encoding das 2 features. Treina as DUAS
    variantes no mesmo pipeline para eliminar qualquer confounding.

CRITERIO DE DECISAO (do plano): se o ganho de AUC-PR em VALIDACAO for > 1pp,
substituir; caso contrario, manter frequency encoding por parsimonia.

Entradas:
  - Projeto/dados/features/v3.parquet
  - Projeto/relatorio/tabelas/lightgbm_v2_no_cascade_hiperparametros.csv (params v3)

Saidas:
  - Projeto/relatorio/tabelas/target_encoding_comparativo.csv

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/21_target_encoding_comparativo.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import average_precision_score, recall_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "target_encoding_comparativo.csv"

LINHAS_ESPERADAS = 544_885
SEED = 42
TARGET = "target_4h"
ALPHA = 10.0  # smoothing
GANHO_MINIMO_PP = 1.0  # criterio de substituicao (pp em validacao)

# 34 features do v3 canonico (sem horas_desde_ultimo_DG)
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

# v3 best params (lightgbm_v2_no_cascade_hiperparametros.csv)
BEST_PARAMS = {
    "n_estimators": 301,
    "learning_rate": 0.011750409866019435,
    "num_leaves": 69,
    "min_child_samples": 50,
    "scale_pos_weight": 2.400711223647736,
    "lambda_l1": 0.1966545804632781,
    "lambda_l2": 1.1830097418431307,
}
PARAMS_BASE = {
    "objective": "binary",
    "verbosity": -1,
    "random_state": SEED,
    "n_jobs": -1,
    "deterministic": True,
    "force_col_wise": True,
}

MESES_TREINO = [1, 2, 3, 4]  # jan-abr


def smoothed_rate(sub: pd.DataFrame, cat_col: str, global_mean: float) -> pd.Series:
    """Taxa de target suavizada por categoria (Series indexada pela categoria)."""
    g = sub.groupby(cat_col, observed=True)[TARGET].agg(["sum", "count"])
    return (g["sum"] + ALPHA * global_mean) / (g["count"] + ALPHA)


def target_encode(meta: pd.DataFrame, cat_col: str) -> np.ndarray:
    """
    Target encoding com KFold temporal (out-of-fold no treino, fit-no-treino p/ val/test).
    Retorna array full-length alinhado a `meta` (ordem de linha preservada).
    """
    enc = pd.Series(np.nan, index=meta.index, dtype=float)
    train = meta[meta["split"] == "train"]

    # --- treino: out-of-fold por mes ---
    for m in MESES_TREINO:
        outros = train[train["mes"].isin([x for x in MESES_TREINO if x != m])]
        gm = float(outros[TARGET].mean())
        rate = smoothed_rate(outros, cat_col, gm)
        idx_fold = train.index[train["mes"] == m]
        enc.loc[idx_fold] = meta.loc[idx_fold, cat_col].map(rate).fillna(gm)

    # --- val + test: fit no treino completo ---
    gm_full = float(train[TARGET].mean())
    rate_full = smoothed_rate(train, cat_col, gm_full)
    idx_vt = meta.index[meta["split"].isin(["val", "test"])]
    enc.loc[idx_vt] = meta.loc[idx_vt, cat_col].map(rate_full).fillna(gm_full)

    assert enc.notna().all(), f"NaN residual no encoding de {cat_col}"
    return enc.to_numpy()


def preparar_X(df: pl.DataFrame, mask: pl.Series, overrides: dict | None) -> tuple[pd.DataFrame, np.ndarray]:
    """Monta X (34 features) para o subconjunto `mask`. overrides: {feature: np.ndarray full-length}."""
    idx = mask.to_numpy()
    sub = df.filter(mask)
    pdf = sub.select(FEATURES + [TARGET]).to_pandas()
    y = pdf[TARGET].to_numpy().astype(np.int8)
    X = pdf[FEATURES].copy()
    if overrides:
        for feat, arr in overrides.items():
            X[feat] = arr[idx]
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return X, y


def treinar_avaliar(df: pl.DataFrame, nome: str, overrides: dict | None) -> dict:
    params = {**PARAMS_BASE, **BEST_PARAMS}
    modelo = lgb.LGBMClassifier(**params)
    X_tr, y_tr = preparar_X(df, df["split"] == "train", overrides)
    modelo.fit(X_tr, y_tr, categorical_feature=CAT_FEATURES)
    res = {"variante": nome}
    for split in ["train", "val", "test"]:
        X, y = preparar_X(df, df["split"] == split, overrides)
        proba = modelo.predict_proba(X)[:, 1]
        pred = (proba >= 0.5).astype(np.int8)
        res[f"auc_pr_{split}"] = round(float(average_precision_score(y, proba)), 4)
        res[f"recall_{split}"] = round(float(recall_score(y, pred, zero_division=0)), 4)
    return res


def main() -> None:
    print("=" * 70)
    print("21_target_encoding_comparativo.py - frequency vs target encoding (W5)")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    assert df.height == LINHAS_ESPERADAS
    print(f"\nv3.parquet: {df.shape}")

    # sanidade: split <-> mes
    chk = (df.group_by("split").agg(pl.col("mes").min().alias("mes_min"),
                                    pl.col("mes").max().alias("mes_max"))
             .sort("split"))
    print("Alinhamento split x mes:")
    for r in chk.iter_rows(named=True):
        print(f"  {r['split']:<6s}: mes {r['mes_min']}-{r['mes_max']}")

    # --- computar target encodings ---
    print("\nComputando target encoding (KFold temporal, alpha=10)...")
    meta = df.select(["TAG", "Nome_Operador_Anon", "mes", TARGET, "split"]).to_pandas()
    tag_te = target_encode(meta, "TAG")
    op_te = target_encode(meta, "Nome_Operador_Anon")

    # diagnostico rapido: correlacao entre freq e target enc no treino
    tr = (df["split"] == "train").to_numpy()
    tag_freq = df["tag_freq"].to_numpy()
    op_freq = df["operador_freq"].to_numpy()
    print(f"  TAG     : corr(freq, target_enc) no treino = "
          f"{np.corrcoef(tag_freq[tr], tag_te[tr])[0,1]:+.3f} | "
          f"target_enc range [{tag_te.min():.4f}, {tag_te.max():.4f}]")
    print(f"  Operador: corr(freq, target_enc) no treino = "
          f"{np.corrcoef(op_freq[tr], op_te[tr])[0,1]:+.3f} | "
          f"target_enc range [{op_te.min():.4f}, {op_te.max():.4f}]")

    overrides_te = {"tag_freq": tag_te, "operador_freq": op_te}

    # --- treinar as 2 variantes (mesmos hiperparams fixos do v3) ---
    print("\nTreinando variante BASELINE (frequency encoding, = v3 canonico)...")
    r_base = treinar_avaliar(df, "frequency (v3 canonico)", None)
    print(f"  AUC-PR  train={r_base['auc_pr_train']} | val={r_base['auc_pr_val']} | "
          f"test={r_base['auc_pr_test']}")
    print(f"  Recall  train={r_base['recall_train']} | val={r_base['recall_val']} | "
          f"test={r_base['recall_test']}")

    print("\nTreinando variante TARGET ENCODING (KFold temporal)...")
    r_te = treinar_avaliar(df, "target_encoding_kfold", overrides_te)
    print(f"  AUC-PR  train={r_te['auc_pr_train']} | val={r_te['auc_pr_val']} | "
          f"test={r_te['auc_pr_test']}")
    print(f"  Recall  train={r_te['recall_train']} | val={r_te['recall_val']} | "
          f"test={r_te['recall_test']}")

    # --- decisao ---
    ganho_val = (r_te["auc_pr_val"] - r_base["auc_pr_val"]) * 100
    ganho_test = (r_te["auc_pr_test"] - r_base["auc_pr_test"]) * 100
    substituir = ganho_val > GANHO_MINIMO_PP

    tab = pl.from_dicts([r_base, r_te])
    tab = tab.with_columns([
        pl.lit(round(ganho_val, 2)).alias("ganho_val_pp_vs_baseline"),
        pl.lit(round(ganho_test, 2)).alias("ganho_test_pp_vs_baseline"),
    ])
    ARQ_TAB.parent.mkdir(parents=True, exist_ok=True)
    tab.write_csv(ARQ_TAB)

    print()
    print("=" * 70)
    print("DECISAO")
    print("=" * 70)
    print(f"  Ganho AUC-PR em VALIDACAO (target_enc - frequency): {ganho_val:+.2f} pp")
    print(f"  Ganho AUC-PR em TESTE:                              {ganho_test:+.2f} pp")
    print(f"  Criterio de substituicao: ganho_val > {GANHO_MINIMO_PP} pp")
    print()
    if substituir:
        print(f"  -> SUBSTITUIR frequency por target encoding "
              f"(ganho_val={ganho_val:+.2f}pp > {GANHO_MINIMO_PP}pp).")
    else:
        print(f"  -> MANTER frequency encoding (ganho_val={ganho_val:+.2f}pp "
              f"<= {GANHO_MINIMO_PP}pp). Parsimonia: menos codigo, sem ganho material.")
    print()
    print(f"  Tabela: {ARQ_TAB.relative_to(ROOT.parent)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
