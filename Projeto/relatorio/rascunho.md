# Rascunho do Relatório — Programa Desenvolver 2026

Documento de escrita progressiva que vai consolidando as seções do relatório final ao longo das semanas W2→W8. Será migrado para `Desenvolver_Template.docx` em W9.

**Status atual:** seções preenchidas até **W6 completa** — **Introdução** (reenquadrada 27/05 como estudo analítico com 2 frentes operacionais + 2 entregas complementares — garantia metodológica via IF + tradução para o negócio — e nota sobre L10), **Entendimento do Negócio** (CM 1.1 + CM 1.2 — cenário de aplicação reenquadrado em 2 frentes operacionais + nota separada sobre o IF como garantia metodológica), **Metodologia Parte 1** (Exploração de Dados — W2 EDA + Q4 + Q5), **Metodologia Parte 2** (Preparação dos Dados — limpeza + 7 famílias de *features* + 3 *targets* multi-janela + *split* temporal *walk-forward* + *fix* de *leakage* de *encoding*, matriz canônica `v3.parquet` com 544.885 × 58 colunas), **Metodologia Parte 3** (Modelagem completa W5+W6 — baseline heurístico, LightGBM v1, **LightGBM v2** com Optuna + CV + determinismo, **SHAP do v2** revelando predição de cascata, **LightGBM v3 promovido a canônico** sem `horas_desde_ultimo_DG` (AUC-PR test=0,8556 + Recall +16,72pp em primeiros DGs), **SHAP do v3**, **Weibull AFT** (C-index test=0,7444), **Isolation Forest** (Risco 3.3 parcialmente mitigado), **Fechamento W6** (validação cruzada SHAP×HR, Fig 9 comparativa, calibração + Platt rejeitado por drift, ablation por grupo)), **Resultados — leitura para o time de negócio e operacional** (3 figuras de negócio novas — timeline CA65926, ranking de risco operacional, horas de parada evitáveis — + promoção das figs ExA e ExG para o corpo principal), **Diferenciais metodológicos do trabalho** (6 pontos posicionando contra outras abordagens), **Síntese parcial de limitações** (L1-L10 atualizadas). Refatoração 24/05: detalhes técnicos dos scripts movidos para `notas_metodologicas.md` Seções 4-18 — `rascunho.md` mantém narrativa + resultados + interpretação. **Pendentes:** Avaliação estratificada final em W7 (`10_evaluation.py`), Conclusão + CM 6.3 (Trabalhos Futuros) em W8, migração para `Desenvolver_Template.docx` em W9.

---

## Introdução

Este relatório apresenta um **estudo analítico** para a antecipação de alertas Don't Go (DG) em frotas de equipamentos de mineração da Vale, na região de Itabira, no escopo do desafio de Análise Avançada de Dados do Programa Desenvolver 2026. A entrega não é um sistema em produção, e sim um conjunto de **conclusões fundamentadas + recomendações operacionais acionáveis**, organizadas em duas frentes operacionais (com modelos correspondentes) e duas entregas complementares — uma de garantia metodológica, outra de tradução para o negócio:

**Frentes operacionais:**

1. **Modelo preditivo de classificação** (LightGBM v3) que estima `P(DG nas próximas 4 horas)` por equipamento, com AUC-PR test = 0,8556 (jun/2025) — **alvo: alerta antecipatório de curto prazo**, caso de uso de plantão.
2. **Modelo de sobrevivência** (Weibull AFT) com *hazard ratios* interpretáveis (IC 95% e p-valor por feature) — **alvo: política de manutenção preventiva estratificada por frota e por equipamento**, sem dependência de *threshold*, caso de uso estratégico.

**Entregas complementares:**

3. **Diagnóstico do rótulo `Is_Dont_Go`** via *Isolation Forest* não-supervisionado — **garantia metodológica** (não é frente operacional): auditoria empírica do viés inerente das regras CMA (Risco 3.3), identificando em quais equipamentos o rótulo captura anomalia estatística real (CA65926, CA65932, CA65924) e em quais não. Sustenta a documentação da Limitação L10 e recomendações em CM 6.3.
4. **Achados estruturais e recomendações operacionais** documentadas com figuras de negócio: timeline de deterioração do equipamento mais crítico (CA65926), ranking de risco operacional dos 33 equipamentos do parque com ação recomendada por nível, e tradução das métricas técnicas em valor operacional (horas de parada não planejada evitáveis no semestre observado).

O conjunto de dados disponibilizado cobre seis meses (janeiro a junho de 2025): aproximadamente **37,16 milhões de eventos de telemetria** distribuídos entre 35 equipamentos com instrumentação contínua, e cerca de **378 mil ciclos de apontamento operacional** sobre 47 equipamentos. A taxa observada de DGs no semestre é de aproximadamente **0,054%** (19.962 ocorrências em 37,16 milhões de eventos), caracterizando um problema de classificação extremamente desbalanceado. O presente trabalho segue a metodologia CRISP-DM e estrutura-se nas seções de Entendimento do Negócio, Exploração de Dados (Metodologia, Parte 1), Preparação dos Dados, Modelagem, **Resultados** (com leitura específica para o time de negócio e operacional), Limitações e Conclusão.

**Sobre o uso operacional dos achados (importante):** durante a análise, três técnicas independentes convergiram para um achado central que reorientou a forma de comunicar os resultados — a performance agregada do modelo de classificação no teste é largamente dirigida pela detecção de um único equipamento em deterioração progressiva (CA65926, responsável por 24,7% dos DGs do semestre). Em regimes sem essa anomalia dominante, a efetividade do modelo cai significativamente. Isso reposiciona a entrega: o modelo de classificação é uma das ferramentas do conjunto, mas o **valor operacional principal está no monitoramento estratificado por equipamento + decisão de manutenção informada pelas duas frentes em conjunto (LightGBM v3 + Weibull AFT)** — não num único *score* automático. Essa nuance permeia toda a seção de Resultados.

---

## Entendimento do Negócio

### Contexto operacional e o fluxo Don't Go (CM 1.1)

A Figura 1 sintetiza o fluxo operacional que gera os dados deste estudo e localiza visualmente o ponto em que o modelo preditivo proposto se encaixa, com o objetivo de converter parada não planejada em inspeção preventiva.

[Figura 1 — Diagrama do fluxo operacional](figuras/fig01_fluxo_de_apontamentos.png)

O ciclo operacional começa quando o operador da Vale inicia um **ciclo de apontamento** (bloco A da figura), registrando o instante inicial (`Inicio`) e identificando o estado em que o equipamento se encontra dentre quatro possibilidades — Operando, Parado, Manutenção ou Hibernando. Cada ciclo é unicamente identificado e encerrado por um instante final (`Fim`), formando a base do conjunto `desenvolver_apontamentos.parquet` (377.907 ciclos no semestre). Detalhes do dicionário de campos estão consolidados em [`notas_exploracao_inicial.md`](notas_exploracao_inicial.md).

Durante o ciclo, os sensores do equipamento geram **telemetria contínua** (bloco B): aproximadamente 206.000 eventos por dia distribuídos entre as 35 TAGs com instrumentação, registrando variáveis como temperatura, pressão, vazão, nível de fluidos, peso de carga e velocidade. Cada evento é classificado em tempo real pela **Central de Monitoramento de Ativos (CMA)** da Vale (bloco C) em três níveis de criticidade — `Informacional`, `Não-Crítico` ou `Crítico` — segundo regras de negócio que combinam o tipo do alarme, o seu valor numérico e o padrão observado nos minutos anteriores. Eventos `Informacional` representam aproximadamente 98,5% do volume e não geram alertas operacionais; as cerca de 1,5% restantes são candidatos a virar Don't Go (detalhamento na Seção de Caracterização dos Dados).

O **catálogo de regras "Muito Alto" da CMA** (bloco D) — consolidado em [`tabelas/eventos_muito_alto.csv`](tabelas/eventos_muito_alto.csv), com 82 regras catalogadas — define exatamente quando um alarme dispara um alerta DG. Duas modalidades coexistem: **(i) disparo imediato** — uma única ocorrência do alarme em nível mais severo é suficiente (`QTD = 1`, `TEMPO = 0`); **(ii) disparo por acumulação** — `N` ocorrências do alarme dentro de uma janela `T` em minutos (por exemplo, "cinco alarmes Nível 2 consecutivos em 360 minutos"). Aproximadamente 95% das regras catalogadas são *wrappers* sobre alarmes nativos do fabricante (`TIPO = ALARME OEM`, principalmente Caterpillar para os caminhões 793-D), 4% derivam de análises de tendência criadas pela própria Vale, e 1% são regras de sistema. Essa proporção tem implicação metodológica relevante e será retomada na seção de Limitações: o *label* `Is_Dont_Go` herda majoritariamente a calibração de fábrica dos sensores, não uma definição operacional autônoma da Vale, o que torna a discussão de viés do *label* uma preocupação concreta a ser empiricamente testada pelo *Isolation Forest* em W6.

Quando alguma das 82 regras é satisfeita pela telemetria observada, o evento recebe a flag **`Is_Dont_Go = 1`** (bloco E), sinalizando que o equipamento **não deve sair da mina ou continuar operando** até que o problema seja resolvido. A **ação operacional** correspondente (bloco F) é então acionada pelo *dispatcher* responsável, que comanda a parada e dispara inspeção, intervenção ou manutenção corretiva. Tipicamente, o equipamento entra em um novo ciclo de apontamento com estado `Manutenção`, fechando o *loop* operacional. No semestre analisado, esse mecanismo gerou **19.962 ocorrências de DG**, distribuídas de forma fortemente desigual entre alarmes, frotas, estados operacionais e meses do semestre — assimetria detalhada nas seções de Caracterização e Análise temporal mais adiante.

### Cenário de aplicação operacional proposto (CM 1.2)

A proposta do estudo se encaixa **lateralmente** ao fluxo operacional descrito acima (bloco G da Figura 1) — não substitui a regra CMA, mas a complementa em **duas frentes operacionais distintas**, cada uma servida por uma das ferramentas analíticas entregues:

**Frente 1 — Alerta antecipatório de curto prazo (LightGBM v3).** Ao consumir continuamente a telemetria recente (*rolling windows* de 1, 2, 4, 8 e 24 horas) junto com o estado operacional corrente, o histórico recente do operador e o histórico próprio do alarme, o modelo de classificação produz a cada instante uma estimativa de `P(DG nas próximas 4 horas)` para cada TAG instrumentada. A janela de 4 horas foi escolhida por três motivos convergentes: **(i) operacional** — compatível com o tempo médio de mobilização de peças e equipe de manutenção em Itabira; **(ii) preditivo** — curta o bastante para que o estado atual dos sensores ainda tenha valor informativo; **(iii) metodológico** — análise de sensibilidade nas janelas 2h e 8h (W5, ver tabela `comparacao_horizontes_lightgbm.csv`) validou empiricamente a escolha. Esta ferramenta entrega o **caso de uso de plantão**: priorização de inspeção a cada turno.

**Frente 2 — Política de manutenção preventiva estratificada (Weibull AFT + ranking estrutural).** O modelo de sobrevivência entrega *hazard ratios* interpretáveis com intervalo de confiança 95% e p-valor por feature. Diferente do modelo de classificação, **não depende de threshold**: a saída é uma estimativa de tempo até o próximo DG em função do estado atual. Combinado com o ranking de risco por equipamento (Figura `figNeg02` na seção de Resultados — 5 ALTO, 18 MÉDIO, 10 BAIXO, com ação recomendada por nível), entrega o **caso de uso estratégico**: revisar o plano de manutenção preventiva com base em diferenças quantificadas entre frotas (LeTourneau vs 793-D 5S, por exemplo, com *time ratio* de 0,17) e entre equipamentos individuais — política orientada por evidência, não por intuição.

**Modo de operação proposto (visão integrada).** A cada início de turno, o painel operacional consolida:

- **Alertas curtos** (Frente 1): TAGs cuja `P(DG ≤ 4h)` ultrapassa um limiar calibrado por curva *precision-recall* e análise de custo-benefício explícita (W7) — fila priorizada de inspeção a cada turno.
- **Risco estrutural** (Frente 2): ranking dos 33 equipamentos com telemetria significativa por *hazard* e por taxa observada de DG, com indicador visual de nível (ALTO/MÉDIO/BAIXO — Figura `figNeg02`) e ação recomendada por nível — informação atualizada mensalmente, base para a política de manutenção preventiva.

**Ganho operacional esperado.** A conversão de uma fração das paradas não planejadas (reativas, custo alto, equipamento desativado sem aviso) em inspeções preventivas (planejadas, custo baixo). A magnitude desse ganho é quantificada na seção de Resultados em três cenários com premissas explícitas — entre **10.480h e 43.582h-equipamento de parada não planejada evitáveis no semestre observado** sobre uma base atual estimada de 79.848h.

**Limitação operacional reconhecida desde o entendimento do negócio.** Análise empírica posterior (Resultados + Limitação L10) revela que a alta performance agregada do modelo de classificação em junho é largamente dirigida pela detecção de um equipamento em deterioração progressiva (CA65926). Em regimes sem essa anomalia dominante, a efetividade da Frente 1 cai significativamente — para próximo da AUC mediana por TAG (~0,61), em vez do agregado de 0,86. Isso reforça a importância da **operação integrada das duas frentes**: a Frente 1 isoladamente não realiza todo o valor proposto; a combinação com a Frente 2 (visão estrutural por equipamento + política de manutenção informada por sobrevivência) é o que sustenta o ganho operacional estimado.

#### Nota sobre o terceiro modelo entregue: o Isolation Forest como garantia metodológica

Um terceiro modelo é entregue no escopo do estudo — o *Isolation Forest* não-supervisionado treinado sem o rótulo `Is_Dont_Go` (`11_isolation_forest.py`). Sua finalidade **não é operacional** e por isso não compõe as duas frentes acima. Sua função é **metodológica**: testar empiricamente o Risco 3.3 (viés do rótulo `Is_Dont_Go`, gerado por 82 regras CMA cuja calibração é ~95% herdada do fabricante dos equipamentos). A pergunta respondida é: *"em quais equipamentos as anomalias estatísticas detectáveis no espaço de features coincidem com os DGs rotulados pela CMA?"*

O achado — convergência forte em apenas 3 equipamentos (CA65926, CA65932, CA65924) com volume significativo — é o que sustenta a documentação honesta da **Limitação L10** em CM 6.2 e a **recomendação CM 6.3** de investigação manual dos eventos com alto *anomaly score* que não foram rotulados como DG (possíveis "DGs perdidos" pelas regras CMA). O modelo IF como ferramenta de **detecção contínua de deterioração em deployment** seria uma extensão natural (treino em janela móvel) e fica registrada em Trabalhos Futuros (CM 6.3), mas **não foi implementada neste estudo** — o IF aqui rodou uma única vez, sobre os splits fixos.

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

Um achado lateral relevante registra-se aqui para evitar repetição posterior. A análise de cobertura por *split* identificou **rotação de equipamentos**: duas TAGs (`CA65791`, `CA65916`) aparecem em validação ou teste mas não em treino, e cinco TAGs (`CA65917`, `CA65908`, `CA65902`, `CA65922`, `CA65923`) aparecem em treino mas não em validação ou teste; treze operadores em validação ou teste estão ausentes do treino. As *features* de codificação `tag_freq` e `operador_freq` (Família 7) foram computadas sobre o *dataset* global, ou seja, embutem volumes de validação e teste em valores que o modelo verá no treino. A magnitude esperada do efeito é pequena — volumes mensais por equipamento são estáveis e a estabilidade compensa a sobreposição temporal — **mas tecnicamente é uma forma branda de** *data leakage*. O *fix* correto é recalcular as frequências apenas sobre o treino e aplicar a validação e teste. **Ambos os pontos foram resolvidos em W5:** (i) o *leakage* brando foi corrigido em 22/05 (`06b_fix_encoding_leakage.py`, gerando o `v3.parquet` canônico); (ii) a migração para *target encoding* com KFold temporal foi avaliada empiricamente em 06/06 (`21_target_encoding_comparativo.py`) e **descartada** — com hiperparâmetros fixos do v3 variando apenas o encoding, o *target encoding* piorou a AUC-PR (−2,25pp em validação, −0,62pp em teste), abaixo do critério de substituição de +1pp. Manteve-se o *frequency encoding*, que se mostrou mais estável sob o drift temporal (taxas-alvo de jan-abr não transferem bem para mai/jun). Decisão registrada em `controle_alteracoes.md` (06/06).

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

**v2 foi o modelo canônico até 24/05/2026** — combina tuning rigoroso, validação cruzada honesta (sem *test set peeking*) e reprodutibilidade *bit-exact*. A análise SHAP feita sobre v2 (próxima subseção) revelou que a *feature* #1 do modelo (`horas_desde_ultimo_DG`, 39,3% do peso) opera como **predição de cascata**, não predição de primeiro DG — limitação operacional significativa. Por causa desse achado, **v2 foi posteriormente substituído pelo v3 (sem `horas_desde_ultimo_DG`) como modelo canônico do relatório final** (subseção "LightGBM v3 — canônico promovido" abaixo). v2 fica **preservado** como modelo intermediário (artefato em `Projeto/modelos/lightgbm_v2.txt`), citado por completude metodológica e como base diagnóstica que motivou a promoção. **v1 fica preservado como referência metodológica** (efeito comparativo "default vs tunado" + diagnóstico do peeking de Mitigação 2).

---

