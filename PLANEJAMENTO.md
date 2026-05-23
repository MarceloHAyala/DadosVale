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
    │   ├── 01_ingestao.py                   (W1) ✅
    │   ├── 02_correcao_tipos.py             (W1) ✅
    │   ├── 03_limpeza.py                    (W1 inspeção + W3 cleaning estendido — 12 etapas) ✅
    │   ├── 04_eda.py                        (W2) ✅
    │   ├── 05_features.py                   (W3 básicas ✅ / W4 avançadas 🔄)
    │   ├── 06_split.py                      (W4) — planejado
    │   ├── 07_baseline.py                   (W5) — planejado
    │   ├── 08_lightgbm.py                   (W5-W6) — planejado
    │   ├── 09_sobrevivencia.py              (W6 — Weibull AFT / Cox) — planejado
    │   ├── 10_evaluation.py                 (W7) — planejado
    │   ├── 11_isolation_forest.py           (W6 — 3ª abordagem não supervisionada) — planejado
    │   ├── exploracao_w2_obs.py             (W2, auxiliar — invest. de obs 2.1, 2.2, 2.5, 2.6, 2.7) ✅
    │   ├── exploracao_w3_sobreposicoes.py   (W3, auxiliar — invest. das 340 sobreposições → CA65789 / H1.4) ✅
    │   ├── extrai_eventos_muito_alto.py     (W2, auxiliar — extrai eventos_muito_alto.csv) ✅
    │   └── utils.py                         (planejado, se necessário)
    ├── dados/
    │   ├── intermediarios/                  (parquets pós-ingestão e limpeza — gitignored)
    │   └── features/                        (matriz pronta para modelo — gitignored)
    ├── modelos/                             (artifacts pickle/joblib — gitignored)
    └── relatorio/
        ├── figuras/                         (PNGs finais — 13 do guia + 3 extras)
        ├── tabelas/                         (CSVs: estatisticas, features, controle_alteracoes)
        ├── controle_alteracoes.md           (ANTES/DEPOIS de toda decisão metodológica)
        ├── hipoteses_eda.md                 (hipóteses levantadas na EDA)
        ├── observacoes_importantes.md      (checklist vivo de pendências e riscos)
        ├── notas_exploracao_inicial.md     (notas iniciais 11/05 — dicionário + CMA + Is_Dont_Go; base para CM 1.1 em W8)
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

- [X] **Fig 1** — Diagrama do fluxo operacional: ciclo de apontamento → telemetria → alerta (CM 1.1)
- [X] **Fig 2** — Distribuição temporal dos registros de apontamentos (volume por dia/hora) (CM 2.1) — `fig02_distribuicao_temporal_apontamentos.png`
- [X] **Fig 3** — Distribuição de alertas por TIPO × NÍVEL de criticidade (CM 2.2) — `fig03_tipo_x_criticidade.png` (stacked bar Tipo de equipamento × Criticidade, Informacional filtrado)
- [X] **Fig 4** — Série temporal: frequência de alertas DG ao longo do período (CM 2.2) — `fig04_serie_temporal_dgs.png` (2 subplots: total + split Crítico/Não-Crítico, MA 7d)
- [X] **Fig 5** — Heatmap de correlação entre features numéricas (CM 2.3) — `fig05_heatmap_correlacao.png`
- [X] **Fig 6** — Taxa de alertas por hora do dia e dia da semana (CM 2.3) → responde **Q5** — `fig06_heatmap_hora_dia.png`

**Figuras extras (agregam valor — fazer se tempo permitir, senão vão para anexo):**

- ~~Extra A — Sobrevivência empírica por frota: P(novo DG > t)~~ — **MOVIDA para W6** (saída natural do `09_sobrevivencia.py` com `lifelines.KaplanMeierFitter`)
- [X] **Extra B — Pareto top-10 alarmes precursores** *(promovido a obrigatório — alimenta diretamente a análise "o que a regra não vê" do W7, parte do diagnóstico K via Isolation Forest)* — `figExB_pareto_alarmes.png` confirma visualmente 87,3% do top 5
- ~~Extra C — Cadeia de eventos no caso CA65924 (do `desenvolver_dontgo.xlsx`)~~ — **MOVIDA para W4** (parte natural da investigação da Obs 2.3 — "padrão CA65924 é universal?")

**Outros entregáveis da semana:**

- [X] Análise da distribuição por **Frota / Tipo / Classe** → responde **Q4** — `dgs_por_frota_tipo_classe.csv` via **join temporal `join_asof`** (achado: 12,65% dos DGs ocorrem em estado `Manutenção`, gerou obs 2.7)
- [X] **Distribuição de alertas por TAG de equipamento** (Pareto/bar plot) — CM 2.2 pede explicitamente — `figExG_pareto_tags.png` (top-15 de 35 TAGs com telemetria)
- [X] **Tabela `eventos_muito_alto.csv`** listando eventos da CMA com NIVEL "Muito Alto" (CM 1.1) — colunas: TIPO / EVENTO / SITUACAO / QTD / TEMPO / NIVEL — **82 eventos** (76 'Muito Alto' + 6 'Muito alto' normalizados — ver `controle_alteracoes.md`). **Achado lateral:** 95,12% vêm de `ALARME OEM`, 3,66% de TENDÊNCIA, 1,22% de SISTEMA — reforça empiricamente o Risco 3.3 (label CMA é majoritariamente herdado dos alarmes do fabricante, não análise autônoma da Vale)
- [X] Escrever em `Projeto/relatorio/rascunho.md` seção EDA + achados de Q4 e Q5
- [X] **`Projeto/relatorio/hipoteses_eda.md`** — registrar TODAS as hipóteses levantadas (confirmadas e não confirmadas) com 1 parágrafo cada — **13 hipóteses indexadas em 6 temas** (2 ✅ confirmadas, 4 ❌ refutadas, 2 🟡 refutadas com reinterpretação, 5 🔄 pendentes para W3-W7)

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

##### 5. Obs 2.6 — Padrão temporal dos DGs: 3 regimes distintos, NÃO drift linear

<details>
<summary><b>Scripts e funções usadas</b></summary>

Funções `obs_2_6_nao_critico_mensal()` e `obs_2_6_extensao_critico_junho()` em [`Projeto/codigo/exploracao_w2_obs.py`](Projeto/codigo/exploracao_w2_obs.py). Para reproduzir:

```powershell
uv run python Projeto/codigo/exploracao_w2_obs.py
```

</details>

A hipótese inicial era que o salto 20% → 48% Não-Crítico fosse drift linear ou pico isolado. A investigação revelou algo bem mais rico: **três regimes temporais distintos com DUAS anomalias completamente diferentes em alarmes diferentes**.

**Distribuição mensal de DGs:**

| Mês | Crítico | Não-Crítico | Total | %NC | Regime |
|---|---:|---:|---:|---:|---|
| Jan | 2.077 | 504 | 2.581 | 19,5% | Baseline normal |
| Fev | 1.071 | **3.422** | 4.493 | 76,2% | ⚠️ **Anomalia A** (Engine Coolant NC) |
| Mar | 771 | **3.452** | 4.223 | 81,7% | ⚠️ **Anomalia A** (pico) |
| Abr | 837 | 1.322 | 2.159 | 61,2% | Recuperação |
| Mai | 685 | 595 | 1.280 | 46,5% | Quase-normal |
| Jun | **4.845** | 381 | 5.226 | 7,3% | ⚠️ **Anomalia B** (Right Front Brake C) |

**O "salto" 20% → 48% era uma média mentirosa**: a média semestre nivela 2 anomalias opostas — nunca houve um mês com 48% de fato.

### Anomalia A — Engine Coolant Level Active (Fev-Mar) — Não-Crítico

| Mês | Não-Crítico | vs Jan |
|---|---:|---:|
| Jan | 259 | 1× |
| Fev | 2.414 | **9,3×** |
| Mar | 2.741 | **10,6×** |
| Abr | 1.261 | 4,9× |
| Mai | 538 | 2,1× |
| Jun | 292 | 1,1× |

### Achado bônus inesperado: a Anomalia A é também uma RECLASSIFICAÇÃO de severidade

Olhando totais combinados (Crítico + Não-Crítico) do **mesmo alarme**:

| Mês | Crítico | Não-Crítico | Total | Mix Crítico |
|---|---:|---:|---:|---:|
| Jan | 1.246 | 259 | 1.505 | **83%** |
| Fev | 276 | 2.414 | 2.690 | **10%** |
| Mar | 177 | 2.741 | 2.918 | **6%** |
| Abr | 186 | 1.261 | 1.447 | 13% |
| Mai | 152 | 538 | 690 | 22% |
| Jun | 73 | 292 | 365 | 20% |

**Duas coisas aconteceram simultaneamente em fevereiro:**
1. O volume total do alarme quase dobrou (1.505 → 2.690, +79%)
2. A severidade migrou massivamente de Crítico para Não-Crítico (83% → 10% Crítico)

Hipótese mais provável: **recalibração de threshold ou regra CMA em fevereiro** que rebaixou a severidade dos eventos Engine Coolant Level. A reversão parcial em maio-junho (20% Crítico) sugere ajuste posterior. Registrado como **Obs 2.8** em `observacoes_importantes.md` para auditoria interna na Vale.

### Anomalia B — Right Front Brake Temperature (Junho) — Crítico

Um único alarme explica **87,7% dos 4.845 DGs Crítico de junho** (4.247 ocorrências):

| Mês | Right Front Brake Crítico | Δ vs média Jan-Mai |
|---|---:|---:|
| Jan | 67 | — |
| Fev | 60 | — |
| Mar | 4 | — |
| Abr | 3 | — |
| Mai | 6 | — |
| Jun | **4.247** | **+151,7×** |

**Não é gradiente — é um evento estrutural pontual.** 4.247 ocorrências de um alarme que tinha entre 3 e 67 ocorrências nos meses anteriores. Hipóteses (registradas como **Obs 2.9** em `observacoes_importantes.md`):
- Recapagem em massa de pneus afetando termoregulação dos freios
- Sazonalidade térmica (final de outono / início inverno em Itabira)
- Mudança de turno operacional ou recalibração de sensor

### Implicação 1: Confirmação empírica e quantificada do Risco 3.2 (drift temporal)

- **Treino jan-abr** contém Anomalia A (Engine Coolant Não-Crítico)
- **Teste jun** contém Anomalia B (Right Front Brake Crítico)
- Right Front Brake Crítico tem **4 ocorrências em março, 3 em abril, 6 em maio** — estatisticamente invisível para o treino
- **O modelo provavelmente não aprenderá a antecipar o alarme dominante do teste**

Decisão metodológica atual (16/05/2026): **manter split fixo jan-abr/mai/jun** e tratar o drift como **tema central** de W7 (análise de erro mensal) e W8 (seção Limitações). Decisão final será registrada em `controle_alteracoes.md` quando W4 implementar o split.

### Implicação 2: Família nova de features para W4 — não substitui, agrega ao plano

Os achados validam uma família de features que não estava prevista no plano original de W4:

- **Razão vs baseline histórico do próprio alarme:** para cada alarme X, `count_X_ultimos_7d / baseline_X_30d_anterior`. Captura "este alarme está disparando muito mais que o normal pra ele" → Right Front Brake teria sinal forte em junho mesmo sem dados históricos do alarme no treino
- **Desvio do regime de criticidade:** features como `razao_Critico_Nao_Critico_ultimos_14d / baseline_60d`. Captura a inversão Engine Coolant Fev-Mar

