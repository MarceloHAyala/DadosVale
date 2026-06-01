# -*- coding: utf-8 -*-
"""
_regen_fig4.py - Wrapper para regenerar apenas a Fig 4 (sem rodar EDA completa).

Reaproveita a função `fig4_serie_temporal_dgs` do 04_eda.py via exec direto,
contornando a limitação de imports de módulos com nome iniciado por dígito.

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/_regen_fig4.py
"""
from pathlib import Path
import polars as pl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime as _dt

ROOT = Path(__file__).resolve().parents[1]
DIR_FIGURAS = ROOT / "relatorio" / "figuras"
ARQ_FIG4 = DIR_FIGURAS / "fig04_serie_temporal_dgs.png"
ARQ_TEL = ROOT / "dados" / "intermediarios" / "telemetria_limpa.parquet"

COR_CRITICO = "#c62828"
COR_NAO_CRITICO = "#f9a825"
COR_NEUTRO = "#1976d2"


def main():
    print("Carregando telemetria_limpa.parquet...")
    tel = pl.read_parquet(ARQ_TEL)
    print(f"  shape: {tel.shape}")

    print("Gerando Fig 4 (regenerada com acentos + anotação CA65926)...")
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
    print(f"Salvo: {ARQ_FIG4.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