### Análise SHAP do LightGBM v2 (`08c_shap_v2.py`) — motivação para a promoção do v3

> **Nota de leitura:** esta subseção descreve a análise SHAP que foi executada **sobre o v2** quando ele ainda era o modelo canônico. O achado crítico identificado aqui (item "predição de cascata") motivou o treino e a promoção do **v3 sem `horas_desde_ultimo_DG`** como novo canônico — descrito logo após. Portanto, esta análise SHAP é apresentada por completude metodológica e como **base diagnóstica da decisão de promoção**, não como descrição do modelo final do relatório.

A análise SHAP (SHapley Additive exPlanations) do (então) modelo canônico v2 foi a etapa de **validação de qualidade** prometida desde o GATE MARCO 1 — sem ela, a AUC-PR de 0,8618 em test ficaria sem explicação. Computada via TreeSHAP sobre o test set completo (71.089 eventos, ~47 s de execução), produziu a matriz canônica `shap_values_v2_test.npy` (19 MB, [71.089 × 35]) que vira o substrato para todas as análises de interpretabilidade subsequentes.

> 📘 **Detalhes técnicos (algoritmo TreeSHAP, configuração, decisões de subgrupos estratificados):** ver [`notas_metodologicas.md` Seção 10](notas_metodologicas.md). **Script:** `Projeto/codigo/08c_shap_v2.py`. **Saídas:** matriz SHAP completa + 2 tabelas (`shap_global_v2.csv`, `shap_estratificado_v2.csv`) + 3 figuras (Fig 9a bar, Fig 9b beeswarm, Fig 10 dependence plots).

#### Ranking de importância global

[Figura 9a — Importância global das features (SHAP)](figuras/fig09a_shap_bar.png)
[Figura 9b — Distribuição dos SHAP values por feature](figuras/fig09b_shap_beeswarm.png)

| Rank | Feature | Família | mean(\|SHAP\|) | % do peso |
|---:|---|---|---:|---:|
| **1** | `horas_desde_ultimo_DG` | 2 — Recência | 0,968 | **39,3%** |
| **2** | `qtd_alarmes_nivel_muito_alto_360min` | 6 — Regra de Negócio | 0,767 | **31,1%** |
| **3** | `razao_alarme_7d_vs_30d_anterior` | 4 — Regimal | 0,211 | **8,6%** |
| 4 | `tipo_caminhao` | 7 — Encoding | 0,122 | 5,0% |
| 5 | `tag_freq` | 7 — Encoding | 0,041 | 1,7% |
| 6 | `count_total_24h` | 1 — Rolling | 0,028 | 1,1% |
| 7 | `horas_desde_ultimo_critico` | 2 — Recência | 0,026 | 1,0% |
| 8 | `razao_severidade_14d_vs_60d` | 4 — Regimal | 0,025 | 1,0% |
| 9 | `mes` | 0 — Básicas | 0,022 | 0,9% |
| 10 | `count_nao_critico_8h` | 1 — Rolling | 0,021 | 0,8% |

**Top 2 features explicam 70% do peso; top 10 explicam 91%.** Três famílias dominam o ranking — Recência (Família 2), Regra de Negócio (Família 6) e Regimal (Família 4) somam **79% do peso** do modelo.

#### Quatro perguntas centrais respondidas pelo SHAP

**1. v2 NÃO é "baseline glorificado".** A *feature* `count_critico_4h` — núcleo do baseline heurístico (W5) — aparece apenas no **rank #29**. O LightGBM v2 aprendeu sinal qualitativamente diferente, justificando empiricamente os +27,6 pp de AUC-PR sobre baseline em test.