Rolling windows simples (já planejadas) **permanecem**; essa família **adiciona** dimensão regimal.

### Implicação 3: Narrativa central para o relatório (W7-W8)

> *"A análise mensal revelou que o semestre não é estatisticamente homogêneo. Três regimes distintos foram identificados: (i) baseline em janeiro; (ii) anomalia Engine Coolant Não-Crítico em fevereiro-março, combinando aumento de volume (+79%) com reclassificação massiva de severidade (83% → 6% Crítico); (iii) anomalia Right Front Brake Temperature Crítico em junho (151,7× a média histórica do alarme). O modelo enfrenta non-stationarity REAL na operação, não simulada. Métricas serão reportadas mês a mês na avaliação para expor o impacto do drift. Recomendações operacionais incluem auditoria da regra CMA entre janeiro e fevereiro (causa provável da inversão Engine Coolant) e investigação do evento operacional de junho que disparou o pico Right Front Brake."*

---

##### 6. Obs 2.7 — DGs em Manutenção: 3 hipóteses testadas, H2 reinterpretada

<details>
<summary><b>Script e função usada</b></summary>

Função `obs_2_7_manutencao_posicao_relativa()` em [`Projeto/codigo/exploracao_w2_obs.py`](Projeto/codigo/exploracao_w2_obs.py). Para reproduzir:

```powershell
uv run python Projeto/codigo/exploracao_w2_obs.py
```

</details>

Os 2.525 DGs em Manutenção foram analisados via **posição relativa** de `Data_Evento` em `[Inicio, Fim]` do ciclo de apontamento ativo. Resultados de 4 sinais diagnósticos:

**Sinal 1 — Estatísticas:** mediana = **38,6%**, média = 42,2%, p10 = 6,5%, p90 = 83,9%. Já elimina H1 como dominante (esperaria mediana próxima de 0).

**Sinal 2 — Histograma (10 buckets de 10%):**

| Bucket | n | % | vs Uniforme |
|---|---:|---:|---|
| 0-10% | 385 | **15,3%** | +5,3pp (viés inicial) |
| 10-20% | 348 | 13,8% | +3,8pp |
| 20-30% | 304 | 12,0% | +2,0pp |
| 30-40% | 265 | 10,5% | +0,5pp |
| 40-50% | 232 | 9,2% | -0,8pp |
| 50-60% | 251 | 9,9% | -0,1pp |
| 60-70% | 206 | 8,2% | -1,8pp |
| 70-80% | 207 | 8,2% | -1,8pp |
| 80-90% | 168 | 6,7% | -3,3pp |
| 90-100% | 159 | 6,3% | -3,7pp |

Distribuição **quase-uniforme com viés monotônico decrescente**. H1 esperaria > 40% no bucket 0-10%; temos só 15,3% — excesso de ~125 casos = **H1 contribui marginalmente (~5%)**.

**Sinal 3 — Top 10 alarmes em Manutenção:**

| Alarme | n | % |
|---|---:|---:|
| Engine Coolant Level | 1.409 | 55,8% |
| Aftercooler Level | 332 | 13,2% |
| Transmission Oil Level | 216 | 8,6% |
| Right Front Brake Temp | 158 | 6,3% |
| Parking Brake | 115 | 4,6% |

**São EXATAMENTE os top 5 alarmes de produção do semestre.** Zero alarmes de diagnóstico/bypass no top 10. H3 (bug CMA) rejeitada.

**Sinal 4 — Distribuição por contexto:** 86,1% dos 2.525 DGs vêm de alarmes do top 5 produção; 13,9% de outros alarmes (mas ainda alarmes operacionais legítimos).

### Veredito sobre as 3 hipóteses

| Hipótese | Status | Evidência |
|---|---|---|
| **H1** — DG causou transição | **Rejeitada como dominante**, contribui ~5% | Bucket 0-10% tem 15,3% (esperaria > 40% se dominante) |
| **H2** — Falsos positivos de bancada | **Distribuição correta, NOME errado** | Uniforme confirmado, mas reinterpretação necessária ↓ |
| **H3** — Bug CMA / alarmes de diagnóstico | **Rejeitada empiricamente** | 86,1% vêm de alarmes de produção; 0 alarmes de bypass no top 10 |

### Reinterpretação central da H2 (achado importante)

**Os 2.525 DGs em Manutenção NÃO são "falsos positivos de bancada"** (alarmes artificiais disparados por testes irreais). **São DGs LEGÍTIMOS ocorrendo durante ciclos de manutenção quando o equipamento é re-ativado para testes operacionais.**

Evidência decisiva: os top alarmes são Engine Coolant Level, Aftercooler Level, Brake Temperatures — alarmes que **dependem do equipamento estar OPERANDO** para serem detectáveis. Um sensor de coolant não dispara com motor desligado. Um termômetro de freio não acusa temperatura alta sem o equipamento estar em movimento.

**Cenário real reconstruído:** ciclos longos de Manutenção (que duram horas a dias) têm múltiplos episódios de ativação para teste operacional; cada teste é uma oportunidade de DG real. A distribuição quase-uniforme reflete os momentos arbitrários dos testes dentro do ciclo.

### Implicação para o target

Esses 2.525 DGs **NÃO são lixo a filtrar** — são DGs legítimos. Mas o **contexto operacional é diferente** do DG de produção: representam "condição anormal detectada em teste de manutenção", não "falha iminente em equipamento produzindo".

Para a pergunta **Q1 estrita** ("DG nas próximas 4h em equipamento OPERANDO"), esses 12,65% são **ruído contextual leve**: não invalidam o label, mas diluem o sinal de "DG operacional próximo".

### Implicação para o Risco 3.3 (viés do label CMA)

O Risco 3.3 é **PARCIALMENTE REFUTADO** nesta análise: os 2.525 DGs em Manutenção **não** eram a "primeira evidência direta" de viés do label como inicialmente registrado — eles são DGs reais. O Risco 3.3 continua existindo (a regra CMA define o positivo, não a falha física), mas **perde essa quantificação fácil**. A validação empírica do viés do label CMA agora depende exclusivamente do **Isolation Forest diagnóstico em W6**.

---

### W3 (27/05-02/06) — Limpeza + features básicas

**Objetivo:** matriz v1 com 10-15 features documentadas.

> **Nota arquitetural (decisão 2026-05-17 — Opção 1):** o script `03_limpeza.py` **já existe** (criado em W1) com as etapas básicas: normalização de Criticidade, verificação de duplicados, frequência de registros, estatísticas descritivas. As etapas de limpeza avançada de W3 (outliers em `Valor`, missing values por coluna, registros com `Inicio > Fim`, sobreposições de ciclo, aplicação do filtro de `Informacional`) serão **adicionadas ao mesmo script** como etapas 7+ — **não** em um novo `03b_limpeza_avancada.py`. Razão: pipeline mais simples (um único script de limpeza), evita carga dupla do parquet, e mantém o `telemetria_limpa.parquet` como artefato único e canônico de saída da fase de limpeza. A decisão também será registrada em `controle_alteracoes.md` quando a primeira etapa de extensão for implementada.

- [X] **Estender `Projeto/codigo/03_limpeza.py`** com tratamento de outliers em `Valor` — **adotado threshold físico `Valor > 1000` em vez de IQR** (distribuição zero-inflada). **Achado:** 0 outliers no dataset filtrado (todos os 118 do W1 eram `Informacional`, eliminados na etapa 6). Etapa mantida como validação defensiva.
- [X] **Estratégia de missing values por coluna** (CM 3.1): **Achado:** apenas `telemetria.Valor` tem nulls (237.443, 43,58% do dataset filtrado); apontamentos com 0 nulls. Decisão: manter null (LightGBM aceita NaN); avaliar feature `valor_disponivel = Valor IS NOT NULL` em W4. Registrado em `controle_alteracoes.csv` e `controle_alteracoes.md`.
- [X] Tratar registros com `Inicio > Fim` nos apontamentos — **Achado:** 0 registros inválidos.
- [X] **Detecção de sobreposições de ciclo** (CM 3.1): **Achado novo (não previsto):** 340 sobreposições (0,09%) em apontamentos. Adicionada flag `is_sobreposicao`; investigação de concentração por Frota/TAG fica como follow-up.
- [X] **Aplicar filtro `Criticidade = "Informacional"` no `03_limpeza.py`** — 36.619.169 linhas removidas; 19.962 DGs preservados (asserção). `telemetria_limpa.parquet` agora persiste filtrado (7 MB vs 435 MB antes).
- [X] Tabela ANTES/DEPOIS em `Projeto/relatorio/tabelas/controle_alteracoes.csv` com **colunas exatas do CM 3.1**: Campo / Problema Identificado / Qtd. Registros / Tratamento Aplicado / Justificativa — 5 entradas geradas.
- [X] `Projeto/codigo/05_features.py` — features básicas (concluído 2026-05-17):
  - [X] `hora_dia`, `dia_semana`, `turno`, `mes` + `valor_disponivel` (5 features no total) — ver `documentacao_features.csv`
  - [ ] **Encoding categórico documentado para as 5 categorias** (CM 3.2) — decisão por cardinalidade:
    - `Tag` (alta cardinalidade, ~centenas de equipamentos) → **target encoding** com smoothing + KFold para evitar leakage
    - `Frota` (média cardinalidade) → **target encoding**
    - `Tipo` (baixa cardinalidade, ~5-10 categorias) → **one-hot**
    - `Classe` (baixa-média cardinalidade) → **one-hot** ou **frequency encoding** conforme contagem distinta
    - `Operador` (alta cardinalidade, anonimizado) → **frequency encoding** + feature derivada `taxa_DG_operador_30d` (semântica útil sem one-hot explodindo dimensão)
  - [ ] Registrar a justificativa de cada escolha em `documentacao_features.csv` (coluna Motivação)
- [X] Salvar `Projeto/dados/features/v1.parquet` — 544.885 linhas × 24 colunas (19 originais + 5 features), 6,9 MB
- [X] Iniciar **`Projeto/relatorio/tabelas/documentacao_features.csv`** (CM 3.2): 5 features documentadas com nome / tipo / descrição / fórmula / motivação / semana_criada
- [X] Registrar em `controle_alteracoes.md` decisões de limpeza (filtros, outliers, missing values, sobreposições) — entrada `2026-05-17` consolidando as 6 etapas da extensão

**Entregável:** matriz v1 + tabela ANTES/DEPOIS + documentacao_features.csv iniciado.

#### Observações e Conclusões (W3)

##### 1. As 340 sobreposições de ciclo são bug pontual do equipamento CA65789

<details>
<summary><b>Script usado para investigar</b></summary>

[`Projeto/codigo/exploracao_w3_sobreposicoes.py`](Projeto/codigo/exploracao_w3_sobreposicoes.py) — análise das 340 sobreposições flagadas por `03_limpeza.py` (etapa 10) decompondo por Frota, TAG, Tipo, Classe, mês e magnitude. Para reproduzir:

```powershell
uv run python Projeto/codigo/exploracao_w3_sobreposicoes.py
```

</details>

A etapa 10 de `03_limpeza.py` detectou 340 sobreposições temporais de ciclos em apontamentos (0,09% do total). Como 0,09% está acima do threshold automático de remoção (0,01%) mas abaixo do threshold de impacto material, foi adicionada flag `is_sobreposicao` e o caso passou para investigação dedicada. O resultado foi dramaticamente concentrado:

**Concentração por dimensão:**

