# Rascunho do Relatório — Programa Desenvolver 2026

Documento de escrita progressiva que vai consolidando as seções do relatório final ao longo das semanas W2→W8. Será migrado para `Desenvolver_Template.docx` em W9.

**Status atual:** seções preenchidas até **W6 parcial (LightGBM v2 canônico treinado)** — **Introdução**, **Entendimento do Negócio** (CM 1.1 + CM 1.2), **Metodologia Parte 1** (Exploração de Dados — W2 EDA + Q4 + Q5), **Metodologia Parte 2** (Preparação dos Dados — limpeza + 7 famílias de *features* (35 cols, com Família 1 expandida em W5 para 5 janelas) + 3 *targets* multi-janela + *split* temporal *walk-forward* + *fix* de *leakage* de *encoding*, totalizando matriz canônica `v3.parquet` com 544.885 × 58 colunas) e **Metodologia Parte 3** (Modelagem — baseline heurístico W5, LightGBM v1 W5 com 5 variantes + GATE MARCO 1 PASS, **LightGBM v2 W6** com Optuna + TimeSeriesSplit CV + determinismo: AUC-PR test 0,8618). Figuras 7, 8 e Extra C integradas. Refatoração 24/05: detalhes técnicos dos scripts movidos para `notas_metodologicas.md` Seções 4-9 — `rascunho.md` mantém narrativa + resultados + interpretação, com referências aos detalhes computacionais. **Pendentes:** Análise SHAP sobre v2 (W6), Sobrevivência Weibull AFT + Isolation Forest (W6), Avaliação estratificada (W7), Conclusão (W8).

---

## Introdução

Este relatório apresenta o desenvolvimento de um modelo preditivo para a antecipação de alertas Don't Go (DG) em frotas de equipamentos de mineração da Vale, na região de Itabira, no escopo do desafio de Análise Avançada de Dados do Programa Desenvolver 2026. O problema central consiste em prever, a partir do histórico recente de telemetria e do contexto operacional de cada equipamento, a probabilidade de ocorrência de um alerta DG nas próximas quatro horas — janela compatível com o tempo necessário para mobilização de peças e equipe de manutenção corretiva no ciclo operacional típico da região.

O conjunto de dados disponibilizado cobre seis meses (janeiro a junho de 2025): aproximadamente **37,16 milhões de eventos de telemetria** distribuídos entre 35 equipamentos com instrumentação contínua, e cerca de **378 mil ciclos de apontamento operacional** sobre 47 equipamentos. A taxa observada de DGs no semestre é de aproximadamente **0,054%** (19.962 ocorrências em 37,16 milhões de eventos), caracterizando um problema de classificação extremamente desbalanceado. O presente trabalho segue a metodologia CRISP-DM e estrutura-se nas seções de Entendimento do Negócio, Exploração de Dados (Metodologia, Parte 1), Preparação dos Dados, Modelagem, Avaliação e Resultados, e Conclusão.

---

## Entendimento do Negócio

### Contexto operacional e o fluxo Don't Go (CM 1.1)

A Figura 1 sintetiza o fluxo operacional que gera os dados deste estudo e localiza visualmente o ponto em que o modelo preditivo proposto se encaixa, com o objetivo de converter parada não planejada em inspeção preventiva.

[Figura 1 — Diagrama do fluxo operacional](figuras/fig01_fluxo_de_apontamentos.png)

O ciclo operacional começa quando o operador da Vale inicia um **ciclo de apontamento** (bloco A da figura), registrando o instante inicial (`Inicio`) e identificando o estado em que o equipamento se encontra dentre quatro possibilidades — Operando, Parado, Manutenção ou Hibernando. Cada ciclo é unicamente identificado e encerrado por um instante final (`Fim`), formando a base do conjunto `desenvolver_apontamentos.parquet` (377.907 ciclos no semestre). Detalhes do dicionário de campos estão consolidados em [`notas_exploracao_inicial.md`](notas_exploracao_inicial.md).

Durante o ciclo, os sensores do equipamento geram **telemetria contínua** (bloco B): aproximadamente 206.000 eventos por dia distribuídos entre as 35 TAGs com instrumentação, registrando variáveis como temperatura, pressão, vazão, nível de fluidos, peso de carga e velocidade. Cada evento é classificado em tempo real pela **Central de Monitoramento de Ativos (CMA)** da Vale (bloco C) em três níveis de criticidade — `Informacional`, `Não-Crítico` ou `Crítico` — segundo regras de negócio que combinam o tipo do alarme, o seu valor numérico e o padrão observado nos minutos anteriores. Eventos `Informacional` representam aproximadamente 98,5% do volume e não geram alertas operacionais; as cerca de 1,5% restantes são candidatos a virar Don't Go (detalhamento na Seção de Caracterização dos Dados).

O **catálogo de regras "Muito Alto" da CMA** (bloco D) — consolidado em [`tabelas/eventos_muito_alto.csv`](tabelas/eventos_muito_alto.csv), com 82 regras catalogadas — define exatamente quando um alarme dispara um alerta DG. Duas modalidades coexistem: **(i) disparo imediato** — uma única ocorrência do alarme em nível mais severo é suficiente (`QTD = 1`, `TEMPO = 0`); **(ii) disparo por acumulação** — `N` ocorrências do alarme dentro de uma janela `T` em minutos (por exemplo, "cinco alarmes Nível 2 consecutivos em 360 minutos"). Aproximadamente 95% das regras catalogadas são *wrappers* sobre alarmes nativos do fabricante (`TIPO = ALARME OEM`, principalmente Caterpillar para os caminhões 793-D), 4% derivam de análises de tendência criadas pela própria Vale, e 1% são regras de sistema. Essa proporção tem implicação metodológica relevante e será retomada na seção de Limitações: o *label* `Is_Dont_Go` herda majoritariamente a calibração de fábrica dos sensores, não uma definição operacional autônoma da Vale, o que torna a discussão de viés do *label* uma preocupação concreta a ser empiricamente testada pelo *Isolation Forest* em W6.

Quando alguma das 82 regras é satisfeita pela telemetria observada, o evento recebe a flag **`Is_Dont_Go = 1`** (bloco E), sinalizando que o equipamento **não deve sair da mina ou continuar operando** até que o problema seja resolvido. A **ação operacional** correspondente (bloco F) é então acionada pelo *dispatcher* responsável, que comanda a parada e dispara inspeção, intervenção ou manutenção corretiva. Tipicamente, o equipamento entra em um novo ciclo de apontamento com estado `Manutenção`, fechando o *loop* operacional. No semestre analisado, esse mecanismo gerou **19.962 ocorrências de DG**, distribuídas de forma fortemente desigual entre alarmes, frotas, estados operacionais e meses do semestre — assimetria detalhada nas seções de Caracterização e Análise temporal mais adiante.

### Cenário de aplicação operacional do modelo (CM 1.2)

O modelo proposto neste estudo encaixa-se **lateralmente** ao fluxo operacional descrito acima (bloco G da Figura 1) — não substitui a regra CMA, mas a **antecipa**. Ao consumir continuamente a telemetria recente (rolling windows de 1, 4 e 24 horas) junto com o estado operacional corrente, o histórico recente do operador e o histórico próprio do alarme, o modelo produz a cada instante uma estimativa de `P(DG nas próximas 4 horas)` para cada TAG instrumentada. A janela de 4 horas foi escolhida por três motivos convergentes: **(i) operacional** — compatível com o tempo médio de mobilização de peças e equipe de manutenção em Itabira; **(ii) preditivo** — curta o bastante para que o estado atual dos sensores ainda tenha valor informativo; **(iii) metodológico** — análise de sensibilidade prevista para W4 testa janelas alternativas (2h e 8h) para validar empiricamente a escolha em vez de fundamentá-la apenas em argumento operacional.

O cenário de aplicação proposto opera da seguinte forma. A cada início de turno operacional (cadência típica de 6h-18h e 18h-6h, ou alternativamente em cadência horária se a infraestrutura suportar), o modelo recalcula a probabilidade de DG das próximas 4h para cada uma das 35 TAGs com telemetria contínua. As TAGs cuja probabilidade ultrapassa um limiar de operação calibrado em W7 — definido pela curva *precision-recall* e por análise de custo-benefício explícita entre falsos positivos (inspeções desnecessárias) e falsos negativos (paradas não planejadas) — aparecem no painel do *dispatcher* como **fila priorizada de inspeção preventiva**, ranqueada pelo score do modelo. O *dispatcher* aciona a manutenção, que mobiliza peça e equipe enquanto o equipamento ainda opera, evitando a parada não planejada caso o DG real efetivamente venha a ocorrer quatro horas depois — ou, no melhor cenário, evitando o DG por completo via intervenção precoce no problema subjacente.

O ganho operacional esperado é a conversão de uma fração das paradas não planejadas (reativas, custo alto, equipamento desativado sem aviso) em inspeções preventivas (planejadas, custo baixo, executadas em janelas de operação ociosa ou em troca de turno). A magnitude desse ganho será quantificada em W7-W8 a partir das métricas finais do modelo escolhido — Recall sobre DG e tempo médio de antecipação — traduzidas em horas de parada evitadas e estimativa de custo evitado por equipamento e por frota.

---

## Metodologia — Parte 1: Exploração de Dados

### 1. Visão geral da abordagem

A análise exploratória cobriu o semestre completo de janeiro a junho de 2025, totalizando 37.164.054 eventos de telemetria distribuídos entre 35 equipamentos com instrumentação contínua, e 377.907 ciclos de apontamento operacional sobre 47 equipamentos. A análise foi conduzida em duas etapas: (i) caracterização estrutural do dataset, padronização de tipos e normalização de inconsistências encontradas na fonte, registradas em `controle_alteracoes.md`; (ii) testes empíricos de 13 hipóteses analíticas (8 testadas em W1+W2, 5 pendentes para fases posteriores), consolidadas em `hipoteses_eda.md`. Os critérios técnicos e ferramentais seguiram a arquitetura definida no `PLANEJAMENTO.md` — Polars como engine de dados (para suportar 37M linhas em 4GB de RAM), `matplotlib + seaborn` para visualização, e asserções defensivas em todos os scripts da pipeline.

### 2. Caracterização e qualidade do dataset

O dataset bruto apresentou três inconsistências sistemáticas de qualidade de dados que exigiram tratamento antes de qualquer análise estatística:

1. **Colunas temporais como `String`**: `Inicio_Turno` e `Fim_Turno` foram entregues como strings no formato `"YYYY-MM-DD HH:MM:SS.fff"`, impossibilitando extração de features temporais e *joins* por intervalo. Convertidas para `Datetime(μs)` sem perda de informação.
2. **Vírgula decimal brasileira em `Valor`**: 821.849 registros (2,2% do total) usavam `","` como separador decimal (ex: `"46,2569999694824"`), incompatível com `cast(Float64)` direto. Foram tratados via `.str.replace(",", ".")` antes do *cast*. Adicionalmente, 237.443 registros eram literalmente a string `"NULL"` — convertidos para `null` real do Polars.
3. **Inconsistências de capitalização e encoding em colunas categóricas**: a coluna `Criticidade` apresentou 5 variantes no dataset bruto, incluindo 11 registros com falha parcial de encoding (`"N??o Crítico"`, `"Não Cr??tico"`). A coluna `NIVEL` (na sheet CMA do arquivo de regras de negócio) apresentou 6 registros com `"Muito alto"` (minúsculo) entre 76 com `"Muito Alto"` — 7,3% de inconsistência localizada que teria gerado perda silenciosa em filtros literais. Ambas as colunas foram normalizadas para forma canônica ASCII.

**Insight metodológico:** as três inconsistências têm padrão comum — múltiplas *pipelines* fonte gravando a mesma categoria com normalização diferente. Sugere problema sistêmico na ingestão de strings categóricas que merece atenção da equipe responsável pela CMA (registrado como recomendação em Trabalhos Futuros).

A análise do volume temporal dos apontamentos operacionais confirma a cobertura completa e estável do dataset ao longo do semestre, condição necessária para o *join* temporal posterior entre telemetria e apontamentos.

[Figura 2 — Distribuição temporal dos apontamentos (jan-jun/2025)](figuras/fig02_distribuicao_temporal_apontamentos.png)

O volume diário oscila entre aproximadamente 1.800 e 2.400 ciclos por dia (média ~2.100/dia, ~88/hora), **sem tendência crescente, sem decrescente, e sem lacunas de dias inteiros sem registro** ao longo dos 180 dias observados. Essa estabilidade tem três implicações relevantes: (i) o dataset é homogêneo em volume operacional bruto, o que torna mais notável a heterogeneidade encontrada na análise mensal dos DGs (Seção 5 — os três regimes não decorrem simplesmente de "mais operação"); (ii) o *join* temporal entre cada evento de telemetria e o ciclo de apontamento ativo no momento atingiu **100% de cobertura** (relatado adiante na Seção 4.2) — a *pipeline* de apontamentos da Vale entrega instrumentação sem gaps; (iii) o volume por hora do dia apresenta variação de aproximadamente ±20% em torno da média horária (cerca de 14.000 a 17.500 apontamentos/hora), com vales discretos em 8-10h e 15h e leves picos em 4-5h e 17-18h, consistentes com as transições do ciclo operacional de 12 horas (turnos típicos 6h-18h e 18h-6h). A operação é, portanto, **contínua 24×7** — não há "horário comercial" em que concentrar atenção, e essa propriedade tem implicação direta para a modelagem: as features temporais derivadas (`hora`, `dia_semana`, `turno`) devem capturar variação intra-dia, não ausência ou presença de operação.

### 3. Decisão de filtragem: eventos `Informacional`

A análise de distribuição de DGs por nível de criticidade revelou um achado determinístico crucial para a viabilidade computacional do projeto:

| Criticidade | Total de eventos | Total de DGs | Taxa de DG | % do volume |
|---|---:|---:|---:|---:|
| Informacional | 36.619.169 | **0** | **0,0000%** | 98,53% |
| Não-Crítico | 461.865 | 9.676 | 2,10% | 1,24% |
| Crítico | 83.020 | 10.286 | **12,39%** | 0,22% |

Os 36,6 milhões de eventos `Informacional` no semestre completo geraram **zero** DGs — não estatisticamente próximo de zero, mas exatamente zero. A separação é determinística: `Informacional` é definicionalmente fora do escopo do *target*. A decisão de filtrar essa criticidade reduz o *dataset* de trabalho de 37.164.054 para 544.885 linhas (redução de 98,53%) sem perda de qualquer caso positivo. Essa decisão habilita o uso de *rolling windows* em W4 sem risco de estouro de memória RAM e foi registrada em `controle_alteracoes.md`.

