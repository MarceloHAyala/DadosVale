# -*- coding: utf-8 -*-
"""
17_distribuicao_antecipacao.py - Distribuição do tempo de antecipação (Qualidade B).

Responde uma pergunta operacional crítica que NÃO é capturada por
Precision/Recall agregados:

  "Quando o modelo emite um alerta positivo (TP), quanto tempo o time
   operacional tem antes do DG real ocorrer?"

Para cada TP (evento com `target_4h=1` E `P(DG) >= 0.30` no v3),
computa o tempo entre o evento de telemetria observado (t) e o
DG real correspondente (t + delta), onde delta in (0, 4h].

Reporta:
  - Histograma (15 bins de 16 minutos cada) da distribuição
  - Estatísticas: P10/P25/P50/P75/P90/média
  - Diferenciação por subgrupos (frota, criticidade pré-evento)
  - Comparação com a "janela de mobilização" típica (referência: 1,5h)

Material para CM 5.2 (Qualidade B) e para a defesa operacional do modelo.

Entradas:
  - dados/features/v3.parquet
  - modelos/lightgbm_v2_no_cascade.txt

Saídas:
  - relatorio/tabelas/distribuicao_antecipacao.csv (estatísticas + por frota)
  - relatorio/figuras/figNeg04_distribuicao_antecipacao.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/17_distribuicao_antecipacao.py
"""
from pathlib import Path

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"

ARQ_TAB = ROOT / "relatorio" / "tabelas" / "distribuicao_antecipacao.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figNeg04_distribuicao_antecipacao.png"

THRESHOLD_OP = 0.30  # canônico W7

FEATURES_V3 = [
    "hora_dia", "dia_semana", "turno", "mes", "valor_disponivel",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    "horas_desde_ultimo_critico",
    "estado_pre_evento",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
]


def computar_tempo_antecipacao(df: pl.DataFrame) -> pl.DataFrame:
    """Para cada evento, computa o tempo até o próximo DG da mesma TAG (em horas).

    Reaproveita lógica do 09_sobrevivencia.py (join_asof forward por TAG).
    """
    print("  Computando tempo até o próximo DG via join_asof forward por TAG...")

    df = df.sort(["TAG", "Data_Evento"])
    dgs = (
        df.filter(pl.col("Is_Dont_Go") == 1)
        .select(["TAG", "Data_Evento"])
        .rename({"Data_Evento": "data_proximo_dg"})
        .sort(["TAG", "data_proximo_dg"])
    )

    df = df.join_asof(
        dgs,
        left_on="Data_Evento",
        right_on="data_proximo_dg",
        by="TAG",
        strategy="forward",
    )

    # Filtrar para DG estritamente futuro (> Data_Evento)
    df = df.with_columns(
        pl.when(pl.col("data_proximo_dg") > pl.col("Data_Evento"))
        .then(
            (pl.col("data_proximo_dg") - pl.col("Data_Evento"))
            .dt.total_seconds() / 3600.0
        )
        .otherwise(None)
        .alias("horas_ate_proximo_dg")
    )
    return df


def predizer_v3(df_test: pl.DataFrame) -> np.ndarray:
    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    X = df_test.select(FEATURES_V3).to_pandas()
    for c in ["turno", "estado_pre_evento"]:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return booster.predict(X)