| Dimensão | Concentração |
|---|---|
| **Equipamento (TAG)** | **CA65789** sozinho = **100%** (1 de 47 TAGs) |
| **Frota** | 793-D 2S = 100% (1 de 5 frotas) |
| **Tipo** | Caminhão = 100% |
| **Mês** | Jan/2025 = 90% (306); Abr = 5%; Jun = 5% |

**Detalhamento do equipamento CA65789:**
- 12.118 apontamentos totais no semestre (2,1% do dataset)
- 2,81% dos apontamentos dele têm sobreposição (vs 0% em todos os outros 46 equipamentos)
- Não está no top 15 de DGs (não é o CA65926 outlier de W2)

**Magnitude dos overlaps:** mediana 60 min, máximo 60 min, mínimo 0,1 min. 55% dos overlaps têm 1-6h de duração, 35% têm 10-60 min. Nenhum > 24h.

**Distribuição por estado operacional dos ciclos sobrepostos:**

| Estado | n | % |
|---|---:|---:|
| Operando | 133 | 39,1% |
| **Hibernando** | **119** | **35,0%** ⚠️ |
| Parado | 72 | 21,2% |
| Manutenção | 16 | 4,7% |

**Diagnóstico:** **BUG PONTUAL no CA65789, NÃO padrão sistêmico.** Evidências:
- 100% das sobreposições em 1 único equipamento (concentração máxima possível)
- 90% concentradas em janeiro de 2025 (padrão temporal localizado)
- 35% dos ciclos sobrepostos em estado **`Hibernando`** — fisicamente estranho (equipamento "dormindo" não deveria gerar dois ciclos simultâneos)

**Recomendação operacional para Vale (CM 6.1):** auditar a *pipeline* de registro de apontamentos do CA65789 no período de janeiro de 2025 — provável bug específico no sistema fonte, possivelmente envolvendo dupla baixa do equipamento ao entrar em Hibernando.

**Implicação para modelagem (W4-W7):** as 340 linhas flagadas vêm todas de um equipamento — não distorcem o dataset agregado. A flag `is_sobreposicao` pode ser usada como feature em W4 (mas tem cardinality muito baixa) ou simplesmente ser usada para diagnóstico estratificado em W7 (análise de CA65789 separadamente).

**Follow-up gerado:** nova obs **2.10** em `observacoes_importantes.md` — verificar se CA65789 apresenta outras anomalias além das sobreposições (taxa de DG, distribuição de alarmes, padrão operacional). Pode ser que esse equipamento tenha um perfil completo de "outlier de qualidade de dados" análogo ao perfil de outlier de DGs do CA65926 (W2).

**Nova hipótese registrada em `hipoteses_eda.md`:** **H1.4** — "Qualidade de dados de apontamento em CA65789 é localmente comprometida" (Confirmada por convergência de 4 evidências: 100% sobreposições, 90% em jan/2025, 35% em estado Hibernando, ausência de problema similar em outros 46 equipamentos).

---

##### 2. Extensão da limpeza (03_limpeza.py etapas 6-12) — encerramento da fase de Preparação dos Dados

<details>
<summary><b>Comando executado</b></summary>

```powershell
uv run python Projeto/codigo/03_limpeza.py
```

Script reescrito como pipeline de 12 etapas: 1-5 inspeção (W1), 6-10 cleaning (W3), 11-12 persistência + audit log. Detalhe completo em `controle_alteracoes.md` (entrada 2026-05-17).

</details>

Achados quantitativos das 5 etapas novas:

| Etapa | Achado | Decisão |
|---|---|---|
| 6 — Filtrar `Informacional` | 36.619.169 linhas removidas; 19.962 DGs preservados | Persistido no parquet (era no-op de runtime antes) |
| 7 — Outliers em `Valor` | **0 outliers** no dataset filtrado — os 118 do W1 eram todos `Informacional` | Etapa mantida como validação defensiva |
| 8 — Missing values | `Valor`: 43,58% de nulls (todos em eventos Crítico/Não-Crítico); apontamentos: 0 nulls | Manter null (LightGBM aceita); criar feature derivada `valor_disponivel` em W3 (etapa abaixo) |
| 9 — `Inicio > Fim` apontamentos | 0 registros inválidos | Sem tratamento |
| 10 — Sobreposições | 340 (0,09%) — todas do CA65789 (ver subseção 1) | Flag `is_sobreposicao` + investigação dedicada |

**Impacto:** `telemetria_limpa.parquet` cai de 435 MB → 7 MB (98% redução). Pipeline downstream agora consome dataset já filtrado e flagado.

---

##### 3. Features básicas criadas (05_features.py) — 5 features em v1.parquet

<details>
<summary><b>Comando executado</b></summary>

```powershell
uv run python Projeto/codigo/05_features.py
```

Script `05_features.py` (W3): 5 etapas — carga → temporais (4) → valor_disponivel (1) → validação (7 asserções) → persistência (v1.parquet + documentacao_features.csv).

</details>

5 features básicas adicionadas à matriz (passou de 19 para 24 colunas em 544.885 linhas):

| Feature | Tipo | Fórmula | Motivação (achado de origem) |
|---|---|---|---|
| `hora_dia` | Int8 (0-23) | `Data_Evento.dt.hour()` | Q5 — pico segunda 23h (Fig 6) |
| `dia_semana` | Int8 (1-7) | `Data_Evento.dt.weekday()` | Q5 — segunda-feira é pior dia |
| `turno` | String | "Diurno" se `Inicio_Turno.hour()==6`, senão "Noturno" | Operação 24×7 em turnos de 12h |
| `mes` | Int8 (1-6) | `Data_Evento.dt.month()` | 3 regimes temporais (Anomalias A e B — H3.1) |
| `valor_disponivel` | Bool | `Valor.is_not_null()` | Achado W3: 43,58% dos eventos não têm Valor numérico — sinal binário "alarme com medição" |

**Achado lateral (sanity check via distribuição):** mesmo após filtrar `Informacional`, a distribuição mensal de eventos relevantes ainda reflete os 3 regimes (Anomalia A em fev-mar gera 80% mais eventos que junho — 128k vs 71k). Confirma H3.1 visualmente por uma terceira via:

| Mês | Eventos | % |
|---|---:|---:|
| Jan | 80.955 | 14,9% |
| **Fev** | **102.677** | 18,8% |
| **Mar** | **128.011** | **23,5%** (pico) |
| Abr | 83.328 | 15,3% |
| Mai | 78.825 | 14,5% |
| Jun | 71.089 | 13,0% |

**Saídas:** `dados/features/v1.parquet` (6,9 MB) + `relatorio/tabelas/documentacao_features.csv` (CM 3.2 com 5 entradas).

**Pendente para W4:** encoding categórico (5 categorias: Tag/Frota/Tipo/Classe/Operador), rolling windows 1h/4h/24h, features de recência, `taxa_DG_operador_30d`, `estado_pre_evento` (join_asof com apontamentos), família regimal (razão vs baseline próprio).

---

### W4 (03-09/06) — Features avançadas + definição do target + split

**Objetivo:** matriz final v2 + datas de corte definidas + target documentado.

- [X] Rolling windows por TAG: contagem de eventos por criticidade nas últimas 1h, 4h, 24h — **9 features** (`count_critico/nao_critico/total × 1h/4h/24h`), implementado em `05_features.py` via `rolling_sum_by(closed="left").over("TAG")`. Asserção: `count_total = count_critico + count_nao_critico` exata.
- [X] Features de recência: `horas_desde_ultimo_DG`, `horas_desde_ultimo_critico` — implementado via `shift(1).forward_fill().over("TAG")`. Achado: 5.104 eventos com `horas_desde_ultimo_critico = 0` (0,94%) indicam cascata de alarmes simultâneos.
- [ ] Features de operador: `taxa_DG_operador_30d` → base para **Q3**
- [ ] Features de regra de negócio: `qtd_alarmes_nivel_muito_alto_360min`
- [X] **[Novo após Obs 2.7]** Feature `estado_pre_evento` — implementada via `join_asof(strategy="backward", t-1h)` com filtro `Data_Evento - 1h <= Fim`. **Achado:** apenas 106 eventos sem apontamento (0,02%) — cobertura quase perfeita. Distribuição: Operando 73,7% / Parado 17,8% / Manutenção 8,3% / Hibernando 0,2% / SEM_APONTAMENTO 0,02%. Reforça H5.1 (Manutenção tem ~1,5× mais DGs que sua representação no dataset).
- [X] **[Novo após Obs 2.6]** Família de features regimais — restrita aos 19 alarmes que geraram >=1 DG (alinhada com hipoteses_eda.md H2.1):
  - `razao_alarme_7d_vs_30d_anterior` — razão normalizada por dias entre frequência do alarme em 7d vs baseline 30d. NULL para alarmes fora dos top 19 (74,3% do dataset). 25,7% restante = ~140k eventos com 100% dos DGs cobertos.
  - `razao_severidade_14d_vs_60d` — razão (Crítico/NãoCrítico) em 14d vs 60d por TAG. NULL em 0,2% dos eventos (início do semestre sem 60d de histórico).
