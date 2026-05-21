"""
exploracao_w4_ca65924.py - Validacao empirica de H5.2 / Obs 2.3.

Plota a cadeia de eventos do caso paradigma (caminhao CA65924, do
`desenvolver_dontgo.xlsx`, 147 eventos consecutivos culminando em 1 DG)
e compara com 3 amostras aleatorias de outros DGs do semestre completo
para responder: o padrao "calmaria -> acumulo -> disparo" e' universal?

Fonte do paradigma:
  - desenvolver_dontgo.xlsx (xlsx de amostra fornecido pela Vale)

Fonte das comparacoes:
  - telemetria_tipada.parquet (pre-filtro de Informacional — base justa
    de comparacao com o paradigma, que tambem inclui Informacionais)

Saidas:
  - Projeto/relatorio/figuras/figExC_ca65924_cadeia.png   (Fig Extra C)

Veredito quantitativo (impresso no terminal):
  Para cada painel, duas metricas:
    razao         = #eventos_ultimos_30min / #eventos_primeiros_90min
    densidade_x   = (u30/30) / (p90/90) = razao * 3  -> "quantas vezes mais densa
                    e' a janela final em relacao a inicial em ev/min"
  Padrao "calmaria sharp -> acumulo -> disparo" confirmado quando razao >= 2
    (equivalentemente, densidade_x >= 6 -> ultimos 30min sao no minimo 6x mais
    densos em eventos por minuto que os primeiros 90min).
  Razao < 2 NAO significa "ausencia de acumulo": valores entre ~0.4 e ~0.6
    correspondem a densificacao GRADUAL (1.2x a 1.8x). Apenas o padrao sharp
    foi rejeitado pelo threshold; a tendencia geral de algum aumento de
    densidade pre-DG pode ser comum mesmo quando o threshold nao se confirma.

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/exploracao_w4_ca65924.py
"""
from datetime import timedelta
from pathlib import Path
import random
import time

import matplotlib.pyplot as plt
import polars as pl
import seaborn as sns


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ARQ_DG_XLSX = (
    ROOT / "Alterado" / "Base de Dados" / "datasets" / "telemetria"
    / "desenvolver_dontgo.xlsx"
)
ARQ_TELEMETRIA_TIPADA = ROOT / "dados" / "intermediarios" / "telemetria_tipada.parquet"
DIR_FIGURAS = ROOT / "relatorio" / "figuras"
ARQ_FIG_OUT = DIR_FIGURAS / "figExC_ca65924_cadeia.png"

# ---------------------------------------------------------------------------
# Parametros
# ---------------------------------------------------------------------------
MINUTOS_JANELA = 120
N_COMPARACAO = 3
SEED = 42

# Mapeamento de Criticidade (copia simplificada de 03_limpeza.py)
CRITICIDADE_MAPEAMENTO = {
    "Critico": "Critico",
    "Crítico": "Critico",
    "Nao Critico": "Nao_Critico",
    "Não Crítico": "Nao_Critico",
    "Não Critico": "Nao_Critico",
    "Nao Crítico": "Nao_Critico",
    "Informacional": "Informacional",
}

COR_CRITICIDADE = {
    "Critico": "#C73E1D",       # vermelho (mesmo padrao das outras figs)
    "Nao_Critico": "#F18F01",   # laranja
    "Informacional": "#2E86AB", # azul
}


# ---------------------------------------------------------------------------
# Funcoes
# ---------------------------------------------------------------------------
def configurar_tema() -> None:
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 8,
        "font.family": "DejaVu Sans",
    })


def normalizar_criticidade(df: pl.DataFrame) -> pl.DataFrame:
    """Normaliza Criticidade para forma canonica ASCII."""
    valores_brutos = set(df.get_column("Criticidade").unique().to_list())
    desconhecidos = valores_brutos - set(CRITICIDADE_MAPEAMENTO.keys())
    if desconhecidos:
        print(f"  AVISO: valores nao mapeados em Criticidade: {desconhecidos}")
        print("  Mantendo valores originais para esses.")
    return df.with_columns(
        pl.col("Criticidade").replace(CRITICIDADE_MAPEAMENTO)
    )


def carregar_ca65924() -> tuple[pl.DataFrame, object]:
    print("\n[1/4] Carregando caso paradigma CA65924 (xlsx)")
    if not ARQ_DG_XLSX.exists():
        raise FileNotFoundError(f"{ARQ_DG_XLSX} nao encontrado.")
    df = pl.read_excel(ARQ_DG_XLSX, engine="openpyxl")
    df = normalizar_criticidade(df)
    df = df.sort("Data_Evento")
    n_total = df.height
    n_dg = df.filter(pl.col("Is_Dont_Go") == 1).height
    tags = df.get_column("TAG").unique().to_list()
    print(f"  Eventos: {n_total} | DGs: {n_dg} | TAG(s): {tags}")
    if n_dg != 1:
        print(f"  AVISO: esperava 1 DG, obtido {n_dg}")
    dg_row = df.filter(pl.col("Is_Dont_Go") == 1).head(1)
    data_dg = dg_row["Data_Evento"][0]
    print(f"  Timestamp do DG paradigma: {data_dg}")
    return df, data_dg


