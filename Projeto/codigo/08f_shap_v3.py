"""
08f_shap_v3.py - Analise SHAP do LightGBM v3 (modelo canonico promovido).

Variante de 08c_shap_v2.py aplicada ao v3 (`Projeto/modelos/lightgbm_v2_no_cascade.txt`),
modelo treinado em 08e_lightgbm_v2_no_cascade.py removendo `horas_desde_ultimo_DG`.

Apos a decisao D-promocao (24/05/2026), v3 e o modelo canonico do projeto.
Esta analise SHAP valida que a remocao da feature de cascata redistribuiu o
peso para sinais com semantica antecipativa (e nao concentrou em outra
"feature dominante" problematica).

PERGUNTAS:
  (1) RANKING GLOBAL: quais features dirigem o v3?
  (2) Concentracao: top 1 esta mais distribuido que no v2 (39.3%)?
  (3) Familia 4 (regimal) subiu no ranking sem `horas_desde_ultimo_DG`?
  (4) `horas_desde_ultimo_critico` herda parte do papel? (substituto plausivel)

ANALISES ESTRATIFICADAS (mesmas 3 dimensoes do v2 para comparabilidade):
  - CA65926 vs resto
  - categorias_conhecidas vs unknown
  - test completo

Entradas:
  - Projeto/dados/features/v3.parquet
  - Projeto/modelos/lightgbm_v2_no_cascade.txt

Saidas:
  - Projeto/modelos/shap_values_v3_test.npy (matriz SHAP completa [71.089 x 34])
  - Projeto/relatorio/tabelas/shap_global_v3.csv
  - Projeto/relatorio/tabelas/shap_estratificado_v3.csv
  - Projeto/relatorio/figuras/fig09c_shap_bar_v3.png
  - Projeto/relatorio/figuras/fig09d_shap_beeswarm_v3.png
  - Projeto/relatorio/figuras/fig10b_shap_dependence_top3_v3.png

Executar:
    uv run python Projeto/codigo/08f_shap_v3.py
"""
from pathlib import Path
import time
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

ARQ_SHAP_VALUES = ROOT / "modelos" / "shap_values_v3_test.npy"
ARQ_SHAP_GLOBAL = ROOT / "relatorio" / "tabelas" / "shap_global_v3.csv"
ARQ_SHAP_ESTRAT = ROOT / "relatorio" / "tabelas" / "shap_estratificado_v3.csv"
ARQ_FIG_BAR = ROOT / "relatorio" / "figuras" / "fig09c_shap_bar_v3.png"
ARQ_FIG_BEESWARM = ROOT / "relatorio" / "figuras" / "fig09d_shap_beeswarm_v3.png"
ARQ_FIG_DEPEND = ROOT / "relatorio" / "figuras" / "fig10b_shap_dependence_top3_v3.png"


LINHAS_ESPERADAS = 544_885
N_TEST = 71_089
TARGET = "target_4h"

# 34 features (sem `horas_desde_ultimo_DG`, alinhado com 08e_lightgbm_v2_no_cascade.py)
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


def carregar() -> tuple[pl.DataFrame, lgb.Booster]:
    print("Etapa 1/6 - Carregando v3.parquet + lightgbm_v2_no_cascade.txt...")
    if not ARQ_V3.exists():
        raise FileNotFoundError(f"v3.parquet ausente: {ARQ_V3}")
    if not ARQ_MODELO.exists():
        raise FileNotFoundError(
            f"lightgbm_v2_no_cascade.txt ausente: {ARQ_MODELO}. "
            "Execute 08e_lightgbm_v2_no_cascade.py antes."
        )
    df = pl.read_parquet(ARQ_V3)
    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    print(f"  v3.parquet: shape {df.shape}")
    print(f"  lightgbm_v3 (v2_no_cascade): {booster.num_trees()} arvores | "
          f"{booster.num_feature()} features")
    assert df.height == LINHAS_ESPERADAS
    assert booster.num_feature() == N_FEATURES
    return df, booster


def preparar_test(df: pl.DataFrame) -> tuple[pd.DataFrame, np.ndarray, pl.DataFrame]:
    print()
    print("Etapa 2/6 - Preparando test set (full, 71.089 eventos)...")
    test = df.filter(pl.col("split") == "test")
    assert test.height == N_TEST
    pdf = test.select(FEATURES + [TARGET]).to_pandas()
    y = pdf[TARGET].to_numpy().astype(np.int8)
    X = pdf[FEATURES].copy()
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    print(f"  X.shape = {X.shape}, y positives = {int(y.sum()):,}")
    return X, y, test


def computar_shap(booster: lgb.Booster, X: pd.DataFrame) -> np.ndarray:
    print()
    print("Etapa 3/6 - Computando SHAP values (TreeSHAP)...")
    t0 = time.time()
    explainer = shap.TreeExplainer(booster)
    shap_raw = explainer.shap_values(X, check_additivity=False)
    shap_arr = np.asarray(shap_raw[1]) if isinstance(shap_raw, list) else np.asarray(shap_raw)
    elapsed = time.time() - t0
    print(f"  Shape: {shap_arr.shape}")
    print(f"  Tempo: {elapsed:.1f}s")
    assert shap_arr.shape == (N_TEST, N_FEATURES)
    ARQ_SHAP_VALUES.parent.mkdir(parents=True, exist_ok=True)
    np.save(ARQ_SHAP_VALUES, shap_arr)
    mb = ARQ_SHAP_VALUES.stat().st_size / 1024 / 1024
    print(f"  Salvo: {ARQ_SHAP_VALUES.relative_to(ROOT.parent)} ({mb:.1f} MB)")
    return shap_arr


def ranking_global(shap_arr: np.ndarray) -> pl.DataFrame:
    print()
    print("Etapa 4/6 - Ranking global de importancia...")
    mean_abs_shap = np.abs(shap_arr).mean(axis=0)
    total = mean_abs_shap.sum()
    df_ranking = pl.from_dicts([
        {
            "rank": rank + 1,
            "feature": FEATURES[idx],
            "mean_abs_shap": round(float(mean_abs_shap[idx]), 6),
            "pct_total": round(float(mean_abs_shap[idx] / total * 100), 2),
        }
        for rank, idx in enumerate(np.argsort(mean_abs_shap)[::-1])
    ])
    df_ranking.write_csv(ARQ_SHAP_GLOBAL)
    print(f"  Salvo: {ARQ_SHAP_GLOBAL.relative_to(ROOT.parent)} "
          f"({df_ranking.height} features)")
    print()
    print("  Top 15 features (ranking global v3):")
    print(f"  {'rank':>4} | {'feature':<40s} | {'pct_total':>9s}")
    print(f"  {'-'*4} | {'-'*40} | {'-'*9}")
    for row in df_ranking.head(15).iter_rows(named=True):
        print(f"  {row['rank']:>4} | {row['feature']:<40s} | {row['pct_total']:>8.2f}%")
    return df_ranking


def analise_estratificada(shap_arr: np.ndarray, test: pl.DataFrame) -> pl.DataFrame:
    print()
    print("Etapa 5/6 - Analises estratificadas...")
    is_ca65926 = (test["TAG"] == "CA65926").to_numpy()
    is_tag_unknown = test["tag_freq"].to_numpy() == 0
    is_op_unknown = test["operador_freq"].to_numpy() == 0
    is_any_unknown = is_tag_unknown | is_op_unknown
    grupos = {
        "test_completo": np.ones(N_TEST, dtype=bool),
        "CA65926": is_ca65926,
        "resto_test (sem CA65926)": ~is_ca65926,
        "categorias_conhecidas (treino)": ~is_any_unknown,
        "categorias_unknown (1.812 eventos)": is_any_unknown,
    }
    print()
    for nome, mask in grupos.items():
        print(f"  {nome:<40s}: {int(mask.sum()):>6,} eventos "
              f"({mask.sum()/N_TEST*100:5.2f}%)")

    linhas = []
    for nome_grupo, mask in grupos.items():
        sub_shap = shap_arr[mask]
        if sub_shap.shape[0] == 0:
            continue
        mean_abs = np.abs(sub_shap).mean(axis=0)
        total = mean_abs.sum()
        ranking = np.argsort(mean_abs)[::-1][:10]
        for rank, idx in enumerate(ranking, start=1):
            linhas.append({
                "subgrupo": nome_grupo,
                "n_eventos": int(mask.sum()),
                "rank": rank,
                "feature": FEATURES[idx],
                "mean_abs_shap": round(float(mean_abs[idx]), 6),
                "pct_total": round(float(mean_abs[idx] / total * 100), 2),
            })
    df_estrat = pl.from_dicts(linhas)
    df_estrat.write_csv(ARQ_SHAP_ESTRAT)
    print()
    print(f"  Salvo: {ARQ_SHAP_ESTRAT.relative_to(ROOT.parent)} "
          f"({df_estrat.height} linhas)")
    return df_estrat


