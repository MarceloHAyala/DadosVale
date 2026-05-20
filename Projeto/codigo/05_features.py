"""
05_features.py - Feature engineering (W3 basicas + W4 avancadas).

Estrutura em 4 famílias de features sobre o dataset filtrado de
telemetria + apontamentos:

W3 (5 features basicas):
  - hora_dia, dia_semana, turno, mes (temporais)
  - valor_disponivel (Valor IS NOT NULL)

W4 (14 features avancadas — 4 familias):
  Familia 1 — Rolling windows (9): count_{critico/nao_critico/total}_{1h,4h,24h}
  Familia 2 — Recencia (2): horas_desde_ultimo_DG, horas_desde_ultimo_critico
  Familia 3 — Estado pre-evento (1): estado_pre_evento via join_asof t-1h
  Familia 4 — Regimal (2): razao_alarme_7d_vs_30d_anterior (top 19),
                            razao_severidade_14d_vs_60d (por TAG)

Decisoes metodologicas (registradas em PLANEJAMENTO.md / controle_alteracoes.md):
  - Leakage prevention: rolling_sum_by com closed="left" (exclui evento atual)
  - Recencia sem precedente: NULL (LightGBM aceita NaN)
  - Regimal sobre 19 alarmes (alinhado com rascunho.md e hipoteses_eda.md H2.1)
  - Estado_pre_evento sem match: "SEM_APONTAMENTO" (consistencia W2 Q4)

Para proxima sessao (W4 cont): operador (taxa_DG_30d), regra de negocio
(qtd_alarmes_muito_alto_360min), n_bypasses_operador_7d (H1.2), encoding
categorico (5 categorias), Fig Extra C (CA65924), target 4h, sensibilidade.

Entradas:
  - Projeto/dados/intermediarios/telemetria_limpa.parquet (~545k linhas)
  - Projeto/dados/intermediarios/apontamentos_limpo.parquet (~377k linhas)

Saidas:
  - Projeto/dados/features/v1.parquet            (5 features basicas — W3)
  - Projeto/dados/features/v2_parcial.parquet    (5 + 14 = 19 features — W4 parcial)
  - Projeto/relatorio/tabelas/documentacao_features.csv (CM 3.2, 19 entradas)

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/05_features.py
"""
from pathlib import Path
import time

import polars as pl


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ARQ_TELEMETRIA_IN = ROOT / "dados" / "intermediarios" / "telemetria_limpa.parquet"
ARQ_APONTAMENTOS_IN = ROOT / "dados" / "intermediarios" / "apontamentos_limpo.parquet"
DIR_FEATURES = ROOT / "dados" / "features"
ARQ_V1 = DIR_FEATURES / "v1.parquet"
ARQ_V2_PARCIAL = DIR_FEATURES / "v2_parcial.parquet"
ARQ_DOC_FEATURES = ROOT / "relatorio" / "tabelas" / "documentacao_features.csv"

# ---------------------------------------------------------------------------
# Expectativas
# ---------------------------------------------------------------------------
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
VALOR_NULLS_ESPERADOS = 237_443
N_FEATURES_BASICAS = 5
N_FEATURES_AVANCADAS = 14
N_FEATURES_TOTAL = N_FEATURES_BASICAS + N_FEATURES_AVANCADAS  # = 19

# Top N alarmes para regimal (alinhado com rascunho.md / hipoteses_eda.md H2.1)
# 19 alarmes que geraram >= 1 DG no semestre — descobertos dinamicamente
N_TOP_ALARMES_ESPERADO = 19


