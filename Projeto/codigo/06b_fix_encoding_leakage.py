"""
06b_fix_encoding_leakage.py - Fix do leakage subtil de frequency encoding (W5).

Pre-condicao obrigatoria de W5 antes de qualquer modelagem: recomputar
`tag_freq` e `operador_freq` (Familia 7 do 05_features.py) usando APENAS
o split de treino, e propagar para val/teste. Substitui as colunas
originais que haviam sido computadas sobre o dataset GLOBAL em 05_features.py
(decisao aceita em 17/05 com a limitacao explicitamente documentada).

Sem este fix, qualquer AUC-PR comparativa em W5-W7 fica tecnicamente
contaminada: `tag_freq` de um evento jan-abr embute volumes de mai-jun.

Decisoes de arquitetura (registradas em notas_metodologicas.md Secao 2):
  - Opcao A: script dedicado (este arquivo), nao embutido em 08_lightgbm.py
  - Opcao B: nova matriz canonica v3.parquet (preserva historico)
  - Opcao C: para categorias unknown no treino, tag_freq = 0 e operador_freq = 0
            (sem feature binaria `is_unknown` — analise teorica + verificacao
            empirica em W5 confirmou que a feature seria constante no treino
            e portanto inerte em single-fold; reconsiderar em W6 apos
            TimeSeriesSplit CV)

Casos de borda identificados pelo estudo de W5:
  - 2 TAGs unknown em test: CA65791 (1.394 eventos) e CA65916 (12 em val + ? test)
  - 1 TAG unknown em val: CA65916
  - 6 operadores unknown em val (154 eventos)
  - 7 operadores unknown em test (418 eventos)
  - Total: 1.812 eventos / 133 DGs em test afetados (2,55% / 2,54%)
  - Total: 166 eventos / 2 DGs em val afetados (0,21% / 0,16%)

Entradas:
  - Projeto/dados/features/v2_split.parquet (544.885 x 58 — 35 features + 3 targets + 19 originais + col split)

Saidas:
  - Projeto/dados/features/v3.parquet (544.885 x 58 — mesmas colunas,
    `tag_freq` e `operador_freq` recalculadas; input canonico de W5+)

Executar (da raiz do repositorio):
    uv run python Projeto/codigo/06b_fix_encoding_leakage.py
"""
from pathlib import Path
import time

import polars as pl


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ARQ_V2_SPLIT = ROOT / "dados" / "features" / "v2_split.parquet"
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"

# ---------------------------------------------------------------------------
# Expectativas (das sessoes anteriores)
# ---------------------------------------------------------------------------
LINHAS_ESPERADAS = 544_885
DGS_ESPERADOS = 19_962
COLUNAS_ESPERADAS = 58  # 19 originais + 35 features + 3 targets + 1 split (era 52 antes da expansao da Familia 1 em 22/05 — janelas 2h e 8h adicionadas)
N_TRAIN = 394_971
N_VAL = 78_825
N_TEST = 71_089

# Categorias unknown identificadas no estudo de W5
TAGS_UNKNOWN_VAL_ESPERADAS = {"CA65916"}
TAGS_UNKNOWN_TEST_ESPERADAS = {"CA65791", "CA65916"}
N_OPS_UNKNOWN_VAL_ESPERADO = 6
N_OPS_UNKNOWN_TEST_ESPERADO = 7


# ===========================================================================
# Etapa 1 - Carregar v2_split e validar
# ===========================================================================
def carregar() -> pl.DataFrame:
    print("Etapa 1/4 - Carregando v2_split.parquet...")
    if not ARQ_V2_SPLIT.exists():
        raise FileNotFoundError(
            f"v2_split.parquet nao encontrado em {ARQ_V2_SPLIT}. "
            "Execute 06_split.py antes."
        )

    df = pl.read_parquet(ARQ_V2_SPLIT)
    print(f"  Shape: {df.shape}")

    assert df.height == LINHAS_ESPERADAS, f"Linhas: {df.height} != {LINHAS_ESPERADAS}"
    assert df.width == COLUNAS_ESPERADAS, f"Colunas: {df.width} != {COLUNAS_ESPERADAS}"
    for col in ("TAG", "Matricula_Operador_Hash", "Is_Dont_Go", "split",
                "tag_freq", "operador_freq"):
        assert col in df.columns, f"Coluna ausente: {col}"

    # Validar contagens por split
    contagens = df.group_by("split").agg(pl.len()).sort("split")
    print(contagens)
    assert df.filter(pl.col("split") == "train").height == N_TRAIN
    assert df.filter(pl.col("split") == "val").height == N_VAL
    assert df.filter(pl.col("split") == "test").height == N_TEST

    return df


