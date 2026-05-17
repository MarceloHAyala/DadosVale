# Rascunho do Relatório — Programa Desenvolver 2026

Documento de escrita progressiva que vai consolidando as seções do relatório final ao longo das semanas W2→W8. Será migrado para `Desenvolver_Template.docx` em W9.

**Status atual:** seção de EDA (W2) preenchida com base nos achados consolidados em `PLANEJAMENTO.md`, `hipoteses_eda.md`, `controle_alteracoes.md` e nos artefatos gerados (figuras, tabelas).

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
| 3 | `Projeto/codigo/03_limpeza.py` | W1 | ✅ | `dados/intermediarios/telemetria_limpa.parquet` + `relatorio/tabelas/estatisticas_descritivas.csv` + `relatorio/tabelas/inspecao_inicial.md` |
| 4 | `Projeto/codigo/04_eda.py` | W2 | ✅ | 7 figuras em `relatorio/figuras/` (fig02-fig06 + figExB + figExG) + `relatorio/tabelas/dgs_por_frota_tipo_classe.csv` |
| 5 | `Projeto/codigo/exploracao_w2_obs.py` | W2 | ✅ | Análises ad-hoc impressas no terminal — investigações das observações 2.1, 2.2, 2.5, 2.6 e 2.7 |
| 6 | `Projeto/codigo/extrai_eventos_muito_alto.py` | W2 | ✅ | `relatorio/tabelas/eventos_muito_alto.csv` (82 regras CMA com nível "Muito Alto") |
| 7 | `Projeto/codigo/04_features.py` | W3-W4 | 🔄 planejado | `dados/features/v1.parquet` + `dados/features/v2.parquet` + `relatorio/tabelas/documentacao_features.csv` |
| 8 | `Projeto/codigo/05_split.py` | W4 | 🔄 planejado | partição temporal treino (jan-abr) / validação (mai) / teste (jun) |
| 9 | `Projeto/codigo/06_baseline.py` | W5 | 🔄 planejado | modelo baseline heurístico + métricas |
| 10 | `Projeto/codigo/07_lightgbm.py` | W5-W6 | 🔄 planejado | LightGBM v1 (defaults) + v2 (após Optuna, 50 trials) — `modelos/lightgbm_v2.lgb` |
| 11 | `Projeto/codigo/08_sobrevivencia.py` | W6 | 🔄 planejado | Weibull AFT (fallback Cox PH) — `modelos/sobrevivencia.joblib` + tabela hazard ratios + Fig Extra A (curva K-M) |
| 12 | `Projeto/codigo/10_isolation_forest.py` | W6 | 🔄 planejado | Isolation Forest diagnóstico (teste empírico do viés do label CMA) — `modelos/isolation_forest.joblib` + `relatorio/tabelas/if_diagnostico.csv` |
| 13 | `Projeto/codigo/09_evaluation.py` | W7 | 🔄 planejado | Métricas finais estratificadas + figuras 9, 10, 11, 12, 13 + análise de erro por mês/frota/estado |

**Comando de execução padrão:**
```powershell
uv run python Projeto/codigo/<nome_do_script>.py
```

**Nota de numeração:** a numeração 04-10 dos scripts planejados pode passar por reconciliação quando forem implementados (atualmente `04_eda.py` ocupa a posição originalmente prevista para `04_features.py`). A reconciliação será registrada em `controle_alteracoes.md` quando ocorrer.

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