def main():
    print("=" * 70)
    print("17_distribuicao_antecipacao.py - Tempo de antecipação dos TPs")
    print("=" * 70)

    df = pl.read_parquet(ARQ_V3)
    print(f"v3.parquet shape: {df.shape}")

    # Computar tempo até próximo DG (em horas) para TODOS os eventos
    df = computar_tempo_antecipacao(df)

    # Filtrar test set
    test = df.filter(pl.col("split") == "test")
    print(f"\nTest set: n={test.height:,}")

    # Predições do v3
    print("Gerando predições do v3 canônico...")
    p = predizer_v3(test)
    test = test.with_columns(pl.Series("p_v3", p))
    test = test.with_columns(
        ((pl.col("p_v3") >= THRESHOLD_OP)
         & (pl.col("target_4h") == 1)).alias("eh_TP"),
    )

    # TPs: target_4h=1 E predito positivo
    tps = test.filter(pl.col("eh_TP") == True)
    n_tps_total = tps.height
    print(f"\nTPs no test (threshold {THRESHOLD_OP}): {n_tps_total:,}")

    # Separar em DOIS grupos:
    # 1. Detecções diretas: o próprio evento é DG (Is_Dont_Go=1) — antecipação = 0
    # 2. Antecipações reais: target_4h=1 mas Is_Dont_Go=0; há DG futuro em (0, 4h]
    tps_detecao_direta = tps.filter(pl.col("Is_Dont_Go") == 1)
    tps_antecipacao_real = tps.filter(pl.col("Is_Dont_Go") == 0).filter(
        (pl.col("horas_ate_proximo_dg").is_not_null())
        & (pl.col("horas_ate_proximo_dg") > 0)
        & (pl.col("horas_ate_proximo_dg") <= 4.0)
    )
    n_dir = tps_detecao_direta.height
    n_ant = tps_antecipacao_real.height
    n_outros = n_tps_total - n_dir - n_ant
    print(f"  Detecções diretas (próprio evento é DG, antecipação=0): {n_dir:,} ({100*n_dir/n_tps_total:.1f}%)")
    print(f"  Antecipações reais (DG futuro em 0-4h, evento não é DG):  {n_ant:,} ({100*n_ant/n_tps_total:.1f}%)")
    print(f"  Outros casos (sem próximo DG válido em janela):           {n_outros:,} ({100*n_outros/n_tps_total:.1f}%)")

    # Para a análise de tempo, focar nas ANTECIPAÇÕES REAIS
    tps_validos = tps_antecipacao_real
    n_validos = tps_validos.height

    horas = tps_validos["horas_ate_proximo_dg"].to_numpy()
    minutos = horas * 60

    # Estatísticas
    estats = {
        "n_TPs_validos": n_validos,
        "media_min": round(float(np.mean(minutos)), 1),
        "mediana_min": round(float(np.median(minutos)), 1),
        "p10_min": round(float(np.percentile(minutos, 10)), 1),
        "p25_min": round(float(np.percentile(minutos, 25)), 1),
        "p50_min": round(float(np.percentile(minutos, 50)), 1),
        "p75_min": round(float(np.percentile(minutos, 75)), 1),
        "p90_min": round(float(np.percentile(minutos, 90)), 1),
    }

    print("\nDistribuição do tempo de antecipação dos TPs (minutos):")
    print(f"  n_TPs válidos: {n_validos:,}")
    print(f"  Média: {estats['media_min']:.1f} min ({estats['media_min']/60:.2f} h)")
    print(f"  P10:   {estats['p10_min']:.1f} min")
    print(f"  P25:   {estats['p25_min']:.1f} min")
    print(f"  P50 (mediana): {estats['p50_min']:.1f} min")
    print(f"  P75:   {estats['p75_min']:.1f} min")
    print(f"  P90:   {estats['p90_min']:.1f} min")

    # Por frota
    print("\nPor frota (Tag_Frota):")
    por_frota = (
        tps_validos.group_by("Tag_Frota").agg(
            pl.len().alias("n_TPs"),
            (pl.col("horas_ate_proximo_dg") * 60).median().alias("mediana_min"),
            (pl.col("horas_ate_proximo_dg") * 60).mean().alias("media_min"),
        )
        .sort("n_TPs", descending=True)
    )
    print(por_frota)

    # Por estado pré-evento
    print("\nPor estado pré-evento:")
    por_estado = (
        tps_validos.group_by("estado_pre_evento").agg(
            pl.len().alias("n_TPs"),
            (pl.col("horas_ate_proximo_dg") * 60).median().alias("mediana_min"),
        )
        .sort("n_TPs", descending=True)
    )
    print(por_estado)

    # Salvar tabela (estats agregada + por frota)
    linhas = [{"subgrupo": "GERAL", "n_TPs": n_validos, **estats}]
    for row in por_frota.iter_rows(named=True):
        linhas.append({
            "subgrupo": f"Frota: {row['Tag_Frota']}",
            "n_TPs": row["n_TPs"],
            "mediana_min": round(float(row["mediana_min"]), 1),
            "media_min": round(float(row["media_min"]), 1),
            "n_TPs_validos": None, "p10_min": None, "p25_min": None,
            "p50_min": None, "p75_min": None, "p90_min": None,
        })
    pl.from_dicts(linhas).write_csv(ARQ_TAB)
    print(f"\nSalvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # Figura — 2 painéis
    print("\nGerando figura (2 painéis: decomposição + distribuição)...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7),
                                    gridspec_kw={"width_ratios": [1, 1.3]})

    # Painel A — Decomposição dos TPs em 3 categorias
    categorias = [
        ("Detecção direta\n(próprio evento é DG)", n_dir, "#9e9e9e"),
        (f"Antecipação real\n(DG futuro em ≤4h)", n_ant, "#1976d2"),
        ("Outros casos\n(target=1 sem DG válido)", n_outros, "#c62828"),
    ]
    nomes = [c[0] for c in categorias]
    valores = [c[1] for c in categorias]
    cores = [c[2] for c in categorias]
    pcts = [100 * v / n_tps_total for v in valores]

    bars = ax1.barh(range(3), valores, color=cores, edgecolor="white", linewidth=1.5)
    for i, (v, p) in enumerate(zip(valores, pcts)):
        ax1.text(v + max(valores) * 0.015, i, f"{v:,} ({p:.1f}%)",
                 va="center", fontsize=11, fontweight="bold")

    ax1.set_yticks(range(3))
    ax1.set_yticklabels(nomes, fontsize=11)
    ax1.invert_yaxis()
    ax1.set_xlabel(f"Número de TPs (total = {n_tps_total:,})", fontsize=12)
    ax1.set_title(
        f"(a) Decomposição dos TPs do v3 (threshold {THRESHOLD_OP})\n"
        f"Metade dos alertas é detecção direta (não antecipação)",
        fontsize=12, fontweight="bold",
    )
    ax1.tick_params(axis="x", labelsize=10)
    ax1.set_xlim(0, max(valores) * 1.25)
    ax1.grid(True, axis="x", alpha=0.3)

    # Painel B — Histograma das ANTECIPAÇÕES REAIS
    bins = np.linspace(0, 240, 25)
    ax2.hist(minutos, bins=bins, color="#1976d2", edgecolor="white",
             linewidth=1.0, alpha=0.85)

    # Marcar percentis
    for pct, label, cor, style, y_frac in [
        (50, "P50 (mediana)", "#c62828", "-", 0.92),
        (75, "P75", "#666666", "--", 0.70),
        (90, "P90", "#666666", "--", 0.50),
    ]:
        v = np.percentile(minutos, pct)
        ax2.axvline(v, color=cor, linestyle=style, linewidth=2, alpha=0.85)
        ax2.text(v + 2, ax2.get_ylim()[1] * y_frac,
                 f"{label}: {v:.0f} min", color=cor, fontsize=10, fontweight="bold",
                 va="top")

    # Referência: janela de mobilização típica (90 min)
    ax2.axvline(90, color="#2e7d32", linestyle=":", linewidth=2.5, alpha=0.75)
    ax2.text(92, ax2.get_ylim()[1] * 0.30,
             "Mobilização típica\n(1,5h = 90 min)",
             color="#2e7d32", fontsize=10, fontweight="bold", va="top")

    pct_acima_90 = float(np.mean(minutos >= 90)) * 100
    pct_acima_60 = float(np.mean(minutos >= 60)) * 100
    pct_acima_30 = float(np.mean(minutos >= 30)) * 100

    leitura = (
        f"Leitura operacional (somente antecipações reais):\n"
        f"  • {pct_acima_30:.0f}% com ≥30 min de antecipação\n"
        f"  • {pct_acima_60:.0f}% com ≥60 min (1h)\n"
        f"  • {pct_acima_90:.0f}% com ≥90 min (mobilização típica)\n"
        f"  • Mediana = {estats['p50_min']:.1f} min (muito curto)"
    )
    ax2.text(0.55, 0.95, leitura, transform=ax2.transAxes,
             fontsize=10, va="top", color="#1976d2",
             bbox=dict(boxstyle="round,pad=0.5", fc="#e3f2fd", ec="#1976d2", lw=1.5))

    ax2.set_xlim(0, 240)
    ax2.set_xlabel("Minutos entre alerta e DG real", fontsize=12)
    ax2.set_ylabel("Frequência (antecipações reais)", fontsize=12)
    ax2.set_title(
        f"(b) Distribuição das antecipações reais\n"
        f"n = {n_validos:,} (apenas alertas onde DG é futuro)",
        fontsize=12, fontweight="bold",
    )
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis="both", labelsize=10)

    fig.suptitle(
        f"Figura — Tempo de antecipação dos alertas verdadeiros do v3 (test set jun/2025)\n"
        f"50% dos TPs são detecções diretas (sem antecipação); dos 50% que antecipam, apenas {pct_acima_90:.0f}% chegam à janela de 90 min",
        fontsize=13, fontweight="bold", y=1.00,
    )

    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
