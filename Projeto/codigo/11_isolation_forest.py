"""
11_isolation_forest.py - Diagnostico do Risco 3.3 (vies do label CMA).

Teste empirico unico de uma limitacao metodologica conhecida: o rotulo
`Is_Dont_Go` e gerado por regras CMA (Centro de Monitoramento e
Acompanhamento, 82 regras de "Muito Alto"). Modelos supervisionados
(LightGBM v3, Weibull AFT) podem estar aprendendo a REPLICAR essas regras,
nao a antecipar anomalias mecanicas reais.

PERGUNTA OPERACIONAL DO ISOLATION FOREST:
  "Sem usar Is_Dont_Go, o que e estatisticamente anomalo no espaco de
  features? Essas anomalias coincidem com os DGs reais?"

  - Se SIM (AUC-ROC alto, precision alta em thresholds baixos):
    o rotulo CMA captura anomalias genuinas. Modelos supervisionados
    aprendem padroes reais. Risco 3.3 MITIGADO.

  - Se NAO (AUC-ROC ~0.5):
    o rotulo CMA pode ser arbitrario das regras de negocio. Modelos
    supervisionados aprendem a replicar regras, nao antecipar mecanica.
    Risco 3.3 CONFIRMADO -> limitacao grave para CM 6.2.

CONFIGURACAO METODOLOGICA (aprovada pelo usuario 25/05):
  1. Mesmas 34 features do v3 canonico (comparabilidade direta)
  2. Multiplos contamination [0.01, 0.03, 0.05, 0.10] para reportar curva
     completa (qualidade > simplicidade — point estimate seria perda)
  3. 3 metricas: AUC-ROC + Precision/Recall por threshold + contingencia 2x2

NAO E MODELO OPERACIONAL — e ferramenta de auditoria do label.

Entradas:
  - Projeto/dados/features/v3.parquet

Saidas:
  - Projeto/modelos/isolation_forest.joblib (modelo + scaler + features)
  - Projeto/relatorio/tabelas/if_auc_roc.csv (AUC-ROC por split)
  - Projeto/relatorio/tabelas/if_diagnostico.csv (P/R por contamination)
  - Projeto/relatorio/tabelas/if_contingencia.csv (4 tabelas 2x2 concatenadas)
  - Projeto/relatorio/figuras/figExD_isolation_forest_diagnostico.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/11_isolation_forest.py
"""
from pathlib import Path
import time
import warnings

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


# ===========================================================================
# Caminhos
# ===========================================================================
ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"

ARQ_MODELO = ROOT / "modelos" / "isolation_forest.joblib"
ARQ_AUC = ROOT / "relatorio" / "tabelas" / "if_auc_roc.csv"
ARQ_DIAG = ROOT / "relatorio" / "tabelas" / "if_diagnostico.csv"
ARQ_CONT = ROOT / "relatorio" / "tabelas" / "if_contingencia.csv"
ARQ_ESTRAT = ROOT / "relatorio" / "tabelas" / "if_auc_estratificado_test.csv"
ARQ_POR_TAG = ROOT / "relatorio" / "tabelas" / "if_auc_por_tag.csv"
ARQ_FIG = ROOT / "relatorio" / "figuras" / "figExD_isolation_forest_diagnostico.png"


# ===========================================================================
# Constantes
# ===========================================================================
LINHAS_ESPERADAS = 544_885
SEED = 42
N_ESTIMATORS = 200  # Default 100 é OK; 200 dá +precisão sem custo significativo
CONTAMINATIONS = [0.01, 0.03, 0.05, 0.10]  # Curva de thresholds

# 34 features alinhadas com v3 canonico (sem horas_desde_ultimo_DG)
FEATURES_NUMERICAS = [
    "hora_dia", "dia_semana", "mes",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    "horas_desde_ultimo_critico",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "operador_freq",
    "frota_793D_2S", "frota_793D_3S", "frota_793D_4S", "frota_793D_5S",
    "tipo_caminhao",
    "valor_disponivel",  # bool -> int
]
FEATURES_CAT = ["turno", "estado_pre_evento"]


