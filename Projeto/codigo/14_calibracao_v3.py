"""
14_calibracao_v3.py - Calibracao do LightGBM v3 (Qualidade A).

Avalia se as probabilidades preditas pelo v3 estao bem calibradas:
  - Se P(target_4h=1) predita = 0.30, esperamos que ~30% desses eventos sejam DG
  - Se mal calibrado, aplica Platt scaling (regressao logistica sobre o val)

Metricas:
  - Brier score: erro quadratico medio entre prob predita e label real
  - Calibration plot: 10 bins de prob predita vs fracao real de positivos
  - ECE (Expected Calibration Error): erro medio ponderado por bin

Decisao operacional:
  - Se ECE < 0.02 (2pp): bem calibrado, deployment OK
  - Se ECE >= 0.02: aplicar Platt scaling, refittando regressao logistica sobre val

Entradas:
  - dados/features/v3.parquet
  - modelos/lightgbm_v2_no_cascade.txt (v3 canonico)

Saidas:
  - relatorio/tabelas/calibracao_v3.csv (Brier + ECE pre/pos calibracao)
  - relatorio/figuras/figExF_calibracao_v3.png (curva de calibracao + histograma)
  - modelos/calibrador_v3_platt.joblib (apenas se Platt aplicado)

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/14_calibracao_v3.py
"""
from pathlib import Path
import warnings

import joblib
import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

warnings.filterwarnings("ignore")


ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_LGB = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"
ARQ_PLATT = ROOT / "modelos" / "calibrador_v3_platt.joblib"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "calibracao_v3.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExF_calibracao_v3.png"

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
N_BINS = 10
LIMIAR_ECE = 0.02  # 2pp


