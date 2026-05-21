# Hipóteses da EDA — Consolidação

Documento de trabalho que registra **todas** as hipóteses analíticas levantadas durante a Exploração de Dados (W1 e W2), com status atual de cada uma.

**Convenções de status:**
- ✅ **Confirmada** — testada empiricamente, evidência suporta
- ❌ **Refutada** — testada empiricamente, evidência contradiz
- 🟡 **Refutada com reinterpretação** — a hipótese cai, mas a investigação produz um achado alternativo relevante
- 🔄 **Pendente** — registrada para investigar em W3-W7

Detalhes completos dos testes empíricos estão em [`PLANEJAMENTO.md`](../../PLANEJAMENTO.md) → "Observações e Conclusões (W1)" e "Observações e Conclusões (W2)". Este arquivo é o índice analítico por hipótese, não a documentação do teste.

---

## 1. Cobertura e qualidade dos dados

### H1.1 — A telemetria cobre todos os equipamentos com apontamentos operacionais
**Status:** ❌ Refutada (W1)

**Origem:** Comparação direta entre TAGs únicas em telemetria e em apontamentos.

**Evidência:** Apontamentos registram 47 TAGs, telemetria cobre apenas 35 — **12 equipamentos têm registro operacional mas zero telemetria** (~25% do parque). Distribuição entre 4 perfis de frota: 5 escavadeiras LeTourneau L 1850 (38% da frota sem telemetria), 3 caminhões 793-D 4S, 3 caminhões 793-D 3S e 1 caminhão 793-D 5S (este último com `CA0000` suspeito de placeholder).

**Implicação:** O modelo preditivo só pode operar nas 35 TAGs com telemetria contínua; os 12 restantes precisariam de baseline alternativo baseado em apontamentos (fora do escopo). Recomendação para Vale (Trabalhos Futuros — CM 6.3): completar cobertura de telemetria, especialmente na frota LeTourneau L 1850.

---

### H1.2 — `Id_Criticidade=4` é uma quarta categoria de severidade não documentada
**Status:** 🟡 Refutada com reinterpretação (W1)

**Origem:** Estatísticas descritivas mostraram `Id_Criticidade.max() = 4`, mas a coluna `Criticidade` tem apenas 3 valores canônicos após normalização (Critico/Nao_Critico/Informacional).

**Evidência:** Os 3.119 registros com `Id_Criticidade=4` mapeiam todos para `Criticidade=Informacional`. Análise por alarme revelou 87% concentrados em **Channel Forced (L-1850)** + outros alarmes de bypass operacional (Hoist And Bucket Limits Bypassed, Steering Limits Bypassed).

**Reinterpretação:** Não é nova categoria de severidade — é **flag latente de eventos de bypass manual do operador**. 95% dos bypasses ocorrem na frota LeTourneau L 1850 (1ª evidência do padrão emergente H4.1).

**Implicação:** Candidato a feature em W4 (`n_bypasses_operador_7d`) como preditor de comportamento de risco. Operadores que fazem bypass com frequência podem ser preditores de DG futuro — comportamento de risco ou pressão operacional excessiva.

---

### H1.3 — `Valor` com magnitude > 1000 é registro válido de medição
**Status:** ❌ Refutada (W1)

**Origem:** Estatísticas descritivas revelaram `Valor.max() = 4347`, fora da escala plausível para qualquer variável conhecida.

**Evidência:** Os 118 registros com `Valor > 1000` vêm exclusivamente de 2 alarmes de peso de carga (Truck Load Weight, Truck Load Weight L-1850). Caminhões 793-D têm capacidade ~240 toneladas; 4347 é fisicamente impossível. **Zero dos 118 registros é DG** — outlier não contamina o target. Causas prováveis: erro de unidade (kg em vez de toneladas), acumulação de cargas no mesmo timestamp, ou overflow de sensor.

**Implicação:** Tratamento de baixo risco em W3 (flag `is_outlier_valor_peso` + manter, ou cap em 300). Revela problema de qualidade de dados no sensor de peso da Vale (88% dos casos vem da frota LeTourneau L 1850 — 3ª evidência do padrão H4.1).

