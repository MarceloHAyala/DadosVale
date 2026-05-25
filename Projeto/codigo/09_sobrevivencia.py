"""
09_sobrevivencia.py - Modelo de Sobrevivencia (Weibull AFT + fallback Cox PH).

Segunda leitura do problema "antecipar Don't Go" — independente do LightGBM v3.
Trata o censoring rigorosamente (eventos sem DG futuro observado) como dado
adicional, oferece tabela de hazard ratios com IC 95% (interpretacao direta
sem SHAP), e gera Kaplan-Meier estratificado por frota (Fig Extra A do CM 4.3).

CONSTRUCAO (T, E) por evento:
  - Para cada evento de uma TAG, T = horas ate o proximo DG dessa mesma TAG
  - E = 1 se proximo DG foi observado, 0 se censurado (chega-se ao fim do
        periodo de observacao da TAG sem novo DG)
  - Eventos com T = 0 (ultimo evento da TAG sem DG futuro) sao filtrados

CONFIGURACAO METODOLOGICA (aprovada pelo usuario, 24/05/2026):
  1. Filtro de correlacao > 0.9 antes do fit (Cox/Weibull sao sensiveis a
     multicolinearidade — features altamente correlacionadas sao removidas)
  2. Fallback automatico para Cox PH se Weibull AFT nao convergir OU se
     C-index na val < 0.6 (criterio de qualidade minima)
  3. 34 features (sem `horas_desde_ultimo_DG`, alinhado com v3 canonico)
  4. Categoricos (turno binario, estado_pre_evento 5 categorias) → one-hot
  5. StandardScaler em features continuas (estabilidade numerica)

OUTPUT vs LightGBM v3:
  - Comparacao em AUC-PR: P(T <= 4h | X) vs target_4h
  - Modelo entrega tambem: C-index, hazard ratios com IC 95%, curva KM

Entradas:
  - Projeto/dados/features/v3.parquet

Saidas:
  - Projeto/modelos/sobrevivencia.joblib (modelo final + scaler + cols_used)
  - Projeto/relatorio/tabelas/sobrevivencia_metricas.csv (C-index/AUC-PR/n)
  - Projeto/relatorio/tabelas/sobrevivencia_hazard_ratios.csv (top features)
  - Projeto/relatorio/tabelas/sobrevivencia_features_excluidas_corr.csv
  - Projeto/relatorio/figuras/figExA_kaplan_meier_por_frota.png

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/09_sobrevivencia.py
"""
from pathlib import Path
import time
import warnings

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from lifelines import CoxPHFitter, KaplanMeierFitter, WeibullAFTFitter
from lifelines.exceptions import ConvergenceError
from lifelines.utils import concordance_index
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


# ===========================================================================
# Caminhos
# ===========================================================================
ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"

ARQ_MODELO = ROOT / "modelos" / "sobrevivencia.joblib"
ARQ_METRICAS = ROOT / "relatorio" / "tabelas" / "sobrevivencia_metricas.csv"
ARQ_HAZARD = ROOT / "relatorio" / "tabelas" / "sobrevivencia_hazard_ratios.csv"
ARQ_CORR_EXC = ROOT / "relatorio" / "tabelas" / "sobrevivencia_features_excluidas_corr.csv"
ARQ_FIG_KM = ROOT / "relatorio" / "figuras" / "figExA_kaplan_meier_por_frota.png"


# ===========================================================================
# Constantes
# ===========================================================================
LINHAS_ESPERADAS = 544_885
HORIZONTE_HORAS = 4.0  # Horizonte de target_4h para comparacao com LightGBM
LIMIAR_CORR = 0.9  # Limiar de correlacao para drop (Cox/Weibull sensitivos)
LIMIAR_C_INDEX = 0.6  # Limiar minimo de C-index para aceitar Weibull
PENALIZER = 0.01  # Regularizacao L2 para estabilidade numerica

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

# Categoricas com mais de 2 niveis (one-hot encode)
FEATURES_CAT = ["turno", "estado_pre_evento"]


