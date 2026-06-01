# -*- coding: utf-8 -*-
"""
figneg_02_ranking_risco.py - Figura de NEGÓCIO #2: Ranking de risco por equipamento.

Mostra TODOS os 35 equipamentos do parque ordenados por risco operacional,
com:
  - n_DG no semestre (volume absoluto)
  - taxa de DG (%)
  - Cor por nível de prioridade (Alto / Médio / Baixo)
  - Coluna lateral: ação recomendada

Critério de risco combinado:
  - ALTO: n_DG >= 1000 (volume) OU taxa >= 30% (severidade) → "Auditoria imediata"
  - MÉDIO: n_DG >= 200 OU taxa >= 5% → "Monitorar mensalmente"
  - BAIXO: resto → "Operação normal"

Esta figura traduz a heterogeneidade do parque em decisão operacional:
política de manutenção preventiva deveria ser POR EQUIPAMENTO, não por frota.

Entradas:
  - dados/intermediarios/telemetria_limpa.parquet
  - relatorio/tabelas/if_auc_por_tag.csv (opcional — flag de sinal IF detectável)

Saídas:
  - relatorio/figuras/figNeg02_ranking_risco_operacional.png
  - relatorio/tabelas/ranking_risco_operacional.csv

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/figneg_02_ranking_risco.py
"""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
ARQ_TEL = ROOT / "dados" / "intermediarios" / "telemetria_limpa.parquet"
ARQ_IF = ROOT / "relatorio" / "tabelas" / "if_auc_por_tag.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figNeg02_ranking_risco_operacional.png"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "ranking_risco_operacional.csv"

COR_ALTO = "#c62828"
COR_MEDIO = "#ff8f00"
COR_BAIXO = "#2e7d32"


def classificar_risco(n_dg: int, taxa: float) -> tuple[str, str, str]:
    """Retorna (nivel, cor, acao_recomendada)."""
    if n_dg >= 1000 or taxa >= 30:
        return "ALTO", COR_ALTO, "Auditoria imediata + revisão da manutenção"
    if n_dg >= 200 or taxa >= 5:
        return "MÉDIO", COR_MEDIO, "Monitoramento mensal estratificado"
    return "BAIXO", COR_BAIXO, "Operação normal (rotina padrão)"


def main() -> None:
    print("Carregando dados...")
    tel = pl.read_parquet(ARQ_TEL)

    # Stats por TAG no semestre inteiro
    stats = (
        tel.group_by("TAG").agg(
            pl.len().alias("eventos"),
            pl.col("Is_Dont_Go").sum().alias("dgs"),
            pl.col("Tag_Frota").first().alias("frota"),
            pl.col("Tipo").first().alias("tipo"),
        )
        .with_columns(
            (pl.col("dgs") / pl.col("eventos") * 100).round(2).alias("taxa_pct")
        )
        .filter(pl.col("eventos") >= 100)  # remove TAGs com sample muito pequeno
        .sort("dgs", descending=True)
    )

    # Junta com IF AUC se disponível
    if ARQ_IF.exists():
        if_auc = pl.read_csv(ARQ_IF).select(["TAG", "auc_roc"]).rename(
            {"auc_roc": "if_auc_test"}
        )
        stats = stats.join(if_auc, on="TAG", how="left")

    # Classifica
    niveis = []
    cores = []
    acoes = []
    for row in stats.iter_rows(named=True):
        nivel, cor, acao = classificar_risco(row["dgs"], row["taxa_pct"])
        niveis.append(nivel)
        cores.append(cor)
        acoes.append(acao)

    stats = stats.with_columns(
        pl.Series("nivel_risco", niveis),
        pl.Series("acao_recomendada", acoes),
    )

    # Salva tabela
    stats.write_csv(ARQ_TAB)
    print(f"Salvo: {ARQ_TAB.relative_to(ROOT.parent)}")
    print()
    n_alto = sum(1 for n in niveis if n == "ALTO")
    n_med = sum(1 for n in niveis if n == "MÉDIO")
    n_baixo = sum(1 for n in niveis if n == "BAIXO")
    print(f"Distribuição: ALTO={n_alto}  MÉDIO={n_med}  BAIXO={n_baixo}")

    # Figura
    print("\nGerando figura...")
    tags = stats["TAG"].to_list()
    dgs_arr = stats["dgs"].to_list()
    taxa_arr = stats["taxa_pct"].to_list()
    n = len(tags)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, max(8, n * 0.32)),
                                    gridspec_kw={"width_ratios": [2, 1]})

    # Painel esquerdo — DGs absolutos (barras horizontais)
    y = list(range(n))
    ax1.barh(y, dgs_arr, color=cores, edgecolor="white", linewidth=1.2)
    for i, (d, t) in enumerate(zip(dgs_arr, taxa_arr)):
        ax1.text(d + max(dgs_arr) * 0.01, i, f"{d:,} ({t:.1f}%)",
                 va="center", fontsize=9)
    ax1.set_yticks(y)
    ax1.set_yticklabels(tags, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlabel("Don't Go (DGs) no semestre — Jan-Jun/2025", fontsize=11)
    ax1.set_title("Ranking de risco por equipamento\n(volume de DGs + taxa %)",
                  fontsize=12, fontweight="bold")
    ax1.tick_params(axis="x", labelsize=10)
    ax1.grid(True, axis="x", alpha=0.3)
    ax1.set_xlim(0, max(dgs_arr) * 1.30)

    # Legenda
    legenda = [
        mpatches.Patch(color=COR_ALTO, label="ALTO (DGs ≥ 1000 ou taxa ≥ 30%)"),
        mpatches.Patch(color=COR_MEDIO, label="MÉDIO (DGs ≥ 200 ou taxa ≥ 5%)"),
        mpatches.Patch(color=COR_BAIXO, label="BAIXO (resto)"),
    ]
    ax1.legend(handles=legenda, loc="lower right", fontsize=10, framealpha=0.95,
               title="Nível de risco operacional", title_fontsize=10)

    # Painel direito — texto da ação recomendada (tabela visual)
    ax2.axis("off")
    ax2.set_title("Ação recomendada", fontsize=12, fontweight="bold",
                  loc="left", pad=18)

    y_pos = 1.0
    step = 1.0 / n
    for i, (tag, nivel, acao) in enumerate(zip(tags, niveis, acoes)):
        cor = cores[i]
        # Tag + nivel à esquerda
        ax2.text(0.02, y_pos - step * (i + 0.5),
                 f"{tag}", fontsize=9, va="center", fontweight="bold")
        # Bullet colorido + ação
        ax2.text(0.20, y_pos - step * (i + 0.5),
                 "●", fontsize=14, va="center", color=cor)
        ax2.text(0.27, y_pos - step * (i + 0.5),
                 acao, fontsize=8.5, va="center")

    fig.suptitle(
        f"Figura — Ranking de risco operacional dos {n} equipamentos do parque (Jan-Jun/2025)\n"
        "Política de manutenção preventiva deveria operar POR EQUIPAMENTO, não por frota",
        fontsize=13, fontweight="bold", y=0.995,
    )

    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
