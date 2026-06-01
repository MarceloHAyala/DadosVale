# -*- coding: utf-8 -*-
"""
18_top100_fps_if.py - Análise "o que a regra CMA não vê" (leitura inversa Risco 3.3).

Identifica os top 100 eventos no test set com MAIOR anomaly_score do Isolation
Forest que NÃO foram rotulados como DG pela CMA. Estes são candidatos a
"DGs perdidos pelo CMA" — anomalias estatísticas reais no espaço de features
que escaparam às 82 regras de negócio da CMA.

Para cada um dos top-100:
  - Examina os 4h seguintes: há concentração de eventos Crítico/Não-Crítico
    acima da base do parque?
  - Há sinais antecipativos próximos (alarmes Família 6 elevados)?
  - Cruza com TAGs/frotas — algum grupo aparece desproporcionalmente?

Veredito honesto em 1 parágrafo: o sinal não-supervisionado complementa
(modos de falha além da regra), dispensa (recupera DGs sem ver rótulo), ou
apenas duplica o sinal da regra CMA?

Entradas:
  - dados/features/v3.parquet
  - modelos/shap_values_v2_test.npy (ou IF para anomaly_score)
  - modelos/isolation_forest.joblib (carrega o modelo IF treinado em W6)

Saídas:
  - relatorio/tabelas/top100_fps_if.csv (top 100 com contexto)
  - relatorio/tabelas/top100_fps_if_concentracoes.csv (perfis por TAG/frota)
  - relatorio/figuras/figExH_top100_fps_if.png (3 painéis)

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/18_top100_fps_if.py
"""
from pathlib import Path
import warnings

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_IF = ROOT / "modelos" / "isolation_forest.joblib"

ARQ_TAB = ROOT / "relatorio" / "tabelas" / "top100_fps_if.csv"
ARQ_CONC = ROOT / "relatorio" / "tabelas" / "top100_fps_if_concentracoes.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExH_top100_fps_if.png"

N_TOP = 100
HORIZONTE_H = 4.0


