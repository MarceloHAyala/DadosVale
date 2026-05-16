# Controle de Alterações Metodológicas

Registro ANTES/DEPOIS de toda decisão metodológica relevante, conforme nota do Estudo Guiado (página 1):

> *"Sempre que uma alteração, exclusão ou decisão metodológica relevante for tomada, registre o ANTES e o DEPOIS com a justificativa correspondente."*

Este arquivo é **anexo do relatório final** e mostra o rastro analítico das decisões tomadas durante o projeto.

---

## Template

```markdown
### YYYY-MM-DD — [Tema da decisão]
- **ANTES:** estado anterior / opção descartada
- **DEPOIS:** estado novo / opção escolhida
- **Justificativa:** por que mudou
- **Impacto:** o que isso afeta (volume, métrica, escopo)
```

---

## Registro cronológico

### 2026-05-13 — Escopo: descarte do sample 500k (W1)

- **ANTES:** Plano original incluía gerar `telemetria_sample_500k.parquet` para acelerar iteração em scripts de desenvolvimento (W3-W5).
- **DEPOIS:** Task removida do PLANEJAMENTO.md. Iteração rápida em desenvolvimento será feita carregando um dos parquets mensais (`telemetry_jan.parquet`, ~5.4M linhas, ~2s de carga) quando necessário.
- **Justificativa:** Os parquets mensais já oferecem volume reduzido vs. consolidado (5-7M vs 37M linhas). Criar e manter um sample adicional seria redundância sem ganho prático significativo. Confirmação prática: a extensão DuckDB do VSCode carrega os parquets mensais sem problema.
- **Impacto:** Nenhum impacto em resultados analíticos. Pequena perda de velocidade em desenvolvimento (~2s vs ~0.5s por carga) — aceitável.

---

### 2026-05-13 — Conversão de tipos pós-ingestão (W1)

Os parquets brutos trazem três colunas com tipo inadequado para análise temporal e numérica. Conversão executada por `Projeto/codigo/02_correcao_tipos.py`.

#### 2a. Inicio_Turno e Fim_Turno

- **ANTES:** `String` com formato `"YYYY-MM-DD HH:MM:SS.fff"` (com milissegundos), ex: `"2025-06-29 06:00:00.000"`.
- **DEPOIS:** `Datetime(time_unit='us', time_zone=None)`, convertido com formato `%Y-%m-%d %H:%M:%S%.f`.
- **Justificativa:** Necessário para:
  - Extração de features temporais em W4 (`.dt.hour()`, `.dt.weekday()`, `.dt.month()`)
  - Cálculo de duração de turno (`Fim_Turno - Inicio_Turno`) em W4
  - Join temporal com apontamentos em W4 (apontamentos.Inicio é Datetime, telemetria.Inicio_Turno era String)
  - Filtros por intervalo de tempo em toda a EDA (W2)
- **Impacto:** 0 nulls gerados. Formato 100% consistente em todos os 37.164.054 registros e em todos os meses jan-jun/2025. Conversão sem perda de informação.
- **Validação adicional:** Duração do turno = 12h em todos os registros (asserção no script).

#### 2b. Valor

- **ANTES:** `String` com mistura de três tipos:
  - 92% inteiros como string (`"0"`, `"1"`, `"2"`, `"48"`...): dominado por `"0"` (34,4M registros, 92% do total).
  - ~2,2% **floats em formato brasileiro** (vírgula como separador decimal): `"46,2569999694824"`, `"45,3499984741211"`, etc. — descoberto na primeira tentativa de conversão (asserção falhou).
  - 0,64% (237.443) strings literais `"NULL"`.
- **DEPOIS:** `Float64`. Duas transformações encadeadas:
  1. String literal `"NULL"` → null real do Polars.
  2. Vírgula decimal substituída por ponto (`"85,5"` → `"85.5"`) antes do cast.
- **Justificativa:** Permite:
  - Estatísticas descritivas (`mean`, `median`, `std`) — CM 2.1
  - Comparações de magnitude e features de threshold em W4
  - Agregações em rolling windows (média móvel, max em janela) em W4
  - Sem o cast, qualquer `.mean()` retornaria `null` silenciosamente — bug perigoso
