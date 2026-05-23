"""
08_lightgbm.py - LightGBM v1 (W5): 5 variantes + GATE MARCO 1.

Treina 5 modelos LightGBM com parametros default (sem Optuna, sem early stopping)
sobre v3.parquet (35 features, encoding limpo, Familia 1 com 5 janelas alinhadas
aos targets), respondendo simultaneamente:

  (1) MITIGACAO 2: A (scale_pos_weight=taxa_treino, sem peeking) vs
                    B (scale_pos_weight=taxa val+test, com peeking branda)
      -> a diferenca B-A da medida implicita do vies do peeking. Esperado:
         1-3pp em favor de B se peeking importar.

  (2) OBS 2.7:    A (target_4h padrao) vs
                    C (target_4h_producao = exclui DGs em estado Manutencao)
      -> testa se filtrar 2.525 DGs em Manutencao melhora performance.

  (3) PROFUNDIDADE 1: T2 (target_2h) vs T4 (=A, target_4h) vs T8 (target_8h)
      -> compara 3 horizontes com hiperparametros identicos e features
         perfeitamente alinhadas (count_critico_2h/4h/8h adicionadas em W5).

  (4) GATE MARCO 1 (re-calibrado em 22/05): A deve atingir
      AUC-PR >= 0.2897 em val (mai) E AUC-PR >= 0.6303 em test (jun).
      Decisao de avancar para W6 ou aplicar Mitigacao 1 antes do Optuna.

DECISAO METODOLOGICA REGISTRADA (notas_metodologicas.md Secao 3):
  A Variante B usa `scale_pos_weight` calculado sobre union val+test —
  forma BRANDA de test set peeking. Vies esperado 1-3pp em favor de B.
  Sera corrigido em v2 (W6) com Optuna + TimeSeriesSplit CV (Mitigacao 1).
  Em W7 a comparacao v1A vs v1B vs v2 dara a magnitude empirica do vies.

Entradas:
  - Projeto/dados/features/v3.parquet (544.885 x 58, pos-fix de encoding)
  - Projeto/relatorio/tabelas/baseline_metricas.csv (referencia para GATE)

Saidas:
  - Projeto/modelos/lightgbm_v1_{A,B,C,T2,T8}.lgb (5 modelos salvos)
  - Projeto/relatorio/tabelas/lightgbm_v1_metricas.csv (10 linhas: 5 var x 2 splits)
  - Projeto/relatorio/tabelas/lightgbm_v1_vs_baseline.csv (comparacao A/B/C)
  - Projeto/relatorio/tabelas/comparacao_horizontes_lightgbm.csv (T2/T4/T8)
  - Projeto/relatorio/tabelas/gate_marco_1.csv (verdict + criterios)

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/08_lightgbm.py
"""
from pathlib import Path
import time
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
)

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")


# ===========================================================================
# Caminhos
# ===========================================================================
ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_BASELINE = ROOT / "relatorio" / "tabelas" / "baseline_metricas.csv"
DIR_MODELOS = ROOT / "modelos"
ARQ_METRICAS = ROOT / "relatorio" / "tabelas" / "lightgbm_v1_metricas.csv"
ARQ_VS_BASELINE = ROOT / "relatorio" / "tabelas" / "lightgbm_v1_vs_baseline.csv"
ARQ_HORIZONTES = ROOT / "relatorio" / "tabelas" / "comparacao_horizontes_lightgbm.csv"
ARQ_GATE = ROOT / "relatorio" / "tabelas" / "gate_marco_1.csv"


# ===========================================================================
# Constantes
# ===========================================================================
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
N_TRAIN = 394_971
N_VAL = 78_825
N_TEST = 71_089

# GATE MARCO 1 re-calibrado em 22/05 (controle_alteracoes.md 2026-05-22)
GATE_VAL_MIN = 0.2897   # baseline val 0,2397 + 5pp
GATE_TEST_MIN = 0.6303  # baseline test 0,5803 + 5pp

SEED = 42

