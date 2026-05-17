"""
exploracao_w3_sobreposicoes.py - Investigacao das 340 sobreposicoes de ciclo.

Achado de W3 (03_limpeza.py etapa 10): 340 ciclos de apontamento sobrepostos
no tempo dentro do mesmo equipamento (0.09% do total). Volume nao desprezivel,
abaixo do threshold de remocao automatica. Esta investigacao quantifica a
concentracao por:
  - Frota (793-D 5S/4S/3S/2S, LeTourneau L 1850)
  - TAG individual (equipamento especifico)
  - Tipo (Caminhao vs Escavadeira)
  - Classe (Operando/Parado/Manutencao/Hibernando)
  - Mes (jan-jun/2025)
  - Magnitude do overlap (minutos)

Objetivo: distinguir 'bug pontual em equipamento especifico' vs 'padrao
sistemico' (insight CM 6.1) vs 'ruido operacional aceitavel'.

Apenas le e imprime; nao altera nenhum arquivo. Conclusao manualmente
registrada em PLANEJAMENTO.md (Observacoes e Conclusoes W3).

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/exploracao_w3_sobreposicoes.py
"""
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
ARQ_APONTAMENTOS = ROOT / "dados" / "intermediarios" / "apontamentos_limpo.parquet"

N_SOBREPOSICOES_ESPERADO = 340


def carregar() -> pl.DataFrame:
    print(f"[1/7] Carregando {ARQ_APONTAMENTOS.relative_to(ROOT)}")
    if not ARQ_APONTAMENTOS.exists():
        raise FileNotFoundError(
            f"{ARQ_APONTAMENTOS} nao encontrado. Rode 03_limpeza.py primeiro."
        )
    df = pl.read_parquet(ARQ_APONTAMENTOS)
    print(f"  {df.shape[0]:,} linhas x {df.shape[1]} colunas")
    return df


def reconstruir_overlap(apo: pl.DataFrame) -> pl.DataFrame:
    """Recomputa Fim_anterior e duracao do overlap para as linhas flagadas."""
    print("\n[2/7] Reconstruindo magnitude do overlap")
    apo_sorted = apo.sort(["Tag", "Inicio"])
    apo_with_overlap = apo_sorted.with_columns(
        pl.col("Fim").shift(1).over("Tag").alias("Fim_anterior")
    ).with_columns(
        ((pl.col("Fim_anterior") - pl.col("Inicio"))
            .dt.total_seconds() / 60).alias("overlap_min")
    )
    sobrepoe = apo_with_overlap.filter(pl.col("is_sobreposicao"))
    assert sobrepoe.height == N_SOBREPOSICOES_ESPERADO, (
        f"Esperado {N_SOBREPOSICOES_ESPERADO} sobreposicoes, "
        f"obtido {sobrepoe.height}"
    )
    print(f"  {sobrepoe.height} sobreposicoes reconstruidas")
    print(f"  overlap_min: min={sobrepoe['overlap_min'].min():.1f}, "
          f"max={sobrepoe['overlap_min'].max():.1f}, "
          f"mediana={sobrepoe['overlap_min'].median():.1f}, "
          f"media={sobrepoe['overlap_min'].mean():.1f}")
    return sobrepoe


def magnitude_overlap(sobrepoe: pl.DataFrame) -> None:
    print("\n[3/7] Distribuicao da magnitude do overlap (minutos)")
    buckets = [
        ("0-1 min", 0, 1),
        ("1-10 min", 1, 10),
        ("10-60 min", 10, 60),
        ("1-6 h", 60, 360),
        ("6-24 h", 360, 1440),
        (">24 h", 1440, float("inf")),
    ]
    total = sobrepoe.height
    print(f"  {'Bucket':<12} {'n':>5}  {'%':>6}")
    for nome, lo, hi in buckets:
        n = sobrepoe.filter(
            (pl.col("overlap_min") >= lo) & (pl.col("overlap_min") < hi)
        ).height
        pct = 100 * n / total
        bar = "#" * int(pct * 0.6)
        print(f"  {nome:<12} {n:>5}  {pct:>5.1f}%  {bar}")


def por_frota(sobrepoe: pl.DataFrame, apo: pl.DataFrame) -> None:
    print("\n[4/7] Concentracao por Frota")
    total_sobrepoe = sobrepoe.height
    total_apo_por_frota = (
        apo.group_by("Frota").len().rename({"len": "total_frota"})
    )
    sob_por_frota = (
        sobrepoe.group_by("Frota").len().rename({"len": "n_sobrepoe"})
    )
    res = (
        sob_por_frota.join(total_apo_por_frota, on="Frota", how="left")
        .with_columns([
            (pl.col("n_sobrepoe") / total_sobrepoe * 100)
                .round(2).alias("pct_do_total_sobrepoe"),
            (pl.col("n_sobrepoe") / pl.col("total_frota") * 100)
                .round(4).alias("taxa_na_frota"),
        ])
        .sort("n_sobrepoe", descending=True)
    )
    print(res)


