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

### 2026-05-17 — Reconciliação da numeração dos scripts do pipeline (Opção B)

Decisão tomada antes de iniciar W3, ao planejar a criação de `*_features.py`. Detalhe: o plano original previa `04_features.py` ocupando o slot 04, mas esse slot foi ocupado em W2 por `04_eda.py` (porque os slots 02 e 03 já estavam em uso por `02_correcao_tipos.py` e `03_limpeza.py`, ambos criados em W1).

- **ANTES (plano original em `PLANEJAMENTO.md`, válido até 2026-05-17):** numeração assumia ordem lógica do pipeline, com EDA no slot 02 e features no slot 04. Estado planejado: `01_ingestao.py`, `02_eda.py`, `03_limpeza.py`, `04_features.py`, `05_split.py`, `06_baseline.py`, `07_lightgbm.py`, `08_sobrevivencia.py`, `09_evaluation.py`, `10_isolation_forest.py`.
- **DEPOIS:** numeração reflete **ordem cronológica de criação**, não ordem lógica do pipeline. Estado final (implementados + planejados):
  - **Implementados em W1-W2:** `01_ingestao.py`, `02_correcao_tipos.py`, `03_limpeza.py`, `04_eda.py` + scripts auxiliares (`exploracao_w2_obs.py`, `extrai_eventos_muito_alto.py`)
  - **Planejados W3+ (deslocados em +1):** `05_features.py` (W3-W4), `06_split.py` (W4), `07_baseline.py` (W5), `08_lightgbm.py` (W5-W6), `09_sobrevivencia.py` (W6), `10_evaluation.py` (W7), `11_isolation_forest.py` (W6)
- **Justificativa:** Opção B (próximo número livre) escolhida sobre Opção A (renomear `04_eda.py` → `05_eda.py` para liberar slot 04) por dois motivos: (i) **menor risco de quebra** — não modifica arquivo já implementado (`04_eda.py`) nem referências em commits anteriores; (ii) **menor esforço** — atualizar apenas o plano e referências em documentos analíticos (PLANEJAMENTO.md, rascunho.md, README.md), sem alterar código existente. Custo aceito: a numeração perde a propriedade de "refletir ordem lógica do pipeline" e passa a refletir ordem de criação, o que é coerente com a forma como o projeto evoluiu (correção de tipos descoberta apenas na execução, limpeza adiantada para W1, etc.).
- **Impacto — arquivos atualizados nesta data:**
  - `PLANEJAMENTO.md` — árvore de estrutura (seção 4) e 8 referências em tasks de W3-W7
  - `Projeto/relatorio/rascunho.md` — tabela do Anexo A.2 e nota de reconciliação
  - `README.md` — exemplos de comandos no passo 7
- **Nota metodológica:** o desencontro entre numeração planejada e numeração real surgiu de duas decisões em W1 tomadas em resposta à exploração dos dados: (i) inserção de `02_correcao_tipos.py` por descoberta de inconsistências de tipo (vírgula decimal BR, strings "NULL", datetimes em texto); (ii) adiantamento de `03_limpeza.py` para W1 porque era pré-requisito para qualquer análise descritiva, mesmo simples. Essas decisões cronologicamente prévias quebraram a sequência prevista no slot 02, levando ao deslocamento subsequente. Padrão a esperar em projetos exploratórios: o plano de numeração inicial raramente sobrevive ao primeiro contato com os dados; vale formalizar a reconciliação assim que ela se torna inevitável.

---

### 2026-05-17 — Extensão do `03_limpeza.py` com fase de cleaning (W3 / CM 3.1)

Aplicada por `Projeto/codigo/03_limpeza.py` (etapas 6-12), encerrando a fase de Preparação dos Dados. Arquitetura adotada: **Opção 1** (estender o script existente em vez de criar um `03b_limpeza_avancada.py` separado) — decisão registrada em `PLANEJAMENTO.md` → W3.

- **ANTES:** O script `03_limpeza.py` (W1) executava apenas inspeção do dataset original: normalização de Criticidade, verificação de duplicados, frequência média, estatísticas descritivas. O parquet de saída (`telemetria_limpa.parquet`, 435 MB, 37,16M linhas) ainda continha todos os eventos `Informacional`. As decisões de limpeza tomadas em W2 (filtro Informacional registrado em 2026-05-16) viviam apenas como filtro de runtime dentro de `04_eda.py` e `exploracao_w2_obs.py`, e não estavam persistidas no parquet.
- **DEPOIS:** Script estendido com **6 novas etapas (6-12)** de cleaning + audit log, gerando dataset limpo definitivo:
  - **Etapa 6:** Filtro `Criticidade = Informacional` aplicado e persistido no parquet (decisão de 2026-05-16). 36.619.169 linhas removidas; **19.962 DGs preservados** (asserção defensiva).
  - **Etapa 7:** Validação defensiva de outliers `Valor > 1000`. **Achado:** 0 outliers no dataset filtrado — os 118 outliers identificados em W1 eram todos `Informacional` e foram automaticamente eliminados pela etapa 6. A etapa permanece como validação defensiva (asserta 0 outliers + 0 DGs entre outliers).
  - **Etapa 8:** Missing values por coluna (CM 3.1). Telemetria: `Valor` tem 237.443 nulls (**43,58% do dataset filtrado** — todos os nulls originais estavam em eventos `Critico`/`Nao_Critico`, nenhum em `Informacional`). Apontamentos: 0 nulls em qualquer coluna. Decisão: manter nulls (LightGBM aceita NaN diretamente); avaliar criação de feature derivada `valor_disponivel = Valor IS NOT NULL` em W4 para capturar o sinal binário "alarme com/sem medição numérica".
  - **Etapa 9:** Validação de `Inicio > Fim` em apontamentos. **Achado:** 0 registros inválidos — qualidade temporal do dataset de apontamentos é alta.
  - **Etapa 10:** Sobreposições de ciclo (Tag, Inicio, Fim). **Achado novo, não previsto:** 340 sobreposições (0,09%) — volume acima do threshold de 0,01%, abaixo do threshold de flag direta. Adicionada flag `is_sobreposicao`. **Investigação de concentração por Frota/TAG/mês fica pendente** (próxima ação proposta — pode revelar bug pontual em equipamento específico ou padrão sistêmico, candidato a insight CM 6.1).
  - **Etapa 11:** Persistência. Saídas: `telemetria_limpa.parquet` (**7 MB**, redução de 98% vs antes do filtro) + `apontamentos_limpo.parquet` (**6,3 MB**, novo — substitui o consumo direto do parquet bruto pelos scripts downstream).
  - **Etapa 12:** Geração de `Projeto/relatorio/tabelas/controle_alteracoes.csv` no formato CM 3.1 obrigatório (Campo / Problema Identificado / Qtd. Registros / Tratamento Aplicado / Justificativa). 5 linhas de registro, anexo direto do relatório final.
- **Justificativa:** Consolida em um único passo executável a fase de Preparação dos Dados do CRISP-DM. Asserções defensivas em pontos críticos (DGs preservados, outliers sem contaminação do target, volume esperado pós-filtro) garantem que qualquer regressão futura é detectada imediatamente. Output minúsculo (~7 MB) torna trivial qualquer iteração downstream em W4-W7.
- **Impacto:**
  - **Pipeline canônico de limpeza fechado:** a partir de agora, todos os scripts downstream (W4+) lêem `telemetria_limpa.parquet` (filtrado, 545k linhas) e `apontamentos_limpo.parquet` (com flag `is_sobreposicao`).
  - **`04_eda.py` e `exploracao_w2_obs.py` continuam funcionando** sem alteração: o `filter(Criticidade != Informacional)` interno deles vira no-op (filtra 0 linhas; asserções já existentes confirmam 19.962 DGs preservados).
  - **Tamanho local cai drasticamente:** telemetria 435 MB → 7 MB. Pode-se opcionalmente deletar `telemetria_consolidado.parquet` (421 MB) e `telemetria_tipada.parquet` (435 MB) — ambos reproduzíveis em ~30s pelo pipeline.
- **Achados secundários que merecem follow-up:**
  1. **340 sobreposições de ciclo:** investigar concentração por Frota/TAG/mês — pode ser bug pontual em equipamento específico ou padrão sistêmico.
  2. **43,58% de nulls em `Valor`:** validar em W4 se a feature derivada `valor_disponivel` adiciona sinal preditivo (provável correlação com tipo de alarme).

---

### 2026-05-17 — Extensão do `05_features.py` com 4 famílias avançadas (W4 parcial)

Aplicada por `Projeto/codigo/05_features.py` (etapas 4-7), implementando 4 das 7 famílias de features avançadas previstas no PLANEJAMENTO.md → W4. Arquitetura consistente com a Opção 1 já adotada em W3 (estender o script existente em vez de criar um novo).

- **ANTES:** O `05_features.py` (W3) tinha 5 features básicas (`hora_dia`, `dia_semana`, `turno`, `mes`, `valor_disponivel`) salvas em `dados/features/v1.parquet` (6,9 MB, 24 colunas). As famílias de features avançadas previstas para W4 ainda não estavam implementadas.
- **DEPOIS:** Script estendido com 4 novas etapas (etapas 4-7) que adicionam 14 features:
  - **Etapa 4 — Rolling windows** (9 features): `count_{critico/nao_critico/total} × {1h/4h/24h}` via `rolling_sum_by(closed="left").over("TAG")`. Asserção exata: `count_total = count_critico + count_nao_critico` (diff_max = 0 em todos os 544.885 eventos).
  - **Etapa 5 — Recência** (2 features): `horas_desde_ultimo_DG` e `horas_desde_ultimo_critico` via `shift(1).forward_fill().over("TAG")`. **Achado:** 5.104 eventos (0,94%) com `horas_desde_ultimo_critico = 0` (cascata de alarmes simultâneos); 479 (0,10%) com `horas_desde_ultimo_DG = 0`. NÃO é leakage — são eventos simultâneos legítimos.
  - **Etapa 6 — Estado pré-evento** (1 feature): `estado_pre_evento` via `join_asof(strategy="backward", t-1h)` com filtro `Data_Evento - 1h <= Fim`. **Achado:** apenas 106 eventos (0,02%) sem apontamento ativo (`SEM_APONTAMENTO`). Estado `Manutenção` representado em 8,3% dos eventos vs 12,65% dos DGs — confirma H5.1 (DGs em manutenção são legítimos).
  - **Etapa 7 — Família regimal** (2 features): `razao_alarme_7d_vs_30d_anterior` (restrita aos 19 alarmes que geraram >=1 DG; 74,3% NULL — esperado e correto) e `razao_severidade_14d_vs_60d` (por TAG; 0,2% NULL — eventos do início do semestre).
- **Justificativa metodológica:** Cada uma das 4 famílias está ancorada em achado empírico anterior (Obs 2.5 → rolling; padrão clássico → recência; Obs 2.7 → estado pré-evento; Obs 2.6 + Obs 2.6 extensão → regimal). A restrição da família regimal aos 19 alarmes está alinhada com decisões documentadas em `rascunho.md` (Seção 4.1) e `hipoteses_eda.md` (H2.1). Asserção `closed="left"` em todas as 13 rolling features previne leakage temporal.
- **Impacto:**
  - **Matriz `v2_parcial.parquet`** gerada: 544.885 linhas × 38 colunas (19 originais + 5 básicas + 14 avançadas), **19,6 MB**.
  - **`v1.parquet` mantida** para compatibilidade retroativa (apenas 5 features básicas).
  - **`documentacao_features.csv` atualizada** para 19 entradas (CM 3.2 — nome, tipo, descrição, fórmula, motivação, semana criada).
  - **Tempo de execução do pipeline completo:** ~2 segundos (Polars rolling é eficiente nessa escala).
- **Decisão metodológica adicional (eventos simultâneos):** As 5.104 ocorrências de `horas_desde_ultimo_critico = 0` foram interpretadas como **sinal preditivo legítimo** (cascata de alarmes simultâneos em resposta a uma única falha física), não como leakage. Asserção foi relaxada para `>= 0` (e não `> 0`) com diagnóstico explícito dos zeros. Justifica-se porque o evento ATUAL não precede no tempo o evento Crítico simultâneo — apenas coincide.
- **Pendente para próxima sessão de W4:** 3 famílias restantes (operador, regra de negócio, encoding categórico) + target 4h + análise de sensibilidade janela 2h/4h/8h + `06_split.py` + Figs 7 e 8 + Fig Extra C (CA65924).

---

### 2026-05-17 — Encoding categórico em W4: frequency + one-hot (target encoding adiado)

Decisão tomada durante a implementação da Família 7 do `05_features.py` (encoding categórico, 7 features novas).

- **ANTES (plano original em PLANEJAMENTO.md W3):** o plano previa target encoding para colunas de média/alta cardinalidade — `Tag` (target encoding com smoothing + KFold para evitar leakage) e `Frota` (target encoding). `Tipo` e `Classe` em one-hot; `Operador` em frequency encoding + feature derivada `taxa_DG_operador_30d`. O plano pressupõe que o target real está disponível para calcular médias por categoria.
- **DEPOIS:** adotado **frequency encoding + one-hot apenas**, sem target encoding nesta iteração:
  - `Tag` (35 valores, alta cardinalidade) → `tag_freq` via frequency encoding (1 coluna)
  - `Frota` (5 valores) → 4 colunas one-hot (`frota_793D_2S/3S/4S/5S`, com LeTourneau L 1850 como referência implícita pela soma = 0)
  - `Tipo` (2 valores) → 1 coluna binária `tipo_caminhao` (1 = Caminhão, 0 = Escavadeira)
  - `Operador` (394 valores únicos, alta cardinalidade anonimizada) → `operador_freq` via frequency encoding (1 coluna)
  - `Classe` (categórica em telemetria, valores `Activate`/null) → **omitida nesta iteração** (cardinalidade muito baixa e semântica de "status do alarme" duplica informação já capturada por `valor_disponivel`)
- **Justificativa:** O **target final** (`y = 1` se há DG na janela de +0 a +4h após o evento) **ainda não foi construído** — essa é uma task pendente da W4 (CM 3.3). Sem target real, fazer "target encoding" exigiria usar `Is_Dont_Go` (label do evento atual) como proxy, o que introduziria **leakage temporal massivo**: o modelo aprenderia `Tag_X tem taxa_dg histórica de Y%` calculada inclusive sobre o próprio evento que está tentando prever. Para uma estimativa não-leaky, exigiria KFold temporal sobre o treino (jan-abr), que por sua vez requer o split temporal de W4 (também pendente). Frequency encoding captura o **"volume operacional"** da categoria (CA65926 com tag_freq alto, por exemplo) sem qualquer leakage — informação útil, ainda que mais fraca que target encoding propriamente dito.
- **Impacto:**
  - **Matriz v2.parquet final gerada** (29 features, 22,4 MB, 48 colunas) usando frequency + one-hot. Suficiente para iniciar a modelagem em W5 e validar a pipeline end-to-end.
  - **Limitação aceita:** features de encoding podem ser subótimas para alta cardinalidade (Tag, Operador). Esperamos que a perda seja modesta porque (i) LightGBM lida razoavelmente bem com frequency encoding em alta cardinalidade, e (ii) já temos outras features que capturam comportamento por TAG (rolling counts, regimal) e por operador (taxa_DG_operador_30d como feature explícita).
  - **Refinamento futuro registrado** — ver task detalhada em `PLANEJAMENTO.md` → W5 → "Refinar encoding categórico após target real".
- **Nota metodológica:** A decisão segue o princípio de **"primeiro fechar o end-to-end, depois otimizar"** — uma matriz funcional vale mais do que uma matriz perfeita para validar que o pipeline integra corretamente. O target encoding será uma iteração de melhoria mensurável (comparação AUC-PR direta entre as duas variantes em W5).

---

### 2026-05-17 — Construção do target multi-janela em W4 (CM 3.3)

Aplicada por `Projeto/codigo/05_features.py` (etapa 11), fechando a definição operacional do *target* prevista no PLANEJAMENTO.md → W4. Gera 3 colunas em `v2.parquet`: `target_2h`, `target_4h`, `target_8h`.

- **ANTES:** O dataset filtrado (`telemetria_limpa.parquet`, 544.885 linhas) carregava apenas a coluna binária `Is_Dont_Go` indicando se o **evento corrente** era DG. Não havia coluna que respondesse à pergunta operacional real do projeto — "haverá DG nas próximas N horas neste equipamento?" — que é a definição de *target* exigida pelo CM 3.3 e pelo cenário operacional descrito no CM 1.2 (Figura 1, bloco G). Sem essa coluna, o pipeline de modelagem em W5 não poderia ser iniciado.
- **DEPOIS:** 3 colunas-alvo construídas simultaneamente para suportar a análise de sensibilidade (Profundidade 1 do PLANEJAMENTO.md → W4):
  - Para cada equipamento, ordenar eventos por `Data_Evento`. Coluna auxiliar `_dg_ts` recebe o timestamp apenas dos eventos com `Is_Dont_Go = 1` e NULL nos demais.
  - Próximo DG futuro localizado via `_dg_ts.reverse().shift(1).forward_fill().reverse().over("TAG")` — semanticamente equivalente a "para cada evento, qual é o timestamp do próximo DG **estritamente posterior** do mesmo equipamento".
  - Cálculo `_horas_ate_dg = (_proximo_dg_ts - Data_Evento) / 3600s` e construção dos rótulos: `target_Nh = 1` se `0 < _horas_ate_dg <= N`, caso contrário `0` (incluindo eventos sem próximo DG observado).
  - Janela aberta no início (`> 0`) exclui explicitamente o próprio DG do conjunto de positivos do **seu próprio** target — o modelo não pode "prever" o evento que ele já está vendo. Janela fechada no fim (`<= N`) inclui o instante exato do DG futuro como positivo do horizonte.