Como nota lateral relevante para a discussão de viés do *label* (Limitações), a taxa de DG por evento `Crítico` é de **12,39%** — aproximadamente um em cada oito eventos críticos torna-se um DG. Isso quantifica a "força preditiva instantânea" da própria categoria de criticidade, independente de qualquer rolling window ou *feature engineering* mais sofisticado.

### 4. Concentração de alertas Don't Go

A análise de concentração dos alertas Don't Go segue três decomposições complementares — por alarme, por equipamento e por estado operacional — e estabelece o panorama empírico que orientará a fase de modelagem. Como decomposição-base, a distribuição de eventos relevantes (após o filtro de `Informacional`) por tipo de equipamento já evidencia a assimetria fundamental do dataset.

[Figura 3 — Eventos por Tipo de equipamento × Criticidade (Informacional filtrado)](figuras/fig03_tipo_x_criticidade.png)

Caminhões 793-D acumulam **376.632 eventos** no semestre (aproximadamente 305 mil Não-Crítico e 71 mil Crítico — ratio 81/19), enquanto escavadeiras LeTourneau L 1850 acumulam **168.253 eventos** (aproximadamente 157 mil Não-Crítico e 11 mil Crítico — ratio 93/7). Os caminhões geram **2,2 vezes mais eventos em termos absolutos** que as escavadeiras, e dentre esses eventos a proporção classificada como Crítico é **2,7 vezes maior** (19% contra 7%). Combinando esses dois fatores com o resultado de Q4 (apenas 167 dos 19.962 DGs ocorrem em escavadeiras — 0,84%), conclui-se que a taxa de conversão de evento em DG nas escavadeiras é da ordem de **53 vezes menor** do que nos caminhões. Esse achado complementa empiricamente a hipótese H4.1 (registrada em `hipoteses_eda.md`) sobre o perfil estatístico distinto da frota LeTourneau L 1850, e justifica a obrigatoriedade da análise estratificada por tipo de equipamento na fase de avaliação (W7 — Qualidade C).

#### 4.1. Concentração por alarme

Dos 4.402 alarmes únicos no dataset, **apenas 19 alarmes geraram pelo menos um DG no semestre completo** — 99,6% dos alarmes monitorados são irrelevantes para o *target*. Entre esses 19, os cinco principais concentram 87,3% dos 19.962 DGs:

[Figura Extra B — Pareto top-10 alarmes precursores de DG](figuras/figExB_pareto_alarmes.png)

| Posição | Alarme | DGs | % | % acumulado |
|---:|---|---:|---:|---:|
| 1 | Engine Coolant Level - Active | 9.615 | 48,17% | 48,17% |
| 2 | Right Front Brake Temperature - Active | 4.494 | 22,51% | 70,68% |
| 3 | Transmission Oil Level - Active | 1.426 | 7,14% | 77,82% |
| 4 | Left Rear Brake Temperature - Active | 999 | 5,00% | 82,82% |
| 5 | Aftercooler Level - Active | 892 | 4,47% | 87,29% |

A concentração observada no semestre completo (87,3%) reproduz o padrão identificado anteriormente no relatório preliminar restrito a janeiro (88%), confirmando que **o universo de alarmes operacionalmente críticos é estável e dramaticamente menor do que o universo de alarmes monitorados**. Esse achado tem implicação direta para *feature engineering*: a fase de modelagem (W4) pode focar atenção nesses 19 alarmes prioritariamente, sem necessidade de criar *features* para os 4.383 restantes.

#### 4.2. Concentração por equipamento (Q4)

A análise por equipamento (Pergunta 4 do escopo analítico) cruzou três dimensões — frota, tipo e estado operacional — usando *join* temporal `join_asof` entre cada evento de telemetria e o ciclo de apontamento ativo no instante do evento (estratégia *backward*, com filtro `Data_Evento <= Fim` para garantir validade temporal). **100% dos 19.962 DGs encontraram um ciclo de apontamento válido**, confirmando cobertura temporal completa da *pipeline* de apontamentos da Vale.

**Distribuição por frota:**

| Frota | Tipo | DGs | % | TAGs |
|---|---|---:|---:|---:|
| 793-D 5S | Caminhão | 9.341 | 46,79% | 13 |
| 793-D 4S | Caminhão | 7.405 | 37,10% | 8 |
| 793-D 2S | Caminhão | 1.699 | 8,51% | 4 |
| 793-D 3S | Caminhão | 1.350 | 6,76% | 3 |
| LeTourneau L 1850 | Escavadeira | 167 | 0,84% | 5 |

Duas frotas (793-D 5S e 4S) concentram **83,89%** dos DGs do semestre, em uma combinação previsível dado o volume operacional desses caminhões. O achado mais relevante, contudo, é a **assimetria entre caminhões e escavadeiras**: caminhões 793-D 5S apresentam taxa média de ~720 DGs por equipamento, enquanto as escavadeiras LeTourneau L 1850 registram apenas ~33 DGs por equipamento — uma diferença de aproximadamente 22 vezes. Essa diferença pode ter três interpretações não mutuamente exclusivas: (i) caminhões realmente sofrem mais falhas que escavadeiras por terem mais componentes em movimento contínuo; (ii) viés da regra CMA, calibrada para caminhões e mal adaptada aos sensores das escavadeiras; (iii) subreporte sistêmico — combinado com outros achados sobre essa frota (cinco escavadeiras sem telemetria contínua, 95% dos *bypasses* manuais do operador, e 88% dos erros de medição de peso vêm dessa frota), sugere problema estrutural de instrumentação. **Recomenda-se análise estratificada (Caminhão vs Escavadeira) em W7 — métricas agregadas mascarariam esse comportamento.**

A decomposição por equipamento individual (TAG), em granularidade abaixo da frota, revela um padrão complementar relevante: a distribuição não é apenas concentrada em poucas frotas — é fortemente concentrada em **poucos equipamentos**, com um caso destacado como outlier.

[Figura Extra G — Pareto top-15 TAGs com mais DGs](figuras/figExG_pareto_tags.png)

O equipamento **CA65926 sozinho responde por aproximadamente 25% de todos os DGs do semestre** (~4.900 de 19.962 DGs), seguido por outros quatro equipamentos (CA65931, CA65930, CA65792, CA65927) na faixa de 1.300 a 1.700 DGs cada. Os cinco TAGs mais frequentes acumulam aproximadamente 60% dos DGs, e os quinze mais frequentes acumulam cerca de 85% — vinte equipamentos com telemetria contribuem com os 15% restantes. Dois padrões adicionais reforçam achados anteriores: **(i) nenhuma escavadeira (TAGs `PE*`) aparece no top 15**, confirmando empiricamente a hipótese H4.1 (LeTourneau L 1850 com perfil estatístico distinto dos caminhões); **(ii) o equipamento CA65926 é candidato a investigação operacional dedicada** pela Vale — pode tratar-se de equipamento com problema crônico (manutenção corretiva profunda, troca de subsistema, falha recorrente de sensor), ou pode coincidir com o equipamento referenciado no caso paradigma `desenvolver_dontgo.xlsx` (cuja cadeia de 147 eventos consecutivos motiva a Obs 2.3 sobre o padrão de acumulação). A análise estratificada por TAG individual em W7, complementar à estratificação por frota, é necessária para distinguir comportamento sistêmico de outlier dominante e evitar generalização indevida do modelo treinado.

#### 4.3. Estado operacional no momento do DG

Cruzando os DGs com o estado operacional do ciclo de apontamento ativo no momento de cada evento, obtém-se uma decomposição inicialmente surpreendente:

| Estado operacional | DGs | % |
|---|---:|---:|
| Operando | 16.122 | 80,76% |
| **Manutenção** | **2.525** | **12,65%** |
| Parado | 1.184 | 5,93% |
| Hibernando | 131 | 0,66% |

O resultado de que aproximadamente **um em cada oito DGs ocorre durante ciclos de Manutenção** motivou uma investigação adicional para diferenciar três hipóteses sobre essa fração: (H1) o DG causou a transição do ciclo para Manutenção; (H2) são falsos positivos gerados por testes de bancada que disparam alarmes artificiais; (H3) bug de *pipeline* na CMA que não verifica o estado antes de gravar o evento. A diferenciação foi feita pela posição relativa de `Data_Evento` no intervalo `[Inicio, Fim]` do ciclo e pelo cruzamento com os alarmes envolvidos.

Os 2.525 DGs em Manutenção apresentaram distribuição quase-uniforme com viés leve para o início do ciclo (bucket 0-10% com 15,3% vs 10% uniforme; mediana em 38,6%). Os top alarmes coincidem exatamente com os top 5 alarmes do semestre (Engine Coolant Level 55,8%, Aftercooler Level 13,2%, etc.), e nenhum alarme de diagnóstico ou *bypass* aparece no top 10. A conclusão é que **a hipótese H2 ("falsos positivos de bancada") está estatisticamente correta na distribuição, mas conceitualmente errada na interpretação**: esses 2.525 DGs são alertas legítimos disparados durante reativações de teste no ciclo de manutenção. Sensores de temperatura de freio e de nível de fluido de motor só disparam com o equipamento operando — não são falsos positivos artificiais. O cenário real é que ciclos longos de manutenção incluem múltiplas ativações operacionais para teste, e cada ativação é oportunidade de DG real.

Essa conclusão tem três implicações: os 2.525 DGs **não devem ser filtrados em W3** (são alertas reais); no entanto, contextualmente eles representam "DG detectado em teste de manutenção" e não "falha iminente em produção", o que justifica a criação de uma variante `Is_Dont_Go_producao` em W5/W6 para comparação de desempenho; e finalmente, esse achado **refuta parcialmente a suposição inicial sobre viés do *label* CMA** — não há 2.525 falsos positivos óbvios para descontar, e a validação empírica desse viés agora depende exclusivamente do diagnóstico via *Isolation Forest* planejado para W6.

#### 4.4. Estrutura de correlação linear entre features numéricas

A análise da matriz de correlação de Pearson entre as variáveis numéricas disponíveis após o filtro de `Informacional` revela um padrão importante para orientar a escolha de algoritmos de modelagem.

[Figura 5 — Heatmap de correlação entre features numéricas](figuras/fig05_heatmap_correlacao.png)

Nenhuma das correlações entre o target `Is_Dont_Go` e as features brutas ultrapassa magnitude **0,22**: as duas mais fortes são `Is_Dont_Go × Valor` (+0,22, valores numéricos mais altos têm associação fraca com a ocorrência de DG) e `Is_Dont_Go × Id_Criticidade` (−0,20, eventos com `Id_Criticidade` menor — isto é, mais críticos — apresentam maior probabilidade de DG). As demais variáveis (`hora`, `dia_semana`, `mes`) apresentam correlação efetivamente nula com o target (módulo abaixo de 0,03). A única correlação não trivial entre variáveis explicativas é `Id_Criticidade × mes` (+0,17), reflexo plausível da inversão de severidade do alarme Engine Coolant Level entre janeiro e fevereiro discutida na Seção 5 (Anomalia A).

Esse achado, embora pareça "negativo" em superfície, sustenta três decisões metodológicas centrais do projeto: **(i) a justificativa empírica para o uso de LightGBM** como modelo principal em vez de regressão logística ou outros métodos lineares — coeficientes de Pearson capturam apenas relações lineares e a ausência delas implica que o sinal preditivo reside em **interações não-lineares** e em **padrões temporais de acumulação**, exatamente o que árvores de gradient boosting combinadas com *rolling windows* são capazes de modelar; **(ii) a centralidade do feature engineering em W4** — se a matriz bruta não exibe estrutura preditiva direta, o ganho virá das features derivadas (`rolling counts` por janela, razões temporais, `estado_pre_evento`, razão vs *baseline* histórico do próprio alarme); **(iii) a confirmação de que o problema é não trivial** — não basta um limiar sobre uma única variável instantânea para antecipar DG, narrativa que será explicitada no relatório como justificativa para a complexidade metodológica adotada.

### 5. Análise temporal: três regimes distintos

A análise da distribuição mensal dos DGs revelou o achado mais significativo da exploração para o desenho do modelo: **o semestre não é estatisticamente homogêneo**.

[Figura 4 — Série temporal de DGs (jan-jun/2025)](figuras/fig04_serie_temporal_dgs.png)

| Mês | Crítico | Não-Crítico | Total | % NC | Regime |
|---|---:|---:|---:|---:|---|
| Jan | 2.077 | 504 | 2.581 | 19,5% | Baseline normal |
| Fev | 1.071 | 3.422 | 4.493 | 76,2% | Anomalia A |
| Mar | 771 | 3.452 | 4.223 | 81,7% | Anomalia A (pico) |
| Abr | 837 | 1.322 | 2.159 | 61,2% | Recuperação |
| Mai | 685 | 595 | 1.280 | 46,5% | Quase-normal |
| Jun | 4.845 | 381 | 5.226 | 7,3% | Anomalia B |

Três regimes operacionais distintos foram identificados:

**Anomalia A (fevereiro-março):** o alarme *Engine Coolant Level - Active* — que em janeiro registrou 259 ocorrências como Não-Crítico — saltou para 2.414 em fevereiro (9,3× janeiro) e 2.741 em março (10,6×). Simultaneamente, **a severidade do mesmo alarme inverteu massivamente**: de 83% Crítico em janeiro para 10% em fevereiro e 6% em março. A combinação volume + inversão de severidade aponta para mudança de *threshold* ou regra da CMA em fevereiro de 2025, não para evento operacional puro (que afetaria volume mas não a proporção entre níveis). A reversão parcial em maio-junho (~20% Crítico) sugere ajuste posterior. Sem acesso a registros internos da CMA, a confirmação dessa hipótese está fora do escopo deste estudo e é registrada como recomendação em Trabalhos Futuros (auditoria interna de mudanças regulatórias na CMA durante o período).

**Anomalia B (junho):** o alarme *Right Front Brake Temperature - Active* registrou entre 3 e 67 ocorrências por mês de janeiro a maio (média 28/mês), e **4.247 ocorrências em junho — salto de 151,7×**. Esse único alarme concentrou 87,7% dos 4.845 DGs Crítico de junho. Visualmente, na série temporal, observa-se que o pico ocorre concentrado nos últimos dias do mês (com um dia registrando aproximadamente 1.100 DGs), não distribuído ao longo de junho. Hipóteses operacionais consideradas (não testáveis sem registros de operação): recapagem em massa de pneus afetando termoregulação dos freios, sazonalidade térmica do início de inverno em Itabira, troca ou recalibração de sensores em lote.

