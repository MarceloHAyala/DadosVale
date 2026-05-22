# Rascunho do Relatório — Programa Desenvolver 2026

Documento de escrita progressiva que vai consolidando as seções do relatório final ao longo das semanas W2→W8. Será migrado para `Desenvolver_Template.docx` em W9.

**Status atual:** seções preenchidas até a Preparação dos Dados — **Introdução**, **Entendimento do Negócio** (CM 1.1 + CM 1.2), **Metodologia Parte 1** (Exploração de Dados — W2 EDA + Q4 + Q5) e **Metodologia Parte 2** (Preparação dos Dados — W3 limpeza + W3-W4 feature engineering completo: **7 famílias de features (29 colunas) + 3 targets multi-janela (target_2h, target_4h, target_8h) + split temporal walk-forward jan-abr / mai / jun** documentados, totalizando matriz canônica `v2_split.parquet` com 544.885 × 52 colunas; Fig 7 (janela de predição), Fig 8 (drift mensal) e Fig Extra C (refutação H5.2) integradas à narrativa). Material a ser refinado em W8. Pendentes: Modelagem (W5-W6), Avaliação (W7) e Conclusão (W8).

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

O pipeline `05_features.py` constrói **19 features documentadas** a partir do dataset limpo, organizadas em 6 famílias semânticas (1 família básica de W3 e 4 famílias avançadas de W4 parcial; 2 famílias adicionais pendentes para próxima sessão de W4).

#### Entradas e saídas

**Entradas:**
- `Projeto/dados/intermediarios/telemetria_limpa.parquet` — 544.885 eventos de telemetria (Crítico e Não-Crítico, após filtro de Informacional)
- `Projeto/dados/intermediarios/apontamentos_limpo.parquet` — 377.907 ciclos de apontamento operacional (estados Operando / Parado / Manutenção / Hibernando)

**Saídas:**
- `Projeto/dados/features/v1.parquet` — versão com apenas as 5 features básicas (compatibilidade retroativa, 6,9 MB)
- `Projeto/dados/features/v2_parcial.parquet` — 5 básicas + 14 avançadas = 19 features (19,6 MB)
- `Projeto/relatorio/tabelas/documentacao_features.csv` — uma linha por feature com nome, tipo, descrição, fórmula, motivação e semana de criação (formato CM 3.2)

#### Família 0 — Features básicas (W3, 5 colunas)

Construídas a partir de extração temporal direta sobre `Data_Evento` (`hora_dia`, `dia_semana`, `mes`) e sobre `Inicio_Turno` (`turno` ∈ {`Diurno`, `Noturno`}, derivado da hora de início do turno operacional de 12 horas), além da feature binária `valor_disponivel` que captura se o evento possui medição numérica em `Valor` ou se é alarme do tipo `Active/Inactive` sem leitura instantânea (43,58% dos eventos relevantes não têm Valor numérico — achado central da etapa 8 da limpeza). Motivações ancoradas nos achados da EDA: padrão hora × dia da semana (Pergunta 5 / Figura 6); 3 regimes temporais distintos no semestre (Observação 2.6); 43,58% de eventos sem medição como categoria potencialmente preditiva.

#### Família 1 — Rolling windows (W4, 9 colunas)

A pergunta operacional que esta família responde é: *"Quantos eventos ocorreram no MESMO equipamento nas últimas N horas?"*. Para cada evento, o script olha para trás em três janelas (1 hora, 4 horas e 24 horas) e conta os eventos do mesmo equipamento, separadamente por criticidade:

- `count_critico_1h`, `count_critico_4h`, `count_critico_24h`
- `count_nao_critico_1h`, `count_nao_critico_4h`, `count_nao_critico_24h`
- `count_total_1h`, `count_total_4h`, `count_total_24h` (= soma das duas anteriores; asserção exata `diff_max = 0`)

A implementação técnica usa `polars.Expr.rolling_sum_by(by="Data_Evento", window_size, closed="left").over("TAG")`. O parâmetro `closed="left"` é crítico para prevenção de *data leakage*: a janela é definida como `[t - N horas, t)`, excluindo o próprio evento da contagem — o modelo só vê o passado, nunca o presente nem o futuro.

