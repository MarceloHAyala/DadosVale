"""
06_split.py - Split temporal walk-forward + Figs 7 e 8 (W4 CM 4.1)

Divide a matriz v2.parquet em treino / validacao / teste por cortes nos
limites de mes, gera as estatisticas descritivas dos 3 splits e produz
duas figuras metodologicas:

  Fig 7 - Diagrama da janela de predicao (instante de decisao -> 4h -> alvo)
  Fig 8 - Estrategia de validacao temporal (3 splits + drift mes-a-mes)

Cortes (limites de mes, alinhados com a Fig 2):
  Treino:    Data_Evento <  2025-05-01  (jan-abr)
  Validacao: 2025-05-01 <= Data_Evento <  2025-06-01  (mai)
  Teste:     2025-06-01 <= Data_Evento                (jun)

Decisao metodologica sobre o corte:
  Cortar em fim de turno (06:00/18:00) seria 6h diferente. O modelo nao e
  shift-aware (predicao por evento, nao por turno), portanto o ganho seria
  cosmetico. Cortar no limite de mes preserva coerencia direta com Fig 2.

Justificativa walk-forward (vs k-fold aleatorio):
  K-fold embaralha eventos no tempo - leakage temporal massivo dado que
  rolling features capturam autocorrelacao. Walk-forward respeita a
  setatemporal real: treina no passado, prediz futuro.

Comportamento de features na fronteira:
  Eventos no inicio de cada split tem rolling features computadas com dados
  do split anterior. Isso e o comportamento desejado em producao (o modelo
  em 1/mai usa naturalmente as ultimas 24h, que incluem 30/abr) - NAO e
  leakage temporal.

Entradas:
  - Projeto/dados/features/v2.parquet (544.885 linhas x 57 colunas — 35 features + 3 targets + 19 originais)

Saidas:
  - Projeto/dados/features/v2_split.parquet (mesmas linhas + coluna `split`)
  - Projeto/relatorio/tabelas/split_temporal.csv (sumario CM 4.1)
  - Projeto/relatorio/figuras/fig07_janela_predicao.png
  - Projeto/relatorio/figuras/fig08_split_temporal.png

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/06_split.py
"""
from datetime import datetime
from pathlib import Path
import time

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import polars as pl


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ARQ_V2 = ROOT / "dados" / "features" / "v2.parquet"
ARQ_V2_SPLIT = ROOT / "dados" / "features" / "v2_split.parquet"
ARQ_TAB_SPLIT = ROOT / "relatorio" / "tabelas" / "split_temporal.csv"
ARQ_FIG7 = ROOT / "relatorio" / "figuras" / "fig07_janela_predicao.png"
ARQ_FIG8 = ROOT / "relatorio" / "figuras" / "fig08_split_temporal.png"

# ---------------------------------------------------------------------------
# Constantes - cortes temporais
# ---------------------------------------------------------------------------
DATA_VAL_INI = datetime(2025, 5, 1)   # treino: Data_Evento < DATA_VAL_INI
DATA_TEST_INI = datetime(2025, 6, 1)  # val: <  DATA_TEST_INI; teste: >=

# ---------------------------------------------------------------------------
# Expectativas (validadas empiricamente em sessao anterior)
# ---------------------------------------------------------------------------
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962

# Por split (eventos / DGs / positivos target_4h):
EXP_TRAIN = {"n": 394_971, "dgs": 13_456, "pos_4h": 132_877}
EXP_VAL =   {"n":  78_825, "dgs":  1_280, "pos_4h":  14_481}
EXP_TEST =  {"n":  71_089, "dgs":  5_226, "pos_4h":  12_038}

# ---------------------------------------------------------------------------
# Cores (consistentes com restante das figuras)
# ---------------------------------------------------------------------------
COR_TRAIN = "#1f77b4"  # azul - treino
COR_VAL = "#ff7f0e"    # laranja - validacao
COR_TEST = "#d62728"   # vermelho - teste
COR_DG = "#C73E1D"     # vermelho escuro - DGs (alinhado com 04_eda.py)
COR_DESTAQUE = "#2E86AB"  # azul para janela de predicao destacada