- [X] **Fig Extra C — Cadeia de eventos no caso CA65924** *(originalmente em W2, movida)* — implementada em [`exploracao_w4_ca65924.py`](Projeto/codigo/exploracao_w4_ca65924.py), saída [`figExC_ca65924_cadeia.png`](Projeto/relatorio/figuras/figExC_ca65924_cadeia.png). **Resultado: H5.2 refutada** — apenas 1 de 4 painéis confirma o padrão de volume; CA65924 tem fluxo uniforme (~1,25 eventos/min). Sub-hipótese de "acúmulo de criticidade" gerada (Obs 2.11). Detalhes em "Observações e Conclusões (W4)" subseção 5.
- [X] **Finalizar `documentacao_features.csv`** com fórmula+motivação de TODAS as features (CM 3.2 nota) — **29 entradas** consolidadas (5 básicas + 9 rolling + 2 recência + 1 estado + 2 regimal + 2 operador + 1 regra + 7 encoding), uma linha por feature com nome/tipo/descrição/fórmula/motivação/semana_criada.
- [X] Construir target: `y = 1` se houver evento DG na janela de +0 a +4h do equipamento (CM 3.3) — **3 colunas geradas** (`target_2h`, `target_4h`, `target_8h`) via padrão `reverse().shift(1).forward_fill().reverse().over("TAG")` para localizar o próximo DG futuro por equipamento. **Achado surpreendente:** taxa de positivos em `target_4h` = **29,3%** (vs expectativa inicial de ~0,054% da taxa global de DGs). Explicação: cada DG "reivindica" ~4h de eventos precedentes do mesmo equipamento como positivos — o problema permanece desbalanceado, mas em ordem de magnitude muito mais branda do que a inicialmente declarada na Introdução. Monotonicidade confirmada: 25,5% (2h) < 29,3% (4h) < 34,2% (8h). 18,83% dos eventos censurados (sem DG futuro observado no horizonte do dataset) tratados como `y = 0` — registrado como limitação a ser quantificada em W7.
- [X] **[Profundidade 1] Análise de sensibilidade da janela de predição — parte descritiva** (~2h): gerar targets paralelos para janelas de **2h, 4h e 8h** — feito em `05_features.py` etapa 11; tabela `sensibilidade_janela.csv` consolida taxas de positivos e distribuição por mês. **Pendente para W5:** treinar LightGBM com parâmetros default em cada janela e comparar AUC-PR/Recall no conjunto de validação para justificar empiricamente a escolha de 4h. Conclusão final será registrada em `controle_alteracoes.md` após a comparação preditiva.
- [X] **Fig 7** — Diagrama da janela de predição: instante de decisão → janela 4h → evento alvo (CM 3.3) — gerada em `06_split.py` (matplotlib, reproduzível). Saída: [`fig07_janela_predicao.png`](Projeto/relatorio/figuras/fig07_janela_predicao.png). Timeline -2h a +6h com instante de decisão `t`, janela `(0, 4h]` destacada em azul, DG hipotético dentro (target=1, X vermelho) e fora (descartado, X cinza), e legenda da semântica "janela aberta no início".
- [X] `Projeto/codigo/06_split.py` — split: treino jan-abr, val mai, teste jun — implementado em 5 etapas (carga → split → sumário → Fig 7 → Fig 8 → persistência). Saída: `dados/features/v2_split.parquet` (544.885 × 52 colunas, 14,9 MB; adiciona col `split ∈ {train, val, test}` ao v2.parquet). **Tempo: 2,6s.** Cortes nos limites de mês (`< 2025-05-01` / `< 2025-06-01`) — coerência direta com Fig 2 mensal.
- [X] **Fig 8** — Diagrama da estratégia de validação temporal (CM 4.1) — gerada em `06_split.py`. Saída: [`fig08_split_temporal.png`](Projeto/relatorio/figuras/fig08_split_temporal.png). 2 painéis verticais: barras mensais coloridas por split + linha de taxa de DG mês-a-mês (drift quantificado). **Drift confirmado:** taxa_dg 3.19% / 4.38% / 3.30% / 2.59% / **1.62%** (val) / **7.35%** (teste) — teste tem **4.5× a taxa de val** e **2.2× a média do treino**.
- [X] Escrever justificativa explícita do porquê não usar k-fold aleatório (data leakage) — registrada no docstring de `06_split.py` e em `controle_alteracoes.md` (2026-05-17 — Split temporal). Síntese: k-fold embaralha eventos no tempo → rolling features capturam autocorrelação → leakage massivo. Walk-forward respeita semântica temporal real (treina no passado, prediz futuro).
- [X] Salvar `Projeto/dados/features/v2.parquet` — feito na sessão anterior (29 features + 3 targets). `v2_split.parquet` é o sucessor canônico (mesmas linhas + col `split`); v2.parquet preservado como matriz "pré-split" para compatibilidade.
- [X] Registrar decisões em `controle_alteracoes.md` (janela 4h, definição target, datas de corte) — 3 entradas: 2026-05-17 sobre target multi-janela (sessão anterior); 2026-05-17 sobre split temporal walk-forward (esta sessão); a comparação preditiva entre janelas (2h/4h/8h) fica para W5 com baseline LightGBM.

**Entregável:** matriz v2 + documentacao_features.csv completa + Fig 7 + Fig 8.

#### Observações e Conclusões (W4)

##### 1. Cascata de alarmes — 5.104 eventos Críticos simultâneos

<details>
<summary><b>Script usado para gerar</b></summary>

Feature `horas_desde_ultimo_critico` em [`Projeto/codigo/05_features.py`](Projeto/codigo/05_features.py). Para reproduzir:

```powershell
uv run python Projeto/codigo/05_features.py
```

</details>

A feature `horas_desde_ultimo_critico` retornou **5.104 eventos com valor = 0** (0,94% do dataset) — eventos não-Critico que ocorrem **no exato mesmo `Data_Evento`** que um evento Critico do mesmo equipamento. Comparativamente, `horas_desde_ultimo_DG` teve apenas 479 valores = 0 (0,10%), ~10× menos.

A diferença não é uniforme — eventos Críticos simultâneos são **substantivamente mais frequentes que DGs simultâneos**. Hipótese mais provável: **alarmes em cascata** (múltiplos sensores disparando no mesmo instante em resposta a uma única falha física). Exemplo conceitual: queda súbita de pressão hidráulica pode disparar simultaneamente alarmes de temperatura de transmissão, vibração e nível de fluido.

**Implicação para modelagem:** `horas_desde_ultimo_critico = 0` é **sinal informativo legítimo** (não leakage temporal). O modelo aprenderá que "cascata em curso" é fator de risco. Asserção `>= 0` no script garante que não há valores negativos (que indicariam leakage real).

---

##### 2. Cobertura quase perfeita do `estado_pre_evento` — apenas 106 SEM_APONTAMENTO

Dos 544.885 eventos no dataset filtrado, apenas **106 (0,02%)** não tiveram um apontamento ativo 1h antes do evento (recebendo o sentinela `"SEM_APONTAMENTO"`). Confirma a **excelência da pipeline temporal de apontamentos da Vale** — ciclos operacionais estão registrados de forma quase contínua nos 6 meses observados.

Distribuição completa de `estado_pre_evento`:

| Estado pré-evento (1h antes) | Eventos | % | Comparativo W2 (DGs em Q4) |
|---|---:|---:|---|
| Operando | 401.494 | **73,7%** | 80,76% — DGs concentram em Operando |
| Parado | 96.945 | **17,8%** | 5,93% — DGs **sub-representados** em Parado |
| **Manutenção** | **45.267** | **8,3%** | **12,65%** — DGs **sobrepresentados ~1,5×** |
| Hibernando | 1.073 | 0,2% | 0,66% |
| SEM_APONTAMENTO | 106 | 0,02% | — |

**Achado:** o estado `Manutenção` tem **proporção de DGs ~1,5× maior do que sua representação no dataset** (12,65% / 8,3% = 1,52). Reforça empiricamente a H5.1 (DGs em Manutenção são legítimos de reativações operacionais de teste). Já o estado `Parado` tem o padrão inverso (5,93% / 17,8% = 0,33×) — equipamentos parados geram eventos mas raramente DGs, coerente com a operação normal.

---

##### 3. Família regimal — 74,3% NULL é o esperado e correto

A feature `razao_alarme_7d_vs_30d_anterior` retornou **NULL em 404.902 eventos (74,3%)** — exatamente o comportamento esperado pela restrição metodológica aos 19 alarmes top (decisão registrada em rascunho.md e hipoteses_eda.md H2.1).

Os **25,7% restantes (~140k eventos)** correspondem a eventos cujo `Alarme` está nos 19 que geraram pelo menos 1 DG no semestre. **100% dos DGs estão nessa fatia** (por definição) — portanto a feature **cobre integralmente o universo do target**, ainda que silente nos demais 4.383 alarmes do dataset.

Para a feature `razao_severidade_14d_vs_60d`, NULL em apenas 0,2% (1.234 eventos) — todos no **início do semestre** (sem 60 dias de histórico anterior). Comportamento esperado por construção do *rolling window*.

---

##### 4. Validação de coerência interna entre features

Asserção exata no script: `count_total_Xh == count_critico_Xh + count_nao_critico_Xh` para janelas de 1h, 4h e 24h. **Diff máximo = 0** em todos os 544.885 eventos. Confirma que as 9 features de rolling estão internamente coerentes e podem ser usadas de forma redundante (modelo pode aprender que `count_total` agrega ambos, ou usar separadamente).

---

##### Resumo de execução

Pipeline `05_features.py` (W3 + W4 parcial) executa em **~2 segundos** sobre 544.885 linhas + 377.907 apontamentos, gerando:
- `v1.parquet` (5 features básicas, 6,9 MB — compatibilidade retroativa)
- `v2_parcial.parquet` (19 features = 5 básicas + 14 avançadas, 19,6 MB)
- `documentacao_features.csv` (19 entradas no formato CM 3.2)

**Pendente para próxima sessão de W4:** features de operador (`taxa_DG_operador_30d`, `n_bypasses_operador_7d`), regra de negócio (`qtd_alarmes_nivel_muito_alto_360min`), encoding categórico (5 categorias), Fig Extra C (CA65924), target 4h + análise de sensibilidade, `06_split.py` + Fig 8.

---

##### 5. Refutação da H5.2 via Fig Extra C — padrão "calmaria → acúmulo → disparo" não é universal

<details>
<summary><b>Script usado para gerar</b></summary>

[`Projeto/codigo/exploracao_w4_ca65924.py`](Projeto/codigo/exploracao_w4_ca65924.py) — carrega o `desenvolver_dontgo.xlsx` (caso paradigma CA65924) e compara com 3 DGs aleatórios de outros TAGs (`telemetria_tipada.parquet`, `random.seed=42`). Para reproduzir:

```powershell
uv run python Projeto/codigo/exploracao_w4_ca65924.py
```

Saída: [`Projeto/relatorio/figuras/figExC_ca65924_cadeia.png`](Projeto/relatorio/figuras/figExC_ca65924_cadeia.png).

</details>

A Hipótese H5.2 ("o padrão calmaria → acúmulo → disparo do caso CA65924 é universal nos DGs") foi originalmente formulada a partir de observação qualitativa do caso paradigma (147 eventos consecutivos no caminhão CA65924 culminando em 1 DG). Testada empiricamente em W4 com a Fig Extra C, comparando o paradigma com 3 amostras aleatórias e métrica quantitativa de acúmulo (razão eventos_últimos_30min / eventos_primeiros_90min ≥ 2).

**Resultado quantitativo:**

| Painel | n eventos | Razão 30min/90min | Veredito |
|---|---:|---:|---|
| **CA65924** (paradigma) | 147 | **0,39** | ❌ Não confirma |
| CA5927 | 28 | 0,47 | ❌ Não confirma |
| **CA65908** | 19 | **3,75** | ✅ Confirma |
| CA65927 | 38 | 0,52 | ❌ Não confirma |

**Apenas 1 dos 4 painéis confirma o padrão de volume.** O próprio CA65924 — que deu nome à hipótese — não exibe o padrão pela métrica quantitativa: tem fluxo aproximadamente uniforme de ~1,25 eventos/min ao longo dos 2h pré-DG. A hipótese original parece ter sido extraída de observação qualitativa de "147 eventos seguidos antes de um DG", sem quantificação rigorosa da distribuição temporal.

**Reinterpretação visual emergente — acúmulo de criticidade**

A inspeção da figura revela um sub-padrão que a métrica de volume não captura: em **3 dos 4 painéis** (CA65924, CA5927, CA65908), eventos `Critico` (representados em vermelho na figura) concentram-se nos últimos minutos pré-DG, mesmo quando o volume total é distribuído uniformemente. O CA65924, por exemplo, tem 138 eventos Informacional + 7 Não-Crítico + apenas **1 evento Crítico — e esse único Crítico ocorre próximo ao DG**.

Sub-hipótese gerada: o padrão real é **"acúmulo de criticidade, não de volume"**. Concretamente, espera-se que a feature `count_critico_*h` (Família 1 do `05_features.py`) tenha importância maior que `count_total_*h` na análise SHAP do modelo principal em W6. Registrado em `observacoes_importantes.md` como **Obs 2.11** para validação empírica.

**Implicação para modelagem (W5-W7)**

- **Família de rolling counts** (volume-based) continua útil — capturou o caso CA65908 — mas **perde força como família dominante** das features. A expectativa anterior de que rolling seria o "core" preditivo deve ser revista.
- **Famílias com maior peso preditivo esperado:** regimal (razão vs baseline próprio, Família 4) e estado pré-evento (Família 3), que capturam **mudanças de comportamento e contexto operacional**, não apenas volume.
- **Validação obrigatória em W6:** SHAP global comparando `count_critico_*h` vs `count_total_*h` resolve formalmente a Obs 2.11.

**Implicação para o relatório (CM 6.1 — Insights Não Óbvios)**

