# -*- coding: utf-8 -*-
"""
figneg_01_timeline_ca65926.py - Figura de NEGÓCIO #1: Timeline do CA65926.

Narrativa para o time operacional: o equipamento CA65926 deu **sinais precursores
em março** (438 DGs, taxa 20%) e **explodiu em junho** (4.298 DGs, via Right Front
Brake Temperature). Janela de antecipação real: 3 meses entre sinal e crise.

Mostra que MONITORAMENTO POR EQUIPAMENTO (não por frota agregada) teria capturado
o problema com tempo de mobilização suficiente.

Entradas:
  - dados/intermediarios/telemetria_limpa.parquet

Saídas:
  - relatorio/figuras/figNeg01_timeline_ca65926.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/figneg_01_timeline_ca65926.py
"""
from pathlib import Path
import matplotlib.pyplot as plt
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
ARQ_TEL = ROOT / "dados" / "intermediarios" / "telemetria_limpa.parquet"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figNeg01_timeline_ca65926.png"

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun"]


def main() -> None:
    print("Carregando telemetria_limpa.parquet e filtrando CA65926...")
    tel = pl.read_parquet(ARQ_TEL)
    ca = tel.filter(pl.col("TAG") == "CA65926")
    print(f"  CA65926: {ca.height:,} eventos")

    ca_mes = (
        ca.with_columns(pl.col("Data_Evento").dt.month().alias("mes"))
          .group_by("mes")
          .agg(
              pl.len().alias("eventos"),
              pl.col("Is_Dont_Go").sum().alias("dgs"),
              (pl.col("Alarme") == "Right Front Brake Temperature - Active").sum().alias("rfb"),
              ((pl.col("Is_Dont_Go") == 1) &
               (pl.col("Alarme") == "Right Front Brake Temperature - Active")).sum().alias("dgs_rfb"),
          )
          .sort("mes")
    )
    print(ca_mes)

    dgs = ca_mes["dgs"].to_list()
    dgs_rfb = ca_mes["dgs_rfb"].to_list()
    dgs_outros = [d - r for d, r in zip(dgs, dgs_rfb)]
    taxa = [
        round(100 * d / e, 2)
        for d, e in zip(dgs, ca_mes["eventos"].to_list())
    ]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=False)

    # Painel A — DGs por mês (barras empilhadas: RFB vs outros)
    x = list(range(6))
    bars1 = ax1.bar(x, dgs_outros, color="#1976d2", label="DGs por outros alarmes",
                     edgecolor="white", linewidth=1.5)
    bars2 = ax1.bar(x, dgs_rfb, bottom=dgs_outros, color="#c62828",
                     label="DGs por Right Front Brake Temperature",
                     edgecolor="white", linewidth=1.5)

    # Anotar valores no topo
    for i, total in enumerate(dgs):
        ax1.text(i, total + max(dgs) * 0.02, f"{total:,}",
                 ha="center", fontsize=11, fontweight="bold")

    # Anotação: sinal precursor (março)
    ax1.annotate(
        "Sinal precursor\n(taxa 20% via outros alarmes)\n— 3 meses antes da crise",
        xy=(2, 438),
        xytext=(0.3, 2000),
        fontsize=10, color="#ff8f00", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#ff8f00", lw=1.8),
        bbox=dict(boxstyle="round,pad=0.4", fc="#fff8e1", ec="#ff8f00", lw=1.5),
    )

    # Anotação: crise junho
    ax1.annotate(
        "Crise: falha mecânica\nse manifesta no sensor RFB\n(98% dos eventos críticos do mês)",
        xy=(5, 4298),
        xytext=(3.2, 3500),
        fontsize=10, color="#b22222", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#b22222", lw=1.8),
        bbox=dict(boxstyle="round,pad=0.4", fc="#fff5f5", ec="#b22222", lw=1.5),
    )

    ax1.set_xticks(x)
    ax1.set_xticklabels(MESES, fontsize=12)
    ax1.set_ylabel("Don't Go (DGs) por mês", fontsize=12)
    ax1.set_title("(a) Evolução de DGs no CA65926 — janela de antecipação real: 3 meses",
                  fontsize=13, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=11, framealpha=0.95)
    ax1.tick_params(axis="both", labelsize=11)
    ax1.set_ylim(0, max(dgs) * 1.15)

    # Painel B — Taxa de DG por mês (% sobre eventos)
    cores_taxa = ["#1976d2"] * 6
    cores_taxa[2] = "#ff8f00"  # destaque março (precursor)
    cores_taxa[5] = "#c62828"  # destaque junho (crise)
    ax2.bar(x, taxa, color=cores_taxa, edgecolor="white", linewidth=1.5)

    # Anotar taxa em cada barra
    for i, t in enumerate(taxa):
        ax2.text(i, t + 1.5, f"{t}%", ha="center", fontsize=11, fontweight="bold")

    # Linha de referência: taxa global
    taxa_global = 3.66
    ax2.axhline(taxa_global, color="gray", linestyle="--", linewidth=1.5, alpha=0.7,
                label=f"Taxa global do parque ({taxa_global:.2f}%)")

    ax2.set_xticks(x)
    ax2.set_xticklabels(MESES, fontsize=12)
    ax2.set_ylabel("Taxa mensal de DG (%)", fontsize=12)
    ax2.set_title("(b) Taxa de DG por mês — março já estava 5x acima do parque",
                  fontsize=13, fontweight="bold")
    ax2.legend(loc="upper left", fontsize=11, framealpha=0.95)
    ax2.tick_params(axis="both", labelsize=11)
    ax2.set_ylim(0, max(taxa) * 1.15)

    fig.suptitle(
        "Figura — Deterioração progressiva do CA65926 (jan-jun/2025)\n"
        "Sinal precursor em março não foi capturado pela operação atual",
        fontsize=14, fontweight="bold", y=1.00,
    )

    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSalvo: {ARQ_FIG.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