**Atualização pós-W3:** confirmado que esses outliers eram TODOS de eventos `Criticidade=Informacional`. O filtro de Informacional aplicado em W3 (etapa 6 do `03_limpeza.py`) os eliminou automaticamente — a flag `is_outlier_valor` no dataset filtrado é sempre `False`. A etapa 7 do script permanece como validação defensiva.

---

### H1.4 — As 340 sobreposições de ciclo em apontamentos são padrão sistêmico distribuído entre equipamentos
**Status:** ❌ Refutada com reinterpretação importante (W3 — Obs registrada em `PLANEJAMENTO.md` W3 conclusões)

**Origem:** Etapa 10 do `03_limpeza.py` (W3) detectou 340 sobreposições temporais (0,09% dos apontamentos). Volume não desprezível motivou investigação dedicada (`exploracao_w3_sobreposicoes.py`) para distinguir bug pontual vs padrão sistêmico.

**Evidência:** Decomposição por todas as dimensões mostrou **concentração máxima possível** — 100% das 340 sobreposições vêm de **um único equipamento** (CA65789, frota 793-D 2S), com 90% concentradas em janeiro de 2025. Nenhum outro dos 46 equipamentos restantes apresenta sobreposições. 35% dos ciclos sobrepostos ocorrem em estado `Hibernando` (fisicamente estranho — equipamento "dormindo" não deveria gerar dois ciclos simultâneos).

**Reinterpretação:** Não é padrão sistêmico — é **bug pontual** no registro de apontamentos do CA65789 em janeiro de 2025. Provavelmente envolve dupla baixa do equipamento ao entrar em estado Hibernando, ou problema temporário no sistema fonte específico desse equipamento. A taxa de 2,81% de sobreposições dentro dos 12.118 apontamentos desse equipamento é localmente significativa, mas o efeito no dataset agregado é desprezível.

**Implicação:** **Insight não óbvio para CM 6.1 do relatório** + **recomendação operacional concreta** para Vale (auditar pipeline de registro do CA65789 em jan/2025). Para modelagem em W4-W7, a flag `is_sobreposicao` tem cardinalidade muito baixa para ser feature útil; melhor usar para análise estratificada (excluir CA65789 da avaliação ou tratar como caso especial). Gerou nova obs pendente **2.10** em `observacoes_importantes.md` para investigar se o CA65789 apresenta outras anomalias (DGs, distribuição de alarmes, padrão operacional) — análogo ao perfil de outlier do CA65926 detectado em W2.

---

## 2. Concentração e distribuição dos DGs

### H2.1 — Top 5 alarmes concentram ~88% dos DGs (extrapolação de janeiro para o semestre)
**Status:** ✅ Confirmada (W2 — Obs 2.1)

**Origem:** Relatório inicial mostrava top 5 alarmes concentrando 88% dos DGs em janeiro; restava verificar se mantinha no semestre completo.

**Evidência:** No semestre completo, top 5 alarmes concentram **87,3%** dos 19.962 DGs — virtualmente idêntico ao janeiro. **Apenas 19 alarmes distintos geraram ≥ 1 DG** no semestre todo (de 4.402 alarmes únicos no dataset). Houve reordenação interna no top 5 (Right Front Brake Temperature subiu de 5º para 2º, devido à anomalia de junho — ver H3.3).

**Implicação:** Feature engineering em W4 pode focar nesses 19 alarmes (prioridade nos top 5) — **99,6% dos alarmes do dataset são irrelevantes para o target**. Insight para CM 6.1 (não óbvios): o universo de alarmes operacionalmente críticos é muito menor que o universo monitorado.

---

### H2.2 — Eventos `Informacional` geram algum DG no semestre
**Status:** ❌ Refutada com precisão cirúrgica (W2 — Obs 2.2)

**Origem:** Janeiro mostrava 5,3M eventos Informacionais com 0 DGs, mas a generalização ao semestre não estava garantida.

**Evidência:** No semestre completo, **36.619.169 eventos Informacionais → 0 DGs exatos** (0,0000%). A separação é determinística, não estatística — `Informacional` é definicionalmente fora do escopo do target. Por contraste, taxas de DG: `Critico` = 12,39% (1 em 8 eventos) e `Nao_Critico` = 2,10%.