# ===========================================================================
# Etapa 1 - Preparar features (mesma logica do 09_sobrevivencia para consistencia)
# ===========================================================================
def preparar_features(df: pl.DataFrame) -> tuple[pd.DataFrame, list[str], StandardScaler, dict]:
    print()
    print("Etapa 1/6 - Preparando matriz de features...")

    cols = FEATURES_NUMERICAS + FEATURES_CAT + ["Is_Dont_Go", "split", "TAG"]
    pdf = df.select(cols).to_pandas()
    pdf["valor_disponivel"] = pdf["valor_disponivel"].astype(np.int8)

    train_mask = pdf["split"] == "train"

    # ===== Imputacao (mesma estrategia do 09 para consistencia) =====
    imputacao = {}
    for col in ["razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d"]:
        pdf[col] = pdf[col].fillna(1.0)
        imputacao[col] = 1.0
    col = "taxa_DG_operador_30d"
    val_imp = float(pdf.loc[train_mask, col].median())
    pdf[col] = pdf[col].fillna(val_imp)
    imputacao[col] = val_imp
    col = "horas_desde_ultimo_critico"
    val_imp = float(pdf.loc[train_mask, col].max())
    pdf[col] = pdf[col].fillna(val_imp)
    imputacao[col] = val_imp
    pdf[FEATURES_NUMERICAS] = pdf[FEATURES_NUMERICAS].fillna(0)

    # One-hot (drop_first para evitar multicolinearidade — IF tolera mais que Cox,
    # mas por consistencia com 09 mantemos drop_first)
    dummies = pd.get_dummies(
        pdf[FEATURES_CAT], prefix=FEATURES_CAT, drop_first=True, dtype=np.int8
    )
    pdf = pd.concat([pdf.drop(columns=FEATURES_CAT), dummies], axis=1)

    features = FEATURES_NUMERICAS + list(dummies.columns)
    print(f"  Features finais: {len(features)} "
          f"({len(FEATURES_NUMERICAS)} numericas + {len(dummies.columns)} dummies)")

    # StandardScaler em todas (IsolationForest e relativamente robusto a escala,
    # mas standardizar ajuda em alguns regimes)
    scaler = StandardScaler()
    scaler.fit(pdf.loc[train_mask, features])
    pdf[features] = scaler.transform(pdf[features])

    # Validacao defensiva
    nan_check = pdf[features].isna().sum().sum()
    inf_check = np.isinf(pdf[features].values).sum()
    print(f"  Validacao: {nan_check} NaN + {inf_check} Inf")
    assert nan_check == 0 and inf_check == 0

    return pdf, features, scaler, imputacao


# ===========================================================================
# Etapa 2 - Fit IsolationForest no train (SEM usar Is_Dont_Go)
# ===========================================================================
def fit_iforest(pdf: pd.DataFrame, features: list[str]) -> IsolationForest:
    print()
    print("Etapa 2/6 - Treinando IsolationForest (NAO-SUPERVISIONADO, sem Is_Dont_Go)...")
    train_X = pdf.loc[pdf["split"] == "train", features].values
    print(f"  Train shape: {train_X.shape}")
    print(f"  n_estimators={N_ESTIMATORS}, random_state={SEED}")
    print(f"  contamination='auto' (calibrado por amostra; thresholds derivados depois)")

    t0 = time.time()
    iforest = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination="auto",  # threshold padrao; vamos derivar thresholds especificos depois
        random_state=SEED,
        n_jobs=-1,
    )
    iforest.fit(train_X)
    elapsed = time.time() - t0
    print(f"  Treinado em {elapsed:.1f}s")
    return iforest


# ===========================================================================
# Etapa 3 - AUC-ROC do anomaly_score vs Is_Dont_Go por split
# ===========================================================================
def auc_roc_por_split(iforest: IsolationForest, pdf: pd.DataFrame,
                      features: list[str]) -> pl.DataFrame:
    print()
    print("Etapa 3/6 - AUC-ROC (anomaly_score continuo vs Is_Dont_Go)...")

    linhas = []
    pdf["anomaly_score"] = np.nan  # adicionado para uso posterior
    for split in ["train", "val", "test"]:
        sub_idx = pdf["split"] == split
        sub_X = pdf.loc[sub_idx, features].values
        y = pdf.loc[sub_idx, "Is_Dont_Go"].values

        # decision_function: ALTO = normal, BAIXO = anomalo
        # Convertemos para anomaly_score: ALTO = mais anomalo
        decision = iforest.decision_function(sub_X)
        anomaly_score = -decision

        pdf.loc[sub_idx, "anomaly_score"] = anomaly_score

        auc = roc_auc_score(y, anomaly_score)
        n_pos = int(y.sum())
        prevalence = n_pos / len(y)
        linhas.append({
            "split": split,
            "n_total": len(y),
            "n_DG": n_pos,
            "prevalencia_DG": round(prevalence, 4),
            "auc_roc": round(float(auc), 4),
        })
        print(f"  {split:<6s}: n={len(y):>7,}  DG={n_pos:>6,} "
              f"({prevalence*100:5.2f}%)  AUC-ROC={auc:.4f}")

    df_auc = pl.from_dicts(linhas)
    df_auc.write_csv(ARQ_AUC)
    print(f"  Salvo: {ARQ_AUC.relative_to(ROOT.parent)}")
    return df_auc


# ===========================================================================
# Etapa 3b - AUC-ROC estratificado por CA65926 (test apenas)
# Diagnostico critico: o sinal alto em test e dirigido pela anomalia dominante
# do CA65926 (Obs 2.9) ou e padrao geral?
# ===========================================================================
def auc_roc_estratificado_test(pdf: pd.DataFrame) -> pl.DataFrame:
    print()
    print("Etapa 3b/6 - AUC-ROC estratificado por CA65926 (test apenas)...")
    print("  Pergunta: o sinal forte em test e dirigido pelo CA65926 (Obs 2.9)?")
    print()

    test_idx = pdf["split"] == "test"
    scores = pdf.loc[test_idx, "anomaly_score"].values
    y = pdf.loc[test_idx, "Is_Dont_Go"].values
    tag = pdf.loc[test_idx, "TAG"].values

    mask_ca = tag == "CA65926"

    linhas = []
    for nome, mask in [("test_completo", np.ones(len(y), dtype=bool)),
                       ("CA65926_apenas", mask_ca),
                       ("test_sem_CA65926", ~mask_ca)]:
        if mask.sum() == 0 or y[mask].sum() == 0:
            continue
        auc = roc_auc_score(y[mask], scores[mask])
        linhas.append({
            "subgrupo": nome,
            "n_eventos": int(mask.sum()),
            "n_DG": int(y[mask].sum()),
            "prevalencia_DG": round(float(y[mask].sum() / mask.sum()), 4),
            "auc_roc": round(float(auc), 4),
        })
        print(f"  {nome:<18s}: n={int(mask.sum()):>7,}  DG={int(y[mask].sum()):>6,}  "
              f"prev={100*y[mask].sum()/mask.sum():5.2f}%  AUC-ROC={auc:.4f}")

    df_estrat = pl.from_dicts(linhas)
    df_estrat.write_csv(ARQ_ESTRAT)
    print()
    print(f"  Salvo: {ARQ_ESTRAT.relative_to(ROOT.parent)}")
    return df_estrat


