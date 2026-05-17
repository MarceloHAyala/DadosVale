# Notas de Exploração Inicial dos Dados

> **Documento de referência histórica** com as anotações feitas durante a fase de descoberta do dataset (11/05/2026), antes do início formal da W1. Material relevante para a redação da seção "Entendimento do Negócio" (CM 1.1) em W8 — contém a documentação do dicionário de dados, das regras CMA e a definição canônica de `Is_Dont_Go = 1`.
>
> **Histórico:** originalmente em `Projeto/Alterado/observações.md`. Movido para `Projeto/relatorio/notas_exploracao_inicial.md` em 17/05/2026 para juntar-se aos demais artefatos analíticos.

---

## 📌 Prompt Inicial — 11/05/2026

> O arquivo `C:\Users\marcelo.ayala\Desktop\DadosVale\Estudo Guiado - Análise Avançada de Dados.pdf` contém instruções do que é esperado, primeiramente a pasta `C:\Users\marcelo.ayala\Desktop\DadosVale\Base de Dados\datasets\apontamentos` tem um arquivo .xlsx e um arquivo .parquet, a pasta `C:\Users\marcelo.ayala\Desktop\DadosVale\Base de Dados\datasets\telemetria` tem um arquivo .xlsx e varios arquivos .parquet. Qual a diferença dos arquivos .xlsx e .parquet em relação aos dados dentro deles?

---

# Observações — Comparação dos Arquivos `.xlsx` vs `.parquet`

> Análise inicial das bases em `Base de Dados/datasets/` (somente leitura, nenhum arquivo foi alterado).

---
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

---

## 📝 Observações sobre os arquivos da pasta `Base de Dados/` — 11/05/2026

> **Prompt do usuário:** *"Explique o que cada arquivo dessa pasta `C:\Users\marcelo.ayala\Desktop\DadosVale\Alterado\Base de Dados` apresenta de dados, alguns não entendi direito a função dele."*

### Estrutura da pasta

```
Base de Dados/
├── README.md
├── Dicionario_Dados.xlsx
├── Alarmes - Regra de Negocio.xlsx
└── datasets/
    ├── apontamentos/   (.xlsx + .parquet)
    └── telemetria/     (.xlsx + 6× .parquet)
```

### 📄 `README.md`
Texto curto que descreve o conteúdo da pasta e traz um **resumo dos volumes**:
- Apontamentos: 377.907 registros (jan a jun/2025).
- Telemetria: 37.164.054 registros (jan a jun/2025).

É um "guia rápido" da pasta.

---

### 📘 `Dicionario_Dados.xlsx` — Dicionário de Dados
Arquivo de **referência** (não tem dados operacionais, só metadados). Tem 2 abas:

**Aba `Apontamentos`** (9 colunas descritas):

| Coluna | Significado |
|---|---|
| `Id` | Identificador único do ciclo de apontamento |
| `Inicio` / `Fim` | Início e término do apontamento |
| `Tag` | Código do equipamento |
| `Frota` | Modelo da frota (ex.: 793-D 5S) |
| `Tipo` | Caminhão, Carregadeira, etc. |
| `Classe` | Classificação da atividade (Operando, Parado…) |
| `Nome_Operador_Anon` | Código anonimizado do operador (OP_XXX) |
| `Matricula_Operador_Hash` | Hash da matrícula |

