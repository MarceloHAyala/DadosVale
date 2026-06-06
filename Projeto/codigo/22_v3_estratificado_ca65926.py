# -*- coding: utf-8 -*-
"""
22_v3_estratificado_ca65926.py - AUC-PR do v3 com vs sem CA65926 (L10, CM 5.2).

Fecha o buraco identificado em 06/06: a estratificacao "com vs sem CA65926"
existia apenas para o Isolation Forest (AUC-ROC sobre Is_Dont_Go), usada como
PROXY para a limitacao L10. Aqui calculamos a metrica do PROPRIO modelo v3
(LightGBM canonico) sobre seu target real (target_4h), separando:

  - test_completo (com CA65926)
  - CA65926_apenas
  - test_sem_CA65926 (generalizacao real para os demais 29 equipamentos)

Material direto para T1.1 (liderar com o numero honesto de generalizacao) e
para sustentar L10 com o numero do proprio modelo, nao com proxy.

Entradas:
  - Projeto/dados/features/v3.parquet
  - Projeto/modelos/lightgbm_v2_no_cascade.txt

Saidas:
  - Projeto/relatorio/tabelas/eval_v3_ca65926.csv

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/22_v3_estratificado_ca65926.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score, recall_score, roc_auc_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "eval_v3_ca65926.csv"

N_TEST = 71_089
TARGET = "target_4h"
THRESHOLD = 0.5

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


def main() -> None:
    print("=" * 70)
    print("22_v3_estratificado_ca65926.py - AUC-PR do v3 com vs sem CA65926 (L10)")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    test = df.filter(pl.col("split") == "test")
    assert test.height == N_TEST

    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    X = test.select(FEATURES).to_pandas()
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)

    proba = booster.predict(X)
    y = test[TARGET].to_numpy().astype(np.int8)
    is_ca = (test["TAG"] == "CA65926").to_numpy()

    grupos = {
        "test_completo (com CA65926)": np.ones(N_TEST, dtype=bool),
        "CA65926_apenas": is_ca,
        "test_sem_CA65926": ~is_ca,
    }

    linhas = []
    print(f"\n{'subgrupo':<32s} | {'n':>7s} | {'pos':>6s} | {'prev':>6s} | "
          f"{'AUC-PR':>7s} | {'AUC-ROC':>7s} | {'Recall':>7s}")
    print("-" * 92)
    for nome, mask in grupos.items():
        yy = y[mask]
        pp = proba[mask]
        n = int(mask.sum())
        npos = int(yy.sum())
        prev = npos / n if n else 0.0
        auc_pr = float(average_precision_score(yy, pp)) if npos > 0 else None
        auc_roc = float(roc_auc_score(yy, pp)) if 0 < npos < n else None
        pred = (pp >= THRESHOLD).astype(np.int8)
        rec = float(recall_score(yy, pred, zero_division=0)) if npos > 0 else None
        linhas.append({
            "subgrupo": nome,
            "n_eventos": n,
            "n_positivos_target4h": npos,
            "prevalencia": round(prev, 4),
            "auc_pr": round(auc_pr, 4) if auc_pr is not None else None,
            "auc_roc": round(auc_roc, 4) if auc_roc is not None else None,
            "recall_05": round(rec, 4) if rec is not None else None,
        })
        ap = f"{auc_pr:.4f}" if auc_pr is not None else "N/A"
        ar = f"{auc_roc:.4f}" if auc_roc is not None else "N/A"
        rc = f"{rec:.4f}" if rec is not None else "N/A"
        print(f"{nome:<32s} | {n:>7,} | {npos:>6,} | {prev:>6.3f} | "
              f"{ap:>7s} | {ar:>7s} | {rc:>7s}")

    pl.from_dicts(linhas).write_csv(ARQ_TAB)
    print(f"\nSalvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # leitura sintetica
    full = linhas[0]
    sem = linhas[2]
    print()
    print("=" * 70)
    print("LEITURA (L10 / T1.1)")
    print("=" * 70)
    print(f"  AUC-PR com CA65926 (manchete): {full['auc_pr']:.4f}")
    print(f"  AUC-PR sem CA65926 (generalizacao real): {sem['auc_pr']:.4f}")
    queda = (full["auc_pr"] - sem["auc_pr"]) * 100
    print(f"  Queda ao remover CA65926: {queda:+.2f} pp")
    print("=" * 70)


if __name__ == "__main__":
    main()