- **Decisão metodológica adicional:** Optou-se pela conversão simples (cast para `Float64`) em vez de criar três colunas separadas (`Valor_num` + `Valor_categoria` + `valor_eh_numerico`). Razão: 100% dos valores não-`"NULL"` são numéricos puros — não há texto categórico misturado (tipo `"Active"`, `"Inactive"`). A feature `valor_eh_numerico` seria 100% redundante com `Valor IS NOT NULL`.
- **Lição metodológica:** A exploração inicial via regex `^-?[0-9]+([.,][0-9]+)?$` falhou em detectar o problema porque o regex aceita vírgula como separador decimal, mas o `Polars.cast(Float64)` não. A descoberta só veio porque o script tem asserção de contagem de nulls. Reforça o padrão de **asserções defensivas** que devem permanecer em todos os scripts da pipeline.
- **Impacto:** 237.443 valores que eram a string literal `"NULL"` agora são null real do Polars (0,64% do total). 36.926.611 valores numéricos preservados (99,36%), dos quais ~821.849 (2,2% do total) precisaram da troca vírgula→ponto.

---

### 2026-05-13 — Normalização de Criticidade + achado de inconsistência no sistema fonte (W1)

Aplicada por `Projeto/codigo/03_limpeza.py` (etapa 2/6).

**Distribuição bruta encontrada (5 variantes em 37.164.054 registros):**

| Valor original | Quantidade | % |
|---|---|---|
| `Informacional` | 36.619.169 | 98,53% |
| `Não Crítico` (com acento) | 461.854 | 1,24% |
| `Critico` (**sem acento**) | 83.020 | 0,22% |
| `N??o Crítico` (encoding parcial) | 6 | < 0,0001% |
| `Não Cr??tico` (encoding parcial) | 5 | < 0,0001% |

**Achados metodológicos não-óbvios:**

1. **Inconsistência sistemática de encoding entre níveis de criticidade.** "Critico" aparece **sem acento** em 100% dos casos (83.020 registros), enquanto "Não Crítico" aparece **com acento** em 99,99% dos casos. Não é caso isolado de corrupção — é padrão. Hipótese mais provável: a coluna `Criticidade` é populada por **duas pipelines distintas** (provavelmente um sistema legado escrevendo "Critico" sem acento e um sistema mais novo escrevendo "Não Crítico" com UTF-8 correto). Sem acesso ao DBA da Vale para confirmar, fica registrado como hipótese.

2. **11 registros com falha parcial de encoding** (caracteres específicos substituídos por `??`): 6 com `"N??o Crítico"` (perdeu o `ã`) e 5 com `"Não Cr??tico"` (perdeu o `í`). Indica que houve um ponto da pipeline onde caracteres não-ASCII foram convertidos com `errors='replace'` em vez de `errors='strict'`. Volume desprezível (< 0,001%) mas o padrão é interessante: dois caracteres distintos falham em registros distintos, sugerindo que a corrupção não é determinística.

**Decisão de normalização:**

- **ANTES:** 5 variantes mistas (com/sem acento + 2 com `??`)
- **DEPOIS:** 3 categorias canônicas em ASCII puro: `Critico`, `Nao_Critico`, `Informacional`
- **Justificativa:** Encoding inconsistente é fonte de bugs silenciosos em filtros (`df.filter(pl.col("Criticidade") == "Não Crítico")` falha para os 11 registros com `??`). ASCII puro elimina a ambiguidade para sempre e facilita serialização (CSV, JSON) sem se preocupar com encoding.
- **Impacto:** 100% dos registros classificados corretamente. Os 11 registros com `??` foram absorvidos no grupo `Nao_Critico` (interpretação inequívoca dada a posição do `??` no meio das palavras).
- **Recomendação para a Vale (vai para Trabalhos Futuros do relatório):** padronizar a escrita em ASCII puro na fonte. Eliminaria a duplicidade de pipelines e a corrupção parcial.

**Distribuição final pós-normalização:**

| Criticidade final | Quantidade | % |
|---|---|---|
| `Informacional` | 36.619.169 | 98,53% |
| `Nao_Critico` | 461.865 | 1,24% |
| `Critico` | 83.020 | 0,22% |

---

