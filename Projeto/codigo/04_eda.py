"""
04_eda.py - EDA visual da W2.

Gera as figuras obrigatorias 2-6 do Estudo Guiado (CM 2.1-2.3), duas figuras
extras de Pareto (alarmes precursores e TAGs com mais DGs) e a tabela Q4
(DGs por Frota / Tipo / Classe).

Fig 1 (diagrama do fluxo operacional) NAO entra aqui - sera desenhada
manualmente em draw.io/PowerPoint depois das figuras data-driven prontas.

Convencoes seguidas:
  - `Path(__file__).resolve().parents[1]` para resolver caminhos relativos a Projeto/
  - Filtra `Criticidade = 'Informacional'` no inicio (decisao validada em W2 -
    ver controle_alteracoes.md, entrada de 2026-05-16)
  - matplotlib + seaborn (sem plotly) - exporta PNG limpo para Word
  - Asercoes finais: arquivos existem, sao nao-vazios, soma de DGs na tabela
    Q4 bate com TOTAL_DGS_ESPERADO

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/04_eda.py
"""
from pathlib import Path
import time

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ARQ_TELEMETRIA = ROOT / "dados" / "intermediarios" / "telemetria_limpa.parquet"
ARQ_APONTAMENTOS = (
    ROOT / "Alterado" / "Base de Dados" / "datasets" / "apontamentos"
    / "desenvolver_apontamentos.parquet"
)
DIR_FIGURAS = ROOT / "relatorio" / "figuras"
DIR_TABELAS = ROOT / "relatorio" / "tabelas"

ARQ_FIG2 = DIR_FIGURAS / "fig02_distribuicao_temporal_apontamentos.png"
ARQ_FIG3 = DIR_FIGURAS / "fig03_tipo_x_criticidade.png"
ARQ_FIG4 = DIR_FIGURAS / "fig04_serie_temporal_dgs.png"
ARQ_FIG5 = DIR_FIGURAS / "fig05_heatmap_correlacao.png"
ARQ_FIG6 = DIR_FIGURAS / "fig06_heatmap_hora_dia.png"
ARQ_FIG_EXB = DIR_FIGURAS / "figExB_pareto_alarmes.png"
ARQ_FIG_EXG = DIR_FIGURAS / "figExG_pareto_tags.png"
ARQ_TAB_Q4 = DIR_TABELAS / "dgs_por_frota_tipo_classe.csv"

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
TOTAL_DGS_ESPERADO = 19_962
DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]

