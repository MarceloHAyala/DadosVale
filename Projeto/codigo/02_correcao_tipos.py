"""
02_correcao_tipos.py - Correcao de tipos pos-ingestao.

Le `Projeto/dados/intermediarios/telemetria_consolidado.parquet` e converte:
  - Inicio_Turno : String -> Datetime(us)
  - Fim_Turno    : String -> Datetime(us)
  - Valor        : String -> Float64
       . string literal "NULL" -> null real
       . virgula brasileira "85,5" -> ponto "85.5" antes do cast

Valida com 5 assercoes (total intacto, tipos corretos, zero nulls em datetimes,
237.443 nulls em Valor apos conversao, duracao do turno = 12h) e salva
`telemetria_tipada.parquet`.

Os caminhos sao resolvidos via `Path(__file__).resolve().parents[1]`, relativos
a `Projeto/`.

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/02_correcao_tipos.py
"""
from pathlib import Path
import time

import polars as pl


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DIR_INTERMEDIARIOS = ROOT / "dados" / "intermediarios"

ARQ_ENTRADA = DIR_INTERMEDIARIOS / "telemetria_consolidado.parquet"
ARQ_SAIDA = DIR_INTERMEDIARIOS / "telemetria_tipada.parquet"

# ---------------------------------------------------------------------------
# Expectativas (validacao automatica)
# ---------------------------------------------------------------------------
LINHAS_ESPERADAS = 37_164_054
NULLS_VALOR_ESPERADOS = 237_443  # strings "NULL" literais que viram null real
FORMATO_DATETIME = "%Y-%m-%d %H:%M:%S%.f"  # %.f aceita qualquer precisao fracional


# ---------------------------------------------------------------------------
# Funcoes
# ---------------------------------------------------------------------------
def carregar(caminho: Path) -> pl.DataFrame:
    print(f"\n[1/5] Carregando {caminho.relative_to(ROOT)}")
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho} nao encontrado. Rode 01_ingestao.py primeiro."
        )
    t0 = time.time()
    df = pl.read_parquet(caminho)
    print(f"  {df.shape[0]:>10,} linhas x {df.shape[1]:>2} colunas  ({time.time()-t0:.1f}s)")
    return df


def converter_datetimes(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[2/5] Convertendo Inicio_Turno e Fim_Turno para Datetime(us)")
    t0 = time.time()
    df = df.with_columns([
        pl.col("Inicio_Turno").str.to_datetime(
            format=FORMATO_DATETIME, strict=False, time_unit="us"
        ),
        pl.col("Fim_Turno").str.to_datetime(
            format=FORMATO_DATETIME, strict=False, time_unit="us"
        ),
    ])
    print(f"  OK  ({time.time()-t0:.1f}s)")
    return df


def converter_valor(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[3/5] Tratando Valor")
    print("       . string 'NULL' -> null real")
    print("       . virgula decimal BR ('85,5') -> ponto ('85.5')")
    print("       . cast Float64")
    t0 = time.time()
    df = df.with_columns(
        pl.when(pl.col("Valor") == "NULL")
          .then(None)
          .otherwise(pl.col("Valor").str.replace(",", "."))
          .cast(pl.Float64, strict=False)
          .alias("Valor")
    )
    print(f"  OK  ({time.time()-t0:.1f}s)")
    return df


def validar(df: pl.DataFrame) -> None:
    print("\n[4/5] Validando")

    # 1. Total intacto (nada foi excluido)
    assert df.shape[0] == LINHAS_ESPERADAS, (
        f"Total mudou: esperado {LINHAS_ESPERADAS:,}, obtido {df.shape[0]:,}"
    )

    # 2. Tipos corretos
    assert df.schema["Inicio_Turno"].is_temporal(), (
        f"Inicio_Turno deveria ser temporal, obtido {df.schema['Inicio_Turno']}"
    )
    assert df.schema["Fim_Turno"].is_temporal(), (
        f"Fim_Turno deveria ser temporal, obtido {df.schema['Fim_Turno']}"
    )
    assert df.schema["Valor"].is_numeric(), (
        f"Valor deveria ser numerico, obtido {df.schema['Valor']}"
    )

    # 3. Zero nulls nos datetimes
    nulls_inicio = df["Inicio_Turno"].null_count()
    nulls_fim = df["Fim_Turno"].null_count()
    assert nulls_inicio == 0, f"Inicio_Turno: {nulls_inicio:,} nulls inesperados"
    assert nulls_fim == 0, f"Fim_Turno: {nulls_fim:,} nulls inesperados"

    # 4. Nulls em Valor exatamente igual ao numero de strings "NULL" originais
    nulls_valor = df["Valor"].null_count()
    assert nulls_valor == NULLS_VALOR_ESPERADOS, (
        f"Valor: {nulls_valor:,} nulls (esperado {NULLS_VALOR_ESPERADOS:,}). "
        f"Diferenca = {nulls_valor - NULLS_VALOR_ESPERADOS:+,} - "
        f"possivel valor nao parseavel no long tail."
    )

    # 5. Sanidade do turno: Fim - Inicio deveria ser sempre 12h
    duracoes = (
        df.select((pl.col("Fim_Turno") - pl.col("Inicio_Turno")).alias("dur"))
          .unique()
          .to_series()
          .to_list()
    )
    duracoes_str = [str(d) for d in duracoes]
    if len(duracoes) == 1:
        print(f"  Duracao de turno: {duracoes_str[0]} (todos os {LINHAS_ESPERADAS:,} registros)")
    else:
        print(f"  ATENCAO: {len(duracoes)} duracoes diferentes de turno detectadas:")
        for d in duracoes_str[:10]:
            print(f"    - {d}")

    print(f"  OK - {nulls_valor:,} nulls em Valor (ex-strings 'NULL')")


def resumir(df: pl.DataFrame) -> None:
    print("\n=== RESUMO ===")
    print(f"\nShape final: {df.shape[0]:,} linhas x {df.shape[1]} colunas")
    print("\nTipos das colunas convertidas:")
    print(f"  Inicio_Turno : {df.schema['Inicio_Turno']}")
    print(f"  Fim_Turno    : {df.schema['Fim_Turno']}")
    print(f"  Valor        : {df.schema['Valor']}")

    print("\nValor (Float64) - estatisticas descritivas:")
    stats = df.select(
        pl.col("Valor").min().alias("min"),
        pl.col("Valor").max().alias("max"),
        pl.col("Valor").mean().alias("mean"),
        pl.col("Valor").median().alias("median"),
        pl.col("Valor").std().alias("std"),
        pl.col("Valor").null_count().alias("nulls"),
    )
    print(stats)


def salvar(df: pl.DataFrame) -> Path:
    DIR_INTERMEDIARIOS.mkdir(parents=True, exist_ok=True)
    print(f"\n[5/5] Salvando {ARQ_SAIDA.relative_to(ROOT)}")
    t0 = time.time()
    df.write_parquet(ARQ_SAIDA, compression="snappy")
    tamanho_mb = ARQ_SAIDA.stat().st_size / 1024 / 1024
    print(f"  {tamanho_mb:,.0f} MB  ({time.time()-t0:.1f}s)")
    return ARQ_SAIDA


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Correcao de tipos pos-ingestao ===")
    df = carregar(ARQ_ENTRADA)
    df = converter_datetimes(df)
    df = converter_valor(df)
    validar(df)
    resumir(df)
    salvar(df)
    print("\n[OK] Conversao concluida.")
    print("Registro metodologico em Projeto/relatorio/controle_alteracoes.md")


if __name__ == "__main__":
    main()