# 35 features (ordem fixa para reproducibilidade)
FEATURES = [
    # Familia 0 (basicas, W3) - 5
    "hora_dia", "dia_semana", "turno", "mes", "valor_disponivel",
    # Familia 1 (rolling, W4 + W5) - 15
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    # Familia 2 (recencia, W4) - 2
    "horas_desde_ultimo_DG", "horas_desde_ultimo_critico",
    # Familia 3 (estado pre-evento, W4) - 1
    "estado_pre_evento",
    # Familia 4 (regimal, W4) - 2
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    # Familia 5 (operador, W4) - 2
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    # Familia 6 (regra de negocio, W4) - 1
    "qtd_alarmes_nivel_muito_alto_360min",
    # Familia 7 (encoding, W4 + fix W5) - 7
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
]
N_FEATURES = len(FEATURES)
CAT_FEATURES = ["turno", "estado_pre_evento"]

# Hiperparametros LightGBM v1 (default + customizacao minima)
LGBM_PARAMS_BASE = {
    "objective": "binary",
    "n_estimators": 100,
    "learning_rate": 0.1,
    "num_leaves": 31,
    "max_depth": -1,
    "min_child_samples": 20,
    "random_state": SEED,
    "verbose": -1,
    "n_jobs": -1,
}


# ===========================================================================
# Etapa 1 - Carregar v3.parquet
# ===========================================================================
def carregar() -> pl.DataFrame:
    print("Etapa 1/6 - Carregando v3.parquet...")
    if not ARQ_V3.exists():
        raise FileNotFoundError(
            f"v3.parquet nao encontrado em {ARQ_V3}. "
            "Execute 06b_fix_encoding_leakage.py antes."
        )

    df = pl.read_parquet(ARQ_V3)
    print(f"  Shape: {df.shape}")
    assert df.height == LINHAS_ESPERADAS

    # Validar contagens por split
    for split, n_esperado in [("train", N_TRAIN), ("val", N_VAL), ("test", N_TEST)]:
        n = df.filter(pl.col("split") == split).height
        assert n == n_esperado, f"{split}: {n} != {n_esperado}"
    print(f"  Splits OK: train={N_TRAIN:,} / val={N_VAL:,} / test={N_TEST:,}")

    # Validar features presentes
    faltantes = [f for f in FEATURES if f not in df.columns]
    assert not faltantes, f"Features ausentes em v3.parquet: {faltantes}"
    print(f"  {N_FEATURES} features encontradas em v3.parquet")

    return df


# ===========================================================================
# Etapa 2 - Construir target_4h_producao (Variante C)
# ===========================================================================
def construir_target_producao(df: pl.DataFrame) -> pl.DataFrame:
    """
    Variante C (Obs 2.7) — exclui DGs ocorridos em estado Manutencao.

    Aplica o mesmo padrao reverse->shift(1)->forward_fill->reverse do
    05_features.py etapa 11, mas filtrando Is_Dont_Go=1 a apenas DGs com
    estado_pre_evento != 'Manutencao'. Eventos em Manutencao deixam de
    contar como "proximo DG" para fins desse target alternativo.
    """
    print()
    print("Etapa 2/6 - Construindo target_4h_producao (Variante C)...")
    df = df.sort(["TAG", "Data_Evento"])

    # Marca apenas DGs que NAO sao em Manutencao
    df = df.with_columns(
        pl.when(
            (pl.col("Is_Dont_Go") == 1)
            & (pl.col("estado_pre_evento") != "Manutenção")
        )
        .then(pl.col("Data_Evento"))
        .otherwise(None)
        .alias("_dg_prod_ts")
    )

    # Proximo DG_prod estritamente posterior (mesma rotina do target_4h)
    df = df.with_columns(
        pl.col("_dg_prod_ts")
        .reverse()
        .shift(1)
        .forward_fill()
        .reverse()
        .over("TAG")
        .alias("_proximo_dg_prod_ts")
    )

    df = df.with_columns(
        (
            (pl.col("_proximo_dg_prod_ts") - pl.col("Data_Evento")).dt.total_seconds() / 3600.0
        ).alias("_horas_ate_dg_prod")
    )

    df = df.with_columns(
        (
            (pl.col("_horas_ate_dg_prod") > 0) & (pl.col("_horas_ate_dg_prod") <= 4.0)
        )
        .fill_null(False)
        .cast(pl.Int8)
        .alias("target_4h_producao")
    )

    df = df.drop("_dg_prod_ts", "_proximo_dg_prod_ts", "_horas_ate_dg_prod")

    # Diagnostico
    n_pos_orig = df.filter(pl.col("target_4h") == 1).height
    n_pos_prod = df.filter(pl.col("target_4h_producao") == 1).height
    n_excluidos = df.filter(
        (pl.col("Is_Dont_Go") == 1) & (pl.col("estado_pre_evento") == "Manutenção")
    ).height
    print(f"  DGs originais em Manutencao excluidos: {n_excluidos:,}")
    print(f"  target_4h positivos:           {n_pos_orig:,} ({n_pos_orig/LINHAS_ESPERADAS*100:.2f}%)")
    print(f"  target_4h_producao positivos:  {n_pos_prod:,} ({n_pos_prod/LINHAS_ESPERADAS*100:.2f}%)")

    return df