A motivação central vem da Observação 2.5: 48% dos DGs do semestre são gerados por **acumulação** (regra CMA `QTD > 1`, isto é, múltiplos alarmes do mesmo tipo em janela temporal definida). Equipamentos que acumulam muitos eventos em pouco tempo têm probabilidade significativamente maior de gerar um DG por acumulação. A versão `count_total` valida adicionalmente a Hipótese 5.2 (padrão "calmaria → acúmulo → disparo" do caso CA65924 é universal) — disponibiliza ao modelo o total agregado para análise direta em W7.

#### Família 2 — Recência (W4, 2 colunas)

A pergunta operacional aqui é: *"Faz quanto tempo desde o último DG (ou último Crítico) deste equipamento?"*.

- `horas_desde_ultimo_DG` — horas decorridas desde o evento mais recente com `Is_Dont_Go = 1` no mesmo TAG (NULL se não houve DG anterior naquela TAG)
- `horas_desde_ultimo_critico` — análogo, mas para o evento mais recente com `Criticidade = Critico`

A implementação usa `shift(1).forward_fill().over("TAG")` sobre uma coluna auxiliar que contém o timestamp apenas dos eventos-alvo e NULL nos demais. O `shift(1)` garante exclusão do evento corrente; o `forward_fill` propaga o timestamp do último evento-alvo para todos os eventos subsequentes daquela TAG.

A motivação é o padrão clássico em manutenção preditiva — a recência da última falha é fator preditivo aceito no campo: equipamento que acabou de ter um DG (ou Crítico) tem perfil de risco diferente das próximas horas. O modelo poderá aprender, por exemplo, que `horas_desde_ultimo_DG < 2h` é fator agravante para um próximo DG iminente.

Um achado lateral relevante apareceu nesta família: **5.104 eventos têm `horas_desde_ultimo_critico = 0`** (0,94% do dataset), aproximadamente 10× mais que `horas_desde_ultimo_DG = 0` (479 eventos, 0,10%). Isso sugere **cascata de alarmes simultâneos** — múltiplos sensores disparando no mesmo instante em resposta a uma única falha física (por exemplo, queda súbita de pressão hidráulica dispara simultaneamente alarmes de temperatura de transmissão, vibração e nível de fluido). Não é leakage temporal — é sinal preditivo legítimo da existência de uma cascata em curso, comportamento que o modelo poderá aprender a reconhecer.

#### Família 3 — Estado pré-evento (W4, 1 coluna)

A pergunta operacional é: *"O que o equipamento estava fazendo na hora anterior a este evento?"*.

Para cada evento de telemetria com timestamp `t`, o script faz um *join* temporal `join_asof(strategy="backward")` com a tabela de apontamentos, procurando o ciclo de apontamento ativo no instante `t - 1h`. A coluna resultante `estado_pre_evento` assume os valores `Operando`, `Parado`, `Manutenção`, `Hibernando` ou `SEM_APONTAMENTO` (sentinela quando o evento ocorre fora de qualquer ciclo de apontamento da mesma TAG — situação rara, observada em apenas 106 eventos = 0,02% do dataset).

A motivação direta é a Observação 2.7: 12,65% dos DGs ocorrem em estado `Manutenção`, são alertas legítimos disparados durante reativações operacionais de teste (não falsos positivos de bancada). A feature `estado_pre_evento` permitirá ao modelo, em W5-W7, distinguir entre "DG durante operação real" e "DG durante teste de manutenção" — categorias com semântica operacional distinta que devem ser tratadas separadamente na análise estratificada em W7. A distribuição global dos 544.885 eventos por estado pré-evento é Operando 73,7% / Parado 17,8% / Manutenção 8,3% / Hibernando 0,2% / SEM_APONTAMENTO 0,02%; o estado `Manutenção` tem proporção de DGs ~1,5× maior que sua representação no dataset (12,65% / 8,3%), confirmando empiricamente a hipótese H5.1.

#### Família 4 — Regimal (W4, 2 colunas)

Esta família surgiu empiricamente como resposta ao achado central da Observação 2.6 e sua extensão: o alarme `Right Front Brake Temperature - Active` registrava entre 3 e 67 ocorrências mensais de janeiro a maio, e explodiu para **4.247 ocorrências em junho** — um salto de 151,7× sobre a média histórica do próprio alarme. Sem alguma feature que capture explicitamente esse tipo de anomalia, o modelo treinado em janeiro-abril não terá como antecipar o alarme dominante do conjunto de teste de junho.

