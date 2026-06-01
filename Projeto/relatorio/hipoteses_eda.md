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
**Status:** 🟡 Refutada com reinterpretação importante (W5 — Obs 2.9 resolvida via `exploracao_w5_obs_pendentes.py`, 22/05/2026)

**Origem:** Right Front Brake Temperature - Active teve entre 3 e 67 ocorrências/mês de jan a mai (média ~74 no dataset filtrado), e **4.278 ocorrências em junho** (salto de 58× sobre média jan-mai, ou ~150× se comparado ao baseline mais restrito de mar-mai). Não é gradiente — é evento estrutural pontual.

**Hipóteses operacionais testadas em W5:**

- **H_recapagem em massa** (afetando termoregulação dos freios) → esperaria distribuição espalhada por TAGs com onset sincronizado
- **H_sazonal térmica** (início de inverno em Itabira) → esperaria rampa gradual ao longo de junho
- **H_sensor em lote** (troca/recalibração de sensores) → esperaria poucas TAGs com onset abrupto em data única
- **H_localizada** (falha em 1-2 equipamentos, análoga ao CA65789 da H1.4) → esperaria concentração extrema (poucas TAGs, possivelmente uma)

**Evidência empírica (W5):**

| Decomposição | Resultado |
|---|---|
| TAGs afetadas | 9 de 30 no split de teste |
| **CA65926 isolado** | **98,53% dos 4.278 eventos RFB-Active de junho** |
| Top 3 TAGs | 99,8% do volume |
| Frota dominante | 793-D 4S (98,55%, herdada da TAG CA65926) |
| Onset (primeiros 5 dias de jun) | 0% do volume |
| Onset (últimos 5 dias de jun) | 58,9% do volume; picos nos dias 26 (458), 27 (518), 30 (1087) |
| CA65926 jan-mai (RFB-Active) | 0/3/6/0/0 eventos por mês → **salto de ~700× no equipamento** |
| CA65926 historicamente | 13.661 eventos, 4.923 DGs no semestre; taxa em março já era 20,28% via outros alarmes |

**Veredito:**

- **H_recapagem em massa**: ❌ **Refutada.** Uma operação de recapagem afetaria múltiplos equipamentos, não 98,5% concentrados em um único.
- **H_sazonal térmica**: ❌ **Refutada.** Sazonalidade térmica seria rampa gradual e difusa entre TAGs; aqui o onset é abrupto e localizado.
- **H_sensor em lote**: ❌ **Refutada.** Lote de sensores trocados afetaria múltiplos equipamentos da mesma frota — aqui apenas o CA65926.
- **H_localizada**: ✅ **Confirmada.** Falha mecânica progressiva do sistema de freio dianteiro direito do CA65926 (ou sensor defeituoso específico do equipamento). CA65926 já tinha sinal precursor em março (438 DGs via outros alarmes); a falha do RFB em junho é a manifestação acumulada do problema mecânico.

**Implicação central (re-framing do Risco 3.2):** o "drift estrutural de junho" não é regimal genérico — é a **deterioração progressiva de um equipamento específico com histórico no treino**. Modelo treinado em jan-mai tem 6.578 eventos do CA65926 com 625 DGs históricos disponíveis para aprendizado. A pergunta deixa de ser "antecipar anomalia nunca vista" e vira "antecipar falha de equipamento que dava sinais". A Família 4 regimal (`razao_alarme_7d_vs_30d_anterior`) foi desenhada exatamente para detectar esse tipo de explosão e ganha protagonismo central na narrativa SHAP de W6. **82,2% de todos os DGs do teste (4.298 de 5.226) vêm do CA65926** — análise estratificada "com vs sem CA65926" em W7 pode quantificar quanto da degradação esperada em jun é mecânica de UM equipamento.

**Padrão emergente reforçado:** CA65926 aparece agora em DOIS contextos independentes (outlier de DGs em W2 + dominante da anomalia RFB em W5), análogo ao CA65789 (W3 — 100% das sobreposições de apontamento). Candidato a **CM 6.1** (Insight Não Óbvio: a EDA agregada esconde equipamentos individuais problemáticos) + **CM 6.3** (Recomendação Operacional Concreta: auditar sistema de freio dianteiro direito do CA65926 e revisar política de manutenção preventiva por equipamento, não por frota).