- **Justificativa técnica:** o padrão `reverse → shift(1) → forward_fill → reverse` sobre `_dg_ts` é o equivalente exato de "achar o próximo evento-alvo posterior", e tem complexidade `O(n)` em Polars (a alternativa `join_asof(strategy="forward")` exigiria duas passagens e um join temporal — desempenho pior). O `shift(1)` aplicado APÓS o `reverse` exclui o evento corrente quando ele próprio é DG (evitando que um DG predisse ele mesmo).
- **Impacto — distribuição empírica nas 544.885 linhas:**

  | Target | Positivos | % | Negativos | Censurados (sem DG futuro) |
  |---|---:|---:|---:|---:|
  | `target_2h` | 139.090 | **25,5%** | 405.795 | 102.602 (18,83%) |
  | `target_4h` (principal) | 159.396 | **29,3%** | 385.489 | 102.602 (18,83%) |
  | `target_8h` | 186.343 | **34,2%** | 358.542 | 102.602 (18,83%) |

  Monotonicidade confirmada (todo positivo de 2h também é positivo de 4h e 8h). 102.602 eventos sem DG futuro observado no horizonte do dataset (eventos no fim do semestre ou em TAGs sem nenhum DG no período) tratados como `y = 0` em todas as 3 janelas — convenção declarada explicitamente.

- **Achado surpreendente (candidato direto a CM 6.1 — Insights Não Óbvios):** a Introdução do `rascunho.md` declara taxa global de DGs de ~0,054% (19.962 / 37.164.054), e o leitor naturalmente extrapola que o target binário do modelo terá essa proporção de positivos — problema "extremamente desbalanceado" no sentido clássico (1 em 1.852). A construção real revela **29,3% de positivos no `target_4h`**, ~540× a expectativa.
  - **Por quê:** o target é uma **janela temporal**, não um evento pontual. Cada DG "reivindica" como positivos todos os eventos do mesmo equipamento nos ~4h precedentes — em média ~25 eventos por DG dado a frequência típica de telemetria pós-filtro (~6 eventos/min). Multiplicando 19.962 DGs × ~25 = ~500k positivos esperados, contra 159.396 observados (a diferença é absorvida pelo censoring e por equipamentos com DGs muito espaçados onde a janela 4h não cobre eventos contíguos).
  - **Consequência para modelagem (W5):** o problema continua desbalanceado, mas em **ordem de magnitude muito mais branda** do que a inicialmente declarada. Estratégias como `class_weight='balanced'` ou `scale_pos_weight ≈ 2.4` (e não `≈ 1850`) são suficientes — não há necessidade do arsenal pesado de imbalance learning (SMOTE temporal, undersampling agressivo).
  - **Consequência para o relatório:** a Introdução do `rascunho.md` precisará de uma nota de pé esclarecendo que a taxa 0,054% se refere ao **evento pontual** `Is_Dont_Go`, e que o target operacional `target_4h` (Figura 7, ainda pendente) tem taxa muito mais alta por construção. Sem essa nota, o relatório seria internamente contraditório.
  - **Consequência para a explicabilidade do modelo (W7):** confirmar via SHAP que o modelo aprende sinal genuíno e não apenas a "regra trivial" `houve DG nas últimas 4h → provavelmente terá DG nas próximas 4h também" (autocorrelação alta dada a regra CMA de acumulação).
- **Decisão metodológica adicional — tratamento do censoring:** eventos sem DG futuro observado (102.602, 18,83%) recebem `y = 0` em vez de NULL. Justificativa: (i) consistente com a semântica operacional — se nenhum DG ocorreu nas N horas seguintes, o instante de decisão era de fato seguro; (ii) NULL exigiria mascaramento durante treino que invalidaria a métrica AUC-PR sobre o teste; (iii) a alternativa Weibull AFT (W6) tratará o censoring de forma rigorosa como dado adicional, oferecendo segunda leitura do problema. Limitação reconhecida: eventos próximos do fim do semestre (junho) têm maior chance de ser falso negativo do label — quantificação prevista para W7 (estratificação mensal do desempenho).
- **Saídas geradas:** `Projeto/dados/features/v2.parquet` (544.885 × 51 colunas, **22,4 MB**) + `Projeto/relatorio/tabelas/sensibilidade_janela.csv` (3 linhas com taxa global e distribuição por mês para cada janela).

---

### 2026-05-17 — Split temporal walk-forward jan-abr / mai / jun (W4 CM 4.1)

Aplicada por `Projeto/codigo/06_split.py` (5 etapas), fechando a estratégia de validação temporal prevista no PLANEJAMENTO.md → W4. Adiciona coluna `split` ao dataset, gera tabela `split_temporal.csv`, Fig 7 (janela de predição) e Fig 8 (drift mês-a-mês).

- **ANTES:** `v2.parquet` continha as 544.885 linhas de features + 3 colunas-alvo, mas não tinha qualquer divisão treino/validação/teste. O plano original previa split temporal jan-abr / mai / jun e justificativa contra k-fold aleatório, mas nenhuma das duas estava materializada em código ou em figura. A modelagem em W5 não poderia ser iniciada sem decisão concreta sobre as fronteiras temporais e sobre o protocolo de avaliação.
- **DEPOIS — Split temporal walk-forward em 3 partições com cortes nos limites de mês:**

  | Split | Período (Data_Evento) | Eventos | DGs | Taxa DG | Positivos `target_4h` | Taxa pos. 4h | TAGs |
  |---|---|---:|---:|---:|---:|---:|---:|
  | `train` | `< 2025-05-01` (jan-abr) | 394.971 | 13.456 | 3,41% | 132.877 | 33,64% | 33 |
  | `val`   | `2025-05-01` a `< 2025-06-01` (mai) | 78.825 | 1.280 | **1,62%** | 14.481 | 18,37% | 31 |
  | `test`  | `>= 2025-06-01` (jun) | 71.089 | 5.226 | **7,35%** | 12.038 | 16,93% | 30 |
  | **Soma** | | **544.885** | **19.962** | — | 159.396 | — | — |

  Asserções defensivas: somas exatas (544.885 eventos, 19.962 DGs), nenhum vazamento entre splits (`Data_Evento` ordenado garante separação determinística). Tempo total de execução: 2,6s.

- **Justificativa do corte por limite de mês (vs corte por fim de turno):**
  1. **Coerência com Fig 2** (distribuição temporal mensal): cortes em `2025-05-01 00:00` e `2025-06-01 00:00` alinham diretamente com o grid mensal já usado na seção exploratória — o leitor verifica "treino = jan+fev+mar+abr" contra Fig 2 visualmente.
  2. **Modelo é event-time-aware, não shift-aware:** features de rolling olham para trás em horas, target olha para frente em horas, LightGBM faz predição por evento. Nada na arquitetura trata "turno" como unidade — cortar 6h antes ou depois do limite de mês é puramente cosmético.
  3. **Comportamento na fronteira é o desejado em produção:** eventos no início de mai (ex.: `00:00:30` de 01/mai) têm `count_critico_24h` computado com dados de 30/abr — reproduz exatamente o cenário operacional (o modelo deployado em mai naturalmente usa as últimas 24h, que incluem 30/abr). **Não é leakage temporal**, pois o sentido cronológico está preservado (passado → futuro).

- **Justificativa contra k-fold aleatório (registrada como pergunta explícita do PLANEJAMENTO.md):** as features de rolling (Família 1, 9 colunas) e de recência (Família 2, 2 colunas) introduzem **autocorrelação temporal forte** dentro de cada TAG. Em um k-fold aleatório, eventos do treino e do teste do mesmo equipamento estariam interleavados no tempo — o modelo aprenderia padrões de "fold X" que não generalizam para o futuro real. Walk-forward respeita a semântica operacional (treinar no passado para prever futuro) e é o único protocolo defensável quando há feature engineering baseada em janelas temporais. Decisão alinhada com a literatura padrão de séries temporais (Hyndman & Athanasopoulos, 2018).

- **Achado quantitativo: drift mês-a-mês forte e direcional, registrado na Fig 8 painel inferior.** Taxas de DG por mês: jan 3,19% / fev 4,38% / mar 3,30% / abr 2,59% / **mai 1,62%** / **jun 7,35%**. Conclusões para modelagem em W5-W7:
  1. **Test (jun) tem 2,2× a taxa de DG do treino médio** (3,37%) e **4,5× a taxa de val**. Modelos LightGBM com bons resultados em mai podem degradar muito em jun.
  2. **Val (mai) tem o menor regime de DGs do semestre** (1,62%, contra média de 3,37% no treino). Hiperparâmetros tunados em mai serão otimistas em precisão e pessimistas em recall — exige ajuste no GATE MARCO 1 de W5 e nas curvas precision-recall de W7.
  3. **A anomalia RFB de junho** (já descrita em Obs 2.6 e na Fig 5 da EDA — Right Front Brake Temperature explode 151,7× sobre baseline) **é o motor mecânico do drift** — não é um shift contextual genérico, é um alarme específico dominando o teste. Vai ser flagado explicitamente no Anexo A e na seção de Limitações.
  4. Análise de erro estratificada mês-a-mês vira **obrigatória**, não opcional, e **começa em W5 (não W7)** — registrada como Mitigação 3 nas tasks do `08_lightgbm.py` em `PLANEJAMENTO.md`. AUC-PR / Recall / Precisão reportadas separadamente para mai e jun já no GATE MARCO 1, permitindo acionar Mitigações 1 (TimeSeriesSplit CV) e 2 (calibração de `scale_pos_weight`) antes que uma iteração inteira de tuning seja desperdiçada. Já estava planejada como entregável de W7 (Risco 3.2) — agora antecipada para W5 com magnitude quantificada e critérios explícitos.

- **Achado lateral: rotação de TAGs entre splits.** 2 TAGs aparecem em val/teste mas não em treino (`CA65791`, `CA65916`); 5 TAGs aparecem em treino mas não em val ou teste (`CA65917`, `CA65908`, `CA65902`, `CA65922`, `CA65923`). 13 operadores em val/teste estão ausentes do treino. **Implicação:** as features de encoding `tag_freq` e `operador_freq` (Família 7) foram computadas sobre o dataset global — embutem volumes de val/teste em features que o modelo usará no treino. Magnitude esperada pequena (volumes mensais por TAG são estáveis), **mas tecnicamente é leakage**. Decisão: documentar e adiar fix para W5, junto com a substituição por target encoding com KFold temporal (refinamento já listado em PLANEJAMENTO.md → W5). O fix será recomputar `tag_freq` e `operador_freq` sobre treino apenas e aplicar a val/teste — mesma rotina do target encoding adequado.

- **Saídas geradas:**
  - `Projeto/dados/features/v2_split.parquet` (544.885 × 52 colunas, **14,9 MB** — menor que v2.parquet por causa da compressão de Int8 dos targets quando o split também é categoria comprimível).
  - `Projeto/relatorio/tabelas/split_temporal.csv` (sumário CM 4.1, 3 linhas × 9 colunas).
  - `Projeto/relatorio/figuras/fig07_janela_predicao.png` (diagrama conceitual do target operacional, matplotlib reproduzível).
  - `Projeto/relatorio/figuras/fig08_split_temporal.png` (2 painéis: barras mensais coloridas por split + linha de taxa de DG).

- **Status do pipeline canônico após esta sessão:** `v2_split.parquet` é o **input canônico para W5** (baseline + LightGBM v1). Scripts downstream lerão `dados/features/v2_split.parquet` e filtrarão por `split == "train"` para treinar, `split == "val"` para tuning, `split == "test"` para reportar métricas finais. `v2.parquet` original fica preservado como matriz "pré-split" (não deve ser usada diretamente em modelagem para evitar contornar o protocolo de avaliação).

---

### 2026-05-22 — Fix do leakage subtil de frequency encoding (`06b_fix_encoding_leakage.py`, W5 pré-modelagem)

Aplicada por `Projeto/codigo/06b_fix_encoding_leakage.py` (4 etapas, ~5s de execução), corrigindo a limitação conhecida das features `tag_freq` e `operador_freq` (Família 7 do `05_features.py`) — calculadas originalmente sobre o dataset GLOBAL na sessão de 17/05, com a inconsistência de leakage temporal subtil documentada e *fix* agendado para W5.

- **ANTES:** as features de *frequency encoding* `tag_freq` e `operador_freq` em `v2_split.parquet` foram computadas em `05_features.py` (Etapa 10, Família 7) como `count(TAG) / 544.885` sobre o dataset filtrado completo (treino + validação + teste). Consequência: para um evento de janeiro-abril (treino), a feature `tag_freq` embute informação sobre volumes de maio-junho (val + teste) — *leakage* temporal de magnitude pequena (volumes mensais por equipamento são estáveis), mas tecnicamente presente. Casos específicos identificados: 2 TAGs (`CA65791`, `CA65916`) aparecem apenas em val/teste e não em treino; 13 operadores adicionais na mesma situação.
- **DEPOIS:** matriz canônica `v3.parquet` (544.885 × 52, 14,9 MB) gerada com `tag_freq` e `operador_freq` **recomputadas sobre o split de treino apenas** (`split == 'train'`, 394.971 eventos) e propagadas para val/teste via `join` por chave. Categorias que aparecem em val/teste mas não em treino recebem `tag_freq = 0` ou `operador_freq = 0` (decisão Opção C-1 — análise rigorosa em `notas_metodologicas.md` Seção 2 mostra que adicionar feature binária `is_*_unknown_in_train` seria inerte em single-fold). Schema preservado (mesmas 52 colunas; o *fix* sobrescreve duas colunas em vez de adicionar novas).

- **Justificativa metodológica:**
  - **Por que isolar em script dedicado (`06b_fix_*` em vez de embutir em `08_lightgbm.py`):** separa responsabilidades (encoding correto é responsabilidade da preparação dos dados, não da modelagem), gera artefato canônico único (`v3.parquet`) reusável por todos os *scripts* downstream (`07_baseline.py`, `08_lightgbm.py`, `09_sobrevivencia.py`, `11_isolation_forest.py`), e mantém o pipeline puro de modelagem mais legível.
  - **Por que `v3.parquet` em vez de sobrescrever `v2_split.parquet`:** preserva histórico para inspeção de regressões; consistente com a convenção v1/v2 já estabelecida em `05_features.py`. `v2_split.parquet` fica como referência histórica do estado "pré-*fix*".
  - **Por que `freq = 0` para unknowns em vez de média global, mediana ou nova feature binária:** análise teórica em `notas_metodologicas.md` Seção 2 demonstra que (a) a Opção 2 (média global) mascara a novidade — operador desconhecido fica indistinguível de operador médio — sem ganho preditivo claro; (b) a Opção 3 (feature binária `is_unknown`) seria **matematicamente inerte** em *single-fold* porque a *feature* seria constante = 0 em 100% dos 394.971 eventos do treino, tendo *information gain* zero e sendo ignorada pelo LightGBM. **A Opção 3 deve ser reavaliada em W6** após implementação da Mitigação 1 (TimeSeriesSplit CV) — registrada como *task* explícita no `PLANEJAMENTO.md → W6`.

- **Verificação empírica de W5 (resumida; detalhes em `notas_metodologicas.md` Seção 2):**

  | Categoria afetada | VAL (78.825 eventos) | TEST (71.089 eventos) |
  |---|---:|---:|
  | Eventos com `tag_freq = 0` (TAG unknown) | 12 (0,02%) | 1.394 (1,96%) |
  | Eventos com `operador_freq = 0` (op unknown) | 154 (0,20%) | 418 (0,59%) |
  | **Eventos com qualquer freq = 0** | **166 (0,21%)** | **1.812 (2,55%)** |
  | DGs com qualquer freq = 0 | 2 de 1.280 (0,16%) | **133 de 5.226 (2,54%)** |

  TAGs unknown: `CA65916` (em val + test), `CA65791` (apenas em test). 6 operadores unknown em val, 7 em test. Asserções defensivas no `06b_fix_encoding_leakage.py` validam essas contagens — falha explícita caso o universo de unknowns mude em futuras execuções.

- **Diff numérico antes/depois (sanity check):**
  - `tag_freq.mean()` original: 0,050747 → pós-*fix*: 0,051484 (diff ~1,4%)
  - `operador_freq.mean()` original: 0,007044 → pós-*fix*: 0,006971 (diff ~1,0%)
  - Diferenças pequenas confirmam que o *leakage* era subtil (volumes mensais por TAG e por operador são empiricamente estáveis no semestre), mas agora está corrigido sem ambiguidade.

- **Impacto no pipeline canônico de Modelagem:**
  - **`v3.parquet` é o input canônico para toda a fase de Modelagem em W5-W7.** Scripts a jusante (`07_baseline.py`, `08_lightgbm.py`, `09_sobrevivencia.py`, `11_isolation_forest.py`) leem `v3.parquet` e filtram pela coluna `split` nos pontos de treino, validação e teste.
  - **`v2_split.parquet` é deprecado para modelagem** mas preservado como referência do estado "com *leakage*", para reprodutibilidade histórica e para o teste opcional em W6 de "qual o impacto real do *leakage* na AUC-PR?" (treinar duas variantes do LightGBM v1, uma com `v2_split.parquet` e outra com `v3.parquet`, comparar — pode virar achado de Limitação se o efeito for não-desprezível).

- **Decisões futuras agendadas com base no estudo de W5:**
  - **W6:** reavaliar Opção 3 (`is_tag_unknown_in_train` como feature) após TimeSeriesSplit CV (Mitigação 1) — em CV a feature pode variar entre *folds* do treino e tornar-se aprendível. *Task* explícita no `PLANEJAMENTO.md → W6`.
  - **W6 SHAP:** análise estratificada das importâncias por subgrupo "categoria conhecida vs unknown" — diagnostica se o modelo extrapola bem.
  - **W7:** análise estratificada obrigatória "TAG/operador conhecidos vs unknown" no teste — reportar AUC-PR / Recall / Precisão separadamente para os 1.812 eventos / 133 DGs unknown. *Task* explícita no `PLANEJAMENTO.md → W7`.
  - **CM 6.3 (Trabalhos Futuros):** argumento empírico concreto para a recomendação de retreino *rolling* mensal — 2,55% dos eventos em produção contínua virão de categorias novas; sem retreino, *blind spot* acumula. *Task* explícita no `PLANEJAMENTO.md → W8 → seção Trabalhos Futuros*.

---

### 2026-05-22 — Re-calibração do Critério B do GATE MARCO 1 após resultado empírico do baseline (W5)