### 2026-05-16 — Filtro de eventos `Criticidade = Informacional` em W3 (validação empírica)

Decisão registrada antes da execução de W3 (limpeza), com base em investigação concluída em W2 (`Projeto/codigo/exploracao_w2_obs.py`, Obs 2.2).

- **ANTES:** O plano original (PLANEJAMENTO.md) previa filtrar `Informacional` em W3 com base no relatório inicial — análise restrita a janeiro (5.319.047 eventos `Informacional` → 0 DGs). Restava o risco de a propriedade ser específica de janeiro e não se manter no semestre completo.
- **DEPOIS:** Filtragem confirmada e mantida no plano. Validação no semestre completo (jan-jun/2025): **36.619.169 eventos `Informacional` → 0 DGs exatos** (0,0000%). A regra CMA não converte `Informacional` em DG em nenhum dia observado. Filtro será aplicado em `Projeto/codigo/03_limpeza.py` em execução posterior dedicada a W3.
- **Justificativa:** Zero positivos perdidos + 98,53% do volume eliminado. A separação é determinística (binária), não estatística — `Informacional` é definicionalmente fora do escopo do target, não apenas "raramente DG".
- **Impacto:** Dataset pós-filtro passa de 37.164.054 para ~544.885 linhas (`Critico` + `Nao_Critico`). Habilita:
  - Rolling windows 1h/4h/24h em W4 sem risco de estouro de RAM (risco 3.1 do `observacoes_importantes.md` é desativado por essa decisão para esta família de features)
  - Iteração de modelagem (W5-W6) ~68× mais rápida em I/O
  - Feature engineering pode focar nos 19 alarmes que efetivamente geram >=1 DG (achado de Obs 2.1, mesma sessão) — 99,6% dos alarmes do dataset são irrelevantes para o target
- **Validação adicional descoberta na mesma investigação:** taxa de DG por criticidade é **assimétrica e separável**:
  - `Critico`: 12,39% (1 em 8 eventos vira DG)
  - `Nao_Critico`: 2,10% (1 em 48)
  - `Informacional`: 0,0000%
- **Nota metodológica:** A decisão **não** afeta o cálculo de features temporais. Como `Informacional` nunca vira DG, qualquer rolling window que o incluísse estaria contando ruído puro para o target.

---

### 2026-05-16 — Migração de join simples para join temporal `join_asof` na Tabela Q4 (W2)

Decisão tomada durante a geração da tabela Q4 (DGs por Frota / Tipo / Classe) em `Projeto/codigo/04_eda.py`.

- **ANTES:** Join simples por chave `TAG ↔ Tag` usando `apo.select(["Tag", "Frota", "Tipo", "Classe"]).unique()` como mapa de atributos. **Resultado: tabela inflada 3,1× (61.646 DGs somados em vez dos 19.962 reais)**. Causa raiz: `Classe` em apontamentos não é atributo fixo do equipamento — é o **estado operacional do ciclo** (`Operando`/`Parado`/`Manutenção`/`Hibernando`), que **varia no tempo**. Como cada TAG aparece em apontamentos sob múltiplas Classes ao longo dos 6 meses (~2,6 classes por TAG em média), o `.unique()` retornou 121 combinações para 47 TAGs, e o join produziu produto cartesiano implícito.
- **DEPOIS:** Join temporal via `polars.DataFrame.join_asof` com:
  - `left_on="Data_Evento"`, `right_on="Inicio"`, `by_left="TAG"`, `by_right="Tag"`, `strategy="backward"` — para cada DG, encontra o ciclo de apontamento da mesma TAG com maior `Inicio <= Data_Evento`
  - Filtro adicional `Data_Evento <= Fim` para descartar matches onde o evento caiu em gap entre ciclos (DGs sem match seriam classificados como `SEM_APONTAMENTO`, transparentes em vez de silenciosamente descartados)
  - Mapa `Tag → Frota` construído separadamente (atributo fixo) via `group_by(["Tag", "Frota"]).first()` ordenado por frequência
  - Cast `ns → μs` em `Inicio`/`Fim` de apontamentos para alinhar precisão temporal com `telemetria.Data_Evento` (μs) — lossless dado que a granularidade real dos dados é de segundos
