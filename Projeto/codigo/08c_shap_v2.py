"""
08c_shap_v2.py - Analise SHAP do LightGBM v2 (modelo canonico).

Computa SHAP values via TreeSHAP sobre o test set COMPLETO (71.089 eventos)
do modelo canonico v2 (`Projeto/modelos/lightgbm_v2.txt`). Responde 4 perguntas:

  (1) RANKING GLOBAL: quais features dirigem as predicoes do v2?
  (2) "MODELO SO REPLICA O BASELINE?" — se count_critico_4h dominar isolada,
      v2 e baseline glorificado. Esperamos diversidade.
  (3) OBS 2.11: count_critico_*h aparecem ACIMA de count_total_*h no ranking?
      (acumulo de criticidade > acumulo de volume — sub-hipotese de H5.2).
  (4) Familia 4 regimal no topo? (`razao_alarme_7d_vs_30d_anterior` desenhada
      para capturar a anomalia RFB do CA65926 — Obs 2.6 / 2.9 / H7.1).

ANALISES ESTRATIFICADAS (3 dimensoes):
  - CA65926 vs resto do test (Obs 2.9 / H7.1): modelo usa features diferentes?
  - TAGs/operadores unknown no treino vs conhecidos (estudo W5, 1.812 eventos):
    como o modelo extrapola para categorias nunca vistas?
  - Mai (val) vs Jun (test): apesar de v2 ter sido treinado em jan-abr,
    podemos rodar SHAP em val tambem para ver mudanca de importancia
    entre regimes distribuido (mai) e concentrado (jun).

NOTA SOBRE A AMOSTRA:
  Rodamos sobre o test COMPLETO (71.089 eventos), nao amostra estratificada.
  TreeSHAP em LightGBM com 199 arvores escala linearmente — tempo estimado
  ~1 min para test completo. Decisao registrada apos discussao de qualidade
  (usuario preferiu cobertura total a amostra reduzida).

Entradas:
  - Projeto/dados/features/v3.parquet
  - Projeto/modelos/lightgbm_v2.txt (modelo canonico salvo por 08b)

Saidas:
  - Projeto/modelos/shap_values_v2_test.npy (matriz SHAP completa
    [71.089 x 35], ~10 MB, formato NumPy para analise reproducivel)
  - Projeto/relatorio/tabelas/shap_global_v2.csv (35 features x mean|SHAP|)
  - Projeto/relatorio/tabelas/shap_estratificado_v2.csv (subgrupos x top 10)
  - Projeto/relatorio/figuras/fig09_shap_global.png (bar + beeswarm)
  - Projeto/relatorio/figuras/fig10_shap_dependence_top3.png (3 dependence plots)

Executar:
    uv run python Projeto/codigo/08c_shap_v2.py
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


# ===========================================================================
# Caminhos
# ===========================================================================
ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO_V2 = ROOT / "modelos" / "lightgbm_v2.txt"

ARQ_SHAP_VALUES = ROOT / "modelos" / "shap_values_v2_test.npy"
ARQ_SHAP_GLOBAL = ROOT / "relatorio" / "tabelas" / "shap_global_v2.csv"
ARQ_SHAP_ESTRAT = ROOT / "relatorio" / "tabelas" / "shap_estratificado_v2.csv"
ARQ_FIG_GLOBAL = ROOT / "relatorio" / "figuras" / "fig09_shap_global.png"
ARQ_FIG_DEPEND = ROOT / "relatorio" / "figuras" / "fig10_shap_dependence_top3.png"


# ===========================================================================
# Constantes (alinhadas com 08b_lightgbm_v2.py)
# ===========================================================================
LINHAS_ESPERADAS = 544_885
N_TEST = 71_089
TARGET = "target_4h"

FEATURES = [
    "hora_dia", "dia_semana", "turno", "mes", "valor_disponivel",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    "horas_desde_ultimo_DG", "horas_desde_ultimo_critico",
    "estado_pre_evento",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
]
N_FEATURES = len(FEATURES)
CAT_FEATURES = ["turno", "estado_pre_evento"]


# ===========================================================================
# Etapa 1 - Carregar v3.parquet + modelo v2
# ===========================================================================
def carregar() -> tuple[pl.DataFrame, lgb.Booster]:
    print("Etapa 1/6 - Carregando v3.parquet + lightgbm_v2.txt...")

    if not ARQ_V3.exists():
        raise FileNotFoundError(f"v3.parquet ausente: {ARQ_V3}")
    if not ARQ_MODELO_V2.exists():
        raise FileNotFoundError(
            f"lightgbm_v2.txt ausente: {ARQ_MODELO_V2}. "
            "Execute 08b_lightgbm_v2.py antes."
        )

    df = pl.read_parquet(ARQ_V3)
    booster = lgb.Booster(model_file=str(ARQ_MODELO_V2))

    print(f"  v3.parquet:    shape {df.shape}")
    print(f"  lightgbm_v2:   {booster.num_trees()} arvores | "
          f"{booster.num_feature()} features")
    assert df.height == LINHAS_ESPERADAS
    assert booster.num_feature() == N_FEATURES
    return df, booster


# ===========================================================================
# Etapa 2 - Preparar X, y do test set
# ===========================================================================
def preparar_test(df: pl.DataFrame) -> tuple[pd.DataFrame, np.ndarray, pl.DataFrame]:
    print()
    print("Etapa 2/6 - Preparando test set (full, 71.089 eventos)...")

    test = df.filter(pl.col("split") == "test")
    assert test.height == N_TEST

    pdf = test.select(FEATURES + [TARGET]).to_pandas()
    y = pdf[TARGET].to_numpy().astype(np.int8)
    X = pdf[FEATURES].copy()

    # Categoricals como pd.Categorical (igual ao treino em 08b_lightgbm_v2.py)
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)

    # Manter o test polars original para juntar com stratificacao depois
    print(f"  X.shape = {X.shape}, y positives = {int(y.sum()):,}")
    return X, y, test


# ===========================================================================
# Etapa 3 - Computar SHAP values via TreeSHAP
# ===========================================================================
def computar_shap(booster: lgb.Booster, X: pd.DataFrame) -> np.ndarray:
    print()
    print("Etapa 3/6 - Computando SHAP values (TreeSHAP)...")
    t0 = time.time()

    explainer = shap.TreeExplainer(booster)
    shap_raw = explainer.shap_values(X, check_additivity=False)

    # SHAP em binary LightGBM: pode retornar array unico (logit) ou
    # lista [neg, pos]. Padronizar para array [n, n_features].
    if isinstance(shap_raw, list):
        # Versao antiga: [neg, pos]; pegamos classe positiva
        shap_arr = np.asarray(shap_raw[1])
    else:
        shap_arr = np.asarray(shap_raw)

    elapsed = time.time() - t0
    print(f"  Shape: {shap_arr.shape}")
    print(f"  Tempo: {elapsed:.1f}s")
    assert shap_arr.shape == (N_TEST, N_FEATURES), (
        f"Esperado ({N_TEST}, {N_FEATURES}), obtido {shap_arr.shape}"
    )

    # Salvar matriz completa
    ARQ_SHAP_VALUES.parent.mkdir(parents=True, exist_ok=True)
    np.save(ARQ_SHAP_VALUES, shap_arr)
    mb = ARQ_SHAP_VALUES.stat().st_size / 1024 / 1024
    print(f"  Salvo: {ARQ_SHAP_VALUES.relative_to(ROOT.parent)} ({mb:.1f} MB)")

    return shap_arr


# ===========================================================================
# Etapa 4 - Ranking global de importancia
# ===========================================================================
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
    print("  Top 15 features (ranking global):")
    print(df_ranking.head(15))

    return df_ranking


# ===========================================================================
# Etapa 5 - Analises estratificadas (3 dimensoes)
# ===========================================================================
def analise_estratificada(shap_arr: np.ndarray, test: pl.DataFrame) -> pl.DataFrame:
    print()
    print("Etapa 5/6 - Analises estratificadas (3 dimensoes)...")

    # Mascaras booleanas
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

    # Diagnostico
    print()
    for nome, mask in grupos.items():
        print(f"  {nome:<40s}: {int(mask.sum()):>6,} eventos "
              f"({mask.sum()/N_TEST*100:5.2f}%)")

    # Para cada grupo, top 10 features
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
          f"({df_estrat.height} linhas: {len(grupos)} grupos x top 10)")

    # Print comparativo direto: top 5 de CA65926 vs resto
    print()
    print("  Comparativo direto — Top 5 features por subgrupo:")
    print(f"  {'rank':>4} | {'CA65926':<35s} | {'resto_test':<35s}")
    print(f"  {'-'*4} | {'-'*35} | {'-'*35}")
    ca_top5 = df_estrat.filter(pl.col("subgrupo") == "CA65926").head(5)
    resto_top5 = df_estrat.filter(pl.col("subgrupo") == "resto_test (sem CA65926)").head(5)
    for i in range(5):
        ca_feat = ca_top5["feature"][i]
        ca_pct = ca_top5["pct_total"][i]
        re_feat = resto_top5["feature"][i]
        re_pct = resto_top5["pct_total"][i]
        print(f"  {i+1:>4} | {ca_feat:<25s} ({ca_pct:5.1f}%) | "
              f"{re_feat:<25s} ({re_pct:5.1f}%)")

    return df_estrat


# ===========================================================================
# Etapa 6 - Figuras (beeswarm + dependence plots)
# ===========================================================================
def gerar_figuras(shap_arr: np.ndarray, X: pd.DataFrame, df_ranking: pl.DataFrame) -> None:
    print()
    print("Etapa 6/6 - Gerando figuras...")
    ARQ_FIG_GLOBAL.parent.mkdir(parents=True, exist_ok=True)

    # Fig 9 — global: bar + beeswarm em 2 paineis
    fig, axes = plt.subplots(1, 2, figsize=(15, 9))

    # Painel A: bar plot (mean |SHAP|)
    plt.sca(axes[0])
    shap.summary_plot(
        shap_arr, X, plot_type="bar", show=False, max_display=15,
        feature_names=FEATURES,
    )
    axes[0].set_title("(A) Importancia global — mean |SHAP|", fontsize=12)

    # Painel B: beeswarm
    plt.sca(axes[1])
    shap.summary_plot(
        shap_arr, X, show=False, max_display=15,
        feature_names=FEATURES,
    )
    axes[1].set_title("(B) Distribuicao dos SHAP values por feature", fontsize=12)

    fig.suptitle(
        "Figura 9 — Analise SHAP do LightGBM v2 (test set, 71.089 eventos)",
        fontsize=13, fontweight="bold", y=1.00,
    )
    plt.tight_layout()
    fig.savefig(ARQ_FIG_GLOBAL, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG_GLOBAL.relative_to(ROOT.parent)}")

    # Fig 10 — dependence plots das 3 features mais importantes
    top3 = df_ranking.head(3)["feature"].to_list()
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    for ax, feat_name in zip(axes, top3):
        plt.sca(ax)
        shap.dependence_plot(
            feat_name, shap_arr, X, show=False,
            ax=ax, feature_names=FEATURES,
            interaction_index=None,  # sem coloracao por feature secundaria
        )
        ax.set_title(f"{feat_name}", fontsize=11)
    fig.suptitle(
        "Figura 10 — Dependence plots das 3 features mais importantes",
        fontsize=13, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    fig.savefig(ARQ_FIG_DEPEND, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG_DEPEND.relative_to(ROOT.parent)}")


# ===========================================================================
# Sumario analitico final
# ===========================================================================
def sumario(df_ranking: pl.DataFrame, df_estrat: pl.DataFrame) -> None:
    print()
    print("=" * 70)
    print("SUMARIO ANALITICO — 4 perguntas centrais")
    print("=" * 70)

    top10 = df_ranking.head(10)
    top1 = top10[0]
    top10_share = top10["pct_total"].sum()

    print()
    print(f"[Pergunta 1] Ranking global — feature dominante?")
    print(f"  Top 1: {top1['feature'][0]} ({top1['pct_total'][0]:.1f}% do total)")
    print(f"  Top 10 acumulam: {top10_share:.1f}% do total")

    print()
    print(f"[Pergunta 2] v2 e 'baseline glorificado'?")
    if top1["feature"][0] == "count_critico_4h" and float(top1["pct_total"][0]) > 50:
        print(f"  ALERTA: count_critico_4h domina sozinho com {top1['pct_total'][0]:.1f}% — "
              f"v2 pode estar replicando baseline")
    else:
        print(f"  Top 1 nao e count_critico_4h ou nao domina sozinho — "
              f"diversidade de sinal preservada (v2 aprende alem do baseline)")

    print()
    print(f"[Pergunta 3] Obs 2.11 — count_critico_*h > count_total_*h?")
    crit_features = {f: df_ranking.filter(pl.col("feature") == f)
                     for f in FEATURES if f.startswith("count_critico_")}
    total_features = {f: df_ranking.filter(pl.col("feature") == f)
                      for f in FEATURES if f.startswith("count_total_")}
    for win in ["1h", "2h", "4h", "8h", "24h"]:
        c = crit_features[f"count_critico_{win}"]["rank"][0]
        t = total_features[f"count_total_{win}"]["rank"][0]
        veredito = "✓" if c < t else "✗"
        print(f"  janela {win}: count_critico (rank #{c}) vs count_total (rank #{t})  {veredito}")

    print()
    print(f"[Pergunta 4] Familia 4 regimal no topo?")
    razao_alarme_rank = df_ranking.filter(
        pl.col("feature") == "razao_alarme_7d_vs_30d_anterior"
    )["rank"][0]
    razao_sev_rank = df_ranking.filter(
        pl.col("feature") == "razao_severidade_14d_vs_60d"
    )["rank"][0]
    print(f"  razao_alarme_7d_vs_30d_anterior: rank #{razao_alarme_rank}")
    print(f"  razao_severidade_14d_vs_60d:    rank #{razao_sev_rank}")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("08c_shap_v2.py - Analise SHAP do LightGBM v2 canonico")
    print("=" * 70)

    df, booster = carregar()
    X, y, test = preparar_test(df)
    shap_arr = computar_shap(booster, X)
    df_ranking = ranking_global(shap_arr)
    df_estrat = analise_estratificada(shap_arr, test)
    gerar_figuras(shap_arr, X, df_ranking)
    sumario(df_ranking, df_estrat)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
