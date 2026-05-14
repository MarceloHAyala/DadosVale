"""
03_limpeza.py - Encerramento de W1 (CM 2.1): normalizacao + inspecao inicial.

Tasks consolidadas:
  - Normalizacao de `Criticidade` (encoding corrompido -> ASCII limpo)
  - Verificacao de duplicados (telemetria + apontamentos)
  - Frequencia media de registros (dia, hora, equipamento)
  - Estatisticas descritivas das variaveis numericas (CM 2.1)
  - Validacao da taxa de Is_Dont_Go (~0.05% esperado)

Entradas:
  - Projeto/dados/intermediarios/telemetria_tipada.parquet   (saida de 02)
  - Projeto/Alterado/Base de Dados/datasets/apontamentos/...

Saidas:
  - Projeto/dados/intermediarios/telemetria_limpa.parquet
  - Projeto/relatorio/tabelas/estatisticas_descritivas.csv
  - Projeto/relatorio/tabelas/inspecao_inicial.md

Executar:
    uv run python Projeto/codigo/03_limpeza.py
"""
from pathlib import Path
import time

import polars as pl


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DIR_INTERMEDIARIOS = ROOT / "dados" / "intermediarios"
DIR_TABELAS = ROOT / "relatorio" / "tabelas"

ARQ_TELEMETRIA_IN = DIR_INTERMEDIARIOS / "telemetria_tipada.parquet"
ARQ_APONTAMENTOS_IN = (
    ROOT / "Alterado" / "Base de Dados" / "datasets" / "apontamentos"
    / "desenvolver_apontamentos.parquet"
)
ARQ_TELEMETRIA_OUT = DIR_INTERMEDIARIOS / "telemetria_limpa.parquet"
ARQ_STATS_CSV = DIR_TABELAS / "estatisticas_descritivas.csv"
ARQ_INSPECAO_MD = DIR_TABELAS / "inspecao_inicial.md"

# ---------------------------------------------------------------------------
# Expectativas / mapeamento de normalizacao
# ---------------------------------------------------------------------------
LINHAS_TELEMETRIA = 37_164_054
LINHAS_APONTAMENTOS = 377_907

# Variantes conhecidas (encoding corrompido + acentos quebrados) -> forma canonica.
# Se aparecer valor novo, o script erra com a lista para atualizar este dict.
CRITICIDADE_MAPEAMENTO = {
    # Variantes de "Critico" - aparecem SEM acento no source (anomalia investigada)
    "Critico": "Critico",
    "Crítico": "Critico",
    "CrÃ­tico": "Critico",
    # Variantes de "Nao Critico" - aparecem COM acento no source
    "Nao Critico": "Nao_Critico",
    "Não Crítico": "Nao_Critico",
    "Não Critico": "Nao_Critico",
    "Nao Crítico": "Nao_Critico",
    "NÃ£o CrÃ­tico": "Nao_Critico",
    # Falhas parciais de encoding (caracteres substituidos por ??):
    "N??o Crítico": "Nao_Critico",   # "ã" virou "??"
    "Não Cr??tico": "Nao_Critico",   # "í" virou "??"
    # Informacional (sem acentos, intacto)
    "Informacional": "Informacional",
}
CRITICIDADE_FINAIS = {"Critico", "Nao_Critico", "Informacional"}

TAXA_DG_MIN = 0.0003  # 0.03%
TAXA_DG_MAX = 0.0010  # 0.10%


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def carregar() -> tuple[pl.DataFrame, pl.DataFrame]:
    print("[1/6] Carregando datasets")
    if not ARQ_TELEMETRIA_IN.exists():
        raise FileNotFoundError(
            f"{ARQ_TELEMETRIA_IN} nao encontrado. Rode 02_correcao_tipos.py primeiro."
        )
    t0 = time.time()
    telemetria = pl.read_parquet(ARQ_TELEMETRIA_IN)
    apontamentos = pl.read_parquet(ARQ_APONTAMENTOS_IN)
    print(
        f"  Telemetria   : {telemetria.shape[0]:>10,} linhas  ({time.time()-t0:.1f}s)\n"
        f"  Apontamentos : {apontamentos.shape[0]:>10,} linhas"
    )
    return telemetria, apontamentos


