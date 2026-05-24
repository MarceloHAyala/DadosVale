"""
08e_lightgbm_v2_no_cascade.py - Variante v2 sem `horas_desde_ultimo_DG`.

Clone do 08b_lightgbm_v2.py com UMA UNICA diferenca: removida a feature
`horas_desde_ultimo_DG` da lista de FEATURES (34 features em vez de 35).
Tudo o mais identico — mesma matriz v3.parquet, mesma TimeSeriesSplit CV
de 4 folds, mesmo Optuna (50 trials, TPESampler seed=42), mesmo determinismo.

Motivacao (mini-diagnose 24/05/2026 — Opcao B):
  SHAP v2 mostrou que `horas_desde_ultimo_DG` (rank #1, 39% do peso) e' uma
  feature de PREDICAO DE CASCATA, nao de primeiro DG. Top 10% dos eventos com
  maior SHAP positivo dessa feature: 100% tem DG anterior em <2h (mediana 1
  minuto), 94% sao DG real. Sem essa feature (NULL ou > 24h), apenas 1% dos
  101 DGs "primeira-vez" sao corretamente preditos. v2 e' essencialmente um
  detector de cascatas em curso, nao um preditor de primeiro DG.

Pergunta empirica:
  Quanto v2 perde de AUC-PR ao remover essa feature? E quanto ganha em recall
  no subgrupo "primeiro DG"? A resposta informa se v3 deve ser o canonico
  (Opcao D — deploy paralelo de v2 e v3) ou se a Opcao A (manter v2 + documentar
  limitacao) e' mais defensavel.

Manter `horas_desde_ultimo_critico` (rank #7, 1.07% do peso) — nao e' fonte
primaria do problema; sinal em outra escala (Criticos sao mais frequentes
que DGs, autocorrelacao mais fraca).

Entradas:
  - Projeto/dados/features/v3.parquet (544.885 x 58)
  - Projeto/relatorio/tabelas/lightgbm_v2_metricas.csv (referencia v2)

Saidas:
  - Projeto/modelos/lightgbm_v2_no_cascade.txt
  - Projeto/modelos/optuna_study_v2_no_cascade.pkl
  - Projeto/relatorio/tabelas/lightgbm_v2_no_cascade_metricas.csv
  - Projeto/relatorio/tabelas/lightgbm_v2_no_cascade_hiperparametros.csv
  - Projeto/relatorio/tabelas/v2_vs_v2_no_cascade.csv (comparativo critico)

Executar:
    uv run python Projeto/codigo/08e_lightgbm_v2_no_cascade.py
"""
from pathlib import Path
import pickle
import time
import warnings

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
import polars as pl
from sklearn.metrics import average_precision_score, recall_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")
optuna.logging.set_verbosity(optuna.logging.WARNING)


# ===========================================================================
# Caminhos
# ===========================================================================
ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_V2_METRICAS = ROOT / "relatorio" / "tabelas" / "lightgbm_v2_metricas.csv"
ARQ_V2_MODELO = ROOT / "modelos" / "lightgbm_v2.txt"

DIR_MODELOS = ROOT / "modelos"
ARQ_MODELO_NC = DIR_MODELOS / "lightgbm_v2_no_cascade.txt"
ARQ_STUDY_NC = DIR_MODELOS / "optuna_study_v2_no_cascade.pkl"

ARQ_METRICAS_NC = ROOT / "relatorio" / "tabelas" / "lightgbm_v2_no_cascade_metricas.csv"
ARQ_HIPERPARAM_NC = ROOT / "relatorio" / "tabelas" / "lightgbm_v2_no_cascade_hiperparametros.csv"
ARQ_COMPARATIVO = ROOT / "relatorio" / "tabelas" / "v2_vs_v2_no_cascade.csv"


# ===========================================================================
# Constantes
# ===========================================================================
LINHAS_ESPERADAS = 544_885
N_TRAIN = 394_971
N_VAL = 78_825
N_TEST = 71_089

SEED = 42
N_TRIALS = 50
TARGET = "target_4h"

# 34 features = 35 originais menos `horas_desde_ultimo_DG`
FEATURES = [
    "hora_dia", "dia_semana", "turno", "mes", "valor_disponivel",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    # `horas_desde_ultimo_DG` REMOVIDA aqui (era a feature problematica)
    "horas_desde_ultimo_critico",  # MANTIDA (rank #7, baixo impacto)
    "estado_pre_evento",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
]
N_FEATURES = len(FEATURES)  # 34
CAT_FEATURES = ["turno", "estado_pre_evento"]

