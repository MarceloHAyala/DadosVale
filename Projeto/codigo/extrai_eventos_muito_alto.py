"""
extrai_eventos_muito_alto.py - Tabela de eventos CMA com NIVEL "Muito Alto".

Le `Projeto/Alterado/Base de Dados/Alarmes - Regra de Negocio.xlsx` (sheet CMA),
filtra `NIVEL == "Muito Alto"` (case-insensitive, ja que ha inconsistencia de
capitalizacao: 'Muito Alto' x 'Muito alto') e salva como CSV.

Conteudo Minimo atendido: CM 1.1 (Entendimento do Negocio - documentacao das
regras CMA com nivel critico de severidade).

Asercao: total esperado = 82 linhas (76 'Muito Alto' + 6 'Muito alto').

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/extrai_eventos_muito_alto.py
"""
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
ARQ_XLSX = (
    ROOT / "Alterado" / "Base de Dados" / "Alarmes - Regra de Negocio.xlsx"
)
DIR_TABELAS = ROOT / "relatorio" / "tabelas"
ARQ_SAIDA = DIR_TABELAS / "eventos_muito_alto.csv"

LINHAS_ESPERADAS = 82
COLUNAS_ESPERADAS = ["TIPO", "EVENTO", "SITUACAO", "QTD", "TEMPO", "NIVEL"]


def main() -> None:
    print("=== Extracao de eventos CMA com NIVEL 'Muito Alto' (CM 1.1) ===")

    if not ARQ_XLSX.exists():
        raise FileNotFoundError(f"{ARQ_XLSX} nao encontrado.")

    print(f"\n[1/4] Lendo sheet 'CMA' de {ARQ_XLSX.relative_to(ROOT)}")
    df = pl.read_excel(ARQ_XLSX, sheet_name="CMA", engine="openpyxl")
    print(f"  {df.shape[0]} linhas x {df.shape[1]} colunas")

    # Asserir colunas esperadas
    cols = df.columns
    print(f"  Colunas: {cols}")
    assert set(cols) == set(COLUNAS_ESPERADAS), (
        f"Colunas inesperadas. Esperado {COLUNAS_ESPERADAS}, obtido {cols}"
    )

    # Distribuicao de NIVEL bruto
    print("\n[2/4] Distribuicao de NIVEL no dataset bruto:")
    dist = (
        df.group_by("NIVEL")
          .agg(pl.len().alias("n"))
          .sort("n", descending=True)
    )
    print(dist)

    # Filtrar (case-insensitive) e normalizar para forma canonica
    print("\n[3/4] Filtrando NIVEL ~ 'Muito Alto' (case-insensitive)")
    df_filtrado = (
        df.filter(pl.col("NIVEL").str.to_lowercase().str.strip_chars() == "muito alto")
          .with_columns(pl.lit("Muito Alto").alias("NIVEL"))
          .select(COLUNAS_ESPERADAS)
    )

    n = df_filtrado.shape[0]
    print(f"  {n} eventos filtrados (esperado {LINHAS_ESPERADAS})")
    assert n == LINHAS_ESPERADAS, (
        f"Total inesperado: {n}, esperado {LINHAS_ESPERADAS}. "
        "Reveja a normalizacao de NIVEL."
    )

    # Salvar
    DIR_TABELAS.mkdir(parents=True, exist_ok=True)
    df_filtrado.write_csv(ARQ_SAIDA)
    print(f"\n[4/4] Salvando {ARQ_SAIDA.relative_to(ROOT)}")
    print(f"  {ARQ_SAIDA.stat().st_size / 1024:.1f} KB")

    # Preview
    print("\nPreview (5 primeiros):")
    with pl.Config(tbl_rows=5, tbl_cols=10, fmt_str_lengths=50):
        print(df_filtrado.head(5))

    # Distribuicao por TIPO dos filtrados
    print("\nDistribuicao por TIPO nos 82 eventos 'Muito Alto':")
    tipos = (
        df_filtrado.group_by("TIPO")
                   .agg(pl.len().alias("n"))
                   .with_columns((pl.col("n") / n * 100).round(2).alias("pct"))
                   .sort("n", descending=True)
    )
    print(tipos)

    print("\n[OK] Extracao concluida.")
    print(
        "\nObs metodologica: encontrada inconsistencia de capitalizacao em NIVEL "
        "(76 'Muito Alto' + 6 'Muito alto'). Normalizada no script. Mesma classe "
        "de problema dos achados W1 sobre encoding inconsistente da Vale."
    )


if __name__ == "__main__":
    main()