# ===========================================================================
# Etapa 1 - Carregar dados e construir (T, E)
# ===========================================================================
def construir_survival_data(df: pl.DataFrame) -> pl.DataFrame:
    """
    Para cada evento, computa:
      - T_horas: horas ate o proximo DG da mesma TAG (ou ate o fim da
        observacao da TAG, o que vier primeiro)
      - E: 1 se evento (DG) observado, 0 se censurado
    """
    print("Etapa 1/7 - Construindo (T, E) por evento...")

    df = df.sort(["TAG", "Data_Evento"])

    # Para cada TAG, calcular max(Data_Evento) — fim da observacao da TAG
    max_data_por_tag = df.group_by("TAG").agg(
        pl.col("Data_Evento").max().alias("ultima_obs_tag")
    )

    df = df.join(max_data_por_tag, on="TAG", how="left")

    # DataFrame com apenas eventos de DG para join_asof forward
    dgs = (
        df.filter(pl.col("Is_Dont_Go") == 1)
        .select(["TAG", "Data_Evento"])
        .rename({"Data_Evento": "data_proximo_dg"})
        .sort(["TAG", "data_proximo_dg"])
    )

    # join_asof forward: para cada evento, achar o proximo DG da mesma TAG
    # strategy="forward" + tolerance=None -> proximo evento APOS ou IGUAL.
    # Para excluir o proprio evento se for DG, usamos comparacao estrita.
    df = df.sort(["TAG", "Data_Evento"]).join_asof(
        dgs.sort(["TAG", "data_proximo_dg"]),
        left_on="Data_Evento",
        right_on="data_proximo_dg",
        by="TAG",
        strategy="forward",
    )

    # Se o evento e ele mesmo um DG, "data_proximo_dg" pode coincidir;
    # precisamos do PROXIMO DG estritamente > Data_Evento.
    # Heuristica: se data_proximo_dg <= Data_Evento, descartar (pegar nulo).
    df = df.with_columns(
        pl.when(pl.col("data_proximo_dg") > pl.col("Data_Evento"))
        .then(pl.col("data_proximo_dg"))
        .otherwise(None)
        .alias("data_proximo_dg_validada")
    )

    # T_horas e E
    df = df.with_columns(
        pl.when(pl.col("data_proximo_dg_validada").is_not_null())
        .then(
            (pl.col("data_proximo_dg_validada") - pl.col("Data_Evento"))
            .dt.total_seconds() / 3600.0
        )
        .otherwise(
            (pl.col("ultima_obs_tag") - pl.col("Data_Evento"))
            .dt.total_seconds() / 3600.0
        )
        .alias("T_horas"),
        pl.when(pl.col("data_proximo_dg_validada").is_not_null())
        .then(1)
        .otherwise(0)
        .alias("E"),
    )

    # Para DGs que sao o proprio evento, mas que ainda tem DGs futuros,
    # ainda queremos contar — ja tratado acima.
    # Mas DGs que sao o ULTIMO evento da TAG: T=0 e E=0 (descartar).

    n_antes = df.height
    df = df.filter(pl.col("T_horas") > 0)
    n_descartados = n_antes - df.height
    print(f"  Eventos antes do filtro T > 0: {n_antes:,}")
    print(f"  Descartados (T = 0 ou negativo): {n_descartados:,}")
    print(f"  Eventos finais: {df.height:,}")

    # Distribuicao de E por split
    print()
    print("  Distribuicao de E (1=evento observado / 0=censurado) por split:")
    dist = df.group_by("split").agg(
        pl.col("E").sum().alias("eventos_observados"),
        (pl.col("E") == 0).sum().alias("censurados"),
        pl.col("E").count().alias("total"),
    )
    for row in dist.iter_rows(named=True):
        pct_cens = 100.0 * row["censurados"] / row["total"]
        print(f"    {row['split']:<6s}: total={row['total']:>7,}  "
              f"observado={row['eventos_observados']:>6,}  "
              f"censurado={row['censurados']:>6,} ({pct_cens:.1f}%)")

    return df