Tabela `relatorio/tabelas/obs29_rfb_junho_decomposicao.csv` (34 linhas long-format: dia / TAG / frota) anexada.

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

**Atualização pós-W7 (27/05/2026 — análise estratificada via `10_evaluation.py`):** A análise estratificada por frota e por tipo no test set revela um achado categórico que **amplia a confirmação de H4.1 com 5ª evidência empírica:**

| Frota | n eventos (test) | DGs | AUC-PR | Precision | Recall | n alertas emitidos |
|---|---:|---:|---:|---:|---:|---:|
| **LeTourneau L 1850** | **31.909 (45%)** | **92** | **0,0077** | **0,000** | **0,000** | **0** |
| 793-D (todas) | 39.180 (55%) | 11.946 | 0,8608 | 0,673 | 0,822 | 14.585 |

O modelo LightGBM v3 emite **zero alertas** em 31.909 ocorrências de escavadeiras. AUC-PR = 0,008 (essencialmente aleatório). Isso **operacionaliza** as 4 evidências anteriores: o efeito não é só de menor base rate na frota, é de **falência operacional do modelo de classificação** para esse tipo de equipamento. Causa provável: a feature `tipo_caminhao` (24% do peso SHAP) atua como *gating* — quando = 0 (escavadeira), o modelo virtualmente desliga predições positivas. **Registrada como nova limitação L11 em CM 6.2** (`rascunho.md` Síntese de Limitações). Mitigações propostas em CM 6.3 (Trabalhos Futuros): modelo dedicado para escavadeiras, ou política via Frente 2 (Weibull AFT — naturalmente reconhece baixo *base rate*).

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

**Atualização pós-W6 (24/05/2026 — Obs 2.11 testada via SHAP do v2 e v3):** A sub-hipótese **falha em ambos os modelos canônicos**:

- **SHAP do v2** (`08c_shap_v2.py`, 24/05): TODAS as 15 features de rolling counts da Família 1 ficam em rank #15–#31 (cumulativo ~5%). Comparação `count_critico_Xh` vs `count_total_Xh` por janela: resultado **misto** em 3 de 5 janelas (apenas 2h e 4h confirmam criticidade > volume; 1h, 8h e 24h dão o oposto). **A versão domain-specific da Família 6 (`qtd_alarmes_nivel_muito_alto_360min`, que conta APENAS alarmes nas 82 regras CMA "Muito Alto") venceu com 31,1% do peso — 6× a soma de todas as 15 features da Família 1.**
- **SHAP do v3** (`08f_shap_v3.py`, 24/05): mesmo padrão se mantém após a remoção de `horas_desde_ultimo_DG`. Família 1 cumulativa ~7%, enquanto Família 6 sobe para 41% (top 1) e Família 4 regimal sobe para 13,1% (vs 9,6% no v2).
- **Ablation por grupo (15_ablation_grupos.py, 25/05):** remover G2 inteiro (15 features rolling) tem Δ = +0,0032 (modelo melhora ligeiramente). Confirmação independente de que rolling counts são **redundantes** no modelo final.

**Veredito final da sub-hipótese (Obs 2.11):** ❌ **Fracamente refutada.** A intuição "criticidade acumula antes do DG" não é falsa em absoluto — apenas é **irrelevante para o modelo**, que prefere a versão *domain-specific* (Família 6) sobre a versão genérica (Família 1). **Lição metodológica importante para CM 6.1:** features genéricas podem perder para versões *domain-specific* da mesma intuição — material direto para a discussão sobre engenharia de features. Status formal de Obs 2.11 em `observacoes_importantes.md` atualizado para `[x]` (resolvida).

**Implicação para modelagem (confirmada em W6):** rolling counts volume-based confirmados como **família não-dominante** — peso conjunto ~7% no v3 vs 41% da Família 6. Features **regimais** (Família 4, 13,1% no v3) e **categóricas codificadas** (`tipo_caminhao`, frota — Família 7, 30,3% no v3 conjunto) dominam a interpretação. Confirma a previsão da reinterpretação ("Família 4 e estado pré-evento provavelmente terão peso maior"), apenas substituindo "estado pré-evento" (Família 3, virtualmente neutra) por "categóricas codificadas" (Família 7, dominantes).

