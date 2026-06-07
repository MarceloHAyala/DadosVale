# -*- coding: utf-8 -*-
"""
23_antecedencia_vs_acuracia.py - Quanto da performance e' antecipacao real vs deteccao do instante? (L12, CM 5.2)

Pergunta: o AUC-PR do v3 (0,8556) refere-se ao alvo "DG nas proximas 4h", que
inclui muitos casos "concomitantes" (DG acontecendo agora, antecipacao ~0). Este
script quantifica quanto da performance sobrevive quando EXIGIMOS um tempo minimo
de antecedencia real.

METODO:
  Para cada lead time minimo L em {0, 15, 30, 60, 90, 120} min, redefine o alvo:
      target_L(t) = 1  sse existe um DG na janela [t+L, t+4h] do mesmo equipamento.
  Mantem o MESMO score p do v3 (treinado em target_4h) e mede AUC-PR, AUC-ROC,
  prevalencia e lift contra cada target_L.

  - L=0 reproduz o target_4h original (sanity check: prevalencia ~0,169, AUC-PR ~0,8556).
  - Conforme L sobe, os positivos viram "DGs genuinamente futuros"; o score precisa
    detecta-los quando o sinal ainda e' fraco.

LEITURA:
  - Se a AUC-ROC (independente de prevalencia) se mantem alta com L grande -> o modelo
    ANTECIPA de fato; a queda do AUC-PR absoluto e' so o piso (prevalencia) caindo.
  - Se a AUC-ROC tambem desaba -> a performance vinha de detectar o instante, nao de antecipar.

Implementacao do alvo: join_asof forward encontra o primeiro DG com timestamp >= t+L;
positivo se esse DG <= t+4h.

Entradas:
  - Projeto/dados/features/v3.parquet
  - Projeto/modelos/lightgbm_v2_no_cascade.txt

Saidas:
  - Projeto/relatorio/tabelas/antecedencia_vs_acuracia.csv
  - Projeto/relatorio/figuras/figExJ_antecedencia_vs_acuracia.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/23_antecedencia_vs_acuracia.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score, roc_auc_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "antecedencia_vs_acuracia.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExJ_antecedencia_vs_acuracia.png"

N_TEST = 71_089
HORIZONTE_H = 4
LEAD_TIMES_MIN = [0, 15, 30, 60, 90, 120]

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


def alvo_para_L(eventos: pl.DataFrame, dgs: pl.DataFrame, L_min: int) -> np.ndarray:
    """target_L = 1 sse existe DG em [t+L, t+4h] (primeiro DG >= t+L cai dentro de t+4h)."""
    ev = eventos.with_columns(
        (pl.col("Data_Evento") + pl.duration(minutes=L_min)).alias("key_time")
    ).sort("key_time")
    j = ev.join_asof(
        dgs, left_on="key_time", right_on="dg_time", by="TAG", strategy="forward"
    )
    j = j.with_columns(
        (
            pl.col("dg_time").is_not_null()
            & (pl.col("dg_time") <= pl.col("Data_Evento") + pl.duration(hours=HORIZONTE_H))
        ).cast(pl.Int8).alias("target_L")
    )
    return j


def metricas(target: np.ndarray, p: np.ndarray) -> dict:
    npos = int(target.sum())
    n = len(target)
    prev = npos / n if n else 0.0
    auc_pr = float(average_precision_score(target, p)) if 0 < npos < n else None
    auc_roc = float(roc_auc_score(target, p)) if 0 < npos < n else None
    lift = (auc_pr / prev) if (auc_pr is not None and prev > 0) else None
    return {"n": n, "n_pos": npos, "prev": prev,
            "auc_pr": auc_pr, "auc_roc": auc_roc, "lift": lift}


def main() -> None:
    print("=" * 78)
    print("23_antecedencia_vs_acuracia.py - antecipacao real vs deteccao do instante (L12)")
    print("=" * 78)

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

    base = test.select(["TAG", "Data_Evento", "Is_Dont_Go"]).with_columns(
        pl.Series("p", p_all)
    )
    dgs = (
        test.filter(pl.col("Is_Dont_Go") == 1)
        .select(["TAG", pl.col("Data_Evento").alias("dg_time")])
        .sort("dg_time")
    )
    print(f"\nTest: n={test.height:,} | DGs no test (definem janelas): {dgs.height:,}")
    is_ca_full = (test["TAG"] == "CA65926").to_numpy()

    linhas = []
    print(f"\n{'L(min)':>6} | {'recorte':<16} | {'n_pos':>6} | {'prev':>6} | "
          f"{'AUC-PR':>7} | {'lift':>5} | {'AUC-ROC':>7}")
    print("-" * 78)
    for L in LEAD_TIMES_MIN:
        j = alvo_para_L(base, dgs, L)
        tgt = j["target_L"].to_numpy()
        p = j["p"].to_numpy()
        is_ca = (j["TAG"] == "CA65926").to_numpy()

        for recorte, mask in [("completo", np.ones(len(tgt), bool)),
                              ("sem_CA65926", ~is_ca)]:
            m = metricas(tgt[mask], p[mask])
            linhas.append({"lead_min": L, "recorte": recorte, **m})
            ap = f"{m['auc_pr']:.4f}" if m['auc_pr'] is not None else "N/A"
            lf = f"{m['lift']:.2f}" if m['lift'] is not None else "N/A"
            ar = f"{m['auc_roc']:.4f}" if m['auc_roc'] is not None else "N/A"
            print(f"{L:>6} | {recorte:<16} | {m['n_pos']:>6,} | {m['prev']:>6.3f} | "
                  f"{ap:>7} | {lf:>5} | {ar:>7}")
        print("-" * 78)

    tab = pl.from_dicts(linhas)
    tab = tab.with_columns([
        pl.col("prev").round(4), pl.col("auc_pr").round(4),
        pl.col("auc_roc").round(4), pl.col("lift").round(2),
    ])
    ARQ_TAB.parent.mkdir(parents=True, exist_ok=True)
    tab.write_csv(ARQ_TAB)
    print(f"\nSalvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # --- figura: AUC-PR e AUC-ROC vs lead time (recorte completo) ---
    comp = tab.filter(pl.col("recorte") == "completo").sort("lead_min")
    Ls = comp["lead_min"].to_list()
    aucpr = comp["auc_pr"].to_list()
    aucroc = comp["auc_roc"].to_list()
    prev = comp["prev"].to_list()

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.plot(Ls, aucroc, "o-", color="#1976d2", linewidth=2.5, markersize=9,
            label="AUC-ROC (independe de prevalência)")
    ax.plot(Ls, aucpr, "s-", color="#c62828", linewidth=2.5, markersize=9,
            label="AUC-PR")
    ax.plot(Ls, prev, "^--", color="#9e9e9e", linewidth=1.8, markersize=7,
            label="prevalência (piso do AUC-PR)")
    for x, y in zip(Ls, aucroc):
        ax.text(x, y + 0.02, f"{y:.3f}", ha="center", fontsize=9, color="#1976d2", fontweight="bold")
    for x, y in zip(Ls, aucpr):
        ax.text(x, y - 0.045, f"{y:.3f}", ha="center", fontsize=9, color="#c62828", fontweight="bold")
    ax.axvline(90, color="#2e7d32", linestyle=":", linewidth=1.5, alpha=0.7)
    ax.text(91, 0.05, "90 min\n(janela de mobilização)", fontsize=9, color="#2e7d32")
    ax.set_xlabel("Tempo mínimo de antecedência exigido, L (minutos)", fontsize=12)
    ax.set_ylabel("Métrica no test (jun/2025)", fontsize=12)
    ax.set_title(
        "Figura Extra J — Antecipação real vs detecção do instante (v3, test)\n"
        "Alvo redefinido: existe DG em [t+L, t+4h]? Score do v3 inalterado.",
        fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1.02)
    ax.set_xticks(Ls)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center right", fontsize=10)
    plt.tight_layout()
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")

    # --- leitura automatica ---
    print()
    print("=" * 78)
    print("LEITURA")
    print("=" * 78)
    r0 = tab.filter((pl.col("lead_min") == 0) & (pl.col("recorte") == "completo")).row(0, named=True)
    r90 = tab.filter((pl.col("lead_min") == 90) & (pl.col("recorte") == "completo")).row(0, named=True)
    print(f"  Sanity L=0: prev={r0['prev']:.3f} (esperado ~0,169), AUC-PR={r0['auc_pr']:.4f} (esperado ~0,8556)")
    print(f"  Em L=90min: prevalência caiu para {r90['prev']:.3f}; AUC-PR={r90['auc_pr']:.4f}; "
          f"AUC-ROC={r90['auc_roc']:.4f}; lift={r90['lift']:.2f}x")
    if r90['auc_roc'] is not None and r90['auc_roc'] >= 0.80:
        print("  -> AUC-ROC ALTA em 90min: o modelo ANTECIPA de fato; a queda do AUC-PR e' piso de prevalencia.")
    elif r90['auc_roc'] is not None and r90['auc_roc'] >= 0.65:
        print("  -> AUC-ROC MODERADA em 90min: antecipa parcialmente; degradacao real mas nao colapso.")
    else:
        print("  -> AUC-ROC BAIXA em 90min: performance vinha majoritariamente de detectar o instante.")
    print("=" * 78)


if __name__ == "__main__":
    main()