# ===========================================================================
# Etapa 3 - Calcular scale_pos_weight para cada variante
# ===========================================================================
def calcular_spw(df: pl.DataFrame) -> dict:
    print()
    print("Etapa 3/6 - Calculando scale_pos_weight por variante...")

    def _spw_from_target(df: pl.DataFrame, target: str, splits: list[str]) -> float:
        sub = df.filter(pl.col("split").is_in(splits))[target].to_numpy()
        n_neg = (sub == 0).sum()
        n_pos = (sub == 1).sum()
        return float(n_neg / n_pos) if n_pos > 0 else 1.0

    spw = {
        # Variante A: scale_pos_weight calibrado para TREINO (sem peeking)
        "A": _spw_from_target(df, "target_4h", ["train"]),
        # Variante B: scale_pos_weight calibrado para VAL+TEST (peeking branda — Mitigacao 2)
        "B": _spw_from_target(df, "target_4h", ["val", "test"]),
        # Variante C: scale_pos_weight calibrado para TREINO no target alternativo
        "C": _spw_from_target(df, "target_4h_producao", ["train"]),
        # Variantes T2/T8: scale_pos_weight calibrado para TREINO em cada horizonte
        "T2": _spw_from_target(df, "target_2h", ["train"]),
        "T8": _spw_from_target(df, "target_8h", ["train"]),
    }

    print(f"  Variante A  (target_4h,           treino):       spw = {spw['A']:.3f}")
    print(f"  Variante B  (target_4h,           val+test PEEK): spw = {spw['B']:.3f}")
    print(f"  Variante C  (target_4h_producao,  treino):       spw = {spw['C']:.3f}")
    print(f"  Variante T2 (target_2h,           treino):       spw = {spw['T2']:.3f}")
    print(f"  Variante T8 (target_8h,           treino):       spw = {spw['T8']:.3f}")

    return spw


# ===========================================================================
# Helper - Preparar X, y para um split + target
# ===========================================================================
def preparar_X_y(
    df: pl.DataFrame, split: str, target: str
) -> tuple[pd.DataFrame, np.ndarray]:
    sub = df.filter(pl.col("split") == split).select(FEATURES + [target])
    pdf = sub.to_pandas()
    y = pdf[target].to_numpy().astype(np.int8)
    X = pdf[FEATURES].copy()
    # Converter categoricals para pd.Categorical (LightGBM trata nativamente)
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    # valor_disponivel (bool) -> int para LightGBM
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    return X, y


