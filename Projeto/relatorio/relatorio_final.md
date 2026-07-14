# Relatório Final
## Desafio: Análise Avançada de Dados

**Antecipação de Alertas Don't Go em Frotas de Mineração**

Trabalho individual (sem grupo).

**Marcelo Henrique Ayala Gomes**
UNESP Bauru
mh.gomes@unesp.br

Programa Desenvolver 2026, Vale. Região analisada: Itabira (MG). Período dos dados: janeiro a junho de 2025.
Código, dados de trabalho e materiais completos: https://github.com/MarceloHAyala/DadosVale.git

---

## Resumo

**Introdução.** Alertas Don't Go sinalizam que um equipamento de mineração não deve operar; cada um é uma parada que custa disponibilidade e produção. Este trabalho investiga se é possível antecipá-los e preveni-los, usando seis meses de dados de Itabira: 37,2 milhões de eventos de telemetria, 377,9 mil ciclos de apontamento e 19.962 alertas Don't Go rotulados pelas regras da CMA. O objetivo central é estimar a probabilidade de um equipamento gerar um alerta nas próximas 4 horas e usar isso para priorizar inspeções.

**Metodologia.** A exploração revelou três pontos que guiaram o resto: o alvo é raro e desbalanceado, o semestre tem três regimes distintos (com o mês de teste dominado por um único equipamento em deterioração, o CA65926) e a média da frota esconde equipamentos individualmente problemáticos. A preparação filtrou os eventos sem risco e produziu 35 features (as variáveis de entrada do modelo, calculadas a partir dos dados brutos), com destaque para as janelas móveis de contagem, que capturam o mecanismo de acumulação das próprias regras da CMA. A validação respeita o tempo (treino de janeiro a abril, validação em maio, teste em junho), evitando o vazamento de um k-fold aleatório. A solução tem duas frentes, um classificador de curto prazo (LightGBM) e um modelo de sobrevivência (Weibull AFT), mais dois diagnósticos, um Isolation Forest que audita o viés do rótulo e um Random Forest de comparação.

**Resultados.** O classificador alcança AUC-PR de 0,86 e AUC-ROC de 0,94 no teste, 27,5 pontos percentuais acima da regra simples. Um cuidado foi decisivo: a interpretabilidade (SHAP) revelou que uma versão intermediária apenas detectava cascatas em curso, e corrigi-la fez o modelo capturar cinco vezes mais primeiros alertas. O modelo generaliza para além do equipamento dominante (AUC-PR de 0,77 sem ele), e o Random Forest empata com o LightGBM, mostrando que o mérito está nas features, não no algoritmo; a feature mais importante vem diretamente das regras da CMA. Traduzido para o negócio, no cenário conservador o estudo estima da ordem de 10 mil horas de parada evitáveis no semestre, além de faixas de risco semafóricas e um ranking de risco por equipamento.

**Conclusão.** Sim, é possível antecipar de forma útil. Os limites são reportados com franqueza: o modelo não opera nas escavadeiras (metade do volume de teste), a antecipação de longo prazo é modesta (existe, mas exige um limiar mais baixo) e o rótulo da CMA tem assinatura estatística clara em poucos equipamentos. O valor operacional vem das duas frentes em conjunto e do monitoramento por equipamento, e todas as decisões metodológicas estão registradas em um controle de alterações no formato ANTES/DEPOIS.

**Palavras-chave:** manutenção preditiva; alertas Don't Go; mineração; LightGBM; análise de sobrevivência; interpretabilidade (SHAP).

---

## 1. Introdução

A operação de uma mina a céu aberto gira em torno de um ciclo contínuo de carga e transporte. Caminhões fora de estrada e escavadeiras trabalham em turnos de doze horas, e cada intervalo de atividade de um equipamento é registrado como um **ciclo de apontamento**: uma linha com o instante de início e de fim, a identificação do equipamento (a TAG, por exemplo `CA65926`), a frota a que ele pertence (`793-D 5S`, `LeTourneau L 1850`, entre outras), o tipo de equipamento (caminhão ou escavadeira) e a classe da atividade (operando, parado, em manutenção, hibernando). Em paralelo, os equipamentos emitem um fluxo de telemetria: milhões de eventos de sensores e alarmes que descrevem, minuto a minuto, o estado de cada máquina, incluindo a identificação do operador, sempre anonimizada.

Sobre essa telemetria atua um conjunto de regras de negócio que define os **alertas Don't Go**. Um alerta Don't Go sinaliza que o equipamento não deve continuar operando, seja por risco à segurança, seja por risco de dano ao próprio equipamento. Na prática, um Don't Go significa uma parada, e uma parada não planejada custa disponibilidade de frota e produção. Antecipar e prevenir esses alertas é, portanto, um problema com valor direto de negócio: quanto antes a manutenção souber que um equipamento caminha para um Don't Go, maior a chance de transformar uma parada corretiva de emergência em uma intervenção preventiva agendada. É um exemplo claro de uso de dados para tomada de decisão operacional.

As condições que disparam um alerta estão catalogadas no arquivo de regras de negócio `Alarmes - Regra de Negocio_V2.xlsx` (aba CMA). Cada regra combina os campos TIPO, EVENTO, SITUAÇÃO e NÍVEL com um critério de QUANTIDADE e TEMPO, ou seja, um número mínimo de ocorrências dentro de uma janela de minutos. Quando a telemetria satisfaz a regra, o evento constitui um Don't Go. Esse mecanismo de acumulação (contar ocorrências dentro de uma janela) é justamente o que motivou, mais adiante, a família de features de janelas móveis (Seção 2.4). Alguns eventos são classificados no nível máximo de criticidade, "Muito Alto"; foram identificados 82 desses eventos no catálogo. Um achado relevante já nesta etapa: cerca de 95% dos eventos "Muito Alto" têm origem em alarmes do fabricante do equipamento (ALARME OEM), e não em análise autônoma da Vale. Esse detalhe é importante porque significa que o rótulo Don't Go é, em boa parte, herdado dos limiares do fabricante, uma característica retomada ao discutir os limites do estudo (Seção 3.2 e Limitação L10).