Esta refutação é candidata forte para a seção de Insights Não Óbvios do relatório final. A narrativa: "uma hipótese formulada qualitativamente a partir de um caso emblemático foi refutada pela análise quantitativa, mas a investigação gerou uma sub-hipótese mais refinada que orienta a interpretação do modelo". Demonstra rigor metodológico e atenção a vieses de seleção (o caso paradigma não é necessariamente representativo).

---

##### 6. Fig 8 e drift mai→jun: 3 mitigações registradas para W5-W6

<details>
<summary><b>Script usado para gerar</b></summary>

Fig 8 gerada em [`Projeto/codigo/06_split.py`](Projeto/codigo/06_split.py) etapa 5/5. Tabela de sumário em [`Projeto/relatorio/tabelas/split_temporal.csv`](Projeto/relatorio/tabelas/split_temporal.csv). Para reproduzir:

```powershell
uv run python Projeto/codigo/06_split.py
```

</details>

A Fig 8 quantificou um **drift mensal forte e direcional** que tem consequências diretas para a modelagem em W5-W6 e merece registro explícito de mitigações antes que o piloto automático "LightGBM default com `class_weight='balanced'`" leve a decisões subótimas em W5. As taxas de DG por mês observadas: 3,19% (jan) / 4,38% (fev) / 3,30% (mar) / 2,59% (abr) / **1,62% (mai, val)** / **7,35% (jun, teste)** — teste tem **4,5× a taxa de val** e **2,2× a média do treino**.

Dois problemas operacionais emergem desse padrão:

1. **Validação em regime raro:** mai com 1,62% de taxa de DG é metade da média do treino. Hiperparâmetros tunados em mai serão otimistas em precisão e pessimistas em recall — métricas single-fold de mai têm alta variância e podem mascarar problemas reais.
2. **Drift mecânico identificado:** o salto para 7,35% em jun não é shift contextual genérico, é **a anomalia RFB** (`Right Front Brake Temperature - Active` explodindo 151,7× sobre baseline) já mapeada na Obs 2.6. Modelo treinado sem capturar sinal regimal vai degradar em jun.

**3 mitigações concretas registradas como tasks explícitas em W5-W6:**

- **Mitigação 1 (W6, antes do Optuna):** TimeSeriesSplit CV de 4 folds expandidos (jan→fev, jan-fev→mar, jan-mar→abr, jan-abr→mai) para tuning, em vez de validar só em mai. Usa ~5× mais sinal, reduz variância, atenua "mai como regime raro". Teste em jun continua intocado.
- **Mitigação 2 (W5, LightGBM v1):** comparar `scale_pos_weight` calibrado para taxa de treino (~2,0) vs taxa de produção esperada — não usar só `class_weight='balanced'` default, que assume distribuição estacionária.
- **Mitigação 3 (W5, GATE MARCO 1):** reportar AUC-PR/Recall/Precisão **estratificados mês-a-mês** desde o LightGBM v1 (não esperar W7). Critério do gate vira **2 critérios** (bate baseline em val E mantém AUC-PR razoável em teste com tolerância de queda ≤ 30%).

Sem essas mitigações registradas, W5 cairia no piloto automático e o drift só seria detectado tarde, em W7 — quando teria custado uma iteração inteira de tuning desperdiçada sobre métricas de validação não confiáveis.

**Implicação para o relatório (CM 6.1 + CM 6.2 + CM 6.3):**

- **CM 6.1 (Insights Não Óbvios):** o drift de jun tem causa mecânica nominal e identificável — RFB anomalia. Não é "modelo pode falhar por motivos desconhecidos", é "modelo precisa aprender o sinal regimal que detecta esse tipo de explosão". A Família 4 (`razao_alarme_7d_vs_30d_anterior`) foi desenhada proativamente para esse padrão.
- **CM 6.2 (Limitações):** validação em regime raro + drift de teste são limitações honestas que o relatório vai expor com magnitude exata (Fig 8 quantifica), não esconder.
- **CM 6.3 (Trabalhos Futuros):** retreinamento rolling mensal em produção é o caminho de mitigação operacional natural — registrar como Trabalho Futuro.

---

### W5 (10-16/06) — Baseline + LightGBM v1 → MARCO 1

**Objetivo:** modelo principal funcionando, batendo o baseline.

- [ ] **[Refinamento de W4 — adiado para W5 por dependência do target real]** Substituir `tag_freq` e `operador_freq` (frequency encoding implementado em `05_features.py`, Família 7) por **target encoding com KFold temporal**. **Motivação dupla:** (a) target encoding capta correlação com o target — mais informativo que frequency puro; (b) **fix de leakage subtil descoberto após o split** — ✅ **PARTE (b) RESOLVIDA EM 22/05 via `06b_fix_encoding_leakage.py`** (gerou `v3.parquet`; ver task de 06b acima e entrada controle_alteracoes 2026-05-22). Resta apenas a parte (a) — substituição por target encoding com KFold, que é o refinamento incremental mais ambicioso. Casos específicos identificados pós-split: 2 TAGs (`CA65791`, `CA65916`) aparecem só em val/teste e não em treino; 13 operadores em val/teste ausentes do treino — tratamento atual em `v3.parquet`: `freq = 0` para esses unknowns (Opção C-1, registrada em `notas_metodologicas.md` Seção 2). Implementação detalhada do target encoding refinado:
  - **Pré-requisito:** target real `y = 1 se DG em [+0, +4h]` (CM 3.3) construído em W4, e split temporal `06_split.py` definido (treino jan-abr / val mai / teste jun).
  - **Para cada categoria de alta cardinalidade** (`Tag` com 35 valores, `Nome_Operador_Anon` com 394 valores):
    1. Sobre o conjunto de **TREINO apenas** (jan-abr), particionar em K folds temporais (sugerido K=4: jan / fev / mar / abr).
    2. Para cada fold `i`: calcular `target_rate_categoria_x_out_of_fold_i = sum(y) / count(eventos)` usando **todos os outros K-1 folds** (não o fold `i`). Aplicar esse encoding aos eventos do fold `i`.
    3. Adicionar **smoothing** para reduzir overfitting em categorias raras: `target_smooth = (count_pos_categoria + α * media_global) / (count_categoria + α)` com α típico = 10. Categorias com poucos eventos no treino ficam puxadas para a média global, evitando ruído.
    4. Para val/test: aplicar encoding fitted sobre o treino **completo** (jan-abr inteiro, sem KFold).
  - **Validação empírica obrigatória:** comparar AUC-PR do LightGBM v1 (frequency encoding atual) vs LightGBM com target encoding nessas duas features. Critério: se ganho de AUC-PR em validação for > 1pp, substituir; se < 1pp, manter frequency (parsimônia + menos código).
  - **Saída esperada:** novas features `tag_target_enc` e `operador_target_enc` em `v2_5.parquet` ou substituição direta em `v2.parquet`. Registrar decisão final em `controle_alteracoes.md`.
  - **Onde resolver:** W5 (junto com o `07_baseline.py` e `08_lightgbm.py` — momento natural para a comparação empírica).
- [X] `Projeto/codigo/07_baseline.py` (executado em 22/05/2026, 0,4s) — heurística: DG=1 se houve crítico nas últimas 4h do mesmo TAG. **Foco em `target_4h` apenas** (pergunta operacional canônica do CM 1.2). Score raw para AUC-PR: `count_critico_4h` (perfeitamente alinhado com o horizonte do *target*). Thresholds binários reportados: 1, 2, 3, 5 (Mitigação 3 estratifica val/test). Decisão registrada após discussão no W5 pré-baseline: NÃO incluir `target_2h` e `target_8h` no baseline porque exigiria features adjacentes mal-alinhadas (`count_critico_1h` para 2h, `count_critico_24h` para 8h) que introduziriam viés metodológico — análise de sensibilidade da janela migra para `08_lightgbm.py` onde é metodologicamente correta. **Saída:** `relatorio/tabelas/baseline_metricas.csv` (8 linhas). Detalhes do achado em §4 das Observações e Conclusões abaixo.
- [X] Métricas baseline no teste de jun: Precision, Recall, F1, AUC-PR — **completas para val e test estratificados**. Resultado: AUC-PR val 0,2397 / test 0,5803 (test 2,42× val — achado contra-intuitivo). F1 máximo: val 0,3127 (threshold=1) / test 0,5243 (threshold=5). Forçou re-calibração do GATE MARCO 1 (ver task abaixo).
- [ ] **[Profundidade 1 — comparação preditiva entre horizontes do *target*, refinamento da análise descritiva já feita em W4]** Em `08_lightgbm.py`, treinar **3 variantes do LightGBM v1 com hiperparâmetros idênticos** mas *targets* diferentes:
  - **Variante T2:** `target_2h` como alvo
  - **Variante T4:** `target_4h` como alvo (canônica)
  - **Variante T8:** `target_8h` como alvo
  - Mesma matriz `v3.parquet` em todas as variantes (features completas — LightGBM tem acesso a `count_critico_1h/4h/24h` e pode usar as que fizerem sentido para cada horizonte). Mesmos hiperparâmetros *default* + mesma calibração de `scale_pos_weight` (Mitigação 2). Comparação rigorosa porque **só o *target* varia**.
  - **Métricas comparativas:** AUC-PR de cada variante em val e teste, estratificadas mai/jun (Mitigação 3). Registrar em tabela `relatorio/tabelas/comparacao_horizontes_lightgbm.csv`.
  - **Critério de decisão:** se T4 dominar em AUC-PR, justifica empiricamente a escolha operacional de 4h (CM 3.3 ganha fundamentação empírica em vez de só argumento operacional). Se T2 ou T8 forem melhores, é achado forte de CM 6.1 (Insight Não Óbvio: horizonte operacional ≠ horizonte ótimo preditivamente) e abre discussão de Trabalhos Futuros.
  - **Cenário de aprofundamento condicional:** se AUC-PR de T2 ou T8 ficar substancialmente abaixo de T4, investigar se a causa é falta de feature alinhada (não temos `count_critico_2h` nem `count_critico_8h` em `v3.parquet`). Nesse caso, voltar a `05_features.py` para adicionar essas 6 features (3 criticidades × 2 janelas) e re-rodar a comparação. **Não adicionar features preventivamente** — só se a evidência empírica justificar.
  - **Conclusão final registrada em `controle_alteracoes.md`** após a comparação preditiva (encerra a Profundidade 1, originalmente prevista para W4).