# ===========================================================================
# Helper - Treinar 1 modelo + avaliar em val e test
# ===========================================================================
def treinar_e_avaliar(
    nome: str,
    target: str,
    spw: float,
    df: pl.DataFrame,
) -> tuple[lgb.LGBMClassifier, dict]:
    t0 = time.time()

    X_train, y_train = preparar_X_y(df, "train", target)
    X_val, y_val = preparar_X_y(df, "val", target)
    X_test, y_test = preparar_X_y(df, "test", target)

    modelo = lgb.LGBMClassifier(scale_pos_weight=spw, **LGBM_PARAMS_BASE)
    modelo.fit(
        X_train, y_train,
        categorical_feature=CAT_FEATURES,
    )

    elapsed = time.time() - t0

    def _metricas_split(X, y) -> dict:
        proba = modelo.predict_proba(X)[:, 1]
        pred = (proba >= 0.5).astype(np.int8)
        return {
            "n_eventos": len(y),
            "n_positivos": int(y.sum()),
            "auc_pr": float(average_precision_score(y, proba)),
            "precision_05": float(precision_score(y, pred, zero_division=0)),
            "recall_05": float(recall_score(y, pred, zero_division=0)),
            "f1_05": float(f1_score(y, pred, zero_division=0)),
        }

    m_val = _metricas_split(X_val, y_val)
    m_test = _metricas_split(X_test, y_test)

    print(f"  [{nome:>2s}] target={target:<20s} spw={spw:5.3f}  "
          f"val AUC-PR={m_val['auc_pr']:.4f}  test AUC-PR={m_test['auc_pr']:.4f}  "
          f"({elapsed:.1f}s)")

    return modelo, {
        "val": m_val, "test": m_test, "tempo_treino_s": elapsed,
        "target": target, "spw": spw,
    }


# ===========================================================================
# Etapa 4 - Treinar 5 variantes
# ===========================================================================
def treinar_variantes(df: pl.DataFrame, spw: dict) -> dict:
    print()
    print("Etapa 4/6 - Treinando 5 variantes (default params, 100 iter)...")
    print(f"  Features: {N_FEATURES} | Categoricals: {CAT_FEATURES}")
    print()

    DIR_MODELOS.mkdir(parents=True, exist_ok=True)

    config = [
        ("A",  "target_4h",         spw["A"]),
        ("B",  "target_4h",         spw["B"]),   # PEEKING
        ("C",  "target_4h_producao", spw["C"]),
        ("T2", "target_2h",         spw["T2"]),
        ("T8", "target_8h",         spw["T8"]),
    ]

    resultados = {}
    for nome, target, spw_val in config:
        modelo, m = treinar_e_avaliar(nome, target, spw_val, df)
        # Salvar modelo (formato txt nativo do LightGBM)
        path = DIR_MODELOS / f"lightgbm_v1_{nome}.txt"
        modelo.booster_.save_model(str(path))
        resultados[nome] = m

    return resultados