# ===========================================================================
# Etapa 3c - AUC-ROC por TAG no test (analise estrutural)
# Em vez de testar uma hipotese ad-hoc (CA65926), reporta a distribuicao
# completa de AUC-ROC entre as 35 TAGs do test — revela se a assimetria
# e dirigida apenas pelo CA65926 ou se ha gradiente entre equipamentos.
# ===========================================================================
def auc_roc_por_tag(pdf: pd.DataFrame) -> pl.DataFrame:
    print()
    print("Etapa 3c/6 - AUC-ROC por TAG no test (distribuicao completa)...")

    test_idx = pdf["split"] == "test"
    scores = pdf.loc[test_idx, "anomaly_score"].values
    y = pdf.loc[test_idx, "Is_Dont_Go"].values
    tag = pdf.loc[test_idx, "TAG"].values

    linhas = []
    for t in sorted(np.unique(tag)):
        mask = tag == t
        n = int(mask.sum())
        n_dg = int(y[mask].sum())
        # AUC indefinido se nao ha variabilidade no target
        if n_dg == 0 or n_dg == n:
            linhas.append({
                "TAG": t,
                "n_eventos": n,
                "n_DG": n_dg,
                "prevalencia_DG": round(n_dg / max(n, 1), 4),
                "auc_roc": None,
                "obs": "AUC indefinido (sem variabilidade no target)",
            })
        else:
            auc = float(roc_auc_score(y[mask], scores[mask]))
            linhas.append({
                "TAG": t,
                "n_eventos": n,
                "n_DG": n_dg,
                "prevalencia_DG": round(n_dg / n, 4),
                "auc_roc": round(auc, 4),
                "obs": "",
            })

    df_tag = pl.from_dicts(linhas).sort("auc_roc", descending=True, nulls_last=True)
    df_tag.write_csv(ARQ_POR_TAG)
    print(f"  Salvo: {ARQ_POR_TAG.relative_to(ROOT.parent)} ({df_tag.height} TAGs)")
    print()
    print("  Distribuicao de AUC-ROC por TAG (ordenado decrescente):")
    print(f"  {'rank':>4} | {'TAG':<10s} | {'n_eventos':>9s} | "
          f"{'n_DG':>6s} | {'prev_DG':>7s} | {'AUC':>6s}")
    print(f"  {'-'*4} | {'-'*10} | {'-'*9} | {'-'*6} | {'-'*7} | {'-'*6}")
    rank = 1
    for row in df_tag.iter_rows(named=True):
        auc_str = f"{row['auc_roc']:.4f}" if row['auc_roc'] is not None else "  N/A "
        print(f"  {rank:>4} | {row['TAG']:<10s} | {row['n_eventos']:>9,} | "
              f"{row['n_DG']:>6,} | {row['prevalencia_DG']*100:>6.2f}% | {auc_str}")
        rank += 1

    # Estatisticas resumo
    aucs_validos = [r["auc_roc"] for r in linhas if r["auc_roc"] is not None]
    if aucs_validos:
        print()
        print(f"  Resumo estatistico (n={len(aucs_validos)} TAGs com AUC valido):")
        print(f"    AUC max     : {max(aucs_validos):.4f}")
        print(f"    AUC mediana : {float(np.median(aucs_validos)):.4f}")
        print(f"    AUC media   : {float(np.mean(aucs_validos)):.4f}")
        print(f"    AUC min     : {min(aucs_validos):.4f}")
        n_acima_075 = sum(1 for a in aucs_validos if a >= 0.75)
        n_abaixo_055 = sum(1 for a in aucs_validos if a < 0.55)
        print(f"    TAGs com AUC >= 0.75 (sinal forte): {n_acima_075} de {len(aucs_validos)}")
        print(f"    TAGs com AUC <  0.55 (~aleatorio):  {n_abaixo_055} de {len(aucs_validos)}")

    return df_tag