# ===========================================================================
# Etapa 2 - Identificar categorias unknown no treino
# ===========================================================================
def identificar_unknowns(df: pl.DataFrame) -> dict:
    print()
    print("Etapa 2/4 - Identificando categorias unknown no treino...")
    train = df.filter(pl.col("split") == "train")
    val = df.filter(pl.col("split") == "val")
    test = df.filter(pl.col("split") == "test")

    tags_train = set(train["TAG"].unique().to_list())
    tags_val = set(val["TAG"].unique().to_list())
    tags_test = set(test["TAG"].unique().to_list())

    ops_train = set(train["Matricula_Operador_Hash"].unique().to_list())
    ops_val = set(val["Matricula_Operador_Hash"].unique().to_list())
    ops_test = set(test["Matricula_Operador_Hash"].unique().to_list())

    tags_unknown_val = tags_val - tags_train
    tags_unknown_test = tags_test - tags_train
    tags_unknown_all = tags_unknown_val | tags_unknown_test

    ops_unknown_val = ops_val - ops_train
    ops_unknown_test = ops_test - ops_train
    ops_unknown_all = ops_unknown_val | ops_unknown_test

    print(f"  TAGs unknown:")
    print(f"    val:  {tags_unknown_val} (esperado: {TAGS_UNKNOWN_VAL_ESPERADAS})")
    print(f"    test: {tags_unknown_test} (esperado: {TAGS_UNKNOWN_TEST_ESPERADAS})")
    print(f"  Operadores unknown:")
    print(f"    val:  {len(ops_unknown_val)} (esperado: {N_OPS_UNKNOWN_VAL_ESPERADO})")
    print(f"    test: {len(ops_unknown_test)} (esperado: {N_OPS_UNKNOWN_TEST_ESPERADO})")

    # Asercoes defensivas
    assert tags_unknown_val == TAGS_UNKNOWN_VAL_ESPERADAS, (
        f"TAGs unknown em val divergem: {tags_unknown_val}"
    )
    assert tags_unknown_test == TAGS_UNKNOWN_TEST_ESPERADAS, (
        f"TAGs unknown em test divergem: {tags_unknown_test}"
    )
    assert len(ops_unknown_val) == N_OPS_UNKNOWN_VAL_ESPERADO
    assert len(ops_unknown_test) == N_OPS_UNKNOWN_TEST_ESPERADO

    return {
        "tags_train": tags_train,
        "ops_train": ops_train,
        "tags_unknown_all": tags_unknown_all,
        "ops_unknown_all": ops_unknown_all,
    }