def main():
    print("=" * 70)
    print("18_top100_fps_if.py - O que a regra CMA não vê (leitura inversa Risco 3.3)")
    print("=" * 70)

    print("\nCarregando v3.parquet + IF...")
    df = pl.read_parquet(ARQ_V3)
    test = df.filter(pl.col("split") == "test")
    print(f"  Test set: n={test.height:,}")

    art = joblib.load(ARQ_IF)
    iforest = art["modelo"]
    scaler = art["scaler"]
    imputacao = art["imputacao"]
    features = art["features"]
    print(f"  IF: {len(features)} features")

    # Aplicar imputação + scaler + predição
    pdf = test.to_pandas()
    pdf["valor_disponivel"] = pdf["valor_disponivel"].astype(np.int8)
    for col, val in imputacao.items():
        pdf[col] = pdf[col].fillna(val)
    pdf = pdf.fillna(0)
    dummies = pd.get_dummies(pdf[["turno", "estado_pre_evento"]],
                              prefix=["turno", "estado_pre_evento"],
                              drop_first=True, dtype=np.int8)
    pdf = pd.concat([pdf.drop(columns=["turno", "estado_pre_evento"]), dummies], axis=1)
    for col in features:
        if col not in pdf.columns:
            pdf[col] = 0
    # IF aplicou scaler em TODAS as features no treino (11_isolation_forest.py)
    X_df = pdf[features].copy()
    X_scaled = scaler.transform(X_df)
    anomaly_score = -iforest.decision_function(X_scaled)
    test = test.with_columns(pl.Series("anomaly_score", anomaly_score))

    # FPs do IF: top anomaly_score que NÃO são DG
    print(f"\nIdentificando top {N_TOP} eventos com maior anomaly_score que NÃO são DG...")
    fps = (
        test.filter(pl.col("Is_Dont_Go") == 0)
        .sort("anomaly_score", descending=True)
        .head(N_TOP)
        .with_columns(
            pl.col("Data_Evento").dt.strftime("%Y-%m-%d %H:%M").alias("data_str"),
        )
    )

    # Para cada FP, contar eventos nos PRÓXIMOS 4h do MESMO TAG
    print(f"\nPara cada FP, contando eventos nos próximos {HORIZONTE_H}h da mesma TAG...")
    test_completo_dict = {}
    test_sorted = test.sort(["TAG", "Data_Evento"])
    test_pdf_all = test_sorted.select(["TAG", "Data_Evento", "Is_Dont_Go",
                                        "Criticidade", "Alarme"]).to_pandas()

    fps_pdf = fps.select(["TAG", "Data_Evento", "anomaly_score", "Tag_Frota",
                          "Tipo", "Criticidade", "Alarme",
                          "qtd_alarmes_nivel_muito_alto_360min"]).to_pandas()

    contexto_4h = []
    for _, row in fps_pdf.iterrows():
        tag = row["TAG"]
        t = row["Data_Evento"]
        # Eventos do mesmo TAG nas próximas 4h
        mask = ((test_pdf_all["TAG"] == tag)
                & (test_pdf_all["Data_Evento"] > t)
                & (test_pdf_all["Data_Evento"] <= t + pd.Timedelta(hours=HORIZONTE_H)))
        proximos = test_pdf_all[mask]
        n_prox = len(proximos)
        n_critico = int((proximos["Criticidade"] == "Critico").sum())
        n_nao_critico = int((proximos["Criticidade"] == "Nao_Critico").sum())
        n_dg = int(proximos["Is_Dont_Go"].sum())
        contexto_4h.append({
            "n_eventos_proximos_4h": n_prox,
            "n_critico_proximos_4h": n_critico,
            "n_nao_critico_proximos_4h": n_nao_critico,
            "n_DG_proximos_4h": n_dg,  # se >0, é DG futuro real que CMA ATÉ pegou
        })
    ctx_df = pd.DataFrame(contexto_4h)
    fps_pdf = pd.concat([fps_pdf.reset_index(drop=True), ctx_df], axis=1)

    # Salvar tabela
    cols_out = ["TAG", "Tag_Frota", "Tipo", "Data_Evento", "Criticidade", "Alarme",
                "anomaly_score", "qtd_alarmes_nivel_muito_alto_360min",
                "n_eventos_proximos_4h", "n_critico_proximos_4h",
                "n_nao_critico_proximos_4h", "n_DG_proximos_4h"]
    pl.from_pandas(fps_pdf[cols_out]).write_csv(ARQ_TAB)
    print(f"\nSalvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    # Estatísticas de resumo
    print(f"\n  Estatísticas dos {N_TOP} top-anomaly FPs:")
    print(f"  - anomaly_score range:    [{fps_pdf['anomaly_score'].min():.4f}, "
          f"{fps_pdf['anomaly_score'].max():.4f}]")
    print(f"  - Mediana n_eventos próximos 4h: {fps_pdf['n_eventos_proximos_4h'].median():.0f}")
    print(f"  - Mediana n_critico próximos 4h: {fps_pdf['n_critico_proximos_4h'].median():.0f}")
    print(f"  - % com >= 1 DG futuro nas 4h:   "
          f"{100*(fps_pdf['n_DG_proximos_4h'] >= 1).mean():.1f}%")
    print(f"  - % com >= 1 evento Crítico nas 4h: "
          f"{100*(fps_pdf['n_critico_proximos_4h'] >= 1).mean():.1f}%")

    # Concentrações por TAG e por frota
    print("\n  Concentração por frota:")
    por_frota = fps_pdf.groupby("Tag_Frota").size().reset_index(name="n_FPs").sort_values(
        "n_FPs", ascending=False
    )
    print(por_frota.to_string(index=False))

    print("\n  Concentração por TAG (top 10):")
    por_tag = fps_pdf.groupby("TAG").size().reset_index(name="n_FPs").sort_values(
        "n_FPs", ascending=False
    ).head(10)
    print(por_tag.to_string(index=False))

    # Salvar concentrações
    conc = pd.concat([
        por_frota.assign(dimensao="Tag_Frota").rename(columns={"Tag_Frota": "valor"}),
        por_tag.assign(dimensao="TAG").rename(columns={"TAG": "valor"})
    ])
    conc = conc[["dimensao", "valor", "n_FPs"]]
    pl.from_pandas(conc).write_csv(ARQ_CONC)
    print(f"\nSalvo: {ARQ_CONC.relative_to(ROOT.parent)}")

    # Figura — 3 painéis
    print("\nGerando figura (3 painéis: contexto, frota, alarme)...")
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # Painel A — Boxplot de eventos próximos 4h
    ax = axes[0]
    data = [
        fps_pdf["n_eventos_proximos_4h"],
        fps_pdf["n_critico_proximos_4h"],
        fps_pdf["n_nao_critico_proximos_4h"],
    ]
    bp = ax.boxplot(data, labels=["Total", "Crítico", "Não-Crítico"],
                     patch_artist=True, showmeans=True)
    cores = ["#1976d2", "#c62828", "#ff8f00"]
    for patch, cor in zip(bp["boxes"], cores):
        patch.set_facecolor(cor)
        patch.set_alpha(0.7)
    ax.set_ylabel("Número de eventos no MESMO TAG nas 4h seguintes", fontsize=11)
    ax.set_title("(a) Contexto de cada FP top-anomaly\n"
                 "Quantos eventos acontecem após o alerta do IF?",
                 fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(axis="both", labelsize=10)

    # Painel B — Top frotas
    ax = axes[1]
    ax.barh(por_frota["Tag_Frota"], por_frota["n_FPs"], color="#1976d2",
            edgecolor="white")
    for i, v in enumerate(por_frota["n_FPs"]):
        ax.text(v + 0.5, i, str(v), va="center", fontsize=10, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlabel(f"Número de FPs entre top-{N_TOP}", fontsize=11)
    ax.set_title("(b) Concentração dos FPs por frota",
                 fontsize=12, fontweight="bold")
    ax.tick_params(axis="both", labelsize=10)
    ax.grid(True, axis="x", alpha=0.3)

    # Painel C — Top 10 TAGs
    ax = axes[2]
    ax.barh(por_tag["TAG"], por_tag["n_FPs"], color="#c62828", edgecolor="white")
    for i, v in enumerate(por_tag["n_FPs"]):
        ax.text(v + 0.5, i, str(v), va="center", fontsize=10, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlabel(f"Número de FPs entre top-{N_TOP}", fontsize=11)
    ax.set_title("(c) Top 10 TAGs com mais FPs (deterioração latente?)",
                 fontsize=12, fontweight="bold")
    ax.tick_params(axis="both", labelsize=9)
    ax.grid(True, axis="x", alpha=0.3)

    pct_com_dg_futuro = 100*(fps_pdf['n_DG_proximos_4h'] >= 1).mean()
    pct_com_critico = 100*(fps_pdf['n_critico_proximos_4h'] >= 1).mean()
    fig.suptitle(
        f"Figura Extra H — O que a regra CMA não vê: top {N_TOP} FPs do Isolation Forest\n"
        f"Eventos com alto anomaly_score NÃO rotulados como DG | "
        f"{pct_com_dg_futuro:.0f}% têm ≥1 DG nas 4h seguintes | "
        f"{pct_com_critico:.0f}% têm ≥1 evento Crítico nas 4h seguintes",
        fontsize=13, fontweight="bold", y=1.02,
    )

    plt.tight_layout()
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")

    # Veredito honesto
    print("\n" + "=" * 70)
    print("VEREDITO HONESTO — o IF complementa, dispensa, ou duplica a CMA?")
    print("=" * 70)

    if pct_com_dg_futuro >= 50:
        print("  COMPLEMENTA com FORÇA: maioria dos FPs do IF tem DG futuro nas 4h.")
        print("  → IF antecipa DGs que a CMA pegou só DEPOIS. Trabalho Futuro: investigar.")
    elif pct_com_critico >= 50:
        print("  COMPLEMENTA PARCIALMENTE: FPs concentram eventos Crítico nas 4h seguintes,")
        print("  mas sem DG. Pode ser anomalia mecânica real que CMA não classificou.")
    else:
        print("  DUPLICA / RUÍDO: FPs não mostram concentração anormal de eventos futuros.")
        print("  → IF detecta padrões estatisticamente raros sem significado operacional claro.")


if __name__ == "__main__":
    main()