# ===========================================================================
# Etapa 4 - Curva P/R por contamination
# ===========================================================================
def curva_precision_recall(pdf: pd.DataFrame) -> pl.DataFrame:
    print()
    print("Etapa 4/6 - Curva Precision/Recall por contamination...")
    print(f"  Contaminations testados: {CONTAMINATIONS}")
    print()

    test_idx = pdf["split"] == "test"
    scores = pdf.loc[test_idx, "anomaly_score"].values
    y = pdf.loc[test_idx, "Is_Dont_Go"].values
    n_test = len(y)
    n_dg = int(y.sum())

    linhas = []
    print(f"  {'cont':>5s} | {'threshold':>10s} | {'n_anom':>7s} | "
          f"{'P':>6s} | {'R':>6s} | {'F1':>6s}")
    print(f"  {'-'*5} | {'-'*10} | {'-'*7} | {'-'*6} | {'-'*6} | {'-'*6}")
    for cont in CONTAMINATIONS:
        # Threshold: top `cont` fracao dos eventos sao "anomalos"
        threshold = np.quantile(scores, 1.0 - cont)
        y_pred = (scores >= threshold).astype(np.int8)
        n_anom = int(y_pred.sum())

        precision, recall, f1, _ = precision_recall_fscore_support(
            y, y_pred, average="binary", zero_division=0
        )
        linhas.append({
            "contamination": cont,
            "threshold_anomaly_score": round(float(threshold), 4),
            "n_anomalias_detectadas": n_anom,
            "pct_anomalias": round(n_anom / n_test * 100, 2),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
        })
        print(f"  {cont:>5.2f} | {threshold:>10.4f} | {n_anom:>7,} | "
              f"{precision:>6.4f} | {recall:>6.4f} | {f1:>6.4f}")

    df_pr = pl.from_dicts(linhas)
    df_pr.write_csv(ARQ_DIAG)
    print()
    print(f"  Salvo: {ARQ_DIAG.relative_to(ROOT.parent)}")
    return df_pr


