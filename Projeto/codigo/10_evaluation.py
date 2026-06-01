# -*- coding: utf-8 -*-
"""
10_evaluation.py - Avaliação estratificada final do LightGBM v3 (W7).

Cobre os itens IMPRESCINDÍVEIS do Grupo A definidos no fechamento de W7:

  1. TABELA CUSTO-BENEFÍCIO — multiplos thresholds × múltiplas premissas
     de custo (1:1, 3:1, 5:1, 10:1) → identifica o limiar operacional ótimo
     para cada premissa.

  2. Q6 — FAIXAS DE PROBABILIDADE → AÇÃO (3 níveis: Verde/Amarelo/Vermelho)
     baseadas em quantis do score do v3 e thresholds da análise custo-benefício.

  3. ANÁLISES ESTRATIFICADAS no test set (Qualidade C + derivadas de W5):
     - Por frota (793-D 2S/3S/4S/5S, LeTourneau L 1850)
     - Por tipo de equipamento (Caminhão vs Escavadeira)
     - Por estado operacional pré-evento (Operando/Manutenção/Parado/Hibernando)
     - Por categoria conhecida vs unknown no treino (TAGs e operadores)

  4. FIG 10 — Matriz de confusão do v3 no test set com anotações de
     impacto operacional (FP = inspeção desnecessária, FN = parada não
     planejada).

Entradas:
  - dados/features/v3.parquet
  - modelos/lightgbm_v2_no_cascade.txt (v3 canônico)

Saídas:
  - relatorio/tabelas/eval_custo_beneficio.csv (thresholds × ratios)
  - relatorio/tabelas/eval_q6_faixas.csv (3 faixas + ação operacional)
  - relatorio/tabelas/eval_estratificado_frota.csv
  - relatorio/tabelas/eval_estratificado_tipo.csv
  - relatorio/tabelas/eval_estratificado_estado.csv
  - relatorio/tabelas/eval_estratificado_unknown.csv
  - relatorio/figuras/fig10_matriz_confusao_v3.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/10_evaluation.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    recall_score,
)

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"

ARQ_CUSTO = ROOT / "relatorio" / "tabelas" / "eval_custo_beneficio.csv"
ARQ_Q6 = ROOT / "relatorio" / "tabelas" / "eval_q6_faixas.csv"
ARQ_FROTA = ROOT / "relatorio" / "tabelas" / "eval_estratificado_frota.csv"
ARQ_TIPO = ROOT / "relatorio" / "tabelas" / "eval_estratificado_tipo.csv"
ARQ_ESTADO = ROOT / "relatorio" / "tabelas" / "eval_estratificado_estado.csv"
ARQ_UNKNOWN = ROOT / "relatorio" / "tabelas" / "eval_estratificado_unknown.csv"
ARQ_FIG10 = ROOT / "relatorio" / "figuras" / "fig10_matriz_confusao_v3.png"

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

# Thresholds a avaliar
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]

# Premissas de custo FN:FP (FN = parada não planejada, FP = inspeção desnecessária)
COST_RATIOS = [1.0, 3.0, 5.0, 10.0]


def predizer_v3(df_test: pl.DataFrame):
    """Predict probabilities from LightGBM v3 on test."""
    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    X = df_test.select(FEATURES_V3).to_pandas()
    for c in ["turno", "estado_pre_evento"]:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return booster.predict(X)


def tabela_custo_beneficio(y, p):
    """Para cada threshold × ratio, computa P/R/F1 + custo total normalizado."""
    print("\nEtapa 1/5 - Tabela custo-benefício (thresholds × cost ratios)...")
    linhas = []
    for thr in THRESHOLDS:
        y_pred = (p >= thr).astype(np.int8)
        tn, fp, fn, tp = confusion_matrix(y, y_pred, labels=[0, 1]).ravel()
        precision, recall, f1, _ = precision_recall_fscore_support(
            y, y_pred, average="binary", zero_division=0
        )
        # F2: peso 2x no recall
        f2 = (5 * precision * recall) / (4 * precision + recall) if (precision + recall) > 0 else 0.0

        row_base = {
            "threshold": thr,
            "n_alertas": int(y_pred.sum()),
            "TP": int(tp),
            "FP": int(fp),
            "FN": int(fn),
            "TN": int(tn),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "f2": round(float(f2), 4),
        }
        # Custo total para cada ratio (normalizado: custo / max_costing)
        # Custo absoluto = FP * 1 + FN * ratio
        for ratio in COST_RATIOS:
            cost_total = fp + ratio * fn
            row_base[f"custo_ratio_{int(ratio)}"] = int(cost_total)
        linhas.append(row_base)

    df_cb = pl.from_dicts(linhas)
    df_cb.write_csv(ARQ_CUSTO)
    print(f"  Salvo: {ARQ_CUSTO.relative_to(ROOT.parent)}")

    # Identificar threshold ótimo por ratio (menor custo)
    print()
    print("  Threshold ótimo por premissa de custo (FN:FP):")
    print(f"  {'ratio':>5s} | {'thr*':>5s} | {'TP':>5s} | {'FP':>5s} | {'FN':>5s} | "
          f"{'P':>6s} | {'R':>6s} | {'F1':>6s} | {'F2':>6s} | {'custo':>7s}")
    print(f"  {'-'*5} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*6} | {'-'*6} | "
          f"{'-'*6} | {'-'*6} | {'-'*7}")
    thresholds_otimos = {}
    for ratio in COST_RATIOS:
        col = f"custo_ratio_{int(ratio)}"
        df_sort = df_cb.sort(col)
        best = df_sort.row(0, named=True)
        thresholds_otimos[ratio] = best["threshold"]
        print(f"  {ratio:>5.1f} | {best['threshold']:>5.2f} | {best['TP']:>5d} | "
              f"{best['FP']:>5d} | {best['FN']:>5d} | {best['precision']:>6.4f} | "
              f"{best['recall']:>6.4f} | {best['f1']:>6.4f} | {best['f2']:>6.4f} | "
              f"{best[col]:>7d}")

    return df_cb, thresholds_otimos


def q6_faixas(y, p, thresholds_otimos):
    """Define 3 faixas: Verde (operar) / Amarelo (monitorar) / Vermelho (inspecionar).

    Limiares:
      - VERDE/AMARELO  = quantil 70% do score (top 30% recebe pelo menos atenção)
      - AMARELO/VERMELHO = threshold ótimo para ratio 5:1 (compromisso central)
    """
    print("\nEtapa 2/5 - Q6: Faixas de probabilidade → ação operacional...")

    thr_amarelo_vermelho = thresholds_otimos[5.0]
    # Verde/amarelo: usar quantil 70% como referência (top 30% precisa atenção)
    thr_verde_amarelo = float(np.quantile(p, 0.70))
    # Garantir ordem
    if thr_verde_amarelo >= thr_amarelo_vermelho:
        thr_verde_amarelo = thr_amarelo_vermelho * 0.4

    faixas = [
        {"nome": "VERDE",
         "intervalo": f"P(DG) < {thr_verde_amarelo:.3f}",
         "acao": "Operar normalmente (rotina padrão)"},
        {"nome": "AMARELO",
         "intervalo": f"{thr_verde_amarelo:.3f} ≤ P(DG) < {thr_amarelo_vermelho:.3f}",
         "acao": "Monitoramento intensivo (alertas adicionais ao plantão)"},
        {"nome": "VERMELHO",
         "intervalo": f"P(DG) ≥ {thr_amarelo_vermelho:.3f}",
         "acao": "Inspeção preventiva planejada (mobilizar peça e equipe)"},
    ]

    # Quantificar quantos eventos caem em cada faixa
    linhas = []
    for faixa in faixas:
        if faixa["nome"] == "VERDE":
            mask = p < thr_verde_amarelo
        elif faixa["nome"] == "AMARELO":
            mask = (p >= thr_verde_amarelo) & (p < thr_amarelo_vermelho)
        else:
            mask = p >= thr_amarelo_vermelho

        n = int(mask.sum())
        n_dg = int(y[mask].sum())
        n_nao_dg = n - n_dg
        prev_faixa = n_dg / n if n > 0 else 0.0
        linhas.append({
            **faixa,
            "n_eventos": n,
            "pct_eventos": round(100 * n / len(y), 2),
            "n_DG_real": n_dg,
            "n_nao_DG": n_nao_dg,
            "prevalencia_DG_faixa_pct": round(100 * prev_faixa, 2),
        })

    df_q6 = pl.from_dicts(linhas)
    df_q6.write_csv(ARQ_Q6)
    print(f"  Salvo: {ARQ_Q6.relative_to(ROOT.parent)}")
    print()
    print(f"  {'Faixa':<10s} | {'Intervalo':<28s} | {'n eventos':>9s} | {'% total':>7s} | "
          f"{'n DG':>6s} | {'prev %':>7s}")
    print(f"  {'-'*10} | {'-'*28} | {'-'*9} | {'-'*7} | {'-'*6} | {'-'*7}")
    for row in linhas:
        print(f"  {row['nome']:<10s} | {row['intervalo']:<28s} | {row['n_eventos']:>9,} | "
              f"{row['pct_eventos']:>6.2f}% | {row['n_DG_real']:>6,} | "
              f"{row['prevalencia_DG_faixa_pct']:>6.2f}%")
    return df_q6, thr_verde_amarelo, thr_amarelo_vermelho


def estratificar(df_test: pd.DataFrame, p: np.ndarray, coluna: str, threshold: float,
                  nome_arq: Path):
    """Estratifica métricas no test por uma coluna categórica."""
    valores_unicos = df_test[coluna].dropna().unique()
    linhas = []
    for v in sorted(valores_unicos, key=str):
        mask = df_test[coluna] == v
        if mask.sum() < 30:
            continue  # ignora classes raras
        y_sub = df_test.loc[mask, "target_4h"].values.astype(np.int8)
        p_sub = p[mask.values]
        n = len(y_sub)
        n_dg = int(y_sub.sum())
        if n_dg == 0:
            auc_pr = None
        else:
            auc_pr = round(float(average_precision_score(y_sub, p_sub)), 4)
        y_pred = (p_sub >= threshold).astype(np.int8)
        if n_dg > 0 and y_pred.sum() > 0:
            precision, recall, _, _ = precision_recall_fscore_support(
                y_sub, y_pred, average="binary", zero_division=0
            )
        else:
            precision, recall = 0.0, 0.0
        linhas.append({
            coluna: str(v),
            "n_eventos": n,
            "n_DG_real": n_dg,
            "prevalencia_pct": round(100 * n_dg / n, 2),
            "auc_pr": auc_pr,
            "precision_thr_op": round(float(precision), 4),
            "recall_thr_op": round(float(recall), 4),
            "n_alertas_thr_op": int(y_pred.sum()),
        })

    df_strat = pl.from_dicts(linhas)
    df_strat.write_csv(nome_arq)
    return df_strat


def analise_estratificada(df_test: pd.DataFrame, p: np.ndarray, threshold: float):
    print(f"\nEtapa 3/5 - Análises estratificadas no test (threshold = {threshold:.3f})...")

    # Por frota
    print("\n  (a) Por frota:")
    df_frota = estratificar(df_test, p, "Tag_Frota", threshold, ARQ_FROTA)
    print(df_frota)

    # Por tipo
    print("\n  (b) Por tipo de equipamento:")
    df_tipo = estratificar(df_test, p, "Tipo", threshold, ARQ_TIPO)
    print(df_tipo)

    # Por estado pré-evento
    print("\n  (c) Por estado pré-evento:")
    df_estado = estratificar(df_test, p, "estado_pre_evento", threshold, ARQ_ESTADO)
    print(df_estado)

    # Conhecidos vs unknown no treino
    print("\n  (d) Conhecidos vs unknown no treino:")
    df_test["categoria_treino"] = np.where(
        (df_test["tag_freq"] == 0) | (df_test["operador_freq"] == 0),
        "unknown_em_treino", "conhecido_em_treino"
    )
    df_unknown = estratificar(df_test, p, "categoria_treino", threshold, ARQ_UNKNOWN)
    print(df_unknown)

    return df_frota, df_tipo, df_estado, df_unknown


def fig10_matriz_confusao(y, p, threshold, n_pos, n_total):
    print(f"\nEtapa 4/5 - Fig 10: Matriz de confusão (threshold = {threshold:.3f})...")
    y_pred = (p >= threshold).astype(np.int8)
    cm = confusion_matrix(y, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    fig, ax = plt.subplots(figsize=(11, 8))

    # Matrix visual (4 quadrantes)
    cores = [["#e8f5e9", "#ffebee"],  # row 0: TN, FP
             ["#ffebee", "#e8f5e9"]]  # row 1: FN, TP
    valores = [[tn, fp], [fn, tp]]
    rotulos = [["TN (Verdadeiro Negativo)", "FP (Falso Positivo)"],
               ["FN (Falso Negativo)", "TP (Verdadeiro Positivo)"]]
    impactos = [["Operação normal\n(equipamento OK não alertado)",
                 "Inspeção preventiva desnecessária\n(custo: 1,5h × evento, planejado)"],
                ["Parada não planejada\n(custo: 4h × evento, REATIVA)",
                 "DG antecipado com sucesso\n(custo: 1,5h × evento, planejado)"]]

    for i in range(2):
        for j in range(2):
            ax.add_patch(plt.Rectangle((j, 1-i), 1, 1, facecolor=cores[i][j],
                                       edgecolor="black", linewidth=2))
            ax.text(j + 0.5, 1.85 - i, rotulos[i][j], ha="center", fontsize=11,
                    fontweight="bold")
            ax.text(j + 0.5, 1.55 - i, f"{valores[i][j]:,}", ha="center",
                    fontsize=24, fontweight="bold",
                    color="#2e7d32" if rotulos[i][j].startswith(("TN", "TP")) else "#c62828")
            ax.text(j + 0.5, 1.15 - i, impactos[i][j], ha="center", fontsize=9,
                    style="italic", color="#555555")

    ax.set_xlim(0, 2)
    ax.set_ylim(0, 2)
    ax.set_xticks([0.5, 1.5])
    ax.set_yticks([0.5, 1.5])
    ax.set_xticklabels(["Predito: NÃO-DG", "Predito: DG"], fontsize=12, fontweight="bold")
    ax.set_yticklabels(["Real: DG", "Real: NÃO-DG"], fontsize=12, fontweight="bold")
    ax.tick_params(axis="both", which="both", length=0)

    # Métricas no rodapé
    txt_metricas = (
        f"Threshold operacional: {threshold:.3f}  |  n = {n_total:,} eventos  |  "
        f"DGs reais = {n_pos:,} ({100*n_pos/n_total:.2f}%)\n"
        f"Precision = {precision:.4f}  |  Recall = {recall:.4f}  |  F1 = {f1:.4f}  |  "
        f"n alertas = {int(y_pred.sum()):,} ({100*y_pred.sum()/n_total:.2f}% do total)"
    )
    ax.set_title(
        f"Figura 10 — Matriz de confusão do LightGBM v3 no test set (jun/2025)\n{txt_metricas}",
        fontsize=12, fontweight="bold", pad=15,
    )

    plt.tight_layout()
    ARQ_FIG10.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG10, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG10.relative_to(ROOT.parent)}")


def main():
    print("=" * 70)
    print("10_evaluation.py - Avaliação estratificada final do v3 canônico (W7)")
    print("=" * 70)

    # Carregar dados
    df = pl.read_parquet(ARQ_V3)
    test = df.filter(pl.col("split") == "test")
    y = test["target_4h"].to_numpy().astype(np.int8)
    n_total = len(y)
    n_pos = int(y.sum())
    prev = n_pos / n_total
    print(f"\nTest set: n={n_total:,}  positivos={n_pos:,}  prevalência={prev*100:.2f}%")

    # Predições do v3
    print("\nGerando predições do v3 canônico...")
    p = predizer_v3(test)
    print(f"  Range das probabilidades: [{p.min():.4f}, {p.max():.4f}]")

    # 1. Custo-benefício
    df_cb, thresholds_otimos = tabela_custo_beneficio(y, p)

    # 2. Q6 faixas (usa threshold do ratio 5:1 como referência)
    df_q6, thr_verde_amarelo, thr_amarelo_vermelho = q6_faixas(y, p, thresholds_otimos)

    # 3. Análise estratificada — usa o threshold do ratio 5:1
    threshold_op = thresholds_otimos[5.0]
    test_pdf = test.to_pandas()
    df_frota, df_tipo, df_estado, df_unknown = analise_estratificada(
        test_pdf, p, threshold_op
    )

    # 4. Fig 10
    fig10_matriz_confusao(y, p, threshold_op, n_pos, n_total)

    # Sumário final
    print("\nEtapa 5/5 - Sumário")
    print("=" * 70)
    print("ENTREGÁVEIS DO GRUPO A (W7)")
    print("=" * 70)
    print()
    print(f"  Threshold operacional escolhido (custo FN:FP = 5:1): {threshold_op:.3f}")
    print(f"  Faixas Q6 (Verde/Amarelo/Vermelho): "
          f"< {thr_verde_amarelo:.3f} | "
          f"{thr_verde_amarelo:.3f}-{thr_amarelo_vermelho:.3f} | "
          f"≥ {thr_amarelo_vermelho:.3f}")
    print()
    print("  Saídas:")
    for arq in [ARQ_CUSTO, ARQ_Q6, ARQ_FROTA, ARQ_TIPO, ARQ_ESTADO, ARQ_UNKNOWN, ARQ_FIG10]:
        print(f"    {arq.relative_to(ROOT.parent)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