# ===========================================================================
# Etapa 1 - Carregar v2.parquet e validar
# ===========================================================================
def carregar_v2() -> pl.DataFrame:
    """Carrega a matriz final v2.parquet e valida shape + colunas-chave."""
    print("Etapa 1/5 - Carga de v2.parquet...")
    t0 = time.time()

    if not ARQ_V2.exists():
        raise FileNotFoundError(
            f"v2.parquet nao encontrado em {ARQ_V2}. "
            "Execute 05_features.py antes."
        )

    df = pl.read_parquet(ARQ_V2)
    elapsed = time.time() - t0

    print(f"  - Linhas: {df.height:,}")
    print(f"  - Colunas: {df.width}")
    print(f"  - Tempo: {elapsed:.1f}s")

    assert df.height == LINHAS_ESPERADAS, (
        f"Shape inesperado: {df.height} != {LINHAS_ESPERADAS}"
    )
    assert "Data_Evento" in df.columns, "Coluna Data_Evento ausente"
    assert "Is_Dont_Go" in df.columns, "Coluna Is_Dont_Go ausente"
    assert "target_4h" in df.columns, "Coluna target_4h ausente"

    n_dgs = df.filter(pl.col("Is_Dont_Go") == 1).height
    assert n_dgs == DGS_ESPERADOS, f"DGs inesperados: {n_dgs} != {DGS_ESPERADOS}"

    return df


# ===========================================================================
# Etapa 2 - Adicionar coluna split
# ===========================================================================
def adicionar_split(df: pl.DataFrame) -> pl.DataFrame:
    """Adiciona coluna `split` baseada em cortes temporais por mes."""
    print()
    print("Etapa 2/5 - Adicionando coluna `split`...")

    df = df.with_columns(
        pl.when(pl.col("Data_Evento") < DATA_VAL_INI).then(pl.lit("train"))
          .when(pl.col("Data_Evento") < DATA_TEST_INI).then(pl.lit("val"))
          .otherwise(pl.lit("test"))
          .alias("split")
    )

    contagens = (
        df.group_by("split")
        .agg(
            pl.len().alias("n"),
            (pl.col("Is_Dont_Go") == 1).sum().alias("dgs"),
            (pl.col("target_4h") == 1).sum().alias("pos_4h"),
        )
        .sort("split")
    )
    print(contagens)

    def _get(s, k):
        return contagens.filter(pl.col("split") == s)[k][0]

    # Asserções defensivas: contagens devem bater EXATAMENTE com a sessao anterior
    for split, exp in [("train", EXP_TRAIN), ("val", EXP_VAL), ("test", EXP_TEST)]:
        n_obs = _get(split, "n")
        dgs_obs = _get(split, "dgs")
        pos_obs = _get(split, "pos_4h")
        assert n_obs == exp["n"], f"{split}: n={n_obs} != esperado {exp['n']}"
        assert dgs_obs == exp["dgs"], f"{split}: dgs={dgs_obs} != esperado {exp['dgs']}"
        assert pos_obs == exp["pos_4h"], f"{split}: pos={pos_obs} != esperado {exp['pos_4h']}"

    # Soma deve fechar
    assert sum(_get(s, "n") for s in ["train", "val", "test"]) == LINHAS_ESPERADAS
    assert sum(_get(s, "dgs") for s in ["train", "val", "test"]) == DGS_ESPERADOS

    print("  - Asercoes OK (contagens batem com expectativa).")

    return df


# ===========================================================================
# Etapa 3 - Sumario por split (split_temporal.csv)
# ===========================================================================
def gerar_sumario(df: pl.DataFrame) -> pl.DataFrame:
    """Gera tabela de sumario por split (entregavel CM 4.1)."""
    print()
    print("Etapa 3/5 - Gerando split_temporal.csv...")

    sumario = (
        df.group_by("split")
        .agg(
            pl.col("Data_Evento").min().alias("data_ini"),
            pl.col("Data_Evento").max().alias("data_fim"),
            pl.len().alias("n_eventos"),
            (pl.col("Is_Dont_Go") == 1).sum().alias("n_dgs"),
            (pl.col("target_4h") == 1).sum().alias("n_positivos_4h"),
            pl.col("TAG").n_unique().alias("n_tags_unicas"),
        )
        .with_columns(
            (pl.col("n_dgs") / pl.col("n_eventos") * 100).round(4).alias("taxa_dg_pct"),
            (pl.col("n_positivos_4h") / pl.col("n_eventos") * 100).round(2).alias("taxa_pos_4h_pct"),
        )
        # Reordena para train/val/test
        .with_columns(
            pl.when(pl.col("split") == "train").then(1)
              .when(pl.col("split") == "val").then(2)
              .otherwise(3).alias("_ord")
        )
        .sort("_ord")
        .drop("_ord")
    )

    sumario.write_csv(ARQ_TAB_SPLIT)
    print(sumario)
    print(f"  - Salvo em {ARQ_TAB_SPLIT.relative_to(ROOT.parent)}")

    return sumario


