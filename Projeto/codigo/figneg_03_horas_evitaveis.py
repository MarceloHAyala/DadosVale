# -*- coding: utf-8 -*-
"""
figneg_03_horas_evitaveis.py - Figura de NEGÓCIO #3: Horas de parada evitável.

Traduz as métricas do modelo (Recall@0.5, AUC-PR) em VALOR OPERACIONAL:
quantas horas-equipamento de parada não planejada poderiam ter sido
convertidas em inspeção preventiva planejada se o v3 estivesse em
deployment no semestre observado.

Apresenta TRÊS cenários com premissas explícitas (não inventa números):

  CONSERVADOR — só os PRIMEIROS DGs em equipamentos arbitrários (Recall 21%)
  REALISTA    — Recall geral do v3 (75%) ponderado pelos 19.962 DGs do semestre
  OTIMISTA    — Recall geral + redução adicional via auditoria proativa do CA65926

Premissas declaradas:
  - Tempo médio de parada não planejada por DG: 4h (1 turno de manutenção corretiva)
  - Tempo médio de inspeção preventiva planejada: 1,5h (janela de troca de turno)
  - Diferença = 2,5h de operação preservada por DG antecipado
  - DGs do semestre = 19.962 (telemetria_limpa, jan-jun/2025)

Saídas:
  - relatorio/figuras/figNeg03_horas_parada_evitavel.png
  - relatorio/tabelas/horas_evitaveis_cenarios.csv

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/figneg_03_horas_evitaveis.py
"""
from pathlib import Path
import matplotlib.pyplot as plt
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figNeg03_horas_parada_evitavel.png"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "horas_evitaveis_cenarios.csv"


# Premissas declaradas (todas com referência aos achados do projeto)
TOTAL_DGs_SEMESTRE = 19_962          # telemetria_limpa, jan-jun/2025
HORAS_PARADA_NAO_PLANEJADA = 4.0     # premissa operacional (1 turno corretivo)
HORAS_INSPECAO_PREVENTIVA = 1.5      # premissa operacional (janela troca de turno)
HORAS_EVITADAS_POR_DG = HORAS_PARADA_NAO_PLANEJADA - HORAS_INSPECAO_PREVENTIVA  # 2,5h


# Cenários
CENARIOS = [
    {
        "nome": "Conservador",
        "cor": "#ff8f00",
        "descricao": "Apenas primeiros DGs em equipamentos arbitrários",
        "recall": 0.21,
        "frac_dgs_alcancaveis": 1.0,  # aplicado sobre o total de DGs
        "premissa_extra": "Recall@0.5 do v3 no subgrupo primeiro_DG (4,3% → 21,1%)",
    },
    {
        "nome": "Realista",
        "cor": "#1976d2",
        "descricao": "Recall geral do v3 ponderado pelo semestre",
        "recall": 0.75,
        "frac_dgs_alcancaveis": 1.0,
        "premissa_extra": "Recall@0.5 do v3 no geral (0,7527 no test set jun/2025)",
    },
    {
        "nome": "Otimista",
        "cor": "#2e7d32",
        "descricao": "Realista + auditoria proativa do CA65926 (sinal de março)",
        "recall": 0.75,
        "frac_dgs_alcancaveis": 1.0,
        "extra_dgs_evitados": 4923 * 0.50,  # se CA65926 fosse auditado em março, ~50% dos 4923 DGs do semestre evitados
        "premissa_extra": "Recall geral + auditoria do CA65926 em março (50% dos 4.923 DGs evitáveis)",
    },
]


def calcular_cenario(c: dict) -> dict:
    dgs_alcancaveis = TOTAL_DGs_SEMESTRE * c["frac_dgs_alcancaveis"]
    dgs_antecipados = dgs_alcancaveis * c["recall"]
    dgs_nao_antecipados = TOTAL_DGs_SEMESTRE - dgs_antecipados

    # Horas-equipamento de parada
    horas_sem_modelo = TOTAL_DGs_SEMESTRE * HORAS_PARADA_NAO_PLANEJADA
    horas_antecipadas = dgs_antecipados * HORAS_INSPECAO_PREVENTIVA
    horas_nao_antecipadas = dgs_nao_antecipados * HORAS_PARADA_NAO_PLANEJADA
    horas_com_modelo = horas_antecipadas + horas_nao_antecipadas

    # Cenário otimista adiciona evitabilidade extra do CA65926
    extra_evitado = c.get("extra_dgs_evitados", 0)
    horas_com_modelo -= extra_evitado * HORAS_EVITADAS_POR_DG

    horas_evitadas = horas_sem_modelo - horas_com_modelo
    return {
        "cenario": c["nome"],
        "recall": c["recall"],
        "dgs_antecipados": int(dgs_antecipados + extra_evitado),
        "horas_sem_modelo": round(horas_sem_modelo, 0),
        "horas_com_modelo": round(horas_com_modelo, 0),
        "horas_evitadas": round(horas_evitadas, 0),
        "pct_reducao": round(100 * horas_evitadas / horas_sem_modelo, 1),
        "premissa": c["premissa_extra"],
    }