**Implicação:** Filtrar `Criticidade = Informacional` em W3 é seguro — zero positivos perdidos, **98,53% do volume eliminado** (37,2M → 545k linhas). Registrado em [`controle_alteracoes.md`](controle_alteracoes.md) (2026-05-16). Habilita rolling windows em W4 sem risco de estouro de RAM (Risco 3.1 desativado por essa decisão).

---

## 3. Regimes temporais e drift

### H3.1 — O salto Não-Crítico 20% → 48% entre janeiro e o semestre é drift linear ou pico isolado
**Status:** ❌ Refutada — padrão é mais rico (W2 — Obs 2.6)

**Origem:** Comparação direta janeiro vs semestre na proporção de DGs por Criticidade revelou um salto de 20% para 48% em Não-Crítico.

**Evidência:** A análise mensal revelou **3 regimes distintos** com 2 anomalias em alarmes diferentes: (i) **baseline em jan** (19,5% NC); (ii) **anomalia A em fev-mar** (76-82% NC, com volume Engine Coolant Level +79% e inversão massiva de severidade 83% → 6% Crítico); (iii) **recuperação em abr-mai**; (iv) **anomalia B em jun** (87,7% dos DGs Crítico vieram de Right Front Brake Temperature, salto de 151,7× a média histórica do alarme). O "48% semestral" era **média mentirosa** — nunca houve um mês com 48% de fato.

**Implicação central:** O drift NÃO é linear nem isolado — é **non-stationarity real** entre regimes operacionais distintos. Confirma e quantifica o Risco 3.2. Treino jan-abr contém Anomalia A; teste jun contém Anomalia B — modelo dificilmente vai antecipar Right Front Brake (era estatisticamente invisível no treino). Gerou família nova de features para W4 (razão vs baseline próprio do alarme + razão Crítico/Não-Crítico).

---

### H3.2 — A inversão de severidade do Engine Coolant Level em fevereiro foi recalibração da regra CMA
**Status:** 🔄 Pendente (Obs 2.8 — investigar em W2 ou Trabalhos Futuros)

**Origem:** Decomposição mensal do alarme Engine Coolant Level mostrou simultaneamente em fevereiro: aumento de volume (1.505 → 2.690, +79%) **e** inversão massiva da severidade (83% Crítico em jan → 10% em fev → 6% em mar). Recuperação parcial em mai-jun para ~20% Crítico.

**Evidência preliminar:** A combinação volume + inversão simultânea aponta para **mudança de threshold ou regra CMA em fevereiro de 2025**. Volume puro explicaria aumento, mas não a inversão massiva de severidade. Sem acesso a registros internos da CMA, hipótese não confirmável dentro do escopo deste estudo.

**Implicação:** Como mitigação dentro do escopo, pode-se comparar a distribuição da coluna `Valor` (numérica) do mesmo alarme entre jan e fev-mar — se Valor é estável mas Criticidade mudou, é confirmação indireta. Independente da causa: vira recomendação operacional concreta no relatório ("documentar mudanças de regra CMA em metadado para evitar viés em séries temporais"). Pendente em [observacoes_importantes.md](observacoes_importantes.md) Obs 2.8.

---

### H3.3 — O pico de Right Front Brake Temperature Crítico em junho foi evento operacional pontual
**Status:** 🔄 Pendente (Obs 2.9 — investigar contexto em W2 ou W7)

**Origem:** Right Front Brake Temperature - Active teve entre 3 e 67 ocorrências/mês de jan a mai, e **4.247 ocorrências em junho** (salto de 151,7×). Não é gradiente — é evento estrutural pontual.

**Evidência preliminar:** Padrão sugere causa única e súbita. Hipóteses operacionais (não testáveis sem registros de manutenção da Vale): recapagem em massa de pneus afetando termoregulação dos freios, sazonalidade térmica (início de inverno em Itabira), troca/recalibração de sensor em lote.

**Implicação:** Diferenciar entre as causas exige cruzamento por TAG (foi concentrado em poucos equipamentos? sugere troca de sensor / falha localizada), por dia dentro de junho (evento único vs difuso), por Frota e Operador. Vira contexto crítico para narrativa do relatório. Sem dados de operação, parte da investigação se converte em Limitação (CM 6.2). Pendente em [observacoes_importantes.md](observacoes_importantes.md) Obs 2.9.