---

### H5.3 — O operador OP_067 (do caso CA65924) tem taxa anormal de DGs
**Status:** 🟡 Refutada com reinterpretação (W5 — Obs 2.4 resolvida via `exploracao_w5_obs_pendentes.py`, 22/05/2026)

**Origem:** O caso paradigma envolve operador específico (OP_067). Vale checar se esse operador é outlier ou se há outros sistematicamente piores — base para responder **Q3 do edital** ("comportamento do operador correlaciona com alertas?").

**Evidência empírica (W5):**

| Métrica | OP_067 | Distribuição (394 operadores) |
|---|---:|---|
| Eventos no dataset filtrado | 426 | mediana 165 |
| DGs absolutos | 27 | mediana 5 |
| **Taxa de DG** | **6,338%** | baseline global 3,664% |
| Rank por taxa | **#76 de 394** (top 19%) | — |
| Razão vs baseline global | 1,73× | — |
| Operadores em faixa comparável (±50%) | **152** outros | — |

Quantis da distribuição de taxa de DG por operador: q25 0,57% / q50 (mediana) 2,99% / q75 5,71% / q90 8,60% / q95 10,87% / q99 35,08% / máx 83,77%. A distribuição é **fortemente assimétrica** (cauda longa para a direita), mas os extremos têm baixo volume — OP_004 com taxa 83,77% só tem 154 eventos (provavelmente operador raro / de teste / outlier de exposição). Os operadores com massa estatística problemática estão no top de volume absoluto: **OP_029 com 1.016 DGs absolutos** (taxa 32,5% sobre 3.125 eventos) — esse sim é um caso de comportamento operacional efetivamente preocupante, com escala suficiente para o modelo aprender.

**Veredito:**

- **Hipótese original (OP_067 é outlier de DGs)**: ❌ **Refutada.** OP_067 está acima do baseline mas longe da extremidade — 152 operadores têm perfil similar. Não é singular.
- **Pergunta substituta (Q3 do edital — operador correlaciona com DG?)**: ✅ **Resposta empírica suave.** Sim, há correlação, mas é **difusa**, não concentrada em 1-2 indivíduos. A taxa varia 30× entre p25 e p95, mas os extremos têm baixo volume. A informação preditiva está no perfil completo (distribuição), não num operador específico.

**Implicação central:** a feature `taxa_DG_operador_30d` (Família 5 do `05_features.py`) é **informativa mas não dominante** — não deve aparecer no topo do ranking SHAP em W6, e qualquer interpretação do tipo "operador X é problemático" precisa ser estratificada por volume de exposição (operadores de baixo volume com taxas extremas são ruído de pequena amostra). O sinal real de comportamento operacional é difuso e provavelmente entra no modelo via interações entre `taxa_DG_operador_30d`, `n_bypasses_operador_7d` (Família 5) e `operador_freq` (Família 7).

**Implicação para a resposta do CM 5 (responder Q3 no relatório final):** Q3 tem resposta empírica honesta — "sim, com sinal difuso, e a feature `taxa_DG_operador_30d` ranqueia operadores de forma consistente mas suave; o caso paradigma OP_067 está acima da média mas não é extremo, e os operadores realmente problemáticos por volume absoluto são OP_029 (1.016 DGs) e similares". Não há narrativa de "operadores ruins versus bons" — há um continuum.

Tabela `relatorio/tabelas/obs24_taxa_dg_por_operador.csv` (394 linhas com `n_eventos`, `n_dgs`, `taxa_dg_pct` por operador) anexada como entregável de Q3.

---

## 6. Viés inerente do label CMA

### H6.1 — O label `Is_Dont_Go` reflete falha física real, não apenas a regra CMA
**Status:** 🟡 Refutada com reinterpretação importante (W6 — Risco 3.3 PARCIALMENTE MITIGADO, resolvido via `11_isolation_forest.py`, 25/05/2026)