**Implicação para a estratégia de modelagem:** o *split* temporal originalmente planejado — treino em jan-abr, validação em mai, teste em jun — atravessa fronteiras de regime: o treino contém a Anomalia A (Engine Coolant Não-Crítico explodindo) enquanto o teste contém a Anomalia B (Right Front Brake Crítico explodindo). O alarme dominante do teste tem entre 3 e 67 ocorrências mensais no treino, o que o torna **estatisticamente invisível para o modelo durante o aprendizado**. Esse padrão é a definição empírica de *non-stationarity*. A decisão metodológica adotada (registrada em `PLANEJAMENTO.md`, formalização em `controle_alteracoes.md` quando W4 implementar o *split*) foi manter o *split* fixo e tratar o *drift* como tema central da análise de erro em W7, com métricas reportadas mês a mês obrigatoriamente. Adicionalmente, foi planejada uma família nova de *features* em W4 que captura "razão de eventos do alarme nos últimos 7 dias contra o *baseline* histórico do próprio alarme" — esse tipo de *feature* poderia, em princípio, gerar sinal preditivo para alarmes que explodem do nada (como o Right Front Brake em junho).

### 6. Q5 — Distribuição por hora e dia da semana

[Figura 6 — Heatmap taxa de DG por hora × dia da semana](figuras/fig06_heatmap_hora_dia.png)

Após o filtro de `Informacional`, a taxa de DG por célula `(hora, dia da semana)` foi calculada como `Σ Is_Dont_Go / count(eventos)` em cada combinação. O resultado responde à Pergunta 5 do escopo analítico ("Alertas concentram em turnos/dias/períodos?") com uma resposta afirmativa e padrão não trivial.

**Achados centrais:**

1. **Segunda-feira concentra as maiores taxas de DG em quase todas as horas do dia.** A linha "Seg" aparece sistematicamente com tonalidades mais claras (taxa mais alta) que os outros dias, com taxa típica entre 4% e 6%.
2. **O pico extremo do mapa ocorre nas segundas-feiras às 23h**, com taxa próxima de 6,5% — a única célula no topo da escala de cor. Esse pico é seguido por taxas elevadas também na madrugada de segunda (2-5h) e ao longo da tarde-noite (10-22h).
3. **Terças e quartas são os dias mais "frios"**, com taxas tipicamente entre 2% e 3%. Domingo também apresenta zonas de baixa taxa, particularmente entre 10h e 11h e entre 17h e 19h.
4. **Sábado apresenta um pico esparso no início da manhã** (~4h), padrão difícil de interpretar sem dados operacionais adicionais.

A interpretação operacional mais provável para o padrão de segunda-feira é a chamada *rampa de retomada após o fim de semana*: equipamentos que tiveram menor uso ou ficaram parados no fim de semana voltam à operação plena na segunda-feira, e problemas latentes (vazamentos, desgastes, falhas eletrônicas em estado dormente) manifestam-se nas primeiras horas de operação intensa. O pico noturno (23h) é compatível com o turno de troca operacional e maior carga térmica acumulada no equipamento ao longo do dia. Hipóteses alternativas — menor experiência dos operadores nos turnos de segunda-feira, pressão por recuperar a produção do fim de semana — são plausíveis mas não testáveis dentro do escopo deste estudo.

**Implicação para modelagem:** *features* derivadas do par (`hora_do_dia`, `dia_semana`) capturam pelo menos parte da variação observada e devem ser incluídas na matriz de modelagem em W4. A magnitude do padrão (variação de aproximadamente 3× entre células mínimas e máximas) é estatisticamente significativa e não deve ser desprezada.

### 7. Q4 — Síntese do perfil dos equipamentos

A combinação das análises dos itens 4.2 e 4.3 acima responde integralmente à Pergunta 4 do escopo: o perfil dos equipamentos com mais alertas concentra-se em **caminhões 793-D 5S e 4S**, que juntos respondem por 83,89% dos DGs do semestre. A frota LeTourneau L 1850 (escavadeiras) apresenta perfil estatístico distinto, com taxa de DG por equipamento aproximadamente 22 vezes menor que os caminhões — comportamento que se soma a três outros achados independentes sobre essa frota (cinco equipamentos sem telemetria contínua, 95% dos *bypasses* manuais do operador, e 88% dos erros de medição de peso vêm dessa frota), sugerindo questões sistêmicas de instrumentação ou viés da regra CMA. Adicionalmente, a decomposição por estado operacional do equipamento no momento do DG revelou que 12,65% dos DGs ocorrem durante ciclos de Manutenção — alertas reais disparados em reativações de teste, mas conceitualmente distintos de "falha iminente em produção", o que motivou a criação planejada de uma variante `Is_Dont_Go_producao` para comparação de desempenho de modelo em W5/W6.

### 8. Síntese de hipóteses e implicações para a modelagem

A análise exploratória testou empiricamente oito hipóteses analíticas (consolidadas integralmente em `hipoteses_eda.md`): duas foram confirmadas (concentração de DGs em poucos alarmes, padrão sistêmico em LeTourneau L 1850), quatro foram refutadas (cobertura completa de telemetria, eventos `Informacional` gerando algum DG, salto Não-Crítico como drift linear, valor=4347 como medição válida), e duas foram refutadas com reinterpretação relevante (`Id_Criticidade=4` revelou-se *flag* de *bypass* manual; DGs em Manutenção revelaram-se alertas legítimos de teste). Cinco hipóteses adicionais permanecem pendentes para investigação em W3-W7, todas registradas em `observacoes_importantes.md`.

A taxa elevada de hipóteses refutadas (seis de oito) é considerada **sinal de qualidade da exploração**: a EDA está cumprindo o papel metodológico de testar premissas, não apenas de confirmar expectativas iniciais. Hipóteses refutadas com reinterpretação geraram, em todos os casos, achados analíticos mais ricos que a hipótese original previa — em particular, a reinterpretação dos DGs em Manutenção produziu uma família nova de *features* para W4 e uma comparação de variantes de *target* para W5/W6.

As implicações para a fase de modelagem (W3-W7) são resumidas a seguir:

- **W3 — Limpeza:** filtro de `Criticidade = Informacional` (decisão validada empiricamente, registrada em `controle_alteracoes.md`); manutenção dos 2.525 DGs em Manutenção (são alertas reais); tratamento padrão de outliers em `Valor` via *flag* (sem impacto no *target*, baixo risco).
- **W4 — Features:** foco em 19 alarmes operacionalmente relevantes; criação de *rolling windows* (1h, 4h, 24h) para capturar acumulação; criação de família regimal de *features* (razão *vs baseline* histórico do próprio alarme; razão entre níveis de criticidade) para mitigar parcialmente o *drift* identificado; criação de *feature* `estado_pre_evento`; *features* temporais (hora, dia da semana, turno) com base no padrão da Pergunta 5.
- **W5/W6 — Modelagem:** treinamento de duas variantes de *target* (`Is_Dont_Go` completo vs `Is_Dont_Go_producao` filtrando os 2.525 em Manutenção) para comparação; *Isolation Forest* como diagnóstico empírico do viés do *label* CMA (única evidência empírica disponível após a refutação parcial do Risco 3.3).
- **W7 — Análise estratificada:** métricas reportadas obrigatoriamente mês a mês (para expor *drift*); estratificação por frota (Caminhão vs Escavadeira) e por estado operacional do DG; análise de erro focada em Right Front Brake Temperature (alarme dominante de junho, estatisticamente invisível no treino).
- **W8 — Limitações:** discussão honesta de *non-stationarity* (três regimes empiricamente identificados); discussão do viés do *label* CMA com evidência do *Isolation Forest*; recomendação à Vale de auditoria de mudanças regulatórias na CMA entre janeiro e fevereiro de 2025 (Anomalia A); recomendação de investigação contextual do evento operacional de junho (Anomalia B).

---

---

## Metodologia — Parte 2: Preparação dos Dados (W3 + W4 parcial)

### Visão geral da fase

A fase de Preparação dos Dados transforma os datasets brutos em uma **matriz pronta para modelagem**, com colunas que codificam explicitamente os padrões temporais e contextuais identificados na exploração (Parte 1). A motivação central é direta: o modelo preditivo (W5-W7) recebe uma tabela e decide, para cada linha, *"haverá um alerta Don't Go nas próximas 4 horas neste equipamento?"*. As 19 colunas brutas do dataset original (`Data_Evento`, `TAG`, `Alarme`, `Criticidade`, `Valor`, etc.) não respondem sozinhas a perguntas como *"este equipamento teve 50 eventos na última hora?"* ou *"este alarme está pulsando mais que o normal dele?"* — informações que estão **implícitas** nos dados e precisam ser materializadas como colunas (features) para que o modelo possa aprender padrões preditivos.

A Parte 2 foi executada em duas semanas: W3 cobriu a limpeza estendida e features básicas; W4 (em andamento) acrescenta as famílias avançadas que codificam histórico temporal recente, contexto operacional e desvios de regime.

### Limpeza estendida (W3 — 03_limpeza.py)

O pipeline `03_limpeza.py` foi expandido em W3 com 6 novas etapas (6-12) sobre o script de inspeção inicial criado em W1, encerrando a fase de tratamento. As etapas 1-5 (inspeção: normalização de Criticidade, verificação de duplicados, frequência média, estatísticas descritivas, validação da taxa de DG) foram preservadas. As etapas 6-12 implementaram: (i) filtro de `Criticidade = Informacional` (decisão validada empiricamente — 36.619.169 eventos sem nenhum DG); (ii) validação defensiva de outliers em `Valor`; (iii) análise de missing values por coluna (CM 3.1); (iv) validação de intervalos inválidos em apontamentos (`Inicio > Fim`); (v) detecção de sobreposições temporais de ciclos; (vi) persistência dos parquets limpos; (vii) geração do `controle_alteracoes.csv` no formato CM 3.1 obrigatório.

O resultado dessa fase é um par de datasets canônicos: `telemetria_limpa.parquet` (544.885 linhas × 19 colunas — redução de 98% vs antes do filtro) e `apontamentos_limpo.parquet` (377.907 linhas × 8 colunas, com flag `is_sobreposicao` para o achado das 340 sobreposições de ciclo concentradas no equipamento CA65789 — H1.4).

### Feature Engineering (W3 + W4 — 05_features.py)

O pipeline `05_features.py` constrói **35 features documentadas + 3 targets multi-janela** a partir do dataset limpo, organizadas em 8 famílias semânticas (1 família básica de W3 numerada como Família 0, 4 famílias avançadas de W4 parcial — Famílias 1 a 4, 3 famílias avançadas de W4 completo — Famílias 5 a 7, e a construção do target em etapa separada — Família 8 conceitualmente). A Família 1 (rolling) foi expandida em W5 (23/05) para incluir as janelas de 2h e 8h, garantindo alinhamento perfeito com a Profundidade 1 do LightGBM (ver `controle_alteracoes.md` entrada de 2026-05-23).

**As 7 famílias de *features* + 1 família conceitual de *targets*:**

| Família | # cols | Pergunta operacional respondida | Motivação |
|---|---:|---|---|
| **0 — Básicas** | 5 | "Quando o evento ocorreu? Tem medição numérica?" | Q5 (Fig 6); 3 regimes temporais; 43,58% de eventos sem `Valor` |
| **1 — Rolling windows** (W4 + W5) | 15 | "Quantos eventos no mesmo TAG nas últimas N horas? (1h, 2h, 4h, 8h, 24h × Critico / Nao_Critico / Total)" | Obs 2.5: 48% dos DGs vêm de acumulação. **Janelas 2h e 8h adicionadas em W5** para alinhamento perfeito com a Profundidade 1 do LightGBM |
| **2 — Recência** | 2 | "Há quantas horas foi o último DG / Crítico desse equipamento?" | Padrão clássico de manutenção preditiva. Achado lateral: 5.104 eventos com `horas_desde_ultimo_critico = 0` indicam cascata de alarmes simultâneos |
| **3 — Estado pré-evento** | 1 | "O que o equipamento estava fazendo 1h antes?" | Obs 2.7: 12,65% dos DGs em estado Manutenção são DGs legítimos (re-ativações de teste) |
| **4 — Regimal** | 2 | "Este alarme está disparando muito mais que o baseline histórico dele neste equipamento?" | Obs 2.6: anomalia RFB de jun (151,7× sobre média), anomalia Engine Coolant fev-mar |
| **5 — Operador** | 2 | "Este operador tem taxa de DG alta? Faz muitos bypasses recentes?" | Q3 do edital; H1.2 (bypass como flag latente) |
| **6 — Regra de negócio** | 1 | "Quantos alarmes 'Muito Alto' (das 82 regras CMA) ocorreram nas últimas 6h?" | Obs 2.5: ~48% dos DGs vêm de regras de acumulação CMA |
| **7 — Encoding categórico** | 7 | (codifica TAG, Frota, Tipo, Operador para o LightGBM consumir) | Pré-condição técnica do modelo; H4.1 (LeTourneau distinta) |
| Total features | **35** | — | — |
| **Targets multi-janela** (CM 3.3) | 3 | `target_2h`, `target_4h`, `target_8h` — DG no horizonte (t, t+Nh]? | Janela operacional de 4h (CM 1.2) + sensibilidade |

> 📘 **Detalhes técnicos do cálculo de cada família (algoritmos Polars exatos, asserções defensivas, justificativas de fórmulas):** ver [`notas_metodologicas.md` Seção 4](notas_metodologicas.md). **Script gerador:** `Projeto/codigo/05_features.py`. **Saídas:** `dados/features/v1.parquet`, `v2_parcial.parquet`, `v2.parquet` (35 features + 3 targets, 24,4 MB) + `relatorio/tabelas/documentacao_features.csv` (35 entradas no formato CM 3.2) + `sensibilidade_janela.csv`.

#### Achado lateral relevante para o relatório: cascata de alarmes simultâneos

A Família 2 (recência) revelou **5.104 eventos (0,94% do dataset) com `horas_desde_ultimo_critico = 0`** — ~10× mais que `horas_desde_ultimo_DG = 0` (479 eventos, 0,10%). Isso indica **cascata de alarmes simultâneos**: múltiplos sensores disparando no mesmo instante em resposta a uma única falha física (e.g., queda súbita de pressão hidráulica que aciona simultaneamente alarmes de temperatura de transmissão, vibração e nível de fluido). **Não é *leakage* temporal** — é sinal preditivo legítimo de cascata em curso, comportamento que o modelo aprenderá a reconhecer. Esse padrão informa diretamente a discussão de CM 6.1 (Insights Não Óbvios).

#### Pergunta 3 do edital (Q3) respondida via Obs 2.4

A investigação em W5 (Obs 2.4 resolvida via `exploracao_w5_obs_pendentes.py`) sobre o operador OP_067 do caso paradigma CA65924 produziu **resposta empírica para a Pergunta 3 do edital**. Resumo:

- **OP_067 NÃO é outlier extremo:** taxa 6,338% (1,73× o baseline global de 3,664%), rank #76 de 394 operadores, com 152 outros operadores em faixa estatisticamente comparável.
- **OP_029 é o caso com maior massa estatística problemática:** 1.016 DGs absolutos sobre 3.125 eventos (taxa 32,5%).
- **Resposta a Q3:** o comportamento do operador correlaciona com DG, **mas de forma difusa** — há um *continuum* de variação ~30× entre p25 e p95, sem 1-2 operadores "ruins" carregando o problema.