# ===========================================================================
# Etapa 2 - Preparar features matrix (one-hot, scale, drop correlacao)
# ===========================================================================
def preparar_features(df: pl.DataFrame) -> tuple[pd.DataFrame, list[str], list[str], StandardScaler, dict]:
    """
    Retorna:
      - df_features: pandas DataFrame com features finais + ['T_horas','E','split']
      - features_finais: lista de nomes das colunas usadas no fit
      - features_excluidas: lista de (feat, motivo)
      - scaler: StandardScaler fitado no treino
      - imputacao: dict {feature: valor_imputado} para reproducibilidade
    """
    print()
    print("Etapa 2/7 - Preparando matriz de features...")

    # Selecionar colunas relevantes + targets + split
    cols = FEATURES_NUMERICAS + FEATURES_CAT + ["T_horas", "E", "split",
                                                "target_4h", "TAG", "Tipo"]
    pdf = df.select(cols).to_pandas()

    # Bool -> int
    pdf["valor_disponivel"] = pdf["valor_disponivel"].astype(np.int8)

    # ===== Imputacao de NaN (Cox/Weibull nao toleram NaN) =====
    # Estrategia por feature, com fit no treino:
    train_mask = pdf["split"] == "train"

    imputacao = {}
    # razao_*: imputar com 1.0 (neutro — mesma taxa que baseline)
    for col in ["razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d"]:
        valor = 1.0
        n_null_pre = pdf[col].isna().sum()
        pdf[col] = pdf[col].fillna(valor)
        imputacao[col] = valor
        print(f"  Imputacao {col:<40s}: 1.0 (neutro) - {n_null_pre:,} nulls preenchidos")

    # taxa_DG_operador_30d: imputar com mediana do treino
    col = "taxa_DG_operador_30d"
    valor = float(pdf.loc[train_mask, col].median())
    n_null_pre = pdf[col].isna().sum()
    pdf[col] = pdf[col].fillna(valor)
    imputacao[col] = valor
    print(f"  Imputacao {col:<40s}: {valor:.4f} (mediana train) - {n_null_pre:,} nulls preenchidos")

    # horas_desde_ultimo_critico: imputar com max do treino (worst case = sem evento recente)
    col = "horas_desde_ultimo_critico"
    valor = float(pdf.loc[train_mask, col].max())
    n_null_pre = pdf[col].isna().sum()
    pdf[col] = pdf[col].fillna(valor)
    imputacao[col] = valor
    print(f"  Imputacao {col:<40s}: {valor:.1f}h (max train) - {n_null_pre:,} nulls preenchidos")

    # Validacao defensiva: nenhum NaN em features numericas restantes
    nulos_restantes = pdf[FEATURES_NUMERICAS].isna().sum()
    nulos_restantes = nulos_restantes[nulos_restantes > 0]
    if len(nulos_restantes) > 0:
        print(f"  AVISO: ainda ha NaN em: {dict(nulos_restantes)}")
        # Imputacao final defensiva: zero
        pdf[FEATURES_NUMERICAS] = pdf[FEATURES_NUMERICAS].fillna(0)
        for c in nulos_restantes.index:
            imputacao[c] = 0.0

    # One-hot encode categoricos (drop_first=True para evitar multicolinearidade)
    dummies = pd.get_dummies(
        pdf[FEATURES_CAT], prefix=FEATURES_CAT, drop_first=True, dtype=np.int8
    )
    pdf = pd.concat([pdf.drop(columns=FEATURES_CAT), dummies], axis=1)

    features_apos_onehot = FEATURES_NUMERICAS + list(dummies.columns)
    print()
    print(f"  Features apos one-hot: {len(features_apos_onehot)} "
          f"({len(FEATURES_NUMERICAS)} numericas + {len(dummies.columns)} dummies)")

    # Filtro de correlacao > 0.9 (calculado sobre o treino, ANTES do scaling
    # para evitar artefatos numericos de StandardScaler em colunas constantes)
    print()
    print(f"  Aplicando filtro de correlacao > {LIMIAR_CORR} (calculo sobre train)...")
    corr_abs = pdf.loc[train_mask, features_apos_onehot].corr().abs()

    # Iteracao em ordem do FEATURES_NUMERICAS: para cada feature, ver quais
    # features POSTERIORES tem correlacao > 0.9 e dropar as posteriores
    features_finais = list(features_apos_onehot)
    features_excluidas = []
    i = 0
    while i < len(features_finais):
        feat = features_finais[i]
        # Achar partners posteriores com correlacao > 0.9
        high_partners = []
        for other in features_finais[i + 1:]:
            corr_val = corr_abs.loc[feat, other]
            if pd.notna(corr_val) and corr_val > LIMIAR_CORR:
                high_partners.append((other, corr_val))
        if high_partners:
            # Dropar o partner com maior correlacao
            partner, corr_val = max(high_partners, key=lambda x: x[1])
            features_finais.remove(partner)
            features_excluidas.append({
                "feature_removida": partner,
                "correlacionada_com": feat,
                "correlacao_abs": round(float(corr_val), 4),
            })
        else:
            i += 1

    print(f"  Features excluidas por correlacao: {len(features_excluidas)}")
    for exc in features_excluidas:
        print(f"    - {exc['feature_removida']:<35s} "
              f"(corr={exc['correlacao_abs']:.3f} com {exc['correlacionada_com']})")
    print(f"  Features finais para o fit: {len(features_finais)}")

    # Salvar tabela de features excluidas
    if features_excluidas:
        pl.from_dicts(features_excluidas).write_csv(ARQ_CORR_EXC)
        print(f"  Salvo: {ARQ_CORR_EXC.relative_to(ROOT.parent)}")

    # StandardScaler nas features continuas FINAIS (fit no treino)
    features_binarias = [c for c in features_finais
                         if set(pdf[c].dropna().unique()).issubset({0, 1})]
    features_continuas = [c for c in features_finais if c not in features_binarias]
    print()
    print(f"  Features continuas (StandardScaler): {len(features_continuas)}")
    print(f"  Features binarias (sem scaling): {len(features_binarias)}")

    scaler = StandardScaler()
    scaler.fit(pdf.loc[train_mask, features_continuas])
    pdf[features_continuas] = scaler.transform(pdf[features_continuas])

    # Validacao final: nenhum NaN/Inf em features_finais
    nan_check = pdf[features_finais].isna().sum().sum()
    inf_check = np.isinf(pdf[features_finais].values).sum()
    print(f"  Validacao final: {nan_check} NaN + {inf_check} Inf restantes")
    assert nan_check == 0 and inf_check == 0, "Ainda ha NaN/Inf nas features finais"

    return pdf, features_finais, [e["feature_removida"] for e in features_excluidas], scaler, imputacao