**Origem:** O label `Is_Dont_Go` é gerado pelas regras da CMA (Central de Monitoramento de Ativos), não por inspeção física do equipamento. Em princípio, modelo poderia estar aprendendo a antecipar a regra, não a falha real.

**Evidência preliminar:** A suposta "primeira evidência direta" (12,65% em Manutenção como falsos positivos) foi **refutada pela H5.1** — esses DGs são reais. Sem essa quantificação fácil, o teste empírico do viés dependeu exclusivamente do **Isolation Forest em W6**: treina-se IF sobre o mesmo dataset **sem usar `Is_Dont_Go`** e mede-se se ele recupera os DGs por anomalia.

**Evidência empírica (W6, `11_isolation_forest.py` em 25/05/2026):**

Isolation Forest treinado em 394.971 eventos de train com 34 features alinhadas ao v3 canônico, 200 árvores, **sem ver `Is_Dont_Go`**. Sobreposição entre `anomaly_score` (não-supervisionado) e `Is_Dont_Go` (rótulo) analisada em 3 camadas:

| Camada | Resultado |
|---|---|
| **(i) AUC-ROC por split** | train=0,5753 (quase aleatório); val=0,5979 (fraco); test=**0,8603** (forte). Assimetria forte sugere efeito de regime no test. |
| **(ii) Estratificação CA65926 vs resto do test** | CA65926 apenas (n=7.083): AUC=**0,8969**. Test sem CA65926 (n=64.006): AUC=**0,5409** (quase aleatório). O sinal forte do agregado vem inteiramente do CA65926. |
| **(iii) AUC-ROC por TAG (análise estrutural)** | **AUC mediana = 0,6060** entre 26 TAGs com AUC válido. Apenas **3 TAGs com sinal forte E sample significativo**: CA65926, CA65932, **CA65924** (paradigma de W4 — validado pelo IF sem usar o rótulo, AUC=0,7915). 8 de 26 TAGs com AUC < 0,55 (~aleatório). |

**Veredito do Risco 3.3 — PARCIALMENTE MITIGADO (assimétrico por regime):**

- ✅ **Para anomalias dominantes (CA65926-like, falhas mecânicas progressivas):** Isolation Forest e CMA concordam fortemente (AUC=0,90). O rótulo CMA captura anomalia estatisticamente real nesse regime. **Risco 3.3 mitigado para esses casos.**
- ⚠️ **Para DGs distribuídos (>88% dos equipamentos):** Isolation Forest e CMA discordam (AUC mediana=0,61, com 8 TAGs em ~0,54 aleatório). O rótulo CMA pode estar capturando eventos sem assinatura estatística distintiva no espaço de features atual. **Risco 3.3 parcialmente confirmado nesse regime.**

**Convergência cruzada como validação independente:** três técnicas (LightGBM v3 via SHAP, Weibull AFT via hazard ratios, Isolation Forest não-supervisionado) chegam à mesma conclusão sobre o test set:
- SHAP v3: `tipo_caminhao` 24%, `frota_793D_5S` no top
- Weibull AFT: `tipo_caminhao` TR=0,038, `frota_793D_5S` TR=0,169
- Isolation Forest: AUC dominado pelo CA65926

Material para CM 6.1 (Insight Não Óbvio — três métodos independentes convergindo é evidência forte) + CM 6.2 (nova limitação L10: performance do v3 em test largamente dirigida pelo CA65926) + CM 6.3 (Trabalhos Futuros: investigar manualmente os FPs do IF como possíveis "DGs perdidos pelo CMA" — leitura inversa do Risco 3.3).

**Implicação para narrativa do relatório:**
- Em CM 6.2 (Limitações): registrar explicitamente que `Is_Dont_Go` é artefato regulatório com **validade heterogênea por equipamento** — forte onde há anomalia mecânica dominante, fraca no resto.
- Em CM 6.3 (Trabalhos Futuros): validação prospectiva com dados de manutenção corretiva (registros de falha física), análise manual dos FPs do IF, retreino rolling mensal já registrado.

---

## 7. Equipamentos individuais problemáticos (padrão emergente)