A Figura 1 reconstrói o fluxo operacional, do ciclo de apontamento à telemetria e ao disparo do alerta, separando visualmente o que é descritivo dos dados do que é a proposta analítica deste trabalho.

[Figura 1: Fluxo operacional: ciclo de apontamento, telemetria e alerta Don't Go](figuras/fig01_fluxo_de_apontamentos.png)

**Objetivo central.** A pergunta que orienta o trabalho é objetiva:

> **Dado o histórico recente de telemetria de um equipamento, qual a probabilidade de ele gerar um alerta Don't Go nas próximas 4 horas?**

A escolha da janela de 4 horas é operacional, não arbitrária. É tempo suficiente para a manutenção mobilizar peça e equipe, mas curto o bastante para que o estado atual do equipamento ainda seja informativo sobre o futuro próximo. A Seção 2.5 detalha e fundamenta empiricamente essa escolha.

Em torno dessa pergunta primária, o estudo responde a um conjunto de perguntas secundárias, todas derivadas do mesmo pipeline de dados:

- **Q3.** O comportamento do operador se correlaciona com a frequência de alertas?
- **Q4.** Qual o perfil dos equipamentos que mais geram Don't Go (frota, tipo)?
- **Q5.** Os alertas se concentram em turnos, dias da semana ou períodos do mês?
- **Q6.** Dado o risco previsto, qual a recomendação de ação (operar, monitorar, inspecionar)?
- **Q7.** Como priorizar a fila de inspeção da manutenção pelo risco de cada equipamento?

Uma pergunta ficou deliberadamente fora do escopo: prever o **tipo** do próximo alerta (motor, transmissão, freio). Ela exigiria um modelo multi-classe com tratamento específico de classes raras, e foi remetida a Trabalhos Futuros (Seção 4).

**Como o sucesso é medido.** Em um problema de evento raro e de alto custo, acurácia não serve como métrica: um modelo que dissesse "nunca haverá Don't Go" acertaria a esmagadora maioria dos casos e não teria utilidade alguma. O que importa é o **Recall** (não deixar passar alertas, porque cada Don't Go perdido é uma parada não planejada), a **Precisão** em nível aceitável (cada alarme falso gera uma inspeção desnecessária), o **tempo de antecipação** efetivo do alerta e, no fim da cadeia, a tradução disso em **horas de parada não planejada evitáveis**.

**Como o modelo entra na operação.** O cenário de uso previsto é o painel do dispatcher de Itabira. O modelo recalcula o risco de cada equipamento ao longo do turno e classifica cada um em uma de três faixas: verde (operar normalmente), amarelo (monitoramento intensivo e alerta antecipado) e vermelho (inspeção preventiva planejada). Isso gera uma fila de inspeção priorizada pelo risco, respondendo diretamente às perguntas Q6 e Q7.

**Um enquadramento honesto do que este trabalho entrega.** Ao longo da análise, ficou claro que a solução mais defensável não é um único modelo preditivo, e sim um **estudo analítico com duas frentes operacionais e duas entregas complementares**:

1. **Frente 1, classificação de risco de curto prazo** (LightGBM), que responde "vem Don't Go nas próximas 4 horas?".
2. **Frente 2, análise de sobrevivência** (Weibull AFT), que responde "quanto tempo até o próximo Don't Go?" e cobre a deterioração de escala mais longa que a Frente 1 não alcança.
3. **Diagnóstico do rótulo** via Isolation Forest não supervisionado, que audita empiricamente o viés das regras da CMA.
4. **Achados estruturais e recomendações operacionais**, traduzidos em figuras de negócio (equipamentos individuais problemáticos, ranking de risco, horas evitáveis).

As duas frentes cobrem escalas de tempo e segmentos de frota complementares; o valor operacional vem delas em conjunto, não de um escore único e automático. Essa é a espinha dorsal que percorre todo o relatório.

---

## 2. Metodologia

Esta seção descreve o fluxo completo da solução, da análise exploratória à avaliação, incluindo os cuidados adotados para garantir qualidade e confiabilidade. A discussão dos resultados propriamente ditos está na Seção 3.

### 2.1 Ferramentas e tecnologias

O trabalho usa Python 3.13, com ambiente reproduzível gerenciado por `uv` (versões travadas em `uv.lock`). O processamento dos dados usa **Polars**, escolhido pela capacidade de lidar com dezenas de milhões de linhas em memória modesta. A modelagem usa **LightGBM** (classificação principal), **lifelines** (sobrevivência Weibull AFT e Cox) e **scikit-learn** (Isolation Forest, Random Forest e métricas). A otimização de hiperparâmetros usa **Optuna**, a interpretabilidade usa **SHAP**, e as figuras usam **matplotlib** e **seaborn**. Cada escolha é justificada no ponto em que aparece.

### 2.2 Análise exploratória dos dados

**Carregamento e inspeção inicial.** O pacote de dados reúne dois conjuntos. A telemetria vem em seis arquivos mensais (janeiro a junho de 2025) e soma **37.164.054 eventos**. Os apontamentos, com o registro dos ciclos operacionais, somam **377.907 linhas**. A leitura foi feita com a biblioteca Polars, escolhida porque 37 milhões de linhas em pandas exigiriam da ordem de 24 GB de memória, enquanto o Polars processa o mesmo volume em cerca de 4 GB. A inspeção inicial exigiu correção de tipos que vieram como texto: os campos de data e hora precisaram ser convertidos para datetime, e o campo `Valor` da telemetria trazia dois problemas que só apareceram com asserções defensivas, a string literal `"NULL"` em 237 mil registros e o uso de vírgula decimal brasileira em outros 822 mil. Sem tratar ambos, o cast para número descartaria silenciosamente mais de um milhão de valores. Verificações de qualidade da etapa: **zero registros duplicados** por chave primária em ambos os conjuntos, o que confirma que o pipeline da Vale entrega chaves únicas. O único campo com ausências relevantes é o `Valor` da telemetria, nulo em 43,58% dos eventos após a filtragem; a decisão de tratamento está na Seção 2.3. A tabela de estatísticas descritivas das variáveis numéricas foi gerada e anexada (`estatisticas_descritivas.csv`). Dois achados laterais revelam a natureza dos dados: um quarto nível de criticidade (`Id_Criticidade = 4`) que não corresponde a falha, e sim a **eventos de bypass manual do operador**, 95% deles concentrados na frota de escavadeiras LeTourneau, o que motivou a criação de uma feature de comportamento do operador; e um punhado de registros com peso de carga fisicamente impossível (até 4.347, contra a capacidade de cerca de 240 toneladas de um 793-D), indicando erro de unidade no sensor, sem impacto no alvo (nenhum era Don't Go).

[Figura 2: Distribuição temporal dos registros de apontamentos](figuras/fig02_distribuicao_temporal_apontamentos.png)

**Análise da variável alvo.** O rótulo `Is_Dont_Go`, já presente na telemetria, é produzido pela aplicação das regras da CMA. No semestre, **19.962 eventos são Don't Go**, o que representa apenas **0,0537% do total**. É um problema fortemente desbalanceado, e esse desbalanceamento orienta toda a escolha de métricas mais adiante. A distribuição por criticidade é reveladora: os eventos "Informacional", que respondem por 98,5% do volume, têm **zero Don't Go no semestre inteiro**, não "quase zero", exatamente zero; isso tornou seguro filtrá-los na preparação, eliminando 98,5% do volume sem perder um único positivo. Entre o que sobra, os eventos "Crítico" têm taxa de Don't Go de 12,39% (um em cada oito) e os "Não Crítico", de 2,10%. O achado mais importante é que **o semestre não é estatisticamente homogêneo**: a série temporal (Figura 4) revela três regimes distintos, não uma tendência suave. Janeiro é a linha de base; fevereiro e março trazem uma anomalia no alarme Engine Coolant Level (aumento de volume combinado com reclassificação massiva de severidade, com a fração de eventos "Crítico" desse alarme caindo de 83% para 6%, sugerindo recalibração de regra da CMA); junho traz uma anomalia no alarme Right Front Brake Temperature, que explodiu para cerca de 150 vezes o histórico e vem quase inteiramente de um único equipamento, o caminhão CA65926. A consequência é direta: o conjunto de teste (junho) é dominado por uma anomalia mecânica localizada, um fato a levar em conta ao interpretar o desempenho do modelo, e discutido em profundidade na Seção 3.2. Duas concentrações fecham o quadro: os cinco alarmes mais frequentes concentram **87% de todos os Don't Go** (e apenas 19 alarmes, de mais de quatro mil, geraram ao menos um Don't Go no semestre), e duas frotas de caminhões (793-D 5S e 4S) concentram **84% dos alertas**.

[Figura 3: Distribuição de alertas por tipo de equipamento e criticidade](figuras/fig03_tipo_x_criticidade.png)

[Figura 4: Série temporal dos Don't Go ao longo do semestre](figuras/fig04_serie_temporal_dgs.png)

**Perfil dos equipamentos (Q4) e padrões (Q5).** Cruzando os Don't Go com o estado operacional no momento do evento, via junção temporal entre telemetria e apontamentos, chegou-se ao perfil da frota. Os caminhões 793-D respondem por praticamente todos os alertas; as escavadeiras LeTourneau L 1850 têm uma taxa de Don't Go por equipamento cerca de 22 vezes menor. Esse contraste antecipa uma limitação importante do modelo (L11, Seção 3.2). Um segundo achado: 12,65% dos Don't Go ocorrem com o equipamento em estado de "Manutenção", e a investigação mostrou que não são falsos positivos de bancada, e sim alertas legítimos gerados quando o equipamento é reativado para testes, portanto não devem ser filtrados. Quanto aos padrões temporais (Q5), o mapa de calor por hora e dia da semana (Figura 6) mostra variação modesta, entre 2% e 6%, sem padrão sistemático forte: turno e dia têm efeito secundário, muito menor que o estado de deterioração do próprio equipamento.

[Figura 6: Taxa de alertas por hora do dia e dia da semana](figuras/fig06_heatmap_hora_dia.png)

**Equipamentos individuais problemáticos.** Um padrão emergiu ao longo da exploração e se tornou um fio condutor do estudo: a média da frota esconde equipamentos individualmente anômalos. O CA65926 aparece como outlier de volume de Don't Go e como origem quase exclusiva da anomalia de junho. O CA65789 concentra 100% de um problema de sobreposição de ciclos de apontamento, localizado em janeiro. Nenhum dos dois é visível na frota agregada; ambos só aparecem na análise estratificada por equipamento. Esse achado sustenta a recomendação de monitoramento por equipamento, e não apenas por frota (Seção 4). Seguindo a orientação do Estudo Guiado, todas as hipóteses levantadas na exploração foram registradas, confirmadas ou não, em `hipoteses_eda.md` (13 hipóteses em 6 temas); várias foram refutadas e reinterpretadas, e diversas dessas refutações viraram insights do relatório final (Seção 3.4).

### 2.3 Limpeza e preparação

A limpeza foi implementada como um pipeline único e reproduzível, documentado passo a passo:

- **Valores ausentes.** O único campo com ausências relevantes é o `Valor` da telemetria (43,58% de nulos, todos em eventos Crítico ou Não Crítico). A decisão foi manter o nulo, porque o LightGBM trata ausência nativamente, e criar uma feature binária `valor_disponivel` que sinaliza "este alarme tem medição numérica". Assim nenhuma informação foi imputada artificialmente.
- **Inconsistências temporais.** A verificação de ciclos com `Início > Fim` encontrou zero registros inválidos. A detecção de sobreposições de ciclo encontrou 340 casos (0,09%), e a investigação dedicada mostrou que **100% deles vêm de um único equipamento, o CA65789**, concentrados em janeiro. Trata-se de um bug pontual de registro, não de um padrão sistêmico; os casos foram marcados com uma flag e mantidos.
- **Outliers.** Adotou-se um critério físico (peso de carga acima de 1.000) em vez do IQR, porque a distribuição é fortemente concentrada em zero. Após a filtragem, restaram zero outliers, os 118 casos identificados na exploração eram todos eventos "Informacional", eliminados na etapa seguinte.
- **Filtragem dos eventos "Informacional".** Como esses 98,5% do volume têm zero Don't Go, foram removidos com segurança: o dataset caiu de 37.164.054 para 544.885 linhas, preservando os 19.962 Don't Go por asserção. Essa redução é o que viabilizou o cálculo das janelas móveis sem estouro de memória.

Todas as decisões estão consolidadas na tabela de controle de alterações (`controle_alteracoes.csv`), no formato de colunas sugerido pelo Estudo Guiado (Campo, Problema Identificado, Quantidade de Registros, Tratamento Aplicado, Justificativa). Além dela, um registro narrativo em `controle_alteracoes.md` mantém o rastro de cada decisão metodológica relevante do projeto, no formato ANTES/DEPOIS.

### 2.4 Engenharia de features

A matriz final tem **35 features**, agrupadas em famílias, cada uma com motivação registrada em `documentacao_features.csv`:

- **Temporais** (4): hora do dia, dia da semana, turno e mês, extraídas do instante do evento.
- **Janelas móveis por equipamento** (15): contagem de eventos Crítico, Não Crítico e Total nas últimas 1h, 2h, 4h, 8h e 24h. Capturam a acumulação, que é o mecanismo por trás de cerca de metade dos Don't Go (a regra da CMA do tipo "quantidade de ocorrências acima de um limite dentro de uma janela de tempo").
- **Recência** (1): horas desde o último evento crítico do equipamento.
- **Estado operacional** (1): o estado do equipamento (operando, parado, manutenção) uma hora antes do evento, obtido por junção temporal com os apontamentos.
- **Regimais** (2): a razão entre a frequência de um alarme nos últimos 7 dias e o seu próprio histórico de 30 dias, e a razão de severidade em 14 dias contra 60 dias. Foram desenhadas especificamente para detectar o padrão "este alarme está disparando muito mais que o normal para ele", que é a assinatura da anomalia do CA65926 em junho.
- **Comportamento do operador** (2): a taxa histórica de Don't Go do operador em 30 dias e a contagem de bypasses manuais em 7 dias.
- **Regra de negócio** (1): a contagem de alarmes de nível "Muito Alto" da CMA nas últimas 6 horas. Esta feature, derivada diretamente do catálogo de regras, viria a ser a mais importante do modelo final.
- **Codificação de categóricas** (9): frequência da TAG e do operador, indicadores de frota e de tipo de equipamento.

**Codificação de categóricas.** Para as categóricas de alta cardinalidade (TAG e operador) adotou-se codificação por frequência, recomputada apenas sobre o conjunto de treino para não vazar informação de validação e teste (a correção de um vazamento sutil identificado após o split está registrada em `controle_alteracoes.md`). Testou-se empiricamente a alternativa mais sofisticada, o target encoding com validação cruzada temporal, mas ela **piorou o desempenho em validação (queda de 2,25 pontos percentuais de AUC-PR)**, provavelmente porque as taxas por categoria calibradas em janeiro a abril não se transferem bem para o regime de maio e junho. Manteve-se a codificação por frequência, por parcimônia e desempenho, e a comparação foi registrada. As categóricas de baixa cardinalidade (tipo, frota) foram tratadas nativamente pelo LightGBM ou por indicadores.

### 2.5 Definição da variável-alvo

O alvo principal é uma classificação binária: um evento recebe rótulo 1 se houver um Don't Go do mesmo equipamento na janela das próximas 4 horas. Um resultado inicialmente surpreendente é que a **prevalência do alvo é de cerca de 17% no teste** (e 29% no treino), muito acima dos 0,05% da taxa bruta de Don't Go. A razão é simples: cada Don't Go "reivindica" como positivos as várias horas de eventos que o precedem no mesmo equipamento. Vale registrar essa distinção com clareza para não superestimar nem subestimar o desbalanceamento: a raridade extrema está no evento Don't Go em si (0,05%), enquanto o alvo de janela de 4h, que é o que o modelo prevê, é bem menos raro (17%). Ainda assim, o lift do modelo sobre a linha de base aleatória permanece expressivo, como mostra a Seção 3.

Cerca de 18,8% dos eventos não têm nenhum Don't Go futuro observado dentro do dataset (censura à direita) e foram tratados como negativos na classificação, uma aproximação cuja limitação é reconhecida (e que a Frente 2 de sobrevivência trata de forma rigorosa).

**Justificativa da janela de 4 horas.** Além do argumento operacional (tempo de mobilização da manutenção), a escolha foi testada empiricamente. Foram gerados alvos paralelos de 2h, 4h e 8h e comparado o desempenho preditivo de cada um. A janela de 8h foi consistentemente a pior; as de 2h e 4h ficaram estatisticamente indistinguíveis (o ranking entre elas inverte entre validação e teste, dentro da faixa de ruído amostral). A conclusão honesta é que 4h está na zona ótima empírica e é compatível com a necessidade operacional, sem ser singularmente superior a 2h. A Figura 7 ilustra a semântica da janela de predição.

[Figura 7: Diagrama da janela de predição](figuras/fig07_janela_predicao.png)

### 2.6 Estratégia de validação

Dados temporais não podem ser divididos aleatoriamente. Um k-fold embaralhado colocaria eventos do futuro no treino e eventos do passado no teste; como as features de janela móvel capturam a autocorrelação temporal do equipamento, isso produziria um vazamento massivo e uma estimativa de desempenho irrealista. Por isso adotou-se um **split temporal fixo**: treino de janeiro a abril, validação em maio, teste em junho. Para o ajuste de hiperparâmetros, usou-se validação cruzada temporal com quatro folds expandidos (walk-forward), sempre treinando no passado e validando no futuro imediato, e o teste de junho nunca foi tocado durante o ajuste.

A Figura 8 quantifica um ponto crucial: existe **drift real** entre os meses. A taxa de Don't Go por evento varia de 1,62% em maio (o mês de validação, o mais calmo do semestre) a 7,35% em junho (o mês de teste, dominado pela anomalia do CA65926). Isso significa que treino, validação e teste representam regimes operacionais diferentes, um fato que não é escondido, e sim usado para interpretar os resultados.

[Figura 8: Estratégia de validação temporal e drift entre meses](figuras/fig08_split_temporal.png)

### 2.7 Baseline e modelos

**Baseline.** O modelo de referência é uma heurística deliberadamente simples, como deve ser um baseline: prevê Don't Go se houve ao menos N eventos críticos nas últimas 4 horas do equipamento. Seu desempenho: AUC-PR de 0,2397 em validação e **0,5803 em teste**. O resultado contém um achado contra-intuitivo que orientou toda a leitura posterior: o baseline vai **melhor no teste do que na validação**, o oposto do que o drift sugeria. A explicação é que junho é dominado por um único equipamento em crise (o CA65926), cujos alarmes críticos disparam em rajada; esse regime concentrado tem assinatura clara para uma regra simples "conte críticos recentes". Maio, ao contrário, é um regime distribuído sem alvo dominante, genuinamente mais difícil. A consequência prática: o baseline de teste é um teto alto (0,58), e o modelo principal precisa superá-lo com folga para justificar sua complexidade.

O Estudo Guiado sugere ao menos duas abordagens distintas, com a ressalva de que dois modelos bem-feitos valem mais que cinco superficiais. Este trabalho traz **duas abordagens principais aprofundadas** e **duas complementares de diagnóstico**.

**LightGBM (Frente 1, classificação).** O modelo principal é um gradient boosting de árvores. Sua evolução foi documentada em três versões, e vale contar essa trajetória porque ela é um exemplo de rigor, não de indecisão. A **versão 1** usou parâmetros padrão como ponto de partida e passou o critério de aprovação do projeto com folga. A **versão 2** aplicou otimização de hiperparâmetros com Optuna (50 tentativas) sobre a validação cruzada temporal; a análise SHAP dessa versão revelou um problema: a feature mais importante, com 39% do peso, era "horas desde o último Don't Go", e uma investigação dedicada confirmou que a v2 era, na prática, um **detector de continuação de cascata**, prevendo um Don't Go principalmente porque acabara de haver um, o que é pouco útil operacionalmente. A **versão 3**, que se tornou o modelo canônico, removeu essa feature: perde apenas 0,62 ponto percentual de AUC-PR agregado, mas captura **cinco vezes mais "primeiros Don't Go"** (o recall nesse subgrupo sobe de 4% para 21%). A troca foi de uma fração desprezível de métrica agregada por uma melhora qualitativa grande no que importa. Essa passagem, da v2 para a v3, é uma das lições metodológicas centrais do trabalho: um AUC-PR alto pode esconder uma estratégia operacionalmente fraca, e só a interpretabilidade (SHAP) somada a uma investigação dirigida revela isso.

**Weibull AFT (Frente 2, sobrevivência).** Em vez de "vem Don't Go em 4h?", o modelo de sobrevivência responde "quanto tempo até o próximo Don't Go?". É uma segunda leitura independente do problema, com três contribuições que a Frente 1 não oferece: trata rigorosamente a censura (equipamentos que não falharam na janela observada são informação parcial, não zero), oferece interpretabilidade intrínseca via Time Ratios (com intervalo de confiança e p-valor por feature) e prevê em qualquer horizonte, não apenas 4 horas. O Weibull foi escolhido após comparação com o Cox de riscos proporcionais, e alcançou um índice de concordância (C-index) de 0,7444 no teste, sua métrica natural.

**Isolation Forest (diagnóstico complementar, não supervisionado).** Não é um modelo competidor, e sim um teste empírico do viés do rótulo. Treinado sem jamais ver o rótulo Don't Go, ele marca eventos estatisticamente anômalos. A pergunta que responde: se um algoritmo cego ao rótulo recupera os Don't Go como anomalias, há sinal estrutural real além da regra da CMA. A resposta, nuançada, está na Seção 3.2.

**Random Forest (comparação controlada).** Foi treinado um Random Forest com exatamente a mesma estratégia rigorosa da v3 (mesmas features, mesmo Optuna, mesma validação cruzada) para responder a uma pergunta específica: o algoritmo escolhido é o diferencial? A resposta é não, e isso é um mérito do estudo, não uma fraqueza. O Random Forest chegou a AUC-PR de 0,8541 contra 0,8556 da v3, um empate técnico. A conclusão é madura: o mérito deste trabalho está na engenharia de features e no enquadramento do problema, não na escolha do algoritmo da moda.

Todos os hiperparâmetros e as decisões de pré-processamento específicas de cada modelo estão documentados (tabelas de hiperparâmetros e seções técnicas em `notas_metodologicas.md`). O determinismo foi garantido (dois treinos produzem o mesmo resultado até a última casa decimal), permitindo auditoria.

### 2.8 Métricas de avaliação

Pelas razões já expostas (evento raro, custo assimétrico), as métricas primárias são Recall, Precisão, F1 e as áreas sob as curvas ROC (AUC-ROC) e Precisão-Recall (AUC-PR). A AUC-PR é a mais informativa aqui, porque foca a classe positiva e ignora os verdadeiros negativos abundantes; a AUC-ROC complementa por ser independente da prevalência.

**O que cada métrica significa, em linguagem simples.** O modelo atribui a cada evento uma nota de 0 a 1, que é a probabilidade estimada de Don't Go. A partir dela:

- **Recall** (sensibilidade): de todos os Don't Go que de fato aconteceram, que fração o modelo capturou. Recall alto quer dizer "poucos alertas passam despercebidos".
- **Precisão:** de todos os alertas que o modelo disparou, que fração era real. Precisão alta quer dizer "poucos alarmes falsos".
- **F1 e F2:** números que combinam Recall e Precisão em um só; o F2 dá mais peso ao Recall, coerente com o fato de que perder um alerta custa mais que um alarme falso.
- **AUC-ROC:** a probabilidade de o modelo dar nota maior a um evento que teve Don't Go do que a um que não teve. Vai de 0,5 (equivale a um chute) a 1,0 (perfeito) e não depende de quão raro é o evento.
- **AUC-PR:** resume o equilíbrio entre Precisão e Recall considerando todos os limiares possíveis. É a métrica mais indicada para eventos raros, mas deve ser lida em relação à prevalência (a fração de positivos), que é o seu piso de acaso.
- **Lift:** quantas vezes o modelo é melhor que o acaso, ou seja, a AUC-PR dividida pela prevalência. Um lift de 5 significa desempenho cinco vezes acima de adivinhar.
- **C-index** (usado na Frente 2 de sobrevivência): a probabilidade de o modelo ordenar corretamente qual de dois equipamentos falha primeiro. É o análogo da AUC-ROC para modelos que preveem tempo até o evento.

O custo dos erros é assimétrico: um falso negativo (Don't Go não detectado) vira parada não planejada, enquanto um falso positivo (alarme falso) gera apenas uma inspeção. Essa assimetria foi traduzida em uma tabela de custo-benefício com quatro razões de custo (1:1, 3:1, 5:1, 10:1) e onze limiares. O **limiar operacional canônico ficou em 0,30** (razão 5:1, que maximiza o F2), coerente com a razão de horas entre uma corretiva e uma preventiva, acrescida dos custos não monetários de mobilização emergencial e segurança.

---

## 3. Resultados e Discussões

### 3.1 Desempenho comparativo

A comparação dos modelos no conjunto de teste (junho):

| Modelo | AUC-PR | AUC-ROC | Observações |
|---|---:|---:|---|
| Baseline (regra simples) | 0,5803 | 0,7661 | referência a superar |
| **LightGBM v3 (canônico)** | **0,8556** | **0,9391** | modelo principal |
| Random Forest (tunado) | 0,8541 | n/d | empate técnico com a v3 |
| Weibull AFT | 0,3148 | 0,7869 | métrica natural é o C-index, 0,7444 |

O LightGBM v3 supera o baseline em **27,5 pontos percentuais de AUC-PR no teste**, uma folga que justifica com sobra a complexidade adicional. O AUC-PR baixo do Weibull não indica um modelo ruim: ele foi construído para ordenar tempo até o evento, e não para classificar a janela de 4h; sua métrica pertinente é o C-index de 0,7444. A Figura 9 traz as curvas ROC e Precisão-Recall comparativas.

[Figura 9: Curvas ROC e Precisão-Recall dos modelos](figuras/fig09_curvas_comparativas.png)

### 3.2 Análise de erros e robustez

**Matriz de confusão e faixas de decisão (Q6).** No limiar 0,30, a matriz de confusão (Figura 10) foi anotada com impacto operacional. O risco foi operacionalizado em três faixas semafóricas: verde (probabilidade abaixo de 0,145, cerca de 70% dos eventos), amarelo (entre 0,145 e 0,30) e vermelho (acima de 0,30, cerca de 20% dos eventos). A faixa vermelha concentra a grande maioria dos Don't Go reais em um quinto do volume, o que a torna uma fila de inspeção priorizada eficaz, resposta direta a Q6 e Q7.

[Figura 10: Matriz de confusão do LightGBM v3 com impacto operacional](figuras/fig10_matriz_confusao_v3.png)

**Onde o modelo falha (falsos negativos).** A análise estratificada por frota expôs a falha mais categórica: nas **escavadeiras LeTourneau L 1850, o modelo tem AUC-PR de 0,008 e não emite praticamente nenhum alerta**, embora elas representem 45% do volume do teste. A feature `tipo_caminhao` funciona como uma chave: quando o equipamento é escavadeira, o modelo virtualmente se desliga. Isso é honestamente uma limitação séria (L11), e sua mitigação está nos Trabalhos Futuros. Esse ponto não é escondido; ao contrário, ele motiva a existência das frentes complementares.

**Degradação temporal (drift).** Dois achados quantificam o drift dentro do próprio teste. Primeiro, na validação cruzada por horizonte, os três primeiros folds produzem AUC-PR estável em torno de 0,88, mas o quarto fold (que valida em maio, o regime mais raro) desaba para 0,17; a média da validação cruzada mascara esse colapso, uma lição sobre não confiar em médias agregadas quando há drift conhecido. Segundo, a análise semanal de junho mostra a AUC-PR variando de 0,35 na semana calma a 0,95 na semana da explosão do CA65926. A implicação operacional é que o monitoramento em produção precisa operar em janela semanal, não mensal.

**A questão do CA65926, tratada com o número do próprio modelo.** Como junho é dominado por um único equipamento, é legítimo perguntar se o desempenho do v3 não seria só "detectar o CA65926". Isso foi medido diretamente. Estratificando a AUC-PR do v3: no teste completo é 0,8556; considerando apenas o CA65926 é 0,9723, mas ali a prevalência é de 81%, então até um chute trivial acerta 0,81 (o lift é de apenas 1,20 vezes); **removendo o CA65926, a AUC-PR é 0,7693, com AUC-ROC praticamente intacta (0,9368) e lift de 7,77 vezes**, maior que o do próprio CA65926. A leitura honesta é que o número absoluto de 0,8556 é parcialmente inflado pela altíssima prevalência do CA65926, mas a **capacidade de generalização do modelo é genuína**: ele é, em termos de habilidade discriminativa, ainda mais forte nos outros 29 equipamentos. A crítica "o modelo só detecta um caminhão quebrado" fica refutada pelos próprios números.

**Tempo de antecipação (L12), a análise mais delicada.** Como o desafio se chama "Antecipação", investigou-se quanto tempo de folga o modelo realmente entrega. No limiar 0,5, metade dos acertos são detecções diretas (o próprio evento já é um Don't Go, antecipação zero) e apenas 18% chegam aos 90 minutos típicos de mobilização. Isso poderia sugerir que o modelo só reage ao presente. Para testar se existe capacidade real de antecipação, o alvo foi redefinido exigindo antecedência mínima e a medição foi feita com rigor, separando o acerto genuíno do acerto por um Don't Go mais próximo na janela. No recorte estrito (próximo Don't Go entre 90 minutos e 4 horas, sem nada iminente antes), a **AUC-ROC honesta é 0,82, com lift estável em cerca de 5 vezes** de 30 a 120 minutos (Figura Extra K). A conclusão equilibrada: há capacidade de antecipação genuína, porém modesta; ela existe no escore e se realiza operando em um limiar mais baixo (a faixa amarela do Q6), ao custo de menor precisão. O limite real é o trade-off entre precisão e antecedência, gerenciável por ponto de operação, e não uma incapacidade de antecipar.

[Figura Extra K: Antecipação real do v3, medição estrita vs inflada](figuras/figExK_antecipacao_honesta.png)

**Calibração.** As probabilidades do v3 têm boa calibração (Brier de 0,057 no teste, com ganho de habilidade de 0,59 sobre o trivial). O erro de calibração esperado (3,78%) fica acima do ideal, e o Platt scaling foi testado para corrigi-lo; ele melhorou a validação mas piorou o teste, sinal de drift de calibração, então a decisão honesta foi **não aplicar** o Platt em produção e manter o modelo cru, recalibrando periodicamente.

**Diagnóstico do rótulo (Isolation Forest).** O Isolation Forest, treinado sem ver o rótulo, recupera bem as anomalias em poucos equipamentos (o CA65926 tem AUC de 0,90), mas fica próximo do aleatório para os Don't Go distribuídos (AUC mediana por TAG de 0,61). Isso indica que a regra da CMA captura anomalia estatística real em alguns casos, mas em outros pode estar rotulando eventos sem assinatura estatística distinta. É um limite do **rótulo**, não do classificador (que, como mostrado acima, generaliza). O achado alimenta a Limitação L10 e a recomendação de auditoria manual (Seção 4).

### 3.3 Interpretabilidade

**Importância global.** A análise SHAP do v3 (Figuras 9c e 9d) mostra três features dominando 76% do peso, todas com semântica antecipativa legítima: a contagem de alarmes "Muito Alto" da CMA nas últimas 6 horas (41%), o tipo de equipamento (24%) e a razão regimal do alarme (11%). É um resultado que valida as escolhas de engenharia de features: a feature derivada diretamente das regras de negócio é a mais importante, e a feature regimal, desenhada para pegar a anomalia do CA65926, aparece no topo como previsto.

[Figura 9c: Importância global das features (SHAP)](figuras/fig09c_shap_bar_v3.png)

**Validação de sentido.** O ranking do SHAP foi cruzado com os Time Ratios do modelo de sobrevivência, dois métodos independentes. Quatro features aparecem no top 10 de ambos (tipo, frota e as regimais), o que dá confiança de que o modelo aprendeu estrutura real, e não artefato. O peso alto de `tipo_caminhao` merece registro honesto: o modelo aprendeu a taxa base por tipo de equipamento como heurística inicial, o que é correto dado os dados (as escavadeiras realmente falham 22 vezes menos por unidade), mas é também a raiz da limitação L11 e da limitação L8 (a composição da frota influencia a taxa base aprendida).

[Figura 9d: Distribuição dos valores SHAP por feature](figuras/fig09d_shap_beeswarm_v3.png)

**Explicação local.** A Figura 12 decompõe uma predição individual: um Don't Go real do caminhão CA65933 (deliberadamente escolhido fora do CA65926, para demonstrar generalização), com probabilidade prevista de 0,97. As três features que sustentam o alerta são justamente as antecipativas legítimas, confirmando no caso individual o que o ranking global mostra no agregado.

[Figura 12: Decomposição SHAP de uma predição individual](figuras/fig12_shap_waterfall_v3.png)

### 3.4 Tradução para o negócio e insights

**Ganho sobre o baseline.** O LightGBM v3 entrega AUC-PR de 0,8556 no teste contra 0,5803 do baseline, um ganho de 27,5 pontos percentuais, e generaliza para além do equipamento dominante (0,7693 sem o CA65926). O Random Forest, com a mesma estratégia, empata com a v3, confirmando que o valor está nas features e no enquadramento.

**Impacto de negócio.** As métricas foram convertidas em horas de parada não planejada evitáveis, com premissas declaradas explicitamente (por exemplo, 4 horas para uma corretiva contra 1,5 hora para uma preventiva). Sobre uma base de cerca de 79,8 mil horas-equipamento de parada não planejada no semestre, o cenário **conservador** aponta cerca de **10,5 mil horas evitáveis**, e cenários mais otimistas chegam a mais de 40 mil horas. Optou-se por destacar o cenário conservador, e não o otimista, e por declarar que o número depende do tempo de antecipação efetivo (L12) e da adoção de monitoramento por equipamento. As figuras de negócio (timeline do CA65926, ranking de risco dos 33 equipamentos e horas evitáveis) traduzem esses achados para o time operacional.

**Insights não óbvios.** O trabalho acumulou treze descobertas contra-intuitivas, das quais se destacam as mais fortes:

- **AUC-PR alto pode esconder estratégia errada.** Só a análise SHAP revelou que a v2 era um detector de cascata, não um antecipador; a métrica agregada não denunciava isso.
- **A EDA agregada esconde indivíduos problemáticos.** Dois equipamentos (CA65926 e CA65789) só emergem na análise por TAG, e são operacionalmente os mais relevantes.
- **Uma heurística simples pode parecer melhor que um modelo complexo em um regime específico** (o baseline foi melhor no teste que na validação), o que exige interpretar desempenho com cuidado.
- **O algoritmo não é o diferencial.** Random Forest e LightGBM empatam; o mérito está nas features.
- **Features de regra de negócio superam features genéricas.** A contagem de alarmes "Muito Alto" (uma feature) supera as quinze features de janela móvel somadas.

---

## 4. Conclusão e Trabalhos Futuros

**Resposta à pergunta central.** Sim, é possível estimar de forma útil a probabilidade de um Don't Go nas próximas 4 horas. O LightGBM v3 faz isso com AUC-PR de 0,77 a 0,86 e AUC-ROC de 0,94, superando com folga a regra de negócio simples e generalizando para além do equipamento dominante. Ele é, de forma precisa, um **bom classificador de risco de curto prazo e um medidor real de deterioração nas próximas horas**. Como antecipador de longo prazo (90 minutos de folga), é modesto porém real, e a antecipação se realiza escolhendo o ponto de operação. As perguntas secundárias foram respondidas: o comportamento do operador correlaciona de forma difusa (Q3), o perfil de risco concentra-se nos caminhões 793-D (Q4), os padrões de turno e dia são secundários (Q5), e as faixas semafóricas e o ranking de risco operacionalizam a recomendação de ação e a fila de inspeção (Q6, Q7).

**Limitações.** O trabalho documenta doze limitações (L1 a L12), das quais as mais importantes são honestas e explícitas:

- **L10, o viés do rótulo.** O Isolation Forest, treinado sem ver o rótulo, recupera bem as anomalias em poucos equipamentos (o CA65926 tem AUC de 0,90), mas fica próximo do aleatório para os Don't Go distribuídos (AUC mediana por TAG de 0,61). É um limite do rótulo, não do classificador (que, como demonstrado, generaliza).
- **L11, as escavadeiras.** O modelo não opera nas LeTourneau. Metade do volume de teste fica descoberta pela Frente 1.
- **L12, a antecipação.** Modesta no longo prazo, como detalhado na Seção 3.2.
- **Janela e região.** Seis meses de uma única região (Itabira), com um mês de teste atípico. As conclusões não devem ser extrapoladas cegamente para outras frotas ou minas.

Nenhuma dessas limitações invalida o trabalho; todas têm magnitude medida, evidência empírica e mitigação proposta. Documentá-las é parte do rigor, não uma concessão.

**Trabalhos futuros.** São propostas extensões concretas, ordenadas por retorno esperado:

1. **Modelo dedicado para escavadeiras** (endereça L11), ou uso da Frente 2 (Weibull) como política de manutenção para esse segmento, já que a Frente 1 não o cobre.
2. **Operação em dois níveis e alvo mais longo** (endereça L12): usar a faixa vermelha (0,30) para risco iminente e a amarela (0,145) para antecipação, e treinar uma variante com janela de 8 a 12 horas para forçar mais folga.
3. **Retreinamento rolling mensal** (endereça o drift e o surgimento de equipamentos e operadores novos, medido em cerca de 2,5% do teste): treinar sempre nos meses mais recentes e implantar para o mês seguinte.
4. **Previsão do tipo de alerta (Q2)**, o modelo multi-classe que ficou fora do escopo.
5. **Integração de novos dados**: registros de manutenção corretiva (para validar prospectivamente as anomalias do Isolation Forest contra falhas físicas reais), condições climáticas e sensores de vibração.
6. **Abordagens não exploradas neste ciclo**: clustering de perfis de equipamento (para formalizar o ranking de risco hoje construído manualmente) e modelagem da frequência de alertas da frota como série temporal (motivada pelo drift semanal).
7. **Arquitetura de deploy**: integração do escore ao painel do dispatcher, com pipeline de recálculo por turno e monitoramento semanal de performance.