**2. Família 4 regimal funciona exatamente como previsto.** `razao_alarme_7d_vs_30d_anterior` (rank #3, 8,6%) foi desenhada em W4 especificamente para detectar a anomalia RFB do CA65926 (Obs 2.6/2.9). O modelo confirma empiricamente que essa decisão de *feature engineering* foi acertada — feature com fundamentação observacional forte ficou no topo.

**3. Obs 2.11 fracamente refutada.** A hipótese de W4 propunha que `count_critico_*` apareceria acima de `count_total_*` no ranking (acúmulo de criticidade > acúmulo de volume). Resultado misto: em janelas 2h/4h, criticidade vence; em 1h/8h/24h, total vence. **Mas o achado mais importante é que TODAS as 15 features de rolling counts ficaram em rank #15-#31** — o modelo não dependeu fortemente desse padrão. A versão "domain-specific" (`qtd_alarmes_muito_alto_360min` da Família 6, que conta APENAS alarmes nas 82 regras CMA Muito Alto) venceu a versão genérica (Família 1) em magnitude (31,1% vs cumulativo ~5% das 15 rolling).

**4. Famílias 4 + 6 + 2 dominam (79% do peso conjunto):** três lógicas qualitativamente distintas — recência temporal, *lookup* de regras CMA, e detecção de anomalia regimal. **Nenhuma delas é "conte críticos recentes"** (que seria o baseline). O modelo aprende padrões mais sofisticados do que o esperado.

#### Análise estratificada — CA65926 vs resto do test

| Rank | CA65926 (9,96% do test) | Resto do test (90,04%) |
|---:|---|---|
| 1 | `horas_desde_ultimo_DG` (36,9%) | `horas_desde_ultimo_DG` (39,6%) |
| 2 | `qtd_alarmes_muito_alto` (34,1%) | `qtd_alarmes_muito_alto` (30,6%) |
| 3 | `razao_alarme_7d_vs_30d` (10,1%) | `razao_alarme_7d_vs_30d` (8,3%) |
| 4 | `tipo_caminhao` (2,0%) | `tipo_caminhao` (5,4%) |
| 5 | `horas_desde_ultimo_critico` (1,9%) | `tag_freq` (1,8%) |

**Top 3 idênticos** entre os dois subgrupos. O modelo usa **a mesma estratégia** para predizer DGs do CA65926 e do resto — não há divisão em "regras específicas para o equipamento problemático". A diferença é apenas de **peso relativo**: CA65926 dá levemente mais importância a `qtd_alarmes_muito_alto` (34% vs 31%) e `razao_alarme_7d_vs_30d` (10% vs 8%), coerente com a Obs 2.9 (anomalia mecânica progressiva detectada por features de acumulação e regimais).

#### Achado crítico — `horas_desde_ultimo_DG` é predição de cascata, não de primeiro DG

O fato da feature #1 do modelo ter 39% do peso e ser `horas_desde_ultimo_DG` motivou diagnóstico dedicado. Inspeção da matriz SHAP nos 12.038 positivos do test:

| Métrica | Resultado |
|---|---|
| Top 10% eventos com maior SHAP+ em `horas_desde_ultimo_DG` (7.109 eventos) | 100% têm DG anterior em ≤ 2h; mediana = 1 minuto |
| Desses, quantos são DG real? | 94,2% (6.696 positivos) |
| 9.475 positivos preditos corretamente (TPs) | 84,7% têm DG anterior em ≤ 1h; 93,1% em ≤ 4h |
| Eventos SEM DG anterior (NULL ou > 24h) — 3.919 casos | Dos 101 positivos reais, **apenas 1 é predito corretamente (1%)** |

**Implicação:** o LightGBM v2 é, em essência, um **detector de continuação de cascatas**. Quando há DG recente (cascata em curso), prediz bem; quando não há histórico, falha quase totalmente. O AUC-PR de 0,8618 em test reflete majoritariamente *cascade recovery*, não *first DG prediction*.

**Para a Vale operacionalmente:** o caso de maior valor é antecipar o **primeiro** DG (evitar que a rajada aconteça); pegar o terceiro ou quarto DG na cascata é tarde demais para mitigação. O modelo atual entrega o oposto.

Esse achado motivou uma **decisão metodológica adicional**: treinar variante v3 sem `horas_desde_ultimo_DG` (`08e_lightgbm_v2_no_cascade.py`) para **quantificar empiricamente** o trade-off entre "predição de cascata" e "predição de primeiro DG". Os resultados dessa análise serão integrados a esta seção quando o experimento concluir.

#### Achados laterais com força para CM 6.1 e CM 6.2

- **`tipo_caminhao` no top 5 (rank #4, 5,0%):** o modelo usa essa *feature* binária (1=Caminhão / 0=Escavadeira) para **ajustar a probabilidade base de DG por tipo de equipamento**. Confirma empiricamente a H4.1 (frota LeTourneau L 1850 tem perfil radicalmente distinto, ~22× menos DGs por equipamento). O modelo aprendeu a tratar as duas frotas como populações estatisticamente diferentes.

- **`operador_freq` no rank #13 (0,72%):** confirma a Q3 do edital — operador correlaciona com DG, mas de **forma difusa**, consistente com o achado da Obs 2.4 (W5, 152 operadores em faixa comparável a OP_067). O modelo usa a feature mas não a prioriza.

- **`mes` no rank #9 (0,89%):** **limitação CM 6.2.** O modelo aprendeu que o mês correlaciona com taxa de DG (provavelmente capturando o *drift* mai → jun via Obs 2.6). Em *deployment* com `mes` fora de [1, 6] (julho/agosto/etc.), o LightGBM extrapola implicitamente — trataria `mes = 7` como "`mes >= 5,5`" (igual a junho). Magnitude do problema é pequena (0,89% do peso), e a recomendação de **retreino *rolling* mensal** já registrada em CM 6.3 endereça a limitação por construção: em deployment real, o modelo é treinado nos últimos N meses, então `mes` nunca extrapola.

- **Família 1 (15 features rolling) virtualmente ignorada pelo modelo:** todas em rank #15-#31. **Lição metodológica:** *features* genéricas (contar eventos em janelas temporais) podem perder para versões *domain-specific* da mesma ideia (contar APENAS alarmes nas regras CMA Muito Alto). Material direto para CM 6.1 — exemplo de como engenharia de *features* com fundamentação no domínio supera engenharia agnóstica.

#### Síntese para o relatório final

O SHAP entrega três contribuições para o relatório:

- **Interpretabilidade (CM 5.2):** ranking explícito + dependence plots permitem ao leitor entender exatamente como o modelo decide.
- **Insights Não Óbvios (CM 6.1):** quatro narrativas convergentes — Família 4 regimal valida engenharia em W4; cascade detection é o que o modelo realmente faz; H4.1 confirmada via `tipo_caminhao`; features domain-specific vencem genéricas.
- **Limitações (CM 6.2):** cascade-only prediction, `mes` como extrapolação implícita, Obs 2.11 fracamente refutada.

A análise da Variante v3 (sem `horas_desde_ultimo_DG`) foi executada em seguida — descrita na próxima subseção. O resultado **promoveu v3 a modelo canônico do relatório**, substituindo v2 (que fica preservado como intermediário diagnóstico).

---

### LightGBM v3 — modelo canônico promovido (`08e_lightgbm_v2_no_cascade.py`)

O LightGBM v3 (também referenciado como "v2_no_cascade" nos arquivos de artefato, por origem da iteração) é o **modelo canônico final do relatório**. É um clone exato do v2 com uma única alteração: a *feature* `horas_desde_ultimo_DG` foi removida do conjunto de entrada (35 → 34 *features*; `horas_desde_ultimo_critico` permanece). Mantém Optuna 50 *trials*, TimeSeriesSplit CV de 4 *folds* expandidos, e determinismo estrito.

> 📘 **Motivação completa da promoção, justificativa e contextualização: ver `controle_alteracoes.md` entrada `2026-05-24 — Promoção de v3 a modelo canônico`.** **Script:** `Projeto/codigo/08e_lightgbm_v2_no_cascade.py` (~25,7 min — Optuna 25,4 min + treino final 14 s). **Saídas:** modelo `Projeto/modelos/lightgbm_v2_no_cascade.txt` + study `Projeto/modelos/optuna_study_v2_no_cascade.pkl` + 3 tabelas (`lightgbm_v2_no_cascade_metricas.csv`, `lightgbm_v2_no_cascade_hiperparametros.csv`, `v2_vs_v2_no_cascade.csv` comparativo decisório).

#### Por que v3 substitui v2 como canônico

O SHAP do v2 revelou que a *feature* `horas_desde_ultimo_DG` (rank #1, 39,3% do peso) operava como **detector de continuação de cascata**, não como antecipação genuína de primeiro DG: dos 101 positivos *sem DG anterior recente* no test, apenas 1 era predito corretamente. Treinar v3 sem essa *feature* força o modelo a aprender sinais antecipativos. A pergunta empírica era: **v3 mantém desempenho competitivo no agregado e melhora no subgrupo "primeiro DG"?**

Resposta direta dos dados (test set completo, n = 71.089):

| Subgrupo | n+ | v2 AUC-PR | v3 AUC-PR | Δ AUC-PR | v2 Recall@0.5 | v3 Recall@0.5 | Δ Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Geral** | 12.038 | 0,8618 | 0,8556 | **−0,62pp** | 0,6803 | 0,7527 | **+7,24pp** |
| **Primeiro DG** (sem DG ≤24h ou NULL) | 1.705 | 0,1876 | **0,1964** | **+0,88pp** | 0,0434 | **0,2106** | **+16,72pp** |
| **Cascata** (DG ≤4h) | 9.035 | 0,9700 | 0,9691 | −0,09pp | 0,8836 | **0,9185** | +3,49pp |

Três fatos críticos sustentam a decisão de promoção:

1. **No agregado, v3 perde apenas 0,62pp de AUC-PR e ganha +7,24pp de *Recall*** — o caso operacional (não perder DGs) valoriza *recall*, então essa troca é vantajosa.
2. **No subgrupo "primeiro DG" — o caso de uso operacional valioso —, v3 ganha em ambas as métricas:** AUC-PR sobe +0,88pp e, decisivamente, *Recall@0.5* sobe de 4,34% para 21,06% (**5× mais primeiros DGs capturados**).
3. **Em cascata, v3 não degrada** — perde apenas 0,09pp de AUC-PR mas ganha +3,49pp de *Recall*, continuando a detectar continuações de rajada quase tão bem quanto v2.

#### Resultados completos do v3

| Métrica | Valor | Comparação |
|---|---:|---|
| AUC-PR train | 0,9653 | gap de 0,25 vs val → overfitting moderado (similar ao v2) |
| AUC-PR val (mai) | 0,7132 | −6,69pp vs v2 (drift mai/jun mais sensível sem feature de cascata) |
| AUC-PR test (jun) | **0,8556** | −0,62pp vs v2 — competitivo |
| AUC-PR CV média (4 folds) | 0,8530 | métrica usada pelo Optuna |
| Melhor *trial* | #41 de 50 | — |
| Tempo total | 25,7 min | Optuna 25,4 min + treino final 14 s |

**Hiperparâmetros encontrados pelo Optuna (vs v2):**

| Hiperparâmetro | v2 (best) | v3 (best) | Direção |
|---|---:|---:|---|
| `n_estimators` | 199 | 301 | +51% (mais árvores compensam menos *features*) |
| `learning_rate` | 0,013 | 0,0118 | −9% (semelhante) |
| `num_leaves` | 61 | 69 | +13% (semelhante) |
| `min_child_samples` | 60 | 50 | −17% (semelhante) |
| `scale_pos_weight` | 0,513 | **2,40** | **+368% — modelo aprendeu a ser mais sensível** |
| `lambda_l1` | 0,32 | 0,197 | −38% |
| `lambda_l2` | 1,82 | 1,18 | −35% |

A diferença mais marcante é o `scale_pos_weight = 2,40` — v3 elevou esse parâmetro próximo ao limite superior do espaço [0,5; 3,0]. Interpretação: sem a *feature* de cascata, o modelo precisa pesar positivos para cima para manter sensibilidade. Isso é precisamente o que explica o salto de *recall*: o v3 emite mais alertas, e em particular emite alertas mesmo na **ausência** de DG anterior recente.

#### GATE MARCO 1 com v3 (re-confirmado)

Critério A (val ≥ 0,2897): **0,7132 ✓** (folga +42,4pp).
Critério B (test ≥ 0,6303): **0,8556 ✓** (folga +22,5pp).

#### Trade-off honesto e calibração

**Trade-off assumido:** v3 perde leve agregado mas é qualitativamente melhor onde importa operacionalmente (primeiros DGs). A *Recall@0.5* mais alta também implica **mais falsos positivos** no agregado — se a Vale preferir menos alertas em deployment, basta calibrar o *threshold* acima de 0,5. O AUC-PR é insensível ao *threshold* e é a métrica que melhor compara modelos; ela mostra que v3 perde apenas 0,62pp no geral, então a curva inteira é praticamente idêntica.

> 📘 **Análise SHAP do v3** (`08f_shap_v3.py`) é apresentada na subseção imediatamente seguinte — valida que a remoção da *feature* de cascata redistribuiu o peso para sinais antecipativos legítimos (e não criou outra "feature dominante" problemática).

---

### Análise SHAP do LightGBM v3 (`08f_shap_v3.py`)

Para validar que a remoção de `horas_desde_ultimo_DG` redistribuiu o peso do modelo para *features* antecipativas legítimas — e não criou uma nova "*feature* dominante problemática" — foi executada análise SHAP do v3 sobre o test set completo (71.089 eventos, ~1,7 min via TreeSHAP). Matriz canônica: `shap_values_v3_test.npy` (18,4 MB, [71.089 × 34]).

> 📘 **Configuração técnica (igual ao 08c, ajustada para v3):** ver [`notas_metodologicas.md` Seção 10](notas_metodologicas.md). **Script:** `Projeto/codigo/08f_shap_v3.py`. **Saídas:** matriz SHAP + 2 tabelas (`shap_global_v3.csv`, `shap_estratificado_v3.csv`) + 3 figuras (Fig 9c bar, Fig 9d beeswarm, Fig 10b dependence plots).

#### Ranking de importância global — v3

[Figura 9c — Importância global das features (SHAP) - v3](figuras/fig09c_shap_bar_v3.png)
[Figura 9d — Distribuição dos SHAP values por feature - v3](figuras/fig09d_shap_beeswarm_v3.png)

| Rank | Feature | Família | mean(\|SHAP\|) | % do peso | Era no v2 |
|---:|---|---|---:|---:|---|
| **1** | `qtd_alarmes_nivel_muito_alto_360min` | 6 — Regra de Negócio | 1,584 | **41,0%** | #2 (31,1%) |
| **2** | `tipo_caminhao` | 7 — Encoding | 0,922 | **23,9%** | #4 (5,0%) |
| **3** | `razao_alarme_7d_vs_30d_anterior` | 4 — Regimal | 0,428 | **11,1%** | #3 (8,6%) |
| 4 | `tag_freq` | 7 — Encoding | 0,128 | 3,3% | #5 (1,7%) |
| 5 | `mes` | 0 — Básicas | 0,081 | 2,1% | #9 (0,9%) |
| 6 | `razao_severidade_14d_vs_60d` | 4 — Regimal | 0,076 | 2,0% | #8 (1,0%) |
| 7 | `frota_793D_4S` | 7 — Encoding | 0,073 | 1,9% | — |
| 8 | `taxa_DG_operador_30d` | 5 — Operador | 0,069 | 1,8% | — |
| 9 | `frota_793D_5S` | 7 — Encoding | 0,058 | 1,5% | — |
| 10 | `count_total_24h` | 1 — Rolling | 0,051 | 1,3% | #6 (1,1%) |
| 11 | `horas_desde_ultimo_critico` | 2 — Recência | 0,043 | 1,1% | #7 (1,0%) |

**Top 3 explicam 76,0% do peso; top 10 explicam 89,9%.** Distribuição similar ao v2 em concentração agregada (top 10 v2: 91%), mas **com composição qualitativamente diferente**: as três *features* dominantes do v3 são todas antecipativas legítimas.

#### Validação da promoção — quatro perguntas centrais

**1. v3 NÃO criou nova "feature dominante problemática".** A nova top 1 (`qtd_alarmes_nivel_muito_alto_360min`, 41%) é *feature* da **Família 6 (Regra de Negócio)** — conta exclusivamente alarmes nas 82 regras CMA "Muito Alto" das últimas 6 horas. É sinal **antecipativo direto** (não lê DGs passados como fazia `horas_desde_ultimo_DG` no v2). A semântica passou de "houve DG recente?" para "houve acúmulo de alarmes graves nas últimas 6 horas?" — pergunta operacionalmente acionável.

**2. `horas_desde_ultimo_critico` NÃO herdou o papel da *feature* removida.** Ficou em rank #11 (1,1% do peso, vs 1,0% no v2 — praticamente inalterado). Isso confirma que a remoção foi cirúrgica: o sinal "DG anterior" no v2 era específico e não foi simplesmente transferido para a versão "alarme crítico anterior". Família 2 (Recência) ficou virtualmente neutra no v3.

**3. Família 4 regimal (Família 4) ganhou peso.** `razao_alarme_7d_vs_30d_anterior` subiu de 8,6% (#3 em v2) para 11,1% (#3 em v3); `razao_severidade_14d_vs_60d` subiu de 1,0% (#8) para 2,0% (#6). Família 4 dobrou seu peso conjunto (de 9,6% para 13,1%) — coerente com a hipótese de que sem a *feature* de cascata, sinais regimais ganham importância para distinguir regime junho (CA65926) de regime jan-abr.

**4. `tipo_caminhao` quase quintuplicou (5,0% → 23,9%).** Esse é o achado mais marcante e merece análise honesta:

#### Achado importante e nuance — `tipo_caminhao` virou rank #2 com 24%

Sem a *feature* de cascata, o modelo passou a depender mais fortemente da diferenciação entre **caminhões** (`tipo_caminhao = 1`, taxa de DG ~3,8%) e **escavadeiras** (`tipo_caminhao = 0`, taxa LeTourneau ~0,17% — H4.1 confirmada empiricamente em W5). Operacionalmente isso significa que o v3 aprendeu **base rate por tipo de equipamento** como heurística principal — predição inicial é "caminhão = mais provável DG; escavadeira = menos provável", refinada depois pelas *features* de Família 6 e 4.

**Defesa metodológica:** essa é a estratégia correta dado os dados — a frota LeTourneau L 1850 realmente tem 22× menos DGs por equipamento, e ignorar essa diferença reduziria desempenho. **Não é viés operacional injusto** (o modelo não está "discriminando equipamentos sem razão"), mas é importante registrar em CM 6.1 como **observação interpretativa**: o v3 trata as duas frotas como populações estatisticamente diferentes desde o início da predição.

**Implicação operacional:** em deployment, se a Vale incluir uma frota nova (não vista no treino), `tipo_caminhao` corretamente classificaria-a, mas eventual sub-frota ainda mais específica poderia precisar de calibração local. **Material para CM 6.2 (limitação L8 — composição da frota influencia base rate aprendida).**

#### Análise estratificada — CA65926 vs resto do test

| Rank | CA65926 (9,96% do test) | Resto do test (90,04%) |
|---:|---|---|
| 1 | `qtd_alarmes_muito_alto` (~40%) | `qtd_alarmes_muito_alto` (~41%) |
| 2 | `tipo_caminhao` (~24%) | `tipo_caminhao` (~24%) |
| 3 | `razao_alarme_7d_vs_30d` (~12%) | `razao_alarme_7d_vs_30d` (~11%) |

(Detalhes completos em `shap_estratificado_v3.csv`, 50 linhas: 5 subgrupos × top 10.)

**Top 3 idênticos** entre CA65926 e resto — mesma estratégia, mesmo ordenamento. Coerente com o achado do v2: o modelo não opera por "regras especiais para equipamento problemático", e sim por **distribuição de pesos diferentes** sobre as mesmas *features*. CA65926 dá levemente mais peso a `razao_alarme_7d_vs_30d` (~12% vs 11%) — coerente com a Obs 2.9 (anomalia regimal localizada captada pela Família 4).

#### Síntese para o relatório — o que SHAP v3 sustenta

| Pergunta | Resposta empírica do SHAP v3 |
|---|---|
| Modelo é cascade detector? | **Não** — top 3 (`qtd_alarmes_muito_alto`, `tipo_caminhao`, `razao_alarme_7d_vs_30d`) são todas antecipativas, somando 76% do peso |
| Família 6 domain-specific venceu Família 1 genérica? | **Sim, ainda mais claramente que em v2** — Família 6 (1 feature) = 41% do peso vs Família 1 (15 features) = ~7% |
| Família 4 regimal sustenta sua relevância? | **Sim e ampliada** — peso conjunto subiu de 9,6% (v2) para 13,1% (v3) |
| Família 5 operador continua difusa (Q3 do edital)? | **Sim** — `taxa_DG_operador_30d` rank #8, `operador_freq` rank #12; sinal real mas distribuído |
| Concentração no top 1 reduziu? | **Não em magnitude** (41% vs 39%), **mas mudou de natureza** — agora é antecipativa legítima |

**Lição metodológica reforçada para CM 6.1:** a comparação SHAP v2 vs SHAP v3 demonstra que **modelos com AUC-PR similar podem ter estratégias internas radicalmente diferentes**. Sem SHAP, a substituição v2 → v3 seria invisível operacionalmente (ambos passam o GATE), mas o v3 entrega exatamente o tipo de predição que a Vale precisa (antecipação) em vez do que o v2 acabou fazendo (detecção de cascata).

#### Explicação local de uma predição individual (Figura 12)

A importância global (Fig 9c/9d) responde "quais *features* o modelo usa em média"; a explicação **local** responde "por que ESTE alerta específico disparou". A Figura 12 é o *waterfall* SHAP de uma predição individual, decompondo o caminho do valor base (log-odds médio do modelo, `E[f(x)] = −0,99`) até o score final do evento.

[Figura 12 — SHAP waterfall de uma predição individual - v3](figuras/fig12_shap_waterfall_v3.png)

> 📘 **Script:** `Projeto/codigo/20_shap_waterfall_v3.py`. **Saídas:** `fig12_shap_waterfall_v3.png` + `shap_waterfall_evento.csv` (34 contribuições). O evento foi selecionado por critério principiado: verdadeiro positivo na faixa vermelha (acerto), **fora do CA65926** (demonstra generalização além do equipamento dominante do test, L10), e com contribuições diversificadas.

O evento selecionado é da TAG **CA65933** (caminhão 793-D 5S, não o CA65926), em 04/jun/2025 (semana 1, regime "calmo" anterior à explosão do CA65926), com alarme `Engine Coolant Level - Active` (o alarme #1 do semestre). O modelo previu **p(DG em 4h) = 0,969** e um DG realmente ocorreu na janela. A decomposição:

| Feature | Valor no evento | Contribuição SHAP (log-odds) | Leitura |
|---|---:|---:|---|
| `qtd_alarmes_nivel_muito_alto_360min` | 322 | **+2,94** | 322 alarmes "Muito Alto" da CMA em 6h, sinal antecipativo dominante |
| `razao_alarme_7d_vs_30d_anterior` | 3,98 | **+0,84** | alarme disparando ~4× o *baseline* histórico do próprio equipamento |
| `tipo_caminhao` | 1 | **+0,40** | base rate de caminhão (vs escavadeira) eleva a probabilidade |
| `count_nao_critico_8h` | 348 | +0,09 | volume recente de eventos não-críticos |

**Por que esta figura fecha a narrativa da promoção do v3:** as três *features* que sustentam o alerta são exatamente as antecipativas legítimas (Família 6 regra de negócio, Família 4 regimal, base rate por tipo), não a *feature* de cascata removida. O exemplo ocorre num caminhão comum, num regime calmo, fora do CA65926, e ainda assim o modelo antecipa corretamente o DG via acúmulo de alarmes graves, demonstrando que o v3 generaliza para além do equipamento dominante do test set. Material direto para CM 5.3 (interpretabilidade local).

---

### Modelo de Sobrevivência — Weibull AFT como segunda leitura (`09_sobrevivencia.py`)

O modelo Weibull AFT (Accelerated Failure Time) é o **segundo modelo canônico do relatório** — segunda leitura do problema "antecipar DG", independente do LightGBM v3. Implementa o objetivo do CM 4.3: "dois modelos bem feitos > cinco superficiais", oferecendo três contribuições que o LightGBM v3 não oferece sozinho:

1. **Tratamento rigoroso do *censoring*** (102.602 eventos sem DG futuro observado tratados como dado adicional, não como `y = 0`).
2. **Interpretabilidade intrínseca** via *Time Ratios* (TR) com IC 95% e p-valor por feature — sem método post-hoc tipo SHAP.
3. **Predição em qualquer horizonte temporal** via `S(t)` — não apenas o horizonte fixo de 4 h do LightGBM.

> 📘 **Detalhes técnicos completos (construção de (T, E), imputação de NaN, filtro de correlação, fallback Cox PH, bug do C-index do Weibull corrigido durante execução):** ver [`notas_metodologicas.md` Seção 13](notas_metodologicas.md). **Script:** `Projeto/codigo/09_sobrevivencia.py` (~56 s). **Saídas:** modelo `Projeto/modelos/sobrevivencia.joblib` (14,5 MB) + 3 tabelas + 1 figura (`figExA_kaplan_meier_por_frota.png`).

#### Construção dos dados de sobrevivência (T, E)

Para cada um dos 544.722 eventos do `v3.parquet` (após filtrar 163 com T = 0):

- **T = horas até o próximo DG da mesma TAG** (via `join_asof` forward), ou **horas até a última observação da TAG** se não houver DG futuro
- **E = 1** se evento observado, **0** se censurado

A distribuição de *censoring* por *split* revela uma assimetria importante:

| Split | Total | E = 1 (observado) | E = 0 (censurado) | % censurado |
|---|---:|---:|---:|---:|
| train | 394.863 | 331.619 | 63.244 | **16,0%** |
| val | 78.816 | 60.159 | 18.657 | 23,7% |
| test | 71.043 | 30.184 | 40.859 | **57,5%** |

O test (jun/2025) tem 57,5% de eventos censurados porque é o último mês observado — eventos próximos do fim de junho não têm tempo de "ver" um DG futuro. Esse padrão difere fortemente do treino (16%), e é uma limitação intrínseca da janela de 6 meses. **Material para CM 6.2.**

#### Configuração metodológica (3 decisões aprovadas em 24/05)

1. **Filtro de correlação > 0,9 antes do fit** — Cox/Weibull são sensíveis a multicolinearidade. 6 *features* da Família 1 removidas (`count_critico_2h`, `count_critico_8h`, `count_nao_critico_2h`, `count_total_1h`, `count_nao_critico_8h`, `count_total_4h`).
2. **Fallback automático para Cox PH se Weibull AFT não convergir OU C-index val < 0,6** — implementado e testado. **Não foi acionado:** Weibull convergiu com C-index val = 0,7097.
3. **34 features alinhadas ao v3 canônico** (sem `horas_desde_ultimo_DG`) — após filtro de correlação e *one-hot* das categóricas, restam **31 features** no fit.

**Imputação de NaN** (Cox/Weibull não toleram NaN, diferente do LightGBM): `razao_*` → 1,0 (neutro semântico); `taxa_DG_operador_30d` → mediana do treino; `horas_desde_ultimo_critico` → max do treino. Estratégia salva no artefato `.joblib` para reprodutibilidade.

#### Resultados

| Métrica | train | val | test |
|---|---:|---:|---:|
| C-index | 0,7517 | 0,7097 | **0,7444** |
| AUC-PR(target_4h) | 0,6487 | 0,4126 | **0,3153** |

**Tempo total:** 56 s (Weibull AFT fit 37 s + avaliação/figuras 19 s).

#### Top 10 hazard ratios (Time Ratios) — interpretabilidade direta com IC 95%

Em modelos AFT, **TR = exp(coef) é o *time ratio***: TR < 1 significa que aumentar a feature em 1 unidade (após StandardScaler) **reduz** o tempo esperado de sobrevida em fator TR; TR > 1 significa que **aumenta** a sobrevida.

| # | Covariate | TR | IC 95% | p | Direção |
|---:|---|---:|---|---:|---|
| 1 | `tag_freq` | 1,432 | [1,41–1,45] | < 0,0001 | Maior frequência → maior sobrevida |
| 2 | **`tipo_caminhao`** | **0,038** | [0,04–0,04] | < 0,0001 | **Caminhão vs escavadeira → sobrevida 3% (efeito massivo)** |
| 4 | **`frota_793D_5S`** | **0,169** | [0,16–0,18] | < 0,0001 | Frota 5S → sobrevida 17% (maior risco entre 793-D) |
| 5 | `frota_793D_2S` | 0,357 | [0,34–0,38] | < 0,0001 | Frota 2S → sobrevida 36% |
| 6 | `frota_793D_4S` | 0,450 | [0,43–0,47] | < 0,0001 | Frota 4S → sobrevida 45% |
| 7 | `frota_793D_3S` | 0,364 | [0,34–0,39] | < 0,0001 | Frota 3S → sobrevida 36% |
| 8 | `operador_freq` | 1,124 | [1,11–1,14] | < 0,0001 | Operadores conhecidos → sobrevida +12% |
| 9 | `valor_disponivel` | 1,224 | [1,20–1,25] | < 0,0001 | Sensor disponível → sobrevida +22% |
| 10 | `count_critico_24h` | 0,844 | [0,83–0,86] | < 0,0001 | Acúmulo críticos 24 h → sobrevida −16% |

Todos com p-valor < 0,0001 (significância forte dado n = 394.863 no treino).

#### Concordância com SHAP v3 (CM 5.3 — validação cruzada entre dois métodos independentes)

A correspondência entre os **top features** do Weibull AFT (via hazard ratios) e do LightGBM v3 (via SHAP) é forte:

| Feature | SHAP v3 (LightGBM) | Weibull AFT (TR) | Interpretação cruzada |
|---|---|---|---|
| `tipo_caminhao` | #2 (23,9%) | TR=0,038, rank #2 | **Ambos identificam como driver principal** — H4.1 confirmada em duas técnicas independentes |
| Família frota (4 dummies) | distribuída em #7, #9 | ranks #4-#7 (TR 0,17-0,45) | Ambos reconhecem heterogeneidade entre frotas 793-D |
| `razao_alarme_7d_vs_30d_anterior` | #3 (11,1%) | significativa (p < 0,0001) | Família 4 regimal valida em ambos |
| `operador_freq` | #12 (0,84%) | rank #8 (TR=1,12) | Ambos: sinal modesto mas significativo (Q3 difuso) |
| `tag_freq` | #4 (3,3%) | rank #1 (TR=1,43) | Ambos no top — TAG identifica equipamento, e equipamento importa |

**Esse alinhamento é evidência forte de validade das estratégias aprendidas.** Duas técnicas com fundamentação matemática radicalmente diferente — TreeSHAP via Shapley values em gradient boosting vs maximum likelihood em modelo paramétrico AFT — chegam às mesmas variáveis-chave. Material direto para CM 5.3.

**Discordância importante e instrutiva:** LightGBM v3 (SHAP) dá peso massivo a `qtd_alarmes_muito_alto_360min` (41%, top 1). Weibull AFT NÃO destaca essa feature no top 10. Razão metodológica: o LightGBM v3 prediz **DG em 4 h específico** (sinal de Família 6 brilha em horizonte curto); o Weibull AFT modela **tempo até qualquer DG futuro** (sinais de base rate — frota, tipo, operador — brilham em horizonte amplo). Os dois modelos respondem perguntas diferentes. Material para CM 6.1 (Insight Não Óbvio).

#### Comparação operacional v3 vs Weibull AFT — usos complementares

| Característica | LightGBM v3 | Weibull AFT |
|---|---|---|
| AUC-PR test (target_4h) | **0,8556** | 0,3153 |
| C-index test | — | **0,7444** |
| Tratamento de censoring | Aproximação (target=0) | **Rigoroso** |
| Interpretabilidade | SHAP (post-hoc) | **HR + IC 95% + p-valor (intrínseca)** |
| Horizonte de predição | Fixo (4 h) | **Qualquer t** |
| Custo computacional | 25,7 min (Optuna) | **0,9 min** |
| Caso de uso operacional | **Alerta de curto prazo (4 h)** | Análise estratégica / planejamento de manutenção / *risk scoring* multi-horizonte |

**O Weibull AFT NÃO substitui o LightGBM v3** para o caso de uso operacional do desafio (alerta 4 h antes do DG) — claramente inferior em AUC-PR. Mas oferece os três valores complementares listados acima, que fortalecem a entrega do relatório.

#### Kaplan-Meier por frota (Fig Extra A)

[Figura Extra A — Curva Kaplan-Meier por frota (7 dias)](figuras/figExA_kaplan_meier_por_frota.png)

A figura mostra a sobrevida empírica (sem ajuste por *covariates*) por frota nos primeiros 7 dias após cada evento. **Validação visual da H4.1:** a curva da LeTourneau L 1850 fica muito acima das curvas das frotas 793-D — a escavadeira "sobrevive" mais entre DGs por simplesmente ter ~22× menos DGs por equipamento. Entre as frotas 793-D, há heterogeneidade (5S = mais antiga, maior risco; 4S = mais recente, menor risco), coerente com os TRs do Weibull AFT.

---

### Isolation Forest — diagnóstico do Risco 3.3 (`11_isolation_forest.py`)

O Isolation Forest é o **terceiro modelo do relatório**, com função diagnóstica única: validar empiricamente que o rótulo `Is_Dont_Go` (gerado por 82 regras CMA "Muito Alto") captura **anomalias mecânicas reais** e não apenas dispara regras de negócio arbitrárias. **Treinado de forma não-supervisionada** (sem ver `Is_Dont_Go`), responde diretamente o **Risco 3.3** identificado no início do projeto.

> 📘 **Configuração técnica, decisões de imputação, contamination thresholds, lógica de estratificação CA65926:** ver [`notas_metodologicas.md` Seção 14](notas_metodologicas.md). **Script:** `Projeto/codigo/11_isolation_forest.py` (~10,8 s). **Saídas:** modelo `Projeto/modelos/isolation_forest.joblib` (0,58 MB) + 4 tabelas + 1 figura (`figExD_isolation_forest_diagnostico.png`).

#### Configuração

- Mesmas 34 *features* do v3 canônico (alinhamento direto com LightGBM v3 e Weibull AFT — comparabilidade)
- 200 árvores, `random_state = 42`, `contamination = "auto"` (thresholds derivados *post-hoc*)
- StandardScaler + imputação NaN igual ao `09_sobrevivencia.py` (consistência)
- Avaliado em 4 *contaminations* [0,01; 0,03; 0,05; 0,10] para curva completa de P/R

#### Achado central — assimetria forte entre regimes

AUC-ROC do `anomaly_score` contra `Is_Dont_Go`:

| Split | n | n_DG | Prevalência | AUC-ROC |
|---|---:|---:|---:|---:|
| train | 394.971 | 13.456 | 3,41% | 0,5753 |
| val | 78.825 | 1.280 | 1,62% | 0,5979 |
| **test** | **71.089** | **5.226** | **7,35%** | **0,8603** |

**Padrão atípico:** train e val ~0,58 (quase aleatório), test 0,86 (forte). A diferença sugeriu hipótese imediata: o sinal de test é dirigido pela anomalia dominante do CA65926 (Obs 2.9 — 82,2% dos DGs de jun vêm desse único equipamento). Estratificação confirma:

| Subgrupo do test | n | n_DG | AUC-ROC |
|---|---:|---:|---:|
| Test completo | 71.089 | 5.226 | 0,8603 |
| **CA65926 apenas** | **7.083** | **4.298** | **0,8969** |
| **Test sem CA65926** | **64.006** | **928** | **0,5409** |

**Achado decisivo:** sem CA65926, a sobreposição IF-CMA cai para 0,54 (essencialmente aleatória). Os 86% de sobreposição agregada são **completamente dirigidos pela detecção do CA65926** — não representam padrão geral.

#### Análise estrutural — AUC-ROC por TAG no test (30 TAGs, 26 com AUC válido)

Para confirmar estruturalmente que o achado não é específico da hipótese CA65926, foi computado AUC-ROC para **cada uma das 30 TAGs** presentes no test. Resultado consolidado:

| Top 5 TAGs (AUC ≥ 0,75) | n | n_DG | prev_DG | AUC | Sample válido? |
|---|---:|---:|---:|---:|---|
| PE3797 | 9.690 | 1 | 0,01% | 0,9263 | ❌ (n_DG=1, artefato amostral) |
| PE3795 | 5.013 | 3 | 0,06% | 0,9254 | ❌ (n_DG=3, artefato amostral) |
| **CA65926** | **7.083** | **4.298** | **60,68%** | **0,8969** | ✅ sinal real e forte |
| CA65932 | 584 | 24 | 4,11% | 0,8367 | ✅ sinal real, sample modesto |
| **CA65924** | **1.097** | **25** | **2,28%** | **0,7915** | ✅ **caso paradigma de W4 — validado** |

| Estatística agregada | Valor |
|---|---:|
| AUC mediana (26 TAGs válidas) | **0,6060** |
| AUC média | 0,6377 |
| TAGs com AUC ≥ 0,75 (sinal forte) | 5 de 26 |
| **Dessas, com sample significativo (n_DG ≥ 10)** | **3 de 26** |
| TAGs com AUC < 0,55 (~aleatório) | 8 de 26 |

**Três leituras críticas que a análise por TAG entrega:**

1. **Agregado é enganoso, mediana é honesta.** O AUC agregado de 0,86 vinha da soma ponderada por número de eventos — o CA65926 dominava o cálculo. A **mediana por TAG = 0,61** é uma medida muito mais honesta do sinal *típico* em deployment, onde cada equipamento opera com sua base rate própria.

2. **Sinal real concentrado em 3 equipamentos.** Das 5 TAGs com AUC ≥ 0,75, duas (PE3797, PE3795 — escavadeiras LeTourneau) têm apenas 1 e 3 DGs respectivamente — o AUC alto é artefato amostral. Restam **CA65926, CA65932 e CA65924** como casos com sinal forte E sample significativo. Para mais de 88% dos equipamentos analisados (23 de 26), o IF é fraco ou aleatório.

3. **Validação independente do W4 — caso paradigma CA65924.** O Isolation Forest, **sem ver o rótulo `Is_Dont_Go`**, identifica o CA65924 como anômalo (AUC=0,79). Isso valida que a investigação de W4 acertou em escolher o CA65924 como caso paradigma da Obs 2.3 (refutação do padrão "calmaria → acúmulo" universal). **Convergência metodológica adicional.**

[Figura Extra D — Isolation Forest: diagnóstico do viés do label CMA (4 painéis)](figuras/figExD_isolation_forest_diagnostico.png)

A figura agora tem 4 painéis: (a) curva P/R/F1 por contamination; (b) histograma do anomaly_score por classe; (c) barras de AUC-ROC por split (assimetria train/val/test); (d) **barras horizontais de AUC-ROC por TAG, coloridas por log10(n_DG)** — revela visualmente que o sinal forte está concentrado em poucos equipamentos com base rate alta.

#### Curva Precision/Recall — sinal real no agregado (com nuance)

| Contamination | n_anom | Precision | Recall | Lift vs random (×) |
|---:|---:|---:|---:|---:|
| 0,01 | 712 | 0,9017 | 0,1228 | 12,3 |
| 0,03 | 2.133 | 0,6484 | 0,2646 | 8,8 |
| 0,05 | 3.572 | 0,5465 | 0,3735 | 7,4 |
| 0,10 | 7.111 | 0,4085 | 0,5559 | 5,6 |

Lifts altos confirmam que `anomaly_score` discrimina DG vs não-DG no agregado. **Mas, dado o achado estratificado, esse poder discriminativo vem majoritariamente de "detectar CA65926"** — o que para fins de auditoria do rótulo CMA significa: a CMA capturou genuinamente o CA65926, mas pode estar capturando outros DGs sem assinatura estatística clara.

[Figura Extra D — Isolation Forest: diagnóstico do viés do label CMA](figuras/figExD_isolation_forest_diagnostico.png)

A figura tem 3 painéis: (a) curva P/R/F1 por contamination com prevalência marcada como referência aleatória; (b) histogramas do `anomaly_score` para DG vs não-DG (sobreposição visual significativa, com cauda direita do não-DG indicando os FPs interpretáveis como "DGs perdidos pelo CMA"); (c) barras de AUC-ROC por split mostrando a assimetria train/val/test.

#### Veredito do Risco 3.3 — parcialmente mitigado (assimétrico por regime)

A síntese honesta divide o veredito por regime:

- ✅ **Para anomalias dominantes (CA65926-like, falhas mecânicas progressivas):** Isolation Forest e CMA concordam fortemente (AUC = 0,90). O rótulo CMA captura anomalia estatisticamente real nesse regime. **Risco 3.3 mitigado.**
- ⚠️ **Para DGs distribuídos (90% dos equipamentos):** Isolation Forest e CMA discordam (AUC = 0,54, quase aleatório). O rótulo CMA pode estar capturando eventos sem assinatura estatística distintiva no espaço de *features* atual. **Risco 3.3 parcialmente confirmado nesse regime.**

#### Convergência com SHAP e Weibull AFT — três técnicas, mesma conclusão (CM 6.1)

| Técnica | Achado convergente |
|---|---|
| SHAP do v3 | `tipo_caminhao` (24%) e Família 4 regimal (11%) no top — modelo aprende "esse equipamento costuma falhar" |
| Weibull AFT | `tipo_caminhao` TR=0,038, `frota_793D_5S` TR=0,169 — mesmo padrão estatístico |
| Isolation Forest | AUC=0,90 em CA65926 vs 0,54 em outros — confirma que sinal é equipamento-específico |

**As três técnicas concordam que o CA65926 é o equipamento mais saliente do test set**, mas é preciso separar dois fatos que a primeira leitura confundia. (i) O **sinal estrutural não-supervisionado** (Isolation Forest, sobre `Is_Dont_Go`) é fortemente dominado pelo CA65926: sem ele, o AUC-ROC do IF cai de 0,86 para 0,54 (quase aleatório). Isso é um achado sobre o **rótulo CMA** (Risco 3.3), não sobre o classificador. (ii) O **modelo supervisionado v3**, ao contrário, **generaliza para além do CA65926** — a estratificação direta do próprio v3 (`22_v3_estratificado_ca65926.py`, ver abaixo) mostra que sem o CA65926 a AUC-PR cai apenas de 0,8556 para 0,7693 e a AUC-ROC fica praticamente intacta (0,9391 → 0,9368). A convergência, portanto, é sobre a **natureza atípica do test e o viés do rótulo**, não sobre uma suposta dependência do v3 de um único equipamento. Material para **CM 6.1 (Insight Não Óbvio)**: técnicas independentes iluminam aspectos diferentes (o IF expõe o viés do rótulo; o SHAP e o Weibull mostram que o v3 usa sinais generalizáveis de identidade e regime).

#### Implicação operacional — limitação L10 para CM 6.2 (re-nuançada com o número do próprio v3)

A leitura inicial, apoiada no colapso do Isolation Forest (0,86 → 0,54), sugeria que a performance do v3 seria "largamente dirigida" pelo CA65926. A medição direta do próprio modelo refuta essa leitura. Estratificando a AUC-PR do v3 por equipamento no test:

| Subgrupo | n | prevalência | AUC-PR | AUC-ROC | lift sobre o acaso |
|---|---:|---:|---:|---:|---:|
| Teste completo (com CA65926) | 71.089 | 0,169 | 0,8556 | 0,9391 | 5,06× |
| CA65926 apenas | 7.083 | 0,809 | 0,9723 | 0,8762 | **1,20×** |
| Teste sem CA65926 | 64.006 | 0,099 | 0,7693 | 0,9368 | **7,77×** |

Remover o CA65926 derruba a AUC-PR em apenas 8,63pp (não um colapso), e a AUC-ROC fica essencialmente inalterada. Mais importante, em termos de **lift** (AUC-PR sobre a prevalência, que é o "acaso" da métrica), o modelo é **mais forte nos outros 29 equipamentos** (7,77×) do que no próprio CA65926 (1,20×). O CA65926 tem prevalência de 80,9% no seu subconjunto, então até um chute trivial acerta 0,81 ali; ele **infla o número absoluto** sem refletir habilidade discriminativa. **A formulação honesta e correta da L10 é:** o AUC-PR absoluto de 0,8556 é parcialmente inflado pela alta prevalência do CA65926 no test, mas a **capacidade de generalização do v3 é genuína** (AUC-ROC estável e lift maior nos demais equipamentos). A crítica "o modelo só detecta um equipamento" fica refutada pelos próprios números do classificador. O que permanece como limitação real é o **viés do rótulo CMA** evidenciado pelo IF (Risco 3.3), não a fragilidade do v3.

**Recomendações para deployment (CM 6.3):**

1. Monitoramento estratificado por equipamento em produção (dashboard com AUC-PR por TAG).
2. Retreino *rolling* mensal já planejado (CM 6.3, registrado em 2026-05-22) — reforçado por este achado.
3. Investigar os FPs do IF como possíveis "DGs perdidos pelo CMA" — leitura inversa do Risco 3.3, análise manual de amostra recomendada.
4. Estender janela de observação para múltiplos anos — diluir o efeito de equipamentos individuais problemáticos.

---

### Fechamento de W6 — análises complementares (validação cruzada + Fig 9 + calibração + ablation)

Quatro análises menores fecham a modelagem antes de avançar para avaliação estratificada (W7). Cada uma resolve um item específico do CM correspondente.

#### Validação cruzada SHAP × Hazard Ratios (`12_validacao_sentido_features.py`) — CM 5.3

A validação cruzada entre as importâncias do LightGBM v3 (via SHAP) e os *time ratios* do Weibull AFT é um teste empírico forte de **validade**: dois métodos com fundamentação matemática completamente diferente (TreeSHAP via Shapley values + maximum likelihood AFT) chegando ao mesmo conjunto de *features* importantes é evidência de que o sinal aprendido é real, não artefato de uma escolha de modelo.

**Features no top 10 de AMBOS:** `tipo_caminhao` (SHAP #2 / Weibull #1), `tag_freq` (SHAP #4 / #7), `frota_793D_4S` (SHAP #7 / #6), `frota_793D_5S` (SHAP #9 / #2). **Todas estruturais — identidade do equipamento.**

**Divergências instrutivas:** *features* antecipativas dominantes no SHAP (`qtd_alarmes_muito_alto_360min` 41%, `razao_alarme_7d_vs_30d_anterior` 11%) NÃO aparecem no top do Weibull. Razão metodológica: LightGBM v3 prediz DG **em 4 h específico** — sinais imediatos brilham; Weibull AFT modela **tempo até qualquer DG** — sinais de base rate estrutural brilham. **Os dois modelos respondem perguntas diferentes** — usá-los em conjunto fortalece a entrega (CM 6.1).

(Tabela completa em `relatorio/tabelas/validacao_sentido_features.csv`; detalhes em `notas_metodologicas.md` Seção 15.)

#### Fig 9 — Curvas ROC + Precision-Recall comparativas (`13_curvas_comparativas.py`) — CM 5.1

[Figura 9 — Comparativo dos 3 modelos no test set](figuras/fig09_curvas_comparativas.png)

Curvas comparando os três modelos finais (Baseline / LightGBM v3 / Weibull AFT) no test (jun/2025, n = 71.089):

| Modelo | AUC-ROC | AUC-PR |
|---|---:|---:|
| Baseline (count_critico_4h) | 0,7661 | 0,5803 |
| **LightGBM v3 (canônico)** | **0,9391** | **0,8556** |
| Weibull AFT (P(T≤4h)) | 0,7869 | 0,3148 |

**v3 domina em AUC-PR** (+27,5pp vs baseline, +54pp vs Weibull) — é o modelo operacional. **Weibull supera baseline em AUC-ROC** mas perde em AUC-PR — coerente com a natureza do modelo (otimiza C-index de ranking, não classificação binária em 4 h específico). Os três modelos servem propósitos diferentes; nenhum substitui o outro completamente.

#### Calibração do v3 + Platt scaling (`14_calibracao_v3.py`) — CM 5.2 + nota em L4

Análise da calibração das probabilidades preditas pelo v3 (`P(y=1)` predita ≈ fração real?). Métricas: Brier score e ECE (Expected Calibration Error) em 10 bins.

**v3 raw (sem calibração):**

| Split | Brier | Skill | ECE |
|---|---:|---:|---:|
| val | 0,09141 | +0,3904 | 3,70pp |
| test | 0,05745 | **+0,5916** | 3,78pp |

**Skill +0,59 no test** — modelo é substancialmente melhor que predição constante. **Mas ECE 3,7-3,8pp** está acima do limiar a priori de 2pp, justificando testar Platt scaling.

**Resultado do Platt scaling (regressão logística sobre val):**

| Split | ECE raw | ECE pós-Platt | Δ ECE |
|---|---:|---:|---:|
| val | 3,70pp | **1,87pp** | **−1,83pp** (melhora) |
| test | 3,78pp | **4,76pp** | **+0,98pp** (piora!) |

**Achado importante:** Platt melhora val (esperado, foi fitado lá) mas **piora test**. Isso indica **drift de calibração entre val e test** — outro sintoma da L4 (drift mai→jun dominado pelo CA65926). **Recomendação operacional honesta: NÃO aplicar Platt em deployment** — manter v3 raw. O calibrador Platt fica salvo apenas para auditoria.

[Figura Extra F — Calibração do v3](figuras/figExF_calibracao_v3.png)

A figura tem 2 painéis: (a) curva de calibração comparando v3 raw vs v3 + Platt no test contra a diagonal "calibração perfeita"; (b) histograma das probabilidades preditas separadas por classe — mostra que o modelo é confiante nas extremidades mas há massa relevante em meio-range (incerteza honesta).

#### Ablation por grupo de features (`15_ablation_grupos.py`) — Profundidade 2 + CM 6.1

Re-treina v3 com hiperparâmetros FIXOS (best Optuna, sem re-tuning) removendo cada **grupo** de *features* para medir queda de AUC-PR. 7 grupos disjuntos cobrindo as 34 *features* do v3.

[Figura Extra E — Ablation por grupo de features](figuras/figExE_ablation_grupos.png)

| Grupo | n removidas | AUC-PR test | Δ vs baseline (0,8556) |
|---|---:|---:|---:|
| **G7 regimal** (Família 4: razao_alarme, razao_severidade) | 2 | 0,8512 | **−0,0044** |
| G3 recência (horas_desde_ultimo_critico) | 1 | 0,8574 | +0,0018 |
| G5 regra de negócio (qtd_alarmes_muito_alto_360min) | 1 | 0,8574 | +0,0018 |
| G1 temporais (hora, dia, turno, mes) | 4 | 0,8581 | +0,0025 |
| G2 rolling counts | 15 | 0,8588 | +0,0032 |
| G4 operador (3 features) | 3 | 0,8620 | +0,0064 |
| **G6 categóricas** (tag_freq, frota, tipo_caminhao, estado, valor_disp) | 8 | **0,8620** | **+0,0064** |

**Achado surpreendente:** **nenhum grupo é estritamente necessário** — variação máxima é ±0,01 AUC-PR. **Apenas G7 regimal causa queda real** (e mesmo assim minúscula, −0,51%). Vários grupos **melhoram** AUC-PR ao serem removidos (G4, G6).

**Contraste forte com SHAP — Insight Não Óbvio para CM 6.1:**

O SHAP disse que `qtd_alarmes_muito_alto_360min` é 41% do peso (rank #1) e `tipo_caminhao` é 24% (rank #2). A ablation diz que remover qualquer um dos dois **não degrada** AUC-PR. **Como conciliar?**

**SHAP mede ATRIBUIÇÃO** (quais *features* o modelo USA quando todas estão disponíveis). **Ablation mede NECESSIDADE** (quais *features* o modelo PRECISA quando uma é removida). A diferença é **REDUNDÂNCIA** — feature de alto SHAP que pode ser removida sem queda significa que o modelo encontra rotas alternativas no espaço de features para a mesma predição.

**O v3 entrega 0,8556 AUC-PR no test através de múltiplas rotas redundantes**, não através de um sinal único insubstituível. Essa redundância **sustenta a generalização documentada na L10**: como a predição se apoia em vários sinais transferíveis simultâneos (tipo_caminhao, frota, count_critico_24h, razao_alarme_*, etc.), o modelo não depende de nenhuma feature ou equipamento isolado, coerente com a manutenção do desempenho fora do CA65926 (AUC-PR 0,7693, lift 7,77×).

**Implicação operacional:** o v3 é **robusto a perda de *features*** em deployment (sensores quebrados, fontes intermitentes). Mesmo perdendo 8 das 34 *features* (G6 inteiro), AUC-PR mantém-se em 0,86. Material direto para CM 6.3 (Trabalhos Futuros — robustez operacional).

---

## Resultados — leitura para o time de negócio e operacional

Esta seção traduz os achados técnicos do projeto em **decisões e recomendações acionáveis**, com figuras desenhadas para o público de negócio. Três peças centrais consolidam a entrega:

### Caso CA65926 — janela de antecipação real de 3 meses

[Figura — Deterioração progressiva do CA65926 (jan-jun/2025)](figuras/figNeg01_timeline_ca65926.png)

A figura acima reconstrói a história operacional do **CA65926**, equipamento responsável por **24,7% de todos os DGs do semestre** (4.923 de 19.962). A leitura é direta:

- **Janeiro–fevereiro:** comportamento próximo ao baseline do parque (taxa 2-4%).
- **Março:** **sinal precursor não capturado pela operação atual** — 438 DGs (taxa 20,28%), **5× a taxa global do parque** (3,66%), mas via alarmes diversos (não o sensor que falharia em junho).
- **Abril–maio:** aparente recuperação (taxa volta a 3-13%) — equipamento parecia "controlado" pelas métricas agregadas.
- **Junho:** **crise** — 4.298 DGs (taxa **60,68%**), 98% deles via Right Front Brake Temperature, manifestação visível da falha mecânica progressiva.

**Janela de antecipação real entre sinal e crise: 3 meses.** Esse intervalo seria suficiente para auditoria física, mobilização de peça e intervenção planejada — *se a operação monitorasse taxa de DG por equipamento*, não apenas por frota.

### Ranking de risco por equipamento — onde focar a atenção

[Figura — Ranking de risco operacional dos 33 equipamentos do parque](figuras/figNeg02_ranking_risco_operacional.png)

A figura ranqueia os 33 equipamentos com telemetria significativa (≥ 100 eventos no semestre) por **volume de DGs + taxa**. Aplicando critérios operacionais combinados, o parque divide-se em:

| Nível | Critério | Quantidade | Ação recomendada |
|---|---|---:|---|
| **ALTO** 🔴 | DGs ≥ 1000 OU taxa ≥ 30% | **5 equipamentos** | Auditoria imediata + revisão da política de manutenção |
| **MÉDIO** 🟠 | DGs ≥ 200 OU taxa ≥ 5% | **18 equipamentos** | Monitoramento mensal estratificado |
| **BAIXO** 🟢 | resto | **10 equipamentos** | Operação normal (rotina padrão) |

Os 5 equipamentos em risco ALTO (CA65926, CA65931, CA65930, CA65792, CA65927) **concentram a maior parte dos DGs do parque**. Política de manutenção preventiva operada por equipamento — não por frota — captura essa heterogeneidade. Tabela completa em `relatorio/tabelas/ranking_risco_operacional.csv`.

### Valor operacional do modelo — horas de parada evitáveis

[Figura — Valor operacional do modelo: horas de parada evitáveis](figuras/figNeg03_horas_parada_evitavel.png)

Traduzindo as métricas técnicas (Recall@0.5 = 75% no geral, 21% em primeiros DGs) em **horas-equipamento de parada não planejada evitáveis** no semestre, com premissas operacionais explícitas (4h de parada corretiva por DG vs 1,5h de inspeção preventiva planejada = 2,5h preservadas por DG antecipado):

| Cenário | Recall | DGs antecipados | Horas evitadas | Redução |
|---|---:|---:|---:|---:|
| Conservador (só primeiros DGs) | 21% | 4.192 | **10.480h** | 13% |
| Realista (Recall geral do v3) | 75% | 14.971 | **37.429h** | 47% |
| Otimista (Realista + CA65926 em mar) | 75% + auditoria | 17.433 | **43.582h** | 55% |

**Base de comparação:** 79.848 horas-equipamento de parada não planejada no semestre observado (jan-jun/2025). O cenário realista converte praticamente metade dessas horas em manutenção planejada.

**Importante:** todos os cenários assumem **threshold operacional adequado** (calibrado por custo-benefício em deployment) e **monitoramento estratificado por equipamento**. Ressalva: o número de horas evitáveis depende fortemente da janela de antecipação efetiva (L12, ~18% dos acertos dão os 90 min de mobilização), e o cenário conservador é a leitura mais defensável. O `~88%` que aparecia em versões anteriores referia-se ao Isolation Forest (perda de sinal estrutural não-supervisionado fora do CA65926), e **não** à efetividade do v3, que generaliza bem (AUC-PR 0,7693 sem o CA65926, ver L10).

### Heterogeneidade entre frotas — quem opera com menos risco

[Figura Extra A — Curva Kaplan-Meier por frota (7 dias)](figuras/figExA_kaplan_meier_por_frota.png)

A análise de sobrevivência mostra a **probabilidade de um equipamento ainda não ter sofrido novo DG** em função das horas desde o último evento, separada por frota:

- **LeTourneau L 1850** (escavadeira) — curva no topo: ~92% ainda sem DG após 7 dias.
- **793-D 4S** (caminhão mais recente) — ~40% após 7 dias.
- **793-D 5S** (caminhão mais antigo) — ~12% após 7 dias.

Material direto para política de manutenção: **frotas mais antigas (5S) precisam de inspeção mais frequente** que frotas mais recentes (4S) ou escavadeiras. Confirmado por três técnicas independentes (LightGBM SHAP, Weibull AFT hazard ratios, Isolation Forest) — convergência metodológica.

### Concentração dos DGs em poucos equipamentos

[Figura Extra G — Pareto top-15 TAGs com mais DGs](figuras/figExG_pareto_tags.png)

Lei de Pareto se aplica fortemente ao parque: **CA65926 sozinho responde por 24,7%** dos DGs do semestre; **top 5 equipamentos concentram >50%**. Combinada com a Figura Extra B (top 5 alarmes = 87% dos DGs), a conclusão operacional é clara: **o foco de auditoria deveria estar em poucos equipamentos × poucos alarmes**, não numa varredura uniforme do parque.

---

## Avaliação estratificada e calibração operacional do v3 (CM 5.2 + Q6)

Esta seção complementa a leitura de negócio com a **avaliação técnica final** do LightGBM v3 no test set (jun/2025) — calibração do limiar operacional, distribuição de erros em subgrupos críticos, e matriz de confusão com impacto operacional anotado. Material direto para CM 5.2 (Métricas) do relatório.

### Calibração do limiar operacional (CM 5.2)

A escolha do limiar de operação não pode ser feita apenas por F1 — depende da **relação de custo** entre falso negativo (FN = parada não planejada, ~4h) e falso positivo (FP = inspeção preventiva desnecessária, ~1,5h). A tabela `eval_custo_beneficio.csv` reporta o limiar ótimo (mínimo custo total = `FP × 1 + FN × ratio`) para quatro premissas de custo:

| Custo FN:FP | Thr* | TP | FP | FN | Precision | Recall | F1 | F2 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1:1 (FP e FN equivalentes) | 0,70 | 8.430 | 946 | 3.608 | 0,899 | 0,700 | 0,787 | 0,733 |
| 3:1 | 0,40 | 9.408 | 3.193 | 2.630 | 0,747 | 0,782 | 0,764 | 0,774 |
| **5:1 (operacional canônico)** | **0,30** | **9.821** | **4.764** | **2.217** | **0,673** | **0,816** | **0,738** | **0,783** |
| 10:1 (recall agressivo) | 0,15 | 10.624 | 10.478 | 1.414 | 0,503 | 0,883 | 0,641 | 0,767 |

**Decisão canônica para o relatório: threshold operacional = 0,30 (ratio 5:1).** Justificativa empírica: a Fig Neg03 estimou que cada FN evitado preserva ~2,5h-equipamento (4h corretiva − 1,5h preventiva), enquanto cada FP custa 1,5h adicional. O ratio "puro" das premissas é 2,7:1, mas considerando custos não-monetizáveis (mobilização emergencial, peças em estoque indisponíveis, risco de segurança em parada não planejada), o ratio efetivo é estimado entre 3:1 e 10:1. **5:1 é compromisso razoável** entre as duas extremidades e maximiza F2 (ver tabela).

Decisão registrada formalmente em `controle_alteracoes.md` (entrada de fechamento de W7).

### Q6 — Faixas de probabilidade → ação operacional

Com base no threshold canônico de 0,30 e no quantil 70% do score (0,145), três faixas semafóricas para uso no plantão e no painel do dispatcher:

| Faixa | Intervalo `P(DG≤4h)` | n eventos | % do total | n DG real | Prevalência na faixa | Ação operacional |
|---|---|---:|---:|---:|---:|---|
| 🟢 **VERDE** | < 0,145 | 49.762 | 70,0% | 1.383 | **2,78%** | Operar normalmente (rotina padrão) |
| 🟡 **AMARELO** | 0,145 ≤ P < 0,300 | 6.742 | 9,5% | 834 | **12,37%** | Monitoramento intensivo (alertas adicionais ao plantão) |
| 🔴 **VERMELHO** | ≥ 0,300 | 14.585 | 20,5% | 9.821 | **67,34%** | Inspeção preventiva planejada (mobilizar peça e equipe) |

**Concentração operacional ótima:** a faixa vermelha contém 20,5% dos eventos mas concentra **81,6% dos DGs reais do test** (9.821 de 12.038) — fator de enriquecimento de 4× sobre a prevalência base (16,93%). A faixa amarela acrescenta um buffer para o time decidir caso a caso.

Tabela completa em `relatorio/tabelas/eval_q6_faixas.csv`. Material para CM 5.2 (operacionalização) e CM 6.3 (recomendação de implementação).

### Análises estratificadas no test set (Qualidade C + derivadas de W5)

Quatro estratificações executadas em paralelo no `10_evaluation.py`, com threshold operacional 0,30:

#### (a) Por frota — modelo NÃO funciona em escavadeiras (achado crítico → L11)

| Frota | n | DGs | Prevalência | AUC-PR | Precision | Recall | n alertas |
|---|---:|---:|---:|---:|---:|---:|---:|
| 793-D 4S (inclui CA65926) | 11.593 | 6.363 | 54,9% | **0,9356** | 0,848 | 0,855 | 6.413 |
| 793-D 5S | 23.760 | 4.774 | 20,1% | 0,8035 | 0,579 | 0,801 | 6.604 |
| 793-D 3S | 1.134 | 541 | 47,7% | 0,7354 | 0,582 | 0,710 | 660 |
| 793-D 2S | 2.693 | 268 | 9,95% | 0,4025 | 0,192 | 0,649 | 908 |
| **LeTourneau L 1850** | **31.909** | **92** | **0,29%** | **0,0077** | **0,000** | **0,000** | **0** |

**Achado crítico (nova limitação L11):** o modelo emite **zero alertas** nas 31.909 ocorrências de escavadeiras LeTourneau no test (45% do volume). AUC-PR de 0,008 é essencialmente aleatório. **A Frente 1 (alerta operacional 4h) não funciona para escavadeiras com o pipeline atual.** Para o caso de uso da Vale, isto significa que monitoramento de DGs em escavadeiras precisa de **modelo dedicado** (Trabalho Futuro CM 6.3) ou de outra estratégia (`tipo_caminhao` como gating, retreino estratificado, etc.).

Detalhamento técnico do achado em `notas_metodologicas.md` Seção 19 (a criar em W8); tabela completa em `relatorio/tabelas/eval_estratificado_frota.csv`.

#### (b) Por tipo de equipamento

| Tipo | n | DGs | Prevalência | AUC-PR | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| Caminhão | 39.180 | 11.946 | 30,5% | 0,8608 | 0,673 | 0,822 |
| Escavadeira | 31.909 | 92 | 0,29% | 0,0077 | 0,000 | 0,000 |

Confirma o achado da estratificação por frota — agregação por tipo apenas reduz granularidade. Material direto para Qualidade C.

#### (c) Por estado pré-evento — modelo robusto a estado operacional

| Estado pré-evento | n | DGs | Prevalência | AUC-PR | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| Operando | 54.108 | 9.770 | 18,06% | 0,8630 | 0,706 | 0,812 |
| Manutenção | 4.776 | 885 | 18,53% | 0,7902 | 0,471 | **0,883** |
| Parado | 12.179 | 1.383 | 11,36% | 0,8380 | 0,657 | 0,800 |
| Hibernando | (< 30 eventos) | — | — | — | — | — |

Modelo mantém AUC-PR razoável em todos os estados — em Manutenção, recall é até maior (0,88) mas precision menor (0,47), coerente com a Obs 2.7 (DGs em manutenção são reais mas em contexto distinto). Refuta a preocupação inicial de "DGs em manutenção sendo ruído contextual" — modelo lida bem com essa distinção.

#### (d) Categorias unknown no treino — achado contra-intuitivo (Insight CM 6.1)

| Categoria | n eventos | DGs | Prevalência | AUC-PR | Recall@thr |
|---|---:|---:|---:|---:|---:|
| Conhecido em treino | 69.277 | 11.870 | 17,13% | 0,8554 | 0,8153 |
| **Unknown em treino** | **1.812** | **168** | **9,27%** | **0,8887** | **0,8512** |

**Insight não óbvio para CM 6.1:** o modelo **performa ligeiramente MELHOR** em categorias unknown (TAGs `CA65791`, `CA65916` + 7 operadores não vistos no treino). Refuta a expectativa inicial do estudo W5 (`notas_metodologicas.md` Seção 2) de degradação por extrapolação. Possíveis explicações: (i) sample pequeno (n_DG=168) pode introduzir variância amostral; (ii) a convenção `freq=0` para unknown (Opção 1 do encoding fix) funciona efetivamente como uma feature binária implícita ("equipamento novo"), que o modelo aprende a usar; (iii) categorias unknown podem ter padrões operacionais menos ambíguos. **Independente da causa, valida empiricamente a Opção 1 do encoding fix de W5** — não há necessidade de Opção 3 (features binárias `is_unknown` explícitas).

### Tempo de antecipação dos alertas verdadeiros (Qualidade B)

A métrica Precision/Recall agregada não responde uma pergunta operacional crítica: **se o modelo emite alerta verdadeiro, quanto tempo o time tem antes do DG real?** Análise complementar via `17_distribuicao_antecipacao.py` decompõe os 9.821 TPs do v3 no test set:

| Categoria | n | % |
|---|---:|---:|
| **Detecções diretas** (próprio evento é DG, antecipação=0) | **4.945** | **50,4%** |
| **Antecipações reais** (DG futuro estritamente em ≤4h) | 4.876 | 49,6% |

**Metade dos TPs são "detecções diretas" — alerta no momento do DG real, sem antecipação útil.**

Distribuição das antecipações reais (minutos):

| Percentil | Antecipação |
|---|---:|
| P25 | 0,8 min |
| **P50 (mediana)** | **5,7 min** |
| P75 | 56 min |
| P90 | 146 min |

**Apenas 18% dos TPs chegam à janela típica de mobilização (90 min); 35% têm ≥30 min.**

[Figura Neg04 — Tempo de antecipação dos alertas](figuras/figNeg04_distribuicao_antecipacao.png)

**Interpretação:** o v3, na prática, funciona muito mais como **detector de DG iminente** do que como **antecipador de janela 4h**. Manifestação residual do mesmo padrão que motivou a promoção do v3 (cascade detection do v2) — mitigado mas não eliminado. **Registrada como limitação L12 em CM 6.2.** Mitigações em CM 6.3: variante com target mais longo (8-12h), uso combinado com Frente 2 (Weibull AFT, multi-horizonte).

### O que a regra CMA não vê: top-100 FPs do Isolation Forest

Análise complementar via `18_top100_fps_if.py` examina os **100 eventos no test set com maior `anomaly_score`** do Isolation Forest (treinado em W6 sem ver o rótulo) **que NÃO foram classificados como DG pela CMA**. Pergunta: o IF identifica DGs "perdidos" pela regra? Resultado em duas camadas:

| Métrica | Valor |
|---|---:|
| % com ≥ 1 DG futuro nas 4h seguintes | **6%** |
| % com ≥ 1 evento Crítico nas 4h seguintes | **99%** |
| Mediana de eventos próximos nas 4h | 46 |

**Resposta direta:** o IF **não complementa a CMA para antecipar DGs perdidos** no curto prazo. Apenas 6% dos top-FPs evoluem para DG.

**Mas a concentração revela algo importante:**

| Frota | n FPs entre top-100 |
|---|---:|
| **LeTourneau L 1850 (escavadeira)** | **94** |
| 793-D 4S | 5 |
| 793-D 5S | 1 |

**94 dos 100 FPs vêm da MESMA escavadeira (PE3797).** Apesar de não terem virado DG, **99% têm eventos Críticos nas 4h seguintes** (mediana 9). Isso indica um regime sistematicamente diferente em LeTourneau: alarmes Críticos elevados que NUNCA viram DG pela regra CMA. Possíveis explicações (mutuamente não-exclusivas): (i) escavadeiras toleram criticidade alta sem falhar; (ii) regras CMA (~95% Caterpillar OEM) subreportam para LeTourneau; (iii) ambos.

[Figura Extra H — Top-100 FPs do Isolation Forest](figuras/figExH_top100_fps_if.png)

**6ª evidência convergente sobre LeTourneau** (junto com as 5 já em H4.1): 38% sem telemetria, 95% dos bypasses, 88% dos erros de peso, 22× menos DGs por equipamento, AUC-PR=0,008 do v3 (L11), e agora 94% dos top-100 FPs do IF.

**Recomendação operacional concreta para CM 6.3:**
- Auditoria manual dos 100 eventos identificados na PE3797 — domain expert valida se são anomalias mecânicas reais ou ruído operacional aceito
- Revisão das regras CMA específicas para escavadeiras — possível recalibração de thresholds

### Figura 10 — Matriz de confusão com impacto operacional

[Figura 10 — Matriz de confusão do LightGBM v3 no test set](figuras/fig10_matriz_confusao_v3.png)

No threshold operacional 0,30 (n_alertas = 14.585, 20,5% do total):
- **TP = 9.821** (DGs antecipados com sucesso → 1,5h × evento, custo planejado)
- **FP = 4.764** (inspeções preventivas desnecessárias → 1,5h × evento, custo planejado)
- **FN = 2.217** (paradas não planejadas → **4h × evento, custo reativo**)
- **TN = 54.287** (operação normal)

**Tradução em horas-equipamento:**

| Cenário | Cálculo | Horas |
|---|---|---:|
| Sem modelo (todos DGs como parada não planejada) | 12.038 × 4h | 48.152 h |
| Com modelo no threshold 0,30 | (TP + FP) × 1,5h + FN × 4h | 30.746 h |
| **Redução** | **48.152 − 30.746** | **17.406 h (36,1%)** |

Resultado **consistente com o cenário Realista da Fig Neg03** (37.429h evitadas no semestre = 47% — pequena diferença porque a Fig Neg03 considera horas totais de parada, este cálculo só compara DGs reais).

---

## Diferenciais metodológicos do trabalho

Esta seção posiciona o trabalho frente a outras abordagens possíveis para o mesmo desafio (incluindo classificadores supervisionados padrão como Random Forest ou XGBoost). **Não há diferencial significativo no algoritmo específico** usado — LightGBM, Random Forest e XGBoost pertencem à mesma família de *gradient boosting* sobre árvores e produzem desempenho comparável em problemas tabulares com a mesma matriz de *features*. O que diferencia este estudo está na **forma de tratar o problema**, não no algoritmo escolhido. Seis pontos sustentam essa afirmação:

### 1. Honestidade metodológica: corrigimos o modelo após descobrir o que ele realmente fazia

A primeira versão treinada (v2, AUC-PR test = 0,8618 com 35 features) passou todos os critérios estabelecidos a priori (GATE MARCO 1, AUC-PR > 0,63 em test). **A análise SHAP posterior revelou que o modelo era, em essência, um detector de continuação de cascatas, não um preditor de primeiros DGs.** A *feature* dominante (`horas_desde_ultimo_DG`, 39,3% do peso) operava como atalho: 100% dos eventos com SHAP positivo alto tinham DG anterior em ≤ 2h (mediana 1 minuto). Para eventos sem DG recente — o caso operacional valioso — o v2 detectava **apenas 1% dos primeiros DGs**.

A resposta foi treinar uma variante v3 removendo a *feature* problemática. O v3 (canônico final do relatório) tem AUC-PR aggregate quase idêntico (0,8556, −0,62 pp) mas **captura 5× mais primeiros DGs** (Recall@0.5 de 4,3% → 21,1%). v2 fica preservado no projeto como modelo intermediário diagnóstico, com explicação completa em `controle_alteracoes.md` (entrada 24/05). **A maioria dos trabalhos não detecta esse tipo de problema** — entrega o modelo com AUC alto e a discussão acaba ali. A combinação SHAP + diagnóstico ad-hoc + retreinamento é diferencial direto de qualidade.

**Validação empírica do ponto "algoritmo não é o diferencial":** treinamos um **Random Forest tunado com a EXATA MESMA estratégia rigorosa do v3** (Optuna 50 trials, TimeSeriesSplit CV de 4 folds expandidos, mesma seed=42, 34 features alinhadas, mesma imputação NaN) em `16_random_forest_comparativo.py`. Resultado:

| Métrica (test) | RF tunado | LightGBM v3 | Diferença |
|---|---:|---:|---:|
| AUC-PR | 0,8541 | **0,8556** | −0,0015 |
| Recall@0.5 | 0,7520 | 0,7527 | −0,0007 |

**Diferença de 0,15 pp em AUC-PR e 0,07 pp em Recall — praticamente nula.** Random Forest e LightGBM, ambos pertencentes à família de *ensembles* de árvores, atingem performance estatisticamente equivalente quando submetidos ao mesmo rigor metodológico. **O diferencial deste estudo, portanto, NÃO está na escolha entre RF e LightGBM** — está na descoberta do cascade detection via SHAP (que faria com o RF também), na triangulação metodológica (SHAP × HR × IF), na auditoria do rótulo, e nas recomendações operacionais quantificadas. Um grupo que entrega "RF com 85% AUC-PR" sem nenhum desses passos entrega menos valor que este estudo, mesmo com algoritmo equivalente.

### 2. Triangulação metodológica: três modelos com matemáticas radicalmente diferentes

O relatório entrega três modelos independentes que respondem perguntas diferentes:

- **LightGBM v3** — classificação supervisionada via *gradient boosting* (Shapley values para interpretabilidade)
- **Weibull AFT** — sobrevivência paramétrica via *maximum likelihood* (hazard ratios com IC 95% para interpretabilidade)
- **Isolation Forest** — detecção de anomalia não-supervisionada via *isolation trees*

As três técnicas concordam em quatro *features* estruturais (`tipo_caminhao`, `tag_freq`, `frota_793D_4S`, `frota_793D_5S`) — convergência metodológica como **validação empírica de validade**, não como redundância. Quando divergem (LightGBM dá 41% para `qtd_alarmes_muito_alto`, Weibull não), a divergência é informativa (sinais antecipativos para horizonte específico vs sinais de *base rate* estrutural). Detalhes em `notas_metodologicas.md` Seções 11-14 e tabela `validacao_sentido_features.csv`.

**Um trabalho com apenas Random Forest entrega uma perspectiva única.** Três técnicas independentes que convergem sobre os mesmos *drivers* é evidência muito mais forte de que o sinal aprendido é real e não artefato do método.

### 3. Auditoria do rótulo: questionamos a confiabilidade do próprio `Is_Dont_Go`

O rótulo `Is_Dont_Go` é gerado por 82 regras da CMA, das quais ~95% são *wrappers* sobre alarmes nativos do fabricante (Caterpillar). Em princípio, o modelo poderia estar aprendendo a replicar as regras CMA, não a antecipar falhas mecânicas reais. O Risco 3.3 (viés do label) foi explicitado no início do projeto e testado empiricamente em W6 via Isolation Forest treinado **sem usar `Is_Dont_Go`**.

Resultado: assimetria forte por equipamento. Para anomalias dominantes (CA65926-like, falha mecânica progressiva), IF e CMA concordam fortemente (AUC=0,90). Para 88% dos demais equipamentos, AUC mediana = 0,61 (próximo do aleatório) — o rótulo CMA pode estar capturando eventos sem assinatura estatística distintiva no espaço de *features* atual. **Risco 3.3 parcialmente confirmado, parcialmente mitigado.** Material direto para a seção de Limitações (L10) e Trabalhos Futuros.

**A maioria dos trabalhos aceita o rótulo como verdade.** Este estudo trata o rótulo como hipótese a testar.

### 4. Achados estruturais acionáveis, não apenas "o modelo prediz"

A entrega contém recomendações operacionais quantificadas que não dependem de o modelo estar em produção:

- **Caso CA65926** (Figura `figNeg01`): timeline mês a mês mostra sinal precursor em março (438 DGs, taxa 20,28% — 5× a média do parque) **3 meses antes** da crise de junho. **Janela de antecipação real existe nos dados** se o monitoramento operar por equipamento, não por frota.
- **Ranking de risco do parque** (Figura `figNeg02`): 5 equipamentos em risco ALTO (auditoria imediata), 18 em MÉDIO (monitoramento mensal), 10 em BAIXO (operação normal). Ação recomendada por equipamento, não por categoria genérica.
- **Tradução em valor operacional** (Figura `figNeg03`): em 3 cenários com premissas declaradas, entre 10.480h e 43.582h-equipamento de parada não planejada evitáveis no semestre observado (base: 79.848h).

Esses achados são **utilizáveis pelo time operacional independentemente** de o modelo de classificação estar deployado. Um relatório que entrega apenas "o modelo classifica DGs com AUC=X" deixa o leitor com a pergunta "e agora?" — este entrega "e agora **estes 5 equipamentos**, com **esta janela de antecipação**, gerando **este ganho estimado em horas**".

### 5. Rigor temporal: validação *walk-forward* sem *leakage*

O *split* temporal é fixo `jan-abr / mai / jun`, com cortes nos limites de mês. O *tuning* (Optuna, 50 *trials*) usa **TimeSeriesSplit CV de 4 *folds* expandidos** (jan→fev, jan-fev→mar, jan-mar→abr, jan-abr→mai), garantindo que o conjunto de teste (junho) **nunca** é tocado durante a otimização de hiperparâmetros. *Feature encoding* (`tag_freq`, `operador_freq`) é calculado **apenas sobre o conjunto de treino** após detecção e correção de *leakage* sutil em W5 (`06b_fix_encoding_leakage.py`, gerou `v3.parquet`).

Adicionalmente, o LightGBM v3 é configurado com `deterministic=True` + `force_col_wise=True`: dois *runs* produzem o mesmo modelo *bit-exact* até a última casa decimal — requisito para auditoria. Detalhes em `notas_metodologicas.md` Seções 6, 9.

**Muitos trabalhos usam *split* aleatório** (treino/teste sorteado sobre todo o semestre) ou *cross-validation* aleatório — **introduz *leakage* temporal** (modelo "vê" o futuro durante o treino) e reporta métricas infladas. A AUC-PR test = 0,8556 deste trabalho é menor que a que se obteria com *split* aleatório, mas é **real** — corresponde à performance esperada em deployment com dados fora da janela observada.

### 6. Rastreabilidade total e refutação como sinal de qualidade

O projeto mantém quatro documentos de rastreabilidade complementares ao código: `controle_alteracoes.md` (8 entradas com decisões metodológicas ANTES/DEPOIS + justificativa + impacto), `hipoteses_eda.md` (15 hipóteses testadas com veredito empírico), `notas_metodologicas.md` (14 seções com detalhamento técnico de cada script), e `observacoes_importantes.md` (checklist vivo de itens em aberto). Todo o pipeline analítico é reproduzível *bit-exact* a partir dos dados brutos via `uv sync` + execução dos scripts em ordem (ver Anexo A).

**Quantitativamente:** das 15 hipóteses analíticas testadas, **11 caíram (refutadas ou refutadas com reinterpretação)** — taxa de refutação de 73%. Esse é sinal claro de que a exploração cumpriu o papel de **testar premissas**, não apenas confirmar intuições prévias. As 3 hipóteses confirmadas (H2.1 top 5 alarmes, H4.1 LeTourneau, H7.1 equipamentos individuais problemáticos) são todas estruturalmente fortes — duas delas emergiram como **padrões não-hipotetizados a priori**, validados pela convergência de múltiplas evidências independentes.

### Síntese

Frase de posicionamento para a defesa do trabalho:

> *"Não entregamos só uma previsão — entregamos uma previsão que entendemos, três modelos complementares que respondem perguntas diferentes, uma auditoria do próprio rótulo que estamos aprendendo, e recomendações operacionais cujos ganhos foram quantificados em horas-equipamento. As limitações estão documentadas com a mesma honestidade dos achados."*

Um modelo Random Forest com 90% de acurácia que ninguém entende e que secretamente só detecta cascatas é **pior** que o v3 canônico deste trabalho — com AUC-PR ligeiramente menor mas com diagnóstico do próprio comportamento + complementos analíticos + recomendações acionáveis.

---

## Insights Não Óbvios consolidados (rascunho para CM 6.1)

Esta subseção consolida os 10 insights mais relevantes que emergiram da análise — todos contra-intuitivos, surpreendentes ou refutativos de premissas iniciais. Material direto para **CM 6.1 (Insights Não Óbvios)** do relatório final.

### Insight 1 — AUC-PR alto pode esconder estratégia operacionalmente errada

O LightGBM v2 atingiu AUC-PR test = 0,8618 e passou todos os critérios estabelecidos a priori (GATE MARCO 1, AUC-PR > 0,63). A análise SHAP revelou que o modelo era, em essência, um **detector de continuação de cascatas** — não um preditor de primeiros DGs. Para eventos sem DG recente (caso operacional valioso), v2 detectava **apenas 1% dos primeiros DGs**. Lição: AUC-PR isoladamente não garante valor operacional. Interpretação via SHAP + mini-diagnose dedicada foi o que revelou o problema e motivou o v3 — sem isso, o modelo iria para deployment com falha operacional crítica não-detectada.

### Insight 2 — Três técnicas com matemáticas radicalmente diferentes convergem sobre os mesmos drivers

LightGBM + SHAP (Shapley values em gradient boosting), Weibull AFT (maximum likelihood paramétrico) e Isolation Forest (isolation trees não-supervisionado) — três fundamentações matemáticas completamente diferentes — chegam às mesmas **4 features estruturais top**: `tipo_caminhao`, `tag_freq`, `frota_793D_4S`, `frota_793D_5S`. Convergência metodológica como validação empírica de validade do sinal aprendido. Quando divergem (LightGBM dá 41% para `qtd_alarmes_muito_alto`, Weibull não), a divergência é informativa — sinais antecipativos de curto prazo vs sinais de *base rate* estrutural.

### Insight 3 — SHAP atribui USO; ablation mede NECESSIDADE; a diferença é REDUNDÂNCIA

SHAP do v3 atribui 41% do peso a `qtd_alarmes_muito_alto_360min` e 24% a `tipo_caminhao`. Ablation por grupo mostra que remover qualquer um dos dois **não degrada** o modelo (variação ±0,01 AUC-PR). Como conciliar? **SHAP mede o que o modelo USA quando todas as features estão disponíveis. Ablation mede o que o modelo PRECISA quando algo é removido.** A diferença é a **redundância** do conjunto de features. O v3 entrega 0,86 AUC-PR por **múltiplas rotas redundantes**, não por um sinal único insubstituível. **Implicação operacional:** v3 é robusto a perda de features em deployment (sensores quebrados, fontes intermitentes) — mesmo perdendo 8 das 34 features, AUC-PR mantém-se em 0,86.

### Insight 4 — EDA agregada esconde equipamentos individuais problemáticos

Pelo menos 3 equipamentos com comportamento sistematicamente anômalo emergiram em investigações distintas e só foram identificados via análise estratificada por TAG:
- **CA65789** (W3): 100% das sobreposições de apontamento em jan/2025
- **CA65926** (W2 + W5 + W6 + W7): 24,7% de todos os DGs do semestre, deterioração progressiva mar→jun
- **CA65924** (W4 + W6): paradigma operacional + validado pelo IF não-supervisionado sem usar o rótulo

A EDA agregada por frota, por mês ou por criticidade **diluiu sistematicamente esses indivíduos**. Lição: análise estratificada por equipamento é mandatória em datasets industriais com forte concentração em poucos casos. Recomendação direta para CM 6.3: política de manutenção orientada por equipamento, não por frota.

### Insight 5 — Features genéricas perdem para versões domain-specific da mesma intuição

A hipótese H5.2 (sub-versão Obs 2.11) previa que `count_critico_*h` (Família 1, 15 features rolling counts genéricas) capturaria o padrão "acúmulo de criticidade pré-DG". Análise SHAP em v2 e v3 **refuta empiricamente**: todas as 15 features de Família 1 ficam em rank #15–#31 (cumulativo ~7%). **A versão *domain-specific* da Família 6 (`qtd_alarmes_nivel_muito_alto_360min`, que conta APENAS alarmes nas 82 regras CMA "Muito Alto") venceu com 41% do peso no v3** — 6× a soma de todas as 15 features genéricas. Ablation confirma: remover Família 1 inteira melhora ligeiramente o modelo. Lição metodológica para engenharia de features.

### Insight 6 — Categorias unknown no treino performam ligeiramente MELHOR que conhecidas

Análise estratificada do v3 no test (W7) revela achado contra-intuitivo:

| Categoria | AUC-PR | Recall@thr |
|---|---:|---:|
| Conhecido em treino | 0,8554 | 0,8153 |
| **Unknown em treino** | **0,8887** | **0,8512** |

**Refuta a expectativa inicial do estudo W5** (`notas_metodologicas.md` Seção 2) de degradação por extrapolação. **Valida empiricamente a Opção 1 do encoding fix** — convenção `freq=0` para unknown atua como feature binária implícita "equipamento novo" que o modelo aprende a usar. Não há necessidade de Opção 3 (features binárias `is_unknown` explícitas).

### Insight 7 — IF não-supervisionado revela regime anômalo em LeTourneau que CMA não classifica como DG

A leitura inversa do Risco 3.3 (via `18_top100_fps_if.py`): 100 eventos com maior `anomaly_score` que NÃO são DG. Apenas 6% têm DG futuro nas 4h, mas **94 dos 100 vêm da MESMA escavadeira (PE3797)** e **99% têm eventos Críticos próximos** (mediana 9). LeTourneau opera em regime de criticidade elevada que NUNCA vira DG pela regra CMA — confirma direcionalmente o Risco 3.3 (rótulo CMA é viesado por tipo de equipamento). **6ª evidência convergente** sobre LeTourneau, somando às 5 já documentadas em H4.1 + L11.

### Insight 8 — Drift de calibração pode acontecer separadamente de drift de AUC-PR

Análise de calibração do v3 (W6, `14_calibracao_v3.py`): aplicar Platt scaling fitado no val (mai) **melhora ECE no val (3,70→1,87pp) mas PIORA no test (3,78→4,76pp)**. **A estrutura de calibração do v3 é diferente entre val e test**, mesmo que AUC-PR seja preservado. Manifestação adicional da L4 (drift mai→jun) — drift de regime afeta as duas dimensões (ranking e probabilidades) independentemente. Em deployment, monitorar AS DUAS.

### Insight 9 — O viés do rótulo é equipamento-específico, mas o modelo supervisionado generaliza

Achado de dupla face, importante separar as duas metades. (i) O **rótulo CMA** tem sinal estrutural não-supervisionado fortemente concentrado: a análise por TAG do Isolation Forest mostra AUC mediana = 0,6060, com apenas 3 equipamentos de sinal forte (CA65926, CA65932, CA65924) e 8 de 26 abaixo de 0,55; sem o CA65926, o IF cai a 0,54. Isso evidencia o viés do rótulo (Risco 3.3): a CMA captura anomalia estatística real em poucos equipamentos. (ii) Mas o **modelo supervisionado v3 não herda essa fragilidade**: estratificando a AUC-PR do próprio v3 (`22_v3_estratificado_ca65926.py`), sem o CA65926 ela cai só de 0,8556 para 0,7693, com AUC-ROC praticamente intacta (0,9368), e o lift sobre o acaso é maior nos demais 29 equipamentos (7,77×) do que no CA65926 (1,20×, alvo fácil por prevalência de 80,9%). **O insight não óbvio é justamente a dissociação:** o IF não-supervisionado colapsa fora do CA65926, mas o classificador supervisionado generaliza, porque aprende sinais transferíveis (regra de negócio, regime, base rate por tipo) que o IF não enxerga. O número absoluto de 0,8556 é parcialmente inflado pela prevalência do CA65926; a habilidade discriminativa real é genuína e distribuída. Material para CM 6.2 (L10) + CM 6.1.

### Insight 10 — Tempo de antecipação ≠ horizonte do target

O v3 prediz `P(DG ≤ 4h)` mas a análise da distribuição temporal dos TPs revela que **na prática o modelo detecta DG iminente, não antecipa em janela ampla**: 50% dos TPs são detecções diretas (próprio evento é DG, antecipação=0), e nos 50% restantes, mediana = 5,7 min, P75 = 56 min, P90 = 146 min. Apenas 18% dos TPs atingem a janela de mobilização típica (90 min). **A métrica que importa operacionalmente (tempo entre alerta e DG) NÃO é capturada por Precision/Recall agregados.** L12 registrada.

### Insight 13 — Drift intra-mês dramático: AUC-PR varia 0,35 a 0,95 em 4 semanas de junho

A análise semanal do test set (`19_drift_semanal_junho.py`) revela que a performance do v3 **NÃO é estável dentro do próprio mês de teste**. AUC-PR varia dramaticamente entre as 4 semanas de junho/2025, alinhado com a prevalência local de DG:

| Semana | n eventos | Prevalência | AUC-PR | Recall@thr |
|---|---:|---:|---:|---:|
| S1 (01-07/jun) | 12.325 | 20,1% | **0,9375** | 0,966 |
| S2 (08-14/jun) | 24.097 | 15,4% | 0,6762 | 0,577 |
| **S3 (15-21/jun)** | 13.536 | **3,75%** | **0,3539** | 0,726 |
| S4 (22-30/jun) | 21.131 | 25,2% | **0,9472** | 0,921 |

**Amplitude de 0,59 pp em AUC-PR dentro de 30 dias.** Quando a prevalência cai (S3, regime "calmo" sem dominância CA65926), o modelo desaba. Quando a prevalência sobe (S4, explosão CA65926), modelo brilha. **Esta é a manifestação mais granular até agora da L4 (drift) + L10 (dependência de poucos equipamentos)** — agora visível semanalmente, não apenas mensalmente. **Implicação para deployment:** monitoramento em produção precisa operar em janela semanal, não mensal — a degradação pode ser detectada em 7 dias, não esperar o fechamento do mês. Material reforça L4 + L10 + recomendação CM 6.3 de monitoramento estratificado contínuo.

[Figura Extra I — Drift semanal do v3 em junho](figuras/figExI_drift_semanal_junho.png)

### Insight 12 — CV temporal agregada mascara colapso no fold mais recente

A comparação T2 vs T4 vs T8 via TimeSeriesSplit CV de 4 folds (`08d_comparacao_horizontes_cv.py`) confirma a equivalência estatística dos três horizontes (Cenário 1, Δ/σ = 0,29 entre T2 e T4 — mantém T4 canônico). Mas o achado **lateral** é mais valioso: o **fold 4 colapsa em todos os horizontes**:

| Horizonte | Fold 1 | Fold 2 | Fold 3 | **Fold 4** |
|---|---:|---:|---:|---:|
| T2 | 0,899 | 0,905 | 0,866 | **0,537** |
| T4 | 0,910 | 0,894 | 0,834 | **0,171** |
| T8 | 0,913 | 0,892 | 0,802 | **0,129** |

Os 3 primeiros folds (jan→fev, jan-fev→mar, jan-mar→abr) produzem AUC-PR ~0,87-0,91 consistentes. O **fold 4 (jan-abr → mai)** desaba — quanto maior o horizonte, mais forte o colapso (T8 cai 0,80 pp; T2 cai 0,36 pp). A AUC-PR média da CV (0,70-0,80) é estatística enganosa: oculta um **colapso de regime que ocorre exatamente onde o modelo seria mais cobrado em deployment** (transição do treino para validação/teste). **Lição metodológica:** em problemas temporais com drift conhecido, reportar AUC-PR média da CV sem decomposição por fold pode dar segurança falsa. A análise fold-a-fold revela onde o modelo realmente quebra. Reforça empiricamente a L4 (drift mai→jun) e a L10 (dependência de CA65926) — agora visíveis também no fold de CV mais próximo do regime de mudança.

### Insight 11 — Refutação como sinal de qualidade

Das 15 hipóteses analíticas formuladas no projeto, **11 caíram** (refutadas ou refutadas com reinterpretação) — **taxa de refutação de 73%**. Em pesquisa científica madura, isso não é sinal de problemas — é sinal de **rigor**: a exploração cumpriu o papel de testar premissas, não apenas confirmá-las. As 3 hipóteses confirmadas (H2.1 top 5 alarmes, H4.1 LeTourneau, H7.1 equipamentos individuais problemáticos) são estruturalmente fortes. As 11 refutadas geraram **achados sempre mais ricos** que a hipótese original previa — H5.2 virou "Família 6 domain-specific vence Família 1 genérica", H3.3 virou "falha localizada do CA65926", H5.3 virou "operador correlaciona difusamente com DG".

---

### Síntese parcial de limitações identificadas (rascunho para CM 6.2)

Esta subseção consolida as limitações metodológicas identificadas até o final de W6 que devem entrar formalmente em **CM 6.2 (Limitações)** durante a escrita do relatório em W8. Cada item é registrado com magnitude, evidência, e — quando aplicável — caminho de mitigação ou trabalho futuro associado.

**L1 — Predição de cascata em v2 (RESOLVIDA pela promoção do v3 como canônico):**
A análise SHAP do v2 identificou que a *feature* `horas_desde_ultimo_DG` (rank #1, 39% do peso global) operava como detector de continuação de rajadas — não de primeiro DG (top 10% dos eventos com maior SHAP+ tinham 100% DG anterior em ≤ 2h; apenas 1% dos primeiros DGs detectados). Essa limitação foi **resolvida pela promoção do v3** como modelo canônico do relatório (subseção "LightGBM v3 — modelo canônico promovido"). O v3 melhora *Recall@0.5* em primeiros DGs de 4,34% para 21,06% (5× ganho) ao custo de apenas 0,62pp de AUC-PR agregado. **Limitação residual em v3:** a tarefa "primeiro DG" continua difícil (AUC-PR = 0,1964 nesse subgrupo, vs 0,8556 geral) — o problema é intrinsecamente mais difícil que predição de cascata. **Trabalho Futuro (CM 6.3):** modelo de sobrevivência Weibull AFT (em `09_sobrevivencia.py`) oferece segunda leitura do problema sem dependência de *thresholds*.

**L2 — Feature `mes` introduz dependência temporal implícita:**
O modelo aprendeu que `mes` correlaciona com taxa de DG (rank #9, 0,89% do peso) — provavelmente capturando o *drift* mai → jun (Obs 2.6) e a anomalia localizada do CA65926 em junho (Obs 2.9). Em *deployment* com `mes` fora de [1, 6] (julho/agosto/etc.), o LightGBM extrapola implicitamente — trataria `mes = 7` como "`mes >= 5,5`" (igual a junho). **Magnitude:** pequena (0,89% do peso). **Mitigação por construção:** a recomendação de **retreino *rolling* mensal** já registrada em CM 6.3 endereça a limitação — em *deployment* real, o modelo é treinado nos últimos N meses, então `mes` nunca está fora da faixa vista no treino.

**L3 — Obs 2.11 (acúmulo de criticidade > volume) fracamente refutada:**
A Família 1 (15 *features* rolling counts) foi a maior família do projeto, motivada pela Obs 2.5 (W2) e pela hipótese de que `count_critico_*` superaria `count_total_*` no ranking. **Resultado SHAP:** todas as 15 *features* em rank #15-#31; comparação `count_critico_Xh` vs `count_total_Xh` deu resultado misto (3 de 5 janelas). A hipótese não é falsa nem verdadeira — é simplesmente **irrelevante para o modelo**, que preferiu a versão *domain-specific* da Família 6 (`qtd_alarmes_muito_alto_360min`). **Implicação metodológica para CM 6.1:** *features* genéricas podem perder para versões *domain-specific* da mesma ideia — lição transferível para projetos futuros.

**L4 — Drift quantificado e direcional jan-abr → jun (já registrado, reforçado pelo SHAP):**
Taxa de DG: 3,41% (treino) / 1,62% (val mai) / 7,35% (test jun) — fator 4,5× entre val e test. Causa mecânica identificada (Obs 2.9): anomalia RFB localizada no CA65926. Modelo aprendeu a usar `mes` (L2) e `razao_alarme_7d_vs_30d_anterior` (rank #3) para capturar o regime; em *deployment* contínuo, o regime pode mudar novamente. **Mitigação:** análise estratificada mensal em W7 + retreino *rolling* (CM 6.3).

**L5 — *Test set peeking* na Mitigação 2 do v1 (registrado e descartado):**
Variante B do v1 usou `scale_pos_weight` calibrado sobre val+test (*peeking* branda). Foi posteriormente descartada empiricamente (B−A < 0 em ambos os splits) e o Optuna do v2 escolheu `scale_pos_weight = 0,513` (direção oposta da Mitigação 2 original). Limitação efetivamente resolvida em v2 — mas vale registrar no relatório como demonstração de boa prática (testar hipótese metodológica e refutá-la com dados).

**L6 — Limitações da Família 5 — operador correlaciona difusamente com DG (Q3 do edital):**
Resposta empírica robusta (Obs 2.4 W5 + SHAP `operador_freq` rank #13): há sinal real (variação 30× entre quartis), mas distribuído entre 394 operadores sem 1-2 outliers claros. **Implicação:** intervenções de RH baseadas em "operador X é problemático" precisam ser cuidadosas — o sinal é estatístico difuso, não pontual.

**L7 — *Censoring* no target (102.602 eventos, 18,83%):**
*Target_4h* trata eventos sem DG futuro observado como `y = 0`, o que é aproximação razoável mas não rigorosa (esses eventos poderiam ter DG após o horizonte observado). **Mitigação parcial:** o modelo de sobrevivência Weibull AFT (`09_sobrevivencia.py`, em planejamento) oferece tratamento rigoroso do *censoring* como dado adicional — segunda leitura do problema.

**L8 — Composição da frota influencia base rate aprendida pelo v3 (`tipo_caminhao` = 23,9% do peso):**
Identificada via SHAP do v3 — a *feature* `tipo_caminhao` saltou de 5,0% (no v2) para 23,9% (no v3) ao se tornar canônica. Sem `horas_desde_ultimo_DG`, o v3 passou a depender mais fortemente da diferenciação caminhões vs escavadeiras (LeTourneau L 1850 tem 22× menos DGs por equipamento — H4.1 W5). **Magnitude:** moderada. **Implicação:** o modelo aprende *base rate* por tipo desde a predição inicial. **Risco operacional:** se a Vale operar uma sub-frota específica não vista no treino, calibração local pode ser necessária — *deployment* uniforme pode subestimar/superestimar essa população. **Não é viés injusto** (a diferença existe nos dados), mas é fator a monitorar. **Validação:** confirmada também via Weibull AFT (TR=0,038 para `tipo_caminhao`, p < 0,0001).

**L9 — *Censoring* assimétrico entre splits limita a robustez do Weibull AFT no test:**
Identificada via `09_sobrevivencia.py` — a distribuição de eventos censurados (E=0) é muito desigual: 16,0% no treino vs 57,5% no test. Isso ocorre porque o test (jun/2025) é o último mês observado, então eventos próximos ao fim de junho não têm tempo para "ver" um DG futuro dentro da janela. **Magnitude:** significativa para o Weibull AFT (AUC-PR test=0,3153 vs val=0,4126), pequena para o LightGBM v3 (que usa apenas `target_4h`, definido localmente). **Implicação:** o Weibull AFT é menos confiável no test que no val devido a esse desbalanceamento. **Mitigação parcial:** a métrica C-index (0,7444 test) é menos afetada pela proporção de censoring que a AUC-PR(4h). **Trabalho Futuro:** janela de observação estendida (12 meses+) reduziria a assimetria.

**L10 — Viés do rótulo CMA é equipamento-específico (Risco 3.3 parcialmente confirmado); o v3 supervisionado, porém, generaliza:**
A limitação real é sobre o **rótulo**, não sobre o classificador, e a distinção foi confirmada por medição direta. O Isolation Forest (`11_isolation_forest.py`), que mede sinal estrutural **sem ver o rótulo**, mostra três camadas: (i) AUC-ROC por split assimétrico (train=0,58 / val=0,60 / test=0,86); (ii) estratificação revela que o CA65926 sozinho tem AUC=0,90 enquanto o resto do test cai a 0,54; (iii) por TAG (26 com AUC válido), a AUC mediana é 0,6060, com apenas 3 equipamentos de sinal forte (CA65926, CA65932, CA65924) e 8 de 26 essencialmente aleatórios. Isso indica que o **rótulo CMA** carrega assinatura estatística clara em poucos equipamentos (viés do Risco 3.3), não que o modelo seja frágil.

A medição direta do próprio v3 (`22_v3_estratificado_ca65926.py`) **refuta** a leitura anterior de que sua performance seria "largamente dirigida" pelo CA65926. Estratificando a AUC-PR do v3 no test: completo 0,8556 (lift 5,06×); CA65926 apenas 0,9723 (lift só 1,20×, pois a prevalência ali é 80,9% e até o chute trivial acerta 0,81); **sem CA65926 0,7693 (lift 7,77×), com AUC-ROC praticamente intacta (0,9391 → 0,9368)**. Ou seja, remover o equipamento dominante derruba a AUC-PR em apenas 8,63pp, e a habilidade discriminativa real (lift) é **maior** nos demais 29 equipamentos. O número absoluto de 0,8556 é parcialmente inflado pela alta prevalência do CA65926, mas a **generalização do v3 é genuína**. **Magnitude:** moderada e bem caracterizada (o que era tido como risco crítico de dependência de um equipamento foi quantificado e em grande parte afastado). **Implicação para deployment:** esperar AUC-PR absoluto mais baixo em meses sem anomalia de altíssima prevalência (o teto cai com a prevalência), mas a capacidade de ordenação (AUC-ROC) e o lift devem se manter. **Mitigações (CM 6.3):** monitoramento estratificado por equipamento; investigação dos FPs do IF como possíveis "DGs perdidos pelo CMA" (leitura inversa do Risco 3.3); retreino *rolling* mensal. **Convergência metodológica (CM 6.1):** SHAP do v3 e Time Ratios do Weibull AFT identificam `tipo_caminhao`, frota e Família 4 regimal como drivers transferíveis (não específicos de um equipamento), e o **CA65924 (paradigma de W4) é recuperado pelo IF sem usar o rótulo** — as técnicas iluminam aspectos complementares: o IF expõe o viés do rótulo, SHAP e Weibull mostram a generalização do v3.

**L12 — Tempo de antecipação curto: 50% dos TPs são detecções diretas, mediana de antecipação real = 6 min:**
Identificada via `17_distribuicao_antecipacao.py` (W7 Grupo B, 01/06). Apesar do v3 prever `target_4h = 1` ("DG nas próximas 4h"), a análise da distribuição temporal dos 9.821 verdadeiros positivos no test revela um padrão operacional importante: **50,4% dos TPs (4.945 eventos) são "detecções diretas"** — o próprio evento alertado já é um DG (`Is_Dont_Go = 1`), portanto **antecipação = 0**. Apenas **49,6% (4.876 eventos)** correspondem a antecipações reais (DG estritamente futuro em ≤ 4h). E entre as antecipações reais, a distribuição é fortemente assimétrica: **mediana = 5,7 min**, P75 = 56 min, P90 = 146 min. **Apenas 18% dos alertas verdadeiros chegam à janela de mobilização típica de 90 minutos.** **Magnitude:** crítica para o uso operacional da Frente 1. **Implicação:** o modelo, na prática, funciona muito mais como **detector de DG iminente** do que como **antecipador de janela 4h** — manifestação residual do mesmo padrão do v2 (cascade detection) que o v3 mitigou mas não eliminou. **Causa provável:** features de Família 6 (`qtd_alarmes_muito_alto_360min`) e Família 4 (`razao_alarme_7d_vs_30d`) capturam sinais que aparecem MUITO próximos do DG real, não com 4h de antecedência. **Mitigações (CM 6.3):** (a) treinar variante com target mais longo (8h ou 12h) para forçar antecipação maior — pode reduzir AUC-PR mas aumentar tempo útil; (b) usar a Frente 2 (Weibull AFT) como complemento — ela modela tempo até qualquer DG futuro, não apenas o próximo; (c) combinar o score do v3 com a probabilidade de sobrevivência em horizonte mais longo. **Material para CM 5.2 (Qualidade B) e CM 6.3 (Trabalho Futuro).** Figura `figNeg04_distribuicao_antecipacao.png` documenta o achado.

**L11 — Modelo não opera em escavadeiras LeTourneau L 1850 (limitação categórica nova):**
Identificada via análise estratificada por frota em `10_evaluation.py` (W7, threshold operacional 0,30). No test set de jun/2025, escavadeiras LeTourneau L 1850 representam **31.909 eventos (44,9% do volume)** com apenas 92 DGs reais (0,29% de prevalência). **O modelo emite ZERO alertas nessa população** — AUC-PR=0,0077 (essencialmente aleatório), Precision=0, Recall=0. **Magnitude:** crítica. A Frente 1 (alerta operacional 4h, LightGBM v3) **não atende escavadeiras** com o pipeline atual. **Causa provável (não totalmente verificada):** a feature `tipo_caminhao` (binária, 24% do peso SHAP) atua como *gating* — quando `tipo_caminhao=0` (escavadeira), o modelo virtualmente desliga as predições positivas. **Mitigações (CM 6.3):** (a) modelo dedicado para escavadeiras com features específicas (volume baixo de DGs justifica abordagem diferente); (b) política de monitoramento via Frente 2 (Weibull AFT, hazard ratios) que naturalmente reconhece o baixo *base rate* da frota — sobrevivência funciona aqui; (c) revisão do conjunto de features para incluir variáveis específicas de escavadeira (peso de carga, regime de operação estática vs dinâmica). **Insight operacional:** para 45% do parque (medido em eventos), o modelo de classificação atual NÃO é a ferramenta certa — a Frente 2 sim. Reforça a importância da operação integrada das duas frentes.

---

*(Próximas seções a desenvolver em W8: Conclusão geral, refinamento de CM 6.1 (Insights Não Óbvios) e CM 6.3 (Trabalhos Futuros).)*

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
| 16 | `Projeto/codigo/08c_shap_v2.py` | W6 | ✅ | **Análise SHAP do LightGBM v2** via TreeSHAP sobre os 71.089 eventos do test (~1 min). Gera matriz SHAP completa para auditoria + ranking global + estratificações (CA65926 vs resto, conhecidos vs unknown). **Top 3 features:** `horas_desde_ultimo_DG` (39,3%) / `qtd_alarmes_nivel_muito_alto_360min` (31,1%) / `razao_alarme_7d_vs_30d_anterior` (8,6%) — soma 79% do peso. **Achados:** v2 NÃO é baseline glorificado; Família 4 regimal funciona como previsto; Obs 2.11 fracamente refutada; **modelo é predição de cascata, não primeiro DG** (mini-diagnose ad-hoc revelou que top 10% SHAP+ em `horas_desde_ultimo_DG` tem 100% DG anterior em ≤2h; apenas 1% dos primeiros DGs detectados). Motivou treino de v3 (linha 17). Saídas: `Projeto/modelos/shap_values_v2_test.npy` (19 MB) + 2 tabelas + 3 figuras (9a/9b/10). Ver `notas_metodologicas.md` Seção 10. |
| 17 | `Projeto/codigo/08e_lightgbm_v2_no_cascade.py` | W6 | ✅ | **LightGBM v3 — modelo canônico promovido (D-promoção, 24/05).** Clone do `08b_lightgbm_v2.py` com 34 features (sem `horas_desde_ultimo_DG`). Mesma configuração Optuna 50 *trials* + TimeSeriesSplit CV + determinismo. **Resultados:** train=0,9653 / val=0,7132 / test=0,8556 (GATE MARCO 1 PASS — folga +22,5pp em test). Trial #41 best, `scale_pos_weight=2,40`. **Comparativo decisório v2 vs v3 (test):** geral −0,62pp AUC-PR mas +7,24pp Recall; primeiro_DG +0,88pp AUC-PR e +16,72pp Recall (5× mais primeiros DGs capturados); cascata pratically equivalent. Decisão **D-promoção** (v3 substitui v2; v2 preservado como intermediário). Saídas: `Projeto/modelos/lightgbm_v2_no_cascade.txt` + `optuna_study_v2_no_cascade.pkl` + 3 tabelas (`lightgbm_v2_no_cascade_metricas.csv`, `lightgbm_v2_no_cascade_hiperparametros.csv`, `v2_vs_v2_no_cascade.csv`). Tempo: 25,7 min. Detalhe em `controle_alteracoes.md` entrada `2026-05-24 — Promoção de v3`. |
| 18 | `Projeto/codigo/08f_shap_v3.py` | W6 | ✅ | **Análise SHAP do LightGBM v3 (canônico).** Clone funcional do `08c_shap_v2.py` aplicado sobre `lightgbm_v2_no_cascade.txt` no test completo (71.089 × 34, ~80 s). Valida que a remoção de `horas_desde_ultimo_DG` redistribuiu o peso para *features* antecipativas legítimas (não criou nova "feature dominante" problemática). Saídas: `Projeto/modelos/shap_values_v3_test.npy` (18,4 MB) + 2 tabelas (`shap_global_v3.csv`, `shap_estratificado_v3.csv`) + 3 figuras (`fig09c_shap_bar_v3.png`, `fig09d_shap_beeswarm_v3.png`, `fig10b_shap_dependence_top3_v3.png`). Resultados específicos integrados em "Análise SHAP do LightGBM v3" no rascunho. |
| 19 | `Projeto/codigo/09_sobrevivencia.py` | W6 | ✅ | **Modelo de Sobrevivência Weibull AFT (segundo modelo canônico)** com `lifelines`, contra `v3.parquet`. **Construção (T, E):** próximo DG da mesma TAG via `join_asof` forward (T em horas); censoring na última observação da TAG (16% train / 24% val / 57,5% test — assimetria significativa registrada como L9). **Config metodológica:** filtro correlação >0,9 (remove 6 features Família 1) + imputação NaN (`razao_*`→1,0; `taxa_DG_operador_30d`→mediana train; `horas_desde_ultimo_critico`→max train) + StandardScaler em contínuas + fallback automático Cox PH se Weibull C-index val < 0,6 (não acionado). **Resultados:** C-index test=0,7444 / AUC-PR(4h) test=0,3153 / convergência em 37 s. **Top TRs (Time Ratios):** `tipo_caminhao` 0,038 (caminhão tem sobrevida 3% da escavadeira), `frota_793D_5S` 0,169 (maior risco entre 793-D), `tag_freq` 1,432, `count_critico_24h` 0,844 — todos com p < 0,0001. **Concordância forte com SHAP v3** (`tipo_caminhao` e Família 4 regimal coincidem entre as duas técnicas — validação cruzada para CM 5.3). Saídas: `modelos/sobrevivencia.joblib` (14,5 MB) + 3 tabelas (`sobrevivencia_metricas.csv`, `sobrevivencia_hazard_ratios.csv`, `sobrevivencia_features_excluidas_corr.csv`) + Fig Extra A (`figExA_kaplan_meier_por_frota.png`). Tempo: 56 s. Detalhes em `notas_metodologicas.md` Seção 13. |
| 20 | `Projeto/codigo/11_isolation_forest.py` | W6 | ✅ | **Isolation Forest diagnóstico do Risco 3.3 (viés do label CMA).** Treinado SEM usar `Is_Dont_Go`, com 34 features alinhadas ao v3, 200 árvores, seed=42. **Achados em camadas:** (i) AUC-ROC por split: train=0,575 / val=0,598 / **test=0,860** (assimetria suspeita); (ii) Estratificação CA65926: CA65926 apenas AUC=0,897 vs resto do test AUC=0,541; (iii) **Análise estrutural por TAG (30 TAGs, 26 com AUC válido): AUC mediana=0,6060, apenas 3 TAGs com sinal forte e sample significativo (CA65926, CA65932, CA65924)**. CA65924 é o caso paradigma de W4 — **validação independente sem usar o rótulo**. **Veredito:** Risco 3.3 PARCIALMENTE MITIGADO — CMA captura anomalias mecânicas dominantes em poucos equipamentos, mas é essencialmente aleatório em >88% das TAGs. **Implicação crítica (L10 em CM 6.2):** performance alta do v3 em test é largamente dirigida pela detecção do CA65926 e poucos outros; em deployment sem anomalia dominante, performance pode degradar. **Convergência metodológica (CM 6.1):** SHAP do v3, Weibull AFT, e IF não-supervisionado chegam à mesma conclusão sobre a natureza atípica do test. Saídas: `modelos/isolation_forest.joblib` (0,58 MB) + 5 tabelas (`if_auc_roc.csv`, `if_auc_estratificado_test.csv`, `if_auc_por_tag.csv`, `if_diagnostico.csv`, `if_contingencia.csv`) + Fig Extra D (**4 painéis** incluindo barras horizontais de AUC por TAG). Tempo: 9,2 s. Detalhes em `notas_metodologicas.md` Seção 14. |
| 21 | `Projeto/codigo/12_validacao_sentido_features.py` | W6 (fechamento) | ✅ | **Validação cruzada SHAP × Hazard Ratios** — cruza top features do LightGBM v3 com top TRs do Weibull AFT. **4 features no top 10 de AMBOS** (`tipo_caminhao`, `tag_freq`, `frota_793D_4S`, `frota_793D_5S` — todas estruturais). Divergências instrutivas: SHAP destaca antecipativas (`qtd_alarmes_muito_alto`, `razao_alarme_*`); Weibull destaca base rate. Material direto para CM 5.3 (validação por método independente). Saída: `validacao_sentido_features.csv`. Tempo: < 5 s. |
| 22 | `Projeto/codigo/13_curvas_comparativas.py` | W6 (fechamento) | ✅ | **Fig 9 — Curvas ROC + PR comparativas (3 modelos)** sobre o test set. Métricas agregadas: Baseline (count_critico_4h) AUC-PR=0,5803 / **v3 AUC-PR=0,8556** / Weibull AFT AUC-PR=0,3148. v3 domina em AUC-PR; Weibull supera baseline em AUC-ROC mas perde em AUC-PR (otimiza C-index). Saídas: `fig09_curvas_comparativas.png` (2 painéis) + `comparacao_modelos_test.csv`. Tempo: ~30 s. |
| 23 | `Projeto/codigo/14_calibracao_v3.py` | W6 (fechamento) | ✅ | **Calibração do v3 + Platt scaling (Qualidade A).** **v3 raw:** Brier test=0,05745 (skill +0,59), ECE test=3,78pp. **Platt scaling melhora val (3,70→1,87pp) MAS piora test (3,78→4,76pp)** — drift de calibração entre regimes (sintoma adicional de L4/L10). **Recomendação: NÃO aplicar Platt em deployment**, manter v3 raw. Calibrador salvo apenas para auditoria. Saídas: `calibracao_v3.csv` + `figExF_calibracao_v3.png` (2 painéis) + `calibrador_v3_platt.joblib` (marcado "não usar"). Tempo: ~15 s. |
| 24 | `Projeto/codigo/15_ablation_grupos.py` | W6 (fechamento) | ✅ | **Ablation por grupo de features (Profundidade 2).** Re-treina v3 com hiperparams FIXOS removendo cada um de 7 grupos. **Achado surpreendente:** **nenhum grupo é estritamente necessário** — variação máxima ±0,01 AUC-PR. Apenas G7 regimal causa queda real (−0,0044). G4 operador e G6 categóricas **melhoram** AUC-PR ao serem removidos (+0,0064). **Insight metodológico para CM 6.1:** SHAP mede atribuição, ablation mede necessidade — a diferença é **redundância**. v3 entrega 0,8556 AUC-PR no test por múltiplas rotas redundantes, coerente com L10. Saídas: `ablation_grupos.csv` + `figExE_ablation_grupos.png`. Tempo: ~110 s (8 retreinos × ~13 s). |
| 25 | `Projeto/codigo/10_evaluation.py` | W7 | 🔄 planejado | Métricas finais estratificadas (mês × frota × estado operacional × top-5 alarmes) + figuras 9-13 do relatório + análise de erro por contexto + curva *precision-recall* com limiar operacional calibrado por custo-benefício explícito. |

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