COR_CRITICO = "#C73E1D"
COR_NAO_CRITICO = "#F18F01"
COR_NEUTRO = "#2E86AB"
COR_DESTAQUE = "#A23B72"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def configurar_tema() -> None:
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "font.family": "DejaVu Sans",
    })


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def carregar() -> tuple[pl.DataFrame, pl.DataFrame]:
    print("\n[1/11] Carregando telemetria_limpa.parquet")
    if not ARQ_TELEMETRIA.exists():
        raise FileNotFoundError(
            f"{ARQ_TELEMETRIA} nao encontrado. Rode 03_limpeza.py primeiro."
        )
    t0 = time.time()
    tel = pl.read_parquet(ARQ_TELEMETRIA)
    print(f"  {tel.shape[0]:>10,} linhas x {tel.shape[1]:>2} colunas  "
          f"({time.time()-t0:.1f}s)")

    print("\n[2/11] Filtrando Informacional (controle_alteracoes 2026-05-16)")
    tel_rel = tel.filter(pl.col("Criticidade") != "Informacional")
    pct_reducao = (1 - tel_rel.shape[0] / tel.shape[0]) * 100
    print(f"  telemetria_relevante: {tel_rel.shape[0]:>10,} linhas "
          f"(-{pct_reducao:.1f}%)")
    total_dgs = tel_rel.get_column("Is_Dont_Go").sum()
    print(f"  DGs preservados: {total_dgs:,} (esperado {TOTAL_DGS_ESPERADO:,})")
    assert total_dgs == TOTAL_DGS_ESPERADO, (
        f"Filtro removeu DGs: esperado {TOTAL_DGS_ESPERADO:,}, "
        f"obtido {total_dgs:,}"
    )

    print("\n  Carregando apontamentos")
    if not ARQ_APONTAMENTOS.exists():
        raise FileNotFoundError(f"{ARQ_APONTAMENTOS} nao encontrado.")
    apo = pl.read_parquet(ARQ_APONTAMENTOS)
    print(f"  {apo.shape[0]:>10,} linhas x {apo.shape[1]:>2} colunas")

    return tel_rel, apo


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------
def fig2_distribuicao_temporal_apontamentos(apo: pl.DataFrame) -> None:
    print("\n[3/11] Fig 2 - Distribuicao temporal de apontamentos")

    diario = (
        apo.with_columns(pl.col("Inicio").dt.truncate("1d").alias("dia"))
           .group_by("dia").agg(pl.len().alias("n"))
           .sort("dia")
    )
    horario = (
        apo.with_columns(pl.col("Inicio").dt.hour().alias("hora"))
           .group_by("hora").agg(pl.len().alias("n"))
           .sort("hora")
    )

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.5))

    ax1.plot(diario["dia"], diario["n"], color=COR_NEUTRO, linewidth=1)
    ax1.fill_between(diario["dia"], diario["n"], alpha=0.2, color=COR_NEUTRO)
    ax1.set_title("(a) Volume diario de apontamentos (jan-jun/2025)")
    ax1.set_xlabel("Data")
    ax1.set_ylabel("Apontamentos")
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    ax2.bar(horario["hora"], horario["n"], color=COR_DESTAQUE, width=0.8)
    ax2.set_title("(b) Volume por hora do dia (agregado)")
    ax2.set_xlabel("Hora do dia")
    ax2.set_ylabel("Apontamentos")
    ax2.set_xticks(range(0, 24, 2))

    plt.tight_layout()
    plt.savefig(ARQ_FIG2)
    plt.close()
    print(f"  -> {ARQ_FIG2.relative_to(ROOT)}")


