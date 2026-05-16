"""
exploracao_w2_obs.py - Investigacao das observacoes pendentes de W2.

Le `Projeto/dados/intermediarios/telemetria_limpa.parquet` uma unica vez e
executa em sequencia as investigacoes herdadas de
`Projeto/relatorio/observacoes_importantes.md`:

  - Obs 2.2: `Informacional` continua sendo 0% de DGs no semestre completo?
  - Obs 2.1: Top 5 alarmes ainda concentram ~88% dos DGs no semestre?
  - Obs 2.5: 504 DGs com `Nao_Critico` (acumulacao) se mantem na proporcao?
  - Obs 2.6: Salto de 20% -> 48% Nao_Critico e' tendencia, pico, ou platô?
  - Obs 2.6 (extensao): Qual alarme puxou o pico de 4.845 DGs Critico em junho?
  - Obs 2.7: Posicao relativa dos 2.525 DGs em Manutencao - 3 hipoteses

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
ARQ_APONTAMENTOS = (
    ROOT / "Alterado" / "Base de Dados" / "datasets" / "apontamentos"
    / "desenvolver_apontamentos.parquet"
)


def carregar() -> pl.DataFrame:
    print(f"\n[1/7] Carregando {ARQ_TELEMETRIA.relative_to(ROOT)}")
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
    print("[2/7] OBS 2.2 - DGs por Criticidade no semestre (jan-jun/2025)")
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
    print("[3/7] OBS 2.1 - Top alarmes que geram DGs no semestre")
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
    print("[4/7] OBS 2.5 - Distribuicao dos DGs por Criticidade")
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


def obs_2_6_nao_critico_mensal(df: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("[5/7] OBS 2.6 - Distribuicao mensal dos DGs Nao_Critico")
    print("=" * 70)
    print(
        "Hipotese: O salto de 20% (jan) para 48% (semestre) na proporcao de\n"
        "Nao_Critico nos DGs e' tendencia crescente, pico em mes especifico,\n"
        "ou plato apos mudanca estrutural? Conexao com Risco 3.2 (drift)."
    )

    dgs = df.filter(pl.col("Is_Dont_Go") == 1)
    nomes_meses = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun"}

    # ----- 1. Distribuicao mensal absoluta + proporcao -----
    mensal = (
        dgs.with_columns(pl.col("Data_Evento").dt.month().alias("mes"))
           .group_by(["mes", "Criticidade"])
           .agg(pl.len().alias("n"))
           .pivot(index="mes", on="Criticidade", values="n")
           .fill_null(0)
           .sort("mes")
    )
    if "Critico" not in mensal.columns:
        mensal = mensal.with_columns(pl.lit(0).alias("Critico"))
    if "Nao_Critico" not in mensal.columns:
        mensal = mensal.with_columns(pl.lit(0).alias("Nao_Critico"))

    mensal = (
        mensal.with_columns(
            (pl.col("Critico") + pl.col("Nao_Critico")).alias("total"),
        )
        .with_columns(
            (pl.col("Nao_Critico") / pl.col("total") * 100)
              .round(2).alias("pct_nao_crit"),
        )
        .select(["mes", "Critico", "Nao_Critico", "total", "pct_nao_crit"])
    )

    print("\nDistribuicao mensal de DGs:")
    print(mensal)

    # ----- 2. Trajetoria mes-a-mes da proporcao -----
    pcts = mensal["pct_nao_crit"].to_list()
    meses = mensal["mes"].to_list()

    print("\nTrajetoria do %Nao_Critico (mes a mes):")
    for i, (m, p) in enumerate(zip(meses, pcts)):
        nome = nomes_meses.get(m, str(m))
        if i == 0:
            print(f"  {nome}: {p:>5.1f}%  (base)")
        else:
            delta = p - pcts[i-1]
            seta = "+" if delta > 0 else ("-" if delta < 0 else "=")
            print(f"  {nome}: {p:>5.1f}%  ({seta}{abs(delta):.1f}pp vs mes anterior)")

    # ----- 3. Volumes absolutos com barra ASCII -----
    nc_vals = mensal["Nao_Critico"].to_list()
    nc_max = max(nc_vals) if nc_vals else 1
    print("\nVolume absoluto de DGs Nao_Critico por mes (barra escalada ao maximo):")
    for m, v in zip(meses, nc_vals):
        nome = nomes_meses.get(m, str(m))
        barra = "#" * int(v / nc_max * 40) if nc_max > 0 else ""
        print(f"  {nome}: {v:>5,}  {barra}")

    # ----- 4. Decomposicao por top 5 alarmes Nao_Critico -----
    top5_alarmes_nc = (
        dgs.filter(pl.col("Criticidade") == "Nao_Critico")
           .group_by("Alarme")
           .agg(pl.len().alias("n"))
           .sort("n", descending=True)
           .head(5)
           .get_column("Alarme")
           .to_list()
    )

    cross_alarme = (
        dgs.filter(
                (pl.col("Criticidade") == "Nao_Critico") &
                (pl.col("Alarme").is_in(top5_alarmes_nc))
            )
            .with_columns(pl.col("Data_Evento").dt.month().alias("mes"))
            .group_by(["Alarme", "mes"])
            .agg(pl.len().alias("n"))
            .pivot(index="Alarme", on="mes", values="n")
            .fill_null(0)
    )

    print("\nTop 5 alarmes Nao_Critico decompostos por mes:")
    with pl.Config(tbl_cols=10, fmt_str_lengths=45):
        print(cross_alarme)

    # ----- 5. Resumo interpretativo -----
    print("\nInterpretacao - olhar o output acima:")
    print("  - Trajetoria monotonica (sempre subindo/quase) -> drift estrutural")
    print("  - Pico em 1-2 meses + queda -> evento pontual (mudanca regra, sazonal)")
    print("  - Volume absoluto + decomposicao por alarme -> qual alarme 'puxa'")


def obs_2_6_extensao_critico_junho(df: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("[6/7] OBS 2.6 EXTENSAO - Decomposicao do pico Critico de junho")
    print("=" * 70)
    print(
        "Contexto: junho teve 4.845 DGs Critico - 2,3x janeiro, 7x maio.\n"
        "Pergunta: qual alarme puxou esse pico? E aparece em outros meses?"
    )

    dgs_critico = (
        df.filter(pl.col("Is_Dont_Go") == 1)
          .filter(pl.col("Criticidade") == "Critico")
          .with_columns(pl.col("Data_Evento").dt.month().alias("mes"))
    )

    # Top alarmes Critico em junho
    junho = (
        dgs_critico.filter(pl.col("mes") == 6)
                   .group_by("Alarme")
                   .agg(pl.len().alias("n"))
                   .sort("n", descending=True)
    )
    total_junho = junho.get_column("n").sum()
    junho_top = (
        junho.head(10)
             .with_columns((pl.col("n") / total_junho * 100).round(2).alias("pct"))
             .with_columns(pl.col("pct").cum_sum().round(2).alias("pct_acum"))
    )

    print(f"\nTotal DGs Critico em junho: {total_junho:,}")
    print("\nTop 10 alarmes Critico em junho:")
    with pl.Config(fmt_str_lengths=45):
        print(junho_top)

    # Comparacao: como esses mesmos alarmes se distribuem nos 6 meses
    alarmes_top_junho = junho_top.get_column("Alarme").to_list()
    comparacao = (
        dgs_critico.filter(pl.col("Alarme").is_in(alarmes_top_junho))
                   .group_by(["Alarme", "mes"])
                   .agg(pl.len().alias("n"))
                   .pivot(index="Alarme", on="mes", values="n")
                   .fill_null(0)
    )

    print("\nMesmos alarmes ao longo dos 6 meses (jan=col '1', ..., jun=col '6'):")
    with pl.Config(tbl_cols=12, fmt_str_lengths=45, tbl_rows=15):
        print(comparacao)

    # Quantificacao do salto: jun vs media dos outros meses
    print("\nSalto em junho vs media dos meses jan-mai:")
    for row in comparacao.iter_rows(named=True):
        alarme = row["Alarme"]
        jun = int(row.get("6", 0) or 0)
        outros = [int(row.get(str(m), 0) or 0) for m in (1, 2, 3, 4, 5)]
        media_outros = sum(outros) / 5
        if media_outros < 1:
            salto_str = "infinito (~0 antes)"
        else:
            salto_str = f"{jun / media_outros:.1f}x"
        print(
            f"  {alarme[:48]:<48} jun={jun:>5,}  "
            f"media jan-mai={media_outros:>6.1f}  salto={salto_str}"
        )

    print("\nInterpretacao - olhar o output acima:")
    print("  - Se 1 alarme concentra > 60% do junho Critico = anomalia focada")
    print("  - Se distribuicao difusa entre 5+ alarmes = problema sistemico")
    print("  - Comparar com top Nao_Critico de fev-mar (Engine Coolant): mesmo")
    print("    alarme? Outro? Conta historia de 2 anomalias diferentes ou da")
    print("    mesma causa em fases distintas?")


def obs_2_7_manutencao_posicao_relativa(df: pl.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("[7/7] OBS 2.7 - Posicao relativa dos DGs em estado Manutencao")
    print("=" * 70)
    print(
        "Contexto: 12,65% dos DGs (2.525) ocorreram em estado Manutencao.\n"
        "Diferenciar 3 hipoteses pela posicao relativa de Data_Evento dentro\n"
        "do intervalo [Inicio, Fim] do ciclo de apontamento:\n"
        "  - Massa perto de 0 -> H1 (DG causou transicao -> vira feature W4)\n"
        "  - Distribuicao uniforme -> H2 (falsos positivos de bancada -> filtrar)\n"
        "  - Concentracao em alarmes de diagnostico -> H3 (bug CMA)"
    )

    if not ARQ_APONTAMENTOS.exists():
        raise FileNotFoundError(f"{ARQ_APONTAMENTOS} nao encontrado.")
    apo = pl.read_parquet(ARQ_APONTAMENTOS)

    # Refaz o mesmo join temporal de tabela_q4() em 04_eda.py
    dgs = df.filter(pl.col("Is_Dont_Go") == 1).sort("Data_Evento")
    apo_para_join = (
        apo.select(["Tag", "Inicio", "Fim", "Classe"])
           .rename({"Classe": "Classe_estado"})
           .with_columns([
               pl.col("Inicio").dt.cast_time_unit("us"),
               pl.col("Fim").dt.cast_time_unit("us"),
           ])
           .sort("Inicio")
    )
    joined = dgs.join_asof(
        apo_para_join,
        left_on="Data_Evento",
        right_on="Inicio",
        by_left="TAG",
        by_right="Tag",
        strategy="backward",
    )

    # Filtra os DGs em Manutencao com casamento valido
    dgs_manut = joined.filter(
        (pl.col("Classe_estado") == "Manutenção")
        & pl.col("Inicio").is_not_null()
        & (pl.col("Data_Evento") <= pl.col("Fim"))
    )

    print(f"\nDGs em estado Manutencao com casamento valido: {dgs_manut.height:,} "
          f"(esperado ~2.525)")

    # Posicao relativa (0 = inicio do ciclo, 1 = fim)
    dgs_manut = dgs_manut.with_columns([
        (pl.col("Data_Evento") - pl.col("Inicio"))
            .dt.total_seconds().alias("dt_inicio_seg"),
        (pl.col("Fim") - pl.col("Inicio"))
            .dt.total_seconds().alias("ciclo_total_seg"),
    ]).filter(
        pl.col("ciclo_total_seg") > 0
    ).with_columns(
        (pl.col("dt_inicio_seg") / pl.col("ciclo_total_seg"))
            .alias("posicao_relativa")
    )

    # Estatisticas
    print("\nEstatisticas de posicao_relativa (0=inicio do ciclo, 1=fim):")
    stats = dgs_manut.select(
        pl.col("posicao_relativa").min().round(4).alias("min"),
        pl.col("posicao_relativa").quantile(0.10).round(4).alias("p10"),
        pl.col("posicao_relativa").quantile(0.25).round(4).alias("p25"),
        pl.col("posicao_relativa").median().round(4).alias("mediana"),
        pl.col("posicao_relativa").quantile(0.75).round(4).alias("p75"),
        pl.col("posicao_relativa").quantile(0.90).round(4).alias("p90"),
        pl.col("posicao_relativa").max().round(4).alias("max"),
        pl.col("posicao_relativa").mean().round(4).alias("media"),
    )
    print(stats)

    # Histograma em 10 buckets de 10%
    total = dgs_manut.height
    buckets = (
        dgs_manut.with_columns(
            (pl.col("posicao_relativa") * 10)
              .floor().clip(0, 9).cast(pl.Int32).alias("bucket")
        )
        .group_by("bucket")
        .agg(pl.len().alias("n"))
        .sort("bucket")
    )

    print("\nDistribuicao por bucket de 10% (0-10%, 10-20%, ..., 90-100%):")
    pct_uniforme = 10.0  # se distribuicao uniforme, cada bucket teria 10%
    for row in buckets.iter_rows(named=True):
        b = row["bucket"]
        n = row["n"]
        pct = n / total * 100
        barra = "#" * int(pct * 2)
        flag = " <-- excesso" if pct > pct_uniforme * 2 else ""
        print(f"  {b*10:>3}-{(b+1)*10:>3}%: {n:>5,}  ({pct:>5.2f}%)  {barra}{flag}")

    # Cruzamento com Alarme (saber se sao alarmes de producao ou de bancada/bypass)
    print("\nTop 10 alarmes nos DGs em Manutencao:")
    top_alarmes = (
        dgs_manut.group_by("Alarme")
                 .agg(pl.len().alias("n"))
                 .sort("n", descending=True)
                 .head(10)
                 .with_columns((pl.col("n") / total * 100).round(2).alias("pct"))
    )
    with pl.Config(fmt_str_lengths=50):
        print(top_alarmes)

    # Comparar com top 5 producao do semestre
    top5_producao = [
        "Engine Coolant Level - Active",
        "Right Front Brake Temperature - Active",
        "Transmission Oil Level - Active",
        "Left Rear Brake Temperature - Active",
        "Aftercooler Level - Active",
    ]
    em_top5_producao = (
        dgs_manut.filter(pl.col("Alarme").is_in(top5_producao)).height
    )
    pct_em_top5 = em_top5_producao / total * 100
    print(f"\nDos {total:,} DGs em Manutencao:")
    print(f"  {em_top5_producao:,} ({pct_em_top5:.1f}%) sao do TOP 5 PRODUCAO "
          "(mesmos alarmes do semestre)")
    print(f"  {total - em_top5_producao:,} ({100-pct_em_top5:.1f}%) sao de outros "
          "alarmes (potencialmente de diagnostico/bancada)")

    print("\nInterpretacao - usar os buckets + top alarmes:")
    print("  - Bucket 0-10% concentra >40% dos casos -> H1 (DG causou transicao)")
    print("  - Cada bucket ~10% (distribuicao quase uniforme) -> H2 (bancada)")
    print("  - Top alarmes sao mesmos da producao (Engine Coolant, Brake) -> NAO e H3")
    print("  - Top alarmes sao 'Channel Forced', 'Limits Bypassed', etc -> H3 (bug)")


def main() -> None:
    print("=== Exploracao W2 - Observacoes pendentes ===")
    df = carregar()
    obs_2_2_informacional_dgs(df)
    obs_2_1_top_alarmes(df)
    obs_2_5_nao_critico_acumulacao(df)
    obs_2_6_nao_critico_mensal(df)
    obs_2_6_extensao_critico_junho(df)
    obs_2_7_manutencao_posicao_relativa(df)
    print("\n[OK] Exploracao concluida.")
    print(
        "\nProximo passo: atualizar `observacoes_importantes.md` (marcar [x]) e "
        "mover conclusoes para `PLANEJAMENTO.md` -> 'Observacoes e Conclusoes (W2)'."
    )


if __name__ == "__main__":
    main()