### H7.1 — Há equipamentos individuais com problemas sistêmicos que não são capturados pelas médias agregadas por frota
**Status:** ✅ Confirmada por convergência de 3 evidências independentes em 2 equipamentos distintos (W2 + W3 + W5)

**Origem:** Padrão emergente — equipamentos específicos surgiram em investigações independentes ao longo de W2-W5 sem terem sido hipotetizados a priori. **Análogo metodológico à H4.1** (frota LeTourneau L 1850, padrão emergente confirmado por 4 evidências), com diferença de escala importante: H4.1 atua sobre uma frota inteira (sistêmico), H7.1 atua sobre equipamentos individuais dentro de outras frotas (idiossincrático). As duas hipóteses são compatíveis e fortalecem mutuamente a tese central de que dados de frota industrial têm heterogeneidade não-trivial que precisa ser respeitada na avaliação e na recomendação operacional.

**Evidência (3 convergências em 2 equipamentos):**

1. **W2 (Q4 — `04_eda.py`):** **CA65926 (frota 793-D 4S)** aparece como outlier no topo do *ranking* de DGs absolutos por equipamento no semestre completo (consolidado em `relatorio/tabelas/dgs_por_frota_tipo_classe.csv` e visualizado em `relatorio/figuras/figExG_pareto_tags.png`). Taxa de DG global do equipamento no semestre supera substancialmente a média da própria frota; em junho a taxa mensal sobe a **60,68%** (4.298 DGs sobre 7.083 eventos do mês). Achado inicial não-marcado como hipótese — apenas registrado como caracterização de Q4.

2. **W3 (sobreposições temporais — `exploracao_w3_sobreposicoes.py`):** **CA65789 (frota 793-D 2S)** concentra **100% das 340 sobreposições temporais de ciclos de apontamento** detectadas pela etapa 10 do `03_limpeza.py`, com 90% concentradas em janeiro/2025 e 35% em estado `Hibernando`. Bug pontual de registro, não padrão sistêmico — mas inteiramente localizado em um único equipamento específico. Taxa local de sobreposições no CA65789 é de 2,81% dos seus 12.118 apontamentos (significativo localmente, irrelevante quando agregado: 0,09% do dataset todo). Formalizada como H1.4 (Refutada com reinterpretação — refuta "padrão sistêmico" mas confirma "bug localizado em UM equipamento").

3. **W5 (decomposição RFB de junho — `exploracao_w5_obs_pendentes.py`):** o pico de `Right Front Brake Temperature - Active` em junho/2025 (4.278 eventos, salto de ~58× sobre média jan-mai) é **98,53% concentrado no CA65926**. Onset abrupto nos últimos 5 dias do mês (58,9% do volume; picos dias 26 / 27 / 30). O equipamento já tinha sinal precursor em março (438 DGs com taxa 20,28% via outros alarmes, antes da manifestação no sensor de freio). **82,2% de TODOS os DGs do conjunto de teste de junho (4.298 de 5.226) vêm exclusivamente do CA65926.** Formalizada como re-framing da H3.3 (Refutada com reinterpretação — refuta "pico operacional genérico" e confirma "falha localizada do CA65926").

**Implicação central:** há pelo menos 2 equipamentos com comportamento sistematicamente anômalo que **só emergem na análise estratificada por TAG**. A EDA agregada por frota, por mês ou por criticidade esconde sistematicamente esses indivíduos:

- A média da frota 793-D 4S é puxada pelo CA65926 em junho (98% dos eventos RFB), mas o CA65926 não domina a frota em todos os meses — o efeito agregado é diluído.
- A taxa de sobreposições do semestre todo é 0,09% — desprezível. Localizada no CA65789 isoladamente é 2,81% — significativa.
- A taxa global de DG é 3,66% — mas o CA65926 tem taxa mensal de 60,68% em junho (16× a média global).

**Três interpretações possíveis (mutuamente não-exclusivas):**