# ===========================================================================
# Etapa 3 - Fit Weibull AFT (com fallback automatico para Cox PH)
# ===========================================================================
def fit_modelo(pdf: pd.DataFrame, features: list[str]) -> tuple[object, str]:
    """
    Tenta WeibullAFT primeiro. Se nao convergir OU C-index val < 0.6, fallback
    para Cox PH.
    Retorna (modelo_fitado, tipo) onde tipo in {'WeibullAFT', 'CoxPH'}.
    """
    print()
    print("Etapa 3/7 - Fitando modelo de sobrevivencia...")

    train = pdf.loc[pdf["split"] == "train", features + ["T_horas", "E"]].copy()
    val = pdf.loc[pdf["split"] == "val", features + ["T_horas", "E"]].copy()

    # === Tentativa 1: Weibull AFT ===
    print()
    print("  [Tentativa 1] WeibullAFTFitter (parametric)...")
    t0 = time.time()
    weibull = WeibullAFTFitter(penalizer=PENALIZER)
    try:
        weibull.fit(train, duration_col="T_horas", event_col="E",
                    show_progress=False)
        elapsed = time.time() - t0
        print(f"    Convergiu em {elapsed:.1f}s")

        # C-index na val. predict_expectation retorna o TEMPO esperado de
        # sobrevivencia (alto = sobrevida longa); concordance_index espera
        # exatamente isso (NAO negativar — usado direto).
        val_pred = weibull.predict_expectation(val)
        c_val = concordance_index(val["T_horas"], val_pred, val["E"])
        print(f"    C-index val: {c_val:.4f}")

        if c_val >= LIMIAR_C_INDEX:
            print(f"    OK (C-index >= {LIMIAR_C_INDEX}) — usando Weibull AFT")
            return weibull, "WeibullAFT"
        else:
            print(f"    C-index < {LIMIAR_C_INDEX} — fallback para Cox PH")
    except (ConvergenceError, Exception) as e:
        elapsed = time.time() - t0
        print(f"    FALHA apos {elapsed:.1f}s: {type(e).__name__}: {str(e)[:100]}")
        print(f"    Fallback para Cox PH...")

    # === Fallback: Cox PH ===
    print()
    print("  [Fallback] CoxPHFitter (semi-parametric)...")
    t0 = time.time()
    cox = CoxPHFitter(penalizer=PENALIZER)
    cox.fit(train, duration_col="T_horas", event_col="E",
            show_progress=False)
    elapsed = time.time() - t0
    print(f"    Convergiu em {elapsed:.1f}s")

    val_partial = cox.predict_partial_hazard(val)
    c_val = concordance_index(val["T_horas"], -val_partial, val["E"])
    print(f"    C-index val: {c_val:.4f}")

    return cox, "CoxPH"


