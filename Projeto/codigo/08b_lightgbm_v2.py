"""
08b_lightgbm_v2.py - LightGBM v2 (W6): Optuna + TimeSeriesSplit CV + determinismo.

Refina o LightGBM v1 (Variante A) substituindo:
  - parametros default -> Optuna com 50 trials sobre espaco de 7 hiperparametros
  - validacao single-fold (so mai) -> TimeSeriesSplit CV de 4 folds expandidos
    (Mitigacao 1 — registrada em PLANEJAMENTO.md W6)
  - n_jobs=-1 sem determinismo -> deterministic=True + force_col_wise=True
    (registrado em PLANEJAMENTO.md W6 e em decisao W5 24/05/2026)

Resultado canonico que vai para o relatorio final.

Espaco de busca refinado pela conclusao empirica da Mitigacao 2 em v1:
  scale_pos_weight em [0.5, 3.0] (originalmente [0.5, 6.0] no plano, mas
  v1 mostrou que valores > 2.0 nao ajudam — controle_alteracoes.md 23/05).

TimeSeriesSplit walk-forward expandido (Mitigacao 1):
  Fold 1: treino=jan,        val=fev
  Fold 2: treino=jan-fev,    val=mar
  Fold 3: treino=jan-fev-mar, val=abr
  Fold 4: treino=jan-fev-mar-abr (=treino original), val=mai (=val original)

Metrica de tuning: AUC-PR media dos 4 folds.

DETERMINISMO ESTRITO (registrado em PLANEJAMENTO.md 24/05):
  deterministic=True + force_col_wise=True -> dois runs produzem AUC-PR
  bit-exact ate a ultima casa decimal. Custo: ~15-30% de tempo a mais.

Entradas:
  - Projeto/dados/features/v3.parquet (544.885 x 58)
  - Projeto/relatorio/tabelas/baseline_metricas.csv (referencia para GATE)
  - Projeto/relatorio/tabelas/lightgbm_v1_metricas.csv (referencia v1 A)

Saidas:
  - Projeto/modelos/lightgbm_v2.txt (modelo canonico)
  - Projeto/modelos/optuna_study_v2.pkl (study completo para auditoria)
  - Projeto/relatorio/tabelas/lightgbm_v2_metricas.csv
  - Projeto/relatorio/tabelas/lightgbm_v2_hiperparametros.csv
  - Projeto/relatorio/tabelas/optuna_trials.csv (50 trials para auditoria)

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/08b_lightgbm_v2.py
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
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
)

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")
optuna.logging.set_verbosity(optuna.logging.WARNING)


# ===========================================================================
# Caminhos
# ===========================================================================
ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_BASELINE = ROOT / "relatorio" / "tabelas" / "baseline_metricas.csv"
ARQ_V1 = ROOT / "relatorio" / "tabelas" / "lightgbm_v1_metricas.csv"

DIR_MODELOS = ROOT / "modelos"
ARQ_MODELO_V2 = DIR_MODELOS / "lightgbm_v2.txt"
ARQ_STUDY = DIR_MODELOS / "optuna_study_v2.pkl"

ARQ_METRICAS = ROOT / "relatorio" / "tabelas" / "lightgbm_v2_metricas.csv"
ARQ_HIPERPARAM = ROOT / "relatorio" / "tabelas" / "lightgbm_v2_hiperparametros.csv"
ARQ_TRIALS = ROOT / "relatorio" / "tabelas" / "optuna_trials.csv"


# ===========================================================================
# Constantes
# ===========================================================================
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
N_TRAIN = 394_971
N_VAL = 78_825
N_TEST = 71_089

SEED = 42
N_TRIALS = 50

TARGET = "target_4h"

# Features (35) — mesma lista do 08_lightgbm.py
FEATURES = [
    "hora_dia", "dia_semana", "turno", "mes", "valor_disponivel",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    "horas_desde_ultimo_DG", "horas_desde_ultimo_critico",
    "estado_pre_evento",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
]
N_FEATURES = len(FEATURES)
CAT_FEATURES = ["turno", "estado_pre_evento"]

# Parametros base (fixos para todos os trials e modelo final)
PARAMS_BASE = {
    "objective": "binary",
    "verbosity": -1,
    "random_state": SEED,
    "n_jobs": -1,
    # Determinismo estrito
    "deterministic": True,
    "force_col_wise": True,
}

# GATE MARCO 1 thresholds (re-calibrados em 22/05)
GATE_VAL_MIN = 0.2897
GATE_TEST_MIN = 0.6303


# ===========================================================================
# Etapa 1 - Carregar v3.parquet
# ===========================================================================
def carregar() -> pl.DataFrame:
    print("Etapa 1/7 - Carregando v3.parquet...")
    df = pl.read_parquet(ARQ_V3)
    print(f"  Shape: {df.shape}")
    assert df.height == LINHAS_ESPERADAS

    # Mes de cada evento (para definir folds CV walk-forward)
    df = df.with_columns(pl.col("Data_Evento").dt.month().alias("_mes_evento"))

    print(f"  {N_FEATURES} features | target = {TARGET}")
    return df


# ===========================================================================
# Etapa 2 - Definir 4 folds TimeSeriesSplit walk-forward expandido
# ===========================================================================
def definir_folds(df: pl.DataFrame) -> list[dict]:
    """
    4 folds walk-forward expandidos sobre o split 'train' (jan-abr) + 'val' (mai).

    Cada fold reusa todos os dados anteriores como treino e adiciona um mes
    como validacao. Mai (Fold 4) usa o split 'val' original do projeto;
    a CV cobre jan-fev-mar-abr-mai mas NUNCA toca em jun (test).
    """
    print()
    print("Etapa 2/7 - Definindo 4 folds CV walk-forward expandido...")

    folds = [
        {"nome": "Fold 1", "treino_meses": [1],         "val_mes": 2},
        {"nome": "Fold 2", "treino_meses": [1, 2],      "val_mes": 3},
        {"nome": "Fold 3", "treino_meses": [1, 2, 3],   "val_mes": 4},
        {"nome": "Fold 4", "treino_meses": [1, 2, 3, 4],"val_mes": 5},
    ]

    # Indices booleanos pre-computados (acelera Optuna trials)
    for f in folds:
        # Treino: meses [treino_meses] e dentro do split 'train' (jan-abr)
        # OBS: val_mes=5 vem do split 'val'; jan-abr vem do split 'train'
        f["_mask_train"] = (
            (df["_mes_evento"].is_in(f["treino_meses"]))
            & (df["split"].is_in(["train", "val"]))  # mai pode ser val mas precisamos incluir
        )
        f["_mask_val"] = (
            (df["_mes_evento"] == f["val_mes"])
            & (df["split"].is_in(["train", "val"]))
        )
        n_t = f["_mask_train"].sum()
        n_v = f["_mask_val"].sum()
        print(f"  {f['nome']}: treino={n_t:,} (meses {f['treino_meses']})  "
              f"val={n_v:,} (mes {f['val_mes']})")

        # Asercao critica walk-forward: nenhum evento de treino pos-val
        if n_t > 0 and n_v > 0:
            max_train = df.filter(f["_mask_train"])["Data_Evento"].max()
            min_val = df.filter(f["_mask_val"])["Data_Evento"].min()
            assert max_train < min_val, (
                f"{f['nome']}: leak temporal — max_train ({max_train}) >= "
                f"min_val ({min_val})"
            )

    print("  Asercoes walk-forward OK em todos os 4 folds")
    return folds


# ===========================================================================
# Helper - Preparar X, y filtrado por mascara
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
# Etapa 3 - Funcao objective do Optuna
# ===========================================================================
def make_objective(df: pl.DataFrame, folds: list[dict]):
    """Cria a funcao objective do Optuna com closure sobre df e folds."""
    def objective(trial: optuna.Trial) -> float:
        # 7 hiperparametros amostrados
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


# ===========================================================================
# Etapa 4 - Rodar Optuna study
# ===========================================================================
def rodar_optuna(df: pl.DataFrame, folds: list[dict]) -> optuna.Study:
    print()
    print(f"Etapa 4/7 - Optuna study ({N_TRIALS} trials, TPESampler seed={SEED})...")
    print(f"  Espaco de busca: 7 hiperparametros")
    print(f"  Metrica: AUC-PR media dos 4 folds (Mitigacao 1)")
    print(f"  Tempo estimado: ~10 min (4 folds x 50 trials)")
    print()

    sampler = optuna.samplers.TPESampler(seed=SEED)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    objective = make_objective(df, folds)

    t0 = time.time()
    # show_progress_bar=False evita poluicao em ambientes sem terminal interativo
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)
    elapsed = time.time() - t0

    print(f"  Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Best AUC-PR (CV media): {study.best_value:.4f}")
    print(f"  Best trial: #{study.best_trial.number}")
    print(f"  Best params:")
    for k, v in study.best_params.items():
        print(f"    {k:<22s}: {v}")

    return study


# ===========================================================================
# Etapa 5 - Treinar modelo final + avaliar
# ===========================================================================
def treinar_final(df: pl.DataFrame, best_params: dict) -> tuple[lgb.LGBMClassifier, dict]:
    print()
    print("Etapa 5/7 - Treinando LightGBM v2 final (best params + determinismo)...")

    final_params = {**PARAMS_BASE, **best_params}
    modelo = lgb.LGBMClassifier(**final_params)

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
            "precision_05": float(precision_score(y, pred, zero_division=0)),
            "recall_05": float(recall_score(y, pred, zero_division=0)),
            "f1_05": float(f1_score(y, pred, zero_division=0)),
        }

    m_train = _metricas(X_train, y_train)
    m_val = _metricas(X_val, y_val)
    m_test = _metricas(X_test, y_test)

    print(f"  Tempo de treino final: {elapsed:.1f}s")
    print(f"  AUC-PR train: {m_train['auc_pr']:.4f}  "
          f"val: {m_val['auc_pr']:.4f}  test: {m_test['auc_pr']:.4f}")

    # Salvar modelo
    DIR_MODELOS.mkdir(parents=True, exist_ok=True)
    modelo.booster_.save_model(str(ARQ_MODELO_V2))
    print(f"  Modelo salvo: {ARQ_MODELO_V2.relative_to(ROOT.parent)}")

    return modelo, {
        "train": m_train, "val": m_val, "test": m_test,
        "tempo_treino_s": elapsed,
    }


# ===========================================================================
# Etapa 6 - Tabelas + comparacao com v1
# ===========================================================================
def gerar_tabelas(study: optuna.Study, resultados: dict) -> None:
    print()
    print("Etapa 6/7 - Gerando tabelas...")

    # ---- Metricas v2 ----
    linhas = []
    for split in ["train", "val", "test"]:
        m = resultados[split]
        linhas.append({
            "split": split,
            "n_eventos": m["n_eventos"],
            "n_positivos": m["n_positivos"],
            "auc_pr": round(m["auc_pr"], 4),
            "precision_05": round(m["precision_05"], 4),
            "recall_05": round(m["recall_05"], 4),
            "f1_05": round(m["f1_05"], 4),
        })
    # Linha adicional com a media CV (Mitigacao 1) para auditoria
    linhas.append({
        "split": "cv_mean_4folds",
        "n_eventos": "N/A",
        "n_positivos": "N/A",
        "auc_pr": round(study.best_value, 4),
        "precision_05": "N/A",
        "recall_05": "N/A",
        "f1_05": "N/A",
    })
    pl.from_dicts(linhas).write_csv(ARQ_METRICAS)
    print(f"  {ARQ_METRICAS.relative_to(ROOT.parent)} ({len(linhas)} linhas)")

    # ---- Hiperparametros ----
    espaco_busca = {
        "n_estimators": "int [50, 500]",
        "learning_rate": "log [0.01, 0.3]",
        "num_leaves": "int [15, 127]",
        "min_child_samples": "int [10, 100]",
        "scale_pos_weight": "uniform [0.5, 3.0]",
        "lambda_l1": "log [0.001, 10]",
        "lambda_l2": "log [0.001, 10]",
    }
    hp_linhas = []
    for k, faixa in espaco_busca.items():
        hp_linhas.append({
            "hiperparametro": k,
            "espaco_busca": faixa,
            "best_value": study.best_params[k],
        })
    pl.from_dicts(hp_linhas).write_csv(ARQ_HIPERPARAM)
    print(f"  {ARQ_HIPERPARAM.relative_to(ROOT.parent)} ({len(hp_linhas)} hiperparametros)")

    # ---- Trials Optuna ----
    trials_data = []
    for t in study.trials:
        row = {
            "trial": t.number,
            "value_auc_pr_cv": round(t.value, 4) if t.value is not None else None,
            "state": str(t.state.name),
        }
        for k, v in t.params.items():
            row[k] = v
        trials_data.append(row)
    pl.from_dicts(trials_data).write_csv(ARQ_TRIALS)
    print(f"  {ARQ_TRIALS.relative_to(ROOT.parent)} ({len(trials_data)} trials)")


# ===========================================================================
# Etapa 7 - Sumario comparativo v2 vs v1 vs baseline + GATE
# ===========================================================================
def sumario_comparativo(resultados: dict) -> None:
    print()
    print("=" * 70)
    print("COMPARATIVO v2 vs v1 (Variante A) vs Baseline")
    print("=" * 70)

    # Carregar v1 e baseline
    v1 = pl.read_csv(ARQ_V1)
    baseline = pl.read_csv(ARQ_BASELINE)

    for split in ["val", "test"]:
        v2_auc = resultados[split]["auc_pr"]
        # v1 A (linhas onde variante=='A' e split correspondente)
        v1_auc = v1.filter(
            (pl.col("variante") == "A") & (pl.col("split") == split)
        )["auc_pr"][0]
        base_auc = baseline.filter(pl.col("split") == split)["auc_pr"][0]

        print()
        print(f"  {split.upper()} (mai={split=='val'} jun={split=='test'}):")
        print(f"    Baseline   AUC-PR: {base_auc:.4f}")
        print(f"    LightGBM v1: {v1_auc:.4f}  (+{(v1_auc-base_auc)*100:+.2f}pp vs baseline)")
        print(f"    LightGBM v2: {v2_auc:.4f}  (+{(v2_auc-v1_auc)*100:+.2f}pp vs v1, "
              f"+{(v2_auc-base_auc)*100:+.2f}pp vs baseline)")

    # GATE MARCO 1
    auc_val = resultados["val"]["auc_pr"]
    auc_test = resultados["test"]["auc_pr"]
    crit_A = auc_val >= GATE_VAL_MIN
    crit_B = auc_test >= GATE_TEST_MIN

    print()
    print("=" * 70)
    print("GATE MARCO 1 (re-confirmacao em v2)")
    print("=" * 70)
    print(f"  Criterio A (val >= {GATE_VAL_MIN}): {auc_val:.4f} -> "
          f"{'PASS' if crit_A else 'FAIL'}")
    print(f"  Criterio B (test >= {GATE_TEST_MIN}): {auc_test:.4f} -> "
          f"{'PASS' if crit_B else 'FAIL'}")
    if crit_A and crit_B:
        print("  VERDICT: PASS — v2 confirma o GATE e e o resultado canonico")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("08b_lightgbm_v2.py - LightGBM v2 (Optuna + CV + determinismo)")
    print("=" * 70)

    df = carregar()
    folds = definir_folds(df)
    study = rodar_optuna(df, folds)

    # Salvar study para auditoria
    DIR_MODELOS.mkdir(parents=True, exist_ok=True)
    with open(ARQ_STUDY, "wb") as f:
        pickle.dump(study, f)
    print(f"  Study salvo: {ARQ_STUDY.relative_to(ROOT.parent)}")

    modelo, resultados = treinar_final(df, study.best_params)
    gerar_tabelas(study, resultados)
    sumario_comparativo(resultados)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
