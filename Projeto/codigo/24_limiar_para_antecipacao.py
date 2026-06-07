# -*- coding: utf-8 -*-
"""
24_limiar_para_antecipacao.py - A partir de qual limiar capturamos a antecipacao de 90-120 min? (L12, CM 5.2)

A figExJ (script 23) prova que a CAPACIDADE de antecipar 90-120 min existe no
score do v3 (AUC-ROC ~0,91, metrica independente de limiar). Mas ela nao diz em
QUAL limiar essa antecipacao vira alerta na pratica, nem a que custo de precisao.

Este script responde isso: para o alvo "existe DG em [t+L, t+4h]" (L = 90 e 120 min),
varre limiares e mede recall (fracao dos DGs antecipados que disparam), precisao
(fracao dos alertas que sao positivos reais) e volume de alertas. Resultado: o
ponto de operacao que realiza a antecipacao.

Entradas:
  - Projeto/dados/features/v3.parquet
  - Projeto/modelos/lightgbm_v2_no_cascade.txt

Saidas:
  - Projeto/relatorio/tabelas/limiar_para_antecipacao.csv
  - Projeto/relatorio/figuras/figExK_limiar_para_antecipacao.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/24_limiar_para_antecipacao.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.metrics import precision_score, recall_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "limiar_para_antecipacao.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExK_limiar_para_antecipacao.png"

N_TEST = 71_089
HORIZONTE_H = 4
LEADS = [90, 120]
THRESH_GRID = np.round(np.arange(0.05, 0.96, 0.025), 3)
THRESH_OP = {"Amarelo Q6": 0.145, "Vermelho Q6": 0.30, "Padrão": 0.5}

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


def alvo_para_L(base: pl.DataFrame, dgs: pl.DataFrame, L_min: int) -> np.ndarray:
    ev = base.with_columns(
        (pl.col("Data_Evento") + pl.duration(minutes=L_min)).alias("key_time")
    ).sort("key_time")
    j = ev.join_asof(dgs, left_on="key_time", right_on="dg_time", by="TAG", strategy="forward")
    j = j.with_columns(
        (
            pl.col("dg_time").is_not_null()
            & (pl.col("dg_time") <= pl.col("Data_Evento") + pl.duration(hours=HORIZONTE_H))
        ).cast(pl.Int8).alias("t")
    )
    return j.select(["p", "t"])


def main() -> None:
    print("=" * 80)
    print("24_limiar_para_antecipacao.py - qual limiar realiza a antecipacao de 90-120 min?")
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

    base = test.select(["TAG", "Data_Evento"]).with_columns(pl.Series("p", p_all))
    dgs = (test.filter(pl.col("Is_Dont_Go") == 1)
           .select(["TAG", pl.col("Data_Evento").alias("dg_time")]).sort("dg_time"))

    linhas = []
    curvas = {}
    for L in LEADS:
        sel = alvo_para_L(base, dgs, L)
        p = sel["p"].to_numpy()
        t = sel["t"].to_numpy()
        n_pos = int(t.sum())
        rec_list, prec_list, nalert_list = [], [], []
        for thr in THRESH_GRID:
            pred = (p >= thr).astype(np.int8)
            n_alert = int(pred.sum())
            rec = recall_score(t, pred, zero_division=0)
            prec = precision_score(t, pred, zero_division=0)
            rec_list.append(rec); prec_list.append(prec); nalert_list.append(n_alert)
        curvas[L] = {"thr": THRESH_GRID, "rec": np.array(rec_list),
                     "prec": np.array(prec_list), "nalert": np.array(nalert_list),
                     "n_pos": n_pos}
        # tabela nos limiares operacionais
        for nome, thr in THRESH_OP.items():
            pred = (p >= thr).astype(np.int8)
            rec = recall_score(t, pred, zero_division=0)
            prec = precision_score(t, pred, zero_division=0)
            n_alert = int(pred.sum())
            n_caught = int(((pred == 1) & (t == 1)).sum())
            linhas.append({
                "lead_min": L, "limiar_nome": nome, "limiar": thr,
                "n_pos_alvo": n_pos, "recall": round(rec, 4), "precision": round(prec, 4),
                "n_alertas": n_alert, "n_DGs_antecipados_pegos": n_caught,
            })
            print(f"  L={L}min | {nome:<12} (thr={thr:<5}): "
                  f"recall={rec:.3f} | precision={prec:.3f} | "
                  f"alertas={n_alert:,} | pega {n_caught:,}/{n_pos:,} dos DGs antecipados")
        print("-" * 80)

    pl.from_dicts(linhas).write_csv(ARQ_TAB)
    print(f"Salvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # --- figura: recall e precision vs limiar, foco em L=90 ---
    c90 = curvas[90]
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    ax.plot(c90["thr"], c90["rec"], "-", color="#2e7d32", linewidth=2.8,
            label="Recall @ L=90min (% dos DGs antecipados capturados)")
    ax.plot(c90["thr"], c90["prec"], "-", color="#c62828", linewidth=2.8,
            label="Precision @ L=90min (% dos alertas que são reais)")
    ax.plot(curvas[120]["thr"], curvas[120]["rec"], "--", color="#66bb6a",
            linewidth=1.8, alpha=0.8, label="Recall @ L=120min")

    cores = {"Amarelo Q6": "#f9a825", "Vermelho Q6": "#c62828", "Padrão": "#455a64"}
    for nome, thr in THRESH_OP.items():
        ax.axvline(thr, color=cores[nome], linestyle=":", linewidth=1.6, alpha=0.8)
        # recall nesse limiar (L=90)
        idx = int(np.argmin(np.abs(c90["thr"] - thr)))
        ax.annotate(f"{nome}\n(thr={thr})\nrecall={c90['rec'][idx]:.0%}",
                    xy=(thr, 0.02), xytext=(thr + 0.01, 0.06),
                    fontsize=8.5, color=cores[nome], fontweight="bold")

    ax.set_xlabel("Limiar de decisão (corte da nota do modelo)", fontsize=12)
    ax.set_ylabel("Métrica no test (jun/2025)", fontsize=12)
    ax.set_title(
        "Figura Extra K — A partir de qual limiar a antecipação de 90 min se realiza\n"
        "Alvo: existe DG em [t+90min, t+4h]? Quanto menor o corte, mais avisos precoces, menor precisão.",
        fontsize=11.5, fontweight="bold")
    ax.set_xlim(0, 0.8)
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9.5)
    plt.tight_layout()
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")

    print()
    print("=" * 80)
    print("LEITURA")
    print("=" * 80)
    r_amar = next(l for l in linhas if l["lead_min"] == 90 and l["limiar_nome"] == "Amarelo Q6")
    r_verm = next(l for l in linhas if l["lead_min"] == 90 and l["limiar_nome"] == "Vermelho Q6")
    r_pad = next(l for l in linhas if l["lead_min"] == 90 and l["limiar_nome"] == "Padrão")
    print(f"  Para capturar DGs com >= 90 min de antecedencia:")
    print(f"    Padrao 0,50 : recall {r_pad['recall']:.0%} (perde a maioria dos avisos precoces)")
    print(f"    Vermelho 0,30: recall {r_verm['recall']:.0%}, precision {r_verm['precision']:.0%}")
    print(f"    Amarelo 0,145: recall {r_amar['recall']:.0%}, precision {r_amar['precision']:.0%} "
          f"(capta mais avisos precoces, mais alarme falso)")
    print("=" * 80)


if __name__ == "__main__":
    main()