# ===========================================================================
# Etapa 4 - Avaliacao (C-index + AUC-PR contra target_4h)
# ===========================================================================
def avaliar(modelo, tipo: str, pdf: pd.DataFrame, features: list[str]) -> pl.DataFrame:
    print()
    print(f"Etapa 4/7 - Avaliacao em train/val/test ({tipo})...")

    linhas = []
    for split in ["train", "val", "test"]:
        sub = pdf.loc[pdf["split"] == split, features + ["T_horas", "E", "target_4h"]].copy()
        n_total = sub.shape[0]
        n_pos_target4h = int(sub["target_4h"].sum())
        n_eventos_observados = int(sub["E"].sum())

        # C-index
        if tipo == "WeibullAFT":
            tempo_esperado = modelo.predict_expectation(sub)
            c_idx = concordance_index(sub["T_horas"], tempo_esperado, sub["E"])
            # P(T <= 4h) = 1 - S(4h)
            surv_at_4h = modelo.predict_survival_function(
                sub, times=[HORIZONTE_HORAS]
            ).iloc[0].values
            prob_dg_4h = 1.0 - surv_at_4h
        else:  # CoxPH
            partial_hazard = modelo.predict_partial_hazard(sub)
            c_idx = concordance_index(sub["T_horas"], -partial_hazard, sub["E"])
            surv_at_4h = modelo.predict_survival_function(
                sub, times=[HORIZONTE_HORAS]
            ).iloc[0].values
            prob_dg_4h = 1.0 - surv_at_4h

        # AUC-PR contra target_4h (comparavel com LightGBM)
        auc_pr = average_precision_score(sub["target_4h"].values, prob_dg_4h)

        linhas.append({
            "split": split,
            "n_total": n_total,
            "n_eventos_observados": n_eventos_observados,
            "n_pos_target_4h": n_pos_target4h,
            "c_index": round(float(c_idx), 4),
            "auc_pr_target_4h": round(float(auc_pr), 4),
        })

        print(f"  {split:<6s}: n={n_total:>7,}  C-index={c_idx:.4f}  "
              f"AUC-PR(target_4h)={auc_pr:.4f}")

    df_metricas = pl.from_dicts(linhas)
    df_metricas.write_csv(ARQ_METRICAS)
    print(f"  Salvo: {ARQ_METRICAS.relative_to(ROOT.parent)}")
    return df_metricas


