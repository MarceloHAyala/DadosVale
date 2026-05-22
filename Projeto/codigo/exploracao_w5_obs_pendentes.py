"""
exploracao_w5_obs_pendentes.py - Resolucoes rapidas das Obs 2.4 e 2.9
                                  antes de iniciar a modelagem em W5.

Obs 2.4: O operador OP_067 (do caso paradigma CA65924) tem taxa de DG anormal?
         Resposta direta a Q3 do edital: comportamento do operador correlaciona
         com a ocorrencia de alertas DG?

Obs 2.9: Qual evento operacional disparou o pico de "Right Front Brake
         Temperature - Active" em junho/2025 (4.247-4.278 ocorrencias vs media
         28/mes jan-mai = ~150x baseline)? Foi:
           H_recapagem: recapagem em massa de pneus (afetando termoregulacao)
                        -> esperaria distribuicao espalhada por TAGs e
                           inicio sincronizado por equipamento
           H_sazonal:   sazonalidade termica (inicio do inverno em Itabira)
                        -> esperaria rampa gradual ao longo de junho
           H_sensor:    troca/recalibracao de sensor em lote
                        -> esperaria concentracao em TAGs especificas e
                           inicio abrupto em data especifica
           H_localizada:problema localizado em 1-2 TAGs (analogo a CA65789)
                        -> esperaria concentracao extrema (poucas TAGs)

Entradas:
  - Projeto/dados/features/v2_split.parquet (matriz canonica, 544.885 x 52)

Saidas:
  - Prints estruturados no terminal (analises descritivas das 2 obs)
  - Projeto/relatorio/tabelas/obs24_taxa_dg_por_operador.csv (CM 5.x — Q3)
  - Projeto/relatorio/tabelas/obs29_rfb_junho_decomposicao.csv (CM 6.2-6.3)

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/exploracao_w5_obs_pendentes.py
"""
from pathlib import Path
import time

import polars as pl


# ---------------------------------------------------------------------------
# Caminhos e constantes
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ARQ_V2_SPLIT = ROOT / "dados" / "features" / "v2_split.parquet"
ARQ_OBS24 = ROOT / "relatorio" / "tabelas" / "obs24_taxa_dg_por_operador.csv"
ARQ_OBS29 = ROOT / "relatorio" / "tabelas" / "obs29_rfb_junho_decomposicao.csv"

NOME_RFB = "Right Front Brake Temperature - Active"
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
N_OPERADORES_ESPERADO = 394


# ===========================================================================
# Obs 2.4 - Taxa de DG por operador (OP_067 e companhia)
# ===========================================================================
def obs_24(df: pl.DataFrame) -> None:
    print("=" * 70)
    print("Obs 2.4 - Taxa de DG por operador (OP_067 anomalo?)")
    print("=" * 70)

    # Estatistica por operador
    stats = (
        df.group_by("Nome_Operador_Anon")
        .agg(
            pl.len().alias("n_eventos"),
            (pl.col("Is_Dont_Go") == 1).sum().alias("n_dgs"),
        )
        .with_columns(
            (pl.col("n_dgs") / pl.col("n_eventos") * 100).round(3).alias("taxa_dg_pct")
        )
        .sort("taxa_dg_pct", descending=True)
    )

    n_op = stats.height
    print(f"\n[Universo] {n_op} operadores no dataset filtrado (esperado: {N_OPERADORES_ESPERADO})")
    assert n_op == N_OPERADORES_ESPERADO, f"Universo inesperado: {n_op}"

    # Sumario global
    taxa_global = (df.filter(pl.col("Is_Dont_Go") == 1).height / df.height) * 100
    print(f"\n[Baseline] Taxa global de DG no dataset filtrado: {taxa_global:.3f}%")
    print(f"           = {DGS_ESPERADOS:,} DGs / {LINHAS_ESPERADAS:,} eventos")

    # Distribuicao da taxa por operador
    print(f"\n[Distribuicao da taxa_dg_pct entre os {n_op} operadores]")
    quantiles_pct = [0.0, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0]
    descr = stats.select("taxa_dg_pct").to_series().describe()
    print(descr)
    for q in quantiles_pct:
        v = stats.select(
            pl.col("taxa_dg_pct").quantile(q, interpolation="linear")
        ).item()
        print(f"  q{int(q*100):>3d}%: {v:.3f}%")

    # OP_067 especifico
    op067 = stats.filter(pl.col("Nome_Operador_Anon") == "OP_067")
    if op067.height == 0:
        print("\n[OP_067] NAO ENCONTRADO no dataset filtrado.")
        return

    op067_taxa = op067.select("taxa_dg_pct").item()
    op067_dgs = op067.select("n_dgs").item()
    op067_n = op067.select("n_eventos").item()
    rank = stats.with_row_index("rank").filter(
        pl.col("Nome_Operador_Anon") == "OP_067"
    ).select("rank").item()
    # Como sort eh descending, rank=0 e' o maior; converter para "posicao do topo"
    pos = rank + 1
    pct_acima = (rank / n_op) * 100

    print(f"\n[OP_067 - operador do caso paradigma CA65924]")
    print(f"  Eventos: {op067_n:,}")
    print(f"  DGs:     {op067_dgs:,}")
    print(f"  Taxa:    {op067_taxa:.3f}%")
    print(f"  Rank:    #{pos} de {n_op} (top {pct_acima:.1f}% dos operadores com maior taxa)")
    print(f"  Vs baseline global ({taxa_global:.3f}%): "
          f"{op067_taxa/taxa_global:.2f}x")

    # Top 10 operadores por taxa
    print(f"\n[Top 10 operadores por taxa_dg_pct]")
    print(stats.head(10))

    # Top 10 operadores por volume absoluto de DGs (operadores mais expostos)
    print(f"\n[Top 10 operadores por VOLUME absoluto de DGs]")
    print(stats.sort("n_dgs", descending=True).head(10))

    # Existem operadores com taxa estatisticamente comparavel a OP_067?
    margem = op067_taxa * 0.5
    comparaveis = stats.filter(
        (pl.col("taxa_dg_pct") >= op067_taxa - margem) &
        (pl.col("taxa_dg_pct") <= op067_taxa + margem) &
        (pl.col("Nome_Operador_Anon") != "OP_067")
    ).height
    print(f"\n[Comparacao] Operadores com taxa em [{op067_taxa-margem:.2f}, {op067_taxa+margem:.2f}]%: {comparaveis}")

    # Persistir
    stats.write_csv(ARQ_OBS24)
    print(f"\n[Saida] {ARQ_OBS24.relative_to(ROOT.parent)} ({n_op} linhas)")