# ---------------------------------------------------------------------------
# Normalizacao de Criticidade
# ---------------------------------------------------------------------------
def normalizar_criticidade(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    print("\n[2/6] Normalizando Criticidade")

    contagens = (
        df.group_by("Criticidade")
          .len()
          .sort("len", descending=True)
    )
    valores_originais = {
        row["Criticidade"]: row["len"] for row in contagens.to_dicts()
    }
    print(f"  Valores distintos encontrados: {len(valores_originais)}")
    for valor, n in valores_originais.items():
        repr_valor = repr(valor)
        print(f"    {repr_valor:<35} {n:>10,}")

    desconhecidos = set(valores_originais.keys()) - set(CRITICIDADE_MAPEAMENTO.keys())
    if desconhecidos:
        raise ValueError(
            f"Valores nao mapeados em Criticidade: {desconhecidos}.\n"
            f"Atualize CRITICIDADE_MAPEAMENTO no script."
        )

    df = df.with_columns(
        pl.col("Criticidade").replace(CRITICIDADE_MAPEAMENTO)
    )

    valores_finais = set(df["Criticidade"].unique().to_list())
    extras = valores_finais - CRITICIDADE_FINAIS
    assert not extras, f"Valores finais inesperados em Criticidade: {extras}"
    print(f"  OK - normalizado para {sorted(valores_finais)}")

    return df, valores_originais


# ---------------------------------------------------------------------------
# Duplicados
# ---------------------------------------------------------------------------
def contar_duplicados(df: pl.DataFrame, nome: str, chave: list[str]) -> dict:
    """Contagem de duplicados pela chave primaria.

    Nao fazemos dedup full-row pois e prohibitivo em 37M x 18 cols (hash de
    todas as colunas com mistura de String/Datetime/Float) e nao agrega valor
    em dados de telemetria (linhas com mesmo timestamp + valor sao raras).
    O que importa metodologicamente: chave primaria unica?
    """
    print(f"\n  Duplicatas - {nome} (chave={chave}):")
    n_total = df.height
    t0 = time.time()
    n_unicas = df.select(chave).n_unique()
    n_dup = n_total - n_unicas
    pct = 100 * n_dup / n_total
    print(
        f"    Total: {n_total:,}  |  Chaves unicas: {n_unicas:,}  |  "
        f"Duplicadas: {n_dup:,} ({pct:.4f}%)  ({time.time()-t0:.1f}s)"
    )
    return {
        "total": n_total,
        "chave": chave,
        "duplicadas_chave": n_dup,
        "pct_chave": pct,
    }


# ---------------------------------------------------------------------------
# Frequencia media
# ---------------------------------------------------------------------------
def frequencia_media(
    df: pl.DataFrame, col_datetime: str, col_tag: str, nome: str
) -> dict:
    print(f"\n  Frequencia - {nome}:")
    n_dias = df.select(pl.col(col_datetime).dt.date()).n_unique()
    n_tags = df.select(pl.col(col_tag)).n_unique()
    total = df.height

    por_dia = total / n_dias if n_dias else 0
    por_hora = por_dia / 24
    por_tag_dia = por_dia / n_tags if n_tags else 0

    print(f"    Total registros        : {total:>12,}")
    print(f"    Dias cobertos          : {n_dias:>12}")
    print(f"    Equipamentos (TAGs)    : {n_tags:>12}")
    print(f"    Registros/dia          : {por_dia:>12,.0f}")
    print(f"    Registros/hora         : {por_hora:>12,.0f}")
    print(f"    Registros/TAG/dia      : {por_tag_dia:>12,.0f}")

    return {
        "total": total, "n_dias": n_dias, "n_tags": n_tags,
        "por_dia": por_dia, "por_hora": por_hora, "por_tag_dia": por_tag_dia,
    }


# ---------------------------------------------------------------------------
# Estatisticas descritivas (CM 2.1)
# ---------------------------------------------------------------------------
def estatisticas_descritivas(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[4/6] Estatisticas descritivas das variaveis numericas")

    colunas_numericas = [
        col for col, dtype in zip(df.columns, df.dtypes) if dtype.is_numeric()
    ]
    print(f"  Variaveis numericas: {colunas_numericas}")

    linhas = []
    n_total = df.height
    for col in colunas_numericas:
        serie = df[col]
        nulls = serie.null_count()
        pct_nulos = round(100 * nulls / n_total, 4)
        linhas.append({
            "coluna": col,
            "tipo": str(serie.dtype),
            "pct_nulos": pct_nulos,
            "min": serie.min(),
            "max": serie.max(),
            "media": round(serie.mean(), 4) if serie.mean() is not None else None,
            "mediana": serie.median(),
            "desvio_padrao": round(serie.std(), 4) if serie.std() is not None else None,
        })

    stats_df = pl.DataFrame(linhas)
    print("\n" + str(stats_df))
    return stats_df


# ---------------------------------------------------------------------------
# Taxa Don't Go
# ---------------------------------------------------------------------------
def taxa_dg(df: pl.DataFrame) -> dict:
    print("\n[5/6] Validando taxa de Is_Dont_Go")
    n_total = df.height
    n_dg = df.filter(pl.col("Is_Dont_Go") == 1).height
    taxa = n_dg / n_total
    pct = 100 * taxa
    print(f"  Don't Go: {n_dg:,} de {n_total:,} = {pct:.4f}%")

    assert TAXA_DG_MIN < taxa < TAXA_DG_MAX, (
        f"Taxa DG {pct:.4f}% fora do esperado "
        f"({100*TAXA_DG_MIN:.2f}% - {100*TAXA_DG_MAX:.2f}%)"
    )
    print("  OK - dentro do range esperado (~0.05%)")
    return {"n_total": n_total, "n_dg": n_dg, "taxa": taxa, "pct": pct}


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def salvar_telemetria(df: pl.DataFrame) -> None:
    print(f"\n[6/6] Salvando outputs")
    t0 = time.time()
    df.write_parquet(ARQ_TELEMETRIA_OUT, compression="snappy")
    mb = ARQ_TELEMETRIA_OUT.stat().st_size / 1024 / 1024
    print(f"  {ARQ_TELEMETRIA_OUT.relative_to(ROOT)}  ({mb:,.0f} MB, {time.time()-t0:.1f}s)")


def salvar_stats(stats_df: pl.DataFrame) -> None:
    DIR_TABELAS.mkdir(parents=True, exist_ok=True)
    stats_df.write_csv(ARQ_STATS_CSV)
    print(f"  {ARQ_STATS_CSV.relative_to(ROOT)}")


def salvar_inspecao_md(
    valores_criticidade: dict,
    dup_tel: dict, dup_apo: dict,
    freq_tel: dict, freq_apo: dict,
    dg: dict,
) -> None:
    DIR_TABELAS.mkdir(parents=True, exist_ok=True)
    linhas_crit = "\n".join(
        f"| `{repr(v)[1:-1]}` | {n:,} |"
        for v, n in valores_criticidade.items()
    )
    conteudo = f"""# Inspecao Inicial dos Dados (CM 2.1)

Gerado por `Projeto/codigo/03_limpeza.py`. Consolida normalizacao da Criticidade,
verificacao de duplicados, frequencia de registros e taxa de Is_Dont_Go.

## 1. Normalizacao de Criticidade

Valores brutos encontrados antes da normalizacao:

| Valor original | Quantidade |
|---|---|
{linhas_crit}

Apos normalizacao todos os valores foram mapeados para: `Critico`, `Nao_Critico`, `Informacional`.

## 2. Duplicados

Verificacao feita pela chave primaria de cada dataset (dedup full-row em 37M
linhas e prohibitivo e nao agrega valor — linhas inteiramente identicas sao
praticamente impossiveis em telemetria por causa dos timestamps).

### Telemetria
- Total: **{dup_tel['total']:,}**
- Chaves unicas em {dup_tel['chave']}: **{dup_tel['total'] - dup_tel['duplicadas_chave']:,}**
- Duplicadas por chave: **{dup_tel['duplicadas_chave']:,}** ({dup_tel['pct_chave']:.4f}%)

### Apontamentos
- Total: **{dup_apo['total']:,}**
- Chaves unicas em {dup_apo['chave']}: **{dup_apo['total'] - dup_apo['duplicadas_chave']:,}**
- Duplicadas por chave: **{dup_apo['duplicadas_chave']:,}** ({dup_apo['pct_chave']:.4f}%)

## 3. Frequencia media de registros

### Telemetria
- Total: **{freq_tel['total']:,}** registros
- Dias cobertos: **{freq_tel['n_dias']}**
- Equipamentos (TAGs): **{freq_tel['n_tags']}**
- Registros/dia: **{freq_tel['por_dia']:,.0f}**
- Registros/hora: **{freq_tel['por_hora']:,.0f}**
- Registros/TAG/dia: **{freq_tel['por_tag_dia']:,.0f}**

### Apontamentos
- Total: **{freq_apo['total']:,}** registros
- Dias cobertos: **{freq_apo['n_dias']}**
- Equipamentos (TAGs): **{freq_apo['n_tags']}**
- Registros/dia: **{freq_apo['por_dia']:,.0f}**
- Registros/hora: **{freq_apo['por_hora']:,.0f}**
- Registros/TAG/dia: **{freq_apo['por_tag_dia']:,.0f}**

## 4. Taxa Is_Dont_Go

- Total: **{dg['n_total']:,}**
- Don't Go (positivos): **{dg['n_dg']:,}**
- Taxa: **{dg['pct']:.4f}%** (range esperado: 0.03% - 0.10%)
"""
    ARQ_INSPECAO_MD.write_text(conteudo, encoding="utf-8")
    print(f"  {ARQ_INSPECAO_MD.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Limpeza + Inspecao Inicial (W1 / CM 2.1) ===\n")

    telemetria, apontamentos = carregar()
    assert telemetria.shape[0] == LINHAS_TELEMETRIA
    assert apontamentos.shape[0] == LINHAS_APONTAMENTOS

    telemetria, valores_criticidade = normalizar_criticidade(telemetria)

    print("\n[3/6] Duplicados e frequencia de registros")
    # Duplicatas - usando Id como chave natural se existir
    dup_tel = contar_duplicados(
        telemetria, "Telemetria",
        chave=["Id_Eventos_Telemetria"],
    )
    dup_apo = contar_duplicados(
        apontamentos, "Apontamentos",
        chave=["Id"],
    )
    # Frequencia
    freq_tel = frequencia_media(telemetria, "Data_Evento", "TAG", "Telemetria")
    freq_apo = frequencia_media(apontamentos, "Inicio", "Tag", "Apontamentos")

    stats_df = estatisticas_descritivas(telemetria)
    dg = taxa_dg(telemetria)

    salvar_telemetria(telemetria)
    salvar_stats(stats_df)
    salvar_inspecao_md(valores_criticidade, dup_tel, dup_apo, freq_tel, freq_apo, dg)

    print("\n[OK] Limpeza + inspecao concluidas.")
    print("\nLembrete: adicionar entrada de normalizacao de Criticidade em")
    print("  Projeto/relatorio/controle_alteracoes.md")


if __name__ == "__main__":
    main()