1. **Falhas mecânicas/sensoriais reais em equipamentos específicos** — CA65926 mostra sinais de deterioração progressiva (sinal em março → manifestação no RFB em junho); CA65789 mostra problema localizado de registro/instrumentação em janeiro. Ambos coerentes com explicações puramente físicas.
2. **Viés de manutenção/operação** — equipamentos com histórico de manutenção pior, operadores específicos recorrentemente atribuídos, ou exposição a operações mais críticas (mineração em fronts mais agressivos, por exemplo). Não verificável só com os dados disponíveis (precisaria de registros de manutenção da Vale).
3. **Limitações da CMA** — regras de alarme calibradas para o "equipamento médio" da frota ficam mal adaptadas para casos extremos — equipamentos em deterioração extrapolam os *thresholds* projetados. Análogo metodológico ao Risco 3.3 (viés do label CMA), mas com efeito direcionado a equipamentos específicos.

**Implicação para modelagem (W5-W7):**

- **Análise estratificada por TAG é obrigatória em W7** (Qualidade C do edital — análise por equipamento). Métricas agregadas (AUC-PR global, *Recall* global) podem esconder duas histórias muito diferentes: "modelo aprendeu a antecipar deterioração de equipamentos conhecidos" vs "modelo manteve *performance* estável em todos os equipamentos". Sem estratificação, a leitura externa do desempenho mistura ambas e perde poder de interpretação.
- Em particular: **análise "com vs sem CA65926"** no conjunto de teste deve ser reportada explicitamente. Quantifica quanto da degradação esperada em junho é mecânica de um equipamento conhecido (~82% dos DGs do teste vêm dele) e quanto é difusa entre os 29 equipamentos restantes — duas histórias com implicações operacionais radicalmente diferentes.
- A análise SHAP em W6 deve incluir **stratificação por TAG** para os equipamentos identificados em H7.1 — se o ranking de *features* mudar substancialmente quando focado em CA65926 ou CA65789, há sinal de que o modelo aprende padrões individualizados (bom para previsão por equipamento, ruim para generalização).

**Implicação para o relatório (CM 6):**

- **CM 6.1 (Insights Não Óbvios):** "A EDA agregada por frota esconde equipamentos individuais problemáticos. Pelo menos 2 equipamentos (CA65789 em W3 e CA65926 em W2 + W5) têm comportamento sistematicamente anômalo que só emerge na análise estratificada por TAG. A descoberta foi não-trivial porque cada equipamento apareceu em uma investigação distinta — só ao consolidar os achados em W5 o padrão emergiu."
- **CM 6.2 (Limitações):** "Médias agregadas têm valor limitado em *datasets* com forte concentração em poucos indivíduos. Qualquer recomendação operacional baseada apenas em estatísticas agregadas por frota risca não capturar os casos onde a ação preventiva tem maior valor."
- **CM 6.3 (Recomendação Operacional Concreta):** dois itens materializáveis e direcionáveis:
  1. **Auditoria manual do CA65926** — investigar fisicamente o sistema de freio dianteiro direito, especialmente o sensor e a integridade mecânica, após os picos de 26-30 de junho. Sinal de deterioração estava presente desde março (438 DGs, taxa 20,28%) — janela de antecipação real.
  2. **Auditoria do pipeline de registro de apontamentos do CA65789** — investigar o sistema de registro especificamente para esse equipamento em janeiro/2025 (340 ciclos sobrepostos, todos localizados nele).
  3. **Revisão da política de manutenção preventiva** — incluir gatilhos baseados em métricas individuais por TAG (taxa mensal de DG, salto de alarmes específicos vs *baseline* próprio do equipamento), não apenas em médias por frota. Trabalho Futuro: explorar se os 35 equipamentos com telemetria contínua se beneficiam de modelos individuais (um modelo por TAG) ou se a estratificação dentro de um modelo único é suficiente.

**Limitação metodológica reconhecida:** com apenas 3 evidências em 2 equipamentos até W5, H7.1 era estatisticamente mais frágil que H4.1 (4 evidências em uma frota inteira). É possível que existam outros equipamentos problemáticos não detectados — a investigação foi *opportunistic*, não sistemática.

**Atualização pós-W6 (25/05/2026 — validação tripla independente via SHAP / Weibull AFT / Isolation Forest):**

O modelo de modelagem em W6 produziu **convergência metodológica forte** que ratifica e estende H7.1:

1. **SHAP do v3 canônico** (`08f_shap_v3.py`, 24/05): `tipo_caminhao` é a feature #2 com 23,9% do peso; `frota_793D_5S` rank #9. O modelo aprende explicitamente que **identidade do equipamento/frota é driver principal da predição**.
2. **Weibull AFT** (`09_sobrevivencia.py`, 25/05): TR `tipo_caminhao`=0,038 (sobrevida ~3% da escavadeira), TR `frota_793D_5S`=0,169 (frota mais antiga, maior risco). Top 4 hazard ratios são todos **estruturais por equipamento** (frotas 5S, 4S, 3S, 2S + tipo_caminhao). Validação por método independente.
3. **Isolation Forest** (`11_isolation_forest.py`, 25/05): análise estrutural **por TAG** (todas as 26 TAGs com AUC válido) confirma: **CA65926 AUC=0,897, CA65932 AUC=0,837, CA65924 AUC=0,792** — os 3 únicos com sinal forte E sample significativo. **CA65924 (paradigma de W4) detectado SEM o IF usar o rótulo** — 4ª evidência convergente para H7.1.
4. **Análise estratificada CA65926 vs resto:** test completo AUC=0,860 mas decompõe-se em CA65926=0,897 vs resto=0,541. Confirma que o sinal do test é dirigido por poucos equipamentos.
5. **Ablation por grupo** (`15_ablation_grupos.py`, 25/05): G6 categóricas (8 features, inclui `tipo_caminhao` e 4 dummies de frota) tem ablation Δ=+0,0064 (modelo melhora ligeiramente ao remover) — sinal de **alta redundância** (modelo encontra rotas alternativas), não de irrelevância. Coerente com L10.

**Veredito reforçado pós-W6: H7.1 CONFIRMADA com convergência metodológica de 4 evidências independentes em 3 equipamentos:**
- **CA65789** (W3 sobreposições) — confirmado
- **CA65926** (W2 outlier de DGs + W5 anomalia RFB + W6 SHAP/Weibull/IF) — confirmado por múltiplas técnicas
- **CA65924** (W4 caso paradigma + W6 IF independente) — confirmação independente em W6

**Implicação direta para CM 6.1, 6.2, 6.3 (nova nota):** a "EDA agregada esconde indivíduos" tem agora demonstração empírica via 3 técnicas de modelagem independentes. Material extremamente forte para CM 6.1 + nova limitação **L10** em CM 6.2 (performance do v3 em test largamente dirigida pelo CA65926 — pode degradar em deployment sem anomalia dominante similar).

**Trabalho Futuro registrado em CM 6.3:** análise sistemática de outliers por TAG ao longo de múltiplas dimensões (taxa de DG, volume, perfil de alarmes, AUC isolado do IF) para construir *ranking* defensável de equipamentos a auditar manualmente. Investigação manual dos FPs do IF como possíveis "DGs perdidos pelo CMA" (leitura inversa do Risco 3.3) também listada.

---

## Resumo quantitativo (status 2026-05-25 — pós W6 conclusão)

| Categoria | Total | ✅ Confirmadas | ❌ Refutadas | 🟡 Refutadas com reinterpretação | 🔄 Pendentes |
|---|---:|---:|---:|---:|---:|
| 1. Cobertura e qualidade dos dados | 4 | 0 | 2 | 2 | 0 |
| 2. Concentração de DGs | 2 | 1 | 1 | 0 | 0 |
| 3. Regimes temporais e drift | 3 | 0 | 1 | 1 | 1 |
| 4. Frota LeTourneau (emergente) | 1 | 1 | 0 | 0 | 0 |
| 5. Estado operacional e contexto | 3 | 0 | 0 | 3 | 0 |
| **6. Viés do label CMA** | **1** | 0 | 0 | **1** | **0** |
| **7. Equipamentos individuais (emergente)** | **1** | **1** | 0 | 0 | 0 |
| **Total** | **15** | **3** | **4** | **7** | **1** |

