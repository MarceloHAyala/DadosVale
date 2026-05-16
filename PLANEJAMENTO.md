# Planejamento — Desafio Análise Avançada de Dados

**Programa Desenvolver 2026 | Vale**
**Participante:** Marcelo Ayala
**Data de início:** 13/05/2026
**Data de entrega:** 20/07/2026 (envio para `projetodesenvolver@vale.com`)
**Janela útil:** 10 semanas

---

## 1. Contexto

Desafio aberto de antecipação de alertas críticos (Don't Go) em frotas de mineração da região de Itabira, com 6 meses de dados (jan-jun/2025): ~37 milhões de eventos de telemetria + ~378 mil ciclos de apontamento.

**Fluxo do programa:**
1. ✅ Verificar arquivos
2. ⏳ Preparar e checar os dados
3. ⏳ Desenvolver o Desafio
4. ⏳ Gerar Relatório final
5. ⏳ Enviar solução por e-mail

**Marcos do programa:**
- 27/04/2026 — Pacote de dados recebido
- 28/04 a 20/07/2026 — Desenvolvimento
- 27/07/2026 — Divulgação dos Finalistas
- 24/08/2026 — Evento de Encerramento

---

## 2. Escopo: 6 perguntas analíticas

### Pergunta primária (foco do modelo)

**Q1** — Dado o histórico recente de telemetria, qual a probabilidade do equipamento gerar um alerta Don't Go nas próximas 4 horas?

Justificativa da janela de 4h:
- Tempo suficiente para a manutenção mobilizar peça/equipe
- Curto o bastante para que o estado atual ainda seja preditivo
- Compatível com o ciclo médio de turno em Itabira

### Perguntas secundárias (subprodutos do mesmo pipeline)

| # | Pergunta | Como será respondida |
|---|---|---|
| Q3 | Comportamento do operador correlaciona com alertas? | Feature `taxa_DG_operador_30d` + SHAP |
| Q4 | Perfil dos equipamentos com mais alertas (frota/tipo)? | EDA + análise de importância por frota |
| Q5 | Alertas concentram em turnos/dias/períodos? | Heatmap hora × dia da semana |
| Q6 | Recomendação de ação (continuar/preventiva/parar)? | Limiar da curva PR + tabela custo-benefício |
| Q7 | Como priorizar fila de inspeção da manutenção? | Ranking pelo score do modelo de Q1 |

### Pergunta fora de escopo

**Q2** — Prever o **tipo** do próximo alerta (motor vs. transmissão).

Justificativa: exige modelo multi-classe separado com tratamento específico de classes raras (alguns tipos têm < 50 ocorrências). Fora de escopo dado o tempo disponível e o trabalho ser individual. **Vai para Trabalhos Futuros.**

### Métrica de sucesso de negócio

- **Recall** sobre Don't Go (perder alerta = parada não planejada)
- **Precision** aceitável (falsos positivos geram inspeção desnecessária)
- **Tempo médio de antecipação** do alerta

---

## 3. Decisões técnicas (fixas — não trocar depois)

| Decisão | Escolha | Justificativa |
|---|---|---|
| Engine de dados | **Polars** | 37M linhas em pandas = 24GB RAM; Polars roda em 4GB |
| Modelo principal | **LightGBM** | Rápido, lida com desbalanceamento, SHAP funciona nativo |
| Modelo alternativo | **Modelo de Sobrevivência (Weibull AFT, fallback Cox PH)** | Prevê *tempo até* próximo DG (não só vai/não vai) — narrativa quantitativamente distinta e mais rica que classificação binária. Listado no CM 4.3 como caminho válido |
| 3ª abordagem (não supervisionada) | **Isolation Forest** treinado sem `Is_Dont_Go` | Resposta empírica direta ao viés inerente do label CMA: se IF recupera os DGs sem ver o rótulo, há sinal estrutural além da regra; se não recupera, a regra é o único sinal visível nos dados disponíveis. Diagnóstico complementar, não modelo competidor (CM 4.3 — "label de anomalia") |
| Biblioteca de sobrevivência | **lifelines** | Padrão Python para Cox/Weibull/Kaplan-Meier; documentação madura |
| Validação | Split temporal fixo + walk-forward final | jan-abr / mai / jun |
| Tuning | **Optuna**, 50 trials | Mais eficiente que GridSearch em poucos dias |
| Estratégia de desbalanceamento | `class_weight='balanced'` no LightGBM | Padrão para prevalência ~0,05%; comparação SMOTE/sem balanceamento descartada por retorno marginal frente ao custo — espaço de W5/W6 redirecionado para Isolation Forest |
| Interpretabilidade | **SHAP** (LightGBM) + coeficientes/HR (sobrevivência) | Padrão da indústria; sobrevivência permite interpretação direta de hazard ratio |
| Visualização | **matplotlib + seaborn** (não plotly) | Exporta PNG limpo para Word |
| Versionamento | Git local + push semanal para GitHub privado | Backup + sync entre máquinas |
| Gerenciador de pacotes | **uv** (pyproject.toml + uv.lock) | Reprodutibilidade exata entre máquinas; downloads paralelos; pina versão do Python |

---

## 4. Estrutura do projeto

```
AnaliseDadosVale/                            ← raiz do repositório Git
├── .gitignore
├── .python-version                          (Python 3.13 pinado)
├── pyproject.toml                           (deps gerenciadas via uv)
├── uv.lock                                  (versões exatas — versionado no Git)
├── README.md                                (como rodar em outra máquina)
├── PLANEJAMENTO.md                          (este arquivo)
├── Original/                                (backup intocado dos dados originais)
└── Projeto/                                 ← código + dados + entregáveis
    ├── Alterado/                            (dados de trabalho — base utilizada)
    │   ├── Base de Dados/
    │   │   ├── datasets/
    │   │   │   ├── apontamentos/desenvolver_apontamentos.parquet
    │   │   │   └── telemetria/telemetry_{jan,feb,mar,abr,may,jun}.parquet
    │   │   ├── Alarmes - Regra de Negocio.xlsx
    │   │   └── Dicionario_Dados.xlsx
    │   ├── Estudo Guiado - Análise Avançada de Dados.pdf
    │   └── Desenvolver_Template.docx
    ├── codigo/
    │   ├── 01_ingestao.py                   (W1)
    │   ├── 02_eda.py                        (W2)
    │   ├── 03_limpeza.py                    (W3)
    │   ├── 04_features.py                   (W3-W4)
    │   ├── 05_split.py                      (W4)
    │   ├── 06_baseline.py                   (W5)
    │   ├── 07_lightgbm.py                   (W5-W6)
    │   ├── 08_sobrevivencia.py              (W6 — Weibull AFT / Cox)
    │   ├── 09_evaluation.py                 (W7)
    │   ├── 10_isolation_forest.py           (W6 — 3ª abordagem não supervisionada)
    │   └── utils.py
    ├── dados/
    │   ├── intermediarios/                  (parquets pós-ingestão e limpeza — gitignored)
    │   └── features/                        (matriz pronta para modelo — gitignored)
    ├── modelos/                             (artifacts pickle/joblib — gitignored)
    └── relatorio/
        ├── figuras/                         (PNGs finais — 13 do guia + 3 extras)
        ├── tabelas/                         (CSVs: estatisticas, features, controle_alteracoes)
        ├── controle_alteracoes.md           (ANTES/DEPOIS de toda decisão metodológica)
        ├── hipoteses_eda.md                 (hipóteses levantadas na EDA)
        ├── rascunho.md                      (escrita progressiva W2→W8)
        └── relatorio_final.docx             (W9)
```

**Convenção:** todos os scripts dentro de `Projeto/codigo/` usam `Path(__file__).resolve().parents[1]` como raiz — ou seja, resolvem caminhos relativos a `Projeto/`. Por isso `Projeto/codigo/01_ingestao.py` lê de `Projeto/Alterado/...` e escreve em `Projeto/dados/...` sem hardcoded paths.

---

## 5. Cronograma resumo

| Semana | Datas | Foco | Marco |
|---|---|---|---|
| W1 | 13-19/05 | Setup + ingestão | |
| W2 | 20-26/05 | EDA visual | |
| W3 | 27/05-02/06 | Limpeza + features básicas | |
| W4 | 03-09/06 | Features avançadas + split | |
| W5 | 10-16/06 | Baseline + LightGBM v1 | **MARCO 1** |
| W6 | 17-23/06 | Tuning + Sobrevivência + SHAP + Ablation | |
| W7 | 24-30/06 | Análise + respostas Q3/Q6/Q7 | **MARCO 2** |
| W8 | 01-07/07 | Escrita do relatório | **MARCO 3** |
| W9 | 08-14/07 | Migração para template + revisão | |
| W10 | 15-20/07 | Buffer + entrega (enviar 18 ou 19/07) | |

**Carga média:** 10-12h/semana (W4-W6 com pico ~15h). Total estimado: ~122h (+10h vs. baseline por itens de profundidade: sensibilidade de janela, ablation, sobrevivência, e Isolation Forest como diagnóstico complementar não supervisionado; balanceamento comparativo removido em favor de `class_weight='balanced'` direto — trade de ~2h de documentação metodológica por ~5h de evidência empírica sobre o viés inerente do label).

---

## 6. Plano detalhado por semana

### W1 (13-19/05) — Setup + ingestão eficiente

**Objetivo:** ler todos os parquets com tipos corretos, sample pronto para iterar rápido.

- [X] Criar estrutura de pastas + `git init` + `pyproject.toml` + `.python-version`
- [X] Instalar `uv` e configurar `UV_HTTP_TIMEOUT`
- [X] Rodar `uv sync` (gerou `uv.lock` com 144 pacotes em `.venv/`)
- [X] Instalar VC++ Redistributable 2015-2022 (dep nativa do lightgbm no Windows)
- [X] Validar imports: polars 1.40.1 / pandas 2.3.3 / lightgbm 4.6.0 / shap 0.51.0 / lifelines 0.30.3
- [X] Configurar repositório privado no GitHub e fazer primeiro push (incluir `uv.lock`)
- [X] `Projeto/codigo/01_ingestao.py`: ler 6 telemetry_*.parquet + apontamentos.parquet com Polars
- [X] Corrigir tipos: `Inicio_Turno`, `Fim_Turno` → Datetime(us), `Valor` → Float64 (com tratamento de string "NULL" e vírgula decimal BR). Script `Projeto/codigo/02_correcao_tipos.py`. Output: `telemetria_tipada.parquet`.
- [X] Normalizar `Criticidade`: 5 variantes → 3 categorias canônicas ASCII (`Critico`, `Nao_Critico`, `Informacional`). Achado: inconsistência sistemática "Critico" sem acento vs "Não Crítico" com acento sugere 2 pipelines fonte distintas. Script `Projeto/codigo/03_limpeza.py`.
- [X] Salvar `Projeto/dados/intermediarios/telemetria_consolidado.parquet`
- [X] Validar: 37.164.054 linhas ✅ (assert em `01_ingestao.py`) + taxa DG = 0,0537% ✅ (19.962 positivos no semestre — assert em `03_limpeza.py`)
- ~~Criar sample de 500k linhas para desenvolvimento rápido~~ — **DESCARTADO** (13/05/2026): os parquets mensais em `Projeto/Alterado/Base de Dados/datasets/telemetria/` (5-7M linhas, 33-43 MB cada) já servem ao duplo propósito de visualização (abrem no VSCode) e iteração rápida em scripts (~2s para carregar). Sample 500k adicional seria redundância sem ganho prático.
- [X] **Verificação de duplicados** (CM 2.1): 0 duplicatas por chave primária em ambos datasets (Telemetria via `Id_Eventos_Telemetria`, Apontamentos via `Id`). Pipeline da Vale entrega chaves únicas.
- [X] **Frequência média de registros** (CM 2.1): Telemetria 206k/dia, 8.6k/hora, 5.9k/TAG/dia | Apontamentos 2.088/dia, 87/hora, 44/TAG/dia. **Achado:** telemetria cobre 35 TAGs vs 47 do apontamentos — diferença a investigar em W2.
- [X] **Tabela de estatísticas descritivas** (CM 2.1) → `Projeto/relatorio/tabelas/estatisticas_descritivas.csv`. 6 variáveis numéricas perfiladas. **Achado:** `Id_Criticidade` tem max=4 mas só 3 categorias normalizadas — investigar em W2 se existe 4º nível não mapeado.
- [X] Inicializar `Projeto/relatorio/controle_alteracoes.md` com 2 entradas iniciais: descarte do sample 500k + conversão de tipos (W1). Estrutura ANTES/DEPOIS/Justificativa/Impacto definida.

**Entregável:** parquet consolidado + script reproduzível + tabela estatísticas + controle_alteracoes iniciado.


#### Comandos Python de exploração (W1)

Registro dos comandos `uv run python -c` executados ad-hoc no terminal durante a W1, com o que estava sendo investigado em cada um. Tarefas implementadas como scripts (`01_ingestao.py`, `02_correcao_tipos.py`, `03_limpeza.py`) embutem a lógica diretamente e não aparecem aqui — para essas, basta rodar o `.py` correspondente.

<details>
<summary><b>1. Validar imports das libs principais</b> (após instalar VC++ Redistributable)</summary>

**O que eu estava explorando:** confirmar que polars / pandas / lightgbm / shap / lifelines / optuna importam sem erro de DLL e capturar as versões. Primeira tentativa quebrou com `FileNotFoundError: lib_lightgbm.dll` — diagnosticado como VC++ Redistributable ausente. Após instalar `vc_redist.x64.exe`, repeti o mesmo comando.

```powershell
uv run python -c "import polars, pandas, lightgbm, shap, lifelines, optuna, matplotlib, seaborn, numba; print('OK -', polars.__version__, pandas.__version__, lightgbm.__version__, shap.__version__, lifelines.__version__)"
```

**Resultado:** `OK - 1.40.1 2.3.3 4.6.0 0.51.0 0.30.3`

</details>

<details>
<summary><b>2. Inspecionar schema pós-ingestão</b> (descoberta de campos String que deveriam ser Datetime/Float)</summary>

**O que eu estava explorando:** confirmar shape (37M linhas, 18 colunas) do `telemetria_consolidado.parquet` recém-criado por `01_ingestao.py` e verificar os tipos brutos. **Achado:** `Inicio_Turno`, `Fim_Turno` e `Valor` vieram do parquet como `String` — motivou a criação do `02_correcao_tipos.py`.

```powershell
uv run python -c "import polars as pl; df = pl.read_parquet('Projeto/dados/intermediarios/telemetria_consolidado.parquet'); print('shape:', df.shape, '| schema:', pl.read_parquet_schema('Projeto/dados/intermediarios/telemetria_consolidado.parquet'))"
```

**Resultado:** `shape: (37164054, 18)` + schema mostrando `Inicio_Turno: String, Fim_Turno: String, Valor: String`.

</details>

<details>
<summary><b>3. Inspecionar formato de <code>Inicio_Turno</code> e top categorias de <code>Valor</code></b></summary>

**O que eu estava explorando:** descobrir o formato exato do datetime (achei `"2024-12-31 18:00:00.000"` com milissegundos — informou o `FORMATO_DATETIME = "%Y-%m-%d %H:%M:%S%.f"` do script 02) e ver a distribuição de `Valor`. **Achado crítico:** a string literal `"NULL"` aparece **237.443** vezes no top 15 — motivou o tratamento `pl.when(Valor == "NULL").then(None)` no `02_correcao_tipos.py`.

```powershell
uv run python -c "import polars as pl; df = pl.read_parquet('Projeto/dados/intermediarios/telemetria_consolidado.parquet'); print('Inicio_Turno samples:'); print(df.select('Inicio_Turno').head(10)); print('\nValor unique top:'); print(df.group_by('Valor').len().sort('len', descending=True).head(15))"
```

**Resultado:** top de `Valor` dominado por `"0"` (34,4M), `"1"`, `"2"`, `"3"`... + `"NULL"` em posição alta com 237.443 ocorrências.

</details>

<details>
<summary><b>4. Diagnosticar 821k strings que falharam no cast para Float64</b> (descoberta da vírgula decimal BR)</summary>

**O que eu estava explorando:** a asserção do `02_correcao_tipos.py` falhou — esperava 237.443 nulls (só os `"NULL"`), obteve 1.059.292. Diferença de 821.849 = strings que passaram pelo regex de validação mas falharam no `cast(Float64)`. Precisava saber QUAIS strings. **Achado:** 821.849 valores usam **vírgula decimal brasileira** (ex: `"46,2569999694824"`) — o regex `^-?[0-9]+([.,][0-9]+)?$` aceita ambos, mas o `Polars.cast(Float64)` só aceita ponto. **Fix posterior:** adicionar `.str.replace(",", ".")` antes do cast.

```powershell
uv run python -c "import polars as pl; df = pl.read_parquet('Projeto/dados/intermediarios/telemetria_consolidado.parquet'); problem = df.filter((pl.col('Valor') != 'NULL') & (pl.col('Valor').cast(pl.Float64, strict=False).is_null())); print('Total problematicos:', problem.height); print('\nTop 30 valores que falham no cast:'); print(problem.group_by('Valor').len().sort('len', descending=True).head(30))"
```

**Resultado:** `Total problematicos: 821849` — top valores `"46,2569999694824"` (10.813×), `"45,3499984741211"` (10.695×), `"48,0709991455078"` (10.621×)... todos com vírgula.

**Lição metodológica registrada em `controle_alteracoes.md`:** regex de validação aceita formato que o cast rejeita — só a asserção de contagem de nulls expôs o problema. Reforça o padrão de **asserções defensivas** em todos os scripts.

</details>

<details>
<summary><b>Nota — Itens sem comando ad-hoc separado</b> (lógica embutida em <code>03_limpeza.py</code>)</summary>

As seguintes verificações **não foram rodadas via `uv run python -c`** — toda a lógica está embutida em `03_limpeza.py` como funções defensivas e gera artefatos quando o script roda:

| Task | Função em `03_limpeza.py` | Artefato gerado |
|---|---|---|
| Descoberta das 5 variantes de Criticidade | `normalizar_criticidade()` com `raise ValueError` ao encontrar valor não mapeado | log no terminal + `telemetria_limpa.parquet` |
| Verificação de duplicados (CM 2.1) | `contar_duplicados()` (chave: `Id_Eventos_Telemetria` / `Id`) | log no terminal |
| Frequência média de registros (CM 2.1) | `frequencia_media()` | `inspecao_inicial.md` |
| Tabela de estatísticas descritivas (CM 2.1) | `estatisticas_descritivas()` | `tabelas/estatisticas_descritivas.csv` |

Para reproduzir, basta:

```powershell
uv run python Projeto/codigo/03_limpeza.py
```

A descoberta das **2 variantes de Criticidade com encoding parcial** (`"N??o Crítico"` e `"Não Cr??tico"`) veio justamente da defesa do `raise ValueError` na 1ª execução do script — o `CRITICIDADE_MAPEAMENTO` original tinha 3 variantes, o `raise` listou as 5 reais, e o dicionário foi atualizado antes da 2ª execução bem-sucedida.

</details>


#### Observações e Conclusões (W1)

##### 1. Diferença de cobertura: 35 TAGs em telemetria vs 47 em apontamentos

<details>
<summary><b>Comando Python usado para investigar</b></summary>

```python
import polars as pl

apo = pl.read_parquet('Projeto/Alterado/Base de Dados/datasets/apontamentos/desenvolver_apontamentos.parquet')
tel = pl.read_parquet('Projeto/dados/intermediarios/telemetria_limpa.parquet')

tags_apo = set(apo['Tag'].unique().to_list())
tags_tel = set(tel['TAG'].unique().to_list())

print('=== TAGs em apontamentos MAS NAO em telemetria ===')
ausentes = sorted(tags_apo - tags_tel)
print(f'Total: {len(ausentes)}')
print(ausentes)

print('\n=== Perfil desses TAGs ausentes (frota + tipo) ===')
print(
    apo.filter(pl.col('Tag').is_in(ausentes))
       .group_by(['Frota', 'Tipo'])
       .agg(
           pl.len().alias('n_apontamentos'),
           pl.col('Tag').n_unique().alias('n_tags'),
       )
)

print('\n=== TAGs em telemetria MAS NAO em apontamentos ===')
extras = sorted(tags_tel - tags_apo)
print(f'Total: {len(extras)}')
print(extras)
```

Executar com:
```powershell
uv run python -c "<colar o codigo acima em uma linha>"
```
ou salvar como `Projeto/codigo/exploracao_tags.py` e rodar `uv run python Projeto/codigo/exploracao_tags.py`.

</details>

Apontamentos têm **12 equipamentos a mais** que telemetria, distribuídos em **4 frotas distintas**:

| Frota | Tipo | TAGs sem telemetria | Registros em apontamentos |
|---|---|---|---|
| **LeTourneau L 1850** | Escavadeira | **5** (PE3782-3785, PE3788) | 17.640 |
| 793-D 4S | Caminhão | 3 (CA65918-CA65920 inferido) | 13.032 |
| 793-D 3S | Caminhão | 3 (CA65901, CA65905, CA65911) | 4.872 |
| 793-D 5S | Caminhão | 1 (`CA0000` — suspeito) | 3.330 |

- A frota mais afetada é a de escavadeiras LeTourneau L 1850 — **5 de cada 13** equipamentos da frota não têm telemetria contínua (gap de ~38%).
- `CA0000` é suspeito: nome "todos zeros" sugere placeholder ou erro de cadastro no sistema fonte.
- 0 TAGs em telemetria sem apontamentos — telemetria é subconjunto perfeito (sanidade do pipeline).

**Implicação para modelagem:** O modelo principal só pode prever DGs para as **35 TAGs com telemetria**. Os 12 sem telemetria precisariam de baseline alternativo (heurística baseada em apontamentos), **fora do escopo deste estudo**.

**Insight para CM 6.1 (Insights não óbvios):** ~25% da frota total não tem instrumentação contínua. **Recomendação para Vale (Trabalhos Futuros):** completar cobertura de telemetria, especialmente nas escavadeiras LeTourneau L 1850.

---

##### 2. `Id_Criticidade=4` — descoberta de eventos de bypass manual do operador

<details>
<summary><b>Comando Python usado para investigar</b></summary>

```python
import polars as pl

tel = pl.read_parquet('Projeto/dados/intermediarios/telemetria_limpa.parquet')

print('=== Mapeamento Id_Criticidade x Criticidade ===')
print(
    tel.group_by(['Id_Criticidade', 'Criticidade'])
       .len()
       .sort(['Id_Criticidade', 'Criticidade'])
)

print('\n=== Registros com Id_Criticidade = 4 ===')
n4 = tel.filter(pl.col('Id_Criticidade') == 4)
print(f'Total: {n4.height:,}')
print(
    n4.group_by(['Id_Criticidade', 'Criticidade', 'Alarme'])
      .len()
      .sort('len', descending=True)
      .head(10)
)
```

</details>

`Id_Criticidade=4` mapeia para `Criticidade=Informacional` (mesmo grupo que `Id=3`). São **3.119 registros (0,008% do total)**. Mapeamento completo:

| Id_Criticidade | Criticidade | Quantidade |
|---|---|---|
| 1 | `Critico` | 83.020 |
| 2 | `Nao_Critico` | 461.865 |
| 3 | `Informacional` | 36.616.050 |
| **4** | `Informacional` | **3.119** |

**Achado central:** Esses 3.119 registros **não são alertas de falha** — são **eventos de bypass manual / override do operador**, com 87% concentrados em 1 alarme:

| Alarme | Quantidade | % |
|---|---|---|
| **Channel Forced (L-1850)** | 2.733 | 87,6% |
| Hoist And Bucket Limits Bypassed | 151 | 4,8% |
| Steering Limits Bypassed (L-1850) | 107 | 3,4% |
| Steering Limits Bypassed By User | 107 | 3,4% |
| Channel Forced | 17 | 0,5% |
| High Voltage Cabinet Door Open | 3 | 0,1% |

**Insight forte para CM 6.1 (Insights não óbvios) — candidato a feature explicativa:** `Id_Criticidade=4` é um **sinal de comportamento operacional**, não de falha de equipamento. **Operadores que fazem bypass com frequência podem ser preditores de DG futuro** — comportamento de risco ou pressão operacional excessiva. Criar feature `n_bypasses_operador_7d` para o modelo (W4).

**Conexão notável:** 95% dos bypasses são específicos da frota **LeTourneau L 1850** (mesma frota com gap de telemetria do achado 1). Pode haver problema operacional sistêmico nessa frota — destacar no relatório.

---

##### 3. `Valor` max=4347 — peso de carga com provável erro de unidade

<details>
<summary><b>Comando Python usado para investigar</b></summary>

```python
import polars as pl

tel = pl.read_parquet('Projeto/dados/intermediarios/telemetria_limpa.parquet')

high = tel.filter(pl.col('Valor') > 1000)
print(f'=== Registros com Valor > 1000: {high.height:,} ===')

print('\n=== Top 15 alarmes que geram Valor > 1000 ===')
print(
    high.group_by('Alarme')
        .agg(
            pl.len().alias('n'),
            pl.col('Valor').min().alias('val_min'),
            pl.col('Valor').max().alias('val_max'),
            pl.col('Valor').mean().round(2).alias('val_mean'),
            pl.col('Is_Dont_Go').sum().alias('n_DG'),
        )
        .sort('n', descending=True)
        .head(15)
)

print('\n=== Registros com max=4347 ===')
print(
    tel.filter(pl.col('Valor') == 4347)
       .select(['TAG', 'Alarme', 'Criticidade', 'Is_Dont_Go', 'Data_Evento'])
       .head(5)
)
```

</details>

Apenas **118 registros (0,0003% do total)** têm `Valor > 1000`. **100% vêm de 2 alarmes relacionados**, ambos sobre peso de carga:

| Alarme | n | Valor mín | Valor max | Valor médio | DGs |
|---|---|---|---|---|---|
| **Truck Load Weight (L-1850)** | 104 | 1002 | **4347** | 1.347 | **0** |
| Truck Load Weight | 14 | 1005 | 2592 | 1.506 | **0** |

- **100% são `Criticidade=Informacional` e `Is_Dont_Go=0`** — nenhum é alerta crítico.
- São **medições de peso de carga** sendo registradas como eventos.
- O registro com Valor=4347 é da TAG `PE3798` (escavadeira), em 2025-03-30 14:55:48.733.

**4347 é fisicamente impossível** para um caminhão (capacidade 793-D ≈ 240t). Causas prováveis: erro de unidade (kg em vez de toneladas?), acumulação de cargas múltiplas no mesmo timestamp, ou bug do sensor registrando overflow.

**Implicação para W3 (limpeza):** Como os outliers **não contaminam o target** (zero DGs entre eles), o tratamento é de **baixo risco**. Três opções:
1. **Manter com flag** (`is_outlier_valor_peso`) — recomendado, preserva informação
2. **Cap em 300** (acima da capacidade física máxima)
3. **Remover** os 118 registros (0,0003%, desprezível)

**Insight para CM 6.1 (Insights não óbvios):** Esses 118 registros revelam **problema de qualidade de dados na medição de peso de carga** — sistema fonte aparentemente mistura unidades. Recomendação para Vale (Trabalhos Futuros): padronizar unidade do sensor de peso e auditar overflow.

---

##### Padrão emergente: frota LeTourneau L 1850

A frota **LeTourneau L 1850** aparece em **3 achados independentes** de W1:
1. 5 equipamentos sem telemetria (achado 1)
2. 95% dos bypasses do operador (achado 2)
3. 88% dos erros de medição de peso (achado 3)

Isso é um **insight não óbvio de alto valor** para o relatório (CM 6.1) — sugere que essa frota tem problemas operacionais e/ou de instrumentação sistêmicos que merecem destaque na Conclusão e Trabalhos Futuros.

---

### W2 (20-26/05) — EDA visual

**Objetivo:** todas as figuras de EDA prontas. Q4 e Q5 respondidas em rascunho. Hipóteses registradas.

**Figuras obrigatórias do Estudo Guiado (numeração segue o guia):**

- [ ] **Fig 1** — Diagrama do fluxo operacional: ciclo de apontamento → telemetria → alerta (CM 1.1)
- [X] **Fig 2** — Distribuição temporal dos registros de apontamentos (volume por dia/hora) (CM 2.1) — `fig02_distribuicao_temporal_apontamentos.png`
- [X] **Fig 3** — Distribuição de alertas por TIPO × NÍVEL de criticidade (CM 2.2) — `fig03_tipo_x_criticidade.png` (stacked bar Tipo de equipamento × Criticidade, Informacional filtrado)
- [X] **Fig 4** — Série temporal: frequência de alertas DG ao longo do período (CM 2.2) — `fig04_serie_temporal_dgs.png` (2 subplots: total + split Crítico/Não-Crítico, MA 7d)
- [X] **Fig 5** — Heatmap de correlação entre features numéricas (CM 2.3) — `fig05_heatmap_correlacao.png`
- [X] **Fig 6** — Taxa de alertas por hora do dia e dia da semana (CM 2.3) → responde **Q5** — `fig06_heatmap_hora_dia.png`

**Figuras extras (agregam valor — fazer se tempo permitir, senão vão para anexo):**

- [ ] Extra A — Sobrevivência empírica por frota: P(novo DG > t)
- [X] **Extra B — Pareto top-10 alarmes precursores** *(promovido a obrigatório — alimenta diretamente a análise "o que a regra não vê" do W7, parte do diagnóstico K via Isolation Forest)* — `figExB_pareto_alarmes.png` confirma visualmente 87,3% do top 5
- [ ] Extra C — Cadeia de eventos no caso CA65924 (do `desenvolver_dontgo.xlsx`)

**Outros entregáveis da semana:**

- [X] Análise da distribuição por **Frota / Tipo / Classe** → responde **Q4** — `dgs_por_frota_tipo_classe.csv` via **join temporal `join_asof`** (achado: 12,65% dos DGs ocorrem em estado `Manutenção`, gerou obs 2.7)
- [X] **Distribuição de alertas por TAG de equipamento** (Pareto/bar plot) — CM 2.2 pede explicitamente — `figExG_pareto_tags.png` (top-15 de 35 TAGs com telemetria)
- [ ] **Tabela `eventos_muito_alto.csv`** listando eventos da CMA com NIVEL "Muito Alto" (CM 1.1) — colunas: TIPO / EVENTO / SITUACAO / QTD / TEMPO / NIVEL
- [ ] Escrever em `Projeto/relatorio/rascunho.md` seção EDA + achados de Q4 e Q5
- [ ] **`Projeto/relatorio/hipoteses_eda.md`** — registrar TODAS as hipóteses levantadas (confirmadas e não confirmadas) com 1 parágrafo cada

**Entregável:** 6 figuras obrigatórias + extras desejáveis + hipoteses_eda.md + eventos_muito_alto.csv + rascunho EDA.

#### Observações e Conclusões (W2)

##### 1. `Informacional` = 0 DGs no semestre completo (Obs 2.2 confirmada com precisão cirúrgica)

<details>
<summary><b>Script usado para investigar</b></summary>

Função `obs_2_2_informacional_dgs()` em [`Projeto/codigo/exploracao_w2_obs.py`](Projeto/codigo/exploracao_w2_obs.py). Para reproduzir:

```powershell
uv run python Projeto/codigo/exploracao_w2_obs.py
```

</details>

Distribuição de DGs por Criticidade no semestre completo (jan-jun/2025):

| Criticidade | Total eventos | Total DGs | Taxa DG | % volume |
|---|---:|---:|---:|---:|
| **Informacional** | 36.619.169 | **0** | **0,0000%** | 98,53% |
| Nao_Critico | 461.865 | 9.676 | 2,10% | 1,24% |
| Critico | 83.020 | 10.286 | **12,39%** | 0,22% |

- **Confirmação total da hipótese:** zero DGs em 36,6M eventos Informacionais — não é "praticamente zero", é **exatamente zero**.
- **Filtrar `Informacional` em W3 é seguro:** zero positivos perdidos, 98,53% do volume eliminado.
- **Bônus inesperado:** a taxa de DG de eventos `Critico` é **12,39%** — 1 em cada 8 eventos críticos é DG. É o sinal instantâneo mais forte do dataset.

**Implicação para W3 (limpeza):** decisão registrada em `controle_alteracoes.md` (2026-05-16). Pós-filtro o dataset cai de 37.164.054 para ~544.885 linhas — viabiliza rolling windows em W4 sem risco de estouro de RAM.

---

##### 2. Top 5 alarmes concentra 87,3% dos DGs (Obs 2.1 confirmada com surpresa de reordenação)

<details>
<summary><b>Script usado para investigar</b></summary>

Função `obs_2_1_top_alarmes()` em [`Projeto/codigo/exploracao_w2_obs.py`](Projeto/codigo/exploracao_w2_obs.py).

</details>

A concentração do top 5 é **virtualmente idêntica entre janeiro e o semestre** (87,3% vs 88%), mas a **ordem mudou** significativamente:

| Pos. | Alarme | DGs jan | DGs semestre | % semestre | Movimento |
|---:|---|---:|---:|---:|---|
| 1 | Engine Coolant Level | 1.505 | 9.615 | 48,17% | mantém #1 |
| 2 | **Right Front Brake Temperature** | 116 | 4.494 | 22,51% | **5º → 2º** ↑↑ |
| 3 | Transmission Oil Level | 205 | 1.426 | 7,14% | mantém |
| 4 | Left Rear Brake Temperature | 160 | 999 | 5,00% | mantém |
| 5 | **Aftercooler Level** | 249 | 892 | 4,47% | **2º → 5º** ↓↓ |

**Achado lateral surpreendente:** apenas **19 alarmes distintos** geraram >=1 DG no semestre todo (de 4.402 alarmes únicos no dataset). Feature engineering em W4 pode focar nesses 19 — 99,6% dos alarmes do dataset são irrelevantes para o target.

**Implicação para W2 (EDA visual):** o salto de "Right Front Brake Temperature" (5º → 2º, +3782%) e a queda de "Aftercooler Level" (2º → 5º) são candidatos a investigação de **sazonalidade ou mudança operacional**. Vale plotar série temporal mensal por alarme (alimenta Fig 4 do guia).

**Insight para CM 6.1 (Insights não óbvios):** o universo de alarmes operacionalmente críticos é **muito menor que o universo de alarmes monitorados**. Recomendação para Vale: redirecionar atenção da operação para esses ~19 alarmes em vez de monitorar 4.402.

---

##### 3. Nao_Critico EXPLODIU de 20% para 48,47% dos DGs (Obs 2.5 — mudança radical)

<details>
<summary><b>Script usado para investigar</b></summary>

Função `obs_2_5_nao_critico_acumulacao()` em [`Projeto/codigo/exploracao_w2_obs.py`](Projeto/codigo/exploracao_w2_obs.py).

</details>

Distribuição dos DGs entre `Critico` e `Nao_Critico`:

| Período | Critico | Nao_Critico | Total DGs |
|---|---:|---:|---:|
| Janeiro (relatório inicial) | **80% (2.005)** | **20% (504)** | 2.509 |
| Semestre completo (jan-jun) | **51,53% (10.286)** | **48,47% (9.676)** | 19.962 |

Em valores absolutos: janeiro teve 504 DGs `Nao_Critico`; fev-jun acumulou **+9.172 DGs** (média de **~1.834/mês — 3,6× a taxa de janeiro**).

**O que mudou?** Hipóteses (a investigar com Fig 4 da EDA visual):
1. **Janeiro foi atípico** (baixa atividade operacional — chuvas, feriados, ramp-up?)
2. **Mudança operacional ou de regra CMA** após janeiro (recalibração de thresholds de acumulação?)
3. **Crescimento orgânico** (mais equipamentos em operação, mais ciclos de carga)

**Implicação central para W4 (feature engineering):** **rolling windows estão fortemente validadas como família dominante de features**. Metade dos DGs do semestre só viraram DG por **acumulação** (regra CMA `QTD > 1`), não por nível crítico em um único evento. Sem rolling window, o modelo não vê essa metade do problema.

**Narrativa para o relatório (W7-W8):** "do total de 19.962 DGs no semestre, **48% só são detectáveis pelo padrão de acumulação temporal** — não por nível crítico em um único evento. Isso justifica empiricamente a escolha de feature engineering temporal sobre estado instantâneo."

---

##### Padrão emergente: as 3 obs se consolidam em um plano operacional para W3-W4

Cruzando os 3 achados, o desenho da próxima semana fica claro:

1. **Filtrar `Informacional`** (Obs 2.2) — viabiliza qualquer rolling window depois
2. **Restringir feature engineering aos 19 alarmes relevantes** (Obs 2.1) — reduz dimensionalidade em 99,6%
3. **Priorizar rolling windows 1h/4h/24h** (Obs 2.5) — captura os 48% de DGs por acumulação

Nova observação pendente gerada nesta investigação: **distribuição mensal dos DGs `Nao_Critico`** para entender se o salto 20% → 48% é tendência ou pico — registrada em `observacoes_importantes.md` (item 2.6).

---

##### 4. Q4 — Perfil dos equipamentos com DGs (via join temporal apontamentos × telemetria)

<details>
<summary><b>Script usado para investigar</b></summary>

Função `tabela_q4()` em [`Projeto/codigo/04_eda.py`](Projeto/codigo/04_eda.py). Usa `join_asof` por TAG entre `telemetria.Data_Evento` e `apontamentos.Inicio` (`strategy="backward"`), seguido de filtro `Data_Evento <= Fim` para garantir que o ciclo de apontamento estava ativo no momento do DG. Cast `ns → μs` em apontamentos para alinhar tipos. DGs sem match seriam marcados como `SEM_APONTAMENTO` — mas no semestre completo isso não aconteceu.

Para reproduzir:
```powershell
uv run python Projeto/codigo/04_eda.py
```

Saída em [`Projeto/relatorio/tabelas/dgs_por_frota_tipo_classe.csv`](Projeto/relatorio/tabelas/dgs_por_frota_tipo_classe.csv) (17 linhas).

</details>

**Qualidade do casamento temporal:** **100% dos 19.962 DGs** encontraram um ciclo de apontamento válido. A pipeline de apontamentos da Vale entrega cobertura temporal completa, sem gaps — pré-condição para usar `estado_operacional_no_DG` como feature em W4.

**Distribuição por Frota / Tipo:**

| Frota | Tipo | DGs | % do total | n_TAGs |
|---|---|---:|---:|---:|
| **793-D 5S** | Caminhão | 9.341 | **46,79%** | 13 |
| **793-D 4S** | Caminhão | 7.405 | **37,10%** | 8 |
| 793-D 2S | Caminhão | 1.699 | 8,51% | 4 |
| 793-D 3S | Caminhão | 1.350 | 6,76% | 3 |
| **LeTourneau L 1850** | Escavadeira | 167 | **0,84%** | 5 |

- 2 frotas (5S + 4S) concentram **83,89%** dos DGs
- 100% dos DGs vêm de caminhões 793-D ou escavadeiras LeTourneau
- Caminhões 793-D 5S: ~720 DGs/equipamento médio. Escavadeiras LeTourneau: **~33 DGs/equipamento** (~22× menos por unidade)

**Distribuição por estado operacional no momento do DG (achado central):**

| Estado (Classe) | DGs | % | Interpretação esperada |
|---|---:|---:|---|
| **Operando** | 16.122 | **80,76%** | esperado — DG de produção |
| **Manutenção** | **2.525** | **12,65%** | ⚠️ **surpreendente — esperaria ~0** |
| Parado | 1.184 | 5,93% | aceitável — sensores ativos com equipamento ocioso |
| Hibernando | 131 | 0,66% | anômalo — equipamento "dormindo" gerou alerta |

**Achado surpreendente: 1 em cada 8 DGs ocorre com o equipamento em estado `Manutenção`.** Três hipóteses precisam ser diferenciadas em W3-W4:

1. **DG → transição de estado** (mais provável): o evento `Data_Evento` foi escrito enquanto o ciclo ainda estava em "Operando", mas o registro do apontamento atualizou para "Manutenção" pouco depois — o DG **causou** a transição. Se confirmada, vira feature poderosa em W4: `transicao_estado_pos_DG` correlacionaria com severidade real do DG.
2. **Falsos positivos de bancada** (preocupante): em diagnósticos de manutenção, sistemas elétricos são energizados sem produção real → alarmes disparam por testes. Se confirmada, esses 2.525 DGs são **viés do label CMA** (reforça Risco 3.3) e deveriam ser excluídos do target.
3. **Bug de pipeline CMA** (menos provável): geração de DGs sem checagem de estado.

**Como diferenciar as 3 hipóteses em W3-W4:** para cada DG em estado "Manutenção", calcular a **posição relativa** de `Data_Evento` dentro de `[Inicio, Fim]`:
- Massa concentrada perto de `Inicio` (≤ 10% do intervalo) → hipótese 1 (DG causou transição, vira feature)
- Distribuição uniforme no intervalo → hipótese 2 (falsos positivos de bancada, vira filtro de limpeza)
- Concentração em alarmes específicos de bancada → hipótese 3 (bug, vira recomendação para a Vale)

**Insight para CM 6.1 (Insights não óbvios):** o conceito de "Don't Go" **não é binário em relação ao estado operacional** — 12,65% dos DGs ocorrem fora de produção real. Recomendação para Vale (Trabalhos Futuros): separar DGs por estado operacional no painel do dispatcher para evitar fadiga de alerta — um DG durante manutenção não tem o mesmo peso que um DG em equipamento operando.

**4ª aparição independente da frota LeTourneau L 1850 (extensão do padrão emergente de W1):**

A frota LeTourneau agora aparece em **4 achados independentes**:
1. (W1) 5 equipamentos sem telemetria
2. (W1) 95% dos bypasses do operador
3. (W1) 88% dos erros de medição de peso
4. **(W2) Taxa de DG por equipamento ~22× menor que caminhões 793-D**

Três interpretações possíveis para o achado 4:
- **Genuíno**: escavadeiras realmente têm menos falhas (são ferramentas estacionárias com menos componentes em movimento contínuo vs caminhões)
- **Viés da regra CMA**: limiares/regras de acumulação calibrados para caminhões, mal adaptados a escavadeiras
- **Subreporte**: combinado com achados 1-3 sugere que **a instrumentação da frota é problemática** — DGs podem estar ocorrendo mas não sendo capturados

**Recomendação metodológica para W7:** análise estratificada por **Caminhão vs Escavadeira** como subgrupos separados — métricas (Precision, Recall, AUC-PR) reportadas em cada um. Já está previsto no Profundidade C do PLANEJAMENTO (W7), mas agora há base empírica forte pra justificar.

---

### W3 (27/05-02/06) — Limpeza + features básicas

**Objetivo:** matriz v1 com 10-15 features documentadas.

- [ ] `Projeto/codigo/03_limpeza.py`: tratar outliers em `Valor` (IQR + flag, manter linhas)
- [ ] **Estratégia de missing values por coluna** (CM 3.1): para cada coluna com nulos, decidir e justificar — remoção de linhas, imputação por mediana/moda, forward-fill (séries temporais) ou flag de ausência. Registrar tabela coluna×estratégia em `controle_alteracoes.md`
- [ ] Tratar registros com `Inicio > Fim` nos apontamentos
- [ ] **Detecção de sobreposições de ciclo** (CM 3.1): identificar registros onde ciclos do mesmo TAG se sobrepõem no tempo; reportar quantidade e decisão (manter / merge / descartar com justificativa)
- [ ] Filtrar `Criticidade = "Informacional"` (não tem positivos, economiza ~80% do volume)
- [ ] Tabela ANTES/DEPOIS em `Projeto/relatorio/tabelas/controle_alteracoes.csv` com **colunas exatas do CM 3.1**: Campo / Problema Identificado / Qtd. Registros / Tratamento Aplicado / Justificativa
- [ ] `Projeto/codigo/04_features.py` — features básicas:
  - [ ] `hora_dia`, `dia_semana`, `turno`, `mes`
  - [ ] **Encoding categórico documentado para as 5 categorias** (CM 3.2) — decisão por cardinalidade:
    - `Tag` (alta cardinalidade, ~centenas de equipamentos) → **target encoding** com smoothing + KFold para evitar leakage
    - `Frota` (média cardinalidade) → **target encoding**
    - `Tipo` (baixa cardinalidade, ~5-10 categorias) → **one-hot**
    - `Classe` (baixa-média cardinalidade) → **one-hot** ou **frequency encoding** conforme contagem distinta
    - `Operador` (alta cardinalidade, anonimizado) → **frequency encoding** + feature derivada `taxa_DG_operador_30d` (semântica útil sem one-hot explodindo dimensão)
  - [ ] Registrar a justificativa de cada escolha em `documentacao_features.csv` (coluna Motivação)
- [ ] Salvar `Projeto/dados/features/v1.parquet`
- [ ] Iniciar **`Projeto/relatorio/tabelas/documentacao_features.csv`** (CM 3.2): para cada feature criada — nome, descrição, fórmula/lógica, motivação/hipótese
- [ ] Registrar em `controle_alteracoes.md` decisões de limpeza (filtros, outliers, encoding)

**Entregável:** matriz v1 + tabela ANTES/DEPOIS + documentacao_features.csv iniciado.

#### Observações e Conclusões (W3)

*(A preencher quando observações de W3 forem investigadas — origem: `Projeto/relatorio/observacoes_importantes.md` ou novas descobertas durante a semana.)*

---

### W4 (03-09/06) — Features avançadas + definição do target + split

**Objetivo:** matriz final v2 + datas de corte definidas + target documentado.

- [ ] Rolling windows por TAG: contagem de eventos por criticidade nas últimas 1h, 4h, 24h
- [ ] Features de recência: `horas_desde_ultimo_DG`, `horas_desde_ultimo_critico`
- [ ] Features de operador: `taxa_DG_operador_30d` → base para **Q3**
- [ ] Features de regra de negócio: `qtd_alarmes_nivel_muito_alto_360min`
- [ ] **Finalizar `documentacao_features.csv`** com fórmula+motivação de TODAS as features (CM 3.2 nota)
- [ ] Construir target: `y = 1` se houver evento DG na janela de +0 a +4h do equipamento (CM 3.3)
- [ ] **[Profundidade 1] Análise de sensibilidade da janela de predição** (~2h): gerar targets paralelos para janelas de **2h, 4h e 8h**; treinar LightGBM com parâmetros default em cada um e comparar AUC-PR/Recall no conjunto de validação. Tabela `sensibilidade_janela.csv` → justificar empiricamente a escolha de 4h em vez de só argumentar com motivos operacionais. Registrar conclusão em `controle_alteracoes.md`
- [ ] **Fig 7** — Diagrama da janela de predição: instante de decisão → janela 4h → evento alvo (CM 3.3)
- [ ] `Projeto/codigo/05_split.py` — split: treino jan-abr, val mai, teste jun
- [ ] **Fig 8** — Diagrama da estratégia de validação temporal (CM 4.1)
- [ ] Escrever justificativa explícita do porquê não usar k-fold aleatório (data leakage)
- [ ] Salvar `Projeto/dados/features/v2.parquet`
- [ ] Registrar decisões em `controle_alteracoes.md` (janela 4h, definição target, datas de corte)

**Entregável:** matriz v2 + documentacao_features.csv completa + Fig 7 + Fig 8.

#### Observações e Conclusões (W4)

*(A preencher quando observações de W4 forem investigadas — origem: `Projeto/relatorio/observacoes_importantes.md` ou novas descobertas durante a semana.)*

---

### W5 (10-16/06) — Baseline + LightGBM v1 → MARCO 1

**Objetivo:** modelo principal funcionando, batendo o baseline.

- [ ] `Projeto/codigo/06_baseline.py` — heurística: DG=1 se houve crítico nas últimas 4h do mesmo TAG
- [ ] Métricas baseline no teste de jun: Precision, Recall, F1, AUC-PR
- [ ] `Projeto/codigo/07_lightgbm.py` — LightGBM v1 com `class_weight='balanced'`, parâmetros default
- [ ] **Documentar pré-processamento específico do baseline e do LightGBM** (CM 4.3): baseline usa só `Criticidade` e `TAG`; LightGBM usa matriz completa v2
- [ ] Comparar com baseline
- [ ] 🚦 **GATE MARCO 1: LightGBM bate baseline em AUC-PR?**
  - SIM → avança para W6
  - NÃO → pare. Reveja features antes de tunar parâmetros

**Entregável:** tabela comparativa baseline×LightGBM + modelos serializados em `Projeto/modelos/` + pré-processamento documentado.

#### Observações e Conclusões (W5)

*(A preencher quando observações de W5 forem investigadas — origem: `Projeto/relatorio/observacoes_importantes.md` ou novas descobertas durante a semana.)*

---

### W6 (17-23/06) — Tuning + Sobrevivência + Isolation Forest + SHAP + Ablation

**Objetivo:** LightGBM otimizado + modelo de sobrevivência + diagnóstico não supervisionado (K) + interpretabilidade + ablation. Semana mais carregada do projeto (~15h).

- [ ] Optuna no LightGBM: 50 trials sobre validação (mai)
- [ ] LightGBM v2 com melhores parâmetros, avaliar no teste
- [ ] `Projeto/codigo/08_sobrevivencia.py` — **Modelo de Sobrevivência (Weibull AFT, fallback Cox PH)** com `lifelines`:
  - [ ] **Reformatar dados para análise de sobrevivência**: para cada equipamento (TAG), construir tuplas (T, E, X) onde T = tempo até o próximo DG (em horas), E = 1 se evento observado / 0 se censurado (fim da janela jan-jun sem DG), X = features no instante de referência
  - [ ] Treinar `WeibullAFTFitter` no treino (jan-abr), avaliar **C-index** em validação (mai) e teste (jun)
  - [ ] Se WeibullAFT não convergir ou C-index < 0.6 → fallback para `CoxPHFitter` (CM 4.3 nota: dois modelos bem feitos > cinco superficiais)
  - [ ] **Pré-processamento específico de sobrevivência** (CM 4.3): mesma matriz numérica v2, mas exclui features com colinearidade > 0.9 (Cox/Weibull são sensíveis); StandardScaler em features contínuas
  - [ ] Converter saída em probabilidade-em-4h: `P(T ≤ 4h | X)` → comparável com LightGBM em AUC-PR
  - [ ] **Interpretação via hazard ratios**: tabela top-10 features com HR e IC 95% — interpretação direta sem SHAP
- [ ] **Fig 9** — Curvas ROC + Precision-Recall comparando baseline × LightGBM × Sobrevivência (CM 5.1)
- [ ] **Fig 11** — SHAP summary plot do LightGBM (CM 5.3)
- [ ] **Fig 12** — SHAP waterfall de 1 predição individual (CM 5.3)
- [ ] **Validação de sentido das features** (CM 5.3): comparar top-10 do SHAP (LightGBM) com top-10 dos hazard ratios (sobrevivência) — concordância entre dois métodos independentes é evidência forte de validade
- [ ] **[Profundidade 2] Ablation por grupo de features** (~3h): retreinar o LightGBM v2 (parâmetros fixos do Optuna) removendo cada família e medir queda de AUC-PR no teste. Grupos:
  - (G1) Temporais (`hora_dia`, `dia_semana`, `turno`, `mes`)
  - (G2) Rolling windows 1h/4h/24h
  - (G3) Recência (`horas_desde_ultimo_DG`, `horas_desde_ultimo_critico`)
  - (G4) Operador (`taxa_DG_operador_30d`, `Operador_freq`)
  - (G5) Regra de negócio (`qtd_alarmes_nivel_muito_alto_360min`)
  - (G6) Categóricas codificadas (`Tag`, `Frota`, `Tipo`, `Classe`)
  - Tabela `ablation_grupos.csv` com ΔAUC-PR e ΔRecall por grupo. **Fig Extra E** — gráfico de barras. Vira insight de produto (qual sinal carrega o modelo)
- [ ] **[Qualidade A] Calibração do modelo escolhido**: calibration plot + Brier score → Fig Extra D. Se descalibrado, aplicar Platt scaling
- [ ] **[K — Isolation Forest, 3ª abordagem não supervisionada] (~3h)**: `Projeto/codigo/10_isolation_forest.py`
  - [ ] Treinar `IsolationForest(n_estimators=200, contamination=0.001)` em jan-abr **sem usar `Is_Dont_Go`** (matriz v2 — mesma feature engineering dos outros modelos)
  - [ ] Scoring em validação (mai) e teste (jun); converter anomaly score em ranking
  - [ ] AUC-PR e **Recall@K** (top 1%, 5%, 10%) usando `Is_Dont_Go` apenas como ground truth de validação (CM 4.3 — abordagem "label de anomalia")
  - [ ] **Critério de abort (hora 1)**: se IF não rodar em tempo viável (> 1h em matriz v2 completa) ou Recall@10% < baseline aleatório, abandonar e registrar tentativa em `controle_alteracoes.md` — sem custo afundado significativo
  - [ ] Enquadrar no relatório como **diagnóstico complementar**, NÃO modelo competidor — tabela à parte, não entra na ROC/PR principal junto a LightGBM/Sobrevivência (comparação seria enviesada)
  - [ ] Salvar `Projeto/modelos/isolation_forest.joblib` + `Projeto/relatorio/tabelas/if_diagnostico.csv`
- [ ] Registrar em `controle_alteracoes.md` escolha de hiperparâmetros, modelo vencedor (LightGBM ou Sobrevivência), decisão de calibração, e resultado do IF (convergiu / aborted)

**Entregável:** 3 modelos supervisionados/sobrevivência (baseline + LightGBM + Sobrevivência) + Isolation Forest como diagnóstico complementar + Fig 9, Fig 11, Fig 12 + ablation_grupos.csv + calibração + tabela de hazard ratios + tabela IF (AUC-PR / Recall@K).

#### Observações e Conclusões (W6)

*(A preencher quando observações de W6 forem investigadas — origem: `Projeto/relatorio/observacoes_importantes.md` ou novas descobertas durante a semana.)*

---

### W7 (24-30/06) — Análise final + respostas Q3/Q6/Q7 → MARCO 2

**Objetivo:** pipeline analítico fechado. A partir daqui só escrita.

- [ ] `Projeto/codigo/09_evaluation.py`:
  - [ ] **Fig 10** — Matriz de confusão do modelo escolhido com anotações de impacto operacional (CM 5.2)
  - [ ] Análise dos falsos negativos: que TAGs/frotas/operadores escapam?
  - [ ] **[Qualidade C] Análise de erro estratificada**: matriz de confusão e métricas por **frota** e por **tipo** (Caminhão vs. Escavadeira) — modelo não pode falhar mais em uma frota
  - [ ] Drift mensal: AUC-PR mês a mês no teste
  - [ ] Tabela custo-benefício: FN × FP × limiar ótimo
- [ ] **Fig 13** — Comparação visual de performance: baseline vs. modelos desenvolvidos (CM 6.1)
- [ ] **Q3:** análise da feature `taxa_DG_operador_30d` via SHAP
- [ ] **Q6:** definir faixas de probabilidade → ações (continuar/preventiva/parar)
- [ ] **Q7:** ranking priorizado de inspeção por turno (top 5 TAGs)
- [ ] Tradução de Recall/Precision em horas de parada evitada e custo monetário estimado
- [ ] **[Qualidade B] Distribuição do tempo de antecipação**: P25 / mediana / P75 / P95 — não só média. Histograma do tempo entre predição positiva e DG real
- [ ] **[Qualidade E] Sanity check do viés inerente**: discussão honesta de que `Is_Dont_Go` é gerado pelas regras CMA, então o modelo aprende a antecipar a regra (não a falha física real). **Agora reforçado empiricamente pelo Isolation Forest do W6** — não é só retórica
- [ ] **[K — análise "o que a regra não vê"] (~2h)**: a partir dos resultados do IF no teste (jun):
  - [ ] Selecionar top-100 TAG×timestamp com maior anomaly score que **não** dispararam `Is_Dont_Go`
  - [ ] Examinar eventos/criticidades nas 4h seguintes — há concentração de níveis Alto/Muito Alto acima da base?
  - [ ] Cruzar com TAGs/frotas — algum grupo específico aparece desproporcionalmente?
  - [ ] **Fig Extra F** — barplot top-N TAGs anômalos × prevalência de eventos não cobertos pela regra
  - [ ] Conclusão honesta em 1 parágrafo: o sinal não supervisionado **complementa** (encontra modos de falha além da regra), **dispensa** (recupera os mesmos DGs sem ver rótulo), ou apenas **duplica** o sinal da regra?
- [ ] **Insights não óbvios** (CM 6.1): seção específica em rascunho com 3-5 achados surpreendentes ou contra-intuitivos da análise
- [ ] Atualizar `rascunho.md` com seção Avaliação e Resultados
- [ ] Registrar em `controle_alteracoes.md` escolha do limiar de operação

**Entregável:** todas as 6 perguntas respondidas + Fig 10 + Fig 13 + Fig Extra F + análise estratificada + distribuição de antecipação + análise "o que a regra não vê" + seção de insights.

#### Observações e Conclusões (W7)

*(A preencher quando observações de W7 forem investigadas — origem: `Projeto/relatorio/observacoes_importantes.md` ou novas descobertas durante a semana.)*

---

### W8 (01-07/07) — Escrita do relatório → MARCO 3

**Objetivo:** rascunho completo em markdown.

- [ ] Introdução (1-2 pp)
- [ ] Entendimento do Negócio (2-3 pp) — incluir obrigatoriamente:
  - [ ] **Cenário de aplicação operacional concreto** (CM 1.2): descrever como o modelo entra no fluxo da operação — ex: "score recalculado a cada início de turno, top-N TAGs com probabilidade > limiar aparecem no painel do dispatcher de Itabira com 4h de antecedência, gerando ordem de inspeção para a manutenção". Definir cadência, consumidor (dispatcher / manutenção / planejamento), e ação esperada
- [ ] Metodologia (8-10 pp) — EDA + Preparação + Modelagem
- [ ] Resultados e Discussões (5-7 pp) — Avaliação + respostas Q1-Q7
- [ ] **Limitações (seção própria, ~0,5-1 p)** (CM 6.2) — discussão honesta e explícita: volume coberto (6 meses, jan-jun/2025), região única (Itabira), features ausentes (manutenção preventiva, clima, sensores de vibração), generalização para outras frotas/regiões, viés inerente do `Is_Dont_Go`. **A inclusão do Isolation Forest não supervisionado (W6/W7) endereça parcialmente esse viés ao mostrar empiricamente quanto da estrutura dos DGs é recuperável sem ver o rótulo — limitação fica discutida com evidência, não só com retórica.**
- [ ] Conclusão (1 p) + Trabalhos Futuros (1 p) — **mínimo 3 propostas concretas e justificadas** (CM 6.3):
  - [ ] Q2 (modelo multi-classe para tipo do alerta)
  - [ ] Integração de dados externos (manutenção preventiva, condições climáticas)
  - [ ] Modelo online com retraining mensal para combater drift detectado em W7
  - [ ] **Autoencoder LSTM** sobre série temporal bruta de telemetria — extensão natural do Isolation Forest já entregue, mas com estrutura temporal explícita; requer GPU não disponível neste ciclo
  - [ ] **Validação prospectiva com dados de manutenção corretiva**: usar registros de intervenção física (não disponíveis no escopo atual) para validar se as anomalias detectadas pelo IF correspondem a falhas reais, fechando o ciclo do diagnóstico complementar
- [ ] **Resumo (500 palavras) — escrever por último**
- [ ] Revisar todas as figuras: legendas, eixos, fontes grandes para .docx

**Entregável:** `rascunho.md` ~25 páginas equivalentes.

#### Observações e Conclusões (W8)

*(A preencher com observações que emergem da própria escrita do relatório — frequentemente o ato de escrever revela buracos analíticos.)*

---

### W9 (08-14/07) — Migração para template + revisão

**Objetivo:** versão `.docx` final pronta.

- [ ] Migrar markdown → `Projeto/Alterado/Desenvolver_Template.docx`
- [ ] Inserir figuras com legenda numerada
- [ ] Formatar tabelas
- [ ] 2 leituras críticas (manhã + tarde de dias diferentes)
- [ ] Checklist dos 6 CMs cobertos
- [ ] Anexos: dicionário de features + tabela ANTES/DEPOIS
- [ ] Validar referências bibliográficas

**Entregável:** `Projeto/relatorio/relatorio_final.docx`.

#### Observações e Conclusões (W9)

*(A preencher com observações da revisão crítica — inconsistências, contradições, ou pontos que precisam de ajuste final.)*

---

### W10 (15-20/07) — Buffer + entrega

**Objetivo:** enviar entre 18-19/07 (não deixar para 20/07).

- [ ] Última revisão completa (1 dia de leitura corrida)
- [ ] Empacotar: relatório.docx + código.zip + README
- [ ] Backup OneDrive/Drive antes de enviar
- [ ] Enviar para `projetodesenvolver@vale.com`
- [ ] Salvar confirmação de envio

**Entregável:** e-mail enviado.

#### Observações e Conclusões (W10)

*(A preencher com retrospectiva final — o que aprendi, o que faria diferente, lições para próximos projetos.)*

---

## 7. Marcos e gates

| Marco | Quando | Critério de passagem |
|---|---|---|
| **MARCO 1** | Fim W5 (16/06) | LightGBM bate o baseline em AUC-PR no teste |
| **MARCO 2** | Fim W7 (30/06) | Pipeline analítico fechado; respostas Q1-Q7 prontas |
| **MARCO 3** | Fim W8 (07/07) | Rascunho completo em markdown |

Se algum gate falhar: **pare, diagnostique, ajuste plano antes de avançar.**

---

## 8. Controle de Alterações (prática contínua)

O Estudo Guiado exige (Nota da página 1):
> *"Sempre que uma alteração, exclusão ou decisão metodológica relevante for tomada, registre o ANTES e o DEPOIS com a justificativa correspondente."*

Por isso, **`Projeto/relatorio/controle_alteracoes.md`** é alimentado durante TODO o projeto (não só na limpeza). Toda vez que uma decisão metodológica for tomada — janela de predição, definição do target, filtro de classe, escolha de modelo, limiar — registrar com o template:

```markdown
### [Data] — [Tema da decisão]
- **ANTES:** estado anterior / opção descartada
- **DEPOIS:** estado novo / opção escolhida
- **Justificativa:** por que mudou
- **Impacto:** o que isso afeta (volume, métrica, escopo)
```

Exemplos do que entra:
- W1: filtro de `Criticidade = Informacional` (perde 80% do volume mas zero positivos)
- W3: critério de outlier (IQR vs. ±3σ)
- W3: estratégia de imputação por coluna
- W4: definição da janela de predição (por que 4h, não 8h)
- W4: datas de corte do split
- W5: escolha do modelo baseline
- W6: hiperparâmetros vencedores do Optuna
- W7: limiar de probabilidade adotado

Esse arquivo é **anexo do relatório final** e mostra rastro analítico — diferencial em banca.

---

## 9. Plano B — cortes em caso de atraso

Cortar na ordem abaixo (do menos crítico para o mais crítico):

1. ✂️ **[Profundidade 1]** Sensibilidade de janela → manter só 4h argumentada operacionalmente
2. ✂️ **[Qualidade A]** Calibração → mencionar que "modelo requer Platt scaling em produção" (cortar **apenas** se Q6 puder operar com probabilidade bruta — verificar antes)
3. ✂️ **[Qualidade C]** Análise estratificada por frota → vira "limitação reconhecida"
4. ✂️ **[Profundidade 2]** Ablation por grupo de features → manter só importância via SHAP
5. ✂️ **[Qualidade B]** Distribuição do tempo de antecipação → fica só com média
6. ✂️ **[K — análise]** Encurtar "o que a regra não vê" para tabela top-10 sem investigação por TAG/frota (mantém treino IF + AUC-PR/Recall@K; perde só a profundidade analítica do W7)
7. ✂️ **[Profundidade 3]** Modelo de Sobrevivência → "abordagem alternativa discutida em Trabalhos Futuros" (custo de saída em W6 ~6h)
8. ✂️ **[K — completo]** Isolation Forest inteiro → vai para Trabalhos Futuros (cortar só se W6 estourar e o abort de hora 1 não tiver sido acionado; perde-se a evidência empírica do viés inerente)
9. ✂️ Walk-forward mensal → manter só split fixo jan-abr/mai/jun
10. ✂️ Análise de operador (Q3) → vira "limitação reconhecida"

**Não cortar nunca:**
- EDA com 6 figuras obrigatórias
- LightGBM com tuning
- SHAP
- Validação temporal
- Conclusão com impacto em horas de parada evitada
- Sanity check do viés inerente (custa só escrita, agrega muito)
- Insights não óbvios (CM 6.1 explicita)
- Cenário de aplicação concreto (CM 1.2)
- Seção de Limitações explícita (CM 6.2)
- Pelo menos a **tentativa documentada** do Isolation Forest (mesmo se aborted, o registro em `controle_alteracoes.md` mostra exploração metodológica)

---

## 10. Bitácora semanal

Toda **sexta-feira, 15 minutos**, preencher abaixo.

### Semana 1 (13-19/05)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 2 (20-26/05)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 3 (27/05-02/06)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 4 (03-09/06)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 5 (10-16/06) — MARCO 1
- Entregável feito? [ ]
- LightGBM bateu baseline em AUC-PR? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 6 (17-23/06)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 7 (24-30/06) — MARCO 2
- Entregável feito? [ ]
- Todas as 6 perguntas respondidas? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 8 (01-07/07) — MARCO 3
- Rascunho completo? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 9 (08-14/07)
- .docx pronto? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 10 (15-20/07)
- E-mail enviado? [ ] Data: ___/___/2026
- Confirmação salva? [ ]
- Horas reais investidas:
