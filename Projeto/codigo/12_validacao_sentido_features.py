"""
12_validacao_sentido_features.py - Validacao cruzada SHAP x Hazard Ratios.

Compara top features do LightGBM v3 (via SHAP) com top features do Weibull AFT
(via hazard ratios / time ratios). Concordancia entre dois metodos independentes
e evidencia forte de validade — material para CM 5.3 do relatorio.

Tres tecnicas independentes:
  - LightGBM v3 + TreeSHAP: Shapley values em gradient boosting
  - Weibull AFT (lifelines): maximum likelihood em modelo parametrico
  - Isolation Forest: anomaly detection nao-supervisionado (Etapa 3c por TAG)

Se as features importantes coincidem entre essas tres tecnicas com
fundamentacao matematica radicalmente diferente, isso e validacao forte
das estrategias aprendidas pelos modelos.

Entradas:
  - relatorio/tabelas/shap_global_v3.csv (34 features x mean|SHAP|)
  - relatorio/tabelas/sobrevivencia_hazard_ratios.csv (32 features x TR, IC, p)
  - relatorio/tabelas/if_auc_por_tag.csv (referencia adicional)

Saidas:
  - relatorio/tabelas/validacao_sentido_features.csv (tabela cruzada)

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/12_validacao_sentido_features.py
"""
from pathlib import Path
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
ARQ_SHAP = ROOT / "relatorio" / "tabelas" / "shap_global_v3.csv"
ARQ_HR = ROOT / "relatorio" / "tabelas" / "sobrevivencia_hazard_ratios.csv"
ARQ_OUT = ROOT / "relatorio" / "tabelas" / "validacao_sentido_features.csv"


def main() -> None:
    print("=" * 70)
    print("12_validacao_sentido_features.py - SHAP x Hazard Ratios")
    print("=" * 70)

    shap = pl.read_csv(ARQ_SHAP)
    hr = pl.read_csv(ARQ_HR)
    print(f"  SHAP v3: {shap.height} features")
    print(f"  Hazard Ratios (Weibull AFT): {hr.height} entries")

    # Filtrar HR para remover Intercept e renomear coluna covariate -> feature
    hr_clean = hr.filter(pl.col("covariate") != "Intercept").rename({
        "covariate": "feature",
        "time_ratio_TR": "weibull_TR",
        "TR_lower_95": "weibull_TR_lower_95",
        "TR_upper_95": "weibull_TR_upper_95",
        "p_valor": "weibull_p",
    })

    # Adicionar rank Weibull baseado em |log(TR)| (efeito absoluto, ignorando direcao)
    hr_clean = hr_clean.with_columns(
        pl.col("weibull_TR").log().abs().alias("log_TR_abs")
    ).sort("log_TR_abs", descending=True).with_row_index("weibull_rank", offset=1).drop("log_TR_abs")

    # Selecionar colunas relevantes do SHAP
    shap_clean = shap.select(["rank", "feature", "pct_total"]).rename({
        "rank": "shap_rank",
        "pct_total": "shap_pct_v3",
    })

    # Join externo (alguma features podem so estar em uma tabela)
    merged = shap_clean.join(
        hr_clean.select(["feature", "weibull_rank", "weibull_TR",
                        "weibull_TR_lower_95", "weibull_TR_upper_95", "weibull_p"]),
        on="feature",
        how="full",
    )

    # Limpeza pos-join (Polars cria coluna `feature_right` no full join)
    if "feature_right" in merged.columns:
        merged = merged.with_columns(
            pl.coalesce(["feature", "feature_right"]).alias("feature")
        ).drop("feature_right")

    # Adicionar coluna de interpretacao
    merged = merged.with_columns(
        pl.when(
            (pl.col("shap_rank") <= 10) & (pl.col("weibull_rank") <= 10)
        ).then(pl.lit("AMBOS top10"))
        .when(
            (pl.col("shap_rank") <= 10) & (pl.col("weibull_rank") > 10)
        ).then(pl.lit("SHAP top10 / Weibull discordante"))
        .when(
            (pl.col("shap_rank") > 10) & (pl.col("weibull_rank") <= 10)
        ).then(pl.lit("Weibull top10 / SHAP discordante"))
        .otherwise(pl.lit("nenhum top10"))
        .alias("concordancia"),
        # Direcao do efeito (Weibull TR < 1 = risco maior; SHAP nao tem direcao isolada
        # mas alto peso indica que feature importa)
        pl.when(pl.col("weibull_TR") < 1).then(pl.lit("RISCO MAIOR"))
        .when(pl.col("weibull_TR") > 1).then(pl.lit("RISCO MENOR"))
        .otherwise(pl.lit("n/a"))
        .alias("weibull_direcao"),
    ).sort("shap_rank", nulls_last=True)

    merged.write_csv(ARQ_OUT)
    print()
    print(f"  Salvo: {ARQ_OUT.relative_to(ROOT.parent)} ({merged.height} features)")

    # Resumo estatistico
    print()
    print("=" * 70)
    print("RESUMO DA VALIDACAO CRUZADA SHAP (v3) x HAZARD RATIOS (Weibull AFT)")
    print("=" * 70)

    ambos = merged.filter(pl.col("concordancia") == "AMBOS top10").height
    so_shap = merged.filter(pl.col("concordancia") == "SHAP top10 / Weibull discordante").height
    so_weibull = merged.filter(pl.col("concordancia") == "Weibull top10 / SHAP discordante").height

    print()
    print(f"  Features no top 10 de AMBOS:                  {ambos}")
    print(f"  Features so no top 10 do SHAP (v3 favorece):   {so_shap}")
    print(f"  Features so no top 10 do Weibull (HR favorece): {so_weibull}")

    print()
    print("  Tabela de concordancia (top 10 SHAP v3):")
    print(f"  {'rank_S':>6} | {'rank_W':>6} | {'feature':<40s} | "
          f"{'SHAP %':>7s} | {'Weibull TR':>10s} | {'concord':<20s}")
    print(f"  {'-'*6} | {'-'*6} | {'-'*40} | {'-'*7} | {'-'*10} | {'-'*20}")
    top10_shap = merged.filter(pl.col("shap_rank") <= 10).sort("shap_rank")
    for row in top10_shap.iter_rows(named=True):
        wr = f"#{row['weibull_rank']}" if row['weibull_rank'] is not None else "N/A"
        tr = f"{row['weibull_TR']:.3f}" if row['weibull_TR'] is not None else "N/A"
        sp = f"{row['shap_pct_v3']:.2f}%" if row['shap_pct_v3'] is not None else "N/A"
        concord = row['concordancia'] or "—"
        print(f"  {row['shap_rank']:>6} | {wr:>6} | {row['feature']:<40s} | "
              f"{sp:>7s} | {tr:>10s} | {concord:<20s}")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