---

## 4. Frota LeTourneau L 1850 (padrão emergente)

### H4.1 — A frota LeTourneau L 1850 tem problemas sistêmicos de instrumentação e/ou viés da regra CMA
**Status:** ✅ Confirmada por convergência de 4 evidências independentes (W1 + W2)

**Origem:** Padrão emergente — a frota apareceu em achados sucessivos sem ser hipótese inicial.

**Evidência (4 convergências):**
1. **W1 (H1.1):** 5 das 13 escavadeiras (38% da frota) NÃO têm telemetria contínua
2. **W1 (H1.2):** 95% dos eventos de bypass manual do operador (`Id_Criticidade=4`) vêm dessa frota
3. **W1 (H1.3):** 88% dos erros de medição de peso (`Valor > 1000`) vêm dessa frota
4. **W2 (Q4):** Taxa de DG/equipamento é ~22× menor que caminhões 793-D 5S (33 DGs/escavadeira vs 719 DGs/caminhão 5S)

**Implicação:** A causa do achado 4 tem três interpretações possíveis: (i) **genuína** — escavadeiras realmente quebram menos (são ferramentas estacionárias com menos componentes em movimento contínuo); (ii) **viés da regra CMA** — thresholds calibrados para caminhões, mal adaptados a escavadeiras; (iii) **subreporte sistêmico** — confluência dos achados 1-3 sugere que a instrumentação da frota é problemática e DGs podem estar ocorrendo mas não sendo capturados. **Análise estratificada Caminhão vs Escavadeira em W7 (Qualidade C) é mandatória** — modelo não pode ser avaliado em métricas agregadas sem essa quebra.

---

## 5. Estado operacional e contexto dos DGs

### H5.1 — DGs em estado `Manutenção` são falsos positivos de bancada (alarmes artificiais de teste)
**Status:** 🟡 Refutada com reinterpretação importante (W2 — Obs 2.7)

**Origem:** Q4 via join temporal revelou que **12,65% dos DGs (2.525) ocorreram em estado `Manutenção`** — proporção surpreendentemente alta para o que se esperaria ser ~0.

**Evidência:** Análise da posição relativa de `Data_Evento` em `[Inicio, Fim]` do ciclo de apontamento + top alarmes mostrou: (i) distribuição quase-uniforme com viés monotônico leve para o início (mediana 38,6%, bucket 0-10% com 15,3% vs 10% uniforme); (ii) top 10 alarmes em Manutenção são **exatamente os top 5 alarmes de produção do semestre** (Engine Coolant 55,8%, Aftercooler 13,2%, Transmission Oil 8,6%...); (iii) **zero alarmes de diagnóstico/bypass** no top 10; (iv) 86,1% dos 2.525 vêm de alarmes do top 5 produção.

**Reinterpretação:** Os 2.525 DGs em Manutenção são **DGs legítimos** ocorrendo durante re-ativações de teste no ciclo de manutenção. Engine Coolant Level e termômetros de freio **só disparam com equipamento operando** — não são alarmes de bancada artificial. Ciclos longos de manutenção têm múltiplas ativações para teste operacional; cada ativação é oportunidade de DG real.

**Implicação:** NÃO filtrar os 2.525 em W3 — são DGs reais. Mas o contexto é diferente do DG de produção — vira ruído contextual leve. Geradas 3 tasks no PLANEJAMENTO: W4 (feature `estado_pre_evento`), W5/W6 (variante `Is_Dont_Go_producao` comparada com target original), W7 (métricas estratificadas por estado operacional). **Risco 3.3 (viés do label CMA) parcialmente refutado** — perde a "primeira evidência direta" inicialmente atribuída a esse achado.

---

### H5.2 — O padrão "calmaria → acúmulo → disparo" do caso CA65924 é universal nos DGs
**Status:** 🟡 Refutada com reinterpretação importante (W4 — Fig Extra C, `exploracao_w4_ca65924.py`)