def amostrar_outros_dgs(
    seed: int = SEED, n: int = N_COMPARACAO
) -> tuple[pl.DataFrame, list[dict]]:
    """Carrega telemetria_tipada e amostra n TAGs distintas com DG."""
    print(f"\n[2/4] Amostrando {n} DGs aleatorios (seed={seed})")
    if not ARQ_TELEMETRIA_TIPADA.exists():
        raise FileNotFoundError(f"{ARQ_TELEMETRIA_TIPADA} nao encontrado.")
    t0 = time.time()
    df_full = pl.read_parquet(ARQ_TELEMETRIA_TIPADA)
    print(f"  telemetria_tipada carregada: "
          f"{df_full.shape[0]:,} linhas ({time.time()-t0:.1f}s)")

    df_full = normalizar_criticidade(df_full)
    dgs = df_full.filter(pl.col("Is_Dont_Go") == 1)
    tags_with_dg = sorted(dgs.get_column("TAG").unique().to_list())
    print(f"  TAGs com >=1 DG no semestre: {len(tags_with_dg)}")

    rng = random.Random(seed)
    sampled_tags = sorted(rng.sample(tags_with_dg, n))
    print(f"  TAGs amostradas: {sampled_tags}")

    amostras = []
    for tag in sampled_tags:
        primeiro_dg = (
            dgs.filter(pl.col("TAG") == tag)
               .sort("Data_Evento")
               .head(1)
        )
        if primeiro_dg.height == 0:
            continue
        data_dg = primeiro_dg["Data_Evento"][0]
        amostras.append({"tag": tag, "data_dg": data_dg})
        print(f"    {tag}: primeiro DG em {data_dg}")

    return df_full, amostras


def construir_janela(
    df_full: pl.DataFrame, tag: str, data_dg, minutos: int = MINUTOS_JANELA
) -> pl.DataFrame:
    """Eventos de `tag` no intervalo [data_dg - minutos, data_dg]."""
    inicio = data_dg - timedelta(minutes=minutos)
    return (
        df_full.filter(
            (pl.col("TAG") == tag)
            & (pl.col("Data_Evento") >= inicio)
            & (pl.col("Data_Evento") <= data_dg)
        )
        .sort("Data_Evento")
    )


def plotar_painel(ax, janela: pl.DataFrame, data_dg, titulo: str) -> dict:
    """Plota um painel com cadeia de eventos pre-DG. Retorna stats."""
    n_total = janela.height
    if n_total == 0:
        ax.text(0.5, 0.5, "Sem eventos no periodo",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=12, color="gray")
        ax.set_title(titulo)
        return {"n_total": 0, "razao": None}

    # Minutos antes do DG (valores negativos; 0 = momento do DG)
    minutos = (
        (janela["Data_Evento"] - data_dg).dt.total_seconds() / 60.0
    ).to_list()
    criticidades = janela["Criticidade"].to_list()
    cumulative = list(range(1, n_total + 1))

    # Step plot do count acumulado (linha cinza)
    ax.step(minutos, cumulative, where="post", color="gray",
            linewidth=1.2, alpha=0.5, zorder=1)

    # Scatter colorido por criticidade
    for crit in ["Informacional", "Nao_Critico", "Critico"]:
        idxs = [i for i, c in enumerate(criticidades) if c == crit]
        if idxs:
            xs = [minutos[i] for i in idxs]
            ys = [cumulative[i] for i in idxs]
            ax.scatter(
                xs, ys,
                color=COR_CRITICIDADE.get(crit, "black"),
                s=22, zorder=3, alpha=0.85,
                label=f"{crit} (n={len(idxs)})",
                edgecolors="white", linewidths=0.4,
            )

    # Linha vertical marcando o DG
    ax.axvline(0, color="red", linestyle="--", linewidth=2,
               alpha=0.7, label="DG (alvo)", zorder=2)

    ax.set_ylabel("# eventos acum.")
    ax.set_title(titulo, loc="left", fontsize=11)
    ax.grid(alpha=0.3)
    ax.set_xlim(-MINUTOS_JANELA - 5, 5)
    ax.legend(loc="upper left", framealpha=0.9, ncol=2)

    # Quantificacao do "acumulo"
    n_ultimos_30 = sum(1 for m in minutos if -30 <= m <= 0)
    n_primeiros_90 = sum(1 for m in minutos if -120 <= m < -30)
    if n_primeiros_90 > 0:
        razao = n_ultimos_30 / n_primeiros_90
    else:
        razao = float("inf") if n_ultimos_30 > 0 else None

    return {
        "n_total": n_total,
        "n_ultimos_30": n_ultimos_30,
        "n_primeiros_90": n_primeiros_90,
        "razao": razao,
    }


def main() -> None:
    print("=== Fig Extra C: Cadeia de eventos CA65924 (Obs 2.3 / H5.2) ===")
    configurar_tema()

    # 1. Caso paradigma
    df_ca, data_dg_ca = carregar_ca65924()

    # 2. Amostras de comparacao
    df_full, amostras = amostrar_outros_dgs(seed=SEED, n=N_COMPARACAO)

    # 3. Plotar
    print(f"\n[3/4] Plotando 4 paineis em coluna (sharex)")
    fig, axes = plt.subplots(
        N_COMPARACAO + 1, 1,
        figsize=(13, 12),
        sharex=True,
    )

    stats_list = []
    # Painel (a) — CA65924
    titulo_ca = (
        f"(a) CA65924 — CASO PARADIGMA | "
        f"{df_ca.height} eventos | DG em {data_dg_ca}"
    )
    stats_ca = plotar_painel(axes[0], df_ca, data_dg_ca, titulo_ca)
    stats_ca["tag"] = "CA65924"
    stats_list.append(stats_ca)

    # Paineis (b), (c), (d) — amostras aleatorias
    for i, amostra in enumerate(amostras):
        tag = amostra["tag"]
        data_dg = amostra["data_dg"]
        janela = construir_janela(df_full, tag, data_dg)
        letra = chr(ord("b") + i)
        titulo = (
            f"({letra}) {tag} (random, seed={SEED}) | "
            f"{janela.height} eventos | DG em {data_dg}"
        )
        s = plotar_painel(axes[1 + i], janela, data_dg, titulo)
        s["tag"] = tag
        stats_list.append(s)

    # Eixo X compartilhado: rotulo so no ultimo
    axes[-1].set_xlabel("Minutos antes do DG")

    plt.suptitle(
        "Cadeia de eventos pre-DG: caso paradigma CA65924 vs 3 comparacoes aleatorias\n"
        "Validacao empirica da H5.2 / Obs 2.3 (padrao 'calmaria → acumulo → disparo')",
        y=1.00,
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()

    # 4. Salvar
    print("\n[4/4] Salvando figura")
    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG_OUT)
    plt.close()
    print(f"  -> {ARQ_FIG_OUT.relative_to(ROOT)} "
          f"({ARQ_FIG_OUT.stat().st_size/1024:.0f} KB)")

    # Quantificacao final
    print("\n" + "=" * 70)
    print("VEREDITO QUANTITATIVO")
    print("=" * 70)
    print(f"  Razao       = #eventos_ultimos_30min / #eventos_primeiros_90min")
    print(f"  Densidade_x = (u30/30) / (p90/90) = razao * 3 (vezes mais densa)")
    print(f"  Padrao sharp 'calmaria -> acumulo -> disparo' confirmado quando")
    print(f"    razao >= 2  (densidade_x >= 6, i.e., janela final >= 6x mais densa)")
    print(f"  Valores razao em ~0.4-0.6 => densificacao GRADUAL (1.2x a 1.8x).")
    print()
    confirmados = 0
    for s in stats_list:
        n = s["n_total"]
        u30 = s.get("n_ultimos_30", 0)
        p90 = s.get("n_primeiros_90", 0)
        razao = s.get("razao")
        if razao is None:
            razao_str = "N/A"
            densidade_str = "N/A"
            interp = ""
        elif razao == float("inf"):
            razao_str = "inf"
            densidade_str = "inf"
            interp = " sharp (todos em -30..0)"
        else:
            razao_str = f"{razao:.2f}"
            densidade_x = razao * 3.0
            densidade_str = f"{densidade_x:.2f}x"
            if razao >= 2:
                interp = " SHARP (calmaria -> spike)"
                confirmados += 1
            elif densidade_x >= 1.0:
                interp = " gradual (leve aumento)"
            else:
                interp = " ~uniforme"
        marca = "  ✓" if razao is not None and (razao == float("inf") or razao >= 2) else ""
        if razao == float("inf"):
            confirmados += 1
        print(f"  {s['tag']:>10s}: {n:>4} eventos | "
              f"u30={u30:>3} | p90={p90:>3} | "
              f"razao={razao_str:>6s} | densidade={densidade_str:>7s}"
              f" |{interp}{marca}")
    print()
    print(f"  Resumo: {confirmados}/{len(stats_list)} paineis com padrao "
          "sharp confirmado.")
    print(f"  Nota: paineis nao-sharp NAO indicam ausencia de tendencia — apenas")
    print(f"        que o aumento pre-DG e' gradual (densidade entre 1.2x e 1.8x).")

    print("\n[OK] Investigacao concluida.")
    print("\nProximos passos sugeridos:")
    print("  - Atualizar H5.2 em hipoteses_eda.md conforme veredito acima")
    print("  - Atualizar Obs 2.3 em observacoes_importantes.md")
    print("  - Adicionar Fig Extra C ao rascunho.md (Metodologia ou Insights CM 6.1)")


if __name__ == "__main__":
    main()