- [X] `Projeto/codigo/06b_fix_encoding_leakage.py` (executado em 22/05/2026, 4,8s) — **fix do leakage subtil de encoding** identificado no estudo prévio de W5. Recomputou `tag_freq` e `operador_freq` (Família 7) sobre o split de treino apenas (394.971 eventos) e propagou para val/teste; categorias unknown no treino receberam `freq = 0` (decisão Opção C-1, registrada em `notas_metodologicas.md` Seção 2 — feature binária `is_unknown` seria inerte em single-fold). **Saída:** `dados/features/v3.parquet` (544.885 × 52, 14,9 MB, input canônico para W5+). Diff médio de `tag_freq` 0,0507→0,0515 (+1,4%) e `operador_freq` 0,0070→0,0070 (-1,0%) — confirma que leakage era subtil mas presente. Casos de borda registrados: 2 TAGs e 13 operadores unknown afetando 1.812 eventos / 133 DGs em test (2,55% / 2,54%). Decisão completa em `controle_alteracoes.md` 2026-05-22.
- [ ] `Projeto/codigo/08_lightgbm.py` — LightGBM v1 com parâmetros default. **Encoding pré-modelagem:** ✅ FIX JÁ APLICADO em `06b_fix_encoding_leakage.py` (linha acima). O `08_lightgbm.py` deve ler `v3.parquet` diretamente como input canônico — não precisa reaplicar o fix. O **target encoding com KFold temporal** (refinamento mais ambicioso, listado abaixo) continua pendente como melhoria incremental.
- [ ] **[Mitigação 2 — derivada da Fig 8 W4, drift mai→jun 4,5×]** Comparar duas calibrações de `scale_pos_weight` em vez de só usar `class_weight='balanced'` default:
  - (a) `scale_pos_weight = (1 - taxa_train) / taxa_train ≈ 2.0` — calibrado para taxa do TREINO (33,64% positivos no `target_4h`).
  - (b) `scale_pos_weight` calibrado para taxa esperada de PRODUÇÃO (mistura realista do semestre, ou — mais agressivo — taxa do TESTE 16,93%). Justificativa: tuning sobre taxa de treino otimiza o objetivo errado quando há drift confirmado. Comparar AUC-PR e Recall das duas variantes no GATE MARCO 1. Registrar em `controle_alteracoes.md` qual venceu e por quê.
- [ ] **[Mitigação 3 — derivada da Fig 8 W4]** **Reportar métricas estratificadas mês-a-mês** já no LightGBM v1 (não esperar W7). Para cada modelo treinado (baseline, LightGBM v1, variante `Is_Dont_Go_producao`, variantes (a)/(b) do scale_pos_weight): tabela com AUC-PR, Recall e Precisão calculados separadamente em mai e em jun. Critério explícito do gate: **modelo deve bater baseline em AUC-PR de val (mai) E manter AUC-PR razoável em test (jun)** — se cair muito em jun, é sinal precoce de que o drift quebrou o modelo e Mitigação 1 (W6, CV expandida) precisa entrar antes do tuning. **Parcialmente concluída em 22/05:** ✅ baseline já reporta P/R/F1 estratificados em val (mai) e test (jun) por 4 thresholds + AUC-PR por split em `baseline_metricas.csv`. **Pendente:** mesma estratificação para LightGBM v1, variantes scale_pos_weight (a)/(b), e Is_Dont_Go_producao.
- [ ] **Documentar pré-processamento específico do baseline e do LightGBM** (CM 4.3): baseline usa só `count_critico_4h` (feature derivada de `Criticidade` + `TAG` via rolling 4h, `closed="left"`); LightGBM usa matriz completa `v3.parquet` (29 features + 3 targets). **Parcialmente concluída em 22/05:** ✅ pré-processamento do baseline documentado em `rascunho.md → Metodologia Parte 3 → Baseline heurístico` e no docstring do `07_baseline.py`. **Pendente:** documentação equivalente para o LightGBM (subseção dedicada em rascunho.md após o LightGBM v1 rodar).
- [ ] Comparar com baseline
- [ ] **[Novo após Obs 2.7]** Treinar **variante `Is_Dont_Go_producao`** (filtra os 2.525 DGs em Manutenção) com os mesmos hiperparâmetros e comparar AUC-PR contra o target original. Se variante "produção" for substancialmente melhor (>5pp AUC-PR), confirma que o contexto Manutenção introduz ruído treinável; registrar decisão em `controle_alteracoes.md`.
- [ ] 🚦 **GATE MARCO 1 (2 critérios — RE-CALIBRADO em 22/05 após resultado empírico do baseline):**
  - **Critério A — superar baseline em validação:** LightGBM v1 em val (mai) deve atingir **AUC-PR ≥ 0,2897** (baseline 0,2397 + 5 pontos percentuais de margem). Baseline simples performa baixo em mai porque o regime distribuído (1,62% de DG, menor do semestre) não oferece assinatura clara para regra binária; LightGBM com 29 features tem espaço amplo para ganhar.
  - **Critério B — superar baseline em teste (FORMULAÇÃO REVISADA):** LightGBM v1 em test (jun) deve atingir **AUC-PR ≥ 0,6303** (baseline 0,5803 + 5 pontos percentuais de margem). **A formulação anterior** ("queda ≤ 30% vs val") **assumia que test seria mais difícil que val** — premissa empiricamente falsa: o baseline em test atingiu 0,5803 (lift 3,43× sobre random) contra apenas 0,2397 em val (lift 1,30×). A anomalia localizada do CA65926 (Obs 2.9) cria assinatura mecânica clara para a heurística "conte Críticos recentes", tornando test mais fácil para regra simples. Para justificar a complexidade adicional, o LightGBM precisa adicionar valor genuíno em cima do baseline — não basta "cair pouco vs val".
  - **A = SIM + B = SIM** → avança para W6 (tuning de hiperparâmetros + sobrevivência + Isolation Forest + SHAP). Esperar SHAP confirmar diversidade de features no topo do ranking (não dominância isolada de `count_critico_4h`).
  - **A = SIM + B = NÃO** → LightGBM aprende padrão de mai mas reproduz baseline em jun — indica super-otimização para regime distribuído. Aplicar Mitigação 1 (TimeSeriesSplit CV em W6) ANTES do Optuna para reduzir overfitting ao regime específico de mai; documentar em CM 6.2 como limitação.
  - **A = NÃO + B = qualquer** → LightGBM não bate baseline em val (cenário ruim que indica falha na geração de features ou no encoding). Reveja `05_features.py` antes de tunar — pode haver problema de leakage residual, features sem variância no treino, ou erro no encoding pós-`06b_fix_encoding_leakage.py`.

**Nota histórica (registro da re-calibração em 2026-05-22):** o Critério B original ("queda ≤ 30% test vs val") foi formulado em W4 (registrado na entrada de 2026-05-17 do `controle_alteracoes.md` — "Split temporal walk-forward jan-abr / mai / jun") assumindo que test seria mais difícil que val. O baseline executado em 22/05 produziu resultado contra-intuitivo (test 0,5803 > val 0,2397, razão 2,42×), revelando que a anomalia mecânica localizada do CA65926 cria assinatura preditiva forte para a heurística simples. Re-calibração formal registrada em `controle_alteracoes.md` (entrada 2026-05-22 — "Re-calibração do Critério B do GATE MARCO 1") com a justificativa empírica completa e o ANTES/DEPOIS dos critérios.

**Entregável:** tabela comparativa baseline×LightGBM + modelos serializados em `Projeto/modelos/` + pré-processamento documentado.

#### Observações e Conclusões (W5)

##### 1. Obs 2.4 — Resposta empírica a Q3 (operador correlaciona com DG): sinal real, mas difuso

<details>
<summary><b>Script usado para gerar</b></summary>

[`Projeto/codigo/exploracao_w5_obs_pendentes.py`](Projeto/codigo/exploracao_w5_obs_pendentes.py) — função `obs_24`. Para reproduzir:

```powershell
uv run python Projeto/codigo/exploracao_w5_obs_pendentes.py
```

</details>

Investigação dedicada ao caso paradigma CA65924 deixou pendente desde W1 a pergunta: o operador OP_067 (que aparece no `desenvolver_dontgo.xlsx`) tem taxa de DG anormal? A resposta direta vai além do operador específico — atinge a **Pergunta 3 do edital** sobre se o comportamento do operador correlaciona com alertas DG.

**Resultado quantitativo** (394 operadores no dataset filtrado):

| Métrica | OP_067 | Distribuição global |
|---|---:|---|
| Eventos | 426 | mediana 165 |
| DGs absolutos | 27 | mediana 5 |
| Taxa de DG | **6,338%** | baseline global 3,664% |
| Rank | **#76 de 394** (top 19%) | — |
| Razão vs baseline | 1,73× | — |
| Operadores em faixa comparável (±50%) | **152** outros | — |

A distribuição é fortemente assimétrica (q25 0,57% / q50 2,99% / q75 5,71% / q95 10,87% / q99 35,08% / máx 83,77%), mas os extremos têm baixo volume — OP_004 com taxa 83,77% só tem 154 eventos, provavelmente operador raro ou de teste. **O caso de comportamento operacional realmente preocupante** está em outro operador: **OP_029 com 1.016 DGs absolutos** (taxa 32,5% sobre 3.125 eventos) — único com massa estatística suficiente para virar sinal preditivo robusto no modelo.

**Veredito sobre H5.3:** ❌ refutada na forma original — OP_067 não é outlier extremo. Atualizada para 🟡 (refutada com reinterpretação) em `hipoteses_eda.md`.

**Resposta empírica para Q3 (CM 5.x do relatório):** sim, comportamento do operador correlaciona com DG, **mas de forma difusa** — não há 1-2 operadores "ruins" carregando o problema; há um continuum de 30× de variação entre p25 e p95. A feature `taxa_DG_operador_30d` (Família 5 do `05_features.py`) é informativa mas não deve dominar o ranking SHAP em W6. Interpretações do tipo "operador X é problemático" precisam ser estratificadas por volume de exposição.

**Entregável anexado:** `relatorio/tabelas/obs24_taxa_dg_por_operador.csv` (394 linhas com `n_eventos`, `n_dgs`, `taxa_dg_pct`) — vira material direto para a seção de resposta a Q3 do relatório final.

---

##### 2. Obs 2.9 — Re-framing forte do drift: anomalia RFB de junho é falha mecânica progressiva de UM equipamento

<details>
<summary><b>Script usado para gerar</b></summary>

[`Projeto/codigo/exploracao_w5_obs_pendentes.py`](Projeto/codigo/exploracao_w5_obs_pendentes.py) — função `obs_29`. Para reproduzir:

```powershell
uv run python Projeto/codigo/exploracao_w5_obs_pendentes.py
```

</details>

A "Anomalia B de junho" havia sido caracterizada em W2 (Obs 2.6) como "explosão de 151,7× do Right Front Brake Temperature - Active" e adotada como **motor mecânico do drift** quantificado pela Fig 8 (taxa de DG 1,62% em mai → 7,35% em jun). Quatro hipóteses operacionais foram registradas para investigação dedicada: recapagem em massa de pneus, sazonalidade térmica de inverno, troca de sensor em lote, ou falha localizada em 1-2 equipamentos. A investigação de W5 decompôs os 4.278 eventos RFB-Active de junho por TAG / dia / frota / operador e produziu veredito **decisivo**:

| Decomposição | Resultado |
|---|---|
| TAGs afetadas | 9 de 30 no split de teste |
| **CA65926 isolado** | **98,53% dos 4.278 eventos** |
| Top 3 TAGs concentram | 99,8% do volume |
| Frota dominante (herdada da TAG) | 793-D 4S (98,55%) |
| Onset temporal (primeiros 5 dias de jun) | 0% do volume |
| Onset temporal (últimos 5 dias de jun) | 58,9% do volume; picos dias 26 (458), 27 (518), 30 (1087) |
| CA65926: RFB-Active jan→jun | 0 / 3 / 6 / 0 / 0 / **4.215** → salto de ~700× no equipamento |
| CA65926: histórico de DGs (todos alarmes) | 13.661 eventos, 4.923 DGs no semestre; **438 DGs em março já com taxa 20,28%** |

**Veredito:**