- **`razao_alarme_7d_vs_30d_anterior`** — para cada evento, compara a frequência do mesmo alarme no mesmo equipamento nos últimos 7 dias contra a frequência nos últimos 30 dias, normalizada por dias. Fórmula: `(count_7d / 7) / (count_30d / 30)`. Uma razão de 5 significa "este alarme está disparando 5 vezes mais que o baseline histórico dele neste equipamento". A feature é calculada apenas para os 19 alarmes que geraram pelo menos um DG no semestre (decisão metodológica documentada — 99,6% dos alarmes do dataset são irrelevantes para o target, decisão consolidada na hipótese H2.1).

- **`razao_severidade_14d_vs_60d`** — para cada evento, compara a proporção Crítico/Não-Crítico em 14 dias recentes contra a mesma proporção em 60 dias do mesmo equipamento. Detecta inversões de severidade como a observada no Engine Coolant Level entre janeiro e fevereiro (de 83% Crítico para 6% Crítico, simultaneamente com aumento de volume — Observação 2.6, candidata à Observação 2.8 sobre mudança de regra CMA em fevereiro).

A interpretação dos resultados confirma o desenho: `razao_alarme_7d_vs_30d_anterior` retorna `NULL` em 74,3% do dataset (eventos cujo `Alarme` não está nos 19 priorizados) — comportamento correto por construção; os 25,7% restantes (~140.000 eventos) cobrem 100% dos DGs do semestre porque por definição todos os DGs derivam de algum dos 19 alarmes. `razao_severidade_14d_vs_60d` retorna `NULL` em apenas 0,2% dos eventos (1.234 ocorrências no início do semestre, sem 60 dias de histórico anterior disponível).

#### Família 5 — Operador (W4, 2 colunas)

Esta família responde diretamente à **Pergunta 3 do edital** ("o comportamento do operador correlaciona com a ocorrência de alertas DG?") e materializa o achado central da Hipótese H1.2 da W1 — que identificou `Id_Criticidade = 4` como **flag latente de bypass manual do operador** (87% concentrados em alarmes de `Channel Forced` e demais bypasses operacionais), não uma quarta categoria de severidade como inicialmente hipotetizado. A intuição operacional subjacente é que operadores recorrentes em bypass — ou em histórico recente de DGs — são candidatos a preditor de comportamento de risco, sob a hipótese de que pressão operacional excessiva ou perfil individual de risco se traduz em alertas Don't Go futuros.

- **`taxa_DG_operador_30d`** — taxa de DG do operador nos 30 dias anteriores ao evento, definida como `n_DGs_operador_30d / n_eventos_operador_30d`. Para cada evento, considera apenas eventos do mesmo operador (chave `Matricula_Operador_Hash`) ocorridos no intervalo `[t - 30 dias, t)` — janela estritamente exclusiva (`closed="left"`) que garante prevenção de leakage temporal análoga às demais features de rolling. Resposta direta à Q3: se a taxa estiver substancialmente acima da média global do treino, o modelo aprenderá a tratá-la como sinal de risco; se a distribuição for uniforme entre operadores, Q3 perde força e a feature funciona como controle informativo. A implementação técnica usa `rolling_sum_by(Is_Dont_Go, by=Data_Evento, window_size="30d", closed="left").over("Matricula_Operador_Hash")` dividido pela contagem total análoga.

- **`n_bypasses_operador_7d`** — contagem absoluta de bypasses manuais (`Id_Criticidade = 4`) feitos pelo operador nos 7 dias anteriores ao evento. A computação envolve um passo adicional não-trivial: como os bypasses tipicamente caem em `Criticidade = Informacional` (e, portanto, foram removidos do dataset filtrado pela decisão de W3), a feature precisa ser computada sobre `telemetria_tipada.parquet` (pré-filtro de Informacional) e em seguida propagada para os eventos pós-filtro via *join* por operador. A escolha de 7 dias (mais curta que `taxa_DG_operador_30d`) captura padrão recente de comportamento; uma janela mais longa diluiria o sinal em médias suaves.