def fig3_tipo_x_criticidade(tel: pl.DataFrame) -> None:
    print("\n[4/11] Fig 3 - Tipo de equipamento x Criticidade")

    pivot = (
        tel.group_by(["Tipo", "Criticidade"])
           .agg(pl.len().alias("n"))
           .pivot(index="Tipo", on="Criticidade", values="n")
           .fill_null(0)
           .sort("Tipo")
    )

    tipos = pivot["Tipo"].to_list()
    critico = pivot["Critico"].to_list() if "Critico" in pivot.columns else [0]*len(tipos)
    nao_crit = (
        pivot["Nao_Critico"].to_list()
        if "Nao_Critico" in pivot.columns else [0]*len(tipos)
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(tipos))
    ax.bar(x, nao_crit, 0.6, label="Nao_Critico", color=COR_NAO_CRITICO)
    ax.bar(x, critico, 0.6, bottom=nao_crit, label="Critico", color=COR_CRITICO)

    for i in range(len(tipos)):
        total = critico[i] + nao_crit[i]
        ax.text(i, total, f"{total:,}", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(tipos, rotation=15, ha="right")
    ax.set_ylabel("Numero de eventos")
    ax.set_title("Eventos por Tipo de equipamento x Criticidade\n"
                 "(Informacional filtrado)")
    ax.legend(title="Criticidade")

    plt.tight_layout()
    plt.savefig(ARQ_FIG3)
    plt.close()
    print(f"  -> {ARQ_FIG3.relative_to(ROOT)}")


def fig4_serie_temporal_dgs(tel: pl.DataFrame) -> None:
    import datetime as _dt
    print("\n[5/11] Fig 4 - Série temporal de DGs (diária + MA 7d)")

    dgs = tel.filter(pl.col("Is_Dont_Go") == 1)
    pivot = (
        dgs.with_columns(pl.col("Data_Evento").dt.truncate("1d").alias("dia"))
           .group_by(["dia", "Criticidade"])
           .agg(pl.len().alias("n"))
           .pivot(index="dia", on="Criticidade", values="n")
           .fill_null(0)
           .sort("dia")
    )

    if "Critico" not in pivot.columns:
        pivot = pivot.with_columns(pl.lit(0).alias("Critico"))
    if "Nao_Critico" not in pivot.columns:
        pivot = pivot.with_columns(pl.lit(0).alias("Nao_Critico"))

    pivot = pivot.with_columns(
        (pl.col("Critico") + pl.col("Nao_Critico")).alias("Total")
    ).with_columns([
        pl.col("Critico").rolling_mean(7).alias("Critico_MA7"),
        pl.col("Nao_Critico").rolling_mean(7).alias("Nao_Critico_MA7"),
        pl.col("Total").rolling_mean(7).alias("Total_MA7"),
    ])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 8), sharex=True)

    ax1.bar(pivot["dia"], pivot["Total"], color="#cccccc", width=1.0,
            label="DGs/dia")
    ax1.plot(pivot["dia"], pivot["Total_MA7"], color=COR_NEUTRO, linewidth=2,
             label="Média móvel 7d")
    ax1.set_title("(a) DGs por dia (total)", fontsize=13, fontweight="bold")
    ax1.set_ylabel("DGs", fontsize=11)
    ax1.legend(loc="upper left", fontsize=10)
    ax1.tick_params(axis="both", labelsize=10)

    # Anotação visual sobre a explosão de junho (CA65926)
    anot_x = _dt.datetime(2025, 6, 26)  # pico do CA65926 (RFB-Active jun)
    ymax = float(pivot["Total"].max())
    ax1.annotate(
        "Explosão de jun: 82% dos DGs do mês\n"
        "vêm de UM equipamento (CA65926)\n"
        "— falha mecânica progressiva",
        xy=(anot_x, ymax * 0.92),
        xytext=(_dt.datetime(2025, 3, 1), ymax * 0.75),
        fontsize=10, color="#b22222", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#b22222", lw=1.5),
        bbox=dict(boxstyle="round,pad=0.4", fc="#fff5f5", ec="#b22222", lw=1),
    )

    ax2.plot(pivot["dia"], pivot["Critico_MA7"], color=COR_CRITICO,
             linewidth=2, label="Crítico (MA7)")
    ax2.plot(pivot["dia"], pivot["Nao_Critico_MA7"], color=COR_NAO_CRITICO,
             linewidth=2, label="Não-Crítico (MA7)")
    ax2.set_title("(b) DGs por dia separados por Criticidade (MA 7d)",
                  fontsize=13, fontweight="bold")
    ax2.set_ylabel("DGs (média 7d)", fontsize=11)
    ax2.set_xlabel("Data", fontsize=11)
    ax2.legend(loc="upper left", fontsize=10)
    ax2.tick_params(axis="both", labelsize=10)
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    plt.suptitle(
        "Figura 4 — Série temporal de DGs (jan-jun/2025)",
        fontsize=14, fontweight="bold", y=1.00,
    )
    plt.tight_layout()
    plt.savefig(ARQ_FIG4, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  -> {ARQ_FIG4.relative_to(ROOT)}")


def fig5_heatmap_correlacao(tel: pl.DataFrame) -> None:
    print("\n[6/11] Fig 5 - Heatmap de correlacao entre features numericas")

    df = tel.with_columns([
        pl.col("Data_Evento").dt.hour().alias("hora"),
        pl.col("Data_Evento").dt.weekday().alias("dia_semana"),
        pl.col("Data_Evento").dt.month().alias("mes"),
    ]).select([
        "Is_Dont_Go", "Id_Criticidade", "Valor", "hora", "dia_semana", "mes"
    ])

    corr = df.to_pandas().corr(method="pearson")

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r",
                center=0, vmin=-1, vmax=1, ax=ax, square=True,
                cbar_kws={"label": "Correlacao de Pearson"})
    ax.set_title("Correlacao entre features numericas\n"
                 "(Informacional filtrado)")
    plt.tight_layout()
    plt.savefig(ARQ_FIG5)
    plt.close()
    print(f"  -> {ARQ_FIG5.relative_to(ROOT)}")