# ===========================================================================
# Etapa 4 - Figura 7: diagrama da janela de predicao
# ===========================================================================
def gerar_fig7() -> None:
    """Diagrama conceitual da janela de predicao (CM 3.3)."""
    print()
    print("Etapa 4/5 - Gerando Fig 7 (janela de predicao)...")

    fig, ax = plt.subplots(figsize=(13, 5))

    # Eixo de tempo de -2h a +6h
    t_min, t_max = -2.0, 6.0
    ax.set_xlim(t_min, t_max)
    ax.set_ylim(-1.3, 1.6)

    # Linha base do tempo
    ax.axhline(0, color="#333", linewidth=1.2, zorder=1)

    # Janela de predicao destacada (0, 4]
    ax.axvspan(0, 4, ymin=0.42, ymax=0.78, color=COR_DESTAQUE, alpha=0.18, zorder=0)
    ax.annotate(
        "Janela de predicao (4h)\ntarget_4h = 1 se HOUVER DG aqui",
        xy=(2.0, 0.78), xytext=(2.0, 1.30),
        ha="center", va="center", fontsize=11, fontweight="bold",
        color=COR_DESTAQUE,
        arrowprops=dict(arrowstyle="-", color=COR_DESTAQUE, lw=1.5),
    )

    # Instante de decisao t=0
    ax.plot([0], [0], "o", color="black", markersize=11, zorder=5)
    ax.annotate(
        "Instante de decisao  t\n(evento de telemetria observado)",
        xy=(0, 0), xytext=(0, -0.95),
        ha="center", va="center", fontsize=10,
        arrowprops=dict(arrowstyle="->", color="black", lw=1.2),
    )

    # Eventos hipoteticos passados (informativos para rolling)
    np.random.seed(7)
    passados = [-1.8, -1.55, -1.25, -1.0, -0.7, -0.45, -0.2]
    for tp in passados:
        ax.plot([tp], [0], "o", color="#888", markersize=5, zorder=3)
    ax.annotate(
        "Eventos passados (entram nas rolling features)",
        xy=(-1.0, 0), xytext=(-1.0, 0.65),
        ha="center", va="center", fontsize=9, color="#555",
        arrowprops=dict(arrowstyle="-", color="#888", lw=0.8),
    )

    # Eventos hipoteticos dentro da janela (nao entram em features)
    dentro = [0.3, 0.7, 1.1, 1.5, 1.9, 2.3, 2.7, 3.1]
    for td in dentro:
        ax.plot([td], [0], "o", color="#bbb", markersize=4, zorder=3, alpha=0.6)

    # DG hipotetico dentro da janela
    t_dg = 2.5
    ax.plot([t_dg], [0], "X", color=COR_DG, markersize=18, markeredgewidth=2, zorder=5)
    ax.annotate(
        "DG futuro\n(target = 1)",
        xy=(t_dg, 0), xytext=(t_dg, -0.95),
        ha="center", va="center", fontsize=10, fontweight="bold",
        color=COR_DG,
        arrowprops=dict(arrowstyle="->", color=COR_DG, lw=1.2),
    )

    # DG fora da janela (target = 0 para esse evento t)
    t_fora = 5.2
    ax.plot([t_fora], [0], "X", color="#888", markersize=14, markeredgewidth=1.5, zorder=4, alpha=0.6)
    ax.annotate(
        "DG > 4h: nao conta\npara target_4h",
        xy=(t_fora, 0), xytext=(t_fora, -0.95),
        ha="center", va="center", fontsize=9, color="#555",
        arrowprops=dict(arrowstyle="->", color="#888", lw=1.0),
    )

    # Setas de extremidade da janela
    ax.annotate(
        "", xy=(4.0, 0.55), xytext=(0.05, 0.55),
        arrowprops=dict(arrowstyle="<->", color=COR_DESTAQUE, lw=2.2),
    )
    ax.text(0.05, 0.45, "t", fontsize=11, fontweight="bold", color=COR_DESTAQUE, va="top")
    ax.text(3.95, 0.45, "t+4h", fontsize=11, fontweight="bold", color=COR_DESTAQUE,
            ha="right", va="top")

    # Janela ABERTA no inicio: anotacao
    ax.annotate(
        "Janela ABERTA no inicio (>0): o\nproprio evento em t nao conta",
        xy=(0.05, 0.15), xytext=(-1.5, 1.30),
        ha="left", va="center", fontsize=9, style="italic", color="#444",
        arrowprops=dict(arrowstyle="->", color="#888", lw=0.9),
    )

    # Decoracao do eixo
    ax.set_xticks([-2, -1, 0, 1, 2, 3, 4, 5, 6])
    ax.set_xticklabels(["-2h", "-1h", "t", "+1h", "+2h", "+3h", "+4h", "+5h", "+6h"], fontsize=10)
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Tempo (horas relativas ao instante de decisao)", fontsize=11)
    ax.set_title(
        "Figura 7 - Janela de predicao do target operacional (target_4h)",
        fontsize=12, fontweight="bold", pad=14,
    )

    plt.tight_layout()
    fig.savefig(ARQ_FIG7, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  - Salvo em {ARQ_FIG7.relative_to(ROOT.parent)}")


# ===========================================================================
# Etapa 5 - Figura 8: estrategia de validacao temporal
# ===========================================================================
def gerar_fig8(df: pl.DataFrame, sumario: pl.DataFrame) -> None:
    """Diagrama da estrategia de validacao temporal (CM 4.1)."""
    print()
    print("Etapa 5/5 - Gerando Fig 8 (split temporal)...")

    # Estatisticas mes a mes
    mensal = (
        df.group_by(pl.col("Data_Evento").dt.month().alias("mes"))
        .agg(
            pl.len().alias("n_eventos"),
            (pl.col("Is_Dont_Go") == 1).sum().alias("n_dgs"),
            (pl.col("target_4h") == 1).sum().alias("n_pos_4h"),
            pl.col("split").first().alias("split"),
        )
        .sort("mes")
        .with_columns(
            (pl.col("n_dgs") / pl.col("n_eventos") * 100).alias("taxa_dg_pct"),
        )
    )

    meses_label = ["jan", "fev", "mar", "abr", "mai", "jun"]
    cor_por_mes = {
        "train": COR_TRAIN, "val": COR_VAL, "test": COR_TEST,
    }
    cores_mes = [cor_por_mes[s] for s in mensal["split"].to_list()]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(13, 7.5), sharex=True,
        gridspec_kw={"height_ratios": [3, 2], "hspace": 0.18},
    )

    # ---- Painel superior: eventos por mes coloridos por split ----
    x = np.arange(6)
    bars = ax1.bar(
        x, mensal["n_eventos"].to_list(),
        color=cores_mes, edgecolor="black", linewidth=0.6, width=0.7,
    )

    # Anotacao de DGs por mes acima de cada barra
    for i, (n_ev, n_dg) in enumerate(zip(
        mensal["n_eventos"].to_list(), mensal["n_dgs"].to_list()
    )):
        ax1.text(
            i, n_ev * 1.02, f"{n_ev:,}\neventos\n({n_dg:,} DGs)",
            ha="center", va="bottom", fontsize=8.5,
        )

    # Linhas verticais nos cortes (entre abr-mai e mai-jun)
    ax1.axvline(3.5, color="black", linestyle="--", linewidth=1.5, alpha=0.7)
    ax1.axvline(4.5, color="black", linestyle="--", linewidth=1.5, alpha=0.7)
    ax1.text(3.5, ax1.get_ylim()[1] * 0.92, " 2025-05-01 ",
             rotation=90, fontsize=8.5, va="top", ha="right",
             bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))
    ax1.text(4.5, ax1.get_ylim()[1] * 0.92, " 2025-06-01 ",
             rotation=90, fontsize=8.5, va="top", ha="right",
             bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))

    ax1.set_ylabel("Eventos no mes (pos-filtro Informacional)", fontsize=10.5)
    ax1.set_title(
        "Figura 8 - Estrategia de validacao temporal: split walk-forward jan-abr / mai / jun",
        fontsize=12, fontweight="bold", pad=12,
    )
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.grid(axis="y", linestyle=":", alpha=0.4)
    # Ajusta limite y para acomodar anotacoes
    ax1.set_ylim(0, max(mensal["n_eventos"].to_list()) * 1.22)

    # Legenda dos splits + estatisticas
    train_n = sumario.filter(pl.col("split") == "train")["n_eventos"][0]
    val_n   = sumario.filter(pl.col("split") == "val")["n_eventos"][0]
    test_n  = sumario.filter(pl.col("split") == "test")["n_eventos"][0]
    train_dg = sumario.filter(pl.col("split") == "train")["n_dgs"][0]
    val_dg   = sumario.filter(pl.col("split") == "val")["n_dgs"][0]
    test_dg  = sumario.filter(pl.col("split") == "test")["n_dgs"][0]
    handles = [
        mpatches.Patch(color=COR_TRAIN,
            label=f"Treino (jan-abr): {train_n:,} eventos / {train_dg:,} DGs"),
        mpatches.Patch(color=COR_VAL,
            label=f"Validacao (mai):  {val_n:,} eventos / {val_dg:,} DGs"),
        mpatches.Patch(color=COR_TEST,
            label=f"Teste (jun):     {test_n:,} eventos / {test_dg:,} DGs"),
    ]
    ax1.legend(handles=handles, loc="upper right", fontsize=9.5, framealpha=0.95)

    # ---- Painel inferior: drift = taxa de DG por mes ----
    ax2.plot(
        x, mensal["taxa_dg_pct"].to_list(),
        marker="o", linewidth=2.2, color=COR_DG, markersize=9, zorder=3,
    )
    for i, txt in enumerate(mensal["taxa_dg_pct"].to_list()):
        ax2.text(i, txt + 0.25, f"{txt:.2f}%", ha="center", fontsize=9.5,
                 color=COR_DG, fontweight="bold")

    # Replica linhas de corte para alinhamento visual
    ax2.axvline(3.5, color="black", linestyle="--", linewidth=1.5, alpha=0.7)
    ax2.axvline(4.5, color="black", linestyle="--", linewidth=1.5, alpha=0.7)

    ax2.set_xticks(x)
    ax2.set_xticklabels(meses_label, fontsize=10.5)
    ax2.set_xlabel("Mes de 2025", fontsize=10.5)
    ax2.set_ylabel("Taxa de DG por mes (%)", fontsize=10.5, color=COR_DG)
    ax2.tick_params(axis="y", labelcolor=COR_DG)
    ax2.set_ylim(0, max(mensal["taxa_dg_pct"].to_list()) * 1.35)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.grid(axis="y", linestyle=":", alpha=0.4)

    # Anotacao do drift
    ax2.annotate(
        "Drift mes-a-mes:\nteste (jun) tem 2x a taxa\nde DG do treino medio\n-> motiva avaliacao\nestratificada em W7",
        xy=(5, mensal["taxa_dg_pct"][-1]),
        xytext=(4.0, mensal["taxa_dg_pct"].max() * 1.15),
        ha="center", va="center", fontsize=8.5, color="#444",
        arrowprops=dict(arrowstyle="->", color="#888", lw=1.0),
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#888", alpha=0.9),
    )

    plt.tight_layout()
    fig.savefig(ARQ_FIG8, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  - Salvo em {ARQ_FIG8.relative_to(ROOT.parent)}")


# ===========================================================================
# Etapa final - Persistencia
# ===========================================================================
def persistir(df: pl.DataFrame) -> None:
    """Salva v2_split.parquet com coluna `split` adicionada."""
    print()
    print(f"Persistindo {ARQ_V2_SPLIT.name}...")
    df.write_parquet(ARQ_V2_SPLIT)
    tamanho_mb = ARQ_V2_SPLIT.stat().st_size / 1024 / 1024
    print(f"  - Shape: {df.shape}")
    print(f"  - Tamanho: {tamanho_mb:.1f} MB")
    print(f"  - Caminho: {ARQ_V2_SPLIT.relative_to(ROOT.parent)}")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("06_split.py - Split temporal walk-forward + Figs 7-8 (W4 CM 4.1)")
    print("=" * 70)

    df = carregar_v2()
    df = adicionar_split(df)
    sumario = gerar_sumario(df)
    gerar_fig7()
    gerar_fig8(df, sumario)
    persistir(df)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