H5.3 fica formalmente refutada com reinterpretação em `hipoteses_eda.md`. Tabela `relatorio/tabelas/obs24_taxa_dg_por_operador.csv` (394 linhas) é o entregável direto para a seção CM 5 do relatório final.

> 📘 **Metodologia completa da investigação de Obs 2.4 (operacionalização de "outlier", quantis da distribuição, análise por volume vs por taxa):** ver [`notas_metodologicas.md` Seção 1](notas_metodologicas.md). **Script:** `Projeto/codigo/exploracao_w5_obs_pendentes.py`.

#### Limitação conhecida do encoding (corrigida em W5)

As *features* `tag_freq` e `operador_freq` da Família 7 foram computadas sobre o *dataset* global (treino + val + teste) em W4 — *leakage* temporal subtil de magnitude pequena (volumes mensais estáveis) mas tecnicamente presente. **Corrigido em W5 via `06b_fix_encoding_leakage.py` (22/05/2026)**, gerando `v3.parquet` (matriz canônica de modelagem). Casos específicos identificados: 2 TAGs (`CA65791`, `CA65916`) e 13 operadores aparecem em val/teste mas não em treino — recebem `freq = 0` no `v3.parquet` (decisão Opção C-1).

> 📘 **Análise teórica e empírica do *fix* (verificação de magnitude antes da decisão, comparação Opção 1 vs 3, justificativa metodológica):** ver [`notas_metodologicas.md` Seção 2](notas_metodologicas.md). **Script:** `Projeto/codigo/06b_fix_encoding_leakage.py`. **Saída:** `v3.parquet` (544.885 × 58, 16,3 MB) — *input* canônico de toda a Modelagem em W5+.

### Estado da matriz de features

A matriz canônica de modelagem após a etapa de correção do *leakage* subtil de *frequency encoding* (W5, executada em 22/05/2026) e a posterior expansão das janelas da Família 1 para alinhamento perfeito com a Profundidade 1 (W5, 23/05/2026 — ver `controle_alteracoes.md` entradas de 2026-05-22 e 2026-05-23 e `notas_metodologicas.md` Seção 2) é o arquivo `Projeto/dados/features/v3.parquet`, com **544.885 linhas × 58 colunas** e **16,3 MB**, produto da execução sequencial de `05_features.py` (35 features + 3 targets), `06_split.py` (coluna `split`) e `06b_fix_encoding_leakage.py` (recomputação de `tag_freq` e `operador_freq` sobre o *split* de treino apenas). A composição completa das 58 colunas é a seguinte:

| Categoria | Colunas | Origem |
|---|---:|---|
| Colunas originais do dataset limpo (telemetria + apontamentos) | 19 | `telemetria_limpa.parquet` + `apontamentos_limpo.parquet` |
| Features básicas (Família 0) | 5 | `05_features.py` etapas 1-3 — W3 |
| Features avançadas (Famílias 1-7) | 30 | `05_features.py` etapas 4-10 — W4 + W5 (Família 1 expandida em 23/05 de 9 para 15 features; `tag_freq` e `operador_freq` recomputadas em 22/05 via `06b_fix_encoding_leakage.py`) |
| Targets multi-janela (`target_2h`, `target_4h`, `target_8h`) | 3 | `05_features.py` etapa 11 — W4 (CM 3.3) |
| Coluna de partição temporal (`split ∈ {train, val, test}`) | 1 | `06_split.py` etapa 2 — W4 (CM 4.1) |
| **Total** | **58** | |

A tabela `documentacao_features.csv` (entregável CM 3.2 do Estudo Guiado) consolida as 35 entradas correspondentes às *features* explicitamente criadas no *script*, com nome, tipo, descrição, fórmula, motivação e semana de criação para cada uma; as 19 colunas originais do dataset e as 4 colunas de *target* e *split* são tratadas como infraestrutura do *pipeline*, não como *features* de modelagem propriamente ditas, e portanto não aparecem nesse dicionário.

Arquivos intermediários do *pipeline* são preservados em `dados/features/` para reprodutibilidade incremental e para inspeção de regressões, formando uma hierarquia clara de versões:

- **`v1.parquet`** (6,9 MB) — 5 *features* básicas da Família 0 apenas (W3, compatibilidade retroativa).
- **`v2_parcial.parquet`** (21,6 MB) — 25 *features* das Famílias 0 a 4 (W4 parcial, com Família 1 já expandida para 15 features em W5).
- **`v2.parquet`** (24,4 MB) — 35 *features* completas + 3 *targets* multi-janela (W4 completo + expansão W5, antes do *split* temporal).
- **`v2_split.parquet`** (16,3 MB) — `v2.parquet` + coluna `split` (W4 final, antes do *fix* de *leakage* do *encoding*; preservado como referência histórica, **não usar em modelagem**).
- **`v3.parquet`** (16,3 MB) — `v2_split.parquet` com `tag_freq` e `operador_freq` recomputadas sobre treino apenas (W5, **input canônico de toda a Modelagem**).

Os *scripts* downstream (`07_baseline.py`, `08_lightgbm.py`, `09_sobrevivencia.py`, `11_isolation_forest.py`) leem `v3.parquet` diretamente e filtram pela coluna `split` nos pontos de treino, validação e teste. Os arquivos `v1`, `v2_parcial`, `v2` e `v2_split` ficam deliberadamente preservados como camadas de inspeção (e em particular `v2_split.parquet` pode ser usado em W6 como variante de teste comparativo "antes vs depois do *fix*" para CM 6.1, conforme task opcional registrada em `PLANEJAMENTO.md`), mas **não devem ser usados diretamente como *input* de modelos** — fazer isso reintroduziria o *leakage* subtil corrigido em 22/05 ou contornaria o protocolo de avaliação temporal.

A execução completa do *pipeline* de feature engineering (carga + 7 famílias + 3 *targets* + validação defensiva + persistência dos três *parquets*) leva aproximadamente **7 segundos** sobre as 544.885 linhas em hardware comum de desenvolvimento; o *split* temporal adicional (`06_split.py`) acrescenta **2,6 segundos**; o *fix* do *encoding* (`06b_fix_encoding_leakage.py`) acrescenta **4,8 segundos**. O tempo total de regeneração de `v3.parquet` a partir dos parquets limpos é de aproximadamente **15 segundos** — Polars opera eficientemente nessa escala, e a iteração rápida foi um critério explícito de arquitetura desde a fase de ingestão (W1). A consequência prática é que qualquer ajuste em features, janelas, *targets* ou tratamento de *encoding* tem custo de iteração desprezível.

Três artefatos auxiliares são gerados em paralelo à matriz e alimentam diretamente o relatório final:

- **`relatorio/tabelas/documentacao_features.csv`** (CM 3.2, 35 entradas) — dicionário canônico das *features*, formato exigido pelo Estudo Guiado.
- **`relatorio/tabelas/sensibilidade_janela.csv`** (3 janelas × 6 meses = 18 entradas) — distribuição mensal dos positivos para `target_2h`, `target_4h` e `target_8h`, base descritiva para a análise comparativa preditiva agendada para W5 (treinar LightGBM com cada uma das três janelas e medir AUC-PR para justificar empiricamente a escolha de 4 horas em vez de fundamentá-la apenas em argumento operacional do CM 1.2).
- **`relatorio/tabelas/split_temporal.csv`** (CM 4.1, 3 entradas) — sumário do *split* com período (`data_ini` e `data_fim`), contagens de eventos / DGs / positivos `target_4h` / TAGs únicas, e taxas percentuais de DG e de positivos por *split*.

### Validação empírica da Hipótese H5.2 (Fig Extra C)

A Hipótese H5.2 originalmente formulada — "o padrão calmaria → acúmulo → disparo do caso CA65924 é universal nos DGs" — foi testada empiricamente na Fig Extra C, que compara o caso paradigma (147 eventos consecutivos do caminhão CA65924 culminando em um DG, conforme `desenvolver_dontgo.xlsx`) com três amostras aleatórias de DGs de outros equipamentos (semente fixa para reprodutibilidade).

A métrica adotada para quantificar "acúmulo" foi a razão entre o número de eventos nos últimos 30 minutos antes do DG e o número de eventos nos 90 minutos anteriores a esse intervalo: `razão = u30 / p90`. Como as duas janelas têm tamanhos diferentes (30 min vs 90 min), a interpretação direta da razão é enganosa — mais útil é a **densidade relativa** (eventos por minuto na janela final dividida pela densidade na janela inicial), igual a `razão × 3`. O padrão *sharp* hipotetizado para CA65924 — "calmaria → acúmulo" — exige uma densidade relativa pelo menos seis vezes maior na janela final (`razão ≥ 2`), valor adotado como limiar de confirmação. Densidades relativas em torno de 1× indicam fluxo aproximadamente uniforme; valores entre 1,2× e 2× indicam densificação **gradual**, sinal mais sutil que o padrão *sharp* hipotetizado.

[Figura Extra C — Cadeia de eventos pré-DG: paradigma CA65924 vs 3 comparações aleatórias](figuras/figExC_ca65924_cadeia.png)

Os resultados quantitativos dos quatro painéis estão consolidados na tabela abaixo:

| Painel | TAG | Eventos (2h pré-DG) | u30 | p90 | Razão | Densidade relativa | Interpretação |
|---|---|---:|---:|---:|---:|---:|---|
| (a) | CA65924 (paradigma) | 147 | 41 | 106 | 0,39 | **1,16×** | ~ uniforme |
| (b) | CA5927 (random) | 28 | 9 | 19 | 0,47 | **1,42×** | gradual |
| (c) | CA65908 (random) | 19 | 15 | 4 | **3,75** | **11,25×** | **sharp ✓** |
| (d) | CA65927 (random) | 38 | 13 | 25 | 0,52 | **1,56×** | gradual |

A leitura mais precisa do resultado é em duas camadas. **Na formulação original — padrão *sharp* universal — a Hipótese H5.2 está refutada:** apenas o painel (c) — CA65908 — exibe o salto característico de densidade exigido pelo limiar (`11,25×`), com 79% dos seus eventos concentrados nos últimos 30 minutos pré-DG sobre uma calmaria efetiva de apenas quatro eventos nos 90 minutos anteriores. Os três painéis restantes ficam todos abaixo do limiar de confirmação. **Em uma formulação fraca alternativa — "há alguma densificação pré-DG" — os quatro painéis são compatíveis:** densidades relativas variando de 1,16× a 11,25× indicam que, em todos os casos observados, a janela final é ao menos um pouco mais densa que a inicial, sem o salto característico do *sharp* em três deles. A própria CA65924, que motivou a hipótese, apresenta um fluxo praticamente uniforme de aproximadamente 1,2 eventos por minuto ao longo das duas horas, sem calmaria identificável — o que é coerente com a observação qualitativa original de "147 eventos consecutivos" (volume alto e contínuo), mas **incoerente com a inferência narrativa subsequente** de que esses 147 eventos representassem uma rampa de acúmulo pré-disparo. Trata-se de um caso típico de **viés de seleção do caso paradigmático**: 147 eventos é um número grande, mas distribuídos uniformemente é silêncio operacional contínuo, não acumulação.

A análise visual da figura sugere, ainda, um sub-padrão alternativo que a métrica de volume agregado não captura e que é **independente da refutação acima**: a distribuição temporal por **criticidade**, e não apenas por volume. Em três dos quatro painéis — CA65924 (painel a), CA5927 (painel b) e CA65908 (painel c) — eventos de criticidade `Crítico`, representados em vermelho na figura, concentram-se nos últimos minutos antes do DG mesmo quando o volume total se distribui uniformemente. O CA65924 é o caso mais expressivo: dos 147 eventos da janela, 138 são `Informacional`, 7 são `Não-Crítico` e apenas **um único** é `Crítico` — e esse único `Crítico` ocorre justamente próximo ao DG. O sinal preditivo central pode portanto residir no **acúmulo de criticidade** (transição de severidade), não no acúmulo de volume — e essa sub-hipótese é independente da métrica `razão = u30/p90` adotada para a hipótese original, ou seja, **a refutação do padrão *sharp* de volume não enfraquece a sub-hipótese de criticidade**. A validação formal está prevista para a fase de Avaliação (W6), via análise SHAP comparando a importância relativa das features `count_critico_*h` e `count_total_*h` (Família 1 do `05_features.py`); a hipótese reformulada está registrada como Observação 2.11 em `observacoes_importantes.md` como pendente de validação empírica.

A consequência metodológica para a fase de Modelagem é que a família de **rolling counts** baseada em volume — apesar de continuar útil, por capturar casos como o CA65908 — deixa de ser a "família dominante" antecipada, e cede primazia para as famílias **regimal** (razão vs baseline próprio do alarme) e **estado pré-evento** (contexto operacional). Essa reinterpretação será confrontada com os resultados empíricos do LightGBM e da análise SHAP em W6.

Esse achado também é candidato direto à seção de **Insights Não Óbvios** (CM 6.1) do relatório final, com a narrativa: uma hipótese formulada qualitativamente a partir de um único caso emblemático foi refutada pela análise quantitativa, mas a própria refutação gerou uma sub-hipótese mais refinada — demonstração concreta de que a análise rigorosa **gera valor mesmo quando refuta** premissas iniciais, e atenção explícita ao viés de seleção do caso paradigmático.

### Construção do target multi-janela (CM 3.3)

Com a matriz de *features* finalizada, fechou-se a definição operacional do *target* — a coluna que o modelo aprenderá a prever em W5-W6. A pergunta operacional traduzida em rótulo é: *"para cada evento de telemetria, haverá pelo menos um DG no mesmo equipamento nas próximas N horas?"*. Para suportar a análise de sensibilidade prevista para W4 (Profundidade 1), o `05_features.py` constrói simultaneamente três rótulos paralelos `target_2h`, `target_4h` e `target_8h` (com `target_4h` adotado como principal pelo motivo operacional descrito na seção CM 1.2 da Introdução).

A construção opera em duas passagens sobre o dataframe ordenado por `Data_Evento` dentro de cada TAG. Uma coluna auxiliar `_dg_ts` recebe o timestamp apenas dos eventos em que `Is_Dont_Go = 1`, e NULL em todos os demais. Em seguida, a expressão `_dg_ts.reverse().shift(1).forward_fill().reverse().over("TAG")` localiza, para cada evento, o timestamp do **próximo DG estritamente posterior** do mesmo equipamento — o `shift(1)` aplicado após o `reverse` garante que um evento que é DG não fique sendo o "próximo DG dele mesmo". A diferença `_proximo_dg_ts - Data_Evento`, convertida para horas, é então comparada contra os três horizontes para gerar os rótulos: `target_Nh = 1` se a diferença está em `(0, N]`, e `0` caso contrário.