A interpretação combinada das duas features deixa o modelo distinguir entre "operador historicamente associado a DGs" (taxa de 30d alta — sinal de longo prazo, padrão estrutural) e "operador em rampa recente de bypasses" (n_bypasses_7d alto — sinal de curto prazo, comportamento agudo). A distribuição empírica esperada de `n_bypasses_operador_7d` concentra-se em zero (95% dos eventos — operadores tipicamente não fazem bypass), com cauda longa fortemente associada à frota LeTourneau L 1850, que concentra 95% dos bypasses do semestre — **4ª evidência independente do padrão emergente H4.1** (problemas sistêmicos de instrumentação e/ou viés CMA nessa frota).

A consulta direta sobre `v2_split.parquet` (Observação 2.4, resolvida em W5 via `exploracao_w5_obs_pendentes.py`) ofereceu **a resposta empírica para a Pergunta 3 do edital** ("o comportamento do operador correlaciona com a ocorrência de alertas DG?"). A taxa global de DG no dataset filtrado é de 3,664%; o operador OP_067 do caso paradigma CA65924 apresenta taxa de 6,338% (1,73× o *baseline*), ocupando o rank #76 entre os 394 operadores únicos — top 19%, mas longe do extremo, com 152 outros operadores em faixa estatisticamente comparável (±50% da taxa de OP_067). A distribuição é fortemente assimétrica (mediana 2,99%, p95 10,87%, máximo 83,77%), mas os extremos têm baixo volume — o caso de comportamento operacional realmente preocupante é o operador OP_029, com 1.016 DGs absolutos sobre 3.125 eventos (taxa 32,5%), único com massa estatística suficiente para virar sinal preditivo robusto. **A resposta empírica a Q3 é portanto: sim, o comportamento do operador correlaciona com DG, mas de forma difusa** — não há um ou dois operadores "ruins" carregando o problema; há um *continuum* de variação aproximadamente 30 vezes entre o quartil inferior e o p95. A Hipótese H5.3 ("OP_067 tem taxa anormal") fica formalmente refutada com reinterpretação em `hipoteses_eda.md`, e a tabela `relatorio/tabelas/obs24_taxa_dg_por_operador.csv` (394 linhas) vira material direto para a seção CM 5 do relatório final. **Implicação para SHAP em W6:** a feature `taxa_DG_operador_30d` é informativa mas não deve dominar o ranking; interpretações do tipo "operador X é problemático" precisarão sempre ser estratificadas por volume de exposição para distinguir sinal real de ruído de pequena amostra.

#### Família 6 — Regra de negócio (W4, 1 coluna)

Esta família é qualitativamente distinta de todas as anteriores: enquanto Famílias 1 a 5 olham para o **histórico estatístico do equipamento e do operador**, esta lê a **estrutura interna da regra CMA** — o sistema de monitoramento da Vale e dos fabricantes que rotula `Is_Dont_Go` a partir de regras catalogadas. O catálogo completo das regras de nível "Muito Alto" está consolidado em `relatorio/tabelas/eventos_muito_alto.csv` (entregável CM 1.1 do Estudo Guiado, 82 entradas extraídas da sheet CMA do dicionário `Alarmes - Regra de Negocio.xlsx`).

- **`qtd_alarmes_nivel_muito_alto_360min`** — contagem de eventos do mesmo equipamento, nos 360 minutos anteriores (seis horas, `closed="left"`), cujo `Alarme` corresponde a alguma das 82 regras com nível "Muito Alto". A escolha de 360 minutos vem de inspeção direta do catálogo CMA: as regras do tipo acumulação (`QTD > 1`, `TEMPO > 0`) registram janelas `TEMPO` predominantemente entre 180 e 360 minutos — esta última cobre o limite superior observado e ainda permanece dentro da escala da janela de predição de 4 horas do *target* (consistência operacional). Implementação: pré-cálculo da lista de alarmes "Muito Alto" via filtro da sheet CMA, depois `is_muito_alto = pl.col("Alarme").is_in(lista_muito_alto)` seguido de `rolling_sum_by(is_muito_alto, by=Data_Evento, window_size="360m", closed="left").over("TAG")`.