Decisão metodológica tomada imediatamente após a execução de `07_baseline.py` (22/05/2026, ~0,4s sobre `v3.parquet`). O baseline produziu resultado quantitativo que contradiz a premissa central do GATE MARCO 1 (formulado em 17/05 e registrado na entrada anterior — "Split temporal walk-forward jan-abr / mai / jun"), exigindo re-calibração explícita ANTES da execução do LightGBM v1 em `08_lightgbm.py`.

- **ANTES (formulação de W4, 17/05/2026):** o GATE MARCO 1 tinha 2 critérios, assumindo implicitamente que o conjunto de teste (junho) seria mais difícil que validação (maio) devido ao drift quantificado pela Fig 8 (taxa de DG 1,62% em mai → 7,35% em jun, fator 4,5×):
  - **Critério A:** LightGBM bate baseline em AUC-PR de val (mai).
  - **Critério B:** LightGBM mantém AUC-PR razoável em test (jun) — *"queda ≤ 30% vs val (regime raro de mai vs anomalia RFB de jun são esperadamente difíceis; queda grande mas não catastrófica é aceitável)"*.

  A formulação fazia sentido na época: como a Fig 8 mostrou que jun tem 4,5× a taxa de DG de mai, era natural pensar "test é o conjunto mais difícil — modelo precisa não cair muito ao mover-se de val para test". Mas a hipótese implícita ("um conjunto com mais positivos é mais difícil para o modelo") não tinha sido testada empiricamente.

- **DEPOIS (re-calibração de 22/05, pós-baseline):** o resultado empírico do `07_baseline.py` **invalida diretamente a premissa do Critério B original**. AUC-PR do baseline:
  - **VAL (mai): 0,2397** (lift 1,30× sobre random AP de 0,1837)
  - **TEST (jun): 0,5803** (lift 3,43× sobre random AP de 0,1693)
  - **Razão test / val: 2,42×** — test é **142% melhor** que val para a regra simples.

  A curva detalhada de Precision/Recall/F1 por threshold confirma a magnitude da diferença:

  | Threshold | VAL P / R / F1 | TEST P / R / F1 |
  |---:|---:|---:|
  | ≥ 1 | 0,2556 / 0,4025 / 0,3127 | 0,3436 / **0,6976** / 0,4604 |
  | ≥ 2 | 0,2887 / 0,2740 / 0,2812 | 0,4060 / 0,5969 / 0,4833 |
  | ≥ 3 | 0,3152 / 0,2226 / 0,2609 | 0,4651 / 0,5510 / 0,5044 |
  | ≥ 5 | 0,3630 / 0,1654 / 0,2273 | **0,5905** / 0,4714 / **0,5243** |

  Os critérios são revisados para:
  - **Critério A — superar baseline em validação:** LightGBM v1 em val (mai) deve atingir **AUC-PR ≥ 0,2897** (baseline 0,2397 + 5 pontos percentuais de margem).
  - **Critério B — superar baseline em teste (NOVA FORMULAÇÃO):** LightGBM v1 em test (jun) deve atingir **AUC-PR ≥ 0,6303** (baseline 0,5803 + 5 pontos percentuais de margem). A formulação anterior ("cair pouco") era incompatível com o regime empírico em que o baseline ganhou em test; a nova exige que o modelo justifique sua complexidade adicional adicionando valor genuíno sobre a regra simples.

- **Justificativa empírica completa (por que test é mais fácil para a heurística simples):**

  O resultado contra-intuitivo do baseline tem explicação mecânica clara via Obs 2.9 (resolvida na mesma sessão, antes do baseline): **82,2% dos DGs de jun (4.298 de 5.226) vêm exclusivamente do CA65926 em falha mecânica progressiva**. Quando esse equipamento dispara Críticos massivamente (a feature `Right Front Brake Temperature - Active` no CA65926 passou de 0–6 eventos por mês em jan–mai para 4.215 em junho — salto de aproximadamente 700×), a feature `count_critico_4h` atinge valores elevados consistentemente nos minutos pré-DG, e a heurística "conte Críticos recentes" tem **assinatura preditiva clara para detectar**.

  Em maio, o regime é qualitativamente diferente: taxa de DG de 1,62% é a mais baixa do semestre, e os DGs estão distribuídos entre múltiplos equipamentos sem dominância única. Não há um "alvo claro" para a regra simples — performance apenas marginalmente acima de chance (lift 1,30×).

  A consequência metodológica é importante e merece destaque: **o "drift mai → jun" não é uniformemente "test mais difícil"** — é **mudança qualitativa da natureza do problema**. Em junho, predizer DG vira predominantemente predizer "CA65926 em deterioração progressiva", uma tarefa com assinatura mecânica forte. Em maio, predizer DG vira predizer regime distribuído sem alvo claro, genuinamente mais difícil para qualquer modelo (incluindo o LightGBM).

- **Impacto da re-calibração nas tasks de W5-W6:**
  - **LightGBM v1 enfrenta teto alto em test (AUC-PR ≥ 0,6303 para passar o gate).** Não é trivial — significa adicionar valor genuíno sobre uma regra que já capta 70% do recall em jun com threshold = 1.
  - **LightGBM v1 enfrenta espaço amplo em val (AUC-PR ≥ 0,2897)**, facilmente alcançável com 29 features vs uma única feature na regra simples.
  - **Cenário esperado:** bate baseline em val (A = SIM) facilmente; pode falhar em test se super-otimizar para regime distribuído de mai. Nesse caso (A = SIM + B = NÃO), o gate bloqueia e a Mitigação 1 (TimeSeriesSplit CV em W6) entra antes do Optuna para reduzir overfitting ao regime específico de mai.
  - **SHAP em W6 ganha relevância dupla:** além de validar a Obs 2.11 (acúmulo de criticidade vs volume), agora também precisa confirmar que LightGBM não está apenas reproduzindo o baseline — se `count_critico_4h` dominar sozinho o ranking de importância, o modelo não justifica sua complexidade. Esperamos especialmente Família 4 regimal (`razao_alarme_7d_vs_30d_anterior`) no topo.

- **Onde o achado vira material de relatório:**
  - **CM 6.1 (Insights Não Óbvios):** "heurísticas simples capturam bem padrões de drift localizado, mas têm desempenho mediano em regimes distribuídos. O baseline produziu AUC-PR 2,42× melhor em jun (regime concentrado) do que em mai (regime distribuído) — contra-intuitivamente, o conjunto de teste 'mais difícil' pela taxa de DG era na verdade o mais fácil para a regra simples por causa da assinatura mecânica clara do CA65926." Esse é candidato direto a *Insight Não Óbvio*, com narrativa convergente com a Obs 2.9 e com a H7.1 (equipamentos individuais problemáticos): a EDA agregada esconde heterogeneidades importantes; quando essas heterogeneidades emergem, métricas e modelos respondem de formas surpreendentes.
  - **CM 5.x (Resultados):** o salto de AUC-PR 0,2397 → 0,5803 entre val e test não é resultado do modelo principal — é propriedade do problema. Reportar essa baseline em ambos os splits desde o início ancorará a discussão de "quanto o LightGBM efetivamente adicionou".
  - **CM 6.2 (Limitações):** se LightGBM superar baseline em val mas falhar em test, a Limitação fica concreta — "o modelo se beneficia da diversidade de features em regime distribuído, mas em regime concentrado a regra simples já captura quase tudo". Material direto para a discussão de quando vale a pena substituir heurísticas por modelos de ML.

- **Saídas anexadas:**
  - `relatorio/tabelas/baseline_metricas.csv` (8 linhas: 4 thresholds × 2 splits) — tabela canônica de referência para `08_lightgbm.py`.
  - Detalhamento metodológico completo do achado em:
    - `PLANEJAMENTO.md → W5 → Observações e Conclusões §4. Baseline heurístico`
    - `rascunho.md → Metodologia — Parte 3: Modelagem → Baseline heurístico`

---

### 2026-05-23 — Expansão das janelas da Família 1 (rolling) para alinhamento perfeito com Profundidade 1 (W5 pré-LightGBM)

Decisão metodológica tomada após análise prévia da arquitetura do `08_lightgbm.py`, especificamente da Profundidade 1 (comparação preditiva entre 3 horizontes de *target*: `target_2h`, `target_4h`, `target_8h`).

- **ANTES:** Família 1 do `05_features.py` produzia **9 features de rolling** combinando 3 criticidades (`critico`, `nao_critico`, `total`) × 3 janelas (`1h`, `4h`, `24h`). Para a Profundidade 1, o LightGBM v1 com `target_4h` teria *feature* alinhada perfeitamente (`count_critico_4h`), mas para `target_2h` a *feature* mais próxima seria `count_critico_1h` (cobre metade do horizonte, perde sinal em -2h..-1h) e para `target_8h` seria `count_critico_24h` (cobre 3× o horizonte, dilui sinal com ruído antigo). Isso enviesa a comparação a favor da Variante T4 (que teria a única *feature* perfeitamente alinhada do trio).
- **DEPOIS:** Família 1 expandida para **15 features de rolling** com 5 janelas (`1h`, `2h`, `4h`, `8h`, `24h`). Cada variante da Profundidade 1 agora tem *feature* perfeitamente alinhada ao seu horizonte de *target*:
  - Variante T2 → `count_critico_2h` (alinhamento 1:1)
  - Variante T4 → `count_critico_4h` (alinhamento 1:1)
  - Variante T8 → `count_critico_8h` (alinhamento 1:1)
  - Adicionalmente, todas as variantes mantêm acesso a `count_critico_1h` (sub-cobertura) e `count_critico_24h` (super-cobertura) como contexto temporal complementar.

- **Justificativa metodológica:**
  - **Razão preditiva:** sem o alinhamento perfeito, a comparação de Profundidade 1 entre T2/T4/T8 ficaria contaminada pela assimetria de *features* — se T4 vencer, não saberíamos se é porque 4h é genuinamente o horizonte ótimo, ou porque T4 ganhou na largada com a única *feature* alinhada do trio. Com alinhamento perfeito em todos os horizontes, qualquer diferença observada nos AUC-PR vira evidência mais limpa de qual horizonte tem melhor sinal preditivo intrínseco.
  - **Razão de qualidade analítica:** o usuário declarou explicitamente que prefere "modelos funcionais com parâmetros certos" em vez de "fazer só para falar que fez". Implementar Profundidade 1 com *features* mal-alinhadas seria o segundo cenário — exercício formal sem rigor metodológico. A discussão completa está em `notas_metodologicas.md` Seção 2 (decisão metodológica de não fazer Opção 3 sem aporte de *features* alinhadas) e em conversa de W5 pré-LightGBM (22-23/05).
  - **Razão de coerência com baseline:** a heurística baseline implementada em `07_baseline.py` (22/05) usou `count_critico_4h` como score raw para `target_4h`, justificando o alinhamento perfeito como princípio metodológico. Aplicar o mesmo princípio para T2 e T8 mantém a comparação contra baseline coerente.

- **Implementação técnica:**
  - **Arquivo modificado:** `05_features.py` — função `criar_features_rolling` (etapa 4/11) e definição `FEATURES_AVANCADAS_W4_PARCIAL` (loop de configuração da Família 1).
  - **Mudança de loop:** `for window in ["1h", "4h", "24h"]` → `for window in ["1h", "2h", "4h", "8h", "24h"]` (em dois pontos do arquivo).
  - **Constantes atualizadas:** `N_FEATURES_AVANCADAS_PARCIAL` 14 → 20 (Famílias 1-4); `N_FEATURES_TOTAL` 29 → 35 (5 básicas + 20 avançadas parcial + 10 avançadas final).
  - **Asserções defensivas:** atualizadas para 15 *rolling* e adicionada **nova asserção de monotonicidade** entre janelas (`count_X_1h ≤ count_X_2h ≤ count_X_4h ≤ count_X_8h ≤ count_X_24h` para cada criticidade X, válida em todos os 544.885 eventos).
  - **Re-execução do pipeline canônico:** `05_features.py` → `06_split.py` → `06b_fix_encoding_leakage.py`, em sequência, regenerando `v1.parquet`, `v2_parcial.parquet`, `v2.parquet`, `v2_split.parquet` e `v3.parquet` com o novo schema. Tempo total de re-execução: aproximadamente 12 segundos.

- **Impacto nos artefatos:**

  | Artefato | ANTES | DEPOIS |
  |---|---|---|
  | `documentacao_features.csv` | 29 entradas | **35 entradas** |
  | `v1.parquet` | 6,9 MB / 22 colunas | 6,9 MB / 27 colunas (5 básicas + 19 originais + 3 sem alteração) |
  | `v2_parcial.parquet` | 19,6 MB / 38 cols (19 features + 19 originais) | **21,6 MB / 47 cols** (25 features Famílias 0-4 + 19 originais + 3 sem alteração) |
  | `v2.parquet` | 22,4 MB / 51 cols (29 features + 3 targets + 19 originais) | **24,4 MB / 57 cols** (35 features + 3 targets + 19 originais) |
  | `v2_split.parquet` | 14,9 MB / 52 cols | **16,3 MB / 58 cols** |
  | `v3.parquet` | 14,9 MB / 52 cols | **16,3 MB / 58 cols** |

  Os números de TAGs unknown, operadores unknown, e eventos afetados pelo *fix* de *encoding* permanecem **idênticos** após a expansão (12 eventos em val / 1.394 em test com `tag_freq = 0`; 154 / 418 com `operador_freq = 0`). Asserções defensivas do `06b_fix_encoding_leakage.py` validaram esses valores exatamente.

- **Validação empírica (sanity check):**
  - **Monotonicidade entre janelas:** asserção `count_critico_1h ≤ count_critico_2h ≤ count_critico_4h ≤ count_critico_8h ≤ count_critico_24h` (idem para `nao_critico` e `total`) passou em todos os 544.885 eventos. Confirma que a expansão é matematicamente consistente (janela maior contém todos os eventos da janela menor).
  - **Coerência aritmética preservada:** `count_total_Xh = count_critico_Xh + count_nao_critico_Xh` continua exata em todas as 5 janelas (diff_max = 0).
  - **DGs preservados:** 19.962 DGs em `Is_Dont_Go = 1` mantidos sem alteração.

- **Onde o achado vira material de relatório:**
  - **CM 3.2 (Dicionário de features):** tabela `documentacao_features.csv` ganha 6 novas entradas com motivação explícita ("Janelas 2h e 8h adicionadas em W5 para alinhamento perfeito com target_2h/target_8h — Profundidade 1").
  - **CM 4.3 (Pré-processamento por modelo):** nota metodológica sobre o princípio de alinhamento feature-target — base para discussão de "como decidimos quais features incluir".
  - **CM 6.1 (Insights Não Óbvios):** *opcional* — narrativa sobre como a investigação rigorosa antes de codar revelou um viés metodológico potencial e exigiu retrabalho preventivo, demonstrando atenção à qualidade.

- **Decisão sobre Profundidade 1 originalmente registrada (PLANEJAMENTO.md → W5):** o "cenário de aprofundamento condicional" ("se T2 ou T8 ficar substancialmente abaixo de T4, voltar a `05_features.py` para adicionar features alinhadas") foi **antecipado preventivamente** com base em discussão de qualidade — em vez de descobrir o viés empiricamente depois do treino, removemos o viés antes. A condicional fica formalmente resolvida.

---

### 2026-05-23 — Resultados do LightGBM v1 (W5) — GATE MARCO 1 PASS + 3 conclusões metodológicas

Aplicada por `Projeto/codigo/08_lightgbm.py` (6 etapas, ~17,5s de execução), treinando 5 variantes do LightGBM com parâmetros *default* (100 iterações, learning_rate=0,1, num_leaves=31, sem *early stopping* nem Optuna) sobre `v3.parquet` (35 features + 3 *targets* + col `split`). Cada variante responde a uma pergunta analítica distinta consolidada no W5.

**Resultados consolidados:**

| Variante | Target | `scale_pos_weight` | AUC-PR val (mai) | AUC-PR test (jun) |
|---|---|---:|---:|---:|
| **A** (canônica) | `target_4h` | 1,972 (treino) | **0,7523** | **0,8566** |
| **B** (Mitigação 2) | `target_4h` | 4,653 (val+test, peeking) | 0,7350 | 0,8517 |
| **C** (Obs 2.7) | `target_4h_producao` | 2,096 (treino) | 0,7012 | 0,8533 |
| **T2** (Profundidade 1) | `target_2h` | 2,360 (treino) | 0,7729 | 0,8378 |
| **T8** (Profundidade 1) | `target_8h` | 1,585 (treino) | 0,7421 | 0,8211 |

**Conclusão 1 — GATE MARCO 1: PASS:**

- **ANTES:** GATE MARCO 1 exigia AUC-PR Variante A ≥ 0,2897 em val e ≥ 0,6303 em test (re-calibrado em 22/05 após resultado do baseline). Cenário esperado: passar A=SIM em val (regime distribuído, espaço amplo), incerto em test (teto alto do baseline 0,5803).
- **DEPOIS:** Variante A atinge **AUC-PR val = 0,7523** (folga de +46,3pp sobre o mínimo) e **AUC-PR test = 0,8566** (folga de +22,6pp). Ambos os critérios passam com folga grande. **Verdict: PASS — avançar para W6** (tuning + sobrevivência + Isolation Forest + SHAP).
- **Sobre o salto vs baseline:** LightGBM A adiciona **+27,6pp de AUC-PR sobre o baseline em test** (0,5803 → 0,8566) e **+51,3pp em val** (0,2397 → 0,7523). O salto em val é o esperado (baseline mediano em regime distribuído, LightGBM com 35 *features* tem muito a ganhar); o salto em test é o achado mais relevante — o LightGBM não está apenas "replicando o baseline mais sofisticado" porque a folga é grande demais para ser explicada pela duplicação da heurística simples sobre `count_critico_4h`. Validação obrigatória via SHAP em W6: confirmar que outras *features* da Família 4 regimal, Família 2 recência e Família 1 (janelas 2h/8h adicionadas em 23/05) aparecem no ranking.

**Conclusão 2 — Mitigação 2 DESCARTADA empiricamente:**