**Aba `Telemetria`** (18 colunas descritas), com destaque para:
- `Id_Criticidade` — **1 = Crítico, 2 = Não Crítico**, etc.
- `Is_Dont_Go` — **flag binário (1 = consta na lista Don't Go, 0 = não)**.
- `Classe` — estado do alarme (`Activate` / `Inactive`).

👉 **Use este arquivo sempre que tiver dúvida sobre o que uma coluna significa.**

---

### 📕 `Alarmes - Regra de Negocio.xlsx` — Regras de Negócio dos Alarmes
Este é o arquivo "que define o que dispara o quê". Tem 3 abas:

**Aba `CMA`** (151 linhas) — **regras do CMA (Centro de Monitoramento de Ativos)**. Define **quando um alarme deve gerar uma ação**.

| Coluna | Significado |
|---|---|
| `TIPO` | `ALARME OEM`, `TENDÊNCIA` ou `SISTEMA` (origem da regra) |
| `EVENTO` | Nome do alarme (ex.: `Low Transmission Oil Level`) |
| `SITUACAO` | Condição de disparo (ex.: *"Mediante cinco alarmes nível 2 consecutivos"*) |
| `QTD` | Quantidade de ocorrências necessárias (1 a 10) |
| `TEMPO` | Janela em minutos (0 a 720) |
| `NIVEL` | Severidade da regra: `Alto` ou `Muito Alto` |

Exemplo de leitura: *"Se houver 5 alarmes de `Low Transmission Oil Level` nível 2 consecutivos em até 360 min → criticidade Muito Alta."*

**Aba `Tendências`** (371 linhas) — **catálogo de tendências monitoradas**. Lista nomes e descrições de "tendências" criadas para acompanhar variáveis operacionais (ex.: *"Pressão Acumulada Freio < 12300 kPa - OP 793F"*). É o que está por trás de eventos do tipo `TENDÊNCIA` na aba CMA.

**Aba `Eventos O&M`** (147.943 linhas) — **catálogo completo de eventos O&M (Operação & Manutenção)**. É só uma coluna `Name` com **todos os nomes de alarmes/eventos possíveis** que os equipamentos podem emitir (ex.: `+24V - Calculated Grasp 1`, `Engine Coolant Level - Active`). Funciona como **vocabulário de referência** dos alarmes que aparecem na coluna `Alarme` da telemetria.

👉 **Resumo da função do arquivo:** ele junta o **vocabulário de alarmes** (`Eventos O&M`), o **catálogo de tendências** (`Tendências`) e as **regras de criticidade** (`CMA`) — ou seja, é o que transforma a telemetria bruta em decisão de negócio.

---

### 📁 `datasets/apontamentos/`
- `desenvolver_apontamentos.xlsx` — **amostra** (100 linhas) para protótipo no Excel.
- `desenvolver_apontamentos.parquet` — **base completa** (377.907 linhas, jan–jun/2025).

Cada registro = **um ciclo de operação** de um equipamento (operando, parado, manutenção…), com início/fim, frota, tipo e classe.

---

### 📁 `datasets/telemetria/`
- `desenvolver_dontgo.xlsx` — **amostra ilustrativa** (147 linhas) com **1 exemplo de evento "Don't Go"**.
- 6 arquivos `telemetry_<mês>.parquet` — **base completa**, **1 arquivo por mês** (jan a jun/2025), totalizando ~37 milhões de eventos.

Cada registro = **um evento de alarme/telemetria** disparado por um equipamento em um instante, com a criticidade, o valor e a flag `Is_Dont_Go`.

---

### 🧭 Resumindo a "função" de cada arquivo

| Arquivo | Função |
|---|---|
| `README.md` | Resumo rápido da pasta |
| `Dicionario_Dados.xlsx` | **Dicionário** — explica cada coluna das tabelas |
| `Alarmes - Regra de Negocio.xlsx` | **Regras de negócio** — define alarmes, tendências e quando geram criticidade |
| `datasets/apontamentos/*` | Dados de **ciclos operacionais** dos equipamentos |
| `datasets/telemetria/*` | Dados de **eventos de telemetria** (alarmes) dos equipamentos |

Os dois `.xlsx` dentro de `datasets/` são só **amostras de desenvolvimento**; o "dado de verdade" para análise está nos `.parquet`. Já os dois `.xlsx` da raiz (`Dicionario_Dados` e `Alarmes - Regra de Negocio`) são **documentos de apoio** — não são dados operacionais, são "manuais" que você consulta enquanto analisa.

---

## 🚨 O que significa `Is_Dont_Go = 1`? — 11/05/2026

> **Prompt do usuário:** *"Cada registro = **um evento de alarme/telemetria** disparado por um equipamento em um instante, com a criticidade, o valor e a flag `Is_Dont_Go`. Is_dont_Go marcado com 1 significa o que?"*

### Definição

`Is_Dont_Go = 1` significa que o alarme/evento **dispara a regra "Don't Go"** — ou seja, o equipamento **não deve sair da mina / não deve continuar operando** até que o problema seja resolvido.

É um **sinalizador crítico de segurança/operação**.

### Interpretação dos valores

| Flag | Significado |
|---|---|
| `Is_Dont_Go = 0` | Alarme "normal" — equipamento pode continuar operando (requer monitoramento) |
| `Is_Dont_Go = 1` | **Alarme crítico — equipamento deve PARAR até resolução** (falha de segurança, defeito grave, etc.) |

### Exemplos práticos

- ❌ `Is_Dont_Go = 1` → "Engine Coolant Level - Critical" → o motor pode superaquecer → **pare agora**
- ❌ `Is_Dont_Go = 1` → "Transmission Oil Pressure - Low" → transmissão vai falhar → **pare agora**
- ⚠️ `Is_Dont_Go = 0` → "Cabin Temperature - High" → incômodo mas operável → monitore

### Volume nos dados

| Dados | Eventos `Is_Dont_Go = 1` | Total de eventos | Percentual |
|---|---:|---:|---|
| **XLSX** (`desenvolver_dontgo.xlsx`) | 1 | 147 | 0,68% (exemplo ilustrativo) |
| **PARQUET janeiro** | 2.581 | 5.400.002 | 0,048% |

### Referência de regras

A coluna `Alarmes - Regra de Negocio.xlsx` aba `CMA` define **quais alarmes** gatilham a flag `Is_Dont_Go = 1` — essa é a **"lista Don't Go"** que o sistema consulta na ingestão de telemetria.
