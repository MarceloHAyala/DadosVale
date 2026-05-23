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

<!-- Próximas entradas serão adicionadas conforme decisões forem tomadas em W3, W4, etc. -->