PARAMS_BASE = {
    "objective": "binary",
    "verbosity": -1,
    "random_state": SEED,
    "n_jobs": -1,
    "deterministic": True,
    "force_col_wise": True,
}


# ===========================================================================
# Etapas 1-2 - Carregar e definir folds (identicos ao 08b)
# ===========================================================================
def carregar() -> pl.DataFrame:
    print("Etapa 1/7 - Carregando v3.parquet...")
    df = pl.read_parquet(ARQ_V3)
    print(f"  Shape: {df.shape}")
    assert df.height == LINHAS_ESPERADAS
    df = df.with_columns(pl.col("Data_Evento").dt.month().alias("_mes_evento"))
    print(f"  {N_FEATURES} features (sem horas_desde_ultimo_DG) | target = {TARGET}")
    return df


def definir_folds(df: pl.DataFrame) -> list[dict]:
    print()
    print("Etapa 2/7 - Definindo 4 folds CV walk-forward expandido...")
    folds = [
        {"nome": "Fold 1", "treino_meses": [1],         "val_mes": 2},
        {"nome": "Fold 2", "treino_meses": [1, 2],      "val_mes": 3},
        {"nome": "Fold 3", "treino_meses": [1, 2, 3],   "val_mes": 4},
        {"nome": "Fold 4", "treino_meses": [1, 2, 3, 4],"val_mes": 5},
    ]
    for f in folds:
        f["_mask_train"] = (
            (df["_mes_evento"].is_in(f["treino_meses"]))
            & (df["split"].is_in(["train", "val"]))
        )
        f["_mask_val"] = (
            (df["_mes_evento"] == f["val_mes"])
            & (df["split"].is_in(["train", "val"]))
        )
        print(f"  {f['nome']}: treino={f['_mask_train'].sum():,}  "
              f"val={f['_mask_val'].sum():,}")
    return folds


# ===========================================================================
# Helpers - preparacao de X/y
# ===========================================================================
def preparar_X_y_mask(df: pl.DataFrame, mask: pl.Series) -> tuple[pd.DataFrame, np.ndarray]:
    sub = df.filter(mask).select(FEATURES + [TARGET])
    pdf = sub.to_pandas()
    y = pdf[TARGET].to_numpy().astype(np.int8)
    X = pdf[FEATURES].copy()
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return X, y


def preparar_X_y_split(df: pl.DataFrame, split: str) -> tuple[pd.DataFrame, np.ndarray]:
    return preparar_X_y_mask(df, df["split"] == split)


# ===========================================================================
# Etapa 3-4 - Optuna
# ===========================================================================
def make_objective(df: pl.DataFrame, folds: list[dict]):
    def objective(trial: optuna.Trial) -> float:
        params = {
            **PARAMS_BASE,
            "n_estimators": trial.suggest_int("n_estimators", 50, 500),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
            "scale_pos_weight": trial.suggest_float("scale_pos_weight", 0.5, 3.0),
            "lambda_l1": trial.suggest_float("lambda_l1", 1e-3, 10.0, log=True),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
        }
        aucs = []
        for f in folds:
            X_tr, y_tr = preparar_X_y_mask(df, f["_mask_train"])
            X_vl, y_vl = preparar_X_y_mask(df, f["_mask_val"])
            modelo = lgb.LGBMClassifier(**params)
            modelo.fit(X_tr, y_tr, categorical_feature=CAT_FEATURES)
            proba = modelo.predict_proba(X_vl)[:, 1]
            aucs.append(float(average_precision_score(y_vl, proba)))
        return float(np.mean(aucs))
    return objective


def rodar_optuna(df: pl.DataFrame, folds: list[dict]) -> optuna.Study:
    print()
    print(f"Etapa 3/7 - Optuna ({N_TRIALS} trials, seed={SEED}, 34 features)...")
    print(f"  Tempo estimado: ~25-30 min")
    print()
    sampler = optuna.samplers.TPESampler(seed=SEED)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    objective = make_objective(df, folds)
    t0 = time.time()
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)
    elapsed = time.time() - t0
    print(f"  Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Best AUC-PR (CV): {study.best_value:.4f}")
    print(f"  Best trial: #{study.best_trial.number}")
    print(f"  Best params:")
    for k, v in study.best_params.items():
        print(f"    {k:<22s}: {v}")
    return study


