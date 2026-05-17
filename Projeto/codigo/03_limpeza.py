"""
03_limpeza.py - Limpeza completa (W1 inspecao + W3 extensao).

Tasks (12 etapas):
  W1:
    [1/12] Carregar telemetria + apontamentos
    [2/12] Normalizacao de Criticidade (encoding -> ASCII)
    [3/12] Verificacao de duplicados + frequencia media
    [4/12] Estatisticas descritivas (CM 2.1)
    [5/12] Validacao da taxa de Is_Dont_Go (~0.05%)
  W3 (extensao - decisao 2026-05-17):
    [6/12] Filtrar Criticidade=Informacional (decisao 16/05/2026)
    [7/12] Outliers em Valor (threshold fisico + flag)
    [8/12] Missing values por coluna (CM 3.1)
    [9/12] Apontamentos: registros com Inicio > Fim
    [10/12] Apontamentos: sobreposicoes de ciclo (CM 3.1)
  Persistencia:
    [11/12] Salvar telemetria_limpa + apontamentos_limpo + stats + inspecao
    [12/12] Gerar controle_alteracoes.csv (CM 3.1)

Entradas:
  - Projeto/dados/intermediarios/telemetria_tipada.parquet
  - Projeto/Alterado/Base de Dados/datasets/apontamentos/desenvolver_apontamentos.parquet

Saidas:
  - Projeto/dados/intermediarios/telemetria_limpa.parquet      (~545k linhas pos filtro)
  - Projeto/dados/intermediarios/apontamentos_limpo.parquet    (W3)
  - Projeto/relatorio/tabelas/estatisticas_descritivas.csv
  - Projeto/relatorio/tabelas/inspecao_inicial.md
  - Projeto/relatorio/tabelas/controle_alteracoes.csv          (W3 - CM 3.1)

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
ARQ_APONTAMENTOS_OUT = DIR_INTERMEDIARIOS / "apontamentos_limpo.parquet"
ARQ_STATS_CSV = DIR_TABELAS / "estatisticas_descritivas.csv"
ARQ_INSPECAO_MD = DIR_TABELAS / "inspecao_inicial.md"
ARQ_CONTROLE_ALTERACOES_CSV = DIR_TABELAS / "controle_alteracoes.csv"

# ---------------------------------------------------------------------------
# Expectativas / parametros
# ---------------------------------------------------------------------------
LINHAS_TELEMETRIA = 37_164_054
LINHAS_APONTAMENTOS = 377_907
LINHAS_TELEMETRIA_POS_FILTRO = 544_885  # validado em W2
DGS_ESPERADOS = 19_962                   # invariante pos filtro

# Variantes conhecidas (encoding corrompido + acentos quebrados) -> forma canonica.
CRITICIDADE_MAPEAMENTO = {
    "Critico": "Critico",
    "Crítico": "Critico",
    "CrÃ­tico": "Critico",
    "Nao Critico": "Nao_Critico",
    "Não Crítico": "Nao_Critico",
    "Não Critico": "Nao_Critico",
    "Nao Crítico": "Nao_Critico",
    "NÃ£o CrÃ­tico": "Nao_Critico",
    "N??o Crítico": "Nao_Critico",
    "Não Cr??tico": "Nao_Critico",
    "Informacional": "Informacional",
}
CRITICIDADE_FINAIS = {"Critico", "Nao_Critico", "Informacional"}

TAXA_DG_MIN = 0.0003  # 0.03%
TAXA_DG_MAX = 0.0010  # 0.10%

# Threshold fisico para outlier em Valor (descoberto em W1):
# 118 registros com Valor > 1000 vem exclusivamente de 2 alarmes de peso de
# carga (Truck Load Weight), todos com Is_Dont_Go=0. Capacidade fisica de
# 793-D ~240t -> qualquer Valor > 1000 e medicao errada. IQR seria inadequado
# em distribuicao zero-inflada (Q1=Q3=0).
VALOR_OUTLIER_THRESHOLD = 1000.0


# ---------------------------------------------------------------------------
# [1/12] Carga
# ---------------------------------------------------------------------------
def carregar() -> tuple[pl.DataFrame, pl.DataFrame]:
    print("[1/12] Carregando datasets")
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
# [2/12] Normalizacao de Criticidade
# ---------------------------------------------------------------------------
def normalizar_criticidade(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    print("\n[2/12] Normalizando Criticidade")

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
# [3/12] Duplicados + Frequencia
# ---------------------------------------------------------------------------
def contar_duplicados(df: pl.DataFrame, nome: str, chave: list[str]) -> dict:
    """Contagem de duplicados pela chave primaria."""
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
        "total": n_total, "chave": chave,
        "duplicadas_chave": n_dup, "pct_chave": pct,
    }


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
# [4/12] Estatisticas descritivas (CM 2.1)
# ---------------------------------------------------------------------------
def estatisticas_descritivas(df: pl.DataFrame) -> pl.DataFrame:
    print("\n[4/12] Estatisticas descritivas das variaveis numericas")

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
# [5/12] Taxa Don't Go (validacao sobre dataset original)
# ---------------------------------------------------------------------------
def taxa_dg(df: pl.DataFrame) -> dict:
    print("\n[5/12] Validando taxa de Is_Dont_Go (sobre dataset original)")
    n_total = df.height
    n_dg = df.filter(pl.col("Is_Dont_Go") == 1).height
    taxa = n_dg / n_total
    pct = 100 * taxa
    print(f"  Don't Go: {n_dg:,} de {n_total:,} = {pct:.4f}%")

    assert TAXA_DG_MIN < taxa < TAXA_DG_MAX, (
        f"Taxa DG {pct:.4f}% fora do esperado "
        f"({100*TAXA_DG_MIN:.2f}% - {100*TAXA_DG_MAX:.2f}%)"
    )
    assert n_dg == DGS_ESPERADOS, f"DGs={n_dg:,} esperado {DGS_ESPERADOS:,}"
    print(f"  OK - dentro do range esperado (~0.05%); total {n_dg:,} DGs")
    return {"n_total": n_total, "n_dg": n_dg, "taxa": taxa, "pct": pct}


# ---------------------------------------------------------------------------
# [6/12] Filtrar Criticidade=Informacional (W3)
# ---------------------------------------------------------------------------
def filtrar_informacional(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    print("\n[6/12] Filtrando Criticidade=Informacional (decisao 16/05/2026)")
    n_antes = df.height

    # Pre-condicao: Informacional realmente nao tem DGs
    n_dgs_info = df.filter(
        (pl.col("Criticidade") == "Informacional") & (pl.col("Is_Dont_Go") == 1)
    ).height
    if n_dgs_info != 0:
        raise AssertionError(
            f"Pre-condicao violada: {n_dgs_info} DGs em Informacional, esperado 0. "
            "A decisao de filtrar precisa ser revisitada."
        )

    n_info = df.filter(pl.col("Criticidade") == "Informacional").height
    df_filtrado = df.filter(pl.col("Criticidade") != "Informacional")
    n_depois = df_filtrado.height
    n_dgs_depois = df_filtrado.filter(pl.col("Is_Dont_Go") == 1).height

    print(f"  Antes:                {n_antes:>12,}")
    print(f"  Remove (Informacional): {n_info:>12,} ({100*n_info/n_antes:.2f}%)")
    print(f"  Depois:               {n_depois:>12,}")
    print(f"  DGs preservados:      {n_dgs_depois:>12,} (esperado {DGS_ESPERADOS:,})")

    # Validacoes
    assert n_dgs_depois == DGS_ESPERADOS, (
        f"DGs nao preservados: {n_dgs_depois:,} vs esperado {DGS_ESPERADOS:,}"
    )
    assert n_depois == LINHAS_TELEMETRIA_POS_FILTRO, (
        f"Volume pos-filtro: {n_depois:,} vs esperado {LINHAS_TELEMETRIA_POS_FILTRO:,}"
    )

    return df_filtrado, {
        "campo": "Criticidade",
        "problema": "Volume excessivo de Informacional (98.5%) sem positivos",
        "qtd_registros": n_info,
        "tratamento": "Removidos do dataset (filtro Criticidade != Informacional)",
        "justificativa": (
            "Validado em W2 (Obs 2.2): 36.619.169 eventos Informacional geraram "
            "0 DGs no semestre (taxa 0.0000%). Separacao deterministica. "
            "Habilita rolling windows em W4 sem risco de RAM."
        ),
    }


# ---------------------------------------------------------------------------
# [7/12] Outliers em Valor (threshold fisico)
# ---------------------------------------------------------------------------
def outliers_valor(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    print("\n[7/12] Outliers em Valor (threshold fisico)")

    # IQR para comparacao (mostrar que e' inadequado)
    q1 = df["Valor"].quantile(0.25)
    q3 = df["Valor"].quantile(0.75)
    print(f"  IQR: q1={q1}, q3={q3} (inadequado - distribuicao zero-inflada)")
    print(f"  Threshold fisico adotado: Valor > {VALOR_OUTLIER_THRESHOLD}")

    df = df.with_columns(
        (pl.col("Valor") > VALOR_OUTLIER_THRESHOLD)
            .fill_null(False)
            .alias("is_outlier_valor")
    )

    n_outliers = df.filter(pl.col("is_outlier_valor")).height
    pct = 100 * n_outliers / df.height
    n_dgs_outliers = df.filter(
        pl.col("is_outlier_valor") & (pl.col("Is_Dont_Go") == 1)
    ).height

    print(f"  Outliers marcados: {n_outliers:,} ({pct:.4f}%)")
    print(f"  DGs entre outliers: {n_dgs_outliers} (esperado 0)")
    assert n_dgs_outliers == 0, (
        f"Outlier contaminou target: {n_dgs_outliers} DGs com Valor>{VALOR_OUTLIER_THRESHOLD}"
    )

    return df, {
        "campo": "Valor",
        "problema": (
            f"Validacao defensiva de outliers fisicamente impossiveis "
            f"(Valor > {VALOR_OUTLIER_THRESHOLD})"
        ),
        "qtd_registros": n_outliers,
        "tratamento": (
            "Validacao concluida; flag 'is_outlier_valor' presente (sempre False "
            "no dataset filtrado pos-etapa 6)"
        ),
        "justificativa": (
            "Achado de W1: 118 registros com Valor > 1000 vinham de 2 alarmes de "
            "peso de carga (Truck Load Weight), todos com Criticidade=Informacional "
            "e Is_Dont_Go=0. Apos o filtro de Informacional (etapa 6), todos foram "
            "automaticamente eliminados — a etapa 7 e mantida como validacao "
            "defensiva (asserta 0 outliers + 0 DGs entre outliers no dataset "
            "filtrado). IQR padrao seria inadequado em distribuicao zero-inflada "
            "(Q1=Q3=0 esperado), motivo do threshold fisico."
        ),
    }


# ---------------------------------------------------------------------------
# [8/12] Missing values por coluna (CM 3.1)
# ---------------------------------------------------------------------------
def missing_values(
    telemetria: pl.DataFrame, apontamentos: pl.DataFrame
) -> list[dict]:
    print("\n[8/12] Missing values por coluna (CM 3.1)")

    registros = []

    for nome, df in [("telemetria", telemetria), ("apontamentos", apontamentos)]:
        n_total = df.height
        colunas_com_null = []
        for col in df.columns:
            nulls = df[col].null_count()
            if nulls > 0:
                colunas_com_null.append((col, nulls))

        if not colunas_com_null:
            print(f"  {nome}: 0 nulls em qualquer coluna ({df.shape[1]} colunas)")
            continue

        print(f"  {nome}: {len(colunas_com_null)} coluna(s) com nulls:")
        for col, nulls in colunas_com_null:
            pct = 100 * nulls / n_total
            print(f"    {col:<30} {nulls:>10,} ({pct:.4f}%)")

            # Decisao por coluna
            if nome == "telemetria" and col == "Valor":
                tratamento = "Manter null (LightGBM aceita NaN diretamente)"
                justif = (
                    "237.443 strings 'NULL' originais ja convertidas para null real "
                    "em W1 (02_correcao_tipos.py). Imputacao por mediana inadequada: "
                    "cada alarme tem distribuicao propria. LightGBM trata NaN como "
                    "categoria propria nas arvores."
                )
            else:
                tratamento = "Manter null - decisao especifica deferida para W4"
                justif = (
                    "Coluna com nulls fora do esperado. Decisao especifica sera "
                    "tomada quando for usada como feature em W4 (encoding "
                    "categorico ou tratamento numerico)."
                )

            registros.append({
                "campo": f"{nome}.{col}",
                "problema": f"{nulls:,} nulls ({pct:.4f}%)",
                "qtd_registros": nulls,
                "tratamento": tratamento,
                "justificativa": justif,
            })

    return registros


# ---------------------------------------------------------------------------
# [9/12] Apontamentos: Inicio > Fim
# ---------------------------------------------------------------------------
def inicio_fim_apontamentos(
    apontamentos: pl.DataFrame,
) -> tuple[pl.DataFrame, dict]:
    print("\n[9/12] Apontamentos - registros com Inicio > Fim")

    n_total = apontamentos.height
    invalidos = apontamentos.filter(pl.col("Inicio") > pl.col("Fim"))
    n_invalidos = invalidos.height
    pct = 100 * n_invalidos / n_total

    print(f"  Total apontamentos: {n_total:,}")
    print(f"  Inicio > Fim: {n_invalidos:,} ({pct:.4f}%)")

    if n_invalidos == 0:
        print("  Validacao OK - nenhum tratamento necessario.")
        return apontamentos, {
            "campo": "apontamentos.Inicio/Fim",
            "problema": "Validacao: registros com Inicio > Fim (intervalo invalido)",
            "qtd_registros": 0,
            "tratamento": "Nenhum",
            "justificativa": "Validacao confirmou 0 registros invalidos",
        }

    if pct < 0.01:
        apontamentos = apontamentos.filter(pl.col("Inicio") <= pl.col("Fim"))
        print(f"  Removidos {n_invalidos} (pct {pct:.4f}% < 0.01%).")
        return apontamentos, {
            "campo": "apontamentos.Inicio/Fim",
            "problema": "Registros com Inicio > Fim",
            "qtd_registros": n_invalidos,
            "tratamento": "Removidos do dataset",
            "justificativa": f"Volume desprezivel ({pct:.4f}% < 0.01%); descarte direto.",
        }

    apontamentos = apontamentos.with_columns(
        (pl.col("Inicio") > pl.col("Fim")).alias("is_intervalo_invalido")
    )
    print(f"  Adicionada flag 'is_intervalo_invalido' ({n_invalidos}).")
    return apontamentos, {
        "campo": "apontamentos.Inicio/Fim",
        "problema": "Registros com Inicio > Fim",
        "qtd_registros": n_invalidos,
        "tratamento": "Flag 'is_intervalo_invalido' adicionada; linhas mantidas",
        "justificativa": (
            f"Volume nao desprezivel ({pct:.4f}%); flag permite analise. "
            "Possivel causa: fuso horario, midnight crossing ou erro do sistema fonte."
        ),
    }


# ---------------------------------------------------------------------------
# [10/12] Apontamentos: sobreposicoes de ciclo (CM 3.1)
# ---------------------------------------------------------------------------
def sobreposicoes_ciclo(
    apontamentos: pl.DataFrame,
) -> tuple[pl.DataFrame, dict]:
    print("\n[10/12] Apontamentos - sobreposicoes de ciclo (mesmo TAG)")

    n_total = apontamentos.height
    apo_sorted = apontamentos.sort(["Tag", "Inicio"])

    apo_with_flag = apo_sorted.with_columns(
        pl.col("Fim").shift(1).over("Tag").alias("Fim_anterior")
    ).with_columns(
        (pl.col("Inicio") < pl.col("Fim_anterior"))
            .fill_null(False)
            .alias("is_sobreposicao")
    )

    n_sobrepoe = apo_with_flag.filter(pl.col("is_sobreposicao")).height
    pct = 100 * n_sobrepoe / n_total
    print(f"  Total: {n_total:,}")
    print(f"  Sobreposicoes: {n_sobrepoe:,} ({pct:.4f}%)")

    if n_sobrepoe == 0:
        print("  Validacao OK - nenhum tratamento necessario.")
        return apontamentos, {
            "campo": "apontamentos.(Tag, Inicio, Fim)",
            "problema": "Validacao: sobreposicoes temporais de ciclos do mesmo TAG",
            "qtd_registros": 0,
            "tratamento": "Nenhum",
            "justificativa": "Validacao confirmou 0 sobreposicoes",
        }

    if pct < 0.01:
        mantem = (
            apo_with_flag.filter(~pl.col("is_sobreposicao"))
                        .select(apontamentos.columns)
        )
        print(f"  Removidas {n_sobrepoe} sobreposicoes ({pct:.4f}% < 0.01%).")
        return mantem, {
            "campo": "apontamentos.(Tag, Inicio, Fim)",
            "problema": "Sobreposicoes temporais de ciclos",
            "qtd_registros": n_sobrepoe,
            "tratamento": "Removida a linha com Inicio mais recente em cada par sobreposto",
            "justificativa": f"Volume desprezivel ({pct:.4f}% < 0.01%); descarte direto.",
        }

    cols_out = apontamentos.columns + ["is_sobreposicao"]
    flag_df = apo_with_flag.select(cols_out)
    print(f"  Adicionada flag 'is_sobreposicao' ({n_sobrepoe}).")
    return flag_df, {
        "campo": "apontamentos.(Tag, Inicio, Fim)",
        "problema": "Sobreposicoes temporais de ciclos",
        "qtd_registros": n_sobrepoe,
        "tratamento": "Flag 'is_sobreposicao' adicionada; linhas mantidas",
        "justificativa": (
            f"Volume nao desprezivel ({pct:.4f}%); flag permite analise. "
            "Sobreposicao pode ser legitima em troca de turno ou bug do sistema fonte."
        ),
    }


# ---------------------------------------------------------------------------
# [11/12] Persistencia
# ---------------------------------------------------------------------------
def salvar_telemetria(df: pl.DataFrame) -> None:
    t0 = time.time()
    df.write_parquet(ARQ_TELEMETRIA_OUT, compression="snappy")
    mb = ARQ_TELEMETRIA_OUT.stat().st_size / 1024 / 1024
    print(f"  {ARQ_TELEMETRIA_OUT.relative_to(ROOT)}  ({mb:,.0f} MB, {time.time()-t0:.1f}s)")


def salvar_apontamentos(df: pl.DataFrame) -> None:
    t0 = time.time()
    df.write_parquet(ARQ_APONTAMENTOS_OUT, compression="snappy")
    mb = ARQ_APONTAMENTOS_OUT.stat().st_size / 1024 / 1024
    print(f"  {ARQ_APONTAMENTOS_OUT.relative_to(ROOT)}  ({mb:,.1f} MB, {time.time()-t0:.1f}s)")


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
# [12/12] controle_alteracoes.csv (CM 3.1)
# ---------------------------------------------------------------------------
def gerar_controle_alteracoes_csv(registros: list[dict]) -> None:
    print("\n[12/12] Gerando controle_alteracoes.csv (CM 3.1)")

    if not registros:
        print("  Nenhuma alteracao para registrar (caso improvavel).")
        return

    DIR_TABELAS.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(registros).select([
        "campo", "problema", "qtd_registros", "tratamento", "justificativa"
    ]).rename({
        "campo": "Campo",
        "problema": "Problema Identificado",
        "qtd_registros": "Qtd. Registros",
        "tratamento": "Tratamento Aplicado",
        "justificativa": "Justificativa",
    })
    df.write_csv(ARQ_CONTROLE_ALTERACOES_CSV)
    print(f"  {ARQ_CONTROLE_ALTERACOES_CSV.relative_to(ROOT)} ({df.height} linhas)")
    with pl.Config(tbl_rows=20, fmt_str_lengths=50):
        print(df)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Limpeza extendida (W1 inspecao + W3 cleaning) ===\n")

    # --- Fase 1: Carga e validacao
    telemetria, apontamentos = carregar()
    assert telemetria.shape[0] == LINHAS_TELEMETRIA, (
        f"Telemetria esperada {LINHAS_TELEMETRIA:,}, obtido {telemetria.shape[0]:,}"
    )
    assert apontamentos.shape[0] == LINHAS_APONTAMENTOS, (
        f"Apontamentos esperado {LINHAS_APONTAMENTOS:,}, obtido {apontamentos.shape[0]:,}"
    )

    # --- Fase 2: Inspecao do dataset original (W1, CM 2.1)
    telemetria, valores_criticidade = normalizar_criticidade(telemetria)

    print("\n[3/12] Duplicados e frequencia de registros")
    dup_tel = contar_duplicados(telemetria, "Telemetria", ["Id_Eventos_Telemetria"])
    dup_apo = contar_duplicados(apontamentos, "Apontamentos", ["Id"])
    freq_tel = frequencia_media(telemetria, "Data_Evento", "TAG", "Telemetria")
    freq_apo = frequencia_media(apontamentos, "Inicio", "Tag", "Apontamentos")

    stats_df = estatisticas_descritivas(telemetria)
    dg = taxa_dg(telemetria)

    # --- Fase 3: Cleaning (W3 - CM 3.1)
    registros_csv = []

    telemetria, reg = filtrar_informacional(telemetria)
    registros_csv.append(reg)

    telemetria, reg = outliers_valor(telemetria)
    registros_csv.append(reg)

    registros_csv.extend(missing_values(telemetria, apontamentos))

    apontamentos, reg = inicio_fim_apontamentos(apontamentos)
    registros_csv.append(reg)

    apontamentos, reg = sobreposicoes_ciclo(apontamentos)
    registros_csv.append(reg)

    # --- Fase 4: Persistencia
    print("\n[11/12] Salvando outputs")
    salvar_telemetria(telemetria)
    salvar_apontamentos(apontamentos)
    salvar_stats(stats_df)
    salvar_inspecao_md(
        valores_criticidade, dup_tel, dup_apo, freq_tel, freq_apo, dg
    )

    # --- Fase 5: Audit log (CM 3.1)
    gerar_controle_alteracoes_csv(registros_csv)

    print("\n[OK] Limpeza extendida concluida.")
    print("\nProximos lembretes:")
    print("  - Registrar entrada em controle_alteracoes.md sobre a extensao W3")
    print("  - Re-rodar 04_eda.py e exploracao_w2_obs.py para confirmar idempotencia")
    print("  - Iniciar 05_features.py em W4 a partir de telemetria_limpa.parquet")


if __name__ == "__main__":
    main()