A semântica da janela merece destaque. O intervalo é **aberto no início** (`> 0`) — o evento corrente, mesmo se for ele próprio um DG, **não pertence ao seu próprio target**, prevenindo a degeneração trivial em que o modelo aprende a "prever" o DG que ele já está observando como input. O intervalo é **fechado no fim** (`<= N`) — o instante exato do próximo DG é incluído como positivo do horizonte, consistente com a definição operacional do dispatcher (a inspeção preventiva é útil enquanto o DG ainda não ocorreu).

Eventos sem DG futuro observado no horizonte temporal do dataset — 102.602 ocorrências (18,83%), tipicamente concentradas nas últimas semanas de junho ou em TAGs sem nenhum DG no semestre — são tratados como **`y = 0` censurado**, em vez de NULL. A escolha é consistente com a semântica operacional (se nenhum DG ocorreu nas N horas seguintes, o instante de decisão era de fato seguro segundo a regra CMA) e mantém a métrica AUC-PR computável sobre o conjunto de teste. A modelagem alternativa por **Weibull AFT** prevista para W6 oferece a segunda leitura rigorosa do problema, tratando o censoring como dado adicional em vez de aproximação.

A distribuição empírica dos três rótulos no dataset de 544.885 linhas revelou um achado metodológico de impacto direto no plano de modelagem:

| Target | Positivos | Taxa de positivos | Negativos | Eventos censurados |
|---|---:|---:|---:|---:|
| `target_2h` | 139.090 | **25,5%** | 405.795 | 102.602 (18,83%) |
| `target_4h` (principal) | 159.396 | **29,3%** | 385.489 | 102.602 (18,83%) |
| `target_8h` | 186.343 | **34,2%** | 358.542 | 102.602 (18,83%) |

A taxa de positivos do `target_4h` (**29,3%**) é cerca de **540 vezes maior que os 0,054% declarados na Introdução** como taxa global de DGs — uma surpresa metodológica que merece ser tratada explicitamente. A divergência não é um erro: ela revela que a Introdução descreve a taxa do **evento pontual** `Is_Dont_Go = 1` (1 evento em 1.852 instantâneos), enquanto o target operacional é uma **janela temporal** em que cada DG "reivindica" como positivos todos os eventos do mesmo equipamento nas ~4h precedentes. Multiplicando os 19.962 DGs do semestre por aproximadamente 25 eventos pré-DG cada (frequência típica de ~6 eventos/min × 4h), chega-se à ordem dos ~500k positivos esperados — a diferença para os 159.396 observados é absorvida pelo censoring e pelos equipamentos com DGs muito espaçados em que a janela 4h não cobre eventos contíguos. A monotonicidade `25,5% < 29,3% < 34,2%` (todo positivo de 2h também é positivo de 4h e de 8h por construção) foi verificada como asserção defensiva.

A consequência prática para o pipeline de modelagem em W5 é significativa. O problema continua desbalanceado, mas em **ordem de magnitude muito mais branda** do que a inicialmente declarada — estratégias como `class_weight='balanced'` ou `scale_pos_weight ≈ 2.4` no LightGBM (e não `≈ 1850`, como sugeriria a leitura literal de 0,054%) são suficientes. Não há necessidade do arsenal pesado de *imbalance learning* — SMOTE temporal, *undersampling* agressivo, *focal loss* — que originalmente se cogitava para um problema 1:1.852. Essa simplificação metodológica deve ser registrada explicitamente na seção de Modelagem (W5) e na Introdução do relatório final (nota de pé esclarecendo que a taxa 0,054% é do evento pontual e o target operacional 4h tem taxa muito mais alta por construção).

Este achado é candidato natural à seção de **Insights Não Óbvios (CM 6.1)** do relatório final, com narrativa convergente com a refutação da Hipótese H5.2 documentada na subseção anterior: uma extrapolação razoável feita no Entendimento do Negócio precisa ser revista assim que confrontada com a definição operacional rigorosa. Demonstra concretamente que **a passagem do "evento" para a "janela de predição" não é trivial** — escolha que muitos relatórios omitem ou tratam como detalhe técnico, e que aqui muda a magnitude do desbalanceamento em duas ordens.

A consequência para a explicabilidade do modelo em W7 é uma checagem específica via análise SHAP: confirmar que o modelo aprende sinal genuíno de pré-falha — desvios de regime, recência, contexto operacional — e não apenas a "regra trivial" *houve DG nas últimas 4h → provavelmente terá DG nas próximas 4h também*, autocorrelação alta induzida pela própria regra CMA de acumulação. Se essa última for a fonte dominante de importância, o modelo será preditivo no papel mas terá valor operacional limitado, e a discussão será aprofundada na seção de Limitações (CM 6.2).

O estado atual da matriz é portanto `v2.parquet` com **544.885 linhas × 57 colunas** (19 colunas originais + 35 features documentadas + 3 colunas-alvo), **24,4 MB** após a expansão da Família 1 em W5 (23/05) para incluir as janelas 2h e 8h. A tabela `sensibilidade_janela.csv` consolida as taxas globais e a distribuição mensal de positivos para cada janela; a comparação preditiva entre os três horizontes via LightGBM com parâmetros *default* — que conclui a Profundidade 1 prevista para W4 — fica reservada para a sessão inicial de W5 (`08_lightgbm.py`), agora com *features* perfeitamente alinhadas a cada horizonte (T2 → `count_critico_2h`, T4 → `count_critico_4h`, T8 → `count_critico_8h`). A conclusão final será registrada em `controle_alteracoes.md` após os resultados empíricos.

### Diagrama da janela de predição (Fig 7)

A semântica do *target* `target_4h` é melhor explicada por meio do diagrama da Figura 7, que materializa o conceito da janela de predição na linha do tempo de telemetria.

[Figura 7 — Janela de predição do target operacional](figuras/fig07_janela_predicao.png)

O instante de decisão `t` corresponde ao momento em que um evento de telemetria é observado e o modelo gera sua probabilidade de DG. Os eventos passados (à esquerda de `t`, em cinza) alimentam as *features* de *rolling* (`count_*_1h`, `count_*_4h`, `count_*_24h`), de recência (`horas_desde_ultimo_*`) e regimais — todas projetadas para usar apenas o passado estrito de cada equipamento. A região azul à direita representa a **janela de predição (`(t, t+4h]`)**: o rótulo `target_4h` recebe valor 1 se houver pelo menos um DG do mesmo equipamento dentro dessa janela, e 0 caso contrário. A janela é aberta no início — o próprio evento em `t`, ainda que seja um DG, **não conta para o seu próprio target**, prevenindo a degeneração trivial em que o modelo "prevê" o evento que ele já está observando. A janela é fechada no fim, o que faz com que um DG em `t+4h` exato seja considerado positivo. Um DG hipotético dentro da janela (X vermelho, em `t+2,5h` no exemplo) leva o rótulo a 1; um DG posterior a 4h (X cinza em `t+5,2h`) é descartado para o cálculo desse rótulo específico — embora venha a ser positivo para os eventos próximos a `t+1,2h` que ainda o cobrem dentro de suas próprias janelas de 4h. O diagrama torna explícita a distinção fundamental entre o **evento pontual** `Is_Dont_Go` (que vale 0,054% no semestre) e o **target operacional** `target_4h` (que vale 29,3% no semestre, pelo mecanismo descrito na subseção anterior).

### Split temporal walk-forward (CM 4.1)

A partição do dataset em conjuntos de treinamento, validação e teste segue o protocolo *walk-forward* exigido para problemas com forte autocorrelação temporal nas *features* — escolha que precisa ser justificada explicitamente porque o protocolo concorrente, o *k-fold* aleatório, é o *default* da literatura de classificação supervisionada e seria escolhido por inércia caso a discussão não acontecesse aqui.

O argumento contra *k-fold* aleatório é direto: as famílias 1 (*rolling*) e 2 (recência) capturam por construção a autocorrelação temporal dentro de cada equipamento — `count_critico_4h` de um evento em `t` está estatisticamente acoplado ao `count_critico_4h` do evento em `t + 5 minutos`, porque ambos compartilham os mesmos eventos no passado de 4 horas. Em um *k-fold* aleatório, eventos do mesmo equipamento espalhados pelos diferentes *folds* iriam interleavar treino e teste no tempo, e o modelo aprenderia padrões locais que não generalizam para o futuro real do equipamento. *Walk-forward* respeita a semântica operacional pretendida: treina sobre dados passados e mede a generalização sobre o futuro estritamente posterior.

Os cortes adotados foram os limites de mês: treinamento sobre janeiro a abril (`Data_Evento < 2025-05-01`), validação sobre maio (`Data_Evento < 2025-06-01`), e teste sobre junho. A coerência visual direta com a Figura 2 (distribuição mensal exploratória) foi o critério decisivo — o leitor pode verificar a composição de cada *split* contra Figura 2 sem cálculos intermediários. A alternativa de cortar nos limites de turno (`06:00`/`18:00`) foi descartada: o modelo é *event-time-aware* (decisão por evento, não por turno), portanto deslocar o corte em seis horas seria cosmético; e as *features* na fronteira de cada *split* têm rolagens computadas com dados do *split* anterior — o que reproduz exatamente o comportamento desejado em produção (o modelo em 1/maio usa naturalmente as últimas 24 horas, que incluem 30/abril), não sendo *data leakage* uma vez que o sentido cronológico passado→futuro é estritamente preservado.

A distribuição empírica dos três *splits* está consolidada na Tabela X e visualizada na Figura 8.

| Split | Período | Eventos | DGs | Taxa de DG | Positivos `target_4h` | Taxa pos. 4h | TAGs |
|---|---|---:|---:|---:|---:|---:|---:|
| **Treino** | jan-abr (Data_Evento < 2025-05-01) | 394.971 (72,5%) | 13.456 (67,4%) | 3,41% | 132.877 | 33,64% | 33 |
| **Validação** | mai (até 2025-06-01) | 78.825 (14,5%) | 1.280 (6,4%) | **1,62%** | 14.481 | 18,37% | 31 |
| **Teste** | jun | 71.089 (13,0%) | 5.226 (26,2%) | **7,35%** | 12.038 | 16,93% | 30 |

[Figura 8 — Estratégia de validação temporal: split walk-forward jan-abr / mai / jun](figuras/fig08_split_temporal.png)

A Figura 8 organiza visualmente o split em dois painéis. O painel superior mostra a contagem mensal de eventos pós-filtro Informacional, colorida por *split* (azul para treino, laranja para validação, vermelho para teste), com anotações da contagem de DGs em cada mês e linhas verticais nos cortes (`2025-05-01` e `2025-06-01`). O painel inferior plota a taxa mensal de DG, evidenciando o padrão de *drift* mês-a-mês.

O *drift* observado é o achado metodológico central desta subseção e direciona vários ajustes operacionais na fase de Modelagem. Três conclusões emergem da Figura 8 com força para impactar W5, W6 e W7:

- **A taxa de DG do teste (junho, 7,35%) é cerca de 2,2× a média do treino (3,37%) e 4,5× a taxa da validação (1,62%).** Modelos LightGBM que apresentem bom desempenho na validação podem degradar substancialmente em junho. A degradação não será aleatória — é direcional, induzida por um motor mecânico identificável: a anomalia *Right Front Brake Temperature Active* de junho (registrada na Observação 2.6 e visualizada na Figura 4), que explode 151,7× sobre o baseline histórico do próprio alarme. A previsibilidade do *drift* é, por si só, uma janela analítica: permite formular hipóteses sobre quais *features* deveriam estar mais ativas em junho (família regimal, em particular `razao_alarme_7d_vs_30d_anterior`) e diagnosticá-las explicitamente em W7 via SHAP.

- **A validação (maio, 1,62% de taxa de DG) é o regime mais escasso do semestre.** Hiperparâmetros calibrados em maio tenderão a ser otimistas em precisão e pessimistas em *recall*. O GATE MARCO 1 de W5 — "LightGBM bate baseline em AUC-PR?" — precisa ser interpretado com essa cautela: ganho marginal em validação pode ser ruído de regime escasso, e a comparação verdadeira fica reservada para a avaliação em teste em W7.

- **Análise de erro estratificada mês-a-mês vira obrigatória, não opcional — e começa em W5, não em W7.** O Risco 3.2 (*drift* temporal) já estava registrado em `observacoes_importantes.md`; a Figura 8 quantifica sua magnitude. A consequência operacional: as métricas AUC-PR, *Recall* e Precisão do LightGBM v1 serão reportadas **separadamente em maio e em junho** já no GATE MARCO 1 (W5), não só no Anexo W7 — detectar problemas cedo permite acionar mitigações antes que uma iteração inteira de *tuning* seja desperdiçada sobre métricas single-fold de maio. O *split* fixo (sem retreinamento intra-mês) é mantido por simplicidade de comunicação no relatório, mas a discussão da seção de Limitações (CM 6.2) precisará confrontar o *trade-off* entre "modelo único e legível" e "estratégia *rolling* de retreinamento mensal" — esta última prevista como Trabalho Futuro (CM 6.3).

Um achado lateral relevante registra-se aqui para evitar repetição posterior. A análise de cobertura por *split* identificou **rotação de equipamentos**: duas TAGs (`CA65791`, `CA65916`) aparecem em validação ou teste mas não em treino, e cinco TAGs (`CA65917`, `CA65908`, `CA65902`, `CA65922`, `CA65923`) aparecem em treino mas não em validação ou teste; treze operadores em validação ou teste estão ausentes do treino. As *features* de codificação `tag_freq` e `operador_freq` (Família 7) foram computadas sobre o *dataset* global, ou seja, embutem volumes de validação e teste em valores que o modelo verá no treino. A magnitude esperada do efeito é pequena — volumes mensais por equipamento são estáveis e a estabilidade compensa a sobreposição temporal — **mas tecnicamente é uma forma branda de** *data leakage*. O *fix* correto é recalcular as frequências apenas sobre o treino e aplicar a validação e teste, e está registrado em `PLANEJAMENTO.md → W5` para resolução conjunta com a migração de *frequency encoding* para *target encoding* (já planejada e dependente do *target* real).

O estado canônico do *pipeline* **após a conclusão de `06_split.py` (W4)** era a matriz `v2_split.parquet` — `v2.parquet` original acrescido da coluna `split ∈ {train, val, test}`. Essa matriz foi a referência intermediária para duas operações subsequentes em W5: (i) o *fix* de *leakage* de *encoding* (`06b_fix_encoding_leakage.py`, 22/05/2026) que recomputou `tag_freq` e `operador_freq` sobre o *split* de treino apenas; e (ii) a expansão das janelas da Família 1 (23/05/2026, retroalimentado em `05_features.py`) para incluir 2h e 8h, com alinhamento perfeito ao `target_2h` e `target_8h` da Profundidade 1. Após essas duas operações, a matriz canônica final é `v3.parquet` (544.885 × 58 colunas, **16,3 MB**) — *input* único para toda a fase de Modelagem em W5+. *Scripts* a jusante lerão `v3.parquet` e filtrarão pela coluna `split` nos pontos de treino, *tuning* e avaliação; `v2.parquet` e `v2_split.parquet` ficam preservados como referências históricas de auditoria mas não devem ser usados diretamente em modelagem, evitando contornar o protocolo de avaliação temporal ou reintroduzir o *leakage* corrigido.