# ===========================================================================
# Etapa 5 - Treinar modelo final
# ===========================================================================
def treinar_final(df: pl.DataFrame, best_params: dict) -> tuple[lgb.LGBMClassifier, dict]:
    print()
    print("Etapa 5/7 - Treinando modelo final no_cascade...")
    params = {**PARAMS_BASE, **best_params}
    modelo = lgb.LGBMClassifier(**params)
    X_train, y_train = preparar_X_y_split(df, "train")
    X_val, y_val = preparar_X_y_split(df, "val")
    X_test, y_test = preparar_X_y_split(df, "test")
    t0 = time.time()
    modelo.fit(X_train, y_train, categorical_feature=CAT_FEATURES)
    elapsed = time.time() - t0

    def _metricas(X, y) -> dict:
        proba = modelo.predict_proba(X)[:, 1]
        pred = (proba >= 0.5).astype(np.int8)
        return {
            "n_eventos": int(len(y)),
            "n_positivos": int(y.sum()),
            "auc_pr": float(average_precision_score(y, proba)),
            "recall_05": float(recall_score(y, pred, zero_division=0)),
            "proba": proba,
        }

    m = {
        "train": _metricas(X_train, y_train),
        "val": _metricas(X_val, y_val),
        "test": _metricas(X_test, y_test),
        "tempo_treino_s": elapsed,
    }
    print(f"  Tempo de treino: {elapsed:.1f}s")
    print(f"  AUC-PR train={m['train']['auc_pr']:.4f}  "
          f"val={m['val']['auc_pr']:.4f}  test={m['test']['auc_pr']:.4f}")

    DIR_MODELOS.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(ARQ_MODELO_NC))
    print(f"  Modelo salvo: {ARQ_MODELO_NC.relative_to(ROOT.parent)}")
    return modelo, m


# ===========================================================================
# Etapa 6 - Analise comparativa critica v2 vs v3_no_cascade
# ===========================================================================
def analise_comparativa(df: pl.DataFrame, m_nc: dict) -> pl.DataFrame:
    print()
    print("Etapa 6/7 - Analise comparativa v2 vs v3_no_cascade...")

    # Carregar v2 (modelo canonico atual)
    v2_booster = lgb.Booster(model_file=str(ARQ_V2_MODELO))

    linhas = []

    # Para cada split, calcular AUC-PR e recall ESTRATIFICADOS por subgrupo
    for split in ["val", "test"]:
        sub = df.filter(pl.col("split") == split)

        # Features para v2 (35 features, incluindo horas_desde_ultimo_DG)
        FEATURES_V2 = FEATURES.copy()
        # Inserir horas_desde_ultimo_DG na posicao correta
        # (entre count_total_24h e horas_desde_ultimo_critico)
        idx_insert = FEATURES_V2.index("horas_desde_ultimo_critico")
        FEATURES_V2.insert(idx_insert, "horas_desde_ultimo_DG")

        pdf_v2 = sub.select(FEATURES_V2 + [TARGET]).to_pandas()
        X_v2 = pdf_v2[FEATURES_V2].copy()
        for c in CAT_FEATURES:
            X_v2[c] = X_v2[c].astype("category")
        if X_v2["valor_disponivel"].dtype == "bool":
            X_v2["valor_disponivel"] = X_v2["valor_disponivel"].astype(np.int8)
        y = pdf_v2[TARGET].to_numpy().astype(np.int8)
        proba_v2 = v2_booster.predict(X_v2)

        # Features para v3 (34, sem horas_desde_ultimo_DG) -- ja preparada
        proba_v3 = m_nc[split]["proba"]

        # Subgrupos
        horas = sub["horas_desde_ultimo_DG"].to_numpy()
        is_first_dg = np.isnan(horas) | (horas > 24)  # sem DG recente
        is_cascade = ~np.isnan(horas) & (horas <= 4)  # DG nas ultimas 4h

        n_first_dg = int(is_first_dg.sum())
        n_cascade = int(is_cascade.sum())
        n_first_dg_pos = int((y[is_first_dg] == 1).sum())
        n_cascade_pos = int((y[is_cascade] == 1).sum())

        # Metricas por subgrupo
        for subgrupo, mask in [
            ("geral", np.ones_like(y, dtype=bool)),
            ("primeiro_DG (sem DG <= 24h ou NULL)", is_first_dg),
            ("cascata (DG <= 4h)", is_cascade),
        ]:
            if mask.sum() == 0 or y[mask].sum() == 0:
                continue
            for modelo_nome, proba in [("v2", proba_v2), ("v3_no_cascade", proba_v3)]:
                auc = float(average_precision_score(y[mask], proba[mask]))
                pred = (proba[mask] >= 0.5).astype(np.int8)
                rec = float(recall_score(y[mask], pred, zero_division=0))
                linhas.append({
                    "split": split,
                    "subgrupo": subgrupo,
                    "n_eventos": int(mask.sum()),
                    "n_positivos": int(y[mask].sum()),
                    "modelo": modelo_nome,
                    "auc_pr": round(auc, 4),
                    "recall_05": round(rec, 4),
                })

    comp = pl.from_dicts(linhas)
    comp.write_csv(ARQ_COMPARATIVO)
    print(f"  {ARQ_COMPARATIVO.relative_to(ROOT.parent)} ({comp.height} linhas)")
    return comp