- **H_recapagem em massa**: ❌ refutada (uma operação de recapagem afetaria múltiplos equipamentos).
- **H_sazonal térmica**: ❌ refutada (sazonalidade seria rampa gradual e difusa entre TAGs; aqui é onset abrupto e localizado).
- **H_sensor em lote**: ❌ refutada (lote afetaria múltiplos equipamentos da mesma frota).
- **H_localizada**: ✅ **confirmada.** Falha mecânica progressiva do sistema de freio dianteiro direito do CA65926 (ou sensor defeituoso específico). CA65926 já tinha sinal precursor em março (438 DGs com taxa 20,28% via outros alarmes); a manifestação no RFB explodiu em junho.

**Re-framing do Risco 3.2 (drift temporal):** o que parecia "drift regimal genérico que o modelo não conseguiria antecipar" é, na verdade, **deterioração progressiva de um equipamento com histórico no treino**. Modelo treinado em jan-mai tem **6.578 eventos do CA65926 com 625 DGs históricos** disponíveis para aprendizado. A pergunta operacional deixa de ser "antecipar anomalia nunca vista" e vira "antecipar falha de equipamento que dava sinais" — significativamente mais respondável. A Família 4 regimal (`razao_alarme_7d_vs_30d_anterior`) foi desenhada exatamente para detectar esse tipo de explosão (volume recente vs baseline próprio) e ganha protagonismo central na narrativa SHAP de W6.

**Implicação quantitativa para W7:** 82,2% de todos os DGs de junho (4.298 de 5.226) vêm do CA65926. Análise estratificada "com vs sem CA65926" no teste deve ser obrigatória — quantifica quanto da degradação esperada em junho é mecânica de UM equipamento vs distribuída entre os demais.

**Veredito sobre H3.3:** ❌ refutada na forma original. Atualizada para 🟡 (refutada com reinterpretação) em `hipoteses_eda.md`.

**Padrão emergente reforçado: equipamentos individuais problemáticos.** O CA65926 aparece agora em **dois contextos independentes** — outlier de DGs em W2 (Q4) + dominante da anomalia RFB em W5. Análogo ao **CA65789** que apareceu em W3 (100% das 340 sobreposições de apontamento). A EDA agregada por frota / mês / criticidade esconde sistematicamente esses indivíduos problemáticos; **análise estratificada por TAG vira mandatória em W7** (Qualidade C — análise por equipamento). Candidato direto a:

- **CM 6.1 (Insights Não Óbvios):** "métricas agregadas escondem equipamentos individuais problemáticos — a Vale tem pelo menos dois equipamentos (CA65789 e CA65926) com comportamento sistematicamente anômalo que só emergem na análise estratificada".
- **CM 6.3 (Recomendação Operacional):** auditar manualmente o sistema de freio dianteiro direito do CA65926 (junho); revisar política de manutenção preventiva por equipamento, não por frota agregada.

**Entregável anexado:** `relatorio/tabelas/obs29_rfb_junho_decomposicao.csv` (34 linhas long-format: `dimensao ∈ {dia, TAG, frota}`, `valor`, `n`) — vira tabela de apoio direta na narrativa de Limitações (CM 6.2) e Trabalhos Futuros (CM 6.3) do relatório.

---

##### 3. Implicações conjuntas para W5 modelagem e W6 SHAP

As duas resoluções confluem para uma narrativa coerente sobre o que esperar do modelo:

1. **Família 4 regimal ganha protagonismo central** (Obs 2.9): `razao_alarme_7d_vs_30d_anterior` deveria estar no topo do ranking SHAP em W6 — foi desenhada exatamente para detectar saltos como o RFB no CA65926.
2. **Família 5 operador é informativa mas suave** (Obs 2.4): `taxa_DG_operador_30d` aparece no SHAP mas não domina; sinal real é difuso, não concentrado.
3. **Família 1 rolling counts e Família 2 recência** capturam deterioração progressiva por TAG (Obs 2.9): também devem aparecer no topo, especialmente `count_critico_24h` (que captura a "acumulação de criticidade" da Obs 2.11) e `horas_desde_ultimo_DG` (que captura o histórico recente de CA65926).
4. **Mitigações 1-3 continuam válidas**, mas a Mitigação 1 (TimeSeriesSplit CV) ganha relevância dupla: além de atenuar "mai como regime raro", a CV expandida vai medir se o modelo aprende o padrão "CA65926 em deterioração" desde o treino mais antigo (jan → fev) — se sim, esperamos boa performance em jun apesar do drift de prevalência.

---

##### 4. Baseline heurístico — AUC-PR superior em teste vs validação (achado contra-intuitivo)

<details>
<summary><b>Script usado para gerar</b></summary>

[`Projeto/codigo/07_baseline.py`](Projeto/codigo/07_baseline.py) — heurística canônica `predict_dg = (count_critico_4h >= threshold)`. Saída: `relatorio/tabelas/baseline_metricas.csv` (8 linhas: 4 thresholds × 2 splits). Tempo: 0,4s. Para reproduzir:

```powershell
uv run python Projeto/codigo/07_baseline.py
```

</details>

Heurística baseline implementada conforme decisão consolidada em W5 pré-modelagem: foco em `target_4h` apenas (pergunta operacional canônica do CM 1.2), score raw `count_critico_4h` (perfeitamente alinhado ao horizonte do *target*), 4 thresholds binários (1, 2, 3, 5) para análise da curva precision/recall, estratificação obrigatória mai vs jun (Mitigação 3 derivada da Fig 8). Execução em 0,4s sobre 149.914 eventos de val + test.

**Resultado quantitativo (estratificado mai vs jun):**

| Métrica | VAL (mai) | TEST (jun) | Razão test / val |
|---|---:|---:|---:|
| Eventos | 78.825 | 71.089 | — |
| Positivos `target_4h` | 14.481 (18,37%) | 12.038 (16,93%) | — |
| **AUC-PR (score = `count_critico_4h`)** | **0,2397** | **0,5803** | **2,42×** |
| Random AP (chance) | 0,1837 | 0,1693 | — |
| Lift sobre random | 1,30× | **3,43×** | — |

Matriz de Precision / Recall / F1 por threshold:

| Threshold | VAL P / R / F1 | TEST P / R / F1 |
|---:|---:|---:|
| ≥ 1 | 0,2556 / 0,4025 / 0,3127 | 0,3436 / **0,6976** / 0,4604 |
| ≥ 2 | 0,2887 / 0,2740 / 0,2812 | 0,4060 / 0,5969 / 0,4833 |
| ≥ 3 | 0,3152 / 0,2226 / 0,2609 | 0,4651 / 0,5510 / 0,5044 |
| ≥ 5 | 0,3630 / 0,1654 / 0,2273 | **0,5905** / 0,4714 / **0,5243** |

**Achado contra-intuitivo:** o baseline performa **2,42 vezes melhor em TEST do que em VAL**, medido por AUC-PR. Recall em threshold = 1 passa de 40% (val) para 70% (test). O F1 máximo em val é 0,3127 (threshold = 1); em test é 0,5243 (threshold = 5) — aproximadamente 1,7× maior por F1.

Esse resultado é o **oposto do que a Figura 8 do W4 sugeria**. O drift mai → jun foi quantificado como aumento de taxa de DG por evento (1,62% → 7,35%, fator 4,5×), e a interpretação corrente era "test mais difícil porque tem mais DGs concentrados em regime nunca visto". Mas o baseline contradisse essa interpretação — o **regime concentrado** é o que **favorece** uma heurística simples.

**Explicação mecânica via Obs 2.9 (resolvida em 22/05, antes do baseline):**

A anomalia RFB de junho não é regime distribuído entre equipamentos — é **falha mecânica progressiva de um único equipamento, o CA65926**:
- **98,53%** dos 4.278 eventos `Right Front Brake Temperature - Active` de junho vêm exclusivamente do CA65926.
- **82,2%** de todos os DGs de junho (4.298 de 5.226) vêm do mesmo equipamento.
- RFB-Active no CA65926 passou de 0–6 eventos por mês (jan-mai) para 4.215 em junho — salto de aproximadamente 700×.

Quando um equipamento dispara Críticos com essa intensidade nos minutos e horas que antecedem um DG, a feature `count_critico_4h` atinge valores elevados consistentemente nesses eventos. A heurística "conte Críticos recentes" tem **assinatura clara para detectar esse padrão concentrado** — é o cenário ideal para uma regra simples.

Em maio, o cenário é qualitativamente diferente: taxa de DG de 1,62% é a mais baixa do semestre e os DGs estão distribuídos entre múltiplos equipamentos sem dominância única. Não há um "alvo claro" para a heurística — a regra simples performa apenas marginalmente acima de chance (lift 1,30×).

**Interpretação metodológica:** o "drift mai → jun" **não é uniformemente "test mais difícil"**. É **mudança qualitativa da natureza do problema**. Em junho, predizer DG vira predominantemente predizer "CA65926 em deterioração progressiva", uma tarefa com assinatura preditiva forte em features simples. Em maio, predizer DG vira predizer regime distribuído sem alvo claro, genuinamente mais difícil para qualquer modelo.

**Exemplo concreto da diferença entre os dois regimes (para o leitor visualizar):**

- **Em junho:** um evento `e` do CA65926 em 28/jun (auge da anomalia) tem provavelmente `count_critico_4h ≥ 5` (cascata de RFB-Active já em curso). A heurística com threshold = 1 prediz corretamente `target_4h = 1`. **70% dos positivos de junho são detectados pela regra simples em threshold = 1.**
- **Em maio:** um evento `e` qualquer pode ter `count_critico_4h ∈ {0, 1, 2}` mesmo precedendo um DG, porque DGs em mai não vêm com cascata pré-existente. A heurística tem dificuldade em distinguir — **apenas 40% dos positivos são detectados em threshold = 1**.

**Quatro implicações operacionais para LightGBM em W5-W6:**

1. **O baseline em test é um teto alto (AUC-PR 0,5803).** LightGBM v1 precisa SUPERAR esse valor para passar o Critério B do GATE MARCO 1. Não é trivial — significa adicionar valor genuíno sobre uma regra que já capta 70% do recall em jun.

2. **O baseline em val é baixo (AUC-PR 0,2397).** Critério A do gate é fácil de bater. Mas não confundir "facilidade de bater baseline em val" com "boa generalização" — se LightGBM super-otimiza para regime distribuído de mai, pode performar pior em test (regime concentrado), invertendo o ganho.

3. **Critério B foi re-calibrado em conjunto com este registro.** A formulação original ("queda ≤ 30% test vs val") assumia que test seria mais difícil. Como o baseline mostrou o oposto, Critério B passa a ser "AUC-PR do LightGBM em test ≥ AUC-PR do baseline em test, com margem ≥ 5pp" (ou seja, ≥ 0,6303). Ver re-calibração formal na próxima task abaixo (GATE MARCO 1) e em `controle_alteracoes.md` (entrada 2026-05-22 — "Re-calibração do Critério B do GATE MARCO 1").

4. **SHAP em W6 vira ainda mais importante metodologicamente.** Precisamos confirmar que LightGBM aprendeu sinal **além** de "contar Críticos recentes". Se SHAP mostrar que `count_critico_4h` domina sozinho o ranking de importância, o modelo praticamente reproduz o baseline e não justifica a complexidade adicional. As outras 28 features precisam aparecer no top 10 — especialmente Família 4 regimal (`razao_alarme_7d_vs_30d_anterior`), desenhada exatamente para detectar a explosão do CA65926.