def main() -> None:
    print("Calculando 3 cenários de horas de parada evitável...")
    resultados = [calcular_cenario(c) for c in CENARIOS]

    # Tabela
    pl.from_dicts(resultados).write_csv(ARQ_TAB)
    print(f"Salvo: {ARQ_TAB.relative_to(ROOT.parent)}")
    print()
    for r in resultados:
        print(f"  {r['cenario']:<12s}: {r['dgs_antecipados']:>6,} DGs antecipados | "
              f"{r['horas_evitadas']:>7,.0f}h evitadas | redução {r['pct_reducao']:.1f}%")
    print()

    # Figura — 2 painéis
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7),
                                    gridspec_kw={"width_ratios": [1.2, 1]})

    # Painel A — barras de horas com vs sem modelo, por cenário
    nomes = [r["cenario"] for r in resultados]
    h_sem = [r["horas_sem_modelo"] for r in resultados]
    h_com = [r["horas_com_modelo"] for r in resultados]
    h_evit = [r["horas_evitadas"] for r in resultados]
    cores = [c["cor"] for c in CENARIOS]

    x = list(range(3))
    largura = 0.35
    ax1.bar([i - largura / 2 for i in x], h_sem, largura,
             label=f"Sem modelo ({HORAS_PARADA_NAO_PLANEJADA:.0f}h × {TOTAL_DGs_SEMESTRE:,} DGs)",
             color="#999999", edgecolor="white", linewidth=1.5)
    bars_com = ax1.bar([i + largura / 2 for i in x], h_com, largura,
                        label="Com v3 em deployment",
                        color=cores, edgecolor="white", linewidth=1.5)

    # Anotar redução absoluta acima de cada par
    for i, (s, c, e, r) in enumerate(zip(h_sem, h_com, h_evit, resultados)):
        ax1.annotate(
            f"−{e:,.0f}h\n({r['pct_reducao']:.0f}%)",
            xy=(i, max(s, c) + max(h_sem) * 0.03),
            ha="center", fontsize=11, fontweight="bold", color=cores[i],
            bbox=dict(boxstyle="round,pad=0.3",
                      fc="#ffffff", ec=cores[i], lw=1.5, alpha=0.95),
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels(nomes, fontsize=12, fontweight="bold")
    ax1.set_ylabel("Horas-equipamento de parada no semestre", fontsize=12)
    ax1.set_title("(a) Horas de parada no semestre — com vs sem modelo",
                  fontsize=13, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=10, framealpha=0.95)
    ax1.tick_params(axis="both", labelsize=11)
    ax1.grid(True, axis="y", alpha=0.3)
    ax1.set_ylim(0, max(h_sem) * 1.18)

    # Painel B — texto com premissas e cenários
    ax2.axis("off")
    ax2.set_title("Premissas e cenários", fontsize=13, fontweight="bold",
                  loc="left", pad=10)

    txt_premissas = (
        f"Premissas operacionais (declaradas):\n"
        f"  • Total de DGs no semestre: {TOTAL_DGs_SEMESTRE:,}\n"
        f"  • Parada não planejada (corretiva): {HORAS_PARADA_NAO_PLANEJADA:.1f}h por DG\n"
        f"  • Inspeção preventiva (planejada):  {HORAS_INSPECAO_PREVENTIVA:.1f}h por DG\n"
        f"  • Ganho por DG antecipado: {HORAS_EVITADAS_POR_DG:.1f}h preservadas"
    )
    ax2.text(0.0, 0.95, txt_premissas, fontsize=10.5, va="top",
             family="monospace",
             bbox=dict(boxstyle="round,pad=0.6", fc="#f5f5f5", ec="#cccccc"))

    # Cenários
    y_pos = 0.62
    for c, r in zip(CENARIOS, resultados):
        bloco = (
            f"{c['nome'].upper()} — {c['descricao']}\n"
            f"  Recall assumido: {r['recall']*100:.0f}%   "
            f"DGs antecipados: {r['dgs_antecipados']:,}\n"
            f"  Horas evitadas: {r['horas_evitadas']:,.0f}h ({r['pct_reducao']:.1f}% de redução)\n"
            f"  Fonte: {r['premissa']}"
        )
        ax2.text(0.0, y_pos, bloco, fontsize=9.5, va="top",
                 color=c["cor"], fontweight="normal")
        y_pos -= 0.22

    fig.suptitle(
        "Figura — Valor operacional do modelo: horas de parada evitáveis no semestre\n"
        f"Cenários com premissas explícitas — total atual: {TOTAL_DGs_SEMESTRE * HORAS_PARADA_NAO_PLANEJADA:,.0f}h-equipamento de parada não planejada",
        fontsize=13, fontweight="bold", y=1.00,
    )

    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