### Re-framing do drift (W5, Obs 2.9): a anomalia de junho é a falha localizada de UM equipamento

A leitura inicial da Figura 8 atribuiu o salto de taxa de DG entre maio e junho (1,62% → 7,35%, fator 4,5×) à anomalia do alarme `Right Front Brake Temperature - Active`, registrada na Observação 2.6 (W2) como uma explosão de aproximadamente 150 vezes sobre o *baseline* histórico do próprio alarme. A diagnose inicial ficou registrada como "*drift* estrutural com causa mecânica identificável" e o plano de Modelagem de W5-W6 foi ajustado em torno dela — três Mitigações nominais foram registradas no `PLANEJAMENTO.md`, o GATE MARCO 1 foi expandido para dois critérios, e a análise estratificada mês-a-mês foi antecipada de W7 para W5. A investigação dedicada de W5 (`exploracao_w5_obs_pendentes.py`, resolvendo a Observação 2.9 pendente em `observacoes_importantes.md`) refinou substancialmente essa diagnose, e o *re-framing* resultante muda a interpretação operacional do que se espera do modelo em junho.

Quatro hipóteses operacionais haviam sido catalogadas inicialmente em paralelo à Observação 2.9, cada uma com assinatura empírica esperada distinta para permitir teste de falsificação:

- **H_recapagem em massa** (operação de pneus afetando termorregulação dos freios) — esperaria distribuição espalhada por múltiplas TAGs com *onset* sincronizado entre equipamentos.
- **H_sazonal térmica** (início de inverno em Itabira) — esperaria rampa gradual ao longo de junho e distribuída entre TAGs.
- **H_sensor em lote** (troca ou recalibração de sensores em escala) — esperaria poucas TAGs específicas com *onset* abrupto em uma data única.
- **H_localizada** (falha em um ou dois equipamentos individuais, análoga ao CA65789 identificado em W3) — esperaria concentração extrema do volume em uma única TAG.

A decomposição empírica dos 4.278 eventos `Right Front Brake Temperature - Active` de junho por TAG, dia, frota e operador forneceu evidência inequívoca:

| Decomposição | Resultado empírico |
|---|---|
| TAGs afetadas em junho | 9 das 30 presentes no *split* de teste |
| **Concentração na TAG CA65926 (793-D 4S)** | **98,53% dos 4.278 eventos** |
| Top 3 TAGs concentram | 99,8% do volume |
| *Onset* (primeiros 5 dias de junho, 01-05) | 0% do volume |
| Período intermediário (06-25) | 41,1% do volume |
| *Onset* (últimos 5 dias, 26-30) | 58,9% do volume; picos nos dias 26 (458 eventos), 27 (518) e 30 (1.087) |
| `Right Front Brake Temperature - Active` no CA65926 mês a mês | 0 / 3 / 6 / 0 / 0 / **4.215** — salto de aproximadamente **700 vezes** sobre o *baseline* do próprio equipamento |
| Histórico completo do CA65926 no semestre | 13.661 eventos, 4.923 DGs; **438 DGs em março já com taxa de DG de 20,28%** via outros alarmes |

A confirmação é unívoca: das quatro hipóteses, apenas **H_localizada se sustenta**. As três outras seriam acompanhadas de distribuição mais ampla entre TAGs ou de *onset* gradual; nenhuma das duas características está presente. A interpretação mais provável é falha mecânica progressiva do sistema de freio dianteiro direito do CA65926 — possivelmente acompanhada ou causada por sensor com defeito específico do equipamento. O CA65926 já dava sinais em março (taxa de DG de 20,28% via outros alarmes — sem sequer envolver o sensor de freio que explodiu posteriormente), e a manifestação no sensor de freio dianteiro direito ocorreu três meses depois, com escalada de volume nos últimos cinco dias do mês de teste. A Hipótese H3.3 (originalmente "o pico em junho foi evento operacional pontual genérico") fica formalmente refutada com reinterpretação em `hipoteses_eda.md`.

A consequência analítica do *re-framing* é forte e reorganiza a narrativa de risco. O **Risco 3.2** havia sido enquadrado como "modelo treinado em regime de *baseline* pode degradar diante de regime nunca visto"; com o *re-framing*, a interpretação correta é "**modelo precisa antecipar a falha progressiva de um equipamento específico com histórico extenso no treino**". O CA65926 está presente em todos os meses de janeiro a maio, com 6.578 eventos e 625 DGs disponíveis para o modelo aprender o padrão de deterioração — não é um equipamento estatisticamente invisível no treino. A pergunta operacional muda de "como anteciparemos uma anomalia que nunca vimos?" para "como anteciparemos a falha de um equipamento que dava sinais?" — significativamente mais respondável dentro do paradigma supervisionado adotado.

A consequência prática para a fase de Modelagem é que a **Família 4 regimal**, em particular a *feature* `razao_alarme_7d_vs_30d_anterior`, ganha protagonismo central na narrativa esperada. Essa *feature* foi desenhada na fase de *Feature Engineering* (W4) precisamente para detectar saltos do tipo "alarme X dispara muito mais que o *baseline* histórico do próprio equipamento" — exatamente o padrão observado no CA65926 em junho (de 0-6 eventos por mês para 4.215). A análise SHAP global do LightGBM v2 em W6 deve confirmar essa hipótese empiricamente. Caso `razao_alarme_7d_vs_30d_anterior` não apareça no topo do *ranking* de importância, a interpretação correta será que a *feature* não capturou o sinal pretendido e o modelo está aprendendo o padrão de deterioração via *proxies* menos diretas — provavelmente `count_critico_24h` (Família 1) e `horas_desde_ultimo_DG` (Família 2). Em qualquer dos cenários, o diagnóstico será claro: o modelo está olhando para o histórico do próprio equipamento, não para sinais regimais difusos da frota.

A consequência quantitativa para W7 é que **82,2% de todos os DGs do conjunto de teste (4.298 de 5.226) vêm exclusivamente do CA65926**. A análise estratificada de erro em W7 deve **obrigatoriamente reportar métricas com e sem o CA65926** isoladamente — sem essa separação, o desempenho agregado mistura duas situações com implicações operacionais radicalmente diferentes: "modelo soube antecipar deterioração de um equipamento conhecido" e "modelo manteve *performance* estável nos demais 29 equipamentos do teste". A leitura agregada esconde qual dessas duas histórias é a verdadeira, e portanto qual mensagem o relatório transmite à Vale. A tabela `relatorio/tabelas/obs29_rfb_junho_decomposicao.csv` (34 linhas em formato *long* com as dimensões `dia`, `TAG` e `frota` consolidadas) materializa a decomposição e vira material direto para as seções de Limitações (CM 6.2) e Trabalhos Futuros (CM 6.3) do relatório final.

O achado reforça também o **padrão emergente de equipamentos individuais problemáticos** que vinha se consolidando ao longo das semanas anteriores. O CA65926 agora aparece em **dois contextos independentes** — outlier por equipamento na análise Q4 da W2 (taxa de DG por equipamento muito acima da mediana) e dominante absoluto da anomalia RFB de W5 (98,53% do volume do alarme). O CA65789, identificado em W3, exibiu um padrão análogo em outra dimensão (100% das 340 sobreposições temporais de ciclos de apontamento, todas concentradas em janeiro de 2025). A EDA agregada por frota, por mês ou por criticidade esconde sistematicamente esses indivíduos problemáticos; **análise estratificada por TAG vira obrigatória em W7** (Qualidade C do edital — análise por equipamento). Os dois casos juntos compõem candidato direto a **CM 6.1 (Insights Não Óbvios)** do relatório final, com a narrativa convergente: a Vale tem pelo menos dois equipamentos com comportamento sistematicamente anômalo que só emergem quando a análise quebra a média da frota — informação operacional concreta que a política atual de manutenção preventiva (inferida como baseada em médias por frota) não captura. Resulta em **CM 6.3 (Recomendação Operacional)** com duas ações claras e materializáveis: (i) auditoria manual do sistema de freio dianteiro direito do CA65926, especialmente após os picos de 26-30 de junho — possível falha mecânica progressiva ou sensor com defeito específico; (ii) revisão da política de manutenção preventiva para incluir auditoria estratificada por equipamento individual, não apenas por frota agregada, com gatilhos baseados em métricas de deterioração específicas por TAG.

---

---

## Metodologia — Parte 3: Modelagem

A fase de Modelagem segue o protocolo de avaliação temporal definido em W4 (Figura 8) e usa como *input* canônico a matriz `v3.parquet` (544.885 × 58 colunas, com *encoding* limpo após o *fix* do *leakage* subtil documentado em W5 e com a Família 1 expandida para 5 janelas — ver `controle_alteracoes.md` entradas de 2026-05-22 e 2026-05-23, e `notas_metodologicas.md` Seção 2). O CM 4.3 do Estudo Guiado exige dois modelos bem feitos com seus respectivos pré-processamentos; este trabalho adota três:

1. **Baseline heurístico** (referência operacional; `07_baseline.py`).
2. **LightGBM principal** (modelo de classificação supervisionada; `08_lightgbm.py`, em versão v1 com parâmetros *default* em W5 e versão v2 com Optuna em W6).
3. **Modelo de Sobrevivência Weibull AFT** (segunda leitura do problema, com tratamento rigoroso de *censoring*; `09_sobrevivencia.py`, em W6).

Adicionalmente, em W6 será treinado um **Isolation Forest diagnóstico** sobre o mesmo *dataset* sem usar o rótulo `Is_Dont_Go` — não é modelo de classificação, mas teste empírico único do Risco 3.3 (viés do *label* CMA). Sua discussão será apresentada em seção dedicada.

### Baseline heurístico (`07_baseline.py`)

A heurística canônica é deliberadamente simples: `DG_predito = 1` se houve evento `Critico` nas últimas 4 horas do mesmo equipamento — formalizada como `predito = (count_critico_4h ≥ threshold).cast(Int8)`. Para AUC-PR (que não depende de threshold), usa-se `count_critico_4h` como *score* contínuo. Foco em `target_4h` apenas; análise de sensibilidade entre horizontes (T2/T4/T8) migra para o LightGBM. Quatro thresholds (1, 2, 3, 5) mapeiam a curva operacional. Estratificação val/test obrigatória (Mitigação 3).

> 📘 **Cálculo, decisões de escopo e algoritmo:** ver [`notas_metodologicas.md` Seção 7](notas_metodologicas.md). **Script:** `Projeto/codigo/07_baseline.py`. **Saída:** `relatorio/tabelas/baseline_metricas.csv` (8 linhas: 4 thresholds × 2 splits).

#### Resultados

| Métrica | VAL (mai) | TEST (jun) | Razão test/val |
|---|---:|---:|---:|
| Eventos | 78.825 | 71.089 | — |
| Positivos `target_4h` | 14.481 (18,37%) | 12.038 (16,93%) | — |
| **AUC-PR** | **0,2397** | **0,5803** | **2,42×** |
| Lift sobre random AP | 1,30× | **3,43×** | — |

Precision / Recall / F1 por *threshold*:

| Threshold | VAL P / R / F1 | TEST P / R / F1 |
|---:|---:|---:|
| ≥ 1 | 0,2556 / 0,4025 / 0,3127 | 0,3436 / **0,6976** / 0,4604 |
| ≥ 2 | 0,2887 / 0,2740 / 0,2812 | 0,4060 / 0,5969 / 0,4833 |
| ≥ 3 | 0,3152 / 0,2226 / 0,2609 | 0,4651 / 0,5510 / 0,5044 |
| ≥ 5 | 0,3630 / 0,1654 / 0,2273 | **0,5905** / 0,4714 / **0,5243** |

#### Achado central — contra-intuitivo

**O baseline performa 2,42× melhor em teste do que em validação** — exatamente o **oposto** do que a Figura 8 do W4 sugeria. O drift mai→jun foi quantificado como aumento da taxa de DG (1,62% → 7,35%), e a leitura prévia era "teste é mais difícil". Mas:

- **98,53%** dos eventos RFB-Active de jun e **82,2%** dos DGs de jun vêm do CA65926 (Obs 2.9, W5).
- O CA65926 disparou Críticos massivamente — 0-6 eventos RFB/mês (jan-mai) → 4.215 em jun (salto de ~700×).
- Quando um equipamento dispara Críticos com essa intensidade pré-DG, a *feature* `count_critico_4h` fica alta consistentemente — a heurística "conte Críticos recentes" tem assinatura clara para detectar.

**Em maio, regime distribuído:** taxa de DG 1,62% (mais baixa do semestre), DGs espalhados entre equipamentos, sem alvo único. A heurística performa apenas marginalmente acima de chance (lift 1,30×).

**A consequência metodológica é importante:** o "drift mai→jun" não é uniformemente "teste mais difícil" — é **mudança qualitativa da natureza do problema**. Em jun, predizer DG vira "antecipar CA65926 em deterioração" (assinatura mecânica clara). Em mai, predizer DG vira regime distribuído sem alvo claro (genuinamente mais difícil para qualquer modelo).

#### Implicações para LightGBM e re-calibração do GATE MARCO 1

O resultado força revisão do GATE MARCO 1, originalmente formulado assumindo que test seria mais difícil. Re-calibração formal em `controle_alteracoes.md` (2026-05-22):

1. **Teto alto em test (AUC-PR baseline 0,5803):** LightGBM precisa atingir **≥ 0,6303** (baseline + 5pp) em jun para justificar complexidade adicional.
2. **Espaço amplo em val (AUC-PR baseline 0,2397):** LightGBM com 35 *features* deve facilmente superar **≥ 0,2897** (baseline + 5pp).
3. **Risco de super-otimização para mai:** critério dual (A *e* B simultâneos) protege contra modelo que ganha em val e perde em test.
4. **SHAP em W6 vira teste central:** se `count_critico_4h` dominar o ranking sozinha, o LightGBM está reproduzindo o baseline; o valor agregado precisa vir de outras *features*, especialmente Família 4 regimal.

#### Candidato a CM 6.1 (Insight Não Óbvio)

A história: *"uma heurística simples pode parecer melhor que um modelo complexo num regime específico se esse regime tem assinatura mecânica clara; comparação rigorosa contra baseline revela quando o ganho de complexidade vale"*. Narrativa convergente com Obs 2.9 (drift localizado), H7.1 (equipamentos individuais problemáticos) e Fig 8 (drift mensal): a EDA agregada esconde heterogeneidades; quando elas emergem, modelos respondem de formas surpreendentes que exigem interpretação cuidadosa.