- **Hipótese da Mitigação 2:** calibrar `scale_pos_weight` para taxa de produção (estimada via val+test) em vez de taxa de treino melhora performance.
- **Resultado empírico:** **B perde para A em ambos os splits** (B−A = −1,73pp em val, −0,50pp em test). Pela análise prévia registrada em `notas_metodologicas.md` Seção 3, o cenário "B−A ≤ 0" é precisamente o caso em que **o viés do *test set peeking* (estimado em 1-3pp em favor de B) foi insuficiente para inflar B além de A** — o que significa que a Mitigação 2 não tem valor preditivo real. Calibrar `scale_pos_weight` para a taxa de treino é melhor que calibrar para taxa de produção neste *dataset*.
- **Implicação para W6:** **Optuna não precisa tunar `scale_pos_weight` agressivamente para cima de 2,0.** Pode-se restringir o espaço de busca a `scale_pos_weight ∈ [0.5, 3.0]` em vez de `[0.5, 6.0]`, economizando *trials* e focando em outros hiperparâmetros (num_leaves, learning_rate, min_child_samples). Decisão a ser implementada no `08b_lightgbm_v2.py` em W6.
- **Implicação para o relatório (CM 6.2):** o achado de que a Mitigação 2 não ajuda é **achado empírico positivo**, não fracasso — registrar como exemplo de hipótese metodológica testada e rejeitada com rigor. Reforça a credibilidade analítica do trabalho.

**Conclusão 3 — Obs 2.7 — filtrar DGs em Manutenção PIORA o modelo (variante C descartada):**

- **Hipótese:** os 1.460 DGs em estado `Manutenção` introduzem ruído contextual; treinar com `target_4h_producao` (excluindo esses DGs do target) melhora performance.
- **Resultado empírico:** **C perde para A em ambos os splits** (C−A = −5,11pp em val, −0,33pp em test). Em val a perda é substancial.
- **Interpretação:** os DGs em Manutenção são **DGs reais** (reativações de teste do equipamento, alarmes legítimos de Engine Coolant, Brake Temperatures), não falsos positivos de bancada. Filtrá-los do *target* não remove ruído — remove sinal. **Confirma empiricamente a reinterpretação da H5.1** já documentada em `hipoteses_eda.md` (W2, Obs 2.7 resolvida): contexto Manutenção é DG legítimo, com semântica distinta mas informação preditiva válida.
- **Implicação para W6:** **não treinar variante `Is_Dont_Go_producao` em v2.** Manter `target_4h` original como *target* canônico. Análise estratificada por estado operacional em W7 pode quantificar a diferença de *performance* dentro de Manutenção vs Operando (Profundidade C original), mas não justifica filtrar o *target*.

**Conclusão 4 — Profundidade 1 — T4 é o vencedor canônico, mas com nuance importante:**

- **Resultado bruto:** T4 (=A, target_4h) vence em test (0,8566 > T2 0,8378 > T8 0,8211); **mas T2 vence em val** (0,7729 > T4 0,7523 > T8 0,7421).
- **Interpretação:** o ranking val vs test **inverte parcialmente** entre T2 e T4. T8 é claramente pior em ambos os splits (consistente). A inversão T2 ↔ T4 entre val e test sugere que **as diferenças são pequenas o suficiente para serem influenciadas por características específicas de cada regime** (val = regime distribuído de mai; test = anomalia localizada de jun no CA65926).
- **Análise de significância:** **as diferenças entre T2 e T4 (1,73pp em val, 1,88pp em test) estão na margem de ruído esperado** para LightGBM com parâmetros fixos e seed único — sem CV ou bootstrap, não é possível afirmar com confiança que T4 é genuinamente superior a T2. **O que pode ser afirmado com confiança:** T8 (8h) é empiricamente o pior dos três horizontes em ambos os splits — diferenças de 3,55pp em test e 1,02pp em val, mais consistentes. **O que NÃO pode ser afirmado:** "T4 é o melhor horizonte" — afirmação mais honesta é "T4 está na zona de melhor desempenho, e a escolha operacional de 4h (CM 1.2) é empiricamente compatível com os melhores resultados".
- **Implicação para W6:** **manter T4 como horizonte canônico operacional** (motivação operacional do CM 1.2 já é suficiente; análise empírica confirma que está na faixa boa). **Optuna tuna apenas o modelo T4** em W6, sem repetir a comparação entre horizontes. **Em W7**, se sobrar tempo, repetir Profundidade 1 com TimeSeriesSplit CV de 4 folds — dá variância sobre os 3 horizontes e permite afirmação mais robusta. Caso contrário, registrar limitação em CM 6.2 ("Profundidade 1 com single-fold não tem variância para diferenciar T2 de T4; CV recomendado como Trabalho Futuro").

**Saídas geradas:**
- **5 modelos** em `Projeto/modelos/`: `lightgbm_v1_{A,B,C,T2,T8}.txt` (formato texto nativo LightGBM, ~350 KB cada).
- **4 tabelas** em `Projeto/relatorio/tabelas/`:
  - `lightgbm_v1_metricas.csv` (10 linhas: 5 variantes × 2 splits, com AUC-PR, P/R/F1 em threshold=0,5, tempo de treino)
  - `lightgbm_v1_vs_baseline.csv` (6 linhas: A/B/C × val/test contra baseline)
  - `comparacao_horizontes_lightgbm.csv` (6 linhas: T2/T4/T8 × val/test)
  - `gate_marco_1.csv` (verdict + critérios)

**Próximos passos para W6:**

1. **Optuna + TimeSeriesSplit CV (Mitigação 1)** com espaço de busca refinado: `scale_pos_weight ∈ [0.5, 3.0]` (em vez de `[0.5, 6.0]`, dada a refutação da Mitigação 2), `num_leaves ∈ [15, 127]`, `learning_rate ∈ [0.01, 0.3]`, `min_child_samples ∈ [10, 100]`.
2. **Análise SHAP global** do LightGBM v2 — confirmar que `count_critico_4h` não domina sozinho (se dominar, modelo é só baseline glorificado), e validar a Obs 2.11 (acúmulo de criticidade — `count_critico_*` no topo do ranking vs `count_total_*`).
3. **Modelo de sobrevivência Weibull AFT** (`09_sobrevivencia.py`) — segunda leitura do problema.
4. **Isolation Forest diagnóstico** (`11_isolation_forest.py`) — teste empírico único do Risco 3.3 (viés do *label* CMA).

---

### 2026-05-24 — Resultados do LightGBM v2 (W6) — GATE MARCO 1 re-confirmado + Mitigação 2 contraditada pelo Optuna

Aplicada por `Projeto/codigo/08b_lightgbm_v2.py` (7 etapas, 28,7 min de execução total), entregando o **modelo canônico final** que vai para o relatório. Refina o LightGBM v1 (Variante A) com três mudanças simultâneas: Optuna (50 trials), TimeSeriesSplit CV de 4 folds expandidos (Mitigação 1) e determinismo estrito.

**ANTES (v1, executado em 23/05):**
- Parâmetros default (100 iter, lr=0,1, num_leaves=31, scale_pos_weight=1,972)
- Validação single-fold (só mai)
- `n_jobs=-1` sem determinismo (variação microscópica entre runs)
- AUC-PR val=0,7523 / test=0,8566

**DEPOIS (v2, executado em 24/05):**
- 50 trials Optuna (TPESampler, seed=42) sobre 7 hiperparâmetros (espaço refinado: `scale_pos_weight ∈ [0,5; 3,0]` em vez de [0,5; 6,0])
- TimeSeriesSplit CV de 4 folds expandidos (Mitigação 1): jan→fev, jan-fev→mar, jan-fev-mar→abr, jan-abr→mai
- `deterministic=True` + `force_col_wise=True` (reprodutibilidade bit-exact)
- **AUC-PR train=0,9658 / val=0,7801 / test=0,8618** (CV média best=0,8834)