**Achado direto para CM 6.1 (Insight Não Óbvio):** "Heurísticas simples capturam bem padrões de drift localizado (1 equipamento em deterioração), mas têm desempenho mediano em regimes distribuídos. O baseline 'conte Críticos nas últimas 4h' produziu AUC-PR 2,42× melhor em jun (regime concentrado) do que em mai (regime distribuído) — contra-intuitivamente, o conjunto de teste 'mais difícil' pela taxa de DG era na verdade o mais fácil para a regra simples por causa da assinatura mecânica clara do CA65926. Esse achado tem implicação direta para a interpretação do desempenho do modelo principal: ganhos do LightGBM sobre baseline são esperados em mai (espaço a ganhar), mas em jun o teto do baseline é alto e o modelo precisa demonstrar valor genuíno via features não-triviais."

**Entregável anexado:** `relatorio/tabelas/baseline_metricas.csv` (8 linhas: 4 thresholds × 2 splits) — vira tabela de referência canônica para o LightGBM v1 em `08_lightgbm.py`.

---

### W6 (17-23/06) — Tuning + Sobrevivência + Isolation Forest + SHAP + Ablation

**Objetivo:** LightGBM otimizado + modelo de sobrevivência + diagnóstico não supervisionado (K) + interpretabilidade + ablation. Semana mais carregada do projeto (~15h).

- [ ] **[Mitigação 1 — derivada da Fig 8 W4, atenua "mai como regime raro de DG 1,62%"]** Substituir validação single-fold (só mai) por **TimeSeriesSplit CV de 4 folds expandidos** antes do Optuna:
  - Fold 1: treino=jan, val=fev
  - Fold 2: treino=jan-fev, val=mar
  - Fold 3: treino=jan-mar, val=abr
  - Fold 4: treino=jan-abr, val=mai (split atual)
  - **Métrica de tuning:** AUC-PR média dos 4 folds. **Teste em jun continua intocado** (não entra na CV em nenhum momento). Ganho: ~5× mais sinal para tuning, reduz variância das métricas de validação, atenua "mai como regime raro" (1,62% de DG é metade da média do treino). Custo: ~5 min de tempo total de treino (LightGBM é rápido). Implementação: `sklearn.model_selection.TimeSeriesSplit` com cortes mensais customizados ou loop manual. **Asserção defensiva crítica:** validar em cada fold que `train.max(Data_Evento) < val.min(Data_Evento)` — protocolo walk-forward estrito.
- [ ] Optuna no LightGBM: 50 trials sobre **AUC-PR média da CV de 4 folds** (Mitigação 1 acima), não sobre validação single-fold de mai.
- [ ] LightGBM v2 com melhores parâmetros, avaliar no teste (jun) — único contato do modelo com test set em todo o pipeline.
- [ ] **[Derivado do estudo W5 sobre encoding fix — `notas_metodologicas.md` Seção 2]** **Reavaliar Opção 3 (`is_tag_unknown_in_train` e `is_op_unknown_in_train` como features binárias)** agora que a Mitigação 1 (TimeSeriesSplit CV) está implementada — em single-fold a feature é constante no treino (LightGBM ignora); em CV expandida, a feature pode variar entre folds e tornar-se aprendível.
  - **Justificativa empírica:** o estudo de W5 mediu que **2,55% dos eventos do teste (1.812 eventos / 133 DGs)** vêm de categorias unknown (TAGs `CA65791`, `CA65916` + 7 operadores). Magnitude não-desprezível mas não-dominante.
  - **Critério de decisão:** treinar LightGBM v2.1 com as 2 features binárias adicionadas e comparar AUC-PR contra v2 (sem essas features). Se v2.1 ganha > 1pp em AUC-PR no teste → adotar; se ganho < 1pp ou negativo → confirmar Opção 1 e descartar definitivamente (parsimônia + menos código).
  - **Critério estratificado adicional:** comparar AUC-PR especificamente nos 1.812 eventos unknown — se v2.1 melhora substancialmente esse subgrupo, vale adotar mesmo que ganho global seja pequeno.
- [ ] **[Derivado do estudo W5]** **Análise SHAP estratificada por categoria unknown** — computar `is_tag_unknown` em runtime (sem persistir como feature) e gerar dois rankings de importância SHAP separados: (a) eventos com TAG/operador conhecidos no treino vs (b) eventos com qualquer unknown. Compara como o modelo extrapola para categorias nunca vistas. **Justificativa:** 1.812 eventos no teste estão nessa situação — se o ranking SHAP for muito diferente entre os dois subgrupos, o modelo está usando estratégias distintas, e isso vira material para CM 6.1 ou CM 6.2 do relatório.
- [ ] `Projeto/codigo/09_sobrevivencia.py` — **Modelo de Sobrevivência (Weibull AFT, fallback Cox PH)** com `lifelines`:
  - [ ] **Reformatar dados para análise de sobrevivência**: para cada equipamento (TAG), construir tuplas (T, E, X) onde T = tempo até o próximo DG (em horas), E = 1 se evento observado / 0 se censurado (fim da janela jan-jun sem DG), X = features no instante de referência
  - [ ] Treinar `WeibullAFTFitter` no treino (jan-abr), avaliar **C-index** em validação (mai) e teste (jun)
  - [ ] Se WeibullAFT não convergir ou C-index < 0.6 → fallback para `CoxPHFitter` (CM 4.3 nota: dois modelos bem feitos > cinco superficiais)
  - [ ] **Pré-processamento específico de sobrevivência** (CM 4.3): mesma matriz numérica v2, mas exclui features com colinearidade > 0.9 (Cox/Weibull são sensíveis); StandardScaler em features contínuas
  - [ ] Converter saída em probabilidade-em-4h: `P(T ≤ 4h | X)` → comparável com LightGBM em AUC-PR
  - [ ] **Interpretação via hazard ratios**: tabela top-10 features com HR e IC 95% — interpretação direta sem SHAP
  - [ ] **Fig Extra A — Sobrevivência empírica por frota** *(originalmente em W2, movida)* — curva Kaplan-Meier `P(novo DG > t)` por Frota (793-D 5S, 4S, 3S, 2S, LeTourneau L 1850) usando `lifelines.KaplanMeierFitter`. Saída natural do mesmo script já planejado (`09_sobrevivencia.py`); alimenta narrativa de Q4 e da H4.1 (LeTourneau tem perfil distinto)
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
- [ ] **[K — Isolation Forest, 3ª abordagem não supervisionada] (~3h)**: `Projeto/codigo/11_isolation_forest.py`
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

- [ ] `Projeto/codigo/10_evaluation.py`:
  - [ ] **Fig 10** — Matriz de confusão do modelo escolhido com anotações de impacto operacional (CM 5.2)
  - [ ] Análise dos falsos negativos: que TAGs/frotas/operadores escapam?
  - [ ] **[Qualidade C] Análise de erro estratificada**: matriz de confusão e métricas por **frota** e por **tipo** (Caminhão vs. Escavadeira) — modelo não pode falhar mais em uma frota
  - [ ] **[Novo após Obs 2.7]** Métricas estratificadas por **estado operacional do DG** (Operando / Manutenção / Parado / Hibernando) — separa "DG operacional" (alvo principal) de "DG em teste de manutenção" (ruído contextual). Reportar Precision/Recall em cada subgrupo.
  - [ ] **[Novo após Obs 2.9, H7.1]** Análise estratificada **"com vs sem CA65926"** no teste de junho — quantifica quanto da degradação esperada em jun é mecânica de UM equipamento (CA65926 = 82,2% dos DGs de jun = 4.298 de 5.226) vs distribuída entre os demais 29 equipamentos. **Justificativa empírica:** Obs 2.9 confirmou que a anomalia RFB de jun é falha localizada do CA65926, não drift regimal genérico. Sem essa separação, métricas agregadas misturam "modelo aprendeu deterioração de equipamento conhecido" (positivo) com "modelo manteve performance nos demais" (também positivo) — duas histórias diferentes que pedem narrativas distintas no relatório.
  - [ ] **[Novo derivado do estudo W5 sobre encoding fix — `notas_metodologicas.md` Seção 2]** Análise estratificada **"TAG/operador conhecidos vs unknown no treino"** no teste — reportar AUC-PR / Recall / Precisão separadamente para:
    - (a) **69.277 eventos / 5.093 DGs** em categorias conhecidas (97,45% do teste)
    - (b) **1.812 eventos / 133 DGs** em categorias unknown (2,55% do teste)
    - Detalhar: TAGs unknown identificadas (`CA65791` com 1.394 eventos, `CA65916`) + 7 operadores unknown (418 eventos).
    - **Justificativa empírica:** o estudo de W5 mediu que 2,55% dos eventos do teste vêm de TAGs/operadores que não existiam no treino — análise agregada esconde se o modelo extrapola bem para essas categorias ou não. Se AUC-PR cai mais que 30% no subgrupo (b) vs (a), vira limitação concreta em CM 6.2 e argumento empírico para a recomendação de retreino rolling em CM 6.3.
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
  - [ ] **Modelo online com retraining mensal para combater drift detectado em W7** — agora com **justificativa empírica concreta** (não apenas conceitual): o estudo de W5 sobre `tag_freq`/`operador_freq` mediu que **2,55% dos eventos do teste de junho (1.812 eventos / 133 DGs) vêm de TAGs/operadores que não existiam no treino jan-abr** (notas_metodologicas.md Seção 2). TAGs identificadas: `CA65791`, `CA65916`; 7 operadores adicionais. Em produção contínua, espera-se taxa mensal similar de "categorias novas" — modelo deployado sem retreino acumula *blind spot* crescente. Retreino *rolling* mensal (modelo treinado no mês N-3 até N-1, deployado para o mês N) elimina esse efeito por construção.
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
- Entregável feito? [X]
- Bloqueador: primeira tentativa de uv falhou por timeout em lxml; fix com UV_HTTP_TIMEOUT=300 demorou 30min
- Ajuste W+1: adiantar exploração de observações pendentes em W2
- Horas reais investidas: 10

### Semana 2 (20-26/05) — antecipada (concluída em 16-17/05, antes do início oficial)
- Entregável feito? [X] (concluída antes do cronograma)
- Bloqueador: nenhum técnico significativo; pequenos ajustes em runtime (Polars `read_excel` exigia `fastexcel` → resolvido com `engine="openpyxl"`; encoding cp1252 do PowerShell em pipes → resolvido com `PYTHONIOENCODING=utf-8`); bug em `tabela_q4` (join cartesiano por interpretar `Classe` errado) → corrigido com `join_asof` temporal.
- Ajuste W+1: aproveitar a folga ganha para antecipar W3 (limpeza estendida + features básicas) e investigar sobreposições de ciclo descobertas em apontamentos.
- Horas reais investidas: 5H

### Semana 3 (27/05-02/06) — antecipada parcialmente (limpeza estendida + features básicas concluídas em 17/05)
- Entregável feito? [X] limpeza estendida (`03_limpeza.py` etapas 6-12) + features básicas (`05_features.py` em `v1.parquet`) + `controle_alteracoes.csv` (CM 3.1) + `documentacao_features.csv` (CM 3.2). Features avançadas naturalmente continuam para W4.
- Bloqueador: nenhum. Achado novo durante a execução: 340 sobreposições de ciclo (etapa 10) — investigação dedicada identificou bug pontual no CA65789 (H1.4). Decisão arquitetural Opção 1 (estender `03_limpeza.py` em vez de criar `03b_*.py`) registrada em `controle_alteracoes.md`.
- Ajuste W+1: começar W4 com a familia regimal de features (após Obs 2.6) + `estado_pre_evento` (após Obs 2.7) — duas famílias que surgiram empiricamente em W2 e devem ter prioridade alta na matriz v2.
- Horas reais investidas: 10H 

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