def predizer_v3(df: pl.DataFrame, booster: lgb.Booster) -> np.ndarray:
    X = df.select(FEATURES_V3).to_pandas()
    for c in ["turno", "estado_pre_evento"]:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return booster.predict(X)


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray,
                                n_bins: int = 10) -> float:
    """ECE: erro medio ponderado por bin entre prob media predita e fracao real."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.digitize(y_prob, bins[1:-1])
    ece = 0.0
    n_total = len(y_true)
    for i in range(n_bins):
        mask = bin_idx == i
        n_bin = int(mask.sum())
        if n_bin == 0:
            continue
        acc = float(y_true[mask].mean())
        conf = float(y_prob[mask].mean())
        ece += (n_bin / n_total) * abs(acc - conf)
    return ece


def main() -> None:
    print("=" * 70)
    print("14_calibracao_v3.py - Calibracao do LightGBM v3 (Qualidade A)")
    print("=" * 70)

    booster = lgb.Booster(model_file=str(ARQ_LGB))
    df = pl.read_parquet(ARQ_V3)
    val = df.filter(pl.col("split") == "val")
    test = df.filter(pl.col("split") == "test")
    y_val = val["target_4h"].to_numpy()
    y_test = test["target_4h"].to_numpy()

    print(f"  val: n={val.height:,}, positivos={int(y_val.sum()):,}")
    print(f"  test: n={test.height:,}, positivos={int(y_test.sum()):,}")
    print()

    # Predicoes raw
    p_val_raw = predizer_v3(val, booster)
    p_test_raw = predizer_v3(test, booster)
    print(f"  Predicoes raw obtidas (range val: [{p_val_raw.min():.4f}, {p_val_raw.max():.4f}])")

    # Metricas raw
    brier_val_raw = brier_score_loss(y_val, p_val_raw)
    brier_test_raw = brier_score_loss(y_test, p_test_raw)
    ece_val_raw = expected_calibration_error(y_val, p_val_raw, N_BINS)
    ece_test_raw = expected_calibration_error(y_test, p_test_raw, N_BINS)
    prev_val = float(y_val.mean())
    prev_test = float(y_test.mean())
    # Brier baseline = variancia da prevalencia (predicao constante)
    brier_baseline_val = prev_val * (1 - prev_val)
    brier_baseline_test = prev_test * (1 - prev_test)

    print()
    print("  Metricas v3 RAW (sem calibracao):")
    print(f"    Brier val:  {brier_val_raw:.5f}  (baseline {brier_baseline_val:.5f}, "
          f"skill = 1 - {brier_val_raw/brier_baseline_val:.4f} = {1 - brier_val_raw/brier_baseline_val:+.4f})")
    print(f"    Brier test: {brier_test_raw:.5f} (baseline {brier_baseline_test:.5f}, "
          f"skill = 1 - {brier_test_raw/brier_baseline_test:.4f} = {1 - brier_test_raw/brier_baseline_test:+.4f})")
    print(f"    ECE val:  {ece_val_raw:.4f} ({ece_val_raw*100:.2f}pp)")
    print(f"    ECE test: {ece_test_raw:.4f} ({ece_test_raw*100:.2f}pp)")

    # Decisao: aplicar Platt scaling?
    print()
    decidir_platt = ece_test_raw >= LIMIAR_ECE or ece_val_raw >= LIMIAR_ECE
    if decidir_platt:
        print(f"  ECE >= {LIMIAR_ECE} (limiar) -> aplicando Platt scaling (fit no val)...")

        # Platt: regressao logistica sobre p_val_raw (1 feature) -> y_val
        platt = LogisticRegression(max_iter=1000)
        platt.fit(p_val_raw.reshape(-1, 1), y_val)
        p_val_cal = platt.predict_proba(p_val_raw.reshape(-1, 1))[:, 1]
        p_test_cal = platt.predict_proba(p_test_raw.reshape(-1, 1))[:, 1]

        brier_val_cal = brier_score_loss(y_val, p_val_cal)
        brier_test_cal = brier_score_loss(y_test, p_test_cal)
        ece_val_cal = expected_calibration_error(y_val, p_val_cal, N_BINS)
        ece_test_cal = expected_calibration_error(y_test, p_test_cal, N_BINS)

        joblib.dump({"platt": platt}, ARQ_PLATT, compress=3)
        print(f"  Calibrador salvo: {ARQ_PLATT.relative_to(ROOT.parent)}")
        print()
        print(f"  Metricas v3 CALIBRADO (Platt sobre val):")
        print(f"    Brier val:  {brier_val_cal:.5f} (delta {brier_val_cal - brier_val_raw:+.5f})")
        print(f"    Brier test: {brier_test_cal:.5f} (delta {brier_test_cal - brier_test_raw:+.5f})")
        print(f"    ECE val:  {ece_val_cal:.4f} ({ece_val_cal*100:.2f}pp; "
              f"delta {ece_val_cal - ece_val_raw:+.4f})")
        print(f"    ECE test: {ece_test_cal:.4f} ({ece_test_cal*100:.2f}pp; "
              f"delta {ece_test_cal - ece_test_raw:+.4f})")
    else:
        print(f"  ECE < {LIMIAR_ECE} (limiar) -> v3 bem calibrado, sem Platt necessario")
        p_val_cal = p_val_raw
        p_test_cal = p_test_raw
        brier_val_cal = brier_val_raw
        brier_test_cal = brier_test_raw
        ece_val_cal = ece_val_raw
        ece_test_cal = ece_test_raw

    # Tabela final
    linhas = [
        {"versao": "raw", "split": "val", "brier": round(brier_val_raw, 5),
         "brier_baseline": round(brier_baseline_val, 5),
         "skill_brier": round(1 - brier_val_raw/brier_baseline_val, 4),
         "ece": round(ece_val_raw, 4)},
        {"versao": "raw", "split": "test", "brier": round(brier_test_raw, 5),
         "brier_baseline": round(brier_baseline_test, 5),
         "skill_brier": round(1 - brier_test_raw/brier_baseline_test, 4),
         "ece": round(ece_test_raw, 4)},
    ]
    if decidir_platt:
        linhas.extend([
            {"versao": "platt", "split": "val", "brier": round(brier_val_cal, 5),
             "brier_baseline": round(brier_baseline_val, 5),
             "skill_brier": round(1 - brier_val_cal/brier_baseline_val, 4),
             "ece": round(ece_val_cal, 4)},
            {"versao": "platt", "split": "test", "brier": round(brier_test_cal, 5),
             "brier_baseline": round(brier_baseline_test, 5),
             "skill_brier": round(1 - brier_test_cal/brier_baseline_test, 4),
             "ece": round(ece_test_cal, 4)},
        ])
    pl.from_dicts(linhas).write_csv(ARQ_TAB)
    print()
    print(f"  Tabela salva: {ARQ_TAB.relative_to(ROOT.parent)}")

    # Figura
    print()
    print("  Gerando figExF (calibracao plot + histograma)...")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # (a) Calibration curve no test
    ax = axes[0]
    frac_pos_raw, mean_pred_raw = calibration_curve(y_test, p_test_raw, n_bins=N_BINS)
    ax.plot(mean_pred_raw, frac_pos_raw, "o-", color="C3", linewidth=2,
            markersize=8, label=f"v3 raw (ECE={ece_test_raw:.4f})")
    if decidir_platt:
        frac_pos_cal, mean_pred_cal = calibration_curve(y_test, p_test_cal, n_bins=N_BINS)
        ax.plot(mean_pred_cal, frac_pos_cal, "s-", color="C2", linewidth=2,
                markersize=8, label=f"v3 + Platt (ECE={ece_test_cal:.4f})")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.5,
            label="Calibracao perfeita")
    ax.set_xlabel("Probabilidade predita (media por bin)", fontsize=11)
    ax.set_ylabel("Fracao real de positivos no bin", fontsize=11)
    ax.set_title(f"(a) Curva de calibracao no test (n_bins={N_BINS})",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    # (b) Histograma da prob predita no test, separando classes
    ax = axes[1]
    bins = np.linspace(0, 1, 40)
    ax.hist(p_test_raw[y_test == 0], bins=bins, alpha=0.5, color="C0",
            label=f"nao-DG (n={int((y_test==0).sum()):,})", density=True)
    ax.hist(p_test_raw[y_test == 1], bins=bins, alpha=0.5, color="C3",
            label=f"DG (n={int((y_test==1).sum()):,})", density=True)
    ax.set_xlabel("Probabilidade predita pelo v3 (raw)", fontsize=11)
    ax.set_ylabel("densidade", fontsize=11)
    ax.set_title("(b) Distribuicao das probabilidades preditas (test)",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        f"Figura Extra F - Calibracao do LightGBM v3 (test, n={len(y_test):,})\n"
        f"Brier raw test = {brier_test_raw:.5f} | "
        f"baseline = {brier_baseline_test:.5f} | "
        f"skill = {1 - brier_test_raw/brier_baseline_test:+.4f}",
        fontsize=12, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")
    print()
    print("=" * 70)
    if decidir_platt:
        print("VEREDITO: v3 estava mal calibrado, Platt scaling aplicado e salvo.")
    else:
        print("VEREDITO: v3 esta bem calibrado, sem Platt scaling necessario.")
    print("=" * 70)


if __name__ == "__main__":
    main()