A feature responde a uma pergunta operacional muito específica que nenhuma outra família captura: *"o equipamento está se aproximando do limiar de acumulação de alguma regra CMA Muito Alto?"*. Se a contagem está alta — digamos, quatro dos cinco alarmes Nível 2 necessários para uma regra de acumulação típica já ocorreram nos últimos 360 minutos — o modelo aprende a antecipar o quinto. É a **operacionalização direta da Observação 2.5** (W2): aproximadamente 48% dos DGs do semestre vêm de regras CMA de acumulação (`QTD > 1`), não de disparo imediato (`QTD = 1`). Sem esta feature, metade do mecanismo de geração do *target* fica fora do alcance do modelo. A distribuição empírica esperada concentra-se em valores baixos (zero a cinco) na grande maioria dos eventos, com cauda longa correspondendo a equipamentos em deterioração progressiva — exatamente o regime onde a antecipação de DG tem maior valor operacional.

#### Família 7 — Encoding categórico (W4, 7 colunas)

Cinco colunas categóricas do dataset (`TAG`, `Tag_Frota`, `Tipo`, `Nome_Operador_Anon`, `Classe`) precisam ser codificadas numericamente antes de alimentarem o LightGBM. A decisão metodológica desta família foi adotar **frequency encoding + one-hot** em vez de **target encoding** propriamente dito — escolha registrada em `controle_alteracoes.md` (entrada de 2026-05-17 — "Encoding categórico em W4: frequency + one-hot, target encoding adiado"). A justificativa é estritamente temporal: na sessão de implementação das Famílias 5-7 o *target* real `target_4h` ainda não havia sido construído (Etapa 11 do `05_features.py`, posterior); fazer *target encoding* sobre `Is_Dont_Go` (rótulo do evento atual, e não do horizonte futuro) introduziria *leakage* temporal massivo — o modelo aprenderia "TAG X tem taxa histórica de DG de Y%" calculada inclusive sobre o próprio evento que está tentando prever. A versão refinada, *target encoding* com KFold temporal sobre o treino, está formalmente agendada para W5 (`PLANEJAMENTO.md → W5`) e dependerá tanto do *target* construído quanto do *split* temporal estabelecido (ambos finalizados em W4).

- **`tag_freq`** — frequência relativa do equipamento no dataset filtrado: `count(TAG = x) / 544.885`. Aplicada às 33 TAGs presentes no dataset pós-filtro. Captura o "volume operacional" do equipamento — equipamentos mais ativos têm frequência mais alta e tendem a ter mais DGs por exposição maior — sem assumir qualquer ordem entre TAGs.

- **`frota_793D_2S`, `frota_793D_3S`, `frota_793D_4S`, `frota_793D_5S`** — quatro colunas *one-hot* derivadas de `Tag_Frota` (cinco valores no total, com `LeTourneau L 1850` como referência implícita pela soma das quatro *dummies* igual a zero). A escolha de *one-hot* sobre *frequency* se justifica pela baixa cardinalidade e pela importância estrutural conhecida da variável: 793-D 5S concentra 46,8% dos DGs do semestre, 4S concentra 32,1%, e a frota LeTourneau L 1850 tem perfil radicalmente distinto — aproximadamente 22 vezes menos DGs por equipamento (4ª evidência independente da H4.1). *One-hot* deixa o modelo aprender pesos diferentes para cada frota sem assumir ordem entre categorias estruturalmente distintas.

- **`tipo_caminhao`** — binário, valor 1 para `Tipo = 'Caminhão'` e 0 para `Tipo = 'Escavadeira'`. Apenas dois valores possíveis no dataset; tecnicamente redundante com a soma das quatro *dummies* de frota (caminhões → uma das quatro dummies = 1; escavadeira → soma = 0), mas mantido como coluna independente por interpretabilidade direta na análise SHAP de W6.

- **`operador_freq`** — frequência relativa do operador no dataset filtrado, análoga a `tag_freq`. Aplicada aos 394 operadores únicos do dataset (alta cardinalidade, identificadores anonimizados pela Vale via *hash*). Complementa a feature `taxa_DG_operador_30d` da Família 5: `operador_freq` captura o "volume operacional" do operador (operador veterano em alta exposição vs operador raro em baixa exposição — sinal estrutural de longo prazo), enquanto `taxa_DG_operador_30d` captura a "qualidade preditiva" (taxa de DG histórica recente — sinal dinâmico de curto prazo). As duas operam em planos complementares.