# ===========================================================================
# Etapa 5 - Tabelas comparativas
# ===========================================================================
def gerar_tabelas(resultados: dict) -> None:
    print()
    print("Etapa 5/6 - Gerando tabelas comparativas...")

    # ---- Tabela 1: metricas wide (5 variantes x 2 splits = 10 linhas) ----
    linhas = []
    for nome, m in resultados.items():
        for split in ["val", "test"]:
            ms = m[split]
            linhas.append({
                "variante": nome,
                "target": m["target"],
                "scale_pos_weight": round(m["spw"], 4),
                "split": split,
                "n_eventos": ms["n_eventos"],
                "n_positivos": ms["n_positivos"],
                "auc_pr": round(ms["auc_pr"], 4),
                "precision_05": round(ms["precision_05"], 4),
                "recall_05": round(ms["recall_05"], 4),
                "f1_05": round(ms["f1_05"], 4),
                "tempo_treino_s": round(m["tempo_treino_s"], 1),
            })
    metricas = pl.from_dicts(linhas)
    metricas.write_csv(ARQ_METRICAS)
    print(f"  {ARQ_METRICAS.relative_to(ROOT.parent)} ({metricas.height} linhas)")

    # ---- Tabela 2: vs baseline (apenas variantes em target_4h: A, B, C usa target_producao) ----
    # Para variantes em target_4h (A, B): comparar com baseline_metricas.csv
    # C usa target diferente, entao comparacao com baseline so faz sentido conceitualmente
    if ARQ_BASELINE.exists():
        baseline = pl.read_csv(ARQ_BASELINE)
        # baseline tem 4 thresholds por split — pegamos o auc_pr (mesma em todas as linhas do mesmo split)
        baseline_auc_val = baseline.filter(pl.col("split") == "val")["auc_pr"][0]
        baseline_auc_test = baseline.filter(pl.col("split") == "test")["auc_pr"][0]

        linhas_vs = []
        for nome in ["A", "B", "C"]:
            for split, base_auc in [("val", baseline_auc_val), ("test", baseline_auc_test)]:
                lgbm_auc = resultados[nome][split]["auc_pr"]
                diff = lgbm_auc - base_auc
                linhas_vs.append({
                    "variante": nome,
                    "target": resultados[nome]["target"],
                    "split": split,
                    "auc_pr_baseline": round(base_auc, 4),
                    "auc_pr_lightgbm": round(lgbm_auc, 4),
                    "diff_pp": round(diff * 100, 2),
                    "bate_baseline_5pp": diff >= 0.05,
                })
        vs_baseline = pl.from_dicts(linhas_vs)
        vs_baseline.write_csv(ARQ_VS_BASELINE)
        print(f"  {ARQ_VS_BASELINE.relative_to(ROOT.parent)} ({vs_baseline.height} linhas)")
    else:
        print(f"  AVISO: baseline_metricas.csv nao encontrado — pulando comparacao vs baseline")

    # ---- Tabela 3: Profundidade 1 (T2 vs T4=A vs T8) ----
    linhas_h = []
    for nome_horizonte, target_real in [("T2", "target_2h"), ("T4", "target_4h"), ("T8", "target_8h")]:
        nome_variante = "A" if nome_horizonte == "T4" else nome_horizonte
        for split in ["val", "test"]:
            ms = resultados[nome_variante][split]
            linhas_h.append({
                "horizonte": nome_horizonte,
                "target": target_real,
                "variante_usada": nome_variante,
                "split": split,
                "n_positivos": ms["n_positivos"],
                "auc_pr": round(ms["auc_pr"], 4),
                "precision_05": round(ms["precision_05"], 4),
                "recall_05": round(ms["recall_05"], 4),
                "f1_05": round(ms["f1_05"], 4),
            })
    horizontes = pl.from_dicts(linhas_h)
    horizontes.write_csv(ARQ_HORIZONTES)
    print(f"  {ARQ_HORIZONTES.relative_to(ROOT.parent)} ({horizontes.height} linhas)")


# ===========================================================================
# Etapa 6 - GATE MARCO 1
# ===========================================================================
def gate_marco_1(resultados: dict) -> dict:
    print()
    print("=" * 70)
    print("GATE MARCO 1 - Decisao de avanco para W6")
    print("=" * 70)

    auc_val_A = resultados["A"]["val"]["auc_pr"]
    auc_test_A = resultados["A"]["test"]["auc_pr"]

    crit_A = auc_val_A >= GATE_VAL_MIN
    crit_B = auc_test_A >= GATE_TEST_MIN

    print(f"  Variante A (canonica):")
    print(f"    val (mai):  AUC-PR = {auc_val_A:.4f}  (criterio A: >= {GATE_VAL_MIN}) "
          f"-> {'PASS' if crit_A else 'FAIL'}")
    print(f"    test (jun): AUC-PR = {auc_test_A:.4f}  (criterio B: >= {GATE_TEST_MIN}) "
          f"-> {'PASS' if crit_B else 'FAIL'}")

    if crit_A and crit_B:
        verdict = "PASS"
        acao = "Avancar para W6 (tuning + sobrevivencia + Isolation Forest + SHAP)"
    elif crit_A and not crit_B:
        verdict = "PARTIAL_A"
        acao = "Aplicar Mitigacao 1 (TimeSeriesSplit CV) ANTES do Optuna em W6"
    elif not crit_A:
        verdict = "FAIL_A"
        acao = "Revisar features/encoding antes de tunar — drift nao e a causa"

    print()
    print(f"  VERDICT: {verdict}")
    print(f"  ACAO:    {acao}")
    print("=" * 70)

    # Salvar
    gate_df = pl.from_dicts([{
        "criterio": "A_val_min",
        "valor_minimo": GATE_VAL_MIN,
        "valor_obtido": round(auc_val_A, 4),
        "resultado": "PASS" if crit_A else "FAIL",
    }, {
        "criterio": "B_test_min",
        "valor_minimo": GATE_TEST_MIN,
        "valor_obtido": round(auc_test_A, 4),
        "resultado": "PASS" if crit_B else "FAIL",
    }, {
        "criterio": "verdict_geral",
        "valor_minimo": "PASS",
        "valor_obtido": verdict,
        "resultado": acao,
    }])
    gate_df.write_csv(ARQ_GATE)
    print(f"  Saida: {ARQ_GATE.relative_to(ROOT.parent)}")

    return {"verdict": verdict, "acao": acao, "crit_A": crit_A, "crit_B": crit_B}


# ===========================================================================
# Sumario adicional - Mitigacao 2 + Obs 2.7 + Profundidade 1
# ===========================================================================
def sumario_analitico(resultados: dict) -> None:
    print()
    print("=" * 70)
    print("ANALISES ADICIONAIS")
    print("=" * 70)

    # ---- Mitigacao 2: A vs B ----
    print()
    print("Mitigacao 2 — A (sem peeking) vs B (peeking branda val+test):")
    for split in ["val", "test"]:
        a = resultados["A"][split]["auc_pr"]
        b = resultados["B"][split]["auc_pr"]
        diff_pp = (b - a) * 100
        print(f"  {split:>4s}: A={a:.4f}  B={b:.4f}  B-A={diff_pp:+.2f}pp")
    print("  Interpretacao (notas_metodologicas.md Secao 3):")
    print("    B-A > +5pp em test  -> ganho real ~2-4pp (resto e vies do peeking)")
    print("    B-A ~ +1-2pp em test -> marginal, provavelmente so vies")
    print("    B-A <= 0 em test    -> Mitigacao 2 descartada (vies insuficiente)")

    # ---- Obs 2.7: A vs C ----
    print()
    print("Obs 2.7 — A (target_4h padrao) vs C (target_4h_producao, sem DGs em Manutencao):")
    for split in ["val", "test"]:
        a = resultados["A"][split]["auc_pr"]
        c = resultados["C"][split]["auc_pr"]
        diff_pp = (c - a) * 100
        print(f"  {split:>4s}: A={a:.4f}  C={c:.4f}  C-A={diff_pp:+.2f}pp")
    print("  Interpretacao:")
    print("    C-A > +5pp -> contexto Manutencao introduzia ruido treinavel")
    print("    C-A < 5pp  -> nao vale a complexidade adicional")

    # ---- Profundidade 1: T2 vs T4 vs T8 ----
    print()
    print("Profundidade 1 — comparacao entre horizontes (test):")
    for nome, var in [("T2", "T2"), ("T4 (=A)", "A"), ("T8", "T8")]:
        auc = resultados[var]["test"]["auc_pr"]
        print(f"  {nome:>10s}: AUC-PR = {auc:.4f}")
    winner = max(
        [("T2", resultados["T2"]["test"]["auc_pr"]),
         ("T4", resultados["A"]["test"]["auc_pr"]),
         ("T8", resultados["T8"]["test"]["auc_pr"])],
        key=lambda x: x[1],
    )
    print(f"  Vencedor (test AUC-PR): {winner[0]} ({winner[1]:.4f})")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("08_lightgbm.py - LightGBM v1 (5 variantes + GATE MARCO 1)")
    print("=" * 70)

    df = carregar()
    df = construir_target_producao(df)
    spw = calcular_spw(df)
    resultados = treinar_variantes(df, spw)
    gerar_tabelas(resultados)
    gate = gate_marco_1(resultados)
    sumario_analitico(resultados)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s")
    print(f"5 modelos salvos em {DIR_MODELOS.relative_to(ROOT.parent)}/")
    print(f"4 tabelas em relatorio/tabelas/")
    print("=" * 70)


if __name__ == "__main__":
    main()