**Origem:** Arquivo `desenvolver_dontgo.xlsx` traz 147 eventos consecutivos do caminhão CA65924 culminando em DG. Hipótese inicialmente formulada com base em observação qualitativa de "acúmulo gradual" nos minutos anteriores ao DG.

**Evidência:** Investigação empírica em W4 (`exploracao_w4_ca65924.py`, gera `figExC_ca65924_cadeia.png`) comparou o caso paradigma com 3 DGs aleatórios de outros TAGs (random.seed=42). Métrica de "acúmulo": razão `u30/p90` entre eventos nos últimos 30 min antes do DG e eventos nos 90 min anteriores. Como as janelas têm tamanhos diferentes (30 vs 90 min), a leitura direta da razão é enganosa — converter para **densidade relativa** = `(u30/30) / (p90/90) = razão × 3` (quantas vezes mais densa em eventos/min é a janela final em relação à inicial). Limiar para o padrão *sharp* hipotetizado: razão ≥ 2 (densidade ≥ 6×). Valores de razão entre 0,33 e 0,67 correspondem a densificação **gradual** (1,0× a 2,0×).

| Painel | TAG | n eventos | u30 | p90 | Razão | Densidade rel. | Interpretação |
|---|---|---:|---:|---:|---:|---:|---|
| (a) | CA65924 (paradigma) | 147 | 41 | 106 | 0,39 | **1,16×** | ~ uniforme |
| (b) | CA5927 | 28 | 9 | 19 | 0,47 | **1,42×** | gradual |
| (c) | CA65908 | 19 | 15 | 4 | **3,75** | **11,25×** | **sharp ✓** |
| (d) | CA65927 | 38 | 13 | 25 | 0,52 | **1,56×** | gradual |

**Veredito em duas camadas:**

- **Na formulação original ("padrão *sharp* universal"): refutada.** Apenas o painel (c) — CA65908 — atinge o limiar (densidade 11,25×, com 79% dos eventos concentrados nos últimos 30 min sobre uma calmaria efetiva de 4 eventos nos 90 min anteriores). O próprio CA65924, que deu nome à hipótese, tem fluxo praticamente uniforme (~1,2 eventos/min ao longo dos 2h pré-DG, densidade 1,16×) — sem calmaria identificável. A hipótese provavelmente foi extraída de observação qualitativa "147 eventos consecutivos antes do DG" sem quantificação rigorosa da distribuição temporal — caso típico de **viés de seleção do caso paradigmático** (volume alto e contínuo lido como acumulação).
- **Numa formulação fraca alternativa ("há alguma densificação pré-DG"): compatível 4/4.** As densidades relativas (1,16× a 11,25×) indicam que a janela final é sempre ao menos um pouco mais densa que a inicial, sem o salto característico do *sharp* em três dos quatro painéis.

**Reinterpretação (sub-hipótese independente da métrica de volume):** análise visual dos pontos coloridos por Criticidade nos 4 painéis sugere padrão alternativo — **acúmulo de criticidade**, não de volume. Em 3 dos 4 painéis (CA65924, CA5927, CA65908), eventos `Critico` (vermelhos) concentram-se nos últimos minutos pré-DG, mesmo quando o volume total se distribui uniformemente. CA65924 é o caso mais expressivo: dos 147 eventos da janela, 138 são `Informacional`, 7 são `Não-Crítico` e apenas **um único** é `Crítico` — e esse único `Crítico` ocorre próximo ao DG. Sub-hipótese gerada (registrada como Obs 2.11 em `observacoes_importantes.md`): a feature `count_critico_*h` (Família 1 do `05_features.py`) será mais importante que `count_total_*h` quando analisada via SHAP em W6. **A refutação do padrão *sharp* de volume não enfraquece essa sub-hipótese** — são métricas independentes (volume agregado vs distribuição por criticidade).

**Implicação para modelagem:** rolling counts volume-based continuam úteis (capturaram o caso CA65908) mas perdem força como **família dominante** de features. Features **regimais** (razão vs baseline próprio, Família 4) e **estado pré-evento** (Família 3) provavelmente terão peso maior na importância do modelo. Validação empírica a fazer em W6 via análise SHAP — também resolve formalmente a Obs 2.11.

---

