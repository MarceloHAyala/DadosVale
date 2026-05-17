"""
05_features.py - Feature engineering basica (W3).

Cria 5 features basicas a partir do dataset limpo (saida do 03_limpeza.py),
documenta cada uma em formato CM 3.2 e salva matriz v1 para uso em W4-W7.

Features adicionadas (5):
  - hora_dia       (Int8, 0-23)    extracao de Data_Evento.dt.hour()
  - dia_semana     (Int8, 1-7)     extracao de Data_Evento.dt.weekday()
  - turno          (String)        Diurno / Noturno baseado em Inicio_Turno
  - mes            (Int8, 1-6)     extracao de Data_Evento.dt.month()
  - valor_disponivel (Bool)        Valor IS NOT NULL (captura sinal binario
                                   'alarme com medicao numerica vs sem')

Decisoes adotadas em W3 (registradas em PLANEJAMENTO.md e
controle_alteracoes.md):
  - Encoding categorico (Tag/Frota/Tipo/Classe/Operador): adiado para W4
  - Rolling windows, recencia, operador, regra de negocio: W4
  - estado_pre_evento (join com apontamentos): W4 apos Obs 2.7
  - Familia regimal (razao vs baseline proprio): W4 apos Obs 2.6

Entradas:
  - Projeto/dados/intermediarios/telemetria_limpa.parquet (~545k linhas)

Saidas:
  - Projeto/dados/features/v1.parquet               (matriz com 5 features)
  - Projeto/relatorio/tabelas/documentacao_features.csv (CM 3.2)

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
DIR_FEATURES = ROOT / "dados" / "features"
ARQ_FEATURES_OUT = DIR_FEATURES / "v1.parquet"
ARQ_DOC_FEATURES = ROOT / "relatorio" / "tabelas" / "documentacao_features.csv"

# ---------------------------------------------------------------------------
# Expectativas
# ---------------------------------------------------------------------------
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
VALOR_NULLS_ESPERADOS = 237_443   # validado em W3
N_FEATURES_NOVAS = 5

# Features definidas (uma linha por feature na documentacao)
FEATURES_DEFINIDAS = [
    {
        "nome": "hora_dia",
        "tipo": "Int8",
        "descricao": "Hora do dia em que o evento ocorreu (0-23)",
        "formula": "Data_Evento.dt.hour()",
        "motivacao": (
            "Q5 (W2): heatmap hora x dia revelou pico extremo de DGs em segunda "
            "as 23h; variacao de aproximadamente 3x entre hora minima e maxima. "
            "Captura padrao circadiano da operacao 24x7."
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
            "terca-quarta sao os dias mais 'frios'. Padrao operacional "
            "interpretado como 'rampa de retomada apos fim de semana'."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "turno",
        "tipo": "String",
        "descricao": "Turno operacional: 'Diurno' (Inicio_Turno=6h) ou 'Noturno' (Inicio_Turno=18h)",
        "formula": "'Diurno' if Inicio_Turno.dt.hour() == 6 else 'Noturno'",
        "motivacao": (
            "Operacao 24x7 em turnos de 12h confirmados em W1 (assert do "
            "02_correcao_tipos.py). Fig 2 (W2) mostra pequenos picos de "
            "apontamentos em 4-5h e 17-18h, consistentes com transicoes "
            "de turno."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "mes",
        "tipo": "Int8",
        "descricao": "Mes do evento (1=jan ... 6=jun de 2025)",
        "formula": "Data_Evento.dt.month()",
        "motivacao": (
            "Obs 2.6 (W2): 3 regimes temporais distintos no semestre. "
            "Anomalia A (Engine Coolant em fev-mar) e Anomalia B (Right "
            "Front Brake em jun) sao especificas de meses; captura "
            "non-stationarity estrutural."
        ),
        "semana_criada": "W3",
    },
    {
        "nome": "valor_disponivel",
        "tipo": "Bool",
        "descricao": "True se o evento possui medicao numerica (Valor IS NOT NULL); False caso contrario",
        "formula": "Valor.is_not_null()",
        "motivacao": (
            "Achado de W3 (etapa 8 do 03_limpeza.py): apos filtro de "
            "Informacional, 43.58% dos eventos relevantes nao possuem Valor "
            "numerico - sao alarmes do tipo 'Active/Inactive' sem medicao. "
            "Categoria binaria potencialmente preditiva (provavel correlacao "
            "com tipo de alarme)."
        ),
        "semana_criada": "W3",
    },
]


# ---------------------------------------------------------------------------
# [1/5] Carga
# ---------------------------------------------------------------------------
def carregar() -> pl.DataFrame:
    print(f"[1/5] Carregando {ARQ_TELEMETRIA_IN.relative_to(ROOT)}")
    if not ARQ_TELEMETRIA_IN.exists():
        raise FileNotFoundError(
            f"{ARQ_TELEMETRIA_IN} nao encontrado. Rode 03_limpeza.py primeiro."
        )
    t0 = time.time()
    df = pl.read_parquet(ARQ_TELEMETRIA_IN)
    print(
        f"  {df.shape[0]:>10,} linhas x {df.shape[1]:>2} colunas  "
        f"({time.time()-t0:.1f}s)"
    )
    assert df.shape[0] == LINHAS_ESPERADAS, (
        f"Esperado {LINHAS_ESPERADAS:,} linhas (pos filtro Informacional), "
        f"obtido {df.shape[0]:,}"
    )
    return df


# ---------------------------------------------------------------------------
# [2/5] Features temporais (hora, dia_semana, turno, mes)
# ---------------------------------------------------------------------------
def criar_features_temporais(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[2/5] Criando features temporais")

    # Validar pre-condicao: Inicio_Turno so tem 2 valores de hora (6, 18)
    horas_inicio = (
        df.select(pl.col("Inicio_Turno").dt.hour().alias("h"))
        ["h"].unique().sort().to_list()
    )
    print(f"  Inicio_Turno hours distintos: {horas_inicio}")
    assert set(horas_inicio).issubset({6, 18}), (
        f"Inicio_Turno tem horas inesperadas: {horas_inicio} (esperado subset de [6, 18])"
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

    print("  OK: hora_dia, dia_semana, mes (Int8) + turno (String)")
    return df


# ---------------------------------------------------------------------------
# [3/5] Feature derivada de missing (valor_disponivel)
# ---------------------------------------------------------------------------
def criar_feature_valor_disponivel(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[3/5] Criando feature valor_disponivel")
    df = df.with_columns(
        pl.col("Valor").is_not_null().alias("valor_disponivel")
    )

    n_true = df.filter(pl.col("valor_disponivel")).height
    n_false = df.height - n_true
    print(f"  True  (Valor disponivel): {n_true:>10,}")
    print(f"  False (Valor null):       {n_false:>10,} ({100*n_false/df.height:.2f}%)")
    return df


# ---------------------------------------------------------------------------
# [4/5] Validacao defensiva
# ---------------------------------------------------------------------------
def validar(df: pl.DataFrame) -> None:
    print("\n[4/5] Validando matriz final")

    # 1. Shape: deve ter +5 colunas
    assert df.shape[0] == LINHAS_ESPERADAS
    print(f"  OK Shape: {df.shape[0]:,} linhas x {df.shape[1]} colunas "
          f"(+{N_FEATURES_NOVAS} features)")

    # 2. DGs preservados (invariante critico)
    n_dgs = df.get_column("Is_Dont_Go").sum()
    assert n_dgs == DGS_ESPERADOS, f"DGs={n_dgs} esperado {DGS_ESPERADOS}"
    print(f"  OK DGs preservados: {n_dgs:,}")

    # 3. Sem nulls nas novas features
    for feat in ["hora_dia", "dia_semana", "turno", "mes", "valor_disponivel"]:
        n_null = df.get_column(feat).null_count()
        assert n_null == 0, f"{feat} tem {n_null} nulls (esperado 0)"
    print("  OK 0 nulls em todas as 5 features novas")

    # 4. Ranges esperados
    assert df["hora_dia"].min() >= 0 and df["hora_dia"].max() <= 23
    assert df["dia_semana"].min() >= 1 and df["dia_semana"].max() <= 7
    assert df["mes"].min() >= 1 and df["mes"].max() <= 6
    print("  OK Ranges: hora_dia in [0,23], dia_semana in [1,7], mes in [1,6]")

    # 5. turno tem exatamente 2 valores
    turnos = sorted(df["turno"].unique().to_list())
    assert turnos == ["Diurno", "Noturno"], f"turno valores: {turnos}"
    print(f"  OK turno: {turnos}")

    # 6. valor_disponivel: consistencia com Valor.null_count() do dataset original
    n_disp_true = df.filter(pl.col("valor_disponivel")).height
    n_disp_false = df.height - n_disp_true
    assert n_disp_false == VALOR_NULLS_ESPERADOS, (
        f"valor_disponivel=False count: {n_disp_false:,}, "
        f"esperado {VALOR_NULLS_ESPERADOS:,} (= nulls de Valor)"
    )
    print(f"  OK valor_disponivel.False = {n_disp_false:,} (= nulls de Valor)")

    # 7. Distribuicao por turno e mes (sanity check)
    print("\n  Distribuicao por turno:")
    print(df.group_by("turno").len().sort("turno"))
    print("\n  Distribuicao por mes:")
    print(df.group_by("mes").len().sort("mes"))


# ---------------------------------------------------------------------------
# [5/5] Persistencia
# ---------------------------------------------------------------------------
def salvar_parquet(df: pl.DataFrame) -> None:
    DIR_FEATURES.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    df.write_parquet(ARQ_FEATURES_OUT, compression="snappy")
    mb = ARQ_FEATURES_OUT.stat().st_size / 1024 / 1024
    print(f"\n  {ARQ_FEATURES_OUT.relative_to(ROOT)}  "
          f"({mb:,.1f} MB, {time.time()-t0:.1f}s)")


def salvar_documentacao() -> None:
    ARQ_DOC_FEATURES.parent.mkdir(parents=True, exist_ok=True)
    doc = pl.DataFrame(FEATURES_DEFINIDAS)
    doc.write_csv(ARQ_DOC_FEATURES)
    print(f"  {ARQ_DOC_FEATURES.relative_to(ROOT)} ({doc.height} features)")

    # Preview
    print("\n  Preview da documentacao:")
    with pl.Config(tbl_rows=10, tbl_cols=10, fmt_str_lengths=45):
        print(doc.select(["nome", "tipo", "descricao", "semana_criada"]))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Feature engineering basica (W3) ===")
    df = carregar()
    df = criar_features_temporais(df)
    df = criar_feature_valor_disponivel(df)
    validar(df)

    print("\n[5/5] Salvando outputs")
    salvar_parquet(df)
    salvar_documentacao()

    print("\n[OK] Features v1 geradas.")
    print("\nProximas etapas (W4):")
    print("  - Encoding categorico (Tag/Frota/Tipo/Classe/Operador)")
    print("  - Rolling windows 1h/4h/24h por TAG")
    print("  - Features de recencia (horas_desde_ultimo_DG)")
    print("  - Feature de operador (taxa_DG_operador_30d) - alimenta Q3")
    print("  - estado_pre_evento (join_asof com apontamentos)")
    print("  - Familia regimal (razao vs baseline proprio do alarme)")


if __name__ == "__main__":
    main()