def gerar_figuras(shap_arr: np.ndarray, X: pd.DataFrame, df_ranking: pl.DataFrame) -> None:
    print()
    print("Etapa 6/6 - Gerando figuras...")
    ARQ_FIG_BAR.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_arr, X, plot_type="bar", show=False,
                      max_display=15, feature_names=FEATURES)
    plt.title("Figura 9c - Importancia global das features (SHAP) - v3 canonico\n"
              "LightGBM sem horas_desde_ultimo_DG (test set: 71.089 eventos)",
              fontsize=12, fontweight="bold", pad=10)
    plt.xlabel("mean(|SHAP value|)", fontsize=11)
    plt.tight_layout()
    plt.savefig(ARQ_FIG_BAR, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG_BAR.relative_to(ROOT.parent)}")

    fig = plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_arr, X, show=False, max_display=15,
                      feature_names=FEATURES)
    plt.title("Figura 9d - Distribuicao dos SHAP values por feature - v3\n"
              "(cor = valor da feature: azul=baixo, vermelho=alto)",
              fontsize=12, fontweight="bold", pad=10)
    plt.xlabel("SHAP value (impact on model output)", fontsize=11)
    plt.tight_layout()
    plt.savefig(ARQ_FIG_BEESWARM, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG_BEESWARM.relative_to(ROOT.parent)}")

    top3 = df_ranking.head(3)["feature"].to_list()
    fig, axes = plt.subplots(3, 1, figsize=(11, 14))
    for ax, feat_name in zip(axes, top3):
        plt.sca(ax)
        shap.dependence_plot(feat_name, shap_arr, X, show=False,
                             ax=ax, feature_names=FEATURES,
                             interaction_index=None)
        rank_idx = df_ranking.filter(pl.col("feature") == feat_name)
        rank = rank_idx["rank"][0]
        pct = rank_idx["pct_total"][0]
        ax.set_title(f"#{rank}  -  {feat_name}  ({pct:.1f}% do peso global)",
                     fontsize=11, fontweight="bold", pad=8)
        ax.set_ylabel(f"SHAP value", fontsize=10)
        ax.set_xlabel(f"valor de {feat_name}", fontsize=10)
        ax.axhline(0, color="gray", linewidth=0.7, alpha=0.5, linestyle="--")
    fig.suptitle("Figura 10b - Dependence plots das 3 features mais importantes - v3\n"
                 "(como o valor da feature impacta a predicao)",
                 fontsize=13, fontweight="bold", y=0.995)
    plt.tight_layout()
    plt.savefig(ARQ_FIG_DEPEND, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG_DEPEND.relative_to(ROOT.parent)}")


def sumario(df_ranking: pl.DataFrame) -> None:
    print()
    print("=" * 70)
    print("SUMARIO ANALITICO v3 - 4 perguntas centrais")
    print("=" * 70)

    top10 = df_ranking.head(10)
    top1 = top10[0]
    top10_share = top10["pct_total"].sum()

    print()
    print(f"[Pergunta 1] Top 1 feature do v3:")
    print(f"  {top1['feature'][0]} ({top1['pct_total'][0]:.1f}% do total)")
    print(f"  Top 10 acumulam: {top10_share:.1f}%")

    print()
    print(f"[Pergunta 2] Concentracao reduziu vs v2?")
    print(f"  v2 Top 1: horas_desde_ultimo_DG (39.3%)")
    print(f"  v3 Top 1: {top1['feature'][0]} ({top1['pct_total'][0]:.1f}%)")
    if float(top1['pct_total'][0]) < 39.3:
        print(f"  -> SIM, concentracao reduziu em {39.3 - float(top1['pct_total'][0]):.1f}pp")
    else:
        print(f"  -> NAO, concentracao manteve ou aumentou (potencial nova feature dominante)")

    print()
    print(f"[Pergunta 3] Familia 4 regimal subiu?")
    razao_alarme_rank = df_ranking.filter(
        pl.col("feature") == "razao_alarme_7d_vs_30d_anterior"
    )["rank"][0]
    razao_sev_rank = df_ranking.filter(
        pl.col("feature") == "razao_severidade_14d_vs_60d"
    )["rank"][0]
    print(f"  razao_alarme_7d_vs_30d_anterior: rank #{razao_alarme_rank} (v2: #3)")
    print(f"  razao_severidade_14d_vs_60d:     rank #{razao_sev_rank}")

    print()
    print(f"[Pergunta 4] `horas_desde_ultimo_critico` herda papel da feature removida?")
    hduc_rank = df_ranking.filter(
        pl.col("feature") == "horas_desde_ultimo_critico"
    )
    if hduc_rank.height > 0:
        print(f"  horas_desde_ultimo_critico: rank #{hduc_rank['rank'][0]} "
              f"({hduc_rank['pct_total'][0]:.1f}% do total)")


def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("08f_shap_v3.py - Analise SHAP do LightGBM v3 (canonico promovido)")
    print("=" * 70)

    df, booster = carregar()
    X, y, test = preparar_test(df)
    shap_arr = computar_shap(booster, X)
    df_ranking = ranking_global(shap_arr)
    df_estrat = analise_estratificada(shap_arr, test)
    gerar_figuras(shap_arr, X, df_ranking)
    sumario(df_ranking)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
