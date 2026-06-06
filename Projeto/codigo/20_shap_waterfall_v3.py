# -*- coding: utf-8 -*-
"""
20_shap_waterfall_v3.py - Figura 12: SHAP waterfall de UMA predicao individual (CM 5.3).

Complementa as figuras globais (9c bar, 9d beeswarm) com a explicacao LOCAL de
uma unica predicao do v3 canonico: como cada feature empurrou o score daquele
evento especifico, partindo do valor base (log-odds medio) ate a predicao final.

CRITERIO DE SELECAO DO EVENTO (principiado, deterministico):
  - Verdadeiro positivo (target_4h == 1): houve DG real nas 4h seguintes
  - Faixa VERMELHA (p >= 0,30): o alerta canonico teria disparado (acerto)
  - TAG != CA65926: demonstra que o modelo generaliza para alem do equipamento
    dominante do test set (L10) - escolha honesta para o relatorio
  - Contribuicoes diversificadas: dentre os candidatos confiantes, escolhe aquele
    cuja feature #1 explica a MENOR fracao do empurrao positivo (historia rica,
    nao monopolizada por uma unica feature)

Entradas:
  - Projeto/dados/features/v3.parquet
  - Projeto/modelos/lightgbm_v2_no_cascade.txt (v3 canonico)

Saidas:
  - Projeto/relatorio/figuras/fig12_shap_waterfall_v3.png
  - Projeto/relatorio/tabelas/shap_waterfall_evento.csv (contribuicoes do evento)

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/20_shap_waterfall_v3.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import shap

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")
warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"

ARQ_FIG = ROOT / "relatorio" / "figuras" / "fig12_shap_waterfall_v3.png"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "shap_waterfall_evento.csv"

N_TEST = 71_089
TARGET = "target_4h"
THRESHOLD_OP = 0.30

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
N_FEATURES = len(FEATURES)
assert N_FEATURES == 34
CAT_FEATURES = ["turno", "estado_pre_evento"]

# faixa de confianca para o candidato: confiante mas realista (evita score saturado)
P_MIN_CANDIDATO = 0.60
P_MAX_CANDIDATO = 0.97
TOP_N_CANDIDATOS = 30  # avalia SHAP nos N TPs mais confiantes (nao-CA65926) na faixa


def preparar_X(test: pl.DataFrame) -> pd.DataFrame:
    pdf = test.select(FEATURES).to_pandas()
    X = pdf[FEATURES].copy()
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return X


def main() -> None:
    print("=" * 70)
    print("20_shap_waterfall_v3.py - Figura 12 (SHAP waterfall local, CM 5.3)")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    test = df.filter(pl.col("split") == "test")
    assert test.height == N_TEST
    print(f"\nTest set: n={test.height:,}")

    X = preparar_X(test)
    p = booster.predict(X)
    y = test[TARGET].to_numpy().astype(np.int8)
    tag = test["TAG"].to_numpy()

    # --- pool de candidatos: TP, faixa vermelha confiante, fora do CA65926 ---
    elegivel = (
        (y == 1)
        & (p >= P_MIN_CANDIDATO)
        & (p <= P_MAX_CANDIDATO)
        & (tag != "CA65926")
    )
    idx_elegiveis = np.where(elegivel)[0]
    print(f"\nVerdadeiros positivos (y=1) na faixa [{P_MIN_CANDIDATO}, "
          f"{P_MAX_CANDIDATO}] fora do CA65926: {len(idx_elegiveis):,}")
    if len(idx_elegiveis) == 0:
        raise RuntimeError("Nenhum candidato elegivel - revisar criterios.")

    # ordena por p desc e pega os TOP_N para avaliar diversidade via SHAP
    ordem = idx_elegiveis[np.argsort(p[idx_elegiveis])[::-1]]
    candidatos = ordem[:TOP_N_CANDIDATOS]

    explainer = shap.TreeExplainer(booster)
    base_value = explainer.expected_value
    if isinstance(base_value, (list, np.ndarray)):
        base_value = float(np.asarray(base_value).ravel()[-1])
    else:
        base_value = float(base_value)
    print(f"Valor base (E[f(x)] em log-odds): {base_value:.4f}")

    X_cand = X.iloc[candidatos]
    shap_cand_raw = explainer.shap_values(X_cand, check_additivity=False)
    shap_cand = (np.asarray(shap_cand_raw[1]) if isinstance(shap_cand_raw, list)
                 else np.asarray(shap_cand_raw))

    # diversidade: fracao do empurrao POSITIVO explicada pela feature #1.
    # menor = mais distribuido = waterfall mais rico para o relatorio.
    melhor_pos = None
    melhor_frac = 2.0
    for i in range(len(candidatos)):
        sv = shap_cand[i]
        pos = sv[sv > 0]
        if pos.size == 0:
            continue
        frac_top1 = pos.max() / pos.sum()
        if frac_top1 < melhor_frac:
            melhor_frac = frac_top1
            melhor_pos = i

    sel = int(candidatos[melhor_pos])
    shap_sel = shap_cand[melhor_pos]
    print(f"\nEvento selecionado: indice posicional test={melhor_pos} "
          f"(row global no test={sel})")
    print(f"  feature #1 explica {melhor_frac*100:.1f}% do empurrao positivo "
          f"(criterio de diversidade)")

    # --- metadados do evento escolhido ---
    ev = test[sel]
    tag_sel = ev["TAG"][0]
    data_sel = ev["Data_Evento"][0]
    alarme_sel = ev["Alarme"][0] if "Alarme" in ev.columns else "n/d"
    p_sel = float(p[sel])
    margin_sel = base_value + float(shap_sel.sum())
    print(f"  TAG={tag_sel} | Data={data_sel} | Alarme={alarme_sel}")
    print(f"  p(DG 4h)={p_sel:.4f} | margin log-odds={margin_sel:.4f} "
          f"| y_real={int(y[sel])}")

    # --- tabela de contribuicoes ---
    vals_evento = X.iloc[sel]
    linhas = []
    for j, feat in enumerate(FEATURES):
        v = vals_evento[feat]
        v_disp = str(v) if feat in CAT_FEATURES else (
            round(float(v), 4) if pd.notna(v) else None)
        linhas.append({
            "feature": feat,
            "valor_no_evento": v_disp,
            "shap_value": round(float(shap_sel[j]), 5),
            "abs_shap": round(abs(float(shap_sel[j])), 5),
        })
    tab = pl.from_dicts(linhas).sort("abs_shap", descending=True)
    tab = tab.with_columns(pl.lit(tag_sel).alias("tag"),
                           pl.lit(p_sel).alias("p_dg_4h"))
    ARQ_TAB.parent.mkdir(parents=True, exist_ok=True)
    tab.write_csv(ARQ_TAB)
    print(f"\nSalvo: {ARQ_TAB.relative_to(ROOT.parent)}")
    print("\nTop 8 contribuicoes (|SHAP|):")
    for row in tab.head(8).iter_rows(named=True):
        sinal = "+" if row["shap_value"] >= 0 else "-"
        print(f"  {sinal} {row['feature']:<38s} = {str(row['valor_no_evento']):>12s}"
              f"  (SHAP={row['shap_value']:+.4f})")

    # --- waterfall ---
    # O shap.plots.waterfall ja prefixa o valor numerico de `data` no rotulo
    # (ex: "322 = feature"). Para evitar duplicacao, os nomes vao SEM valor;
    # categoricas levam o rotulo legivel no proprio nome (string) e codigo em data.
    codes = {c: X[c].cat.codes for c in CAT_FEATURES}
    data_num = []
    for feat in FEATURES:
        if feat in CAT_FEATURES:
            data_num.append(float(codes[feat].iloc[sel]))
        else:
            v = vals_evento[feat]
            data_num.append(float(v) if pd.notna(v) else np.nan)
    data_num = np.asarray(data_num)

    feat_labels = []
    for feat in FEATURES:
        if feat in CAT_FEATURES:
            feat_labels.append(f"{feat} ({vals_evento[feat]})")
        else:
            feat_labels.append(feat)

    expl = shap.Explanation(
        values=shap_sel,
        base_values=base_value,
        data=data_num,
        feature_names=feat_labels,
    )

    plt.figure(figsize=(11, 8))
    shap.plots.waterfall(expl, max_display=14, show=False)
    plt.title(
        f"Figura 12 - Explicacao local de uma predicao (SHAP waterfall) - v3\n"
        f"TAG {tag_sel} | p(DG em 4h) = {p_sel:.3f} (faixa VERMELHA, acerto: DG real ocorreu)\n"
        f"valor base (log-odds) {base_value:.2f}  ->  f(x) {margin_sel:.2f}",
        fontsize=11, fontweight="bold", pad=14,
    )
    plt.tight_layout()
    plt.savefig(ARQ_FIG, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"\nSalvo: {ARQ_FIG.relative_to(ROOT.parent)}")
    print("\n" + "=" * 70)
    print("Figura 12 concluida.")
    print("=" * 70)


if __name__ == "__main__":
    main()