# ===========================================================================
# Etapa 5 - Tabelas de contingencia 2x2 (test set)
# ===========================================================================
def contingencias(pdf: pd.DataFrame) -> pl.DataFrame:
    print()
    print("Etapa 5/6 - Tabelas de contingencia 2x2 (test set)...")
    print()

    test_idx = pdf["split"] == "test"
    scores = pdf.loc[test_idx, "anomaly_score"].values
    y = pdf.loc[test_idx, "Is_Dont_Go"].values

    todas_linhas = []
    for cont in CONTAMINATIONS:
        threshold = np.quantile(scores, 1.0 - cont)
        y_pred = (scores >= threshold).astype(np.int8)

        # Convencao sklearn: rows = true, cols = pred. labels=[0,1]
        cm = confusion_matrix(y, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()

        # Inspecionar especificamente os "FP" — eventos anomalos NAO rotulados
        # como DG. Sao possíveis DGs perdidos pelo CMA (Risco 3.3 reverso).
        print(f"  Contamination={cont:.2f}  threshold={threshold:.4f}")
        print(f"  {'':>20s} | {'Pred: normal':>14s} | {'Pred: anomalia':>14s}")
        print(f"  {'-'*20} | {'-'*14} | {'-'*14}")
        print(f"  {'True: nao-DG (0)':>20s} | {tn:>14,} | {fp:>14,}")
        print(f"  {'True: DG (1)':>20s} | {fn:>14,} | {tp:>14,}")
        print()

        todas_linhas.append({
            "contamination": cont,
            "TN_nao_DG_predito_normal": int(tn),
            "FP_nao_DG_predito_anomalia": int(fp),
            "FN_DG_predito_normal": int(fn),
            "TP_DG_predito_anomalia": int(tp),
            "obs_FP_pode_ser_DG_perdido_CMA": (
                "alta sobreposicao -> FP suspeitos de serem DG perdidos pelo CMA"
                if fp / max(tn + fp, 1) > 0.5 else
                "FP baixa proporcao -> CMA captura a maioria das anomalias"
            ),
        })

    df_cont = pl.from_dicts(todas_linhas)
    df_cont.write_csv(ARQ_CONT)
    print(f"  Salvo: {ARQ_CONT.relative_to(ROOT.parent)} "
          f"({df_cont.height} contaminations)")
    return df_cont


# ===========================================================================
# Etapa 6 - Figura diagnostica
# ===========================================================================
def gerar_figura(df_pr: pl.DataFrame, df_auc: pl.DataFrame, pdf: pd.DataFrame,
                 df_por_tag: pl.DataFrame) -> None:
    print()
    print("Etapa 6/6 - Figura diagnostica (Fig Extra D)...")
    ARQ_FIG.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    axes = axes.flatten()

    # Painel 1 — P/R por contamination (test)
    ax = axes[0]
    cont_arr = df_pr["contamination"].to_numpy()
    p_arr = df_pr["precision"].to_numpy()
    r_arr = df_pr["recall"].to_numpy()
    f_arr = df_pr["f1"].to_numpy()
    ax.plot(cont_arr, p_arr, "o-", label="Precision", color="C0", linewidth=2)
    ax.plot(cont_arr, r_arr, "s-", label="Recall", color="C1", linewidth=2)
    ax.plot(cont_arr, f_arr, "^-", label="F1", color="C2", linewidth=2)
    auc_test = df_auc.filter(pl.col("split") == "test")["auc_roc"][0]
    prev_test = df_auc.filter(pl.col("split") == "test")["prevalencia_DG"][0]
    ax.axhline(prev_test, color="gray", linestyle="--", alpha=0.6,
               label=f"Prevalencia DG ({prev_test*100:.1f}%)")
    ax.set_xlabel("contamination (fracao de top-anomalias)", fontsize=10)
    ax.set_ylabel("metrica vs Is_Dont_Go", fontsize=10)
    ax.set_title(f"P/R por contamination (test)\nAUC-ROC test = {auc_test:.3f}",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(cont_arr)

    # Painel 2 — Histograma do anomaly_score por classe (test)
    ax = axes[1]
    test_idx = pdf["split"] == "test"
    scores_pos = pdf.loc[test_idx & (pdf["Is_Dont_Go"] == 1), "anomaly_score"]
    scores_neg = pdf.loc[test_idx & (pdf["Is_Dont_Go"] == 0), "anomaly_score"]
    bins = np.linspace(scores_neg.min(), scores_pos.max(), 60)
    ax.hist(scores_neg, bins=bins, alpha=0.5, label=f"nao-DG (n={len(scores_neg):,})",
            color="C0", density=True)
    ax.hist(scores_pos, bins=bins, alpha=0.5, label=f"DG (n={len(scores_pos):,})",
            color="C3", density=True)
    ax.set_xlabel("anomaly_score (alto = mais anomalo)", fontsize=10)
    ax.set_ylabel("densidade", fontsize=10)
    ax.set_title("Distribuicao do anomaly_score por classe (test)",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)

    # Painel 3 — AUC-ROC por split (train/val/test)
    ax = axes[2]
    splits = df_auc["split"].to_list()
    aucs = df_auc["auc_roc"].to_list()
    bar_colors = ["C0" if s == "train" else "C1" if s == "val" else "C3"
                  for s in splits]
    bars = ax.bar(splits, aucs, color=bar_colors, alpha=0.7,
                  edgecolor="black", linewidth=1)
    for bar, auc in zip(bars, aucs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f"{auc:.4f}", ha="center", fontsize=10, fontweight="bold")
    ax.axhline(0.5, color="gray", linestyle="--", alpha=0.6,
               label="Aleatorio (0.5)")
    ax.set_ylabel("AUC-ROC (anomaly_score vs Is_Dont_Go)", fontsize=10)
    ax.set_ylim(0, 1.0)
    ax.set_title("AUC-ROC por split — diagnostico do Risco 3.3",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")

    # Painel 4 — Distribuicao de AUC-ROC por TAG (revela onde o sinal vive)
    ax = axes[3]
    aucs_validos = [(r["TAG"], r["auc_roc"], r["n_DG"])
                    for r in df_por_tag.iter_rows(named=True)
                    if r["auc_roc"] is not None]
    aucs_validos = sorted(aucs_validos, key=lambda x: x[1], reverse=True)
    tags_lbl = [t for t, _, _ in aucs_validos]
    aucs_arr = [a for _, a, _ in aucs_validos]
    ndg_arr = [n for _, _, n in aucs_validos]

    # Cor por n_DG (escala logaritmica)
    ndg_log = np.log10(np.maximum(np.array(ndg_arr), 1))
    cmap = plt.cm.viridis
    colors = cmap(ndg_log / max(ndg_log.max(), 1))

    bars = ax.barh(range(len(tags_lbl)), aucs_arr, color=colors,
                   edgecolor="black", linewidth=0.5)
    ax.set_yticks(range(len(tags_lbl)))
    ax.set_yticklabels(tags_lbl, fontsize=7)
    ax.invert_yaxis()  # AUC mais alto no topo
    ax.axvline(0.5, color="gray", linestyle="--", alpha=0.6, label="Aleatorio")
    ax.axvline(0.75, color="green", linestyle=":", alpha=0.6, label="Sinal forte (0.75)")
    mediana = float(np.median(aucs_arr))
    ax.axvline(mediana, color="red", linestyle="-.", alpha=0.7,
               label=f"Mediana ({mediana:.3f})")
    ax.set_xlabel("AUC-ROC", fontsize=10)
    ax.set_xlim(0, 1.0)
    ax.set_title(
        f"AUC-ROC por TAG no test ({len(tags_lbl)} TAGs com AUC valido)\n"
        "cor = log10(n_DG); sinal forte concentrado em poucas TAGs",
        fontsize=11, fontweight="bold",
    )
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, alpha=0.3, axis="x")

    fig.suptitle(
        "Figura Extra D — Isolation Forest: diagnostico do vies do label CMA (Risco 3.3)\n"
        "Modelo NAO-SUPERVISIONADO (treinado sem Is_Dont_Go) - "
        "sobreposicao com DGs reais valida o rotulo",
        fontsize=12, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    plt.savefig(ARQ_FIG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG.relative_to(ROOT.parent)}")


# ===========================================================================
# Sintese diagnostica do Risco 3.3 — usa estratificacao CA65926 para
# distinguir mitigacao em regime dominante vs distribuido
# ===========================================================================
def sintese_risco_33(df_auc: pl.DataFrame, df_pr: pl.DataFrame,
                     df_estrat: pl.DataFrame, df_por_tag: pl.DataFrame) -> None:
    print()
    print("=" * 70)
    print("SINTESE DIAGNOSTICA — Risco 3.3 (vies do label CMA)")
    print("=" * 70)
    print()

    auc_test_total = float(
        df_estrat.filter(pl.col("subgrupo") == "test_completo")["auc_roc"][0]
    )
    auc_ca = float(
        df_estrat.filter(pl.col("subgrupo") == "CA65926_apenas")["auc_roc"][0]
    )
    auc_resto = float(
        df_estrat.filter(pl.col("subgrupo") == "test_sem_CA65926")["auc_roc"][0]
    )

    print(f"AUC-ROC test (completo):     {auc_test_total:.4f}")
    print(f"AUC-ROC test (CA65926 only): {auc_ca:.4f}")
    print(f"AUC-ROC test (sem CA65926):  {auc_resto:.4f}")
    print()
    print("Interpretacao estratificada (a leitura correta do Risco 3.3):")
    print()

    if auc_ca >= 0.75 and auc_resto < 0.60:
        print("  ASSIMETRIA FORTE entre regimes:")
        print(f"  - CA65926 (anomalia dominante): AUC={auc_ca:.4f} -> CMA-IF concordam")
        print(f"    Para falhas mecanicas progressivas tipo CA65926, CMA captura sinal real.")
        print(f"  - Resto do test (DGs distribuidos): AUC={auc_resto:.4f} -> CMA-IF quase aleatorios")
        print(f"    Para DGs distribuidos entre equipamentos, rotulo CMA pode estar")
        print(f"    capturando eventos sem assinatura estatistica distintiva.")
        print()

        # Validacao adicional via distribuicao por TAG
        aucs = [r["auc_roc"] for r in df_por_tag.iter_rows(named=True)
                if r["auc_roc"] is not None]
        if aucs:
            mediana = float(np.median(aucs))
            n_forte = sum(1 for a in aucs if a >= 0.75)
            n_fraco = sum(1 for a in aucs if a < 0.55)
            print(f"  Validacao via distribuicao por TAG (n={len(aucs)} TAGs com AUC valido):")
            print(f"  - AUC mediana por TAG: {mediana:.4f}")
            print(f"  - TAGs com AUC >= 0.75 (sinal forte): {n_forte}")
            print(f"  - TAGs com AUC <  0.55 (~aleatorio):  {n_fraco}")
            print(f"  - O AUC agregado (0.86) e DOMINADO por poucos equipamentos —")
            print(f"    {n_forte} TAGs com sinal forte vs {n_fraco} com sinal proximo de aleatorio.")
            print(f"  - A mediana ({mediana:.4f}) e medida mais honesta do sinal tipico.")
        print()
        print("  VEREDITO: Risco 3.3 PARCIALMENTE MITIGADO (assimetrico por regime).")
        print()
        print("  Implicacao para CM 6.2 / deployment:")
        print("  - Performance alta do v3 em test (AUC-PR 0.8556) e largamente")
        print("    dirigida pela deteccao de poucos equipamentos.")
        print("  - Em regime sem anomalia dominante, performance pode degradar")
        print("    para perto do baseline (consistente com AUC-PR train/val mais baixo).")
        print("  - Recomendacao: monitorar performance estratificada por equipamento")
        print("    em producao; retreino rolling captura mudancas de regime.")
    elif auc_test_total >= 0.75:
        print("  AUC-ROC total >= 0.75 e nao-assimetrico -> SOBREPOSICAO FORTE GENUINA.")
        print("  Risco 3.3 MITIGADO empiricamente para todo o test set.")
    elif auc_test_total >= 0.60:
        print("  AUC-ROC total moderado -> SOBREPOSICAO MODERADA.")
        print("  Risco 3.3 PARCIALMENTE MITIGADO.")
    else:
        print("  AUC-ROC total baixo -> SOBREPOSICAO FRACA.")
        print("  Risco 3.3 PARCIALMENTE CONFIRMADO — limitacao para CM 6.2.")

    print()


# ===========================================================================
# Etapa 7 - Salvar modelo
# ===========================================================================
def salvar_modelo(iforest, features, scaler, imputacao):
    print()
    print("Salvando modelo Isolation Forest...")
    ARQ_MODELO.parent.mkdir(parents=True, exist_ok=True)
    artefato = {
        "modelo": iforest,
        "features": features,
        "scaler": scaler,
        "imputacao": imputacao,
        "n_estimators": N_ESTIMATORS,
        "seed": SEED,
        "contaminations_testados": CONTAMINATIONS,
    }
    joblib.dump(artefato, ARQ_MODELO, compress=3)
    mb = ARQ_MODELO.stat().st_size / 1024 / 1024
    print(f"  Salvo: {ARQ_MODELO.relative_to(ROOT.parent)} ({mb:.2f} MB)")


# ===========================================================================
# Main
# ===========================================================================
def main():
    t_start = time.time()
    print("=" * 70)
    print("11_isolation_forest.py - Diagnostico Risco 3.3 (vies do label CMA)")
    print("=" * 70)

    if not ARQ_V3.exists():
        raise FileNotFoundError(f"v3.parquet ausente: {ARQ_V3}")

    df = pl.read_parquet(ARQ_V3)
    print(f"v3.parquet shape: {df.shape}")
    assert df.height == LINHAS_ESPERADAS

    pdf, features, scaler, imputacao = preparar_features(df)
    iforest = fit_iforest(pdf, features)
    df_auc = auc_roc_por_split(iforest, pdf, features)
    df_estrat = auc_roc_estratificado_test(pdf)
    df_por_tag = auc_roc_por_tag(pdf)
    df_pr = curva_precision_recall(pdf)
    df_cont = contingencias(pdf)
    gerar_figura(df_pr, df_auc, pdf, df_por_tag)
    sintese_risco_33(df_auc, df_pr, df_estrat, df_por_tag)
    salvar_modelo(iforest, features, scaler, imputacao)

    elapsed = time.time() - t_start
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