A coluna `Classe` da telemetria (valores `Activate` / `null`, semântica de "status do alarme") foi **omitida da matriz nesta família**: cardinalidade efetiva de dois valores e semântica redundante com a feature `valor_disponivel` da Família 0 (que já distingue alarmes com / sem medição numérica). A decisão está documentada em `documentacao_features.csv` apenas como informação metodológica; não há feature derivada de `Classe` em `v2_split.parquet`.

**Limitação conhecida e *fix* agendado para W5:** as duas features de *frequency encoding* (`tag_freq` e `operador_freq`) foram computadas sobre o dataset **global** (treino + validação + teste). Para um evento de janeiro-abril, a feature `tag_freq` embute conhecimento dos volumes de maio e junho — *leakage* temporal subtil de magnitude pequena (volumes mensais por equipamento são empiricamente estáveis), mas tecnicamente presente. O *fix* correto é recalcular essas frequências **apenas sobre o treino** e aplicá-las à validação e ao teste; está agendado como primeira sub-tarefa do `08_lightgbm.py` em W5, integrado à rotina mais ampla de substituição por *target encoding* com KFold temporal. Casos específicos identificados pós-*split* tornam o problema mais concreto: duas TAGs (`CA65791`, `CA65916`) aparecem em validação ou teste mas não em treino; treze operadores em validação ou teste estão ausentes do treino — o *leakage* é mais intenso para esses casos de borda, ainda que a magnitude global agregada seja pequena. A correção em W5 elimina o efeito por completo sem alterar a arquitetura nem o *split*.

### Coerência interna e validações defensivas

O `05_features.py` aplica sete grupos de asserções defensivas na função `validar()` ao final do pipeline: *shape* esperado (544.885 linhas), preservação dos 19.962 DGs após todas as operações de *join* e cálculo, zero `null` nas features básicas e nas 9 features de *rolling*, coerência aritmética `count_total = count_critico + count_nao_critico` (diferença máxima exatamente zero em todas as 544.885 linhas e nas três janelas 1h / 4h / 24h), valores positivos ou zero nas features de recência quando não-NULL (proibindo apenas valores estritamente negativos, que seriam *leakage* temporal real), domínio fechado de `estado_pre_evento` ∈ {Operando, Parado, Manutenção, Hibernando, SEM_APONTAMENTO}, e razões não-negativas nas features regimais quando não-NULL. As asserções foram desenhadas para falhar explicitamente caso uma regressão futura seja introduzida — uma alteração que quebre qualquer um dos sete grupos gera exceção imediata em vez de gerar dados silenciosamente corruptos.

### Estado da matriz de features

A matriz canônica de modelagem é o arquivo `Projeto/dados/features/v2_split.parquet`, com **544.885 linhas × 52 colunas** e **14,9 MB**, produto da execução sequencial de `05_features.py` (29 features + 3 targets) seguida de `06_split.py` (coluna `split`). A composição completa das 52 colunas é a seguinte:

| Categoria | Colunas | Origem |
|---|---:|---|
| Colunas originais do dataset limpo (telemetria + apontamentos) | 19 | `telemetria_limpa.parquet` + `apontamentos_limpo.parquet` |
| Features básicas (Família 0) | 5 | `05_features.py` etapas 1-3 — W3 |
| Features avançadas (Famílias 1-7) | 24 | `05_features.py` etapas 4-10 — W4 |
| Targets multi-janela (`target_2h`, `target_4h`, `target_8h`) | 3 | `05_features.py` etapa 11 — W4 (CM 3.3) |
| Coluna de partição temporal (`split ∈ {train, val, test}`) | 1 | `06_split.py` etapa 2 — W4 (CM 4.1) |
| **Total** | **52** | |

A tabela `documentacao_features.csv` (entregável CM 3.2 do Estudo Guiado) consolida as 29 entradas correspondentes às *features* explicitamente criadas no *script*, com nome, tipo, descrição, fórmula, motivação e semana de criação para cada uma; as 19 colunas originais do dataset e as 4 colunas de *target* e *split* são tratadas como infraestrutura do *pipeline*, não como *features* de modelagem propriamente ditas, e portanto não aparecem nesse dicionário.