---

### LightGBM v1 (`08_lightgbm.py`) — modelo principal de classificação

O modelo principal de classificação é o **LightGBM** (gradient boosting com *histogram-based* tree learning). A versão 1 usa parâmetros *default* (100 iterações, `learning_rate=0,1`, `num_leaves=31`, `random_state=42`) — sem Optuna nem *early stopping*. Serve como referência simples para o GATE MARCO 1 e como ponto de partida para o tuning de v2 em W6. Matriz de entrada: `v3.parquet` (35 *features*; 19 colunas originais excluídas para evitar *label leakage*). Categóricas `turno` e `estado_pre_evento` são passadas como `pd.Categorical` para que o LightGBM aplique *split handling* otimizado.

O *script* treina **5 variantes** com parâmetros idênticos, diferindo apenas em *target* ou `scale_pos_weight` — cada variante responde a uma pergunta analítica distinta consolidada nas semanas anteriores.

> 📘 **Configuração detalhada, espaço de busca, justificativa das 5 variantes e formato das saídas:** ver [`notas_metodologicas.md` Seção 8](notas_metodologicas.md). **Script:** `Projeto/codigo/08_lightgbm.py` (~17,5 s). **Saídas:** 5 modelos em `Projeto/modelos/lightgbm_v1_{A,B,C,T2,T8}.txt` + 4 tabelas em `relatorio/tabelas/` (`lightgbm_v1_metricas.csv`, `lightgbm_v1_vs_baseline.csv`, `comparacao_horizontes_lightgbm.csv`, `gate_marco_1.csv`).

#### Resultados consolidados

| Variante | Target | `scale_pos_weight` | AUC-PR val (mai) | AUC-PR test (jun) |
|---|---|---:|---:|---:|
| **A** (canônica) | `target_4h` | 1,972 (taxa treino) | **0,7523** | **0,8566** |
| **B** (Mitigação 2) | `target_4h` | 4,653 (taxa val+test, *peeking*) | 0,7350 | 0,8517 |
| **C** (Obs 2.7) | `target_4h_producao` | 2,096 | 0,7012 | 0,8533 |
| **T2** (Profundidade 1) | `target_2h` | 2,360 | 0,7729 | 0,8378 |
| **T8** (Profundidade 1) | `target_8h` | 1,585 | 0,7421 | 0,8211 |

#### GATE MARCO 1: PASS

Variante A atinge **AUC-PR 0,7523 em val** (≥ 0,2897 do critério A, folga +46,3pp) e **0,8566 em test** (≥ 0,6303 do critério B, folga +22,6pp). **Verdict: PASS** — avança para W6. Sobre o baseline: +51,3pp em val, +27,6pp em test — folga substancial justifica empiricamente a complexidade do modelo. A análise SHAP em W6 fica como teste de qualidade obrigatório: se `count_critico_4h` dominar isoladamente, parte do desempenho é apenas "réplica sofisticada do baseline"; esperamos especialmente a Família 4 regimal no topo do ranking.

#### 3 conclusões analíticas

**Mitigação 2 descartada empiricamente.** Variante B perde para A em ambos os splits (B−A = −1,73pp val, −0,50pp test). O *peeking* foi insuficiente para inflar B além de A — `scale_pos_weight` calibrado para taxa de produção via val+test **não tem valor preditivo neste dataset**. Para W6: restringir busca Optuna a `scale_pos_weight ∈ [0,5; 3,0]`. Vira material de CM 6.2 (hipótese refutada com rigor).

**DGs em Manutenção contêm sinal, não ruído** (Obs 2.7 confirmada). Variante C perde para A em ambos os splits (C−A = −5,11pp val, −0,33pp test). Filtrar os 1.460 DGs em estado Manutenção **remove sinal preditivo legítimo** — confirma reinterpretação da H5.1 já documentada em `hipoteses_eda.md`. Para W6: manter `target_4h` original; **não treinar variante `Is_Dont_Go_producao`** em v2.

**Profundidade 1 — T8 é o pior, T2/T4 indistinguíveis.** Ranking val: T2 (0,7729) > T4 (0,7523) > T8 (0,7421). Ranking test: T4 (0,8566) > T2 (0,8378) > T8 (0,8211). O **ranking entre T2 e T4 inverte entre val e test** — diferenças (~1,9pp) estão na faixa de ruído amostral para LightGBM single-fold. **T8 é robustamente o pior** (consistente em ambos os splits, magnitude maior). Afirmação honesta: **T2 e T4 são estatisticamente indistinguíveis** com esta configuração; a escolha operacional de 4h (CM 1.2) é **empiricamente compatível** com os melhores resultados, mas não singularmente vencedora. Para W6: manter T4 canônico, tunar apenas o modelo T4. Em W7, repetir com TimeSeriesSplit CV se sobrar tempo (variância robusta sobre os 3 horizontes).

> 📘 **Análise estatística completa da significância das diferenças T2 vs T4 (variabilidade esperada de AUC-PR, fontes de ruído amostral, recomendação metodológica):** ver `notas_metodologicas.md` Seção 8 (subseção "Profundidade 1 — análise de significância").

Os 3 achados convergem para candidato CM 6.1 (Insights Não Óbvios): hipóteses metodológicas testadas com rigor e refutadas/refinadas com dados; comparações honestas que distinguem ganho real de ruído ou viés de regime.

---

### LightGBM v2 (`08b_lightgbm_v2.py`) — Optuna + TimeSeriesSplit CV + determinismo

A versão 2 é o **modelo canônico para o relatório final**. Refina o v1 por três mudanças simultâneas:

1. **Optuna com 50 *trials*** sobre 7 hiperparâmetros (espaço refinado pela conclusão da Mitigação 2 — `scale_pos_weight ∈ [0,5; 3,0]`).
2. **TimeSeriesSplit CV de 4 *folds* expandidos** (Mitigação 1): `jan→fev`, `jan-fev→mar`, `jan-fev-mar→abr`, `jan-abr→mai`. Métrica de *tuning*: AUC-PR média dos 4 *folds*. Teste (jun) **nunca** entra na CV — só na avaliação final.
3. **Determinismo estrito** via `deterministic=True` + `force_col_wise=True`: dois runs produzem AUC-PR *bit-exact* até a última casa decimal — requisito para auditoria do trabalho.

> 📘 **Espaço de busca completo dos 7 hiperparâmetros, configuração do Optuna TPE Sampler, estrutura dos 4 *folds* e justificativa do determinismo:** ver [`notas_metodologicas.md` Seção 9](notas_metodologicas.md). **Script:** `Projeto/codigo/08b_lightgbm_v2.py` (~28,7 min — Optuna 28,5 min + treino final 8 s). **Saídas:** modelo `Projeto/modelos/lightgbm_v2.txt` + study completo `Projeto/modelos/optuna_study_v2.pkl` (auditoria) + 3 tabelas em `relatorio/tabelas/` (`lightgbm_v2_metricas.csv`, `lightgbm_v2_hiperparametros.csv`, `optuna_trials.csv` com os 50 *trials*).

#### Resultados

| Métrica | Valor | Comparação |
|---|---:|---|
| AUC-PR train | 0,9658 | gap de 0,19 vs val → overfitting moderado |
| AUC-PR val (mai) | **0,7801** | **+2,78pp vs v1 A** (+54,0pp vs baseline) |
| AUC-PR test (jun) | **0,8618** | **+0,52pp vs v1 A** (+28,2pp vs baseline) |
| AUC-PR CV média (4 folds) | 0,8834 | métrica usada pelo Optuna |
| Melhor *trial* | #34 de 50 | — |
| Tempo total | 28,7 min | Optuna 28,5 min + treino final 8 s |

**Hiperparâmetros encontrados pelo Optuna (vs default do v1):**

| Hiperparâmetro | v1 (default) | v2 (best) | Direção |
|---|---:|---:|---|
| `n_estimators` | 100 | 199 | +99% (mais árvores) |
| `learning_rate` | 0,1 | 0,013 | **−87% (muito mais lento)** |
| `num_leaves` | 31 | 61 | +97% (árvores mais complexas) |
| `min_child_samples` | 20 | 60 | +200% (regularização) |
| `scale_pos_weight` | 1,972 | **0,513** | **−74% (downweight de positivos!)** |
| `lambda_l1` | 0 | 0,32 | regularização L1 |
| `lambda_l2` | 0 | 1,82 | regularização L2 |

#### Achado importante: Optuna escolheu `scale_pos_weight = 0,513`

Optuna selecionou *downweight* de positivos (`scale_pos_weight ≈ 0,5`), **menor** que o valor "neutro" calculado pela fórmula clássica `(1-taxa)/taxa = 1,97` do v1 A. Isso **reforça a conclusão empírica da Mitigação 2** (W5): pesar positivos para cima não ajuda — o ótimo está **abaixo** do que sairia da heurística clássica. Provavelmente porque os positivos compartilham assinatura mecânica forte do CA65926 em test (Obs 2.9), tornando-os "fáceis" e exigindo menos peso explícito. **A Mitigação 2 estava propondo a direção exatamente oposta da ótima** — a investigação rigorosa em W5 evitou um caminho que teria piorado o modelo.

#### GATE MARCO 1 re-confirmado em v2

Critério A (val ≥ 0,2897): **0,7801 ✓** (folga +49,0pp).
Critério B (test ≥ 0,6303): **0,8618 ✓** (folga +23,1pp).

**v2 é o modelo canônico** para o relatório final — combina tuning rigoroso, validação cruzada honesta (sem *test set peeking*) e reprodutibilidade *bit-exact*. **v1 fica preservado como referência metodológica** (efeito comparativo "default vs tunado" + diagnóstico do peeking de Mitigação 2). A análise SHAP em W6 será feita sobre v2.

---

*(Próximas seções a desenvolver em W6-W8: Análise SHAP global + estratificada sobre v2, modelo de sobrevivência Weibull AFT + Isolation Forest diagnóstico (W6), Avaliação e Resultados estratificada (W7), Conclusão (W8).)*

---

## Anexo A — Reprodutibilidade

Todo o pipeline analítico deste estudo é reproduzível em qualquer máquina compatível (Windows / Linux / macOS) via os passos abaixo. O detalhamento das decisões metodológicas tomadas em cada etapa está em `Projeto/relatorio/controle_alteracoes.md`; o cronograma e os resultados das investigações ad-hoc estão em `PLANEJAMENTO.md`; as hipóteses analíticas levantadas e seu status atual estão em `Projeto/relatorio/hipoteses_eda.md`.

### A.1. Setup inicial

```powershell
# 1. Instalar uv (gerenciador de pacotes Python)
#    https://docs.astral.sh/uv/getting-started/installation/

# 2. Clonar o repositório
git clone <repo_url>
cd AnaliseDadosVale

# 3. Sincronizar dependências (cria .venv com as versões exatas de uv.lock)
uv sync

# 4. Validar imports
uv run python -c "import polars, pandas, lightgbm, shap, lifelines, optuna; print('OK')"
```

A versão do Python (3.13) está fixada em `.python-version`. Todas as dependências, com versões exatas, estão em `uv.lock`. Instruções completas em `README.md`.

### A.2. Pipeline analítico — scripts e ordem de execução