def fig6_heatmap_hora_dia(tel: pl.DataFrame) -> None:
    print("\n[7/11] Fig 6 - Heatmap hora x dia da semana (taxa de DG)")

    grid = (
        tel.with_columns([
            pl.col("Data_Evento").dt.hour().alias("hora"),
            pl.col("Data_Evento").dt.weekday().alias("dia_semana"),
        ])
        .group_by(["dia_semana", "hora"])
        .agg(
            pl.len().alias("total"),
            pl.col("Is_Dont_Go").sum().alias("dgs"),
        )
        .with_columns((pl.col("dgs") / pl.col("total") * 100).alias("taxa_dg_pct"))
    )

    grid_pd = (
        grid.to_pandas()
            .pivot(index="dia_semana", columns="hora", values="taxa_dg_pct")
            .sort_index()
    )
    grid_pd.index = [
        DIAS_SEMANA[i-1] if 1 <= i <= 7 else str(i) for i in grid_pd.index
    ]

    fig, ax = plt.subplots(figsize=(14, 4.5))
    sns.heatmap(grid_pd, cmap="viridis", annot=False, ax=ax,
                cbar_kws={"label": "Taxa de DG (%)"})
    ax.set_title("Taxa de DG por hora x dia da semana\n"
                 "(Informacional filtrado - responde Q5)")
    ax.set_xlabel("Hora do dia")
    ax.set_ylabel("Dia da semana")
    plt.tight_layout()
    plt.savefig(ARQ_FIG6)
    plt.close()
    print(f"  -> {ARQ_FIG6.relative_to(ROOT)}")


def fig_extra_b_pareto_alarmes(tel: pl.DataFrame) -> None:
    print("\n[8/11] Fig Extra B - Pareto top-10 alarmes precursores de DG")

    dgs = tel.filter(pl.col("Is_Dont_Go") == 1)
    total_dg = dgs.height

    top = (
        dgs.group_by("Alarme")
           .agg(pl.len().alias("n_DGs"))
           .sort("n_DGs", descending=True)
           .head(10)
           .with_columns((pl.col("n_DGs") / total_dg * 100).alias("pct"))
           .with_columns(pl.col("pct").cum_sum().alias("pct_acum"))
    )

    alarmes = [a if len(a) <= 35 else a[:32] + "..." for a in top["Alarme"].to_list()]
    x = np.arange(len(alarmes))

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(x, top["n_DGs"], color=COR_NEUTRO, alpha=0.85)
    ax1.set_xlabel("Alarme")
    ax1.set_ylabel("Numero de DGs", color=COR_NEUTRO)
    ax1.set_xticks(x)
    ax1.set_xticklabels(alarmes, rotation=40, ha="right")

    ax2 = ax1.twinx()
    ax2.plot(x, top["pct_acum"], color=COR_CRITICO, marker="o", linewidth=2)
    ax2.set_ylabel("% acumulado dos DGs", color=COR_CRITICO)
    ax2.set_ylim(0, 105)
    ax2.axhline(80, linestyle="--", color="gray", alpha=0.5, linewidth=1)
    ax2.text(len(alarmes)-1, 80, "80%", ha="right", va="bottom",
             fontsize=9, color="gray")

    ax1.set_title(
        f"Pareto: top 10 alarmes precursores de DG\n"
        f"Top 5 = 87,3% dos {total_dg:,} DGs do semestre"
    )
    plt.tight_layout()
    plt.savefig(ARQ_FIG_EXB)
    plt.close()
    print(f"  -> {ARQ_FIG_EXB.relative_to(ROOT)}")


