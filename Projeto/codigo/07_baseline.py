"""
07_baseline.py - Modelo baseline heuristico para predicao de DG em 4h (W5).

Heuristica canonica: "DG_predito = 1 se houve evento Critico nas ultimas 4h
do mesmo TAG". Implementada como threshold sobre a feature `count_critico_4h`
(Familia 1 do 05_features.py, ja em v3.parquet).

Decisoes de escopo (consolidadas em conversa W5 pre-baseline):
  - Foco em target_4h APENAS (pergunta operacional canonica CM 1.2).
  - Score raw para AUC-PR: count_critico_4h (perfeitamente alinhado ao horizonte
    do target). Decisao: NAO incluir target_2h/target_8h no baseline porque
    exigiria features mal-alinhadas (count_critico_1h, count_critico_24h) que
    introduziriam vies metodologico. Sensibilidade da janela migra para
    08_lightgbm.py (Profundidade 1).
  - Thresholds binarios para Precision/Recall/F1: 1, 2, 3, 5 (cobertura ampla
    do espaco operacional).
  - Estratificacao mai vs jun obrigatoria desde o baseline (Mitigacao 3 — derivada
    da Fig 8 W4, drift mai->jun 4,5x).

Justificativa para servir de referencia em W5/W6:
  - Sem baseline, qualquer AUC-PR do LightGBM v1 fica sem contexto operacional.
  - GATE MARCO 1 exige comparacao explicita: LightGBM deve bater baseline em val
    E manter performance razoavel em test.
  - Baseline simples permite quantificar o "preco da complexidade" — se LightGBM
    nao bate baseline, problema esta nas features, nao no algoritmo.

Entradas:
  - Projeto/dados/features/v3.parquet (544.885 x 52, encoding limpo)

Saidas:
  - Print estruturado no terminal (val + test, por threshold)
  - Projeto/relatorio/tabelas/baseline_metricas.csv (8 linhas: 4 thresholds x 2 splits)

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/07_baseline.py
"""
from pathlib import Path
import time

import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_OUT = ROOT / "relatorio" / "tabelas" / "baseline_metricas.csv"

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
TARGET = "target_4h"
SCORE = "count_critico_4h"
THRESHOLDS = [1, 2, 3, 5]
SPLITS = ["val", "test"]

# Expectativas por split (asercoes defensivas)
N_VAL = 78_825
N_TEST = 71_089
POS_VAL = 14_481
POS_TEST = 12_038


# ===========================================================================
# Etapa 1 - Carregar e validar
# ===========================================================================
def carregar() -> pl.DataFrame:
    print("Etapa 1/3 - Carregando v3.parquet...")
    if not ARQ_V3.exists():
        raise FileNotFoundError(
            f"v3.parquet nao encontrado em {ARQ_V3}. "
            "Execute 06b_fix_encoding_leakage.py antes."
        )

    df = pl.read_parquet(ARQ_V3)
    print(f"  Shape: {df.shape}")

    # Validacoes basicas
    assert df.height == LINHAS_ESPERADAS, f"Linhas: {df.height} != {LINHAS_ESPERADAS}"
    for col in (SCORE, TARGET, "split"):
        assert col in df.columns, f"Coluna ausente: {col}"

    # Validacoes de NULLs (rolling/target devem ser preenchidos por construcao)
    nulls_score = df[SCORE].null_count()
    nulls_target = df[TARGET].null_count()
    assert nulls_score == 0, f"{SCORE} tem {nulls_score} NULLs — inesperado"
    assert nulls_target == 0, f"{TARGET} tem {nulls_target} NULLs — inesperado"

    # Validar contagens por split
    n_val = df.filter(pl.col("split") == "val").height
    n_test = df.filter(pl.col("split") == "test").height
    pos_val = df.filter((pl.col("split") == "val") & (pl.col(TARGET) == 1)).height
    pos_test = df.filter((pl.col("split") == "test") & (pl.col(TARGET) == 1)).height
    assert n_val == N_VAL, f"VAL: {n_val} != {N_VAL}"
    assert n_test == N_TEST, f"TEST: {n_test} != {N_TEST}"
    assert pos_val == POS_VAL, f"VAL pos: {pos_val} != {POS_VAL}"
    assert pos_test == POS_TEST, f"TEST pos: {pos_test} != {POS_TEST}"

    print(f"  Asercoes OK (val: {n_val:,}/{pos_val:,} | test: {n_test:,}/{pos_test:,})")
    return df


