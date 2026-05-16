"""
exploracao_w2_obs.py - Investigacao das 3 observacoes pendentes de W2.

Le `Projeto/dados/intermediarios/telemetria_limpa.parquet` uma unica vez e
executa em sequencia as 3 investigacoes herdadas de
`Projeto/relatorio/observacoes_importantes.md`:

  - Obs 2.2: `Informacional` continua sendo 0% de DGs no semestre completo?
  - Obs 2.1: Top 5 alarmes ainda concentram ~88% dos DGs no semestre?
  - Obs 2.5: 504 DGs com `Nao_Critico` (acumulacao) se mantem na proporcao?

Apenas imprime no terminal - nao escreve em disco. As conclusoes serao
registradas manualmente em `PLANEJAMENTO.md` (Observacoes e Conclusoes W2)
e o status `[ ]` -> `[x]` atualizado em `observacoes_importantes.md`.

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/exploracao_w2_obs.py
"""
from pathlib import Path
import time

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
ARQ_TELEMETRIA = ROOT / "dados" / "intermediarios" / "telemetria_limpa.parquet"


def carregar() -> pl.DataFrame:
    print(f"\n[1/4] Carregando {ARQ_TELEMETRIA.relative_to(ROOT)}")
    if not ARQ_TELEMETRIA.exists():
        raise FileNotFoundError(
            f"{ARQ_TELEMETRIA} nao encontrado. Rode 03_limpeza.py primeiro."
        )
    t0 = time.time()
    df = pl.read_parquet(ARQ_TELEMETRIA)
    total_dgs = df.get_column("Is_Dont_Go").sum()
    print(
        f"  {df.shape[0]:>10,} linhas x {df.shape[1]:>2} colunas  "
        f"({time.time()-t0:.1f}s)"
    )
    print(f"  Total de DGs no semestre: {total_dgs:,}")
    return df


def obs_2_2_informacional_dgs(df: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("[2/4] OBS 2.2 - DGs por Criticidade no semestre (jan-jun/2025)")
    print("=" * 70)
    print(
        "Hipotese: 'Informacional' continua gerando 0 DGs (como em janeiro)?\n"
        "Se sim, justifica filtrar Informacional em W3 (economia ~98% volume)."
    )

    resumo = (
        df.group_by("Criticidade")
          .agg(
              pl.len().alias("total_eventos"),
              pl.col("Is_Dont_Go").sum().alias("total_DGs"),
          )
          .with_columns([
              (pl.col("total_DGs") / pl.col("total_eventos") * 100)
                .round(4).alias("taxa_DG_pct"),
              (pl.col("total_eventos") / df.height * 100)
                .round(2).alias("pct_volume"),
          ])
          .sort("total_eventos", descending=True)
    )
    print()
    print(resumo)


def obs_2_1_top_alarmes(df: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("[3/4] OBS 2.1 - Top alarmes que geram DGs no semestre")
    print("=" * 70)
    print(
        "Hipotese: Top 5 alarmes ainda concentram ~88% dos DGs (como em janeiro)?\n"
        "Se sim, foca feature engineering nesses 5 (vs 4402 alarmes unicos)."
    )

    dgs = df.filter(pl.col("Is_Dont_Go") == 1)
    total_dg = dgs.height

    top10 = (
        dgs.group_by("Alarme")
           .agg(pl.len().alias("n_DGs"))
           .sort("n_DGs", descending=True)
           .head(10)
           .with_columns(
               (pl.col("n_DGs") / total_dg * 100).round(2).alias("pct_DGs")
           )
           .with_columns(
               pl.col("pct_DGs").cum_sum().round(2).alias("pct_acum")
           )
    )
    print(f"\nTotal de DGs no semestre: {total_dg:,}")
    print(f"Alarmes distintos que geraram >= 1 DG: {dgs['Alarme'].n_unique():,}")
    print()
    print(top10)

    top5_sum = top10.head(5).get_column("n_DGs").sum()
    print(
        f"\nTop 5 concentra: {top5_sum:,} DGs = {top5_sum/total_dg*100:.1f}% "
        f"(vs 88% em janeiro)"
    )


def obs_2_5_nao_critico_acumulacao(df: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("[4/4] OBS 2.5 - Distribuicao dos DGs por Criticidade")
    print("=" * 70)
    print(
        "Hipotese: 'Nao_Critico' mantem proporcao relevante dos DGs (era ~20% em\n"
        "janeiro = 504 DGs). Esses sao DGs gerados por acumulacao (regra CMA\n"
        "QTD > 1), justificando rolling windows como feature dominante em W4."
    )

    dgs = df.filter(pl.col("Is_Dont_Go") == 1)
    total_dg = dgs.height

    dist = (
        dgs.group_by("Criticidade")
           .agg(pl.len().alias("n_DGs"))
           .sort("n_DGs", descending=True)
           .with_columns(
               (pl.col("n_DGs") / total_dg * 100).round(2).alias("pct_DGs")
           )
    )
    print()
    print(dist)

    print(f"\nTotal DGs: {total_dg:,}")
    print("\nComparacao com janeiro (relatorio inicial):")
    print("  Critico:     80% | Nao_Critico:     20% (504 DGs)")


def main() -> None:
    print("=== Exploracao W2 - Observacoes pendentes ===")
    df = carregar()
    obs_2_2_informacional_dgs(df)
    obs_2_1_top_alarmes(df)
    obs_2_5_nao_critico_acumulacao(df)
    print("\n[OK] Exploracao concluida.")
    print(
        "\nProximo passo: atualizar `observacoes_importantes.md` (marcar [x]) e "
        "mover conclusoes para `PLANEJAMENTO.md` -> 'Observacoes e Conclusoes (W2)'."
    )


if __name__ == "__main__":
    main()