def fig_extra_g_pareto_tags(tel: pl.DataFrame) -> None:
    print("\n[9/11] Fig Extra G - Pareto top-15 TAGs por numero de DGs")

    dgs = tel.filter(pl.col("Is_Dont_Go") == 1)
    total_dg = dgs.height
    n_tags_relevantes = tel["TAG"].n_unique()

    top = (
        dgs.group_by("TAG")
           .agg(pl.len().alias("n_DGs"))
           .sort("n_DGs", descending=True)
           .head(15)
           .with_columns((pl.col("n_DGs") / total_dg * 100).alias("pct"))
           .with_columns(pl.col("pct").cum_sum().alias("pct_acum"))
    )

    tags = top["TAG"].to_list()
    x = np.arange(len(tags))

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(x, top["n_DGs"], color=COR_DESTAQUE, alpha=0.85)
    ax1.set_xlabel("TAG (equipamento)")
    ax1.set_ylabel("Numero de DGs", color=COR_DESTAQUE)
    ax1.set_xticks(x)
    ax1.set_xticklabels(tags, rotation=40, ha="right")

    ax2 = ax1.twinx()
    ax2.plot(x, top["pct_acum"], color=COR_CRITICO, marker="o", linewidth=2)
    ax2.set_ylabel("% acumulado dos DGs", color=COR_CRITICO)
    ax2.set_ylim(0, 105)
    ax2.axhline(80, linestyle="--", color="gray", alpha=0.5, linewidth=1)

    ax1.set_title(
        f"Pareto: top 15 TAGs com mais DGs\n"
        f"(de {n_tags_relevantes} TAGs com Critico/Nao_Critico em telemetria)"
    )
    plt.tight_layout()
    plt.savefig(ARQ_FIG_EXG)
    plt.close()
    print(f"  -> {ARQ_FIG_EXG.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Tabela Q4
# ---------------------------------------------------------------------------
def tabela_q4(tel: pl.DataFrame, apo: pl.DataFrame) -> pl.DataFrame:
    print("\n[10/11] Tabela Q4 - DGs por Frota / Tipo / Classe (join temporal)")
    print("  'Classe' aqui = ESTADO operacional do ciclo de apontamento ativo no")
    print("  momento do DG (via join_asof: Tag + Inicio <= Data_Evento <= Fim).")

    # ----- 1. Mapa Tag -> Frota (atributo fixo do equipamento, 1:1) -----
    mapa_frota = (
        apo.group_by(["Tag", "Frota"])
           .agg(pl.len().alias("n"))
           .sort(["Tag", "n"], descending=[False, True])
           .group_by("Tag", maintain_order=True)
           .agg(pl.col("Frota").first())
    )

    # ----- 2. Filtrar DGs e preparar para join_asof -----
    dgs = tel.filter(pl.col("Is_Dont_Go") == 1).sort("Data_Evento")
    print(f"\n  DGs a casar: {dgs.height:,}")

    # Alinhar precisao temporal com telemetria (Data_Evento esta em us;
    # apontamentos vem como ns - cast e' lossless dado granularidade de seg/min)
    apo_para_join = (
        apo.select(["Tag", "Inicio", "Fim", "Classe"])
           .rename({"Classe": "Classe_estado"})
           .with_columns([
               pl.col("Inicio").dt.cast_time_unit("us"),
               pl.col("Fim").dt.cast_time_unit("us"),
           ])
           .sort("Inicio")
    )
    print(f"  Ciclos de apontamento disponiveis: {apo_para_join.height:,}")

    # ----- 3. join_asof: cada DG -> apontamento mesma TAG com maior Inicio <= Data_Evento -----
    joined = dgs.join_asof(
        apo_para_join,
        left_on="Data_Evento",
        right_on="Inicio",
        by_left="TAG",
        by_right="Tag",
        strategy="backward",
    )

    # ----- 4. Diagnostico de casamento -----
    sem_apo_anterior = joined.filter(pl.col("Inicio").is_null()).height
    if sem_apo_anterior > 0:
        print(f"  AVISO: {sem_apo_anterior:,} DGs sem apontamento anterior "
              "(antes do primeiro Inicio da TAG)")

    fora_intervalo = joined.filter(
        pl.col("Inicio").is_not_null() & (pl.col("Data_Evento") > pl.col("Fim"))
    ).height
    if fora_intervalo > 0:
        print(f"  AVISO: {fora_intervalo:,} DGs com Data_Evento > Fim "
              "(gap entre apontamentos)")

    com_match = joined.height - sem_apo_anterior - fora_intervalo
    pct_match = com_match / dgs.height * 100
    print(f"  DGs com match valido: {com_match:,} ({pct_match:.2f}%)")

    # ----- 5. Marcar DGs sem match como SEM_APONTAMENTO (transparente, nao silencia) -----
    joined = joined.with_columns(
        pl.when(pl.col("Inicio").is_null() | (pl.col("Data_Evento") > pl.col("Fim")))
          .then(pl.lit("SEM_APONTAMENTO"))
          .otherwise(pl.col("Classe_estado"))
          .alias("Classe_estado")
    )

    # ----- 6. Join com mapa Frota -----
    joined_com_frota = joined.join(
        mapa_frota, left_on="TAG", right_on="Tag", how="left"
    )

    # ----- 7. Tabela agregada -----
    tabela = (
        joined_com_frota.group_by(["Frota", "Tipo", "Classe_estado"])
                        .agg(
                            pl.col("TAG").n_unique().alias("n_tags"),
                            pl.len().alias("total_DGs"),
                        )
                        .with_columns(
                            (pl.col("total_DGs") / TOTAL_DGS_ESPERADO * 100)
                              .round(2).alias("pct_DGs")
                        )
                        .sort("total_DGs", descending=True)
                        .rename({"Classe_estado": "Classe"})
    )

    DIR_TABELAS.mkdir(parents=True, exist_ok=True)
    tabela.write_csv(ARQ_TAB_Q4)
    print(f"\n  -> {ARQ_TAB_Q4.relative_to(ROOT)}")
    print("\n  Preview (top 25):")
    with pl.Config(tbl_rows=25, tbl_cols=10, fmt_str_lengths=40):
        print(tabela)

    print("\n  Resumo agregado por Classe (estado operacional no momento do DG):")
    resumo_classe = (
        tabela.group_by("Classe")
              .agg(pl.col("total_DGs").sum().alias("DGs"))
              .with_columns(
                  (pl.col("DGs") / TOTAL_DGS_ESPERADO * 100).round(2).alias("pct")
              )
              .sort("DGs", descending=True)
    )
    print(resumo_classe)

    return tabela


# ---------------------------------------------------------------------------
# Validacao
# ---------------------------------------------------------------------------
def validar(tabela: pl.DataFrame) -> None:
    print("\n[11/11] Validacao final")

    arquivos = [
        ARQ_FIG2, ARQ_FIG3, ARQ_FIG4, ARQ_FIG5, ARQ_FIG6,
        ARQ_FIG_EXB, ARQ_FIG_EXG, ARQ_TAB_Q4,
    ]
    for arq in arquivos:
        assert arq.exists(), f"Arquivo nao gerado: {arq}"
        assert arq.stat().st_size > 0, f"Arquivo vazio: {arq}"
        tamanho_kb = arq.stat().st_size / 1024
        print(f"  OK  {arq.relative_to(ROOT)}  ({tamanho_kb:.1f} KB)")

    total_na_tabela = tabela["total_DGs"].sum()
    assert total_na_tabela == TOTAL_DGS_ESPERADO, (
        f"Soma de DGs na tabela Q4 = {total_na_tabela:,}, "
        f"esperado {TOTAL_DGS_ESPERADO:,}"
    )
    print(f"  OK  Soma de DGs na tabela Q4 = {total_na_tabela:,} "
          f"(esperado {TOTAL_DGS_ESPERADO:,})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== EDA visual (W2) ===")
    configurar_tema()

    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    DIR_TABELAS.mkdir(parents=True, exist_ok=True)

    tel, apo = carregar()
    fig2_distribuicao_temporal_apontamentos(apo)
    fig3_tipo_x_criticidade(tel)
    fig4_serie_temporal_dgs(tel)
    fig5_heatmap_correlacao(tel)
    fig6_heatmap_hora_dia(tel)
    fig_extra_b_pareto_alarmes(tel)
    fig_extra_g_pareto_tags(tel)
    tabela = tabela_q4(tel, apo)
    validar(tabela)

    print("\n[OK] EDA visual concluida.")
    print("\nProximos passos manuais:")
    print("  1. Fig 1 (diagrama do fluxo operacional) em draw.io ou PowerPoint")
    print("  2. Escrever Projeto/relatorio/hipoteses_eda.md a partir dos achados")
    print("  3. Atualizar Projeto/relatorio/rascunho.md - secao EDA + Q4 + Q5")
    print("  4. Investigar Obs 2.6 - olhar fig04 para padrao do salto Nao_Critico")


if __name__ == "__main__":
    main()
