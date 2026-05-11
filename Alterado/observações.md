# Observações — Comparação dos Arquivos `.xlsx` vs `.parquet`

> Análise inicial das bases em `Base de Dados/datasets/` (somente leitura, nenhum arquivo foi alterado).

---
OBS: 11/05/2026
## 📁 Pasta `apontamentos/`

| Aspecto | XLSX | PARQUET |
|---|---|---|
| Arquivo | `desenvolver_apontamentos.xlsx` | `desenvolver_apontamentos.parquet` |
| Tamanho | 13 KB | 6 MB |
| Linhas | **100** | **377.907** |
| Colunas | 7 (idênticas) | 7 (idênticas) |
| Período | 04/01 a 08/01/2025 (≈ 4 dias) | 01/01 a 30/06/2025 (6 meses) |
| Frotas únicas | 5 | 5 (as mesmas) |

**Colunas (iguais nos dois arquivos):**
`Id`, `Inicio`, `Fim`, `Tag`, `Frota`, `Tipo`, `Classe`

**Frotas presentes:** `793-D 2S`, `793-D 3S`, `793-D 4S`, `793-D 5S`, `LeTourneau L 1850`

✅ Os **100 Ids** do XLSX estão **todos contidos** no parquet — ou seja, **o XLSX é apenas uma pequena amostra de "desenvolvimento" do parquet**, que é a base completa.

---

## 📁 Pasta `telemetria/`

### XLSX — `desenvolver_dontgo.xlsx`
- 21 KB, **147 linhas**, **19 colunas**
- Período: apenas **01/01/2025**, entre 00:05 e 02:03 (≈ 2 horas)
- Distribuição: 146 eventos normais + **1 evento `Is_Dont_Go = 1`** (amostra ilustrativa de "don't go")

### PARQUETs — 6 arquivos, um por mês (jan a jun/2025)

| Arquivo | Linhas | Período |
|---|---:|---|
| `telemetry_jan.parquet` | 5.400.002 | janeiro/2025 |
| `telemetry_feb.parquet` | 5.709.935 | fevereiro/2025 |
| `telemetry_mar.parquet` | 5.688.538 | março/2025 |
| `telemetry_abr.parquet` | 6.475.045 | abril/2025 |
| `telemetry_may.parquet` | 6.036.291 | maio/2025 |
| `telemetry_jun.parquet` | 7.854.243 | junho/2025 |
| **TOTAL** | **37.164.054** | **6 meses completos** |

### Diferenças de schema entre o XLSX e os PARQUETs (telemetria)

- O XLSX tem **18 colunas em comum + 1 coluna extra: `Porte`** (que **não existe** nos parquets).
- Tipos de dados divergentes nos parquets (atenção na ingestão):
  - `Inicio_Turno` e `Fim_Turno` chegam como **texto** (`object`) em vez de `datetime`.
  - `Valor` chega como **texto** (`object`) em vez de `float64`.
- Volume de eventos `Is_Dont_Go = 1`:
  - XLSX: apenas **1 evento**.
  - PARQUET (somente janeiro): **2.581 eventos**.

**Colunas do XLSX:**
`Id_Eventos_Telemetria`, `Data_Evento`, `Inicio_Turno`, `Fim_Turno`, `Dia`, `Localidade`, `TAG`, `Tag_Frota`, `Porte`, `Tipo`, `Nome_Operador_Anon`, `Matricula_Operador_Hash`, `Id_Alarme`, `Alarme`, `Id_Criticidade`, `Criticidade`, `Valor`, `Classe`, `Is_Dont_Go`

**Colunas dos PARQUETs:** as mesmas, **exceto `Porte`**.

---

## 🎯 Resumo prático

| | XLSX | PARQUET |
|---|---|---|
| **Apontamentos** | Amostra de 100 linhas (≈ 4 dias) | Base completa: 377 mil linhas, 6 meses |
| **Telemetria** | Amostra de 147 linhas (≈ 2 horas), com 1 coluna extra (`Porte`) | Base completa: 37 milhões de linhas, particionada por mês (jan–jun/2025) |

### Conclusão
- Os arquivos **`.xlsx` são amostras de desenvolvimento/visualização** — servem para entender a estrutura dos dados e fazer protótipos rápidos no Excel.
- Os arquivos **`.parquet` são a base de dados real para análise**, em formato colunar comprimido, otimizado para grandes volumes.
- **A análise avançada deve ser feita sobre os parquets.**

### Pontos de atenção para a ingestão
1. Na telemetria, **converter** `Inicio_Turno`, `Fim_Turno` e `Valor` para os tipos corretos (datetime e numérico).
2. A coluna `Porte` **só existe no XLSX** — se for relevante, será necessário cruzar com outra fonte ou derivá-la (ex.: a partir da `Tag_Frota`).
3. Os 6 parquets de telemetria podem ser **concatenados** para formar a base completa do semestre.