Arquivos intermediários do *pipeline* (`v1.parquet` com 5 *features* básicas, 6,9 MB; `v2_parcial.parquet` com 19 *features* — Famílias 0 a 4, 19,6 MB; `v2.parquet` final com 29 *features* + 3 *targets*, 22,4 MB) são preservados em `dados/features/` para reprodutibilidade incremental e para inspeção de regressões, mas **não são consumidos por nenhum *script* a jusante**. O *input* canônico para toda a fase de Modelagem em W5-W6 é `v2_split.parquet`; os *scripts* downstream (`07_baseline.py`, `08_lightgbm.py`, `09_sobrevivencia.py`, `11_isolation_forest.py`) leem esse arquivo único e filtram pela coluna `split` nos pontos de treino, validação e teste. O `v2.parquet` original fica deliberadamente preservado como matriz "pré-*split*" para reprodutibilidade, mas não deve ser usado diretamente em modelagem, evitando contornar inadvertidamente o protocolo de avaliação temporal.

A execução completa do *pipeline* de feature engineering (carga + 7 famílias + 3 *targets* + validação defensiva + persistência dos três *parquets*) leva aproximadamente **7 segundos** sobre as 544.885 linhas em hardware comum de desenvolvimento; o *split* temporal adicional (`06_split.py`) acrescenta **2,6 segundos** — Polars opera eficientemente nessa escala, e a iteração rápida foi um critério explícito de arquitetura desde a fase de ingestão (W1). A consequência prática é que qualquer ajuste em features, janelas ou *targets* tem custo de iteração desprezível: o *pipeline* inteiro pode ser regenerado em menos de dez segundos.

Três artefatos auxiliares são gerados em paralelo à matriz e alimentam diretamente o relatório final:

- **`relatorio/tabelas/documentacao_features.csv`** (CM 3.2, 29 entradas) — dicionário canônico das *features*, formato exigido pelo Estudo Guiado.
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

O estado atual da matriz é portanto `v2.parquet` com **544.885 linhas × 51 colunas** (19 colunas originais + 29 features documentadas + 3 colunas-alvo), **22,4 MB**. A tabela `sensibilidade_janela.csv` consolida as taxas globais e a distribuição mensal de positivos para cada janela; a comparação preditiva entre os três horizontes via LightGBM com parâmetros *default* — que conclui a Profundidade 1 prevista para W4 — fica reservada para a sessão inicial de W5, com a conclusão final registrada em `controle_alteracoes.md` após os resultados empíricos.

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

O estado canônico do *pipeline* após esta sessão é portanto: a matriz `v2_split.parquet` (544.885 linhas × 52 colunas, **14,9 MB**) — `v2.parquet` original acrescido da coluna `split ∈ {train, val, test}` — vira o *input* único para a fase de Modelagem em W5. *Scripts* a jusante lerão essa matriz e filtrarão por *split* nos pontos de treino, *tuning* e avaliação. A matriz `v2.parquet` é preservada como referência "pré-*split*" para reprodutibilidade mas não deve ser usada diretamente em modelagem, evitando contornar inadvertidamente o protocolo de avaliação temporal.

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