# ===========================================================================
# Obs 2.9 - Decomposicao do pico de Right Front Brake Temperature em junho
# ===========================================================================
def obs_29(df: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print(f"Obs 2.9 - Decomposicao do pico de RFB em junho/2025")
    print(f"          (alarme: '{NOME_RFB}')")
    print("=" * 70)

    rfb = df.filter(pl.col("Alarme") == NOME_RFB)
    rfb_jun = rfb.filter(pl.col("split") == "test")  # test = jun
    n_jun = rfb_jun.height
    print(f"\n[Universo] {n_jun:,} eventos RFB-Active em jun/2025")
    print(f"           Criticidade unica: {rfb_jun['Criticidade'].unique().to_list()}")
    print(f"           DGs entre estes:   {rfb_jun.filter(pl.col('Is_Dont_Go')==1).height:,}")

    # Comparativo com baseline historico jan-mai
    rfb_train = rfb.filter(pl.col("split").is_in(["train", "val"]))
    print(f"\n[Baseline histórico jan-mai] {rfb_train.height:,} eventos RFB-Active")
    rfb_por_mes_treino = (
        rfb_train.group_by(pl.col("Data_Evento").dt.month().alias("mes"))
        .agg(pl.len().alias("n"))
        .sort("mes")
    )
    print(rfb_por_mes_treino)
    media_mensal_train = rfb_train.height / 5.0
    salto = n_jun / media_mensal_train if media_mensal_train > 0 else float("inf")
    print(f"  Media jan-mai: {media_mensal_train:.1f} eventos/mes")
    print(f"  Salto jun vs media: {salto:.1f}x")

    # ---- Decomposicao por dia de junho ----
    print(f"\n[Decomposicao 1: distribuicao por DIA de junho]")
    por_dia = (
        rfb_jun.group_by(pl.col("Data_Evento").dt.day().alias("dia"))
        .agg(pl.len().alias("n"))
        .sort("dia")
    )
    print(por_dia)
    print(f"  Dias com >=1 evento: {por_dia.height} de 30")
    print(f"  Dia de maior volume: dia {por_dia.sort('n', descending=True)['dia'][0]} "
          f"com {por_dia['n'].max()} eventos")
    print(f"  Primeira ocorrencia em junho: dia {por_dia['dia'].min()}")

    # ---- Decomposicao por TAG ----
    print(f"\n[Decomposicao 2: distribuicao por TAG (equipamento)]")
    por_tag = (
        rfb_jun.group_by("TAG")
        .agg(pl.len().alias("n"))
        .with_columns(
            (pl.col("n") / n_jun * 100).round(2).alias("pct")
        )
        .sort("n", descending=True)
    )
    print(por_tag)
    n_tags_afetadas = por_tag.height
    print(f"  TAGs afetadas: {n_tags_afetadas} (de 30 TAGs no split de teste)")
    print(f"  TAG dominante: {por_tag['TAG'][0]} com {por_tag['n'][0]} eventos "
          f"({por_tag['pct'][0]}%)")
    top3_pct = por_tag.head(3)['pct'].sum()
    print(f"  Top 3 TAGs concentram: {top3_pct:.1f}%")

    # ---- Decomposicao por frota ----
    print(f"\n[Decomposicao 3: distribuicao por FROTA]")
    por_frota = (
        rfb_jun.group_by("Tag_Frota")
        .agg(pl.len().alias("n"))
        .with_columns(
            (pl.col("n") / n_jun * 100).round(2).alias("pct")
        )
        .sort("n", descending=True)
    )
    print(por_frota)

    # ---- Decomposicao por operador ----
    print(f"\n[Decomposicao 4: top 10 operadores que registraram RFB-Active em jun]")
    por_op = (
        rfb_jun.group_by("Nome_Operador_Anon")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .head(10)
    )
    print(por_op)
    n_ops_afetados = (
        rfb_jun.group_by("Nome_Operador_Anon").agg(pl.len()).height
    )
    print(f"  Total operadores envolvidos: {n_ops_afetados}")

    # ---- Padrao temporal: gradual rampa ou onset abrupto? ----
    print(f"\n[Diagnostico: gradual vs abrupto]")
    primeiros_5_dias = por_dia.filter(pl.col("dia") <= 5)["n"].sum()
    ultimos_5_dias = por_dia.filter(pl.col("dia") >= 26)["n"].sum()
    meio_jun = por_dia.filter((pl.col("dia") >= 6) & (pl.col("dia") <= 25))["n"].sum()
    print(f"  Volume nos primeiros 5 dias (01-05): {primeiros_5_dias} ({primeiros_5_dias/n_jun*100:.1f}%)")
    print(f"  Volume no meio do mes (06-25):       {meio_jun} ({meio_jun/n_jun*100:.1f}%)")
    print(f"  Volume nos ultimos 5 dias (26-30):   {ultimos_5_dias} ({ultimos_5_dias/n_jun*100:.1f}%)")

    # Onset abrupto se a maioria do volume cair logo nos primeiros dias
    # Rampa gradual se for distribuido uniforme ou crescente

    # ---- Veredito quantitativo das 4 hipoteses ----
    print(f"\n[VEREDITO sobre as 4 hipoteses]")
    print(f"  H_recapagem    -> esperaria muitas TAGs afetadas com onset proximo")
    print(f"  H_sazonal      -> esperaria rampa gradual; volume crescendo ao longo de jun")
    print(f"  H_sensor       -> esperaria poucas TAGs com onset abrupto em data unica")
    print(f"  H_localizada   -> esperaria 1-2 TAGs com >75% do volume")
    print(f"")
    print(f"  Evidencia:")
    print(f"    - TAGs afetadas: {n_tags_afetadas} de 30")
    print(f"    - Top 1 TAG: {por_tag['pct'][0]}% do volume")
    print(f"    - Top 3 TAGs: {top3_pct:.1f}% do volume")
    print(f"    - Frota dominante: {por_frota['Tag_Frota'][0]} ({por_frota['pct'][0]}%)")
    print(f"    - Dias com eventos: {por_dia.height}/30")
    print(f"    - Primeiros 5 dias: {primeiros_5_dias/n_jun*100:.1f}% do volume")

    # Persistir decomposicao em tabela longa
    # Concatenar dia/TAG/frota/operador em formato long
    parts = []
    for label, tbl in [
        ("dia", por_dia.rename({"dia": "valor"})),
        ("TAG", por_tag.rename({"TAG": "valor"})),
        ("frota", por_frota.rename({"Tag_Frota": "valor"})),
    ]:
        # Cast valor para String e selecionar colunas
        sub = tbl.with_columns(
            pl.lit(label).alias("dimensao"),
            pl.col("valor").cast(pl.String).alias("valor"),
        ).select(["dimensao", "valor", "n"])
        parts.append(sub)

    concat = pl.concat(parts)
    concat.write_csv(ARQ_OBS29)
    print(f"\n[Saida] {ARQ_OBS29.relative_to(ROOT.parent)} ({concat.height} linhas long-format)")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("Carregando v2_split.parquet...")
    df = pl.read_parquet(ARQ_V2_SPLIT)
    print(f"  Shape: {df.shape}\n")

    obs_24(df)
    obs_29(df)

    elapsed = time.time() - t_start
    print(f"\nConcluido em {elapsed:.1f}s")


if __name__ == "__main__":
    main()