### H5.3 — O operador OP_067 (do caso CA65924) tem taxa anormal de DGs
**Status:** 🔄 Pendente (Obs 2.4 — investigar em W4 ou W7)

**Origem:** O caso paradigma envolve operador específico (OP_067). Vale checar se esse operador é outlier ou se há outros sistematicamente piores — base para responder Q3 ("comportamento do operador correlaciona com alertas?").

**Evidência preliminar:** Não testada ainda.

**Implicação:** Se OP_067 é outlier (ou se outros operadores são sistematicamente piores), justifica feature `taxa_DG_operador_30d` em W4 + análise SHAP em W7 para Q3. Se a distribuição é uniforme, Q3 perde força mas é honestidade analítica reportar.

---

## 6. Viés inerente do label CMA

### H6.1 — O label `Is_Dont_Go` reflete falha física real, não apenas a regra CMA
**Status:** 🔄 Pendente (Risco 3.3 — teste único em W6)

**Origem:** O label `Is_Dont_Go` é gerado pelas regras da CMA (Central de Monitoramento de Ativos), não por inspeção física do equipamento. Em princípio, modelo poderia estar aprendendo a antecipar a regra, não a falha real.

**Evidência preliminar:** A suposta "primeira evidência direta" (12,65% em Manutenção como falsos positivos) foi **refutada pela H5.1** — esses DGs são reais. Sem essa quantificação fácil, o teste empírico do viés depende exclusivamente do **Isolation Forest em W6**: treina-se IF sobre o mesmo dataset **sem usar `Is_Dont_Go`** e mede-se se ele recupera os DGs por anomalia. Se sim (AUC-PR razoável), há sinal estrutural além da regra → Risco 3.3 majoritariamente refutado. Se não, modelo está limitado ao escopo da regra → Risco 3.3 confirmado e merece destaque em Limitações.

**Implicação:** Decisão importante para narrativa do relatório (W7-W8). Em qualquer cenário, discutir honestamente em Limitações (CM 6.2) que `Is_Dont_Go` é artefato regulatório. Se Risco 3.3 confirmado: recomendação para Vale em Trabalhos Futuros — validar prospectivamente com dados de manutenção corretiva (registros de falha física), fora do escopo deste estudo.

---

## Resumo quantitativo (status 2026-05-17 — pós W4 Fig Extra C)

| Categoria | Total | ✅ Confirmadas | ❌ Refutadas | 🟡 Refutadas com reinterpretação | 🔄 Pendentes |
|---|---:|---:|---:|---:|---:|
| 1. Cobertura e qualidade dos dados | 4 | 0 | 2 | 2 | 0 |
| 2. Concentração de DGs | 2 | 1 | 1 | 0 | 0 |
| 3. Regimes temporais e drift | 3 | 0 | 1 | 0 | 2 |
| 4. Frota LeTourneau (emergente) | 1 | 1 | 0 | 0 | 0 |
| 5. Estado operacional e contexto | 3 | 0 | 0 | **2** | **1** |
| 6. Viés do label CMA | 1 | 0 | 0 | 0 | 1 |
| **Total** | **14** | **2** | **4** | **4** | **4** |

**Observação metodológica:** 8 das 10 hipóteses testadas em W1-W4 caíram (refutadas ou refutadas com reinterpretação) — taxa de 80% de refutação. Esse é **sinal claro de qualidade da exploração**: a EDA está cumprindo o papel de testar premissas, não apenas confirmá-las. Hipóteses refutadas com reinterpretação (H1.2, H1.4, H5.1, **H5.2**) geraram achados mais ricos que a hipótese original previa:
- **H1.2 → bypass manual do operador como flag latente** (Id_Criticidade=4)
- **H1.4 → bug pontual no CA65789** (recomendação operacional concreta para Vale)
- **H5.1 → DGs em Manutenção são legítimos** (reativações de teste, não falsos positivos)
- **H5.2 (W4) → padrão "acúmulo de criticidade" no lugar de "acúmulo de volume"** (sub-hipótese registrada como Obs 2.11 para validação via SHAP em W6)

---

**Última atualização:** 2026-05-17 (W4 — Fig Extra C / refutação de H5.2)