# ---------------------------------------------------------------------------
# Definicao de features (uma entrada por feature, CM 3.2)
# ---------------------------------------------------------------------------
FEATURES_BASICAS_W3 = [
    {
        "nome": "hora_dia",
        "tipo": "Int8",
        "descricao": "Hora do dia em que o evento ocorreu (0-23)",
        "formula": "Data_Evento.dt.hour()",
        "motivacao": (
            "Q5 (W2): heatmap hora x dia revelou pico extremo de DGs em segunda "
            "as 23h; variacao de aproximadamente 3x entre hora minima e maxima."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "dia_semana",
        "tipo": "Int8",
        "descricao": "Dia da semana do evento (1=Seg ... 7=Dom)",
        "formula": "Data_Evento.dt.weekday()",
        "motivacao": (
            "Q5 (W2): segunda-feira concentra as maiores taxas de DG; "
            "padrao de 'rampa de retomada apos fim de semana'."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "turno",
        "tipo": "String",
        "descricao": "Turno operacional: 'Diurno' (Inicio_Turno=6h) ou 'Noturno' (Inicio_Turno=18h)",
        "formula": "'Diurno' if Inicio_Turno.dt.hour() == 6 else 'Noturno'",
        "motivacao": (
            "Operacao 24x7 em turnos de 12h. Fig 2 mostra picos em 4-5h e "
            "17-18h consistentes com transicoes de turno."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "mes",
        "tipo": "Int8",
        "descricao": "Mes do evento (1=jan ... 6=jun de 2025)",
        "formula": "Data_Evento.dt.month()",
        "motivacao": (
            "Obs 2.6: 3 regimes temporais distintos. Anomalia A (Engine Coolant "
            "fev-mar) e Anomalia B (Right Front Brake jun); captura non-stationarity."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "valor_disponivel",
        "tipo": "Bool",
        "descricao": "True se o evento possui medicao numerica (Valor IS NOT NULL)",
        "formula": "Valor.is_not_null()",
        "motivacao": (
            "Achado W3: 43.58% dos eventos relevantes nao possuem Valor numerico — "
            "alarmes 'Active/Inactive' sem medicao. Categoria binaria preditiva."
        ),
        "semana_criada": "W3",
    },
]

FEATURES_AVANCADAS_W4 = []
# Familia 1 — Rolling windows (9)
for criticidade in ["critico", "nao_critico", "total"]:
    for window in ["1h", "4h", "24h"]:
        FEATURES_AVANCADAS_W4.append({
            "nome": f"count_{criticidade}_{window}",
            "tipo": "Int32",
            "descricao": (
                f"Contagem de eventos {criticidade.replace('_', ' ').title()} "
                f"do mesmo TAG nas ultimas {window} (closed=left, exclui evento atual)"
            ),
            "formula": (
                f"rolling_sum_by(by=Data_Evento, window={window}, closed='left').over(TAG)"
            ),
            "motivacao": (
                "Obs 2.5: 48% dos DGs vem de acumulacao (regra CMA QTD>1). "
                "Rolling captura padrao temporal de acumulacao — family core. "
                "count_total valida empiricamente H5.2 / Obs 2.3 (padrao CA65924)."
            ),
            "semana_criada": "W4",
        })

# Familia 2 — Recencia (2)
FEATURES_AVANCADAS_W4.extend([
    {
        "nome": "horas_desde_ultimo_DG",
        "tipo": "Float64",
        "descricao": "Horas desde o ultimo DG do mesmo TAG (NULL se nao houve DG anterior)",
        "formula": "(Data_Evento - last_DG_timestamp).total_hours() per TAG",
        "motivacao": (
            "Padrao classico de manutencao preditiva: tempo desde ultima falha "
            "correlaciona com risco. NULL para eventos antes do primeiro DG da TAG."
        ),
        "semana_criada": "W4",
    },
    {
        "nome": "horas_desde_ultimo_critico",
        "tipo": "Float64",
        "descricao": "Horas desde o ultimo evento Critico do mesmo TAG (NULL se nao houve)",
        "formula": "(Data_Evento - last_Critico_timestamp).total_hours() per TAG",
        "motivacao": (
            "Critico tem taxa de DG 12,39% (Obs 2.2). Recencia de Critico captura "
            "'risco crescente' mesmo antes de virar DG."
        ),
        "semana_criada": "W4",
    },
])

# Familia 3 — Estado pre-evento (1)
FEATURES_AVANCADAS_W4.append({
    "nome": "estado_pre_evento",
    "tipo": "String",
    "descricao": (
        "Estado operacional do equipamento ~1h antes do evento "
        "(Operando/Parado/Manutencao/Hibernando ou SEM_APONTAMENTO)"
    ),
    "formula": (
        "join_asof(apontamentos.Inicio <= Data_Evento - 1h, by=TAG, "
        "strategy=backward, filtro Fim >= Data_Evento - 1h)"
    ),
    "motivacao": (
        "Obs 2.7: 12,65% dos DGs em estado Manutencao sao legitimos (reativacoes "
        "de teste). Capturar o estado pre-evento separa 'DG operacional' de "
        "'DG em teste de manutencao' — base para analise estratificada W7."
    ),
    "semana_criada": "W4",
})

# Familia 4 — Regimal (2)
FEATURES_AVANCADAS_W4.extend([
    {
        "nome": "razao_alarme_7d_vs_30d_anterior",
        "tipo": "Float64",
        "descricao": (
            "Razao normalizada por dias entre frequencia do mesmo alarme em (TAG, Alarme) "
            "nos ultimos 7d vs baseline historico de 30d. NULL se Alarme nao esta nos top 19."
        ),
        "formula": (
            "(count_7d/7) / (count_30d/30) per (TAG, Alarme); restrito a top 19 alarmes "
            "que geraram >=1 DG no semestre"
        ),
        "motivacao": (
            "Obs 2.6 extensao: alarme Right Front Brake Temperature explodiu 151,7x "
            "em junho (estatisticamente invisivel no treino jan-mai). Razao vs proprio "
            "baseline captura essas explosoes — endereca risco 3.2 (drift)."
        ),
        "semana_criada": "W4",
    },
    {
        "nome": "razao_severidade_14d_vs_60d",
        "tipo": "Float64",
        "descricao": (
            "Razao (count_Critico_14d/count_NaoCritico_14d) / (count_Critico_60d/count_NaoCritico_60d) "
            "per TAG. Captura inversoes de severidade. NULL quando denominadores=0."
        ),
        "formula": (
            "(crit_14d * nc_60d) / (nc_14d * crit_60d) per TAG, rolling closed=left"
        ),
        "motivacao": (
            "Obs 2.6: Engine Coolant Level inverteu severidade (83% Critico → 6% em fev-mar). "
            "Razao mix Critico/Nao-Critico em janela curta vs longa detecta inversoes."
        ),
        "semana_criada": "W4",
    },
])

FEATURES_DEFINIDAS = FEATURES_BASICAS_W3 + FEATURES_AVANCADAS_W4


# ---------------------------------------------------------------------------
# [1/9] Carga
# ---------------------------------------------------------------------------
def carregar() -> tuple[pl.DataFrame, pl.DataFrame]:
    print(f"[1/9] Carregando datasets")
    for arq in [ARQ_TELEMETRIA_IN, ARQ_APONTAMENTOS_IN]:
        if not arq.exists():
            raise FileNotFoundError(
                f"{arq} nao encontrado. Rode 03_limpeza.py primeiro."
            )
    t0 = time.time()
    telemetria = pl.read_parquet(ARQ_TELEMETRIA_IN)
    apontamentos = pl.read_parquet(ARQ_APONTAMENTOS_IN)
    print(
        f"  Telemetria   : {telemetria.shape[0]:>10,} linhas x {telemetria.shape[1]:>2}\n"
        f"  Apontamentos : {apontamentos.shape[0]:>10,} linhas x {apontamentos.shape[1]:>2}"
        f"  ({time.time()-t0:.1f}s)"
    )
    assert telemetria.shape[0] == LINHAS_ESPERADAS
    return telemetria, apontamentos


# ---------------------------------------------------------------------------
# [2/9] Features temporais (W3 — basicas)
# ---------------------------------------------------------------------------
def criar_features_temporais(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[2/9] Features temporais (W3 — 4 features)")
    horas_inicio = (
        df.select(pl.col("Inicio_Turno").dt.hour().alias("h"))
        ["h"].unique().sort().to_list()
    )
    assert set(horas_inicio).issubset({6, 18}), (
        f"Inicio_Turno tem horas inesperadas: {horas_inicio}"
    )
    df = df.with_columns([
        pl.col("Data_Evento").dt.hour().cast(pl.Int8).alias("hora_dia"),
        pl.col("Data_Evento").dt.weekday().cast(pl.Int8).alias("dia_semana"),
        pl.col("Data_Evento").dt.month().cast(pl.Int8).alias("mes"),
        (pl.when(pl.col("Inicio_Turno").dt.hour() == 6)
            .then(pl.lit("Diurno"))
            .otherwise(pl.lit("Noturno"))
            .alias("turno")),
    ])
    print("  OK hora_dia, dia_semana, turno, mes")
    return df


# ---------------------------------------------------------------------------
# [3/9] valor_disponivel (W3)
# ---------------------------------------------------------------------------
def criar_feature_valor_disponivel(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[3/9] Feature valor_disponivel (W3)")
    df = df.with_columns(
        pl.col("Valor").is_not_null().alias("valor_disponivel")
    )
    n_true = df.filter(pl.col("valor_disponivel")).height
    print(f"  True: {n_true:,} | False: {df.height-n_true:,} "
          f"({100*(df.height-n_true)/df.height:.2f}%)")
    return df


# ---------------------------------------------------------------------------
# [4/9] Familia 1 — Rolling windows (W4, 9 features)
# ---------------------------------------------------------------------------
def criar_features_rolling(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[4/9] Familia 1 — Rolling windows (9 features)")
    t0 = time.time()

    df = df.sort(["TAG", "Data_Evento"])
    df = df.with_columns([
        (pl.col("Criticidade") == "Critico").cast(pl.Int32).alias("_is_critico"),
        (pl.col("Criticidade") == "Nao_Critico").cast(pl.Int32).alias("_is_nao_critico"),
        pl.lit(1).cast(pl.Int32).alias("_is_total"),
    ])

    for window in ["1h", "4h", "24h"]:
        df = df.with_columns([
            pl.col("_is_critico").rolling_sum_by(
                by="Data_Evento", window_size=window, closed="left"
            ).over("TAG").fill_null(0).cast(pl.Int32)
              .alias(f"count_critico_{window}"),
            pl.col("_is_nao_critico").rolling_sum_by(
                by="Data_Evento", window_size=window, closed="left"
            ).over("TAG").fill_null(0).cast(pl.Int32)
              .alias(f"count_nao_critico_{window}"),
            pl.col("_is_total").rolling_sum_by(
                by="Data_Evento", window_size=window, closed="left"
            ).over("TAG").fill_null(0).cast(pl.Int32)
              .alias(f"count_total_{window}"),
        ])
        print(f"  janela {window}: OK")

    df = df.drop("_is_critico", "_is_nao_critico", "_is_total")
    print(f"  9 features rolling criadas ({time.time()-t0:.1f}s)")
    return df


# ---------------------------------------------------------------------------
# [5/9] Familia 2 — Recencia (W4, 2 features)
# ---------------------------------------------------------------------------
def criar_features_recencia(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[5/9] Familia 2 — Recencia (2 features)")
    t0 = time.time()

    df = df.sort(["TAG", "Data_Evento"])
    df = df.with_columns([
        pl.when(pl.col("Is_Dont_Go") == 1)
          .then(pl.col("Data_Evento"))
          .otherwise(None)
          .alias("_dg_ts"),
        pl.when(pl.col("Criticidade") == "Critico")
          .then(pl.col("Data_Evento"))
          .otherwise(None)
          .alias("_crit_ts"),
    ])

    # shift(1) + forward_fill por TAG: pega o ultimo timestamp ANTES do evento atual
    df = df.with_columns([
        pl.col("_dg_ts").shift(1).forward_fill().over("TAG").alias("_last_dg"),
        pl.col("_crit_ts").shift(1).forward_fill().over("TAG").alias("_last_crit"),
    ])

    df = df.with_columns([
        ((pl.col("Data_Evento") - pl.col("_last_dg")).dt.total_seconds() / 3600.0)
            .alias("horas_desde_ultimo_DG"),
        ((pl.col("Data_Evento") - pl.col("_last_crit")).dt.total_seconds() / 3600.0)
            .alias("horas_desde_ultimo_critico"),
    ])

    df = df.drop("_dg_ts", "_crit_ts", "_last_dg", "_last_crit")

    n_null_dg = df.get_column("horas_desde_ultimo_DG").null_count()
    n_null_crit = df.get_column("horas_desde_ultimo_critico").null_count()
    print(f"  horas_desde_ultimo_DG: {n_null_dg:,} NULLs "
          f"(eventos antes do 1o DG do TAG)")
    print(f"  horas_desde_ultimo_critico: {n_null_crit:,} NULLs")
    print(f"  2 features recencia criadas ({time.time()-t0:.1f}s)")
    return df


# ---------------------------------------------------------------------------
# [6/9] Familia 3 — Estado pre-evento (W4, 1 feature)
# ---------------------------------------------------------------------------
def criar_feature_estado_pre_evento(
    df: pl.DataFrame, apo: pl.DataFrame
) -> pl.DataFrame:
    print("\n[6/9] Familia 3 — Estado pre-evento (1 feature)")
    t0 = time.time()

    # Cast apontamentos para us (era ns)
    apo_clean = (
        apo.select(["Tag", "Inicio", "Fim", "Classe"])
        .rename({"Classe": "_estado_apo"})
        .with_columns([
            pl.col("Inicio").dt.cast_time_unit("us"),
            pl.col("Fim").dt.cast_time_unit("us"),
        ])
        .sort("Inicio")
    )

    # Adiciona row_idx para restaurar ordem depois
    df = df.with_row_index("_row_idx")
    df_with_pre = df.with_columns(
        (pl.col("Data_Evento") - pl.duration(hours=1)).alias("_t_pre")
    ).sort("_t_pre")

    # join_asof backward
    joined = df_with_pre.join_asof(
        apo_clean,
        left_on="_t_pre",
        right_on="Inicio",
        by_left="TAG",
        by_right="Tag",
        strategy="backward",
    )

    # estado = _estado_apo se _t_pre <= Fim e Inicio nao-null; senao SEM_APONTAMENTO
    joined = joined.with_columns(
        pl.when(
            pl.col("Inicio").is_null() | (pl.col("_t_pre") > pl.col("Fim"))
        )
        .then(pl.lit("SEM_APONTAMENTO"))
        .otherwise(pl.col("_estado_apo"))
        .alias("estado_pre_evento")
    )

    # Restaura ordem original e remove helpers
    result = (
        joined.sort("_row_idx")
        .drop("_row_idx", "_t_pre", "_estado_apo", "Inicio", "Fim")
    )

    print("  Distribuicao de estado_pre_evento:")
    dist = result.group_by("estado_pre_evento").len().sort("len", descending=True)
    print(dist)
    print(f"  1 feature estado_pre_evento criada ({time.time()-t0:.1f}s)")
    return result


# ---------------------------------------------------------------------------
# [7/9] Familia 4 — Regimal (W4, 2 features sobre 19 alarmes)
# ---------------------------------------------------------------------------
def identificar_top_alarmes(df: pl.DataFrame) -> list[str]:
    """Retorna os alarmes que geraram >= 1 DG no semestre (esperado: 19)."""
    top = (
        df.filter(pl.col("Is_Dont_Go") == 1)
          .get_column("Alarme").unique().to_list()
    )
    print(f"  Top alarmes (geraram >= 1 DG): {len(top)}")
    assert len(top) == N_TOP_ALARMES_ESPERADO, (
        f"Esperado {N_TOP_ALARMES_ESPERADO} alarmes top, obtido {len(top)}"
    )
    return top


def criar_features_regimais(
    df: pl.DataFrame, top_alarmes: list[str]
) -> pl.DataFrame:
    print(f"\n[7/9] Familia 4 — Regimal (2 features, restrito a {len(top_alarmes)} alarmes)")
    t0 = time.time()

    df = df.sort(["TAG", "Data_Evento"])
    df = df.with_columns([
        pl.col("Alarme").is_in(top_alarmes).alias("_is_top_alarme"),
        pl.lit(1).cast(pl.Int32).alias("_one"),
        (pl.col("Criticidade") == "Critico").cast(pl.Int32).alias("_is_crit"),
        (pl.col("Criticidade") == "Nao_Critico").cast(pl.Int32).alias("_is_nc"),
    ])

    # Rolling counts por (TAG, Alarme) — feature 1
    df = df.with_columns([
        pl.col("_one").rolling_sum_by(
            by="Data_Evento", window_size="7d", closed="left"
        ).over(["TAG", "Alarme"]).fill_null(0).cast(pl.Int32).alias("_alarme_7d"),
        pl.col("_one").rolling_sum_by(
            by="Data_Evento", window_size="30d", closed="left"
        ).over(["TAG", "Alarme"]).fill_null(0).cast(pl.Int32).alias("_alarme_30d"),
    ])
    print("  Rolling per (TAG, Alarme) — 7d e 30d: OK")

    df = df.with_columns(
        pl.when(
            pl.col("_is_top_alarme") & (pl.col("_alarme_30d") > 0)
        )
        .then(
            (pl.col("_alarme_7d").cast(pl.Float64) * 30.0)
            / (pl.col("_alarme_30d").cast(pl.Float64) * 7.0)
        )
        .otherwise(None)
        .alias("razao_alarme_7d_vs_30d_anterior")
    )

    # Rolling counts por TAG para severidade — feature 2
    for window in ["14d", "60d"]:
        df = df.with_columns([
            pl.col("_is_crit").rolling_sum_by(
                by="Data_Evento", window_size=window, closed="left"
            ).over("TAG").fill_null(0).cast(pl.Int32).alias(f"_crit_{window}"),
            pl.col("_is_nc").rolling_sum_by(
                by="Data_Evento", window_size=window, closed="left"
            ).over("TAG").fill_null(0).cast(pl.Int32).alias(f"_nc_{window}"),
        ])
    print("  Rolling per TAG — 14d e 60d (Critico/NaoCritico): OK")

    df = df.with_columns(
        pl.when(
            (pl.col("_nc_14d") > 0)
            & (pl.col("_nc_60d") > 0)
            & (pl.col("_crit_60d") > 0)
        )
        .then(
            (pl.col("_crit_14d").cast(pl.Float64) * pl.col("_nc_60d"))
            / (pl.col("_nc_14d").cast(pl.Float64) * pl.col("_crit_60d"))
        )
        .otherwise(None)
        .alias("razao_severidade_14d_vs_60d")
    )

    df = df.drop(
        "_is_top_alarme", "_one", "_is_crit", "_is_nc",
        "_alarme_7d", "_alarme_30d",
        "_crit_14d", "_crit_60d", "_nc_14d", "_nc_60d",
    )

    n_null_alarme = df.get_column("razao_alarme_7d_vs_30d_anterior").null_count()
    n_null_sev = df.get_column("razao_severidade_14d_vs_60d").null_count()
    print(f"  razao_alarme NULL: {n_null_alarme:,} "
          f"({100*n_null_alarme/df.height:.1f}%) — esperado: alarmes fora dos top 19")
    print(f"  razao_severidade NULL: {n_null_sev:,} "
          f"({100*n_null_sev/df.height:.1f}%) — esperado: eventos no inicio do semestre")
    print(f"  2 features regimais criadas ({time.time()-t0:.1f}s)")
    return df


# ---------------------------------------------------------------------------
# [8/9] Validacao defensiva
# ---------------------------------------------------------------------------
def validar(df: pl.DataFrame) -> None:
    print("\n[8/9] Validando matriz final")

    # Shape
    assert df.shape[0] == LINHAS_ESPERADAS, (
        f"Linhas: esperado {LINHAS_ESPERADAS}, obtido {df.shape[0]}"
    )
    print(f"  OK Shape: {df.shape[0]:,} linhas x {df.shape[1]} colunas "
          f"(+{N_FEATURES_TOTAL} features)")

    # DGs preservados
    n_dgs = df.get_column("Is_Dont_Go").sum()
    assert n_dgs == DGS_ESPERADOS, f"DGs={n_dgs} esperado {DGS_ESPERADOS}"
    print(f"  OK DGs preservados: {n_dgs:,}")

    # Features básicas: 0 nulls
    for feat in ["hora_dia", "dia_semana", "turno", "mes", "valor_disponivel"]:
        assert df.get_column(feat).null_count() == 0, f"{feat} tem nulls"
    print("  OK 5 features basicas: 0 nulls")

    # Rolling features: 0 nulls (fill_null(0)), tipo Int32, >= 0
    for criticidade in ["critico", "nao_critico", "total"]:
        for window in ["1h", "4h", "24h"]:
            col = f"count_{criticidade}_{window}"
            assert df.get_column(col).null_count() == 0, f"{col} tem nulls"
            assert df.get_column(col).min() >= 0, f"{col} < 0"
    print("  OK 9 features rolling: 0 nulls, >= 0")

    # Coerencia interna: count_total = count_critico + count_nao_critico
    for window in ["1h", "4h", "24h"]:
        total_calc = (
            df.get_column(f"count_critico_{window}")
            + df.get_column(f"count_nao_critico_{window}")
        )
        total_real = df.get_column(f"count_total_{window}")
        diff_max = (total_calc - total_real).abs().max()
        assert diff_max == 0, (
            f"count_total_{window} != count_critico + count_nao_critico (diff_max={diff_max})"
        )
    print("  OK Coerencia: count_total = count_critico + count_nao_critico")

    # Recencia: pode ter NULL para eventos antes do primeiro DG/Crit do TAG
    # Valores >= 0 (= 0 quando ha eventos simultaneos no mesmo Data_Evento;
    # nao e' leakage real — apenas multiplos eventos da mesma TAG no mesmo
    # instante de telemetria)
    for col in ["horas_desde_ultimo_DG", "horas_desde_ultimo_critico"]:
        non_null = df.filter(pl.col(col).is_not_null()).get_column(col)
        if non_null.len() > 0:
            assert non_null.min() >= 0, f"{col} tem valor < 0 (leakage real!)"
            n_zeros = (non_null == 0).sum()
            pct_zeros = 100 * n_zeros / non_null.len()
            print(f"  {col}: min={non_null.min():.6f}h, "
                  f"valores = 0: {n_zeros:,} ({pct_zeros:.2f}%) — eventos simultaneos")
    print("  OK 2 features recencia: >= 0 quando nao-NULL")

    # estado_pre_evento: dominio fechado
    estados = sorted(df.get_column("estado_pre_evento").unique().to_list())
    valores_validos = {"Operando", "Parado", "Manutenção", "Hibernando", "SEM_APONTAMENTO"}
    extras = set(estados) - valores_validos
    assert not extras, f"estado_pre_evento valores inesperados: {extras}"
    print(f"  OK estado_pre_evento valores: {estados}")

    # Regimal: pode ter NULL; sem-NULL devem ser >= 0
    for col in ["razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d"]:
        non_null = df.filter(pl.col(col).is_not_null()).get_column(col)
        if non_null.len() > 0:
            assert non_null.min() >= 0, f"{col} < 0"
    print("  OK 2 features regimais: NULL OK, sem-NULL >= 0")


# ---------------------------------------------------------------------------
# [9/9] Persistencia
# ---------------------------------------------------------------------------
def salvar_v1(df: pl.DataFrame) -> None:
    DIR_FEATURES.mkdir(parents=True, exist_ok=True)
    # v1 contem apenas as 5 features basicas (para compatibilidade retroativa)
    cols_basicas = [
        c for c in df.columns
        if c not in [f["nome"] for f in FEATURES_AVANCADAS_W4]
    ]
    df_v1 = df.select(cols_basicas)
    t0 = time.time()
    df_v1.write_parquet(ARQ_V1, compression="snappy")
    mb = ARQ_V1.stat().st_size / 1024 / 1024
    print(f"\n  {ARQ_V1.relative_to(ROOT)}  "
          f"({mb:,.1f} MB, {df_v1.shape[1]} cols, {time.time()-t0:.1f}s)")


def salvar_v2_parcial(df: pl.DataFrame) -> None:
    t0 = time.time()
    df.write_parquet(ARQ_V2_PARCIAL, compression="snappy")
    mb = ARQ_V2_PARCIAL.stat().st_size / 1024 / 1024
    print(f"  {ARQ_V2_PARCIAL.relative_to(ROOT)}  "
          f"({mb:,.1f} MB, {df.shape[1]} cols, {time.time()-t0:.1f}s)")


def salvar_documentacao() -> None:
    ARQ_DOC_FEATURES.parent.mkdir(parents=True, exist_ok=True)
    doc = pl.DataFrame(FEATURES_DEFINIDAS)
    doc.write_csv(ARQ_DOC_FEATURES)
    print(f"  {ARQ_DOC_FEATURES.relative_to(ROOT)} ({doc.height} features documentadas)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Feature engineering (W3 basicas + W4 avancadas) ===")

    telemetria, apontamentos = carregar()
    print(f"\n  Identificando top alarmes (Is_Dont_Go == 1):")
    top_alarmes = identificar_top_alarmes(telemetria)

    df = criar_features_temporais(telemetria)
    df = criar_feature_valor_disponivel(df)
    df = criar_features_rolling(df)
    df = criar_features_recencia(df)
    df = criar_feature_estado_pre_evento(df, apontamentos)
    df = criar_features_regimais(df, top_alarmes)

    validar(df)

    print("\n[9/9] Salvando outputs")
    salvar_v1(df)
    salvar_v2_parcial(df)
    salvar_documentacao()

    print(f"\n[OK] Features W3+W4 (parcial) geradas. Total: {N_FEATURES_TOTAL} features.")
    print("\nProximas etapas (continuar W4 em proxima sessao):")
    print("  - Features de operador: taxa_DG_operador_30d (alimenta Q3) + n_bypasses_operador_7d (H1.2)")
    print("  - Features de regra de negocio: qtd_alarmes_nivel_muito_alto_360min")
    print("  - Encoding categorico (Tag, Frota, Tipo, Classe, Operador)")
    print("  - Fig Extra C: cadeia de eventos CA65924 (Obs 2.3)")
    print("  - Construir target y=1 se DG em [+0, +4h] (CM 3.3)")
    print("  - Sensibilidade janela 2h/4h/8h + Fig 7")
    print("  - 06_split.py: jan-abr / mai / jun + Fig 8")
    print("  - Salvar v2.parquet (final)")


if __name__ == "__main__":
    main()