# ===========================================================================
# Etapa 5 - Hazard ratios / Time ratios (top features)
# ===========================================================================
def hazard_ratios(modelo, tipo: str) -> pl.DataFrame:
    print()
    print(f"Etapa 5/7 - Tabela de hazard ratios ({tipo})...")

    summary = modelo.summary.copy()
    summary = summary.reset_index()

    if tipo == "WeibullAFT":
        # AFT: exp(coef) = time ratio (TR). Coef positivo -> sobrevida MAIOR (HR < 1).
        # Para alinhar com Cox PH (HR > 1 = risco maior), reportamos TR e
        # tambem o HR equivalente quando aplicavel.
        df_hr = (
            summary[summary["param"] == "lambda_"][
                ["covariate", "coef", "exp(coef)", "coef lower 95%",
                 "coef upper 95%", "p", "exp(coef) lower 95%",
                 "exp(coef) upper 95%"]
            ]
            .rename(columns={
                "exp(coef)": "time_ratio_TR",
                "coef lower 95%": "coef_lower_95",
                "coef upper 95%": "coef_upper_95",
                "exp(coef) lower 95%": "TR_lower_95",
                "exp(coef) upper 95%": "TR_upper_95",
                "p": "p_valor",
            })
        )
        df_hr["interpretacao"] = df_hr["time_ratio_TR"].apply(
            lambda tr: ("RISCO MAIOR (sobrevida menor)" if tr < 1
                        else "RISCO MENOR (sobrevida maior)" if tr > 1
                        else "neutro")
        )
        df_hr = df_hr.sort_values("p_valor")
    else:  # CoxPH
        df_hr = summary[
            ["covariate", "coef", "exp(coef)", "coef lower 95%",
             "coef upper 95%", "p", "exp(coef) lower 95%",
             "exp(coef) upper 95%"]
        ].rename(columns={
            "exp(coef)": "hazard_ratio_HR",
            "coef lower 95%": "coef_lower_95",
            "coef upper 95%": "coef_upper_95",
            "exp(coef) lower 95%": "HR_lower_95",
            "exp(coef) upper 95%": "HR_upper_95",
            "p": "p_valor",
        })
        df_hr["interpretacao"] = df_hr["hazard_ratio_HR"].apply(
            lambda hr: ("RISCO MAIOR" if hr > 1
                        else "RISCO MENOR" if hr < 1
                        else "neutro")
        )
        df_hr = df_hr.sort_values("p_valor")

    # Arredondar colunas numericas
    for col in df_hr.columns:
        if df_hr[col].dtype in [np.float64, np.float32]:
            df_hr[col] = df_hr[col].round(4)

    df_hr_pl = pl.from_pandas(df_hr)
    df_hr_pl.write_csv(ARQ_HAZARD)
    print(f"  Salvo: {ARQ_HAZARD.relative_to(ROOT.parent)} "
          f"({df_hr_pl.height} features)")

    print()
    print("  Top 10 features mais significativas (menor p-valor):")
    if tipo == "WeibullAFT":
        print(f"  {'rank':>4} | {'covariate':<40s} | {'TR':>8s} | {'IC95':>16s} | {'p':>8s}")
        print(f"  {'-'*4} | {'-'*40} | {'-'*8} | {'-'*16} | {'-'*8}")
        for i, row in enumerate(df_hr.head(10).itertuples(index=False), 1):
            ic = f"[{row.TR_lower_95:.2f},{row.TR_upper_95:.2f}]"
            print(f"  {i:>4} | {str(row.covariate):<40s} | "
                  f"{row.time_ratio_TR:>8.3f} | {ic:>16s} | {row.p_valor:>8.4f}")
    else:
        print(f"  {'rank':>4} | {'covariate':<40s} | {'HR':>8s} | {'IC95':>16s} | {'p':>8s}")
        print(f"  {'-'*4} | {'-'*40} | {'-'*8} | {'-'*16} | {'-'*8}")
        for i, row in enumerate(df_hr.head(10).itertuples(index=False), 1):
            ic = f"[{row.HR_lower_95:.2f},{row.HR_upper_95:.2f}]"
            print(f"  {i:>4} | {str(row.covariate):<40s} | "
                  f"{row.hazard_ratio_HR:>8.3f} | {ic:>16s} | {row.p_valor:>8.4f}")

    return df_hr_pl