**Mudança em relação ao status pós-W5:** H6.1 (viés do label CMA) saiu de 🔄 Pendente para 🟡 Refutada com reinterpretação após o diagnóstico do Isolation Forest em W6. **Apenas 1 hipótese permanece pendente** — H3.2 (recalibração CMA em fev/2025), que depende de evidência externa (registros internos da Vale) fora do escopo deste estudo.

**Observação metodológica:** 14 das 15 hipóteses do projeto receberam veredito empírico até W6. Das 14 testadas, 11 caíram (refutadas ou refutadas com reinterpretação) — **taxa de 79% de refutação**. Sinal claro de qualidade da exploração: a EDA cumpriu o papel de testar premissas, não apenas confirmá-las. As **3 hipóteses confirmadas** (H2.1 top 5 alarmes / H4.1 LeTourneau / H7.1 equipamentos individuais) são todas estruturalmente fortes — duas delas (H4.1 e H7.1) emergiram como padrões não-hipotetizados a priori, validados pela convergência de múltiplas evidências independentes.

**Hipóteses refutadas com reinterpretação geraram achados sempre mais ricos:**
- **H1.2 → bypass manual do operador como flag latente** (Id_Criticidade=4)
- **H1.4 → bug pontual no CA65789** (recomendação operacional concreta para Vale)
- **H3.3 (W5) → falha mecânica progressiva localizada do CA65926** (não recapagem em massa, não sazonalidade térmica, não troca de sensor em lote — re-framing forte do Risco 3.2; ver tabela `obs29_rfb_junho_decomposicao.csv`)
- **H5.1 → DGs em Manutenção são legítimos** (reativações de teste, não falsos positivos)
- **H5.2 (W4 → W6) → "acúmulo de criticidade" fracamente refutado via SHAP** (Família 1 rolling em rank #15–#31 nos dois modelos canônicos; **Família 6 *domain-specific* venceu Família 1 genérica** — material direto para CM 6.1)
- **H5.3 (W5) → operador correlaciona com DG de forma difusa** (OP_067 não é outlier, mas Q3 tem resposta empírica; ver tabela `obs24_taxa_dg_por_operador.csv`)
- **H6.1 (W6) → Risco 3.3 PARCIALMENTE MITIGADO (assimétrico por regime)** — Isolation Forest concorda com CMA em anomalias dominantes (CA65926 AUC=0,90) mas é aleatório em DGs distribuídos (AUC mediana por TAG = 0,61). Convergência tripla SHAP × HR × IF como validação independente. Nova limitação **L10** registrada em CM 6.2 (performance do v3 em test largamente dirigida pelo CA65926).

**Padrão emergente forte ratificado em W6 (validação tripla — H7.1):** equipamentos individuais problemáticos aparecem em múltiplos contextos independentes:
- **CA65789** (W3): 100% das sobreposições de apontamento
- **CA65926** (W2 + W5 + **W6 SHAP/Weibull/IF**): 82,2% dos DGs de junho, dominante no AUC-ROC do IF (0,90 isolado vs 0,54 resto)
- **CA65924** (W4 + **W6 IF**): paradigma de W4 detectado pelo IF não-supervisionado (AUC=0,79) **sem usar o rótulo** — 4ª evidência independente

A EDA agregada esconde esses indivíduos; **três técnicas de modelagem completamente diferentes (Shapley values + maximum likelihood paramétrico AFT + isolation trees não-supervisionado)** chegam à mesma conclusão sobre a natureza atípica do test set. Material extremamente forte para **CM 6.1** (Insight Não Óbvio: convergência metodológica), **CM 6.2** (L8 + L10), **CM 6.3** (Recomendação Operacional: auditoria manual do CA65926, CA65789, CA65924 + revisão da política de manutenção preventiva por equipamento, não por frota + investigação manual dos FPs do IF como possíveis "DGs perdidos pelo CMA").

---

**Última atualização:** 2026-05-27 (W7 Grupo A — H4.1 reforçada com 5ª evidência empírica via análise estratificada por frota: modelo emite ZERO alertas em escavadeiras, novo achado categórico → L11. Threshold operacional canônico definido em 0,30. Achado contra-intuitivo registrado: modelo performa ligeiramente MELHOR em categorias unknown que conhecidas no treino — refuta expectativa W5 sobre extrapolação.)