# ===========================================================================
# Etapa 2 - Calcular metricas por split
# ===========================================================================
def metricas_binarias(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Precision/Recall/F1 + matriz de confusao bruta."""
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": prec, "recall": rec, "f1": f1}


def avaliar_split(df: pl.DataFrame, split: str) -> tuple[list[dict], float, float]:
    """Avalia heuristica em um split. Retorna (rows, auc_pr, random_ap)."""
    sub = df.filter(pl.col("split") == split)
    n = sub.height
    y_true = sub[TARGET].to_numpy().astype(np.int8)
    score = sub[SCORE].to_numpy()
    n_pos = int(y_true.sum())

    # AUC-PR sobre score raw (count_critico_4h como continuo)
    auc_pr = float(average_precision_score(y_true, score))

    # Baseline de chance (taxa de positivos = AP de classificador aleatorio)
    random_ap = n_pos / n

    print()
    print(f"=" * 70)
    print(f"Split: {split:<5} | {n:>7,} eventos | {n_pos:>6,} positivos "
          f"({n_pos/n*100:5.2f}%)")
    print(f"=" * 70)
    print(f"  AUC-PR (score = {SCORE}):  {auc_pr:.4f}")
    print(f"  Random AP (chance baseline):   {random_ap:.4f}")
    print(f"  Lift sobre random:             {auc_pr/random_ap:.2f}x")

    print()
    print(f"  Metricas binarias por threshold:")
    print(f"  {'thr':>3} | {'n_pred=1':>9} | {'TP':>7} | {'FP':>7} | {'FN':>7} | "
          f"{'TN':>7} | {'Prec':>7} | {'Rec':>7} | {'F1':>7}")
    print(f"  {'-' * 3:>3} | {'-' * 9:>9} | {'-' * 7:>7} | {'-' * 7:>7} | "
          f"{'-' * 7:>7} | {'-' * 7:>7} | {'-' * 7:>7} | {'-' * 7:>7} | {'-' * 7:>7}")

    rows = []
    for t in THRESHOLDS:
        y_pred = (score >= t).astype(np.int8)
        m = metricas_binarias(y_true, y_pred)
        n_pos_pred = int(y_pred.sum())

        print(f"  {t:>3} | {n_pos_pred:>9,} | {m['tp']:>7,} | {m['fp']:>7,} | "
              f"{m['fn']:>7,} | {m['tn']:>7,} | "
              f"{m['precision']:>7.4f} | {m['recall']:>7.4f} | {m['f1']:>7.4f}")

        rows.append({
            "split": split,
            "threshold": t,
            "n_eventos": n,
            "n_positivos": n_pos,
            "n_pos_predito": n_pos_pred,
            "tp": m["tp"], "fp": m["fp"], "fn": m["fn"], "tn": m["tn"],
            "precision": round(m["precision"], 4),
            "recall": round(m["recall"], 4),
            "f1": round(m["f1"], 4),
            "auc_pr": round(auc_pr, 4),
            "random_ap": round(random_ap, 4),
        })

    return rows, auc_pr, random_ap


# ===========================================================================
# Etapa 3 - Consolidar, persistir e sumario Mitigacao 3
# ===========================================================================
def persistir(all_rows: list[dict]) -> pl.DataFrame:
    print()
    print("Etapa 3/3 - Persistindo baseline_metricas.csv...")

    metricas = pl.from_dicts(all_rows)
    metricas.write_csv(ARQ_OUT)
    print(f"  {metricas.height} linhas escritas em {ARQ_OUT.relative_to(ROOT.parent)}")
    return metricas


def sumario_mitigacao_3(metricas: pl.DataFrame, auc_val: float, auc_test: float) -> None:
    """Comparacao explicita val (mai) vs test (jun) — Mitigacao 3."""
    print()
    print("=" * 70)
    print("SUMARIO MITIGACAO 3 — Comparacao val (mai) vs test (jun)")
    print("=" * 70)

    for t in THRESHOLDS:
        row_val = metricas.filter(
            (pl.col("split") == "val") & (pl.col("threshold") == t)
        ).row(0, named=True)
        row_test = metricas.filter(
            (pl.col("split") == "test") & (pl.col("threshold") == t)
        ).row(0, named=True)

        print(f"\n  Threshold = {t}:")
        print(f"    {'metrica':<10} | {'val (mai)':>10} | {'test (jun)':>10} | {'diff':>8}")
        for col in ["precision", "recall", "f1"]:
            v = row_val[col]
            te = row_test[col]
            diff = te - v
            print(f"    {col:<10} | {v:>10.4f} | {te:>10.4f} | {diff:>+8.4f}")

    print()
    print(f"  AUC-PR val (mai):     {auc_val:.4f}")
    print(f"  AUC-PR test (jun):    {auc_test:.4f}")
    razao = auc_test / auc_val if auc_val > 0 else float("inf")
    print(f"  Razao test/val:       {razao:.2f}x")
    queda = (auc_val - auc_test) / auc_val * 100 if auc_val > 0 else 0
    if queda > 0:
        print(f"  Queda test vs val:    {queda:+.1f}%")
    else:
        print(f"  Ganho test vs val:    {-queda:+.1f}% (test melhor)")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("07_baseline.py - Heuristica baseline para target_4h (W5)")
    print("=" * 70)
    print(f"  Heuristica: predict_dg = (count_critico_4h >= threshold)")
    print(f"  Target:     {TARGET}")
    print(f"  Score:      {SCORE}")
    print(f"  Thresholds: {THRESHOLDS}")
    print(f"  Splits:     {SPLITS}")

    df = carregar()

    all_rows = []
    aucs = {}
    for split in SPLITS:
        rows, auc_pr, _ = avaliar_split(df, split)
        all_rows.extend(rows)
        aucs[split] = auc_pr

    metricas = persistir(all_rows)
    sumario_mitigacao_3(metricas, aucs["val"], aucs["test"])

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s")
    print(f"Referencia baseline pronta para comparacao em 08_lightgbm.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