| # | Script | Semana | Status | Saída(s) principal(is) |
|---:|---|---|---|---|
| 1 | `Projeto/codigo/01_ingestao.py` | W1 | ✅ | `dados/intermediarios/telemetria_consolidado.parquet` (37.164.054 linhas, ~421 MB — consolidação dos 6 parquets mensais brutos) |
| 2 | `Projeto/codigo/02_correcao_tipos.py` | W1 | ✅ | `dados/intermediarios/telemetria_tipada.parquet` — conversão de `Inicio_Turno`/`Fim_Turno` (String → Datetime μs) e `Valor` (String com vírgula decimal BR + literais `"NULL"` → Float64 com nulls reais). 237.443 nulls preservados (0,64%). |
| 3 | `Projeto/codigo/03_limpeza.py` | W1 inspeção + W3 cleaning | ✅ | **W1 (etapas 1-5):** normalização de Criticidade (5 variantes incluindo encoding parcial `??` → 3 categorias canônicas ASCII), dedup, frequência média, estatísticas descritivas (CM 2.1). **W3 (extensão 17/05, etapas 6-12):** filtro `Criticidade=Informacional` (98,53% do volume, zero DGs perdidos), outliers `Valor`, missing values por coluna, `Inicio > Fim`, sobreposições temporais (340 flagadas, todas concentradas no CA65789), persistência + `controle_alteracoes.csv` (CM 3.1). Saídas: `dados/intermediarios/telemetria_limpa.parquet` (7 MB, 544.885 linhas — pós-filtro) + `dados/intermediarios/apontamentos_limpo.parquet` (6,3 MB, com flag `is_sobreposicao`) + 4 artefatos em `relatorio/tabelas/` |
| 4 | `Projeto/codigo/04_eda.py` | W2 | ✅ | 7 figuras em `relatorio/figuras/` (`fig02_distribuicao_temporal_apontamentos.png`, `fig03_tipo_x_criticidade.png`, `fig04_serie_temporal_dgs.png`, `fig05_heatmap_correlacao.png`, `fig06_heatmap_hora_dia.png`, `figExB_pareto_alarmes.png`, `figExG_pareto_tags.png`) + `relatorio/tabelas/dgs_por_frota_tipo_classe.csv` (tabela Q4 via `join_asof` temporal, 100% dos 19.962 DGs com match de apontamento). Fig 1 (diagrama do fluxo operacional) é desenhada manualmente em draw.io, fora deste *script*. |
| 5 | `Projeto/codigo/exploracao_w2_obs.py` | W2 | ✅ | Análises ad-hoc impressas no terminal — investigações das observações 2.1 (top 5 alarmes / 19 alarmes com ≥1 DG), 2.2 (validação `Informacional`=0 DGs no semestre), 2.5 (salto Não-Crítico 20%→48%), 2.6 (3 regimes temporais com 2 anomalias) e 2.7 (12,65% DGs em Manutenção — H1 / H2 / H3 testadas) |
| 6 | `Projeto/codigo/extrai_eventos_muito_alto.py` | W2 | ✅ | `relatorio/tabelas/eventos_muito_alto.csv` (CM 1.1 obrigatório, 82 regras CMA com nível "Muito Alto"; normalização de 6 registros com capitalização inconsistente `"Muito alto"` → `"Muito Alto"`) |
| 7 | `Projeto/codigo/exploracao_w3_sobreposicoes.py` | W3 | ✅ | Investigação das 340 sobreposições de ciclo flagadas pelo `03_limpeza.py` etapa 10 — decomposição por Frota / TAG / Tipo / Classe / mês identifica **bug pontual no CA65789** (100% das sobreposições, 90% concentradas em jan/2025, 35% em estado `Hibernando`); resultados impressos no terminal, conclusão em PLANEJAMENTO.md → W3 Observações + hipótese H1.4 refutada com reinterpretação em `hipoteses_eda.md` |
| 8 | `Projeto/codigo/exploracao_w4_ca65924.py` | W4 | ✅ | Validação empírica de H5.2 / Obs 2.3 — comparação do caso paradigma CA65924 (`desenvolver_dontgo.xlsx`) com 3 DGs aleatórios (`random.seed=42`). Saída: `relatorio/figuras/figExC_ca65924_cadeia.png` (Fig Extra C). Métricas: razão `u30/p90` e densidade relativa por painel. **Veredito em duas camadas:** padrão *sharp* universal refutado (1 de 4 painéis confirma); padrão de densificação gradual compatível com 4 de 4. Sub-hipótese de acúmulo de criticidade (Obs 2.11) gerada para validação via SHAP em W6 |
| 9 | `Projeto/codigo/05_features.py` | W3 (básicas) + W4 (avançadas + target) + W5 (expansão Família 1) | ✅ completo | Pipeline em 11 etapas que constrói **7 famílias de features (35 colunas) + 3 *targets* multi-janela**: Família 0 — básicas (5: `hora_dia`, `dia_semana`, `turno`, `mes`, `valor_disponivel`); Família 1 — rolling (15: `count_{critico,nao_critico,total}_{1h,2h,4h,8h,24h}`; **janelas 2h e 8h adicionadas em W5 23/05 para alinhamento perfeito com a Profundidade 1**); Família 2 — recência (2: `horas_desde_ultimo_DG`, `horas_desde_ultimo_critico`); Família 3 — estado pré-evento (1: `estado_pre_evento` via `join_asof` t-1h); Família 4 — regimal (2: `razao_alarme_7d_vs_30d_anterior`, `razao_severidade_14d_vs_60d`); Família 5 — operador (2: `taxa_DG_operador_30d`, `n_bypasses_operador_7d`); Família 6 — regra de negócio (1: `qtd_alarmes_nivel_muito_alto_360min`); Família 7 — encoding categórico (7: `tag_freq`, `frota_793D_2S/3S/4S/5S`, `tipo_caminhao`, `operador_freq`); *targets* `target_2h`, `target_4h` (principal), `target_8h`. Saídas: `dados/features/v1.parquet` (5 básicas, 6,9 MB) + `dados/features/v2_parcial.parquet` (25, 21,6 MB) + `dados/features/v2.parquet` (35 + 3 *targets*, 24,4 MB, 57 cols) + `relatorio/tabelas/documentacao_features.csv` (CM 3.2, 35 entradas) + `relatorio/tabelas/sensibilidade_janela.csv` (descritiva, 18 entradas). Tempo de execução total: ~7s |
| 10 | `Projeto/codigo/06_split.py` | W4 | ✅ | *Split* temporal *walk-forward* com cortes nos limites de mês (`< 2025-05-01` para treino jan-abr, `< 2025-06-01` para validação mai, `>=` para teste jun). Saídas: `dados/features/v2_split.parquet` (544.885 × 58 colunas, 16,3 MB — antecessor de `v3.parquet`) + `relatorio/tabelas/split_temporal.csv` (CM 4.1, 3 entradas) + `relatorio/figuras/fig07_janela_predicao.png` (diagrama do *target*) + `relatorio/figuras/fig08_split_temporal.png` (2 painéis: distribuição mensal por *split* + *drift* mês-a-mês). Tempo: 3,1s |
| 11 | `Projeto/codigo/06b_fix_encoding_leakage.py` | W5 | ✅ | *Fix* do *leakage* subtil de *frequency encoding* da Família 7. Recomputa `tag_freq` e `operador_freq` sobre o *split* de treino apenas (394.971 eventos, antes vinha do *dataset* global em `05_features.py`) e propaga para val/teste; categorias unknown no treino (2 TAGs: `CA65791`, `CA65916`; 13 operadores) recebem `freq = 0` por convenção (Opção C-1 — análise teórica + empírica em `notas_metodologicas.md` Seção 2 mostra que feature binária `is_unknown` seria inerte em *single-fold* de W5). Asserções defensivas validam 12 eventos com `tag_freq = 0` em val e 1.394 em test; 154 e 418 com `operador_freq = 0` em val/test. Saída: `dados/features/v3.parquet` (544.885 × 58 colunas, 16,3 MB — **input canônico de toda a Modelagem em W5+**). Diff médio pós-fix: `tag_freq` +1,4%, `operador_freq` -1,0% (confirma que *leakage* era subtil mas presente). Tempo: 1,5s |
| 12 | `Projeto/codigo/exploracao_w5_obs_pendentes.py` | W5 | ✅ | Resolução das duas observações pendentes do `observacoes_importantes.md` antes de iniciar a modelagem: **Obs 2.4** (operador OP_067 do caso paradigma CA65924 tem taxa anormal? — Q3 do edital) e **Obs 2.9** (causa da explosão de RFB em junho/2025 — recapagem, sazonalidade, troca de sensor em lote, ou falha localizada?). **Veredito 2.4:** OP_067 não é outlier (rank #76 de 394, taxa 6,338% vs baseline 3,664%; 152 operadores em faixa comparável); resposta empírica a Q3 é "operador correlaciona com DG de forma difusa". **Veredito 2.9:** anomalia é **falha mecânica progressiva localizada do CA65926** — 98,53% dos 4.278 eventos RFB-Active de jun vêm exclusivamente desse equipamento; 82,2% dos DGs de jun (4.298 de 5.226) também. Saídas: `relatorio/tabelas/obs24_taxa_dg_por_operador.csv` (394 linhas) + `relatorio/tabelas/obs29_rfb_junho_decomposicao.csv` (34 linhas long-format). Re-framing forte do Risco 3.2 e formalização da H7.1 (equipamentos individuais problemáticos). Tempo: 0,4s |
| 13 | `Projeto/codigo/07_baseline.py` | W5 | ✅ | Modelo baseline heurístico: `DG_predito = 1 se count_critico_4h ≥ threshold` aplicado a `target_4h` (canônica do CM 1.2). Score raw para AUC-PR: `count_critico_4h` (alinhamento perfeito ao horizonte do *target*). Thresholds binários para P/R/F1: 1, 2, 3, 5. Estratificação obrigatória mai vs jun (Mitigação 3). **Resultado contra-intuitivo:** AUC-PR test (jun) = 0,5803 é **2,42× maior** que AUC-PR val (mai) = 0,2397 — *recall* de 70% em test com *threshold* = 1 mesmo sem modelo de ML. Explicação mecânica: 82,2% dos DGs de jun vêm do CA65926 em deterioração progressiva (Obs 2.9), criando assinatura clara para a regra simples; mai é regime distribuído sem alvo único. Forçou re-calibração do GATE MARCO 1 (registrada em `controle_alteracoes.md` 2026-05-22). Saída: `relatorio/tabelas/baseline_metricas.csv` (8 linhas: 4 thresholds × 2 splits, com TP/FP/FN/TN, P/R/F1, AUC-PR, Random AP). Tempo: 0,4s |
| 14 | `Projeto/codigo/08_lightgbm.py` | W5 | ✅ | LightGBM v1 com 5 variantes (A/B/C/T2/T8) e parâmetros *default* sobre `v3.parquet`. Variante A canônica para GATE MARCO 1. **Resultados:** A val=0,7523 / test=0,8566 (GATE PASS, +51,3pp / +27,6pp vs baseline). Mitigação 2 (B) e Obs 2.7 (C) **empiricamente descartadas**. Profundidade 1 (T2/T4/T8): T8 pior, T2 vs T4 indistinguíveis (ranking inverte val↔test, magnitude na faixa de ruído). Saídas: 5 modelos em `Projeto/modelos/lightgbm_v1_*.txt` + 4 tabelas (`lightgbm_v1_metricas.csv`, `lightgbm_v1_vs_baseline.csv`, `comparacao_horizontes_lightgbm.csv`, `gate_marco_1.csv`). Tempo: 17,5s. Ver `notas_metodologicas.md` Seção 8. |
| 15 | `Projeto/codigo/08b_lightgbm_v2.py` | W6 | ✅ | **LightGBM v2 — modelo canônico do relatório.** Optuna (50 trials, TPE seed=42) + TimeSeriesSplit CV de 4 folds expandidos (Mitigação 1) + determinismo estrito (`deterministic=True` + `force_col_wise=True`). Espaço de busca: 7 hiperparâmetros (`scale_pos_weight ∈ [0,5; 3,0]` refinado após refutação da Mitigação 2). **Resultados:** AUC-PR train=0,9658 / val=0,7801 / test=0,8618 (best CV=0,8834 trial #34). Ganho sobre v1 A: val +2,78pp, test +0,52pp. **GATE MARCO 1 re-confirmado PASS.** Optuna escolheu `scale_pos_weight=0,513` — contradiz a direção da Mitigação 2 (que propunha cima para 4,65). Saídas: `Projeto/modelos/lightgbm_v2.txt` + `optuna_study_v2.pkl` + 3 tabelas (`lightgbm_v2_metricas.csv`, `lightgbm_v2_hiperparametros.csv`, `optuna_trials.csv`). Tempo: 28,7 min. Ver `notas_metodologicas.md` Seção 9. |
| 16 | `Projeto/codigo/09_sobrevivencia.py` | W6 | 🔄 planejado | Modelo de Sobrevivência (Weibull AFT principal, *fallback* Cox PH se Weibull não convergir) com biblioteca `lifelines`. Trata o *censoring* (102.602 eventos sem DG futuro observado) rigorosamente como dado adicional, oferecendo segunda leitura do problema independente de *threshold* de classificação. Saídas: `modelos/sobrevivencia.joblib` + tabela de *hazard ratios* + Fig Extra A (curva Kaplan-Meier por estado pré-evento). |
| 17 | `Projeto/codigo/11_isolation_forest.py` | W6 | 🔄 planejado | Isolation Forest diagnóstico — treinado sobre o mesmo dataset **sem usar `Is_Dont_Go`**; mede a sobreposição entre DGs reais e *score* de anomalia. Teste empírico único do Risco 3.3 (viés do *label* CMA). Saídas: `modelos/isolation_forest.joblib` + `relatorio/tabelas/if_diagnostico.csv`. |
| 18 | `Projeto/codigo/10_evaluation.py` | W7 | 🔄 planejado | Métricas finais estratificadas (mês × frota × estado operacional × top-5 alarmes) + figuras 9-13 do relatório + análise de erro por contexto + curva *precision-recall* com limiar operacional calibrado por custo-benefício explícito. |

**Comando de execução padrão:**
```powershell
uv run python Projeto/codigo/<nome_do_script>.py
```

**Nota de numeração (reconciliada em 2026-05-17, com adição em 2026-05-22):** o plano original previa `04_features.py`, mas o slot 04 acabou ocupado por `04_eda.py` (criado em W2) porque os slots 02 e 03 já estavam em uso (`02_correcao_tipos.py` e `03_limpeza.py`, ambos criados em W1). A reconciliação adotada (Opção B) mantém `04_eda.py` no slot 04 e desloca todos os scripts subsequentes do plano em +1: `05_features.py`, `06_split.py`, `07_baseline.py`, `08_lightgbm.py`, `09_sobrevivencia.py`, `10_evaluation.py`, `11_isolation_forest.py`. Decisão registrada formalmente em `controle_alteracoes.md` (2026-05-17). **Adição posterior (2026-05-22):** o script `06b_fix_encoding_leakage.py` foi inserido entre `06_split.py` e `07_baseline.py` como pré-condição obrigatória de toda a Modelagem em W5+ (gera `v3.parquet`, *input* canônico). O sufixo `b` ao invés de novo número inteiro preserva a numeração subsequente já estabelecida e sinaliza que é um *fix* incremental sobre o *split*, não um novo passo conceitual do *pipeline*.

### A.3. Convenções de código

Todos os scripts seguem as convenções abaixo, garantindo previsibilidade e debugabilidade:

- **Resolução de caminhos:** `Path(__file__).resolve().parents[1]` define a raiz do projeto como `Projeto/`. Todos os caminhos são relativos a essa raiz — não há hardcoding absoluto.
- **Asserções defensivas em pontos críticos:** contagens de linhas esperadas, tipos de colunas pós-conversão, totais de soma após filtros, integridade de joins (ex: 100% de match no `join_asof` da tabela Q4 em W2). Falhas geram exceção explícita, não bug silencioso.
- **Logs estruturados em `[N/total]`:** cada etapa do script imprime sua progressão (ex: `[3/11] Fig 4 — Série temporal de DGs`). Facilita identificar onde ocorreu falha em scripts longos.
- **ASCII puro em código e comentários:** evita problemas de encoding em sistemas mistos (PowerShell no Windows, bash no Linux).
- **Docstring no topo de cada arquivo** explicando entrada, saída, comando de execução e referência aos artefatos gerados.

### A.4. Fluxo de dados

```
Projeto/Alterado/Base de Dados/datasets/       (dados brutos, versionados no Git)
            │
            ▼
Projeto/dados/intermediarios/*.parquet         (pós-ingestão e limpeza, gitignored)
            │
            ▼
Projeto/dados/features/*.parquet               (matriz de features, gitignored)
            │
            ▼
Projeto/modelos/*.{lgb,joblib,pkl}             (artifacts treinados, gitignored)
            │
            ▼
Projeto/relatorio/figuras/*.png                (figuras finais, versionadas)
Projeto/relatorio/tabelas/*.csv                (tabelas finais, versionadas)
Projeto/relatorio/{controle_alteracoes,
                   hipoteses_eda,
                   rascunho}.md                (documentos analíticos, versionados)
```

Arquivos `gitignored` são reproduzíveis a partir dos brutos versionados e dos scripts — não são "fonte de verdade", e por isso não pesam o repositório. O `uv.lock` garante que qualquer máquina chegará exatamente nos mesmos artefatos finais.

### A.5. Reprodução completa (do zero ao relatório final)

Após o setup (A.1), executar em sequência:

```powershell
uv run python Projeto/codigo/01_ingestao.py
uv run python Projeto/codigo/02_correcao_tipos.py
uv run python Projeto/codigo/03_limpeza.py
uv run python Projeto/codigo/04_eda.py
uv run python Projeto/codigo/exploracao_w2_obs.py
uv run python Projeto/codigo/extrai_eventos_muito_alto.py
# (W3-W7: scripts 7-13 conforme implementados)
```

Tempo total estimado de reprodução completa em hardware comparável (Intel i5 / 16GB RAM): aproximadamente 10-15 minutos para os scripts W1-W2 já implementados. Tempos de scripts futuros serão registrados conforme execução em W3-W7.