# ===========================================================================
# Etapa 3 - Recomputar tag_freq e operador_freq sobre TREINO apenas
# ===========================================================================
def recomputar_freqs(df: pl.DataFrame, unknowns: dict) -> pl.DataFrame:
    print()
    print("Etapa 3/4 - Recomputando tag_freq e operador_freq sobre TREINO apenas...")

    train = df.filter(pl.col("split") == "train")
    n_train = train.height

    # tag_freq computada SOBRE TREINO APENAS
    tag_counts_train = (
        train.group_by("TAG")
        .agg(pl.len().alias("count_train"))
        .with_columns(
            (pl.col("count_train") / n_train).alias("tag_freq_train")
        )
    )
    print(f"  TAGs distintas no treino: {tag_counts_train.height}")
    print(f"  tag_freq_train min/max: "
          f"{tag_counts_train['tag_freq_train'].min():.6f} / "
          f"{tag_counts_train['tag_freq_train'].max():.6f}")

    # operador_freq computada SOBRE TREINO APENAS
    op_counts_train = (
        train.group_by("Matricula_Operador_Hash")
        .agg(pl.len().alias("count_train"))
        .with_columns(
            (pl.col("count_train") / n_train).alias("operador_freq_train")
        )
    )
    print(f"  Operadores distintos no treino: {op_counts_train.height}")
    print(f"  operador_freq_train min/max: "
          f"{op_counts_train['operador_freq_train'].min():.6f} / "
          f"{op_counts_train['operador_freq_train'].max():.6f}")

    # Join na matriz completa - propaga frequencias para val/teste
    # Para categorias unknown no treino, o join produz NULL -> fill com 0
    df = (
        df.join(
            tag_counts_train.select(["TAG", "tag_freq_train"]),
            on="TAG", how="left"
        )
        .join(
            op_counts_train.select([
                "Matricula_Operador_Hash", "operador_freq_train"
            ]),
            on="Matricula_Operador_Hash", how="left"
        )
        .with_columns(
            pl.col("tag_freq_train").fill_null(0.0).alias("tag_freq_new"),
            pl.col("operador_freq_train").fill_null(0.0).alias("operador_freq_new"),
        )
    )

    # Diagnostico: quantas linhas receberam 0 (categoria unknown)
    n_tag_zero = df.filter(pl.col("tag_freq_new") == 0).height
    n_op_zero = df.filter(pl.col("operador_freq_new") == 0).height
    print(f"  Linhas com tag_freq=0 (TAG unknown):      {n_tag_zero:,}")
    print(f"  Linhas com operador_freq=0 (op unknown):  {n_op_zero:,}")

    # Por split
    for split in ["train", "val", "test"]:
        sub = df.filter(pl.col("split") == split)
        n_tag_zero_s = sub.filter(pl.col("tag_freq_new") == 0).height
        n_op_zero_s = sub.filter(pl.col("operador_freq_new") == 0).height
        print(f"  [{split}]  tag_freq=0: {n_tag_zero_s:,} | operador_freq=0: {n_op_zero_s:,}")

    # No treino, NINGUEM deveria ter freq=0 (por construcao)
    assert df.filter(
        (pl.col("split") == "train") & (pl.col("tag_freq_new") == 0)
    ).height == 0, "Encontrei tag_freq=0 no TREINO — bug grave"
    assert df.filter(
        (pl.col("split") == "train") & (pl.col("operador_freq_new") == 0)
    ).height == 0, "Encontrei operador_freq=0 no TREINO — bug grave"

    # Substituir as colunas originais (sem mudar schema de v3)
    df = df.with_columns(
        pl.col("tag_freq_new").alias("tag_freq"),
        pl.col("operador_freq_new").alias("operador_freq"),
    ).drop(["tag_freq_train", "operador_freq_train", "tag_freq_new", "operador_freq_new"])

    print(f"  Shape pos-fix: {df.shape}")
    assert df.width == COLUNAS_ESPERADAS, (
        f"Schema mudou: {df.width} != {COLUNAS_ESPERADAS}"
    )

    return df


# ===========================================================================
# Etapa 4 - Persistir como v3.parquet
# ===========================================================================
def persistir(df: pl.DataFrame) -> None:
    print()
    print(f"Etapa 4/4 - Persistindo {ARQ_V3.name}...")

    df.write_parquet(ARQ_V3)
    tamanho_mb = ARQ_V3.stat().st_size / 1024 / 1024
    print(f"  Shape final: {df.shape}")
    print(f"  Tamanho:     {tamanho_mb:.1f} MB")
    print(f"  Caminho:     {ARQ_V3.relative_to(ROOT.parent)}")

    # Asercoes pos-write: re-ler e validar
    re = pl.read_parquet(ARQ_V3)
    assert re.shape == df.shape
    assert re.filter(pl.col("Is_Dont_Go") == 1).height == DGS_ESPERADOS, (
        "DGs nao preservados pos-fix"
    )

    # Comparacao numerica antes/depois (sanity check)
    print()
    print("  Sanity check: distribuicao de tag_freq pos-fix vs original")
    orig = pl.read_parquet(ARQ_V2_SPLIT)
    print(f"    Original (sobre dataset global):")
    print(f"      tag_freq      mean: {orig['tag_freq'].mean():.6f}")
    print(f"      operador_freq mean: {orig['operador_freq'].mean():.6f}")
    print(f"    Pos-fix (sobre treino apenas):")
    print(f"      tag_freq      mean: {re['tag_freq'].mean():.6f}")
    print(f"      operador_freq mean: {re['operador_freq'].mean():.6f}")
    print(f"    Diff esperado: pequeno (volumes mensais por TAG/op sao estaveis)")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    t_start = time.time()
    print("=" * 70)
    print("06b_fix_encoding_leakage.py - Fix do leakage subtil de Familia 7")
    print("=" * 70)

    df = carregar()
    unknowns = identificar_unknowns(df)
    df = recomputar_freqs(df, unknowns)
    persistir(df)

    elapsed = time.time() - t_start
    print()
    print("=" * 70)
    print(f"Concluido em {elapsed:.1f}s")
    print(f"v3.parquet pronto para uso em 07_baseline.py e 08_lightgbm.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
