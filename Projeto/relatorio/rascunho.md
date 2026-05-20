# Rascunho do Relatório — Programa Desenvolver 2026

Documento de escrita progressiva que vai consolidando as seções do relatório final ao longo das semanas W2→W8. Será migrado para `Desenvolver_Template.docx` em W9.

**Status atual:** seção de EDA (W2) preenchida com base nos achados consolidados em `PLANEJAMENTO.md`, `hipoteses_eda.md`, `controle_alteracoes.md` e nos artefatos gerados (figuras, tabelas). Adicionalmente, esqueleto preliminar das seções **Introdução** e **Entendimento do Negócio** (CM 1.1 + CM 1.2) — material a ser refinado em W8.

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

*(Próximas seções a desenvolver em W3-W8: Preparação dos Dados, Modelagem, Avaliação e Resultados, Conclusão.)*

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
| 1 | `Projeto/codigo/01_ingestao.py` | W1 | ✅ | `dados/intermediarios/telemetria_consolidado.parquet` (37.164.054 linhas) |
| 2 | `Projeto/codigo/02_correcao_tipos.py` | W1 | ✅ | `dados/intermediarios/telemetria_tipada.parquet` |
| 3 | `Projeto/codigo/03_limpeza.py` | W1 inspeção + W3 cleaning | ✅ | **W1:** normalização Criticidade, dedup, frequência, estatísticas (CM 2.1). **W3 (extensão 17/05):** filtro Informacional, outliers Valor, missing values, Inicio>Fim, sobreposições, controle_alteracoes.csv (CM 3.1). Saídas: `dados/intermediarios/telemetria_limpa.parquet` (7 MB, 545k linhas — pós-filtro) + `dados/intermediarios/apontamentos_limpo.parquet` (6,3 MB, com flag `is_sobreposicao`) + 4 artefatos em `relatorio/tabelas/` |
| 4 | `Projeto/codigo/04_eda.py` | W2 | ✅ | 7 figuras em `relatorio/figuras/` (fig02-fig06 + figExB + figExG) + `relatorio/tabelas/dgs_por_frota_tipo_classe.csv` |
| 5 | `Projeto/codigo/exploracao_w2_obs.py` | W2 | ✅ | Análises ad-hoc impressas no terminal — investigações das observações 2.1, 2.2, 2.5, 2.6 e 2.7 |
| 6 | `Projeto/codigo/extrai_eventos_muito_alto.py` | W2 | ✅ | `relatorio/tabelas/eventos_muito_alto.csv` (82 regras CMA com nível "Muito Alto") |
| 7 | `Projeto/codigo/exploracao_w3_sobreposicoes.py` | W3 | ✅ | Investigação das 340 sobreposições de ciclo flagadas pelo `03_limpeza.py` etapa 10 — análise por Frota/TAG/Tipo/Classe/mês identifica **bug pontual no CA65789** (H1.4); resultados impressos no terminal, conclusão em PLANEJAMENTO.md → W3 Observações |
| 8 | `Projeto/codigo/05_features.py` | W3 (básicas) / W4 (avançadas) | ✅ W3 / ✅ W4 (parcial — 4 famílias de 7) | **W3 ✅:** `dados/features/v1.parquet` (6,9 MB, 5 features básicas). **W4 ✅ (parcial):** `dados/features/v2_parcial.parquet` (19,6 MB, 19 features = 5 básicas + 14 avançadas). Famílias implementadas: rolling windows (9), recência (2), estado_pre_evento (1), regimal (2). **Pendente:** operador (taxa_DG_30d + n_bypasses_7d), regra de negócio (qtd_alarmes_muito_alto_360min), encoding categórico → `v2.parquet` final |
| 9 | `Projeto/codigo/06_split.py` | W4 | 🔄 planejado | partição temporal treino (jan-abr) / validação (mai) / teste (jun) |
| 10 | `Projeto/codigo/07_baseline.py` | W5 | 🔄 planejado | modelo baseline heurístico + métricas |
| 11 | `Projeto/codigo/08_lightgbm.py` | W5-W6 | 🔄 planejado | LightGBM v1 (defaults) + v2 (após Optuna, 50 trials) — `modelos/lightgbm_v2.lgb` |
| 12 | `Projeto/codigo/09_sobrevivencia.py` | W6 | 🔄 planejado | Weibull AFT (fallback Cox PH) — `modelos/sobrevivencia.joblib` + tabela hazard ratios + Fig Extra A (curva K-M) |
| 13 | `Projeto/codigo/11_isolation_forest.py` | W6 | 🔄 planejado | Isolation Forest diagnóstico (teste empírico do viés do label CMA) — `modelos/isolation_forest.joblib` + `relatorio/tabelas/if_diagnostico.csv` |
| 14 | `Projeto/codigo/10_evaluation.py` | W7 | 🔄 planejado | Métricas finais estratificadas + figuras 9, 10, 11, 12, 13 + análise de erro por mês/frota/estado |

**Comando de execução padrão:**
```powershell
uv run python Projeto/codigo/<nome_do_script>.py
```

**Nota de numeração (reconciliada em 2026-05-17):** o plano original previa `04_features.py`, mas o slot 04 acabou ocupado por `04_eda.py` (criado em W2) porque os slots 02 e 03 já estavam em uso (`02_correcao_tipos.py` e `03_limpeza.py`, ambos criados em W1). A reconciliação adotada (Opção B) mantém `04_eda.py` no slot 04 e desloca todos os scripts subsequentes do plano em +1: `05_features.py`, `06_split.py`, `07_baseline.py`, `08_lightgbm.py`, `09_sobrevivencia.py`, `10_evaluation.py`, `11_isolation_forest.py`. Decisão registrada formalmente em `controle_alteracoes.md` (2026-05-17).

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
