"""
01_ingestao.py - Ingestao dos dados brutos.

Le os 6 parquets mensais de telemetria + apontamentos em
`Projeto/Alterado/Base de Dados/datasets/`, concatena a telemetria em ordem
cronologica, valida contagens e salva o consolidado em
`Projeto/dados/intermediarios/telemetria_consolidado.parquet`.

Escopo deste script: somente ingestao crua. Correcao de tipos, normalizacao
de encoding, verificacao de duplicados e estatisticas descritivas ficam em
scripts subsequentes da W1.

Os caminhos sao resolvidos via `Path(__file__).resolve().parents[1]`, ou seja,
relativos a `Projeto/`. Funciona de onde voce rodar o comando.

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/01_ingestao.py
"""
from pathlib import Path
import time

import polars as pl


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DIR_RAW = ROOT / "Alterado" / "Base de Dados" / "datasets"
DIR_INTERMEDIARIOS = ROOT / "dados" / "intermediarios"

ARQ_APONTAMENTOS = DIR_RAW / "apontamentos" / "desenvolver_apontamentos.parquet"

# Ordem cronologica explicita — sorted() alfabetico colocaria abr antes de feb.
MES_ORDEM = {"jan": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6}


def _mes_do_arquivo(caminho: Path) -> int:
    """Extrai o numero do mes a partir de nomes como 'telemetry_abr.parquet'."""
    mes = caminho.stem.split("_")[-1].lower()
    return MES_ORDEM.get(mes, 99)


ARQ_TELEMETRIA = sorted(
    (DIR_RAW / "telemetria").glob("telemetry_*.parquet"),
    key=_mes_do_arquivo,
)

# ---------------------------------------------------------------------------
# Expectativas (validacao automatica — falha cedo se algo divergir)
# ---------------------------------------------------------------------------
LINHAS_TELEMETRIA_ESPERADAS = 37_164_054
LINHAS_APONTAMENTOS_ESPERADAS = 377_907

COLUNAS_CHAVE_TELEMETRIA = {
    "Id_Eventos_Telemetria", "Data_Evento", "TAG", "Tag_Frota", "Tipo",
    "Nome_Operador_Anon", "Id_Alarme", "Alarme", "Criticidade", "Is_Dont_Go",
}
COLUNAS_CHAVE_APONTAMENTOS = {"Id", "Inicio", "Fim", "Tag", "Frota", "Tipo", "Classe"}


# ---------------------------------------------------------------------------
# Funcoes
# ---------------------------------------------------------------------------
def carregar_telemetria() -> pl.DataFrame:
    """Le os 6 parquets mensais e concatena verticalmente."""
    if not ARQ_TELEMETRIA:
        raise FileNotFoundError(
            f"Nenhum arquivo telemetry_*.parquet encontrado em {DIR_RAW / 'telemetria'}"
        )

    print(f"\n[1/4] Carregando telemetria ({len(ARQ_TELEMETRIA)} arquivos)")
    t0 = time.time()
    dataframes = []
    for caminho in ARQ_TELEMETRIA:
        df = pl.read_parquet(caminho)
        print(f"  {caminho.name:<28} {df.shape[0]:>10,} linhas")
        dataframes.append(df)
    telemetria = pl.concat(dataframes, how="vertical")
    print(f"  {'CONSOLIDADO':<28} {telemetria.shape[0]:>10,} linhas  ({time.time()-t0:.1f}s)")
    return telemetria


def carregar_apontamentos() -> pl.DataFrame:
    """Le o parquet de apontamentos."""
    if not ARQ_APONTAMENTOS.exists():
        raise FileNotFoundError(ARQ_APONTAMENTOS)

    print("\n[2/4] Carregando apontamentos")
    t0 = time.time()
    df = pl.read_parquet(ARQ_APONTAMENTOS)
    print(f"  {ARQ_APONTAMENTOS.name:<38} {df.shape[0]:>10,} linhas  ({time.time()-t0:.1f}s)")
    return df


def validar(telemetria: pl.DataFrame, apontamentos: pl.DataFrame) -> None:
    """Valida contagens e presenca das colunas-chave."""
    print("\n[3/4] Validando contagens e colunas-chave")

    assert telemetria.shape[0] == LINHAS_TELEMETRIA_ESPERADAS, (
        f"Telemetria: esperado {LINHAS_TELEMETRIA_ESPERADAS:,}, "
        f"obtido {telemetria.shape[0]:,}"
    )
    assert apontamentos.shape[0] == LINHAS_APONTAMENTOS_ESPERADAS, (
        f"Apontamentos: esperado {LINHAS_APONTAMENTOS_ESPERADAS:,}, "
        f"obtido {apontamentos.shape[0]:,}"
    )

    faltantes_tel = COLUNAS_CHAVE_TELEMETRIA - set(telemetria.columns)
    assert not faltantes_tel, f"Telemetria sem colunas-chave: {faltantes_tel}"

    faltantes_apo = COLUNAS_CHAVE_APONTAMENTOS - set(apontamentos.columns)
    assert not faltantes_apo, f"Apontamentos sem colunas-chave: {faltantes_apo}"

    print("  OK")


def resumir(telemetria: pl.DataFrame, apontamentos: pl.DataFrame) -> None:
    """Resumo final de shape, memoria e colunas."""
    print("\n=== RESUMO ===")

    mb_tel = telemetria.estimated_size("mb")
    mb_apo = apontamentos.estimated_size("mb")

    print(
        f"\nTelemetria   : {telemetria.shape[0]:>10,} linhas x {telemetria.shape[1]:>2} colunas"
        f"  ({mb_tel:>7,.0f} MB em memoria)"
    )
    print(
        f"Apontamentos : {apontamentos.shape[0]:>10,} linhas x {apontamentos.shape[1]:>2} colunas"
        f"  ({mb_apo:>7,.0f} MB em memoria)"
    )

    print("\nColunas telemetria:")
    for col, dtype in zip(telemetria.columns, telemetria.dtypes):
        print(f"  - {col:<28} {dtype}")

    print("\nColunas apontamentos:")
    for col, dtype in zip(apontamentos.columns, apontamentos.dtypes):
        print(f"  - {col:<28} {dtype}")


def salvar_consolidado(telemetria: pl.DataFrame) -> Path:
    """Persiste a telemetria concatenada para uso nas etapas seguintes."""
    DIR_INTERMEDIARIOS.mkdir(parents=True, exist_ok=True)
    destino = DIR_INTERMEDIARIOS / "telemetria_consolidado.parquet"
    print(f"\n[4/4] Salvando {destino.relative_to(ROOT)}")
    t0 = time.time()
    # snappy: compatibilidade ampla (visualizadores VSCode, DBeaver, Tad) +
    # leitura mais rapida que zstd. Tamanho final ~270MB (vs ~210MB com zstd) -
    # irrelevante porque o arquivo e gitignored.
    telemetria.write_parquet(destino, compression="snappy")
    tamanho_mb = destino.stat().st_size / 1024 / 1024
    print(f"  {tamanho_mb:,.0f} MB  ({time.time()-t0:.1f}s)")
    return destino


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Ingestao dos dados brutos ===")
    telemetria = carregar_telemetria()
    apontamentos = carregar_apontamentos()
    validar(telemetria, apontamentos)
    resumir(telemetria, apontamentos)
    salvar_consolidado(telemetria)
    print("\n[OK] Ingestao concluida.")


if __name__ == "__main__":
    main()