def por_tag(sobrepoe: pl.DataFrame, apo: pl.DataFrame) -> None:
    print("\n[5/7] Concentracao por TAG (equipamento) - top 15")
    total_sobrepoe = sobrepoe.height
    total_apo_por_tag = (
        apo.group_by("Tag").len().rename({"len": "total_tag"})
    )
    sob_por_tag = (
        sobrepoe.group_by("Tag").len().rename({"len": "n_sobrepoe"})
    )
    res = (
        sob_por_tag.join(total_apo_por_tag, on="Tag", how="left")
        .with_columns([
            (pl.col("n_sobrepoe") / total_sobrepoe * 100)
                .round(2).alias("pct_do_total"),
            (pl.col("n_sobrepoe") / pl.col("total_tag") * 100)
                .round(4).alias("taxa_na_tag"),
        ])
        .sort("n_sobrepoe", descending=True)
        .head(15)
    )
    with pl.Config(tbl_rows=20):
        print(res)

    n_tags_total = apo["Tag"].n_unique()
    n_tags_com_sobrepoe = sobrepoe["Tag"].n_unique()
    print(f"\n  TAGs com pelo menos 1 sobreposicao: {n_tags_com_sobrepoe}/{n_tags_total}")
    top5_sum = res.head(5)["n_sobrepoe"].sum()
    print(f"  Top 5 TAGs concentram: {top5_sum} de {total_sobrepoe} "
          f"({100*top5_sum/total_sobrepoe:.1f}%)")


def por_classe_tipo(sobrepoe: pl.DataFrame, apo: pl.DataFrame) -> None:
    print("\n[6/7] Concentracao por Tipo e Classe")

    # Tipo (Caminhao/Escavadeira)
    print("\n  Por Tipo:")
    total = sobrepoe.height
    res = (
        sobrepoe.group_by("Tipo").len()
        .rename({"len": "n"})
        .with_columns((pl.col("n") / total * 100).round(2).alias("pct"))
        .sort("n", descending=True)
    )
    print(res)

    # Classe (estado operacional)
    print("\n  Por Classe (estado operacional):")
    res = (
        sobrepoe.group_by("Classe").len()
        .rename({"len": "n"})
        .with_columns((pl.col("n") / total * 100).round(2).alias("pct"))
        .sort("n", descending=True)
    )
    print(res)


def por_mes(sobrepoe: pl.DataFrame) -> None:
    print("\n[7/7] Distribuicao mensal")
    total = sobrepoe.height
    res = (
        sobrepoe.with_columns(pl.col("Inicio").dt.month().alias("mes"))
        .group_by("mes").len()
        .rename({"len": "n"})
        .with_columns((pl.col("n") / total * 100).round(2).alias("pct"))
        .sort("mes")
    )
    print(res)


def diagnostico_final(sobrepoe: pl.DataFrame, apo: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("DIAGNOSTICO INTERPRETATIVO")
    print("=" * 70)

    total = sobrepoe.height
    n_tags_total = apo["Tag"].n_unique()
    n_tags_com_sob = sobrepoe["Tag"].n_unique()

    # Top TAG concentra X%?
    top_tag_n = (
        sobrepoe.group_by("Tag").len().sort("len", descending=True)
        .head(1)["len"][0]
    )
    pct_top1 = 100 * top_tag_n / total

    # Top 5 concentra Y%?
    top5_n = (
        sobrepoe.group_by("Tag").len().sort("len", descending=True)
        .head(5)["len"].sum()
    )
    pct_top5 = 100 * top5_n / total

    print(f"\nResumo de concentracao:")
    print(f"  TAGs envolvidas: {n_tags_com_sob}/{n_tags_total} "
          f"({100*n_tags_com_sob/n_tags_total:.1f}% das TAGs)")
    print(f"  Top 1 TAG: {pct_top1:.1f}% das sobreposicoes")
    print(f"  Top 5 TAGs: {pct_top5:.1f}% das sobreposicoes")

    print("\nClassificacao (heuristica):")
    if pct_top1 > 50:
        print(f"  >> BUG PONTUAL: 1 equipamento sozinho concentra {pct_top1:.1f}%")
    elif pct_top5 > 70:
        print(f"  >> CONCENTRADO: top 5 TAGs respondem por {pct_top5:.1f}%")
    elif n_tags_com_sob < 0.3 * n_tags_total:
        print(f"  >> SUBGRUPO LOCALIZADO: < 30% das TAGs envolvidas")
    else:
        print(f"  >> DIFUSO: distribuicao espalhada (provavel ruido operacional)")


def main() -> None:
    print("=== Investigacao das 340 sobreposicoes de ciclo (W3) ===")
    apo = carregar()
    sobrepoe = reconstruir_overlap(apo)
    magnitude_overlap(sobrepoe)
    por_frota(sobrepoe, apo)
    por_tag(sobrepoe, apo)
    por_classe_tipo(sobrepoe, apo)
    por_mes(sobrepoe)
    diagnostico_final(sobrepoe, apo)
    print("\n[OK] Investigacao concluida.")


if __name__ == "__main__":
    main()