"""
05_features.py - Feature engineering completo (W3 basicas + W4 completo).

Pipeline em 10 etapas que constroi 29 features sobre o dataset limpo de
telemetria + apontamentos, gerando a matriz definitiva v2.parquet para
modelagem em W5-W7.

Familias implementadas (7 grupos = 29 features):

W3 (5 features basicas):
  - hora_dia, dia_semana, turno, mes (temporais)
  - valor_disponivel

W4 — Familias 1-4 (14 features):
  Familia 1 — Rolling windows (9): count_{critico/nao_critico/total}_{1h,4h,24h}
  Familia 2 — Recencia (2): horas_desde_ultimo_DG, horas_desde_ultimo_critico
  Familia 3 — Estado pre-evento (1): estado_pre_evento via join_asof t-1h
  Familia 4 — Regimal (2): razao_alarme_7d_vs_30d_anterior, razao_severidade_14d_vs_60d

W4 — Familias 5-7 (10 features, novas nesta sessao):
  Familia 5 — Operador (2):
    - taxa_DG_operador_30d (alimenta Q3)
    - n_bypasses_operador_7d (H1.2 — carrega telemetria_tipada pre-filtro)
  Familia 6 — Regra de negocio (1):
    - qtd_alarmes_nivel_muito_alto_360min (lista de 82 regras CMA)
  Familia 7 — Encoding categorico (7):
    - tag_freq, frota_* (4 dummies), tipo_caminhao, operador_freq
    - Target encoding propriamente dito fica para iteracao apos W4
      construir o target real (CM 3.3)

Decisoes metodologicas (registradas em PLANEJAMENTO.md / controle_alteracoes.md):
  - Leakage prevention: rolling_sum_by com closed="left" em todas features
  - Recencia sem precedente: NULL
  - Regimal sobre 19 alarmes (alinhado com hipoteses_eda.md H2.1)
  - Bypasses: carga adicional de telemetria_tipada.parquet (pre-filtro)
  - Encoding: frequency + one-hot nesta sessao (sem target encoding)

Entradas:
  - Projeto/dados/intermediarios/telemetria_limpa.parquet (~545k linhas, pos filtro)
  - Projeto/dados/intermediarios/apontamentos_limpo.parquet (~377k linhas)
  - Projeto/dados/intermediarios/telemetria_tipada.parquet (pre-filtro, so para bypasses)
  - Projeto/relatorio/tabelas/eventos_muito_alto.csv (82 regras CMA)

Saidas:
  - Projeto/dados/features/v1.parquet            (5 features basicas — W3)
  - Projeto/dados/features/v2_parcial.parquet    (19 features — W4 parcial)
  - Projeto/dados/features/v2.parquet            (29 features — W4 completo)
  - Projeto/relatorio/tabelas/documentacao_features.csv (CM 3.2, 29 entradas)

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
ARQ_TELEMETRIA_TIPADA = ROOT / "dados" / "intermediarios" / "telemetria_tipada.parquet"
ARQ_EVENTOS_MUITO_ALTO = ROOT / "relatorio" / "tabelas" / "eventos_muito_alto.csv"
DIR_FEATURES = ROOT / "dados" / "features"
ARQ_V1 = DIR_FEATURES / "v1.parquet"
ARQ_V2_PARCIAL = DIR_FEATURES / "v2_parcial.parquet"
ARQ_V2 = DIR_FEATURES / "v2.parquet"
ARQ_DOC_FEATURES = ROOT / "relatorio" / "tabelas" / "documentacao_features.csv"

# ---------------------------------------------------------------------------
# Expectativas
# ---------------------------------------------------------------------------
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
VALOR_NULLS_ESPERADOS = 237_443
N_FEATURES_BASICAS = 5
N_FEATURES_AVANCADAS_PARCIAL = 14   # Familias 1-4
N_FEATURES_AVANCADAS_FINAL = 10     # Familias 5-7
N_FEATURES_TOTAL = (
    N_FEATURES_BASICAS + N_FEATURES_AVANCADAS_PARCIAL + N_FEATURES_AVANCADAS_FINAL
)  # = 29
N_TOP_ALARMES_ESPERADO = 19
N_BYPASSES_ESPERADO = 3_119  # Id_Criticidade=4 no semestre


# ---------------------------------------------------------------------------
# Definicao de features (uma entrada por feature, CM 3.2)
# ---------------------------------------------------------------------------
FEATURES_BASICAS_W3 = [
    {
        "nome": "hora_dia", "tipo": "Int8",
        "descricao": "Hora do dia em que o evento ocorreu (0-23)",
        "formula": "Data_Evento.dt.hour()",
        "motivacao": (
            "Q5 (W2): heatmap hora x dia revelou pico extremo de DGs em segunda "
            "as 23h; variacao de aproximadamente 3x entre hora minima e maxima."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "dia_semana", "tipo": "Int8",
        "descricao": "Dia da semana do evento (1=Seg ... 7=Dom)",
        "formula": "Data_Evento.dt.weekday()",
        "motivacao": (
            "Q5 (W2): segunda-feira concentra as maiores taxas de DG; "
            "padrao de 'rampa de retomada apos fim de semana'."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "turno", "tipo": "String",
        "descricao": "Turno operacional: 'Diurno' (Inicio_Turno=6h) ou 'Noturno' (Inicio_Turno=18h)",
        "formula": "'Diurno' if Inicio_Turno.dt.hour() == 6 else 'Noturno'",
        "motivacao": (
            "Operacao 24x7 em turnos de 12h. Fig 2 mostra picos em 4-5h e "
            "17-18h consistentes com transicoes de turno."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "mes", "tipo": "Int8",
        "descricao": "Mes do evento (1=jan ... 6=jun de 2025)",
        "formula": "Data_Evento.dt.month()",
        "motivacao": (
            "Obs 2.6: 3 regimes temporais distintos. Anomalia A (Engine Coolant "
            "fev-mar) e Anomalia B (Right Front Brake jun); captura non-stationarity."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "valor_disponivel", "tipo": "Bool",
        "descricao": "True se o evento possui medicao numerica (Valor IS NOT NULL)",
        "formula": "Valor.is_not_null()",
        "motivacao": (
            "Achado W3: 43.58% dos eventos relevantes nao possuem Valor numerico — "
            "alarmes 'Active/Inactive' sem medicao. Categoria binaria preditiva."
        ),
        "semana_criada": "W3",
    },
]

FEATURES_AVANCADAS_W4_PARCIAL = []
# Familia 1 — Rolling windows (9)
for criticidade in ["critico", "nao_critico", "total"]:
    for window in ["1h", "4h", "24h"]:
        FEATURES_AVANCADAS_W4_PARCIAL.append({
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
                "Rolling captura padrao temporal — family core. "
                "count_total valida H5.2 / Obs 2.3 (padrao CA65924)."
            ),
            "semana_criada": "W4 parcial",
        })

# Familia 2 — Recencia (2)
FEATURES_AVANCADAS_W4_PARCIAL.extend([
    {
        "nome": "horas_desde_ultimo_DG", "tipo": "Float64",
        "descricao": "Horas desde o ultimo DG do mesmo TAG (NULL se nao houve DG anterior)",
        "formula": "(Data_Evento - last_DG_timestamp).total_hours() per TAG",
        "motivacao": (
            "Padrao classico de manutencao preditiva. Achado lateral: 479 valores "
            "= 0 indicam DGs simultaneos (cascata)."
        ),
        "semana_criada": "W4 parcial",
    },
    {
        "nome": "horas_desde_ultimo_critico", "tipo": "Float64",
        "descricao": "Horas desde o ultimo evento Critico do mesmo TAG",
        "formula": "(Data_Evento - last_Critico_timestamp).total_hours() per TAG",
        "motivacao": (
            "Critico tem taxa de DG 12,39% (Obs 2.2). 5.104 valores = 0 (0,94%) "
            "indicam cascata de alarmes Criticos simultaneos — sinal preditivo legitimo."
        ),
        "semana_criada": "W4 parcial",
    },
])

# Familia 3 — Estado pre-evento (1)
FEATURES_AVANCADAS_W4_PARCIAL.append({
    "nome": "estado_pre_evento", "tipo": "String",
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
        "de teste). Cobertura quase perfeita — apenas 106 eventos SEM_APONTAMENTO."
    ),
    "semana_criada": "W4 parcial",
})

# Familia 4 — Regimal (2)
FEATURES_AVANCADAS_W4_PARCIAL.extend([
    {
        "nome": "razao_alarme_7d_vs_30d_anterior", "tipo": "Float64",
        "descricao": (
            "Razao normalizada por dias entre frequencia do mesmo alarme em (TAG, Alarme) "
            "nos ultimos 7d vs baseline historico de 30d. NULL se Alarme nao esta nos top 19."
        ),
        "formula": (
            "(count_7d/7) / (count_30d/30) per (TAG, Alarme); restrito a top 19 alarmes"
        ),
        "motivacao": (
            "Obs 2.6 extensao: Right Front Brake explodiu 151,7x em junho "
            "(estatisticamente invisivel no treino jan-mai). Razao detecta explosoes."
        ),
        "semana_criada": "W4 parcial",
    },
    {
        "nome": "razao_severidade_14d_vs_60d", "tipo": "Float64",
        "descricao": (
            "Razao (Critico/NaoCritico) em 14d vs 60d per TAG. "
            "NULL quando denominadores=0."
        ),
        "formula": "(crit_14d * nc_60d) / (nc_14d * crit_60d) per TAG, rolling closed=left",
        "motivacao": (
            "Obs 2.6: Engine Coolant inverteu severidade (83% Critico → 6% em fev-mar). "
            "Razao Critico/Nao-Critico em janela curta vs longa detecta inversoes."
        ),
        "semana_criada": "W4 parcial",
    },
])

FEATURES_AVANCADAS_W4_FINAL = [
    # ====== Familia 5 — Operador (2) ======
    {
        "nome": "taxa_DG_operador_30d", "tipo": "Float64",
        "descricao": (
            "Proporcao de DGs nos eventos do mesmo operador nos ultimos 30 dias "
            "(NULL quando operador nao tem eventos nas 30d anteriores)"
        ),
        "formula": (
            "sum(Is_Dont_Go) / count(eventos) sobre janela 30d closed=left "
            "per Nome_Operador_Anon"
        ),
        "motivacao": (
            "Alimenta diretamente Q3 (operador correlaciona com alertas?). Obs 2.4 "
            "(OP_067 do caso CA65924 e' outlier?) sera respondida via SHAP em W7 "
            "sobre essa feature."
        ),
        "semana_criada": "W4 final",
    },
    {
        "nome": "n_bypasses_operador_7d", "tipo": "Int32",
        "descricao": (
            "Numero de eventos de bypass manual (Id_Criticidade=4) feitos pelo mesmo "
            "operador nos ultimos 7d, contando inclusive bypasses Informacional "
            "(pre-filtro)"
        ),
        "formula": (
            "rolling_sum_by(by=Data_Evento, window=7d, closed=left) sobre flag "
            "Id_Criticidade=4 do dataset telemetria_tipada (pre-filtro de "
            "Informacional), per Nome_Operador_Anon"
        ),
        "motivacao": (
            "H1.2 (W1): 3.119 eventos com Id_Criticidade=4 sao bypass manual; 87% "
            "concentrados em 'Channel Forced (L-1850)'. Operadores que bypassam "
            "frequentemente podem ser preditores de DG futuro (comportamento de risco)."
        ),
        "semana_criada": "W4 final",
    },

    # ====== Familia 6 — Regra de negocio (1) ======
    {
        "nome": "qtd_alarmes_nivel_muito_alto_360min", "tipo": "Int32",
        "descricao": (
            "Quantidade de eventos do mesmo TAG nas ultimas 360 min (6h) cujo "
            "Alarme pertence a lista de 82 regras CMA 'Muito Alto'"
        ),
        "formula": (
            "rolling_sum_by(by=Data_Evento, window=6h, closed=left) sobre flag "
            "Alarme.is_in(eventos_muito_alto.EVENTO.unique()), per TAG"
        ),
        "motivacao": (
            "Eventos da lista 'Muito Alto' sao precursores diretos de DG conforme "
            "regra CMA documentada em eventos_muito_alto.csv (gerada em W2). "
            "Janela de 6h captura padroes de acumulacao no escopo das regras CMA QTD>1."
        ),
        "semana_criada": "W4 final",
    },

    # ====== Familia 7 — Encoding categorico (7) ======
    # Usando frequency encoding + one-hot. Target encoding propriamente dito
    # fica para iteracao apos W4 construir target real (CM 3.3).
    {
        "nome": "tag_freq", "tipo": "Float64",
        "descricao": "Frequencia relativa do TAG no dataset filtrado (count(TAG=x) / total)",
        "formula": "count(TAG) / 544885",
        "motivacao": (
            "Frequency encoding para alta cardinalidade (35 TAGs). Captura 'volume "
            "operacional' do equipamento; CA65926 (Pareto top 1) tera valor alto."
        ),
        "semana_criada": "W4 final",
    },
    {
        "nome": "frota_793D_2S", "tipo": "Int8",
        "descricao": "1 se Tag_Frota=='793-D 2S', 0 caso contrario",
        "formula": "(Tag_Frota == '793-D 2S').cast(Int8)",
        "motivacao": (
            "One-hot encoding para Frota (5 valores). LeTourneau L 1850 e' "
            "referencia (todas as 4 dummies = 0 implica LeTourneau)."
        ),
        "semana_criada": "W4 final",
    },
    {
        "nome": "frota_793D_3S", "tipo": "Int8",
        "descricao": "1 se Tag_Frota=='793-D 3S', 0 caso contrario",
        "formula": "(Tag_Frota == '793-D 3S').cast(Int8)",
        "motivacao": "One-hot encoding para Frota — ver frota_793D_2S.",
        "semana_criada": "W4 final",
    },
    {
        "nome": "frota_793D_4S", "tipo": "Int8",
        "descricao": "1 se Tag_Frota=='793-D 4S', 0 caso contrario",
        "formula": "(Tag_Frota == '793-D 4S').cast(Int8)",
        "motivacao": "One-hot encoding para Frota — ver frota_793D_2S.",
        "semana_criada": "W4 final",
    },
    {
        "nome": "frota_793D_5S", "tipo": "Int8",
        "descricao": "1 se Tag_Frota=='793-D 5S', 0 caso contrario",
        "formula": "(Tag_Frota == '793-D 5S').cast(Int8)",
        "motivacao": (
            "One-hot encoding para Frota. 793-D 5S concentra 46,8% dos DGs do semestre — "
            "feature de alta importancia esperada."
        ),
        "semana_criada": "W4 final",
    },
    {
        "nome": "tipo_caminhao", "tipo": "Int8",
        "descricao": "1 se Tipo=='Caminhao', 0 se 'Escavadeira'",
        "formula": "(Tipo == 'Caminhao').cast(Int8)",
        "motivacao": (
            "Binario para Tipo (so 2 valores). Caminhoes 793-D respondem por ~99% dos "
            "DGs; LeTourneau (escavadeira) tem perfil distinto (H4.1)."
        ),
        "semana_criada": "W4 final",
    },
    {
        "nome": "operador_freq", "tipo": "Float64",
        "descricao": (
            "Frequencia relativa do operador no dataset filtrado "
            "(count(Nome_Operador_Anon=x) / total)"
        ),
        "formula": "count(Nome_Operador_Anon) / 544885",
        "motivacao": (
            "Frequency encoding para Operador (alta cardinalidade, anonimizado). "
            "Complementa taxa_DG_operador_30d capturando 'volume operacional' do operador."
        ),
        "semana_criada": "W4 final",
    },
]

FEATURES_DEFINIDAS = (
    FEATURES_BASICAS_W3
    + FEATURES_AVANCADAS_W4_PARCIAL
    + FEATURES_AVANCADAS_W4_FINAL
)


# ---------------------------------------------------------------------------
# [1/10] Carga
# ---------------------------------------------------------------------------
def carregar() -> tuple[pl.DataFrame, pl.DataFrame]:
    print("[1/10] Carregando datasets")
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
# [2/10] Features temporais (W3)
# ---------------------------------------------------------------------------
def criar_features_temporais(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[2/10] Features temporais (W3 — 4 features)")
    horas_inicio = (
        df.select(pl.col("Inicio_Turno").dt.hour().alias("h"))
        ["h"].unique().sort().to_list()
    )
    assert set(horas_inicio).issubset({6, 18})
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
# [3/10] valor_disponivel (W3)
# ---------------------------------------------------------------------------
def criar_feature_valor_disponivel(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[3/10] Feature valor_disponivel (W3)")
    df = df.with_columns(
        pl.col("Valor").is_not_null().alias("valor_disponivel")
    )
    n_true = df.filter(pl.col("valor_disponivel")).height
    print(f"  True: {n_true:,} | False: {df.height-n_true:,} "
          f"({100*(df.height-n_true)/df.height:.2f}%)")
    return df


# ---------------------------------------------------------------------------
# [4/10] Familia 1 — Rolling windows (W4 parcial, 9 features)
# ---------------------------------------------------------------------------
def criar_features_rolling(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[4/10] Familia 1 — Rolling windows (9 features)")
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
    df = df.drop("_is_critico", "_is_nao_critico", "_is_total")
    print(f"  9 features rolling criadas ({time.time()-t0:.1f}s)")
    return df


# ---------------------------------------------------------------------------
# [5/10] Familia 2 — Recencia (W4 parcial, 2 features)
# ---------------------------------------------------------------------------
def criar_features_recencia(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[5/10] Familia 2 — Recencia (2 features)")
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
    print(f"  2 features recencia criadas ({time.time()-t0:.1f}s)")
    return df


# ---------------------------------------------------------------------------
# [6/10] Familia 3 — Estado pre-evento (W4 parcial, 1 feature)
# ---------------------------------------------------------------------------
def criar_feature_estado_pre_evento(
    df: pl.DataFrame, apo: pl.DataFrame
) -> pl.DataFrame:
    print("\n[6/10] Familia 3 — Estado pre-evento (1 feature)")
    t0 = time.time()
    apo_clean = (
        apo.select(["Tag", "Inicio", "Fim", "Classe"])
        .rename({"Classe": "_estado_apo"})
        .with_columns([
            pl.col("Inicio").dt.cast_time_unit("us"),
            pl.col("Fim").dt.cast_time_unit("us"),
        ])
        .sort("Inicio")
    )
    df = df.with_row_index("_row_idx")
    df_with_pre = df.with_columns(
        (pl.col("Data_Evento") - pl.duration(hours=1)).alias("_t_pre")
    ).sort("_t_pre")
    joined = df_with_pre.join_asof(
        apo_clean,
        left_on="_t_pre",
        right_on="Inicio",
        by_left="TAG",
        by_right="Tag",
        strategy="backward",
    )
    joined = joined.with_columns(
        pl.when(
            pl.col("Inicio").is_null() | (pl.col("_t_pre") > pl.col("Fim"))
        )
        .then(pl.lit("SEM_APONTAMENTO"))
        .otherwise(pl.col("_estado_apo"))
        .alias("estado_pre_evento")
    )
    result = (
        joined.sort("_row_idx")
        .drop("_row_idx", "_t_pre", "_estado_apo", "Inicio", "Fim")
    )
    print(f"  1 feature estado_pre_evento criada ({time.time()-t0:.1f}s)")
    return result


# ---------------------------------------------------------------------------
# [7/10] Familia 4 — Regimal (W4 parcial, 2 features)
# ---------------------------------------------------------------------------
def identificar_top_alarmes(df: pl.DataFrame) -> list[str]:
    top = (
        df.filter(pl.col("Is_Dont_Go") == 1)
          .get_column("Alarme").unique().to_list()
    )
    assert len(top) == N_TOP_ALARMES_ESPERADO
    return top


def criar_features_regimais(
    df: pl.DataFrame, top_alarmes: list[str]
) -> pl.DataFrame:
    print(f"\n[7/10] Familia 4 — Regimal (2 features, restrito a {len(top_alarmes)} alarmes)")
    t0 = time.time()
    df = df.sort(["TAG", "Data_Evento"])
    df = df.with_columns([
        pl.col("Alarme").is_in(top_alarmes).alias("_is_top_alarme"),
        pl.lit(1).cast(pl.Int32).alias("_one"),
        (pl.col("Criticidade") == "Critico").cast(pl.Int32).alias("_is_crit"),
        (pl.col("Criticidade") == "Nao_Critico").cast(pl.Int32).alias("_is_nc"),
    ])
    df = df.with_columns([
        pl.col("_one").rolling_sum_by(
            by="Data_Evento", window_size="7d", closed="left"
        ).over(["TAG", "Alarme"]).fill_null(0).cast(pl.Int32).alias("_alarme_7d"),
        pl.col("_one").rolling_sum_by(
            by="Data_Evento", window_size="30d", closed="left"
        ).over(["TAG", "Alarme"]).fill_null(0).cast(pl.Int32).alias("_alarme_30d"),
    ])
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
    for window in ["14d", "60d"]:
        df = df.with_columns([
            pl.col("_is_crit").rolling_sum_by(
                by="Data_Evento", window_size=window, closed="left"
            ).over("TAG").fill_null(0).cast(pl.Int32).alias(f"_crit_{window}"),
            pl.col("_is_nc").rolling_sum_by(
                by="Data_Evento", window_size=window, closed="left"
            ).over("TAG").fill_null(0).cast(pl.Int32).alias(f"_nc_{window}"),
        ])
    df = df.with_columns(
        pl.when(
            (pl.col("_nc_14d") > 0) & (pl.col("_nc_60d") > 0) & (pl.col("_crit_60d") > 0)
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
    print(f"  2 features regimais criadas ({time.time()-t0:.1f}s)")
    return df


# ---------------------------------------------------------------------------
# [8/10] Familia 5 — Operador (W4 final, 2 features)
# ---------------------------------------------------------------------------
def criar_features_operador(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[8/10] Familia 5 — Operador (2 features)")
    t0 = time.time()

    # --- Feature 1: taxa_DG_operador_30d ---
    df = df.sort(["Nome_Operador_Anon", "Data_Evento"])
    df = df.with_columns([
        pl.col("Is_Dont_Go").cast(pl.Int32).alias("_is_dg"),
        pl.lit(1).cast(pl.Int32).alias("_one_op"),
    ])
    df = df.with_columns([
        pl.col("_is_dg").rolling_sum_by(
            by="Data_Evento", window_size="30d", closed="left"
        ).over("Nome_Operador_Anon").fill_null(0).cast(pl.Int32).alias("_dg_30d"),
        pl.col("_one_op").rolling_sum_by(
            by="Data_Evento", window_size="30d", closed="left"
        ).over("Nome_Operador_Anon").fill_null(0).cast(pl.Int32).alias("_eventos_30d"),
    ])
    df = df.with_columns(
        pl.when(pl.col("_eventos_30d") > 0)
          .then(pl.col("_dg_30d").cast(pl.Float64) / pl.col("_eventos_30d"))
          .otherwise(None)
          .alias("taxa_DG_operador_30d")
    )
    df = df.drop("_is_dg", "_one_op", "_dg_30d", "_eventos_30d")
    print("  taxa_DG_operador_30d: OK")

    # --- Feature 2: n_bypasses_operador_7d ---
    # Carrega telemetria_tipada (pre-filtro) e extrai bypasses
    if not ARQ_TELEMETRIA_TIPADA.exists():
        raise FileNotFoundError(f"{ARQ_TELEMETRIA_TIPADA} nao encontrado.")
    bypasses = (
        pl.read_parquet(ARQ_TELEMETRIA_TIPADA)
          .filter(pl.col("Id_Criticidade") == 4)
          .select(["Nome_Operador_Anon", "Data_Evento"])
    )
    print(f"  Bypasses extraidos de telemetria_tipada (Id_Criticidade=4): "
          f"{bypasses.height:,} (esperado ~{N_BYPASSES_ESPERADO})")
    assert bypasses.height == N_BYPASSES_ESPERADO, (
        f"Esperado {N_BYPASSES_ESPERADO} bypasses, obtido {bypasses.height}"
    )

    # Concat main + bypasses, com flag
    main_min = df.select(["Nome_Operador_Anon", "Data_Evento"]).with_columns([
        pl.lit(0).cast(pl.Int32).alias("_is_bp"),
    ]).with_row_index("_main_idx")
    bypasses_with = bypasses.with_columns([
        pl.lit(1).cast(pl.Int32).alias("_is_bp"),
        pl.lit(None, dtype=pl.UInt32).alias("_main_idx"),
    ]).select(["_main_idx", "Nome_Operador_Anon", "Data_Evento", "_is_bp"])

    combined = pl.concat([main_min, bypasses_with], how="vertical").sort(
        ["Nome_Operador_Anon", "Data_Evento"]
    )
    combined = combined.with_columns(
        pl.col("_is_bp").rolling_sum_by(
            by="Data_Evento", window_size="7d", closed="left"
        ).over("Nome_Operador_Anon").fill_null(0).cast(pl.Int32).alias("_bp_7d")
    )

    # Extrai so eventos do main (com _main_idx nao-null)
    main_with_bp = (
        combined.filter(pl.col("_main_idx").is_not_null())
                .select(["_main_idx", "_bp_7d"])
                .rename({"_bp_7d": "n_bypasses_operador_7d"})
    )

    # Join de volta no df principal
    df = df.with_row_index("_main_idx")
    df = df.join(main_with_bp, on="_main_idx", how="left")
    df = df.drop("_main_idx")
    print(f"  n_bypasses_operador_7d: OK ({time.time()-t0:.1f}s)")

    return df


# ---------------------------------------------------------------------------
# [9/10] Familia 6 — Regra de negocio (W4 final, 1 feature)
# ---------------------------------------------------------------------------
def criar_feature_regra_negocio(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[9/10] Familia 6 — Regra de negocio (1 feature)")
    t0 = time.time()

    if not ARQ_EVENTOS_MUITO_ALTO.exists():
        raise FileNotFoundError(f"{ARQ_EVENTOS_MUITO_ALTO} nao encontrado.")
    eventos_mt = pl.read_csv(ARQ_EVENTOS_MUITO_ALTO)
    alarmes_mt = eventos_mt.get_column("EVENTO").unique().to_list()
    print(f"  Alarmes 'Muito Alto' unicos: {len(alarmes_mt)} (de 82 regras CMA)")

    df = df.sort(["TAG", "Data_Evento"])
    df = df.with_columns(
        pl.col("Alarme").is_in(alarmes_mt).cast(pl.Int32).alias("_is_mt")
    )
    df = df.with_columns(
        pl.col("_is_mt").rolling_sum_by(
            by="Data_Evento", window_size="6h", closed="left"
        ).over("TAG").fill_null(0).cast(pl.Int32)
          .alias("qtd_alarmes_nivel_muito_alto_360min")
    )
    df = df.drop("_is_mt")
    n_eventos_mt = df.filter(
        pl.col("Alarme").is_in(alarmes_mt)
    ).height
    print(f"  Eventos com Alarme em lista Muito Alto: {n_eventos_mt:,} "
          f"({100*n_eventos_mt/df.height:.1f}% do dataset)")
    print(f"  1 feature regra_negocio criada ({time.time()-t0:.1f}s)")

    return df


# ---------------------------------------------------------------------------
# [10/10] Familia 7 — Encoding categorico (W4 final, 7 features)
# ---------------------------------------------------------------------------
def criar_features_encoding(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[10/10] Familia 7 — Encoding categorico (7 features)")
    t0 = time.time()

    total = df.height

    # --- tag_freq ---
    tag_counts = df.group_by("TAG").agg(pl.len().alias("_tag_count"))
    df = df.join(tag_counts, on="TAG", how="left")
    df = df.with_columns(
        (pl.col("_tag_count").cast(pl.Float64) / total).alias("tag_freq")
    ).drop("_tag_count")
    print(f"  tag_freq: OK ({df['TAG'].n_unique()} TAGs)")

    # --- frota_* one-hot (4 colunas, LeTourneau como referencia) ---
    frotas_esperadas = {"793-D 2S", "793-D 3S", "793-D 4S", "793-D 5S", "LeTourneau L 1850"}
    frotas_atual = set(df.get_column("Tag_Frota").unique().to_list())
    if frotas_atual != frotas_esperadas:
        print(f"  AVISO: Tag_Frota tem valores diferentes do esperado.")
        print(f"    Esperado: {frotas_esperadas}")
        print(f"    Obtido:   {frotas_atual}")

    df = df.with_columns([
        (pl.col("Tag_Frota") == "793-D 2S").cast(pl.Int8).alias("frota_793D_2S"),
        (pl.col("Tag_Frota") == "793-D 3S").cast(pl.Int8).alias("frota_793D_3S"),
        (pl.col("Tag_Frota") == "793-D 4S").cast(pl.Int8).alias("frota_793D_4S"),
        (pl.col("Tag_Frota") == "793-D 5S").cast(pl.Int8).alias("frota_793D_5S"),
    ])
    print("  frota_* (4 one-hot, LeTourneau referencia): OK")

    # --- tipo_caminhao binario ---
    tipos = sorted(df.get_column("Tipo").unique().to_list())
    print(f"  Tipos encontrados: {tipos}")
    df = df.with_columns(
        (pl.col("Tipo") == "Caminhao").cast(pl.Int8).alias("tipo_caminhao")
    )

    # --- operador_freq ---
    op_counts = df.group_by("Nome_Operador_Anon").agg(pl.len().alias("_op_count"))
    df = df.join(op_counts, on="Nome_Operador_Anon", how="left")
    df = df.with_columns(
        (pl.col("_op_count").cast(pl.Float64) / total).alias("operador_freq")
    ).drop("_op_count")
    print(f"  operador_freq: OK ({df['Nome_Operador_Anon'].n_unique()} operadores)")

    print(f"  7 features encoding criadas ({time.time()-t0:.1f}s)")
    return df


# ---------------------------------------------------------------------------
# Validacao defensiva
# ---------------------------------------------------------------------------
def validar(df: pl.DataFrame) -> None:
    print("\nValidando matriz final")

    # Shape
    assert df.shape[0] == LINHAS_ESPERADAS
    print(f"  OK Shape: {df.shape[0]:,} linhas x {df.shape[1]} colunas "
          f"(+{N_FEATURES_TOTAL} features novas)")

    # DGs preservados
    n_dgs = df.get_column("Is_Dont_Go").sum()
    assert n_dgs == DGS_ESPERADOS
    print(f"  OK DGs preservados: {n_dgs:,}")

    # Basicas
    for feat in ["hora_dia", "dia_semana", "turno", "mes", "valor_disponivel"]:
        assert df.get_column(feat).null_count() == 0
    print("  OK 5 basicas: 0 nulls")

    # Rolling
    for criticidade in ["critico", "nao_critico", "total"]:
        for window in ["1h", "4h", "24h"]:
            col = f"count_{criticidade}_{window}"
            assert df.get_column(col).null_count() == 0
            assert df.get_column(col).min() >= 0
    print("  OK 9 rolling: 0 nulls, >= 0")

    # Coerencia rolling
    for window in ["1h", "4h", "24h"]:
        diff = (
            df.get_column(f"count_critico_{window}")
            + df.get_column(f"count_nao_critico_{window}")
            - df.get_column(f"count_total_{window}")
        ).abs().max()
        assert diff == 0
    print("  OK count_total = count_critico + count_nao_critico")

    # Recencia
    for col in ["horas_desde_ultimo_DG", "horas_desde_ultimo_critico"]:
        non_null = df.filter(pl.col(col).is_not_null()).get_column(col)
        if non_null.len() > 0:
            assert non_null.min() >= 0
    print("  OK 2 recencia: >= 0 quando nao-NULL")

    # estado_pre_evento
    estados = sorted(df.get_column("estado_pre_evento").unique().to_list())
    valores_validos = {"Operando", "Parado", "Manutenção", "Hibernando", "SEM_APONTAMENTO"}
    assert set(estados).issubset(valores_validos)
    print(f"  OK estado_pre_evento: {estados}")

    # Regimal
    for col in ["razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d"]:
        non_null = df.filter(pl.col(col).is_not_null()).get_column(col)
        if non_null.len() > 0:
            assert non_null.min() >= 0
    print("  OK 2 regimais: NULL OK, sem-NULL >= 0")

    # --- Familia 5 — Operador ---
    # taxa_DG_operador_30d: float em [0, 1] quando nao-NULL
    taxa = df.filter(pl.col("taxa_DG_operador_30d").is_not_null()).get_column("taxa_DG_operador_30d")
    if taxa.len() > 0:
        assert taxa.min() >= 0 and taxa.max() <= 1, (
            f"taxa_DG_operador_30d fora do range [0,1]: "
            f"min={taxa.min()}, max={taxa.max()}"
        )
    print(f"  OK taxa_DG_operador_30d: range [0, 1], NULLs={df.get_column('taxa_DG_operador_30d').null_count():,}")

    # n_bypasses_operador_7d: Int32, >= 0, 0 nulls
    bp = df.get_column("n_bypasses_operador_7d")
    assert bp.null_count() == 0
    assert bp.min() >= 0
    print(f"  OK n_bypasses_operador_7d: 0 nulls, >= 0, max={bp.max():,}")

    # --- Familia 6 — Regra de negocio ---
    mt = df.get_column("qtd_alarmes_nivel_muito_alto_360min")
    assert mt.null_count() == 0
    assert mt.min() >= 0
    print(f"  OK qtd_alarmes_nivel_muito_alto_360min: 0 nulls, >= 0, max={mt.max():,}")

    # --- Familia 7 — Encoding ---
    # tag_freq, operador_freq: Float em (0, 1)
    for col in ["tag_freq", "operador_freq"]:
        s = df.get_column(col)
        assert s.null_count() == 0
        assert s.min() > 0 and s.max() <= 1, f"{col} fora de (0,1]"
    print("  OK tag_freq, operador_freq: 0 nulls, (0, 1]")

    # frota_*: 0/1, 0 nulls
    for f in ["frota_793D_2S", "frota_793D_3S", "frota_793D_4S", "frota_793D_5S"]:
        s = df.get_column(f)
        assert s.null_count() == 0
        assert s.min() >= 0 and s.max() <= 1
    # Soma das 4 frota dummies: 0 (LeTourneau) ou 1 (uma das 4)
    soma_frotas = (
        df.get_column("frota_793D_2S") + df.get_column("frota_793D_3S")
        + df.get_column("frota_793D_4S") + df.get_column("frota_793D_5S")
    )
    assert soma_frotas.min() >= 0 and soma_frotas.max() <= 1, (
        f"Soma das frotas one-hot fora de [0,1]: max={soma_frotas.max()}"
    )
    print("  OK frota_* (4 one-hot): 0 nulls, soma <= 1 (LeTourneau como referencia)")

    # tipo_caminhao: 0/1, 0 nulls
    tipo = df.get_column("tipo_caminhao")
    assert tipo.null_count() == 0
    assert tipo.min() >= 0 and tipo.max() <= 1
    print(f"  OK tipo_caminhao: 0 nulls, 0/1, caminhoes={tipo.sum():,}")


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def salvar_v1(df: pl.DataFrame) -> None:
    DIR_FEATURES.mkdir(parents=True, exist_ok=True)
    cols_avancadas = [
        f["nome"] for f in (FEATURES_AVANCADAS_W4_PARCIAL + FEATURES_AVANCADAS_W4_FINAL)
    ]
    cols_v1 = [c for c in df.columns if c not in cols_avancadas]
    df_v1 = df.select(cols_v1)
    df_v1.write_parquet(ARQ_V1, compression="snappy")
    mb = ARQ_V1.stat().st_size / 1024 / 1024
    print(f"  {ARQ_V1.relative_to(ROOT)}  ({mb:,.1f} MB, {df_v1.shape[1]} cols)")


def salvar_v2_parcial(df: pl.DataFrame) -> None:
    cols_finais = [f["nome"] for f in FEATURES_AVANCADAS_W4_FINAL]
    cols_v2parcial = [c for c in df.columns if c not in cols_finais]
    df_v2p = df.select(cols_v2parcial)
    df_v2p.write_parquet(ARQ_V2_PARCIAL, compression="snappy")
    mb = ARQ_V2_PARCIAL.stat().st_size / 1024 / 1024
    print(f"  {ARQ_V2_PARCIAL.relative_to(ROOT)}  ({mb:,.1f} MB, {df_v2p.shape[1]} cols)")


def salvar_v2(df: pl.DataFrame) -> None:
    df.write_parquet(ARQ_V2, compression="snappy")
    mb = ARQ_V2.stat().st_size / 1024 / 1024
    print(f"  {ARQ_V2.relative_to(ROOT)}  ({mb:,.1f} MB, {df.shape[1]} cols)")


def salvar_documentacao() -> None:
    ARQ_DOC_FEATURES.parent.mkdir(parents=True, exist_ok=True)
    doc = pl.DataFrame(FEATURES_DEFINIDAS)
    doc.write_csv(ARQ_DOC_FEATURES)
    print(f"  {ARQ_DOC_FEATURES.relative_to(ROOT)} ({doc.height} features documentadas)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Feature engineering (W3 basicas + W4 completo) ===")

    telemetria, apontamentos = carregar()
    top_alarmes = identificar_top_alarmes(telemetria)

    df = criar_features_temporais(telemetria)
    df = criar_feature_valor_disponivel(df)
    df = criar_features_rolling(df)
    df = criar_features_recencia(df)
    df = criar_feature_estado_pre_evento(df, apontamentos)
    df = criar_features_regimais(df, top_alarmes)
    df = criar_features_operador(df)
    df = criar_feature_regra_negocio(df)
    df = criar_features_encoding(df)

    validar(df)

    print("\nSalvando outputs")
    salvar_v1(df)
    salvar_v2_parcial(df)
    salvar_v2(df)
    salvar_documentacao()

    print(f"\n[OK] Matriz v2 final gerada. Total: {N_FEATURES_TOTAL} features documentadas.")
    print(f"     Shape v2.parquet: {df.shape[0]:,} linhas x {df.shape[1]} colunas")
    print("\nProximas etapas de W4 (separadas):")
    print("  - Fig Extra C: cadeia de eventos CA65924 (Obs 2.3)")
    print("  - Construir target y=1 se DG em [+0, +4h] (CM 3.3)")
    print("  - Sensibilidade janela 2h/4h/8h + Fig 7")
    print("  - 06_split.py: jan-abr / mai / jun + Fig 8")


if __name__ == "__main__":
    main()