- **Justificativa:** A semântica correta de "estado operacional no momento do DG" exige join temporal, não join por chave. O bug do join simples não era de implementação — era de modelo conceitual sobre o que a coluna `Classe` representa. Decisão validada empiricamente: **100% dos 19.962 DGs encontraram match temporal válido** (0 `SEM_APONTAMENTO`), confirmando cobertura completa da pipeline de apontamentos da Vale.
- **Impacto:**
  - Tabela Q4 ganha dimensão analítica nova: distribuição de DGs por estado operacional → resposta de Q4 mais rica que o mínimo do guia
  - **Achado emergente novo:** 2.525 DGs (12,65%) ocorreram em estado `Manutenção` — esperaria-se ~0 → registrado como obs pendente **2.7** em `observacoes_importantes.md` com método para diferenciar 3 hipóteses (DG → transição / falsos positivos de bancada / bug CMA)
  - Se hipótese 2 (falsos positivos) for confirmada em W3, isso é evidência **direta** do viés inerente do label CMA (Risco 3.3 reforçado)
  - A função `tabela_q4()` vira ativo reutilizável: se W4 decidir usar `estado_operacional_no_DG` como feature, o código já está validado
- **Lição metodológica:** Coluna com nome igual entre fontes (`Classe` em telemetria e em apontamentos) pode significar **conceitos completamente diferentes** (status do alarme vs estado operacional do ciclo). Sempre validar semântica antes de assumir equivalência. A descoberta veio porque a asserção `total_DGs == 19.962` ao final do script falhou — reforça padrão de **asserções defensivas** em todos os scripts.

---

### 2026-05-16 — Normalização de `NIVEL` em `Alarmes - Regra de Negocio.xlsx` (sheet CMA)

Aplicada por `Projeto/codigo/extrai_eventos_muito_alto.py` ao gerar `Projeto/relatorio/tabelas/eventos_muito_alto.csv` (entregável CM 1.1).

**Distribuição bruta encontrada na coluna `NIVEL` da sheet CMA (152 linhas totais):**

| Valor original | Quantidade |
|---|---:|
| `Muito Alto` | 76 |
| `Alto` | 69 |
| `Muito alto` (minúsculo no segundo termo) | **6** |

**Achado metodológico:** Mais uma inconsistência sistemática de capitalização na fonte de dados da Vale — segue o mesmo padrão do achado de W1 sobre encoding inconsistente de `Criticidade` (sistemas pipelines distintos escrevendo a mesma categoria com normalização diferente). 6 registros de "Muito alto" entre 82 totais com semântica "Muito Alto" = ~7,3% de inconsistência localizada.

- **ANTES:** Filtro literal `NIVEL == "Muito Alto"` capturaria apenas 76 de 82 registros (perda silenciosa de 7,3%).
- **DEPOIS:** Filtro case-insensitive com `.str.to_lowercase().str.strip_chars() == "muito alto"`, normalização canônica para `"Muito Alto"` antes de gravar o CSV. Asserção defensiva no script garante exatamente 82 registros (76 + 6).
- **Justificativa:** Filtro literal silencioso é mais perigoso que erro explícito — perderíamos 6 eventos críticos da CMA sem aviso. A normalização preserva 100% dos registros relevantes e garante coluna canônica no entregável.
- **Impacto:** Tabela `eventos_muito_alto.csv` final tem 82 linhas em vez de 76 (+7,9% de cobertura). Sem o tratamento, a documentação do CM 1.1 estaria incompleta. **A inconsistência em si não foi corrigida na fonte** — vira recomendação para Vale (Trabalhos Futuros): padronizar capitalização em ASCII puro na pipeline da CMA (mesma recomendação já feita para `Criticidade`).
- **Padrão emergente:** essa é a **2ª evidência independente** de problemas de normalização textual em fontes da Vale (1ª foi a Criticidade em W1, com 5 variantes incluindo encoding parcial `??`). Sugere padrão sistêmico de pipelines fonte que não validam normalização de strings categóricas antes de gravar. Vira observação consolidada para CM 6.1 (Insights não óbvios) e CM 6.3 (Trabalhos Futuros).

---

<!-- Próximas entradas serão adicionadas conforme decisões forem tomadas em W3, W4, etc. -->