# ===========================================================================
# Etapa 6 - Kaplan-Meier por frota (Fig Extra A)
# ===========================================================================
def kaplan_meier_por_frota(df: pl.DataFrame) -> None:
    print()
    print("Etapa 6/7 - Kaplan-Meier por frota (Fig Extra A)...")

    pdf = df.select(["Tag_Frota", "T_horas", "E"]).to_pandas()
    pdf = pdf.dropna(subset=["Tag_Frota", "T_horas", "E"])

    frotas = sorted(pdf["Tag_Frota"].dropna().unique())
    print(f"  Frotas presentes: {len(frotas)} -> {frotas}")

    fig, ax = plt.subplots(figsize=(11, 7))
    cores = plt.cm.tab10.colors

    for i, frota in enumerate(frotas):
        sub = pdf[pdf["Tag_Frota"] == frota]
        if sub.shape[0] < 10:
            continue
        kmf = KaplanMeierFitter()
        kmf.fit(durations=sub["T_horas"], event_observed=sub["E"],
                label=f"{frota} (n={sub.shape[0]:,})")
        kmf.plot_survival_function(ax=ax, ci_show=True, color=cores[i % 10])

    ax.set_xlim(0, 168)  # 7 dias
    ax.set_xlabel("Tempo desde o evento (horas)", fontsize=11)
    ax.set_ylabel("P(novo DG ainda nao ocorreu)", fontsize=11)
    ax.set_title(
        "Figura Extra A - Curva Kaplan-Meier por frota (7 dias)\n"
        "Sobrevivencia empirica entre eventos consecutivos. "
        "Frotas com curva mais alta = menor risco de DG.",
        fontsize=12, fontweight="bold",
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    ARQ_FIG_KM.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ARQ_FIG_KM, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {ARQ_FIG_KM.relative_to(ROOT.parent)}")


# ===========================================================================
# Etapa 7 - Salvar modelo
# ===========================================================================
def salvar_modelo(modelo, tipo: str, features: list[str], scaler: StandardScaler,
                  imputacao: dict) -> None:
    print()
    print("Etapa 7/7 - Salvando modelo...")
    ARQ_MODELO.parent.mkdir(parents=True, exist_ok=True)
    artefato = {
        "modelo": modelo,
        "tipo": tipo,
        "features": features,
        "scaler": scaler,
        "horizonte_horas": HORIZONTE_HORAS,
        "imputacao": imputacao,
    }
    joblib.dump(artefato, ARQ_MODELO, compress=3)
    mb = ARQ_MODELO.stat().st_size / 1024 / 1024
    print(f"  Salvo: {ARQ_MODELO.relative_to(ROOT.parent)} ({mb:.2f} MB)")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("09_sobrevivencia.py - Weibull AFT + fallback Cox PH")
    print("=" * 70)

    if not ARQ_V3.exists():
        raise FileNotFoundError(f"v3.parquet ausente: {ARQ_V3}")

    df = pl.read_parquet(ARQ_V3)
    print(f"v3.parquet shape: {df.shape}")
    assert df.height == LINHAS_ESPERADAS

    df = construir_survival_data(df)
    pdf, features, excluidas, scaler, imputacao = preparar_features(df)
    modelo, tipo = fit_modelo(pdf, features)
    df_metricas = avaliar(modelo, tipo, pdf, features)
    df_hr = hazard_ratios(modelo, tipo)
    kaplan_meier_por_frota(df)
    salvar_modelo(modelo, tipo, features, scaler, imputacao)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"Modelo final: {tipo}")
    print(f"Features finais: {len(features)}")
    print(f"Features excluidas por correlacao > {LIMIAR_CORR}: {len(excluidas)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