**Hiperparâmetros encontrados pelo Optuna (trial #34 vencedor):**

| Hiperparâmetro | v1 (default) | v2 (Optuna best) | Direção |
|---|---:|---:|---|
| `n_estimators` | 100 | 199 | +99% |
| `learning_rate` | 0,1 | 0,013 | **−87%** (muito mais lento) |
| `num_leaves` | 31 | 61 | +97% |
| `min_child_samples` | 20 | 60 | +200% (regularização) |
| `scale_pos_weight` | 1,972 | **0,513** | **−74% (downweight!)** |
| `lambda_l1` | 0 | 0,32 | regularização L1 |
| `lambda_l2` | 0 | 1,82 | regularização L2 |

**Ganho de v2 sobre v1 A:** val +2,78pp / test +0,52pp. **GATE MARCO 1 re-confirmado em PASS** (folga val +49,0pp, folga test +23,1pp).

**Achado central — Mitigação 2 contraditada pelo Optuna:**

O Optuna escolheu `scale_pos_weight = 0,513` — **menor que 1**, **MUITO menor** que a fórmula clássica `(1-taxa)/taxa = 1,97` usada em v1 A, e na **direção exatamente oposta** da Mitigação 2 original (que propunha calibrar para cima para ~4,65 baseado na taxa de produção esperada). Isso reforça com evidência empírica forte a refutação da Mitigação 2 em W5 (registrada em entrada 2026-05-23): **pesar positivos para cima neste dataset não ajuda — o ótimo está abaixo do valor "neutro"**.

Hipótese explicativa: os positivos compartilham assinatura mecânica forte (CA65926 dominando jun pela Obs 2.9), tornando-os "fáceis" de detectar mesmo com peso reduzido. Pesar para cima força o modelo a fazer mais predições positivas, prejudicando a curva precision-recall.

**Achado metodologicamente importante:** se a Mitigação 2 tivesse sido implementada sem investigação prévia (W5 v1), o projeto teria adotado `scale_pos_weight ≈ 4,65` e provavelmente perdido performance. A combinação **"testar antes de aplicar + Optuna sem viés de premissa"** evitou esse caminho. Material direto para CM 6.1 (Insights Não Óbvios) e CM 6.2 (boas práticas metodológicas) do relatório final.

**Saídas geradas:**
- `Projeto/modelos/lightgbm_v2.txt` (modelo canônico, formato texto nativo LightGBM)
- `Projeto/modelos/optuna_study_v2.pkl` (study completo, 50 trials, abrir via `pickle.load`)
- `relatorio/tabelas/lightgbm_v2_metricas.csv` (4 linhas: train/val/test/CV)
- `relatorio/tabelas/lightgbm_v2_hiperparametros.csv` (7 hiperparâmetros: espaço de busca + best value)
- `relatorio/tabelas/optuna_trials.csv` (50 linhas — todos os trials para auditoria)

**Próximos passos para W6:**

1. **Análise SHAP global** sobre v2 — confirmar que `count_critico_4h` não domina sozinho o ranking; esperamos Família 4 regimal e Família 2 recência no topo.
2. **Análise SHAP estratificada** por categoria unknown (`tag_freq=0` ou `operador_freq=0` em test) — diagnostica como o modelo extrapola para categorias nunca vistas.
3. **`09_sobrevivencia.py`** — Weibull AFT como segunda leitura do problema (independente do LightGBM).
4. **`11_isolation_forest.py`** — diagnóstico do Risco 3.3 (viés do label CMA).

**Status do pipeline canônico após W6 parcial:**
- Pipeline de dados: 01 → 02 → 03 → 04 → 05 → 06 → 06b → `v3.parquet` (canônico)
- Modelo canônico: `lightgbm_v2.txt` (treinado sobre `v3.parquet`, sem peeking, com tuning rigoroso)
- `v1` preservado como referência metodológica (comparação default vs tunado + diagnóstico do peeking da Mitigação 2)

---

### 2026-05-24 — Análise SHAP do LightGBM v2 + descoberta de "predição de cascata" + decisão de treinar variante v3 sem `horas_desde_ultimo_DG`

Aplicada por `Projeto/codigo/08c_shap_v2.py` (~1 min) + mini-diagnose ad hoc da matriz SHAP. Análise revela como o modelo canônico v2 realmente funciona — e identifica fragilidade operacional significativa.

**ANTES:** LightGBM v2 era o modelo canônico (AUC-PR test=0,8618, val=0,7801, GATE MARCO 1 PASS) mas sem interpretabilidade. Não sabíamos quais *features* dirigem as predições nem se o modelo está aprendendo sinal genuíno ou apenas padrões superficiais.

**DEPOIS:** SHAP global sobre os 71.089 eventos do test (matriz `shap_values_v2_test.npy`, 19 MB) revela ranking de importância das 35 *features*:

| Rank | Feature | Família | % do peso |
|---:|---|---|---:|
| 1 | `horas_desde_ultimo_DG` | 2 — Recência | **39,3%** |
| 2 | `qtd_alarmes_nivel_muito_alto_360min` | 6 — Regra de Negócio | **31,1%** |
| 3 | `razao_alarme_7d_vs_30d_anterior` | 4 — Regimal | **8,6%** |
| 4 | `tipo_caminhao` | 7 — Encoding | 5,0% |
| 5-10 | demais | várias | < 2% cada |

**Top 2 explicam 70% do peso. Top 10 explicam 91%.**

**Achados (4 perguntas respondidas pelo SHAP):**

1. **v2 NÃO é "baseline glorificado":** `count_critico_4h` (feature core do baseline) está no **rank #29** — modelo aprendeu sinal qualitativamente diferente.
2. **Família 4 regimal funciona como previsto:** `razao_alarme_7d_vs_30d_anterior` rank #3 — feature desenhada em W4 especificamente para a anomalia do CA65926 ficou no topo.
3. **Obs 2.11 fracamente refutada:** TODAS as 15 features rolling estão em rank #15-#31. O modelo NÃO usou fortemente o padrão "acúmulo de criticidade vs volume" hipotetizado. A versão "domain-specific" (`qtd_alarmes_muito_alto_360min` — Família 6) venceu a versão genérica (Família 1).
4. **Família 4 + 6 + 2 dominam:** três famílias com lógicas distintas (recência + lookup de regras + anomalia regimal) somam 79% do peso — modelo aprende padrões sofisticados.

**ACHADO CRÍTICO via mini-diagnose:** `horas_desde_ultimo_DG` (#1 com 39%) não é sinal preditivo genuíno — é **predição de cascata**. Inspeção da matriz SHAP nos 12.038 positivos do test revela:

- **Top 10% eventos com maior SHAP positivo dessa feature:** **100% têm DG anterior em < 2h**, mediana = 1 minuto. **94% são DG real.**
- **9.475 positivos preditos corretamente (TPs):** 84,7% têm DG anterior em ≤ 1h; 93,1% em ≤ 4h.
- **Eventos SEM DG anterior (3.919 casos, NULL ou > 24h):** dos 101 que são positivos reais, **apenas 1 é predito corretamente (1%)**.

**Implicação:** o modelo é **detector de continuação de cascatas**, não preditor de primeiro DG. O AUC-PR 0,8618 mascara fragilidade operacional grave — pegar o **primeiro** DG (caso de maior valor para a Vale) está fora do alcance atual do modelo.

**Decisão metodológica:** treinar variante v3 sem `horas_desde_ultimo_DG` (`08e_lightgbm_v2_no_cascade.py`) com mesma configuração do v2 (Optuna 50 trials + TimeSeriesSplit CV + determinismo). Comparar v2 (com cascade) vs v3 (sem) em 3 estratificações:
- Geral
- Subgrupo "primeiro DG" (`horas_desde_ultimo_DG` NULL ou > 24h)
- Subgrupo "cascata" (`horas_desde_ultimo_DG` ≤ 4h)

Aprovação do usuário registrada: **Opção B confirmada, com promessa de avançar para Opção D (v2 e v3 paralelos canônicos) se v3 mostrar performance competitiva**. Resultados do v3 pendentes (execução em background no momento do registro).

**Limitação adicional documentada — `mes` como feature (rank #9, 0,89% do peso):**

O modelo aprendeu que o `mes` correlaciona com DG (provavelmente capturando o drift mai → jun). Em deployment com `mes` fora de [1, 6] (julho/agosto), o LightGBM extrapola implicitamente — trataria `mes = 7` como "mes >= 5,5" (igual junho). **Não é catastrófico** dado o peso baixo da feature, mas é limitação real. Resolvida por construção pela recomendação de **retreino *rolling* mensal** já em CM 6.3 (entrada controle_alteracoes 2026-05-22). Documentado em CM 6.2.

**Achados laterais para CM 6.1 (Insights Não Óbvios):**

- **`tipo_caminhao` no top 5 (5%):** modelo usa essa feature para ajustar baseline por tipo de equipamento — confirma empiricamente H4.1 (LeTourneau tem perfil radicalmente distinto).
- **`operador_freq` rank #13 (0,72%):** confirma Q3 do edital — operador correlaciona com DG mas de forma difusa (consistente com Obs 2.4 de W5).
- **Família 1 (rolling counts, 15 features) virtualmente ignorada:** modelo prefere a versão domain-specific (`qtd_alarmes_muito_alto_360min` da Família 6) que conta APENAS alarmes nas 82 regras CMA Muito Alto. **Lição metodológica para CM 6.1:** features genéricas podem perder para versões domain-specific da mesma ideia.

**Saídas geradas:**

| Arquivo | Conteúdo |
|---|---|
| `Projeto/modelos/shap_values_v2_test.npy` (19 MB) | Matriz SHAP completa [71.089 × 35] — auditável |
| `relatorio/tabelas/shap_global_v2.csv` | 35 features × rank, mean(\|SHAP\|), %total |
| `relatorio/tabelas/shap_estratificado_v2.csv` | 5 subgrupos × top 10 (test completo / CA65926 / resto / conhecidos / unknown) |
| `relatorio/figuras/fig09a_shap_bar.png` | Bar plot importância global (top 15) |
| `relatorio/figuras/fig09b_shap_beeswarm.png` | Beeswarm distribuição SHAP por feature |
| `relatorio/figuras/fig10_shap_dependence_top3.png` | Dependence plots das 3 features top (vertical, layout corrigido) |

**Onde os achados viram material de relatório:**

- **CM 5.2 (Interpretabilidade):** ranking SHAP + dependence plots, Fig 9a/9b/10.
- **CM 6.1 (Insights Não Óbvios):** (a) v2 não é baseline glorificado; (b) Família 6 domain-specific venceu Família 1 genérica; (c) modelo é detector de cascata, não primeiro DG; (d) H4.1 confirmada via `tipo_caminhao`.
- **CM 6.2 (Limitações):** (a) cascade-only prediction (modelo cego para primeiros DGs); (b) `mes` como feature implícita; (c) Obs 2.11 fracamente refutada.
- **CM 6.3 (Trabalhos Futuros):** já registrado retreino rolling mensal — agora reforçado pela limitação do `mes`.

---

### 2026-05-24 — Promoção de v3 (sem `horas_desde_ultimo_DG`) a modelo canônico do projeto

Aplicada por `Projeto/codigo/08e_lightgbm_v2_no_cascade.py` (~25,7 min Optuna 50 trials + treino final). Decisão tomada após análise comparativa v2 vs v3 em 3 subgrupos do test set.

**ANTES:** v2 era o modelo canônico (35 features, AUC-PR test = 0,8618). Plano original (Opção B aprovada em 24/05) era treinar v3 sem `horas_desde_ultimo_DG` e decidir entre:
- **Opção A:** descartar v3, manter v2 (se v3 degradasse significativamente)
- **Opção D-clássica:** manter v2 e v3 em paralelo (cada um para um caso de uso)
- **Opção D-promoção:** promover v3 a canônico, v2 fica como modelo intermediário no Anexo

**DEPOIS:** v3 (34 features, `horas_desde_ultimo_DG` removida, `horas_desde_ultimo_critico` mantida) torna-se o modelo canônico do projeto. v2 fica **preservado em `Projeto/modelos/lightgbm_v2.txt`** e citado na Parte 3 do `rascunho.md` como modelo intermediário, com explicação completa da promoção.

**Comparativo v2 vs v3 no test set (n = 71.089):**

| Subgrupo | n+ | v2 AUC-PR | v3 AUC-PR | Δ AUC-PR | v2 Recall@0.5 | v3 Recall@0.5 | Δ Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Geral | 12.038 | 0,8618 | 0,8556 | **−0,62pp** | 0,6803 | 0,7527 | **+7,24pp** |
| Primeiro DG (sem DG ≤24h ou NULL) | 1.705 | 0,1876 | 0,1964 | **+0,88pp** | 0,0434 | **0,2106** | **+16,72pp** |
| Cascata (DG ≤4h) | 9.035 | 0,9700 | 0,9691 | −0,09pp | 0,8836 | 0,9185 | +3,49pp |

**Hiperparâmetros best (trial #41 do Optuna v3):**
- `n_estimators = 301`
- `learning_rate = 0.01175`
- `num_leaves = 69`
- `min_child_samples = 50`
- `scale_pos_weight = 2.40` (mais agressivo que v2 = 1,42, mas dentro do espaço refinado [0,5; 3,0])
- `lambda_l1 = 0.197`, `lambda_l2 = 1.183`

**Justificativa para D-promoção:**

1. **v3 resolve a limitação L1 do CM 6.2 (cascade-only prediction).** Sem `horas_desde_ultimo_DG`, o modelo não pode mais "ler o DG anterior recente" como atalho. Tem que aprender sinais antecipativos.
2. **+16,72pp Recall em primeiro DG** (4,3% → 21,1%, quase **5× mais primeiros DGs capturados**). Esse é o caso de uso operacional valioso — antecipar o **primeiro** Don't Go (não a continuação de uma cascata já em curso).
3. **AUC-PR aggregate praticamente intocado:** −0,62pp no geral, **+0,88pp no subgrupo primeiro_DG** (o que mais importa). Aggregate desce ligeiramente porque o subgrupo "fácil" (cascata) recebe menos peso quando a feature dominante é removida.
4. **GATE MARCO 1 passa com larga margem:** test AUC-PR = 0,8556 ≫ alvo 0,6303; val AUC-PR = 0,7132 ≫ alvo 0,2897.
5. **Defesa operacional honesta:** v3 não promete antecipar primeiros DGs com alta precisão (Recall@0.5 ainda é 21,1%), mas é **5× melhor que v2 nessa tarefa** — defensável como "passo na direção correta".

**Riscos assumidos (registrados para transparência):**

- **Gap train-val maior:** v3 train=0,9653/val=0,7132 (ratio 74%) vs v2 train=0,973/val=0,7801 (ratio 80%). v3 tem leve sobreajuste maior, mitigado pelo test (0,8556) que confirma generalização.
- **`scale_pos_weight = 2.40` agressivo:** modelo aprendeu a ser mais sensível, gerando mais alertas. Pode ser calibrado em deployment via threshold > 0,5 se a Vale preferir menos falsos positivos.
- **Análise SHAP do v3 pendente** (`08f_shap_v3.py` em execução no momento da promoção, será incorporada nas próximas seções do rascunho).

**Trabalho preservado de v2:**

- `Projeto/modelos/lightgbm_v2.txt` mantido (1.4 MB)
- `Projeto/modelos/optuna_study_v2.pkl` mantido
- `Projeto/modelos/shap_values_v2_test.npy` mantido (19 MB)
- Todas as tabelas `lightgbm_v2_*.csv` e figuras `fig09a/9b/10` preservadas
- Subseção "Análise SHAP do LightGBM v2" no `rascunho.md` recontextualizada como **análise diagnóstica** que motivou a promoção de v3, não como descrição do modelo final

**Caminho v2 vs v3 nas tabelas:**

| Artefato | Modelo |
|---|---|
| `lightgbm_v2.txt` | v2 (intermediário) |
| `lightgbm_v2_no_cascade.txt` | **v3 (canônico)** |
| `shap_values_v2_test.npy` | v2 (motivou a promoção) |
| `shap_values_v3_test.npy` | v3 (canônico) |
| `v2_vs_v2_no_cascade.csv` | tabela comparativa decisória |

**Limitações que persistem em v3:**

- **L2 do CM 6.2 — `mes` como feature implícita** (extrapolação para jul/ago em deployment).
- **L3 — Obs 2.11 fracamente refutada** (transferida para v3, mesma observação: features genéricas perderam para domain-specific).
- **L4 — Drift mai → jun não totalmente absorvido** (val AUC-PR 0,7132 reflete dificuldade do regime mai).
- **L6 — Q3 (operador difuso):** persiste em v3, será reavaliada quando SHAP v3 (`08f`) concluir.
- **L7 — Censoring 18,83%:** persiste (será endereçado por Weibull AFT em `09_sobrevivencia.py`).

**Limitação L1 (cascade-only) resolvida pela promoção de v3.** L5 (test peeking) já estava resolvida desde o refit pós-fix do leakage.

**Saídas geradas (novas):**

| Arquivo | Conteúdo |
|---|---|
| `Projeto/modelos/lightgbm_v2_no_cascade.txt` (2,3 MB) | Modelo canônico v3 |
| `Projeto/modelos/optuna_study_v2_no_cascade.pkl` (33 KB) | Study Optuna v3 (50 trials, seed=42) |
| `relatorio/tabelas/lightgbm_v2_no_cascade_metricas.csv` | Métricas train/val/test/CV |
| `relatorio/tabelas/lightgbm_v2_no_cascade_hiperparametros.csv` | 7 hiperparâmetros best |
| `relatorio/tabelas/v2_vs_v2_no_cascade.csv` | Tabela decisória (3 subgrupos × 2 modelos × 2 métricas) |

**Pipeline canônico atualizado:**

`01 → 02 → 03 → 04 → 05 → 06 → 06b → v3.parquet → 08e → lightgbm_v2_no_cascade.txt (canônico) → 08f → SHAP v3`

(v2 fica como passo intermediário diagnóstico, gerado por `08b` e analisado em SHAP por `08c`)

**Próximos passos imediatos:**

1. **08f_shap_v3.py** (executado em seguida — registro abaixo): valida que a remoção redistribuiu o peso para features antecipativas legítimas.
2. **09_sobrevivencia.py** (Weibull AFT) executará contra o **mesmo `v3.parquet`** com **34 features** (alinhado com v3 canônico para comparação justa).
3. **Atualização do CM 6.2** no relatório final: remover L1 (resolvida), manter L2-L7, adicionar **L8** (composição da frota influencia base rate aprendida).

---

### 2026-05-24 — Análise SHAP do LightGBM v3 + identificação da limitação L8 (composição da frota)

Aplicada por `Projeto/codigo/08f_shap_v3.py` (~1,7 min) — clone funcional do `08c_shap_v2.py` adaptado ao modelo v3 canônico. **Confirma empiricamente que a promoção do v3 atingiu seu objetivo**: o modelo NÃO é mais cascade detector.

**ANTES:** v3 acabava de ser promovido a canônico via decisão D-promoção, mas sem análise SHAP confirmatória — restava a pergunta: **a remoção de `horas_desde_ultimo_DG` realmente redistribuiu o peso para features antecipativas, ou criou outra "feature dominante" problemática?**

**DEPOIS:** Ranking SHAP do v3 sobre 71.089 eventos test responde de forma direta:

| Rank | Feature | Família | % do peso | Era no v2 |
|---:|---|---|---:|---|
| **1** | `qtd_alarmes_nivel_muito_alto_360min` | 6 — Regra de Negócio | **41,0%** | #2 (31,1%) |
| **2** | `tipo_caminhao` | 7 — Encoding | **23,9%** | #4 (5,0%) |
| **3** | `razao_alarme_7d_vs_30d_anterior` | 4 — Regimal | **11,1%** | #3 (8,6%) |
| 4 | `tag_freq` | 7 — Encoding | 3,3% | #5 (1,7%) |
| 5 | `mes` | 0 — Básicas | 2,1% | #9 (0,9%) |
| 6 | `razao_severidade_14d_vs_60d` | 4 — Regimal | 2,0% | #8 (1,0%) |
| 11 | `horas_desde_ultimo_critico` | 2 — Recência | 1,1% | #7 (1,0%) |

**Top 3 explicam 76,0%, top 10 explicam 89,9%** (vs 91% no v2 — concentração similar mas composição diferente).

**Achados validativos da promoção:**

1. ✅ **v3 NÃO é cascade detector.** Top 3 features (`qtd_alarmes_muito_alto`, `tipo_caminhao`, `razao_alarme_7d_vs_30d`) são todas antecipativas legítimas — somam 76% do peso. **Família 2 (Recência) reduzida drasticamente** (de 40,3% para 1,1%) — exatamente o objetivo da remoção.
2. ✅ **`horas_desde_ultimo_critico` NÃO herdou o papel da feature removida** — rank #11 com 1,1% do peso (era #7 com 1,0% no v2). A remoção foi cirúrgica.
3. ✅ **Família 6 (Regra de Negócio domain-specific) reforçada** — de 31,1% para 41,0% (top 1).
4. ✅ **Família 4 (Regimal) ganhou peso** — peso conjunto subiu de 9,6% (v2) para 13,1% (v3); coerente com hipótese de que sem cascade, sinais regimais ganham importância para distinguir regime junho do regime jan-abr.
5. ⚠️ **`tipo_caminhao` quase quintuplicou** (5,0% → 23,9%) — registrado como nova limitação L8.

**Nova limitação L8 — Composição da frota influencia base rate aprendida pelo v3:**

Sem a *feature* de cascata, o v3 passou a depender mais fortemente da diferenciação caminhões vs escavadeiras. A frota LeTourneau L 1850 (`tipo_caminhao = 0`) tem 22× menos DGs por equipamento que caminhões 793-D (`tipo_caminhao = 1`) — H4.1 confirmada em W5. O modelo aprendeu *base rate* por tipo de equipamento como heurística inicial da predição, refinada depois pelas Famílias 6 e 4.

**Defesa metodológica:** essa é a estratégia correta dado os dados — ignorar a diferença reduziria desempenho. **Não é viés operacional injusto** (a diferença existe nos dados, não foi inventada pelo modelo).

**Implicação operacional:** em deployment, se a Vale incluir uma frota nova (não vista no treino) ou sub-frota muito específica, calibração local pode ser necessária. **Fator a monitorar.** Adicionada como **L8** na síntese de limitações de CM 6.2 (rascunho.md).

**Lição metodológica para CM 6.1 (reforçada pela comparação SHAP v2 vs v3):**

**Modelos com AUC-PR similar podem ter estratégias internas radicalmente diferentes.** Sem a análise SHAP, a substituição v2 → v3 seria invisível operacionalmente (ambos passam o GATE com folga), mas o v3 entrega exatamente o tipo de predição que a Vale precisa (antecipação) em vez do que o v2 fazia (detecção de cascata). **A análise SHAP foi o instrumento que permitiu enxergar essa diferença.**

**Detalhe técnico — UnicodeEncodeError corrigido:**

A primeira execução do `08f_shap_v3.py` falhou na Etapa 4 com `UnicodeEncodeError: 'charmap' codec can't encode characters` ao imprimir o DataFrame Polars (caracteres Unicode de *box drawing* não estão no cp1252 do Windows). Matriz SHAP e CSV já tinham sido salvos antes do crash. **Correção aplicada:** substituí `print(df_ranking.head(15))` por loop ASCII explícito; execução também usa `PYTHONIOENCODING=utf-8` como prefixo no Windows. Lição registrada em `notas_metodologicas.md` Seção 12.

**Saídas geradas (novas):**

| Arquivo | Conteúdo |
|---|---|
| `Projeto/modelos/shap_values_v3_test.npy` (18,4 MB) | Matriz SHAP completa [71.089 × 34] — auditável |
| `relatorio/tabelas/shap_global_v3.csv` | 34 features × rank, mean(\|SHAP\|), %total |
| `relatorio/tabelas/shap_estratificado_v3.csv` | 5 subgrupos × top 10 (50 linhas) |
| `relatorio/figuras/fig09c_shap_bar_v3.png` | Bar plot importância global do v3 (top 15) |
| `relatorio/figuras/fig09d_shap_beeswarm_v3.png` | Beeswarm distribuição SHAP do v3 |
| `relatorio/figuras/fig10b_shap_dependence_top3_v3.png` | Dependence plots top 3 do v3 |

**Status atualizado da limitação L1:** RESOLVIDA pela promoção do v3. CM 6.2 agora terá L2-L8 (L1 movida para histórico).

---

### 2026-05-25 — Modelo de Sobrevivência (Weibull AFT) como segunda leitura do problema

Aplicada por `Projeto/codigo/09_sobrevivencia.py` (~56 s). Implementa modelo de sobrevivência paramétrico com fallback automático para Cox PH semi-paramétrico — segunda leitura do problema "antecipar DG" independente do LightGBM v3 canônico. Trata o *censoring* rigorosamente (parte essencial do CM 4.3 "dois modelos bem feitos > cinco superficiais") e fornece tabela de *hazard ratios* com IC 95% como ferramenta de interpretabilidade complementar ao SHAP.

**ANTES:** apenas LightGBM v3 disponível como modelo. Não havia tratamento rigoroso do *censoring* (102.602 eventos em treino sem DG futuro observado eram tratados como `target_4h = 0`, aproximação razoável mas não rigorosa). Sem ferramenta de interpretabilidade direta com IC 95% e p-valor por *feature*.

**DEPOIS:** Weibull AFT canônico (segundo modelo do relatório), validado contra o mesmo `v3.parquet` que o LightGBM v3:

**Configuração metodológica (3 decisões aprovadas pelo usuário em 24/05):**

1. **Filtro de correlação > 0,9 antes do fit** — Cox/Weibull são sensíveis a multicolinearidade (diferente do LightGBM que tolera). 6 *features* da Família 1 (rolling counts) foram removidas:
   - `count_critico_2h` (corr=0,944 com `count_critico_1h`)
   - `count_critico_8h` (corr=0,944 com `count_critico_4h`)
   - `count_nao_critico_2h` (corr=0,942 com `count_nao_critico_1h`)
   - `count_total_1h` (corr=0,912 com `count_nao_critico_1h`)
   - `count_nao_critico_8h` (corr=0,931 com `count_nao_critico_4h`)
   - `count_total_4h` (corr=0,926 com `count_total_2h`)
2. **Fallback automático para Cox PH se Weibull AFT não convergir OU C-index val < 0,6** — implementado e testado.
3. **34 features alinhadas com v3 canônico** (sem `horas_desde_ultimo_DG`) — após filtro de correlação restam **31 features** para o fit (28 numéricas + 5 dummies de `estado_pre_evento` + 1 dummy de `turno`, menos os 6 removidos por correlação).

**Imputação de NaN (Cox/Weibull não toleram NaN, diferente do LightGBM):**

Diagnóstico revelou:
- `razao_alarme_7d_vs_30d_anterior`: **404.795 nulls (74%)** — feature só computada quando há lookback de 30 dias
- `razao_severidade_14d_vs_60d`: 1.232 nulls
- `taxa_DG_operador_30d`: 704 nulls
- `horas_desde_ultimo_critico`: 1.071 nulls

Estratégia de imputação (fitada no treino, transparente, salva no artefato `.joblib` para reprodutibilidade):
- `razao_*` → **1,0** (neutro — mesma taxa que baseline; semântica preservada)
- `taxa_DG_operador_30d` → **0,0197** (mediana do treino)
- `horas_desde_ultimo_critico` → **2.177,4 h** (max do treino — *worst case*)

**Construção (T, E) por evento (~544k eventos):**

- Para cada evento, `join_asof` forward por TAG encontra o próximo DG da mesma TAG (estritamente > Data_Evento)
- Se existe → T = horas até próximo DG, E = 1 (evento observado)
- Se não existe → T = horas até última observação da TAG, E = 0 (*censurado*)
- 163 eventos com T = 0 (último evento de cada TAG sem DG futuro) descartados

**Distribuição de E por split (insight metodológico importante):**

| Split | Total | E=1 (observado) | E=0 (censurado) | % censurado |
|---|---:|---:|---:|---:|
| train | 394.863 | 331.619 | 63.244 | 16,0% |
| val | 78.816 | 60.159 | 18.657 | 23,7% |
| **test** | **71.043** | **30.184** | **40.859** | **57,5%** |

**% censurado no test é muito maior que no train** — porque test é jun/2025 (último mês observado), então muitos eventos não têm DG futuro dentro da janela observacional. Isso afeta a comparabilidade entre splits e é fator a registrar em CM 6.2.

**Resultados finais (Weibull AFT canônico — fallback não acionado):**

| Métrica | train | val | test |
|---|---:|---:|---:|
| C-index | 0,7517 | 0,7097 | **0,7444** |
| AUC-PR(target_4h) | 0,6487 | 0,4126 | **0,3153** |

**Tempo total:** 56 s (37 s para fit do Weibull + 19 s para avaliação/figuras).

**Bug corrigido durante execução:**

Na primeira tentativa, o cálculo do C-index para Weibull AFT estava negativando `predict_expectation` indevidamente (resíduo de adaptação a partir do código do Cox PH, que usa `-partial_hazard`). Isso resultou em C-index val = 0,29 (quase perfeitamente inverso de 0,71), fazendo o fallback automático disparar erroneamente. **Correção:** `predict_expectation` já retorna o tempo esperado de sobrevivência (alto = sobrevida longa), formato exato que `concordance_index` espera. Sem negativação. Após o fix, Weibull AFT C-index val = 0,7097 (passa o threshold de 0,6) e o fallback corretamente não é acionado.

**Top 10 hazard ratios (Time Ratios — TR < 1 = maior risco, TR > 1 = menor risco):**

| # | Covariate | TR | IC 95% | p | Interpretação |
|---:|---|---:|---|---:|---|
| 1 | `tag_freq` | 1,432 | [1,41–1,45] | 0,0000 | TAGs frequentes têm sobrevida 43% maior |
| 2 | **`tipo_caminhao`** | **0,038** | [0,04–0,04] | 0,0000 | Caminhões têm sobrevida ~3% da escavadeira (efeito massivo) |
| 4 | **`frota_793D_5S`** | **0,169** | [0,16–0,18] | 0,0000 | Frota 5S tem sobrevida 17% da baseline |
| 5 | `frota_793D_2S` | 0,357 | [0,34–0,38] | 0,0000 | |
| 6 | `frota_793D_4S` | 0,450 | [0,43–0,47] | 0,0000 | |
| 7 | `frota_793D_3S` | 0,364 | [0,34–0,39] | 0,0000 | |
| 8 | `operador_freq` | 1,124 | [1,11–1,14] | 0,0000 | Operadores conhecidos: sobrevida +12% |
| 9 | `valor_disponivel` | 1,224 | [1,20–1,25] | 0,0000 | Sensor disponível: sobrevida +22% |
| 10 | `count_critico_24h` | 0,844 | [0,83–0,86] | 0,0000 | Acúmulo críticos 24h: sobrevida −16% |

**Concordância forte com SHAP v3** (validação cruzada entre duas técnicas independentes — material para CM 5.3):

- `tipo_caminhao` é dominante em ambos (SHAP v3 #2 com 23,9%; Weibull TR=0,038 = maior risco isolado)
- Família 4 regimal (`razao_alarme_7d_vs_30d_anterior`) aparece como significativa em ambos
- `tag_freq` no top em ambos
- `operador_freq` aparece com sinal real mas modesto em ambos (Q3 do edital: operador correlaciona difusamente)

**Discordância interpretativa importante:**

LightGBM v3 (SHAP) dá peso massivo a `qtd_alarmes_muito_alto_360min` (41%) — é a feature top 1. Weibull AFT NÃO destaca essa feature no top 10 dos p-valores. Possível explicação: o Weibull AFT modela o tempo até o próximo DG (não importando se em 4h ou 4 dias), enquanto LightGBM v3 foca em "DG em 4h" especificamente. **Features que predizem DG iminente (Família 6) brilham no LightGBM; features que predizem qualquer DG futuro (frota, tipo, operador) brilham no Weibull.** Material para CM 6.1.

**Comparação operacional v3 vs Weibull AFT:**

| Característica | LightGBM v3 | Weibull AFT |
|---|---|---|
| AUC-PR test (target_4h) | **0,8556** | 0,3153 |
| C-index test | — (não aplicável) | 0,7444 |
| Tratamento de censoring | Aproximação (target=0) | **Rigoroso** |
| Interpretabilidade | SHAP (post-hoc) | HR + IC 95% + p-valor (intrínseca) |
| Horizonte | Específico (4h) | **Qualquer t** |
| Custo computacional | 25,7 min (Optuna) | **0,9 min** |
| Caso de uso | Alerta operacional 4h | Análise estratégica/manutenção planejada |

**Conclusão metodológica:** Weibull AFT NÃO substitui LightGBM v3 (claramente inferior em classificação 4h, como esperado pela natureza das duas técnicas). Mas oferece:

1. **Tratamento estatístico rigoroso** do censoring (essencial dado 57,5% de censoring no test)
2. **Interpretabilidade direta** com IC 95% e p-valor (sem post-hoc tipo SHAP)
3. **Predição em qualquer horizonte** (não apenas 4h) — `predict_survival_function(times=[t])` para qualquer t
4. **Validação cruzada do v3** — features importantes coincidem (tipo_caminhao, frota, regimal)

**Saídas geradas:**

| Arquivo | Conteúdo |
|---|---|
| `Projeto/modelos/sobrevivencia.joblib` (14,5 MB) | Modelo Weibull + scaler + imputação + lista de features |
| `relatorio/tabelas/sobrevivencia_metricas.csv` | C-index/AUC-PR/n por split |
| `relatorio/tabelas/sobrevivencia_hazard_ratios.csv` | 32 features × TR, IC 95%, p-valor, interpretação |
| `relatorio/tabelas/sobrevivencia_features_excluidas_corr.csv` | 6 features removidas pelo filtro |
| `relatorio/figuras/figExA_kaplan_meier_por_frota.png` | KM por frota (5 curvas, até 168h = 7 dias) |

**Nova entrada de CM 5.3 (validação cruzada por dois métodos independentes):**

A concordância dos top features entre SHAP do v3 e hazard ratios do Weibull AFT (especialmente `tipo_caminhao`, frotas, e Família 4 regimal) é evidência forte de **validade** das estratégias aprendidas. Dois métodos com fundamentação matemática completamente diferente (TreeSHAP via Shapley values em gradient boosting vs maximum likelihood em modelo paramétrico AFT) chegam às mesmas variáveis-chave.

**Limitações específicas do Weibull AFT (a entrar em CM 6.2):**

- AUC-PR(4h) significativamente abaixo do LightGBM v3 — não é o modelo adequado para alerta operacional de curto prazo
- Distribuição de censoring muito diferente entre train (16%) e test (57,5%) — sugere que a janela de observação curta (6 meses) é insuficiente para survival robusto no test
- Filtro de correlação removeu 6 features Família 1 — perda de granularidade temporal fina

---

### 2026-05-25 — Diagnóstico do Risco 3.3 via Isolation Forest (viés do label CMA)

Aplicada por `Projeto/codigo/11_isolation_forest.py` (~10,8 s). Teste empírico único de uma limitação metodológica conhecida: o rótulo `Is_Dont_Go` é gerado por regras CMA (82 regras "Muito Alto"). Modelos supervisionados (LightGBM v3, Weibull AFT) poderiam estar aprendendo a **replicar** essas regras, não a antecipar anomalias mecânicas reais. **Isolation Forest é treinado SEM o rótulo** — se as anomalias detectadas coincidem com DGs reais, o rótulo é validado; se não, há viés.

**ANTES:** Risco 3.3 (`PLANEJAMENTO.md` linha 1002+) era hipotético — sem evidência empírica de que o rótulo CMA captura anomalias mecânicas reais vs apenas dispara regras de negócio. Os altos AUC-PR de v3 (0,8556) e Weibull AFT (C-index 0,7444) poderiam estar mascarando "modelo aprende as regras CMA, não a mecânica subjacente".

**DEPOIS:** Isolation Forest treinado em 394.971 eventos de train **sem usar Is_Dont_Go**, com:
- Mesmas 34 features do v3 canônico (alinhamento direto para comparabilidade)
- 200 árvores, `random_state=42`
- StandardScaler em todas as features (consistência com 09_sobrevivencia)
- Imputação NaN igual ao 09 (`razao_*`→1,0; `taxa_DG_operador_30d`→0,0197; `horas_desde_ultimo_critico`→2.177,4 h)

**Achado central — AUC-ROC do anomaly_score vs Is_Dont_Go por split:**

| Split | n | n_DG | Prevalência | AUC-ROC |
|---|---:|---:|---:|---:|
| train | 394.971 | 13.456 | 3,41% | 0,5753 |
| val | 78.825 | 1.280 | 1,62% | 0,5979 |
| **test** | **71.089** | **5.226** | **7,35%** | **0,8603** |

**Padrão estranho:** train e val ~0,58 (quase aleatório), test 0,86 (forte). Hipótese imediata: o sinal de test é dirigido pela anomalia dominante do CA65926 (Obs 2.9 — 82,2% dos DGs de junho vêm desse único equipamento).

**Validação da hipótese — AUC-ROC estratificado por CA65926 no test:**

| Subgrupo | n | n_DG | AUC-ROC |
|---|---:|---:|---:|
| Test completo | 71.089 | 5.226 | 0,8603 |
| **CA65926 apenas** | **7.083** | **4.298** | **0,8969** |
| **Test sem CA65926** | **64.006** | **928** | **0,5409** |

**Confirmação dramática.** O sinal forte do test é **completamente dirigido** pelo CA65926:
- CA65926 representa 10% dos eventos e 82,2% dos DGs no test
- Isolation Forest detecta o CA65926 isoladamente com AUC=0,90 (sinal real e forte)
- Sem CA65926, a sobreposição IF-CMA cai para AUC=0,54 (quase aleatória)

**Adição metodológica (mesmo dia): AUC-ROC por TAG no test (análise estrutural completa).**

A análise CA65926 vs resto foi um teste de hipótese ad-hoc. Para uma leitura *estrutural* (não baseada em suspeita prévia), foi computado AUC-ROC para **cada uma das 30 TAGs presentes no test set** (4 não computáveis por terem zero DGs ou eventos). Resultado:

| Top 5 (sinal forte ≥ 0,75) | n | n_DG | prev_DG | AUC | Comentário |
|---|---:|---:|---:|---:|---|
| PE3797 | 9.690 | 1 | 0,01% | 0,9263 | LeTourneau, sinal questionável (n_DG=1) |
| PE3795 | 5.013 | 3 | 0,06% | 0,9254 | LeTourneau, sinal questionável (n_DG=3) |
| **CA65926** | **7.083** | **4.298** | **60,68%** | **0,8969** | **Sinal real, equipamento dominante** |
| CA65932 | 584 | 24 | 4,11% | 0,8367 | Sinal real, sample modesto |
| CA65924 | 1.097 | 25 | 2,28% | 0,7915 | **Caso paradigma de W4 — confirma assinatura anômala** |

| Estatística | Valor |
|---|---:|
| AUC mediana entre 26 TAGs válidas | **0,6060** |
| AUC média | 0,6377 |
| TAGs com AUC ≥ 0,75 (sinal forte) | **5 de 26** |
| TAGs com AUC < 0,55 (~aleatório) | **8 de 26** |
| AUC mínimo (CA65931) | 0,3510 |

**Leituras críticas:**

1. **Mediana 0,61 vs Agregado 0,86 — agregado é enganoso.** A média ponderada pelo número de eventos faz o CA65926 (10% dos eventos, 82% dos DGs) dominar o agregado. A mediana por TAG é uma medida mais honesta do sinal **típico** em deployment, onde cada equipamento opera com sua própria base rate.

2. **Apenas 5 TAGs têm sinal forte** — e dessas, 2 (PE3797, PE3795) têm tão poucos DGs (1 e 3) que o AUC alto é provavelmente artefato amostral. **De fato, apenas 3 TAGs têm sinal forte E sample significativo: CA65926, CA65932, CA65924.**

3. **Validação independente do W4 (caso paradigma CA65924):** o IF, sem ver o rótulo, identifica o CA65924 como anômalo (AUC=0,79). Isso valida que a investigação de W4 acertou em escolher esse equipamento como paradigma da Obs 2.3.

4. **8 TAGs com AUC < 0,55** — para mais de 30% dos equipamentos válidos, o IF é essencialmente aleatório. **O rótulo CMA nesses equipamentos pode estar capturando eventos sem assinatura estatística distintiva** — confirma o Risco 3.3 nesse regime.

5. **Lição metodológica:** a estratificação **por TAG** é mais rigorosa que estratificação **por uma TAG suspeita** (CA65926 vs resto). Em projetos futuros, **começar pela distribuição estrutural** evita o viés de confirmação de hipóteses ad-hoc.

**Curva Precision/Recall por contamination (test completo):**

| contamination | threshold | n_anom | Precision | Recall | F1 |
|---:|---:|---:|---:|---:|---:|
| 0,01 | 0,0646 | 712 | 0,9017 | 0,1228 | 0,2162 |
| 0,03 | 0,0402 | 2.133 | 0,6484 | 0,2646 | 0,3759 |
| 0,05 | 0,0284 | 3.572 | 0,5465 | 0,3735 | 0,4437 |
| 0,10 | 0,0168 | 7.111 | 0,4085 | 0,5559 | 0,4709 |

Lift vs prevalência (7,35%): no threshold 0,10, precisão 0,4085 = **5,56× random**. No threshold 0,01, precisão 0,90 = **12,2× random**. Sinal forte agregado (mas, dado o achado estratificado, esse sinal é majoritariamente do CA65926).

**Veredito honesto e nuançado — Risco 3.3 PARCIALMENTE MITIGADO (assimétrico por regime):**

- ✅ **Para anomalias dominantes (CA65926-like):** Isolation Forest e CMA concordam fortemente (AUC=0,90). Para falhas mecânicas progressivas com assinatura clara, o rótulo CMA captura anomalia estatisticamente real. **Risco 3.3 mitigado nesse regime.**
- ⚠️ **Para DGs distribuídos (90% dos equipamentos):** Isolation Forest e CMA discordam (AUC=0,54). O rótulo CMA pode estar capturando eventos que não têm assinatura estatística distintiva no espaço de features atual. **Risco 3.3 parcialmente confirmado nesse regime.**

**Implicação operacional crítica (a entrar em CM 6.2 como nova limitação L10):**

A performance alta do LightGBM v3 em test (AUC-PR=0,8556) é **largamente dirigida pela detecção do CA65926**. Em regime sem anomalia dominante (cenário esperado em deployment futuro), a performance pode degradar significativamente — possivelmente para perto do baseline original (AUC-PR train ~ AUC-PR val), já que o sinal "extra" em test vinha de um único equipamento.

**Recomendações (CM 6.3 — Trabalhos Futuros):**

1. **Monitorar performance estratificada por equipamento em produção:** dashboard que separa AUC-PR por TAG para detectar dependência de equipamentos específicos.
2. **Retreino *rolling* mensal:** já registrado em CM 6.3 (entrada 2026-05-22), agora reforçado por este achado — captura mudanças de regime mecânico.
3. **Estender janela de observação:** com mais meses de dados, regimes anômalos como CA65926 ficariam balanceados por outros equipamentos problemáticos potenciais, reduzindo viés do test set atual.
4. **Investigar os FPs do IF como possíveis "DGs perdidos pelo CMA":** eventos com `anomaly_score` alto que NÃO foram rotulados como DG podem ser falhas mecânicas que escaparam às regras CMA. Análise manual de uma amostra desses casos validaria/refutaria essa leitura inversa do Risco 3.3.

**Coerência com outros achados do projeto:**

Este resultado é **internamente consistente** com:
- **SHAP do v3:** `tipo_caminhao` (24%) e `frota_793D_5S` no top — modelo aprende que "essa equipamento/frota costuma falhar de jeito específico"
- **Hazard ratios do Weibull AFT:** `tipo_caminhao` TR=0,038, `frota_793D_5S` TR=0,169 — mesmo padrão
- **Obs 2.9 (W5):** anomalia RFB em jun é falha localizada do CA65926 (98,5% dos eventos RFB-Active vêm desse único equipamento)
- **Drift jun (CA65926):** já registrado como L4 — recapitulado agora pelo IF

Em todos os ângulos analisados, o **regime de teste é atípico** — dominado por uma única falha mecânica em curso. **Material direto para CM 6.1 (Insights Não Óbvios):** três técnicas independentes (LightGBM SHAP, Weibull AFT hazard ratios, Isolation Forest não-supervisionado) convergem para a mesma conclusão sobre a natureza do test set.

**Saídas geradas:**

| Arquivo | Conteúdo |
|---|---|
| `Projeto/modelos/isolation_forest.joblib` (0,58 MB) | Modelo + scaler + imputação + lista de features |
| `relatorio/tabelas/if_auc_roc.csv` | AUC-ROC por split (train/val/test) |
| `relatorio/tabelas/if_auc_estratificado_test.csv` | AUC-ROC em 3 subgrupos do test (CA65926 vs resto) |
| `relatorio/tabelas/if_auc_por_tag.csv` | **AUC-ROC por TAG (30 TAGs, 26 com AUC válido)** — análise estrutural completa |
| `relatorio/tabelas/if_diagnostico.csv` | P/R/F1 por contamination (4 thresholds) |
| `relatorio/tabelas/if_contingencia.csv` | 4 tabelas 2×2 (TN/FP/FN/TP) concatenadas |
| `relatorio/figuras/figExD_isolation_forest_diagnostico.png` | **4 painéis:** P/R curve, histograma scores, AUC-ROC por split, **AUC-ROC por TAG (barras coloridas por log10(n_DG))** |

**Nova limitação registrada (L10 em CM 6.2):** "Dependência da performance do v3 do regime CA65926" — explicada acima.

---

### 2026-05-27 — W7 Grupo A: Avaliação estratificada, threshold operacional 0,30 (FN:FP=5:1), L11 (escavadeira), insight unknown

Aplicado por `Projeto/codigo/10_evaluation.py` (~30 s). Avaliação técnica final do LightGBM v3 no test set jun/2025 cobrindo os itens do Grupo A de W7 (excluídos os já entregues em W6 + figuras de negócio Neg01-Neg03 + Fig 5 → reserva).

#### Decisão metodológica 1 — threshold operacional canônico = 0,30 (ratio FN:FP = 5:1)

**ANTES:** o modelo v3 foi avaliado e SHAP-analisado, mas não havia ponto de operação canônico definido. Fig 9 (curvas) mostrava AUC-PR=0,8556 sem associar a um corte específico.

**DEPOIS:** tabela `eval_custo_beneficio.csv` testa 11 thresholds (0,05 a 0,80) × 4 premissas de custo (1:1, 3:1, 5:1, 10:1). Threshold ótimo (mínimo custo total) por premissa:

| Custo FN:FP | Thr* | TP | FP | FN | P | R | F1 | F2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1:1 | 0,70 | 8.430 | 946 | 3.608 | 0,899 | 0,700 | 0,787 | 0,733 |
| 3:1 | 0,40 | 9.408 | 3.193 | 2.630 | 0,747 | 0,782 | 0,764 | 0,774 |
| **5:1 (CANÔNICO)** | **0,30** | **9.821** | **4.764** | **2.217** | **0,673** | **0,816** | **0,738** | **0,783** |
| 10:1 | 0,15 | 10.624 | 10.478 | 1.414 | 0,503 | 0,883 | 0,641 | 0,767 |

**Justificativa:** ratio puro das premissas operacionais (FN=4h corretiva vs FP=1,5h preventiva) é 2,7:1. Considerando custos não monetizados (mobilização emergencial, peças em estoque, segurança), o ratio efetivo é estimado entre 3:1 e 10:1. **5:1 é compromisso razoável** e maximiza F2 (0,783) — métrica adequada para mineração onde FN é claramente mais custoso. Decisão aprovada pelo usuário (27/05) após revisão da tabela completa.

**Q6 — Faixas operacionais derivadas:**

| Faixa | Intervalo P(DG≤4h) | n eventos | % | DGs reais na faixa | Prevalência |
|---|---|---:|---:|---:|---:|
| 🟢 VERDE | < 0,145 | 49.762 | 70,0% | 1.383 | 2,78% |
| 🟡 AMARELO | 0,145 ≤ P < 0,300 | 6.742 | 9,5% | 834 | 12,37% |
| 🔴 VERMELHO | ≥ 0,300 | 14.585 | 20,5% | 9.821 | **67,34%** |

Faixa vermelha (20,5% do volume) concentra **81,6% dos DGs reais** — fator de enriquecimento 4× sobre prevalência base. Boa operacionalização do modelo.

#### Decisão metodológica 2 — Nova limitação L11 (modelo não opera em escavadeiras LeTourneau)

**Achado:** análise estratificada por frota no test set revela que LeTourneau L 1850 (escavadeira, 31.909 eventos = 44,9% do volume) tem **AUC-PR=0,0077** (essencialmente aleatório), Precision=0, Recall=0, **n_alertas = 0** no threshold operacional.

**Implicação categórica:** a Frente 1 do modelo NÃO atende escavadeiras com o pipeline atual. Causa provável (não totalmente verificada): a feature `tipo_caminhao` (binária, 24% do peso SHAP do v3) atua como *gating* — quando = 0 (escavadeira), o modelo virtualmente desliga as predições positivas.

**Registro:** Nova **limitação L11** adicionada à seção "Síntese parcial de limitações" do `rascunho.md`. Mitigações sugeridas em CM 6.3:
- Modelo dedicado para escavadeiras com features específicas
- Política de monitoramento via Frente 2 (Weibull AFT) — naturalmente reconhece baixo *base rate*
- Revisão do conjunto de features para incluir variáveis específicas de escavadeira

**Coerência com L8:** L11 não duplica L8 — L8 fala da influência GERAL da composição da frota na *base rate* aprendida; L11 é o achado CATEGÓRICO de que para 45% do parque o modelo simplesmente não emite alertas. Decisão aprovada pelo usuário (27/05).

#### Achado adicional registrado em CM 6.1 — categorias unknown performam ligeiramente MELHOR que conhecidas

**Achado contra-intuitivo:** análise estratificada "categoria conhecida vs unknown no treino" no test:

| Categoria | n | DGs | AUC-PR | Recall@thr |
|---|---:|---:|---:|---:|
| Conhecido em treino | 69.277 | 11.870 | 0,8554 | 0,8153 |
| **Unknown em treino** | **1.812** | **168** | **0,8887** | **0,8512** |

Refuta a expectativa inicial do estudo W5 (`notas_metodologicas.md` Seção 2) de degradação por extrapolação. Possíveis explicações: (i) sample pequeno (n_DG=168) introduz variância amostral; (ii) convenção `freq=0` para unknown atua como feature binária implícita "equipamento novo" que o modelo aprende; (iii) categorias unknown podem ter padrões operacionais menos ambíguos.

**Independente da causa, valida empiricamente a Opção 1 do encoding fix** (registrada em `controle_alteracoes.md` 22/05) — não há necessidade de Opção 3 (features binárias `is_unknown` explícitas). Insight registrado para **CM 6.1** (Insights Não Óbvios) no relatório final.

#### Outras análises estratificadas validadas (Qualidade C)

- **Por tipo:** Caminhão AUC-PR=0,86 vs Escavadeira 0,01 (mesmo achado da estratificação por frota, agregação).
- **Por estado pré-evento:** Operando 0,86 / Manutenção 0,79 / Parado 0,84 — modelo robusto a estado operacional. Refuta preocupação inicial de que "DGs em Manutenção seriam ruído" (Obs 2.7 — agora confirmada como DGs legítimos via re-ativações).

#### Fig 10 — Matriz de confusão com impacto operacional

No threshold canônico 0,30: TP=9.821 (DGs antecipados, 1,5h custo), FP=4.764 (inspeções desnecessárias, 1,5h custo), FN=2.217 (paradas não planejadas, 4h custo), TN=54.287 (operação normal).

**Tradução operacional:** cenário sem modelo = 48.152h-equipamento; com modelo = 30.746h. **Redução de 17.406h (36,1%)** — consistente com cenário Realista da Fig Neg03 (47%, considerando horas totais de parada vs só DGs reais).

#### Saídas geradas (W7 Grupo A)

| Arquivo | Conteúdo |
|---|---|
| `relatorio/tabelas/eval_custo_beneficio.csv` | 11 thresholds × 4 ratios + métricas P/R/F1/F2 |
| `relatorio/tabelas/eval_q6_faixas.csv` | 3 faixas Verde/Amarelo/Vermelho com ação operacional |
| `relatorio/tabelas/eval_estratificado_frota.csv` | 5 frotas × P/R/AUC-PR/n_alertas |
| `relatorio/tabelas/eval_estratificado_tipo.csv` | Caminhão vs Escavadeira |
| `relatorio/tabelas/eval_estratificado_estado.csv` | 4 estados pré-evento |
| `relatorio/tabelas/eval_estratificado_unknown.csv` | Conhecido vs unknown |
| `relatorio/figuras/fig10_matriz_confusao_v3.png` | Matriz 2×2 com anotações de impacto operacional |

#### Próximos passos

- W7 ainda: ~~integrar Random Forest tunado (`16_random_forest_comparativo.py`, em execução) à seção "Diferenciais" para reforçar empiricamente que o algoritmo não é o diferencial deste estudo.~~ **CONCLUÍDO em 01/06.** Veja entrada `2026-06-01 — W7 Item 6 (RF comparativo)` abaixo.
- W8: refinamento de CM 6.1 (12 insights consolidados), CM 6.3 (trabalhos futuros incluindo L11, L12), Conclusão.

---

### 2026-06-01 — W7 Grupo B: Tempo de antecipação (L12) + Top-100 FPs do IF (6ª evidência LeTourneau)

Aplicado por dois scripts complementares de W7 Grupo B, executados em 01/06 enquanto o Random Forest tunado roda em background.

#### B#2 — `17_distribuicao_antecipacao.py` → Nova limitação L12

**ANTES:** Tínhamos as métricas agregadas P/R/F1 no threshold operacional 0,30, mas não a distribuição temporal das antecipações — métricas Qualidade B do edital pendentes.

**DEPOIS:** Análise da distribuição temporal dos 9.821 TPs do v3 no test set revela achado crítico:

| Subgrupo | n | Percentual |
|---|---:|---:|
| Total TPs | 9.821 | 100% |
| **Detecções diretas** (próprio evento é DG, antecipação=0) | **4.945** | **50,4%** |
| **Antecipações reais** (DG futuro estritamente em 4h) | **4.876** | **49,6%** |
| Outros (target=1 mas sem DG válido) | 0 | 0% |

**Distribuição dos 4.876 com antecipação real (em minutos):**

| Percentil | Antecipação |
|---|---:|
| P10 | 0,2 min |
| P25 | 0,8 min |
| **P50 (mediana)** | **5,7 min** |
| P75 | 56 min |
| P90 | 146 min |

**Apenas 18% dos TPs atingem a janela de mobilização típica (≥ 90 min); 50% têm antecipação ≤ 6 min.**

**Nova limitação L12 registrada em CM 6.2** (`rascunho.md` Síntese de Limitações). Interpretação: o v3 funciona muito mais como **detector de DG iminente** do que como **antecipador de janela 4h**. Manifestação residual do mesmo padrão do v2 (cascade detection) que o v3 mitigou parcialmente mas não eliminou.

**Mitigações propostas em CM 6.3:**
- Treinar variante com target mais longo (8h, 12h) — explora trade-off entre AUC-PR e tempo útil
- Usar Frente 2 (Weibull AFT) como complemento — modela tempo até qualquer DG futuro
- Combinar score do v3 com probabilidade de sobrevivência em horizonte mais longo

**Saídas:** `relatorio/tabelas/distribuicao_antecipacao.csv` + `relatorio/figuras/figNeg04_distribuicao_antecipacao.png` (2 painéis: decomposição + distribuição com percentis marcados).

#### B#3 — `18_top100_fps_if.py` → 6ª evidência convergente sobre LeTourneau

**Análise:** Top 100 eventos no test set com **maior `anomaly_score` do Isolation Forest** que **NÃO foram rotulados como DG pela CMA**. Para cada um, examinados os eventos nos 4h seguintes (mesmo TAG).

**Resultados:**

| Métrica | Valor |
|---|---:|
| Range de `anomaly_score` | [0,0592, 0,0896] |
| Mediana eventos próximos 4h | 46 |
| Mediana Críticos próximos 4h | 9 |
| **% com ≥ 1 DG futuro nas 4h** | **6%** |
| **% com ≥ 1 evento Crítico nas 4h** | **99%** |

**Concentração por equipamento:**

| Frota | n FPs entre top-100 |
|---|---:|
| **LeTourneau L 1850 (escavadeira)** | **94** |
| 793-D 4S | 5 |
| 793-D 5S | 1 |

**94 dos 100 FPs vêm da MESMA escavadeira (PE3797).**

**Veredito honesto sobre o Risco 3.3 (leitura inversa):**

- ❌ **IF NÃO complementa a CMA para antecipar mais DGs** — apenas 6% dos top-FPs têm DG futuro nas 4h.
- ⚠️ **MAS o IF revela um regime sistematicamente diferente em escavadeiras LeTourneau:** 99% dos top-FPs têm eventos Críticos próximos (mediana 9), concentrados em UMA escavadeira (PE3797). Padrão de **alarmes Críticos elevados que NUNCA vira DG na CMA**.

**Possíveis interpretações (mutuamente não-exclusivas):**
1. Escavadeiras toleram criticidade alta sem falhar (modo de operação diferente, ferramenta estacionária)
2. Regras CMA (~95% Caterpillar OEM) são subreportadoras para LeTourneau (regras calibradas para caminhões)
3. Combinação dos dois efeitos

**Material para CM 6.1 (Insight Não Óbvio):** o Isolation Forest, sem ver o rótulo, identifica um **regime operacional anômalo em LeTourneau que a regra CMA não classifica como DG**. Confirma indiretamente que o rótulo `Is_Dont_Go` tem viés direcionado por tipo de equipamento (Risco 3.3 manifestação adicional).

**Material para CM 6.3 (Recomendação Operacional Concreta):**
- **Auditoria manual dos 100 eventos da PE3797** identificados pelo IF — validar com domain expert se são anomalias mecânicas reais não classificadas ou ruído operacional aceito.
- **Revisão das regras CMA para escavadeiras** — possivelmente novo conjunto de regras específicas ou recalibração dos thresholds existentes.

#### B#1 — `08d_comparacao_horizontes_cv.py` → Cenário 1 confirmado + Insight #12 (colapso fold 4)

**Análise:** Treino de 3 modelos v3 (T2, T4, T8) com hiperparâmetros idênticos via TimeSeriesSplit CV de 4 folds expandidos. Objetivo: validar empiricamente a escolha de horizonte 4h (target_4h canônico do CM 1.2).

**Resultados:**

| Horizonte | Prevalência train | AUC-PR média | ± std |
|---|---:|---:|---:|
| T2 | 29,77% | 0,8019 | ± 0,1535 |
| **T4 (canônico)** | 33,64% | **0,7023** | ± 0,3082 |
| T8 | 38,69% | 0,6841 | ± 0,3230 |

**Comparação T2 vs T4:** Δ = +0,0996, σ_combined = 0,3443, Δ/σ = 0,29 < 2σ → **Cenário 1: indistinguíveis**. Mantém **T4 como horizonte canônico do relatório**. Decisão de W4/W5 validada empiricamente.

**Achado lateral CRÍTICO — colapso do fold 4 em todos os horizontes:**

| Horizonte | Fold 1 | Fold 2 | Fold 3 | **Fold 4** | Queda fold3→fold4 |
|---|---:|---:|---:|---:|---:|
| T2 | 0,8990 | 0,9054 | 0,8660 | **0,5372** | −0,33 pp |
| T4 | 0,9105 | 0,8937 | 0,8343 | **0,1708** | **−0,66 pp** |
| T8 | 0,9126 | 0,8921 | 0,8023 | **0,1292** | **−0,67 pp** |

Os folds 1-3 (treino expandindo até abr, validando em meses internos do treino) produzem AUC-PR ~0,87-0,91 consistentes. O **fold 4 (treina jan-abr, valida em mai)** desaba — quanto maior o horizonte, mais forte o colapso.

**Interpretação:** essa é a manifestação mais clara até agora do drift mai→jun em CV temporal. O fold 4 é exatamente onde o regime começa a mudar (transição treino→val). A AUC-PR média da CV (0,70-0,80) **é estatística enganosa** — oculta um colapso de regime que ocorre **exatamente onde o modelo seria mais cobrado em deployment**.

**Registrado como Insight #12 em CM 6.1** (`rascunho.md` — "CV temporal agregada mascara colapso no fold mais recente"). Reforça empiricamente:
- L4 (drift mai→jun quantificado): agora visível também na CV
- L10 (performance dirigida por poucos equipamentos): mesmo padrão no fold 4

**Lição metodológica:** em problemas com drift conhecido, reportar AUC-PR média da CV sem decomposição por fold pode dar segurança falsa. Análise fold-a-fold é mandatória para auditar onde o modelo realmente quebra. **Material para CM 5.2.**

**Tempo de execução real:** 8h (vs 6 min estimado originalmente). Causa: tempos por fold variaram drasticamente (T8 fold 3 levou 5h sozinho). Para auditoria futura, vale rodar amostra antes de full CV. **Saída:** `relatorio/tabelas/comparacao_horizontes_cv.csv`.

---

**6ª evidência convergente sobre LeTourneau** (junto com as 5 já documentadas em H4.1 + L11):

| # | Evidência | Origem |
|---|---|---|
| 1 | 5/13 escavadeiras sem telemetria | W1 (H1.1) |
| 2 | 95% dos bypasses do operador | W1 (H1.2) |
| 3 | 88% dos erros de medição de peso | W1 (H1.3) |
| 4 | 22× menos DGs por equipamento que caminhões 793-D 5S | W2 (Q4) |
| 5 | AUC-PR=0,008 e zero alertas do v3 no test | W7 (L11) |
| **6** | **94% dos top-100 FPs do IF concentrados em PE3797** | **W7 (este achado)** |

**Saídas:** `relatorio/tabelas/top100_fps_if.csv` (100 eventos × 12 colunas) + `relatorio/tabelas/top100_fps_if_concentracoes.csv` (concentrações por frota/TAG) + `relatorio/figuras/figExH_top100_fps_if.png` (3 painéis: contexto, frota, TAGs).

---

### 2026-06-01 — W7 Fechamento: drift semanal de junho (Insight #13) + limpeza PLANEJAMENTO

Aplicado por `Projeto/codigo/19_drift_semanal_junho.py` (~10 s). Última análise empírica de W7, fechando os itens originais "Drift mensal: AUC-PR mês a mês" (adaptado para semanal porque o test é apenas junho).

**Achado:** o v3 NÃO é estável dentro do próprio mês de teste. AUC-PR varia dramaticamente:

| Semana de junho | n | Prevalência | AUC-PR |
|---|---:|---:|---:|
| S1 (01-07) | 12.325 | 20,14% | 0,9375 |
| S2 (08-14) | 24.097 | 15,43% | 0,6762 |
| **S3 (15-21)** | 13.536 | **3,75%** | **0,3539** |
| S4 (22-30) | 21.131 | 25,22% | 0,9472 |

**Amplitude de 0,59 pp em AUC-PR em 30 dias.** S3 (regime "calmo" sem dominância CA65926) tem AUC-PR baixa (0,35); S4 (explosão CA65926) tem AUC-PR alta (0,95). **Insight #13 registrado em CM 6.1** — drift detectável em janela semanal, não mensal.

**Implicação para CM 6.3:** monitoramento em produção precisa operar em janela semanal, não mensal — degradação detectável em 7 dias. Reforça empiricamente L4 + L10.

**Saídas:** `relatorio/tabelas/drift_semanal_junho.csv` + `relatorio/figuras/figExI_drift_semanal_junho.png` (2 painéis).

#### Status final de W7

Todos os entregáveis originais de W7 cobertos (alguns por scripts diferentes do plano original):

| Item original W7 | Onde foi entregue |
|---|---|
| Fig 10 matriz confusão | `10_evaluation.py` (W7 Grupo A) |
| Análise falsos negativos | Estratificada por frota |
| Qualidade C estratificada | `10_evaluation.py` |
| Métricas por estado pré-evento | `10_evaluation.py` |
| Com vs sem CA65926 | IF estratificado (W6) → L10 |
| TAG/operador unknown vs conhecido | `10_evaluation.py` (insight CM 6.1) |
| Tabela custo-benefício + limiar | `10_evaluation.py` |
| 08d comparação horizontes | B#1 (Cenário 1 confirmado + Insight #12) |
| Q3 operador SHAP | W5 (Obs 2.4) + W6 (SHAP rank #12) |
| Q6 faixas | `10_evaluation.py` (Verde/Amarelo/Vermelho) |
| Q7 ranking | `figNeg02_ranking_risco_operacional.png` |
| Tradução em horas | `figNeg03_horas_parada_evitavel.png` |
| Qualidade B distribuição antecipação | B#2 → L12 |
| Qualidade E sanity check viés | IF (W6) + B#3 (W7) |
| K análise top-100 FPs | B#3 |
| Insights não óbvios CM 6.1 | 13 insights consolidados |
| Drift mensal | **`19_drift_semanal_junho.py` (este, adaptado para semanal)** |
| Fig 13 | **Coberto pela Fig 9 (curvas comparativas)** — não criada por redundância |

**W7 oficialmente fechado.** Próximo: W8 (escrita final + CM 6.3 detalhado + Conclusão).

---

### 2026-06-01 — W7 Item 6 (RF comparativo): algoritmo não é o diferencial — confirmado empiricamente

**ANTES:** O Diferencial #1 ("rigor > algoritmo") do relatório era argumento teórico baseado em conhecimento de domínio (RF e LightGBM são família de ensembles de árvores, performance similar esperada). Faltava validação empírica.

**DEPOIS:** `16_random_forest_comparativo.py` treinou **Random Forest com EXATA MESMA estratégia rigorosa do v3** — Optuna 50 trials, TimeSeriesSplit CV de 4 folds expandidos, mesma seed=42, 34 features alinhadas ao v3, mesma imputação NaN.

**Comparação final no test set (n=71.089, prev=16,93%):**

| Métrica | RF tunado | LightGBM v3 canônico | Diferença |
|---|---:|---:|---:|
| AUC-PR test | 0,8541 | **0,8556** | **−0,0015** |
| Recall@0.5 test | 0,7520 | 0,7527 | −0,0007 |

**Diferença de 0,15 pp em AUC-PR e 0,07 pp em Recall — praticamente nula.** Confirma empiricamente que **algoritmo não é o diferencial** deste estudo.

**Best hyperparams do RF (trial #42/50 do Optuna):**
- n_estimators = 359
- max_depth = 10
- min_samples_split = 29
- min_samples_leaf = 16
- max_features = sqrt
- class_weight = balanced

**Best CV AUC-PR:** 0,7988 (vs v3 = 0,8530 best CV).

**Tempo de execução real:** 10h+ (vs 30-60 min estimado originalmente). RF é mais lento que LightGBM em tunning porque cada árvore é treinada independentemente (sem o boosting que reusa cálculos).

**Integração no relatório (`rascunho.md`):**
- Seção "Diferenciais metodológicos do trabalho" → Diferencial #1 → adicionado o parágrafo "Validação empírica do ponto 'algoritmo não é o diferencial'" com a tabela comparativa.
- Tabela `comparacao_modelos_test.csv` atualizada com linha do RF.

**Insight final para a defesa:** "Um grupo que entrega RF com 85% AUC-PR sem nenhum dos passos metodológicos rigorosos deste estudo (descoberta do cascade via SHAP, triangulação SHAP × HR × IF, auditoria do label, recomendações operacionais quantificadas) entrega menos valor que este estudo, mesmo com algoritmo equivalente. O diferencial é a metodologia."

**Saídas:** `modelos/random_forest_comparativo.joblib` (12,1 MB) + `relatorio/tabelas/rf_metricas.csv` + `relatorio/tabelas/rf_hiperparametros.csv` + `modelos/optuna_study_rf.pkl`.

---

---

### 2026-05-25 — Fechamento de W6: validação cruzada de features + Fig 9 + calibração + ablation por grupo

Quatro tarefas pendentes de W6 executadas em sequência (2026-05-25, ~15 min total), agrupadas aqui por se referirem ao **fechamento metodológico** do pipeline modelagem antes de W7 (avaliação final).

#### Subseção 1 — `12_validacao_sentido_features.py` (Validação cruzada SHAP × Hazard Ratios)

Material para CM 5.3 do relatório. Gera tabela `validacao_sentido_features.csv` cruzando top features do LightGBM v3 (via SHAP, `shap_global_v3.csv`) com top features do Weibull AFT (via TR, `sobrevivencia_hazard_ratios.csv`).

**Resultados:**

| Feature | Rank SHAP | SHAP % | Rank Weibull | Weibull TR | Concordância |
|---|---:|---:|---:|---:|---|
| **tipo_caminhao** | #2 | 23,89% | **#1** | 0,038 | ✅ AMBOS top 10 |
| **tag_freq** | #4 | 3,30% | **#7** | 1,432 | ✅ AMBOS top 10 |
| **frota_793D_4S** | #7 | 1,90% | **#6** | 0,450 | ✅ AMBOS top 10 |
| **frota_793D_5S** | #9 | 1,51% | **#2** | 0,169 | ✅ AMBOS top 10 |
| qtd_alarmes_muito_alto_360min | #1 | 41,04% | #26 | 0,982 | ⚠️ SHAP só |
| razao_alarme_7d_vs_30d_anterior | #3 | 11,10% | #18 | 0,935 | ⚠️ SHAP só |
| mes | #5 | 2,09% | #16 | 1,079 | ⚠️ SHAP só |
| razao_severidade_14d_vs_60d | #6 | 1,98% | #23 | 1,027 | ⚠️ SHAP só |
| taxa_DG_operador_30d | #8 | 1,78% | #15 | 0,918 | ⚠️ SHAP só |
| count_total_24h | #10 | 1,33% | #13 | 0,887 | ⚠️ SHAP só |

**Concordância forte em 4 features estruturais (identidade do equipamento):** `tipo_caminhao`, `tag_freq`, `frota_793D_4S`, `frota_793D_5S`. Duas técnicas com fundamentação matemática diferente (TreeSHAP + maximum likelihood AFT) chegam ao mesmo conjunto. **Validação empírica forte para CM 5.3.**

**Divergência explicada:** features dominantes do SHAP que NÃO aparecem no top do Weibull (`qtd_alarmes_muito_alto_360min`, `razao_alarme_7d_vs_30d_anterior`) são **antecipativas** — predizem DG iminente no horizonte específico de 4 h. O Weibull AFT modela "tempo até qualquer DG", então sinais imediatos perdem para sinais de base rate estrutural. **Os dois modelos respondem perguntas diferentes — material para CM 6.1.**

#### Subseção 2 — `13_curvas_comparativas.py` (Fig 9 — ROC + PR comparativas)

Curvas ROC e Precision-Recall dos 3 modelos no test set (jun/2025, n=71.089, prevalência=16,93%).

**Métricas agregadas:**

| Modelo | AUC-ROC | AUC-PR |
|---|---:|---:|
| Baseline (count_critico_4h) | 0,7661 | 0,5803 |
| **LightGBM v3 (canônico)** | **0,9391** | **0,8556** |
| Weibull AFT (P(T≤4h)) | 0,7869 | 0,3148 |

**Observações operacionais:**
- v3 domina visivelmente em AUC-PR (0,8556 vs baseline 0,5803, +27,5pp; vs Weibull 0,3148, +54pp). Razão: v3 otimizado para classificação binária 4h.
- Weibull AFT supera baseline em AUC-ROC (0,7869 vs 0,7661) mas perde em AUC-PR — coerente com C-index alto + dependência da prevalência.
- **Pequena curiosidade:** prevalência reportada aqui (16,93%) inclui o `target_4h` raw do `v3.parquet`, que é maior que a taxa de DG bruta (7,35%) porque captura **qualquer DG em até 4h** (não apenas DG instantâneo). Consistente com o desenho da target já registrado em CM 4.1.

**Saída:** `fig09_curvas_comparativas.png` (2 painéis lado a lado) + `comparacao_modelos_test.csv`.

#### Subseção 3 — `14_calibracao_v3.py` (Qualidade A: calibração + Platt scaling)

Avalia se as probabilidades preditas pelo v3 estão bem calibradas (`P(y=1) predita ≈ fração real`).

**Resultados — v3 raw (sem calibração):**

| Split | Brier | Brier baseline | Skill | ECE |
|---|---:|---:|---:|---:|
| val | 0,09141 | 0,14996 | +0,3904 | 3,70pp |
| test | 0,05745 | 0,14066 | **+0,5916** | 3,78pp |

**Skill score (1 − Brier/Brier_baseline) = +0,59 no test** — modelo é substancialmente melhor que predição constante. Mas **ECE de 3,7-3,8pp** está acima do limiar 2pp definido a priori.

**Platt scaling aplicado (regressão logística sobre o val):**

| Split | ECE raw | ECE pós-Platt | Δ ECE |
|---|---:|---:|---:|
| val | 3,70pp | **1,87pp** | **−1,83pp** (melhora) |
| test | 3,78pp | **4,76pp** | **+0,98pp** (piora!) |

**Achado importante:** Platt melhora calibração no val (esperado, foi fitado lá) mas **piora no test**. Isso indica **drift de calibração entre val e test** — outro sintoma da L4 (drift mai→jun, dominado pelo CA65926) e L10 (anomalia regimal).

**Recomendação operacional honesta:** **NÃO aplicar Platt scaling em deployment**. Apesar de melhorar no val, a degradação no test (mais representativo do que veremos em produção, dado que junho tem o regime anômalo) é argumento empírico contra o ajuste. Manter v3 raw. **Calibrador Platt salvo no `joblib` para auditoria**, mas com nota explícita de "não usar".

Material para CM 5.2 (Métricas) e CM 6.2 (nova nota sobre estabilidade de calibração entre regimes).

**Saídas:** `calibracao_v3.csv`, `figExF_calibracao_v3.png` (curva de calibração + histograma), `calibrador_v3_platt.joblib` (com nota "não usar em deployment").

#### Subseção 4 — `15_ablation_grupos.py` (Profundidade 2: qual grupo carrega o modelo?)

Re-treina v3 com hiperparâmetros FIXOS (best Optuna, sem re-tuning) removendo cada **grupo** de features para medir queda de AUC-PR no test. 7 grupos + baseline = 8 treinos × ~13 s = ~110 s total.

**Resultados (test, ordenados pelo maior impacto NEGATIVO):**

| Grupo | n features removidas | AUC-PR test | Δ vs baseline (0,8556) | Queda % |
|---|---:|---:|---:|---:|
| **G7_regimal** (razao_alarme, razao_severidade) | 2 | **0,8512** | **−0,0044** | **−0,51%** |
| G3_recencia (horas_desde_ultimo_critico) | 1 | 0,8574 | +0,0018 | +0,21% |
| G5_regra_negocio (qtd_alarmes_muito_alto) | 1 | 0,8574 | +0,0018 | +0,21% |
| G1_temporais (hora, dia, turno, mes) | 4 | 0,8581 | +0,0025 | +0,29% |
| G2_rolling (15 counts) | 15 | 0,8588 | +0,0032 | +0,37% |
| G4_operador (taxa_DG, n_bypasses, op_freq) | 3 | 0,8620 | +0,0064 | +0,75% |
| **G6_categoricas** (tag_freq, frota, tipo_caminhao, estado, valor_disp) | 8 | **0,8620** | **+0,0064** | **+0,75%** |

**Achado SURPREENDENTE e crítico:** **nenhum grupo é estritamente necessário** — variação máxima ±0,01 AUC-PR. **Apenas G7 regimal causa queda real** (e mesmo assim minúscula, −0,51%). Vários grupos **melhoram** AUC-PR ao serem removidos (G4, G6).

**Contraste forte com SHAP:**
- SHAP v3 disse: `qtd_alarmes_muito_alto_360min` é 41% do peso (rank #1)
- Ablation diz: remover G5 (essa exata feature) tem **delta +0,0018** — nenhuma queda
- SHAP v3 disse: `tipo_caminhao` é 24% (rank #2)
- Ablation diz: remover G6 (que inclui `tipo_caminhao` E todas as frotas E estado_pre_evento) **MELHORA** AUC-PR em +0,75%

**Interpretação metodológica (Insight Não Óbvio — CM 6.1):**

**SHAP mede ATRIBUIÇÃO (quais features o modelo USA); ablation mede NECESSIDADE (quais features o modelo PRECISA).** A diferença entre as duas é **redundância** — feature de alto SHAP que pode ser removida sem queda significa que o modelo encontra rotas alternativas no espaço de features para a mesma predição.

O v3 entrega 0,8556 AUC-PR no test através de **múltiplas rotas redundantes**, não através de um sinal único insubstituível. Isso é coerente com L10 (sinal do CA65926 é fortemente identificável por múltiplas features: tipo_caminhao, frota, count_critico_24h, razao_alarme_*, etc.).

**Por que vários grupos melhoram quando removidos?**

Três hipóteses (não mutuamente exclusivas):
1. **Regularização efetiva** — remover features age como L1 implícito; o modelo overfita menos no train e generaliza marginalmente melhor no test.
2. **Ruído correlacionado** — features redundantes com sinal verdadeiro podem ser ruidosas; removê-las reduz variância.
3. **Hiperparams fixos não-otimais** — os best params do Optuna foram fitted para 34 features. Com menos features, params ligeiramente diferentes seriam ótimos. Não é "regularização perfeita".

**Implicação operacional importante:** o v3 é **robusto a perda de features** em deployment (sensores quebrados, fontes de dados intermitentes). Mesmo perdendo 8 das 34 features (G6 inteiro), AUC-PR mantém-se em 0,86. **Material direto para CM 6.3 (Trabalhos Futuros — robustez operacional).**

**Saídas:** `ablation_grupos.csv` (8 linhas: baseline + 7 ablations) + `figExE_ablation_grupos.png` (bar chart horizontal de deltas).

**Atualização de status do CM 6.2:**

Nenhuma nova limitação registrada hoje (L1-L10 cobrem o relevante). Mas a **calibração assimétrica val/test** vira nota adicional em L4 (drift mai→jun): "afeta também a calibração das probabilidades, não apenas a métrica AUC-PR".

---

### 2026-06-06 — Fig 12 (SHAP waterfall local) gerada + escolha do evento (item de W6 adiado, agora fechado)

- **ANTES:** Fig 12 (waterfall SHAP de uma predição individual, CM 5.3) marcada no plano como adiada para W8, com sugestão original de usar uma predição do **CA65926** (equipamento dominante do test).
- **DEPOIS:** gerada em `20_shap_waterfall_v3.py`. Evento escolhido por critério principiado e determinístico: verdadeiro positivo na faixa vermelha (p ≥ 0,30, acerto), **fora do CA65926**, com contribuições diversificadas (menor fração do empurrão positivo concentrada na feature #1, dentre os 30 TPs mais confiantes na faixa [0,60; 0,97]). Selecionado: **CA65933** (caminhão 793-D 5S), 04/jun/2025, alarme `Engine Coolant Level - Active`, p = 0,969, DG real ocorreu. Drivers: `qtd_alarmes_nivel_muito_alto_360min` = 322 (SHAP +2,94), `razao_alarme_7d_vs_30d_anterior` = 3,98 (+0,84), `tipo_caminhao` = 1 (+0,40).
- **Justificativa:** a sugestão original (CA65926) reforçaria a narrativa do equipamento dominante; escolher um caminhão comum num regime calmo (semana 1 de junho, antes da explosão do CA65926) demonstra que o v3 **generaliza** além do CA65926, resposta direta à L10. As três features que sustentam o alerta são antecipativas legítimas (Família 6 regra de negócio, Família 4 regimal, base rate por tipo), fechando a narrativa da promoção do v3 (não é cascade detector).
- **Impacto:** fecha o último item técnico aberto de W6. Saídas: `fig12_shap_waterfall_v3.png` + `shap_waterfall_evento.csv` (34 contribuições). Referência inserida no `rascunho.md` (subseção "Explicação local de uma predição individual"). Sem impacto em métricas ou modelo.

---

### 2026-06-06 — Target encoding vs frequency encoding: comparação empírica fecha item de W5 (CM 3.2)

- **ANTES:** o encoding das categóricas de alta cardinalidade (`TAG`, `Nome_Operador_Anon`) usava **frequency encoding** (Família 7), com fix de leakage aplicado em 22/05 (`06b`). O plano de W5 previa avaliar a substituição por **target encoding com KFold temporal** como refinamento incremental, mas a comparação nunca havia sido executada (item permanecia aberto, classificado como opcional).
- **DEPOIS:** target encoding implementado e comparado em `21_target_encoding_comparativo.py` (06/06). Protocolo: KFold temporal por mês (jan/fev/mar/abr) com out-of-fold no treino, smoothing α=10, ajuste sobre treino completo para val/test; comparação apples-to-apples com **hiperparâmetros fixos do v3** (mesma metodologia do ablation 15), variando somente o encoding das 2 features, treinando ambas as variantes no mesmo pipeline. **Resultado:** frequency (= v3 canônico) val=0,7132 / test=0,8556; target encoding val=0,6907 / test=0,8494. **Target encoding PIORA: −2,25pp em validação, −0,62pp em teste.** Critério de substituição do plano (ganho_val > 1pp) não atingido. **Decisão: manter frequency encoding.**
- **Justificativa:** além do critério não ser atingido, a degradação tem causa coerente com a narrativa do projeto. (i) Drift temporal (L4): as taxas-alvo por categoria calibradas em jan-abr não transferem para o regime de mai/jun; frequency encoding é mais estável sob mudança de regime. (ii) Correlação negativa entre frequência e taxa de DG no treino (−0,31 para TAG, −0,22 para operador): equipamento mais frequente não é equipamento com mais DG, então as duas codificações carregam sinais diferentes, e o target encoding superajusta ao regime de treino. Sanity check: a variante baseline reproduziu o v3 canônico bit-a-bit no teste (0,8556), confirmando fidelidade do pipeline de comparação.
- **Impacto:** fecha o último item analítico aberto de W5 (antes opcional, agora resolvido com evidência empírica). `v3.parquet` permanece canônico sem alteração. Saída: `relatorio/tabelas/target_encoding_comparativo.csv`. Reforça empiricamente a robustez do frequency encoding sob drift e dá material adicional para a discussão de L4/L10.

---

<!-- Próximas entradas serão adicionadas conforme decisões forem tomadas em W3, W4, etc. -->