*(Próximas seções a desenvolver em W5-W8: Modelagem — baseline + LightGBM (W5), modelo de sobrevivência + Isolation Forest (W6), Avaliação e Resultados (W7), Conclusão (W8).)*

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
| 9 | `Projeto/codigo/05_features.py` | W3 (básicas) + W4 (avançadas + target) | ✅ completo | Pipeline em 11 etapas que constrói **7 famílias de features (29 colunas) + 3 *targets* multi-janela**: Família 0 — básicas (5: `hora_dia`, `dia_semana`, `turno`, `mes`, `valor_disponivel`); Família 1 — rolling (9: `count_{critico,nao_critico,total}_{1h,4h,24h}`); Família 2 — recência (2: `horas_desde_ultimo_DG`, `horas_desde_ultimo_critico`); Família 3 — estado pré-evento (1: `estado_pre_evento` via `join_asof` t-1h); Família 4 — regimal (2: `razao_alarme_7d_vs_30d_anterior`, `razao_severidade_14d_vs_60d`); Família 5 — operador (2: `taxa_DG_operador_30d`, `n_bypasses_operador_7d`); Família 6 — regra de negócio (1: `qtd_alarmes_nivel_muito_alto_360min`); Família 7 — encoding categórico (7: `tag_freq`, `frota_793D_2S/3S/4S/5S`, `tipo_caminhao`, `operador_freq`); *targets* `target_2h`, `target_4h` (principal), `target_8h`. Saídas: `dados/features/v1.parquet` (5 básicas, 6,9 MB) + `dados/features/v2_parcial.parquet` (19, 19,6 MB) + `dados/features/v2.parquet` (29 + 3 *targets*, 22,4 MB) + `relatorio/tabelas/documentacao_features.csv` (CM 3.2, 29 entradas) + `relatorio/tabelas/sensibilidade_janela.csv` (descritiva, 18 entradas). Tempo de execução total: ~7s |
| 10 | `Projeto/codigo/06_split.py` | W4 | ✅ | *Split* temporal *walk-forward* com cortes nos limites de mês (`< 2025-05-01` para treino jan-abr, `< 2025-06-01` para validação mai, `>=` para teste jun). Saídas: `dados/features/v2_split.parquet` (544.885 × 52 colunas, 14,9 MB — *input* canônico para Modelagem em W5-W6) + `relatorio/tabelas/split_temporal.csv` (CM 4.1, 3 entradas) + `relatorio/figuras/fig07_janela_predicao.png` (diagrama do *target*) + `relatorio/figuras/fig08_split_temporal.png` (2 painéis: distribuição mensal por *split* + *drift* mês-a-mês). Tempo: 2,6s |
| 11 | `Projeto/codigo/07_baseline.py` | W5 | 🔄 planejado | Modelo baseline heurístico: `DG_predito = 1` se houve evento `Critico` nas últimas 4h do mesmo TAG. Métricas Precision / Recall / F1 / AUC-PR em validação (mai) e em teste (jun), estratificadas mês-a-mês (Mitigação 3 da Fig 8). Referência de comparação obrigatória para o GATE MARCO 1. |
| 12 | `Projeto/codigo/08_lightgbm.py` | W5 (v1) + W6 (v2 pós-Optuna) | 🔄 planejado | **W5 v1:** *fix* prévio do *leakage* de `tag_freq`/`operador_freq` (recompute sobre treino apenas) + LightGBM com parâmetros *default* + comparação de duas calibrações de `scale_pos_weight` (Mitigação 2: taxa de treino vs taxa de produção) + variante `Is_Dont_Go_producao` filtrando os 2.525 DGs em Manutenção (Obs 2.7) + métricas estratificadas mai vs jun (Mitigação 3). **W6 v2:** *TimeSeriesSplit* CV de 4 *folds* expandidos (Mitigação 1) + Optuna com 50 *trials* sobre AUC-PR média da CV + LightGBM v2 com melhores hiperparâmetros. Saída final: `modelos/lightgbm_v2.lgb`. |
| 13 | `Projeto/codigo/09_sobrevivencia.py` | W6 | 🔄 planejado | Modelo de Sobrevivência (Weibull AFT principal, *fallback* Cox PH se Weibull não convergir) com biblioteca `lifelines`. Trata o *censoring* (102.602 eventos sem DG futuro observado) rigorosamente como dado adicional, oferecendo segunda leitura do problema independente de *threshold* de classificação. Saídas: `modelos/sobrevivencia.joblib` + tabela de *hazard ratios* + Fig Extra A (curva Kaplan-Meier por estado pré-evento). |
| 14 | `Projeto/codigo/11_isolation_forest.py` | W6 | 🔄 planejado | Isolation Forest diagnóstico — treinado sobre o mesmo dataset **sem usar `Is_Dont_Go`**; mede a sobreposição entre DGs reais e *score* de anomalia. Teste empírico único do Risco 3.3 (viés do *label* CMA). Saídas: `modelos/isolation_forest.joblib` + `relatorio/tabelas/if_diagnostico.csv`. |
| 15 | `Projeto/codigo/10_evaluation.py` | W7 | 🔄 planejado | Métricas finais estratificadas (mês × frota × estado operacional × top-5 alarmes) + figuras 9-13 do relatório + análise de erro por contexto + curva *precision-recall* com limiar operacional calibrado por custo-benefício explícito. |

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