# ===========================================================================
# Etapa 7 - Tabelas + sumario
# ===========================================================================
def gerar_tabelas(study: optuna.Study, m_nc: dict) -> None:
    print()
    print("Etapa 7/7 - Tabelas auxiliares...")
    # Metricas v3
    linhas = []
    for split in ["train", "val", "test"]:
        ms = m_nc[split]
        linhas.append({
            "split": split,
            "n_eventos": ms["n_eventos"],
            "n_positivos": ms["n_positivos"],
            "auc_pr": round(ms["auc_pr"], 4),
            "recall_05": round(ms["recall_05"], 4),
        })
    linhas.append({
        "split": "cv_mean_4folds", "n_eventos": "N/A", "n_positivos": "N/A",
        "auc_pr": round(study.best_value, 4), "recall_05": "N/A",
    })
    pl.from_dicts(linhas).write_csv(ARQ_METRICAS_NC)
    print(f"  {ARQ_METRICAS_NC.relative_to(ROOT.parent)}")

    # Hiperparametros
    espaco = {
        "n_estimators": "int [50, 500]",
        "learning_rate": "log [0.01, 0.3]",
        "num_leaves": "int [15, 127]",
        "min_child_samples": "int [10, 100]",
        "scale_pos_weight": "uniform [0.5, 3.0]",
        "lambda_l1": "log [0.001, 10]",
        "lambda_l2": "log [0.001, 10]",
    }
    hp = [{"hiperparametro": k, "espaco_busca": v, "best_value": study.best_params[k]}
          for k, v in espaco.items()]
    pl.from_dicts(hp).write_csv(ARQ_HIPERPARAM_NC)
    print(f"  {ARQ_HIPERPARAM_NC.relative_to(ROOT.parent)}")


def sumario(comp: pl.DataFrame, m_nc: dict) -> None:
    print()
    print("=" * 70)
    print("COMPARATIVO v2 (com cascade feature) vs v3 (sem cascade feature)")
    print("=" * 70)
    for split in ["val", "test"]:
        print()
        print(f"  {split.upper()}:")
        for subgrupo in ["geral", "primeiro_DG (sem DG <= 24h ou NULL)", "cascata (DG <= 4h)"]:
            sub = comp.filter((pl.col("split") == split) & (pl.col("subgrupo") == subgrupo))
            if sub.height == 0:
                continue
            n_ev = sub["n_eventos"][0]
            n_pos = sub["n_positivos"][0]
            v2_row = sub.filter(pl.col("modelo") == "v2")
            v3_row = sub.filter(pl.col("modelo") == "v3_no_cascade")
            if v2_row.height == 0 or v3_row.height == 0:
                continue
            v2_auc = v2_row["auc_pr"][0]
            v3_auc = v3_row["auc_pr"][0]
            v2_rec = v2_row["recall_05"][0]
            v3_rec = v3_row["recall_05"][0]
            print(f"    {subgrupo:<40s} (n={n_ev:>6,}, pos={n_pos:>5,}):")
            print(f"      AUC-PR:  v2 = {v2_auc:.4f}  | v3 = {v3_auc:.4f}  | diff = {(v3_auc-v2_auc)*100:+.2f}pp")
            print(f"      Recall:  v2 = {v2_rec:.4f}  | v3 = {v3_rec:.4f}  | diff = {(v3_rec-v2_rec)*100:+.2f}pp")
    print()
    print("=" * 70)


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("08e_lightgbm_v2_no_cascade.py - Variante sem horas_desde_ultimo_DG")
    print("=" * 70)

    df = carregar()
    folds = definir_folds(df)
    study = rodar_optuna(df, folds)

    DIR_MODELOS.mkdir(parents=True, exist_ok=True)
    with open(ARQ_STUDY_NC, "wb") as f:
        pickle.dump(study, f)
    print(f"  Study salvo: {ARQ_STUDY_NC.relative_to(ROOT.parent)}")

    modelo, m_nc = treinar_final(df, study.best_params)
    comp = analise_comparativa(df, m_nc)
    gerar_tabelas(study, m_nc)
    sumario(comp, m_nc)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
