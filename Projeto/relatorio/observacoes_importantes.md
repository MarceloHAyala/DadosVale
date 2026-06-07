# Observações a Investigar — Checklist Vivo

Arquivo de **trabalho** para controlar observações que precisam ser investigadas até o fim do projeto.

**Convenção:**
- `[ ]` — pendente de investigação
- `[x]` — investigado, com a conclusão registrada logo abaixo

Observações já **incorporadas** em `controle_alteracoes.md` (decisões metodológicas tomadas) **não aparecem aqui** — este arquivo é só sobre o que ainda precisa de resposta.

---

## 1. Observações sobre os dados

*(Sem itens pendentes — ver Histórico na seção 4.)*

---

## 2. Observações sobre o domínio (negócio)


### - [ ] 2.8 Houve recalibração de threshold ou regra CMA no Engine Coolant Level em fevereiro de 2025?

**Contexto:** Investigação Obs 2.6 (16/05/2026) revelou que o alarme `Engine Coolant Level - Active` teve em fevereiro:
- Aumento de volume total: 1.505 (jan) → 2.690 (fev) → 2.918 (mar) — +94% em 2 meses
- **Inversão massiva da severidade**: 83% Crítico em janeiro → 10% em fevereiro → 6% em março (depois reverteu parcialmente para 20% em mai-jun)

A combinação volume + inversão simultânea aponta para **mudança de regra CMA / threshold em fevereiro de 2025**, não um evento operacional puro (que afetaria volume mas não a proporção entre Crítico e Não-Crítico).

**Por que importa:**
- Se confirmado, é uma **decisão da Vale (CMA)** que altera o significado da variável `Criticidade` ao longo do tempo — afeta interpretação de qualquer modelo que use essa coluna como feature ou que trate as séries temporais como estacionárias.
- Vira **recomendação concreta no relatório**: "padronizar threshold por janela móvel" ou "documentar mudanças de regra CMA em metadado".
- Se NÃO foi mudança de regra, então o equipamento físico mudou — também útil saber.

**Investigar:**
- Sem acesso a registros de mudança da CMA (fora do escopo), este item provavelmente vira **Trabalhos Futuros / Recomendação para Vale**.
- Como mitigação dentro do escopo: comparar a distribuição de `Valor` (numérica) do mesmo alarme entre jan e fev-mar. Se a distribuição de Valor é a mesma mas a Criticidade mudou, é confirmação indireta de mudança de regra.

**Onde resolver:** W7 (Limitações e Recomendações) / W8 (Trabalhos Futuros). Investigação técnica auxiliar pode ocorrer em W2-W3 se sobrar tempo.

---

### - [ ] 2.10 O equipamento CA65789 apresenta outras anomalias além das sobreposições de apontamento?

**Contexto:** Investigação W3 (`exploracao_w3_sobreposicoes.py`, 2026-05-17) revelou que **100% das 340 sobreposições de ciclo no semestre vêm de um único equipamento — CA65789** (frota 793-D 2S), com 90% concentradas em janeiro/2025 e 35% em estado `Hibernando`. Confirmado bug pontual no registro de apontamentos desse equipamento, não padrão sistêmico.

**Por que importa:** O CA65789 acabou de ser identificado como "outlier de qualidade de dados de apontamento". É natural verificar se essa anomalia se estende para outras dimensões — pode haver um perfil completo de "equipamento problemático" análogo ao do CA65926 (W2, outlier de DGs). Se sim, vira recomendação operacional duplamente fundamentada.

**Investigar:**
- **Taxa de DG do CA65789** comparada com os outros 34 equipamentos com telemetria (lembrar: CA65789 está em apontamentos, mas verificar se tem telemetria — pode estar entre os 12 sem instrumentação)
- **Distribuição de alarmes do CA65789** (se tiver telemetria): top alarmes, padrão temporal, comparação com os caminhões 793-D 2S restantes
- **Comportamento dos operadores que rodaram CA65789** em jan/2025 (operadores específicos? mudança de turno problemática?)
- **CA65789 está entre os 12 equipamentos sem telemetria contínua** (H1.1)? Se sim, é mais uma evidência de instrumentação problemática nesse equipamento.

**Atualização parcial (25/05/2026 — W6 Isolation Forest):** O CA65789 aparece no test set com 155 eventos (e portanto **tem telemetria contínua** — não está entre os 12 sem instrumentação de H1.1). Apresenta 6 DGs (prevalência 3,87%, próxima da média global de 3,66%). **AUC-ROC do `anomaly_score` vs `Is_Dont_Go` para CA65789 isolado = 0,5794** — *próximo do aleatório*, abaixo do limiar 0,75 de "sinal forte" definido na análise estrutural por TAG. **Implicação:** CA65789 não é outlier estatístico no espaço de 34 features do v3 — o problema dele em W3 (sobreposições de apontamento em jan/2025) parece ser **limitado ao registro de apontamentos**, não comportamento operacional anômalo geral. Restam por investigar: distribuição de alarmes específica + comportamento dos operadores. Recomendação: rebaixar prioridade — investigar em W7 se sobrar tempo, ou registrar como Trabalho Futuro em CM 6.3 (escopo "análise sistemática de outliers por TAG" já registrado).

**Onde resolver:** W4 (ao construir features por TAG, naturalmente surge a comparação) ou W7 (análise estratificada por equipamento — Qualidade C).

---

## 3. Riscos a monitorar (não são observações, mas precisam vigilância)

### - [x] 3.1 Estouro de memória em W4 (features com rolling windows) — RISCO DESATIVADO

**Risco original:** Features de rolling 1h/4h/24h sobre 37M linhas vão multiplicar colunas. RAM pode estourar 4GB do `.venv` se não usar lazy mode.

**Conclusão (16/05/2026):** Risco desativado pela decisão de filtrar `Criticidade = Informacional` em W3 (registrada em `controle_alteracoes.md`, validada na Obs 2.2). Pós-filtro o dataset cai para ~544.885 linhas (de 37.164.054) — rolling windows passam a caber confortavelmente em RAM. Nova posição: monitorar memória só se algum experimento exigir reincluir `Informacional` (não previsto no plano).

---

### - [ ] 3.2 Drift temporal do modelo (jan-abr → jun) — RISCO CONFIRMADO, QUANTIFICADO E COM MITIGAÇÕES REGISTRADAS

**Risco:** Operação de mineração tem sazonalidade (chuva, troca de equipamentos, recapagem de pneus). Modelo treinado em jan-abr pode degradar em jun.

**Quantificação inicial (16/05/2026 — Obs 2.6 e extensão):** O drift **não é hipotético — está medido**. A análise mensal identificou **3 regimes distintos** com 2 anomalias em alarmes diferentes:

- **Jan:** baseline normal (19,5% Não-Crítico)
- **Fev-Mar:** Anomalia A — Engine Coolant Level Não-Crítico explode (9,3-10,6× baseline), com inversão simultânea de severidade (volume +79%, mix Crítico 83% → 6%)
- **Jun:** Anomalia B — Right Front Brake Temperature Crítico explode (4.247 ocorrências vs média 28/mês jan-mai = 151,7× baseline)

**Quantificação refinada pós-split (17/05/2026 — Fig 8 do `06_split.py`):** com o *split* temporal materializado, a magnitude exata do *drift* ficou medida em termos de **taxa de DG por split**: 3,41% (treino) / **1,62% (validação, mai)** / **7,35% (teste, jun)**. Em razão direta, **o teste tem 4,5× a taxa de DG da validação e 2,2× a média do treino**. Junho também concentra 26,2% de todos os DGs do semestre apesar de representar apenas 13,0% dos eventos — DGs clusterizados em torno da anomalia RFB.

**Re-framing do drift (22/05/2026 — Obs 2.9 resolvida, ver `exploracao_w5_obs_pendentes.py`):** a investigação dedicada da anomalia RFB de junho refutou as hipóteses de drift regimal difuso e revelou que **a anomalia é a falha mecânica progressiva de UM ÚNICO equipamento (CA65926, frota 793-D 4S)**. Decomposição empírica: 98,53% dos 4.278 eventos RFB-Active de junho vêm exclusivamente do CA65926, e **82,2% de TODOS os DGs de junho (4.298 de 5.226)** vêm do mesmo equipamento. Onset abrupto (0% nos primeiros 5 dias de jun, 41% no meio, 58,9% nos últimos 5 dias — picos nos dias 26, 27 e 30). CA65926 já tinha histórico parcial (438 DGs em março via outros alarmes, taxa 20,28%) que pode ter sido sinal precursor da falha que se manifestou em junho. **Consequência para a interpretação do Risco 3.2:** o que parecia "drift estrutural genérico" é, na verdade, **um equipamento em deterioração progressiva** — pergunta para o modelo deixa de ser "antecipar regime nunca visto" e vira "antecipar falha progressiva de equipamento com histórico no treino" (6.578 eventos / 625 DGs do CA65926 em jan-mai disponíveis para aprendizado). As Mitigações 1-3 continuam válidas, mas a Família 4 regimal (`razao_alarme_7d_vs_30d_anterior`) ganha protagonismo central — foi desenhada exatamente para detectar esse tipo de explosão (RFB salta de 0-6/mês para 4.215 em jun no CA65926).

**Impacto direto no split planejado (jan-abr / mai / jun):**
- Treino contém Anomalia A
- Teste contém Anomalia B
- Right Front Brake Temperature Crítico tem 3-67 ocorrências/mês no treino → estatisticamente invisível para o modelo
- O alarme dominante do teste é praticamente desconhecido no treino
- Validação (mai, 1,62%) é o **regime mais raro de DG do semestre** — métricas single-fold de mai têm alta variância e podem mascarar problemas reais

**Decisões metodológicas — ✅ ambas registradas em `controle_alteracoes.md`:**
1. **17/05/2026 — manutenção do split fixo jan-abr/mai/jun:** registrado na entrada "2026-05-17 — Split temporal walk-forward jan-abr / mai / jun (W4 CM 4.1)". Cortes nos limites de mês (coerência com Fig 2); justificativa formal contra *k-fold* aleatório (autocorrelação das rolling features); semântica de fronteira documentada (features na borda usam dados do *split* anterior — comportamento desejado em produção, não *leakage*).
2. **17/05/2026 — 3 mitigações nominais para W5-W6:** registradas no PLANEJAMENTO.md como subseção §6 da seção "Observações e Conclusões (W4)" e como *tasks* explícitas em W5 e W6:
   - **Mitigação 1 (W6, antes do Optuna):** *TimeSeriesSplit* CV de 4 *folds* expandidos (jan→fev, jan-fev→mar, jan-mar→abr, jan-abr→mai). Usa ~5× mais sinal para *tuning*, reduz variância, atenua "mai como regime raro". Teste em jun permanece intocado.
   - **Mitigação 2 (W5, LightGBM v1):** comparar `scale_pos_weight` calibrado para taxa de treino vs taxa de produção esperada — não usar só `class_weight='balanced'` *default* que assume distribuição estacionária.
   - **Mitigação 3 (W5, GATE MARCO 1):** métricas AUC-PR / Recall / Precisão estratificadas **mai vs jun** desde o LightGBM v1 (não esperar W7). Gate vira **2 critérios** (A: bate baseline em val; B: mantém AUC-PR razoável em teste com tolerância de queda ≤ 30%).

**Monitorar (W5-W7):** Análise de *drift* mensal (AUC-PR por mês no teste de junho), agora com **expectativa empírica precisa** — desempenho deve cair em jun, especialmente em eventos cujo alarme é Right Front Brake Temperature; magnitude da queda calibra se as 3 mitigações foram suficientes ou se será preciso plano alternativo (retreino *rolling* mensal proposto para CM 6.3 — Trabalhos Futuros).

**Mitigação adicional já implementada em W4:** a Família 4 de *features* regimais (`razao_alarme_7d_vs_30d_anterior`, `razao_severidade_14d_vs_60d`) foi desenhada proativamente para capturar exatamente o tipo de anomalia que gera o *drift* — a feature `razao_alarme_7d_vs_30d_anterior` é a operacionalização direta da detecção de explosões como a do RFB. A análise SHAP em W6 vai diagnosticar se essa família efetivamente capturou o sinal regimal pretendido.

**Onde resolver:** W5 (Mitigações 2 + 3 + GATE MARCO 1) + W6 (Mitigação 1 + análise SHAP da Família 4) + W7 (análise estratificada mês × frota × estado, decisão final) + W8 (escrita de Limitações em CM 6.2 e Trabalhos Futuros em CM 6.3).

---

### - [x] 3.3 Viés inerente do label CMA — RISCO PARCIALMENTE MITIGADO (assimétrico por regime, W6)

**Risco:** `Is_Dont_Go` é gerado pelas regras CMA, não pela falha física real. Modelo aprende a antecipar a regra, não o evento de campo.

**Atualização (16/05/2026 — pós-Obs 2.7):** A hipótese inicial de que os 2.525 DGs em estado `Manutenção` (12,65%) eram "primeira evidência direta" do viés foi **PARCIALMENTE REFUTADA pela investigação Obs 2.7**:
- Distribuição quase-uniforme com viés ligeiro inicial (não concentrada em 0-10% como H1 esperaria)
- Top 10 alarmes em Manutenção = top 5 produção do semestre (Engine Coolant, Brake Temps...) — 86,1% vêm de alarmes operacionais legítimos
- Zero alarmes de diagnóstico/bypass no top 10

**Reinterpretação:** os 2.525 DGs em Manutenção são DGs REAIS ocorrendo durante re-ativações de teste no ciclo de manutenção (Engine Coolant e termos de freio só disparam com equipamento operando). Não são falsos positivos de bancada.

**Reforço lateral (extração `eventos_muito_alto.csv`, 16/05/2026):** Dos 82 eventos CMA com nível "Muito Alto", **95,12% vêm de `ALARME OEM`** (alarmes nativos do fabricante — Caterpillar, etc), só 3,66% de `TENDÊNCIA` (análise sobreposta) e 1,22% de `SISTEMA`. Isso significa que a CMA é majoritariamente um **wrapper sobre o sistema de alarmes do fabricante** — o "viés inerente" do label não vem só das regras da Vale, mas também herda toda a calibração de fábrica, que foi otimizada para garantia/proteção do equipamento, não para manutenção preditiva. Reforça a importância do IF como teste de viés.

**Resolução empírica (25/05/2026 — W6 Isolation Forest, `11_isolation_forest.py`):**

IF treinado em 394.971 eventos de train com 34 features alinhadas ao v3 canônico, 200 árvores, **sem ver `Is_Dont_Go`**. Resultado em 3 camadas:

| Camada | Resultado |
|---|---|
| AUC-ROC por split | train=0,5753 / val=0,5979 / **test=0,8603** |
| Estratificação CA65926 vs resto (test) | CA65926=0,8969 / sem CA65926=**0,5409** (~aleatório) |
| AUC mediana por TAG (26 com AUC válido) | **0,6060** (mediana mais honesta que o agregado) |
| TAGs com sinal forte E sample significativo (n_DG ≥ 10) | **3 de 26**: CA65926, CA65932, CA65924 (paradigma de W4 validado pelo IF sem usar o rótulo) |

**Veredito final: Risco 3.3 PARCIALMENTE MITIGADO (assimétrico por regime):**

- ✅ **Para anomalias dominantes (CA65926-like, falhas mecânicas progressivas):** IF e CMA concordam fortemente (AUC=0,90). O rótulo CMA captura anomalia estatisticamente real nesse regime.
- ⚠️ **Para DGs distribuídos (>88% das TAGs):** IF e CMA discordam (AUC mediana=0,61, 8 TAGs em ~aleatório). O rótulo CMA pode estar capturando eventos sem assinatura estatística distintiva no espaço de features atual.

**Convergência metodológica (atualizada em 06/06):** as três técnicas iluminam aspectos COMPLEMENTARES, não a mesma conclusão. O IF (não-supervisionado) expõe o viés do rótulo (colapsa fora do CA65926); o SHAP do v3 e os hazard ratios do Weibull mostram que o modelo supervisionado usa sinais transferíveis (tipo, frota, regime) e generaliza. Material para CM 6.1.

**Limitação L10 (CM 6.2) — RE-NUANÇADA em 06/06 via `22_v3_estratificado_ca65926.py`:** a leitura anterior ("performance do v3 largamente dirigida pelo CA65926") foi refutada pela medição direta do próprio modelo. AUC-PR do v3: completo 0,8556 (lift 5,06×) / CA65926 apenas 0,9723 (lift só 1,20×, prevalência 80,9%) / **sem CA65926 0,7693 (lift 7,77×)**, com AUC-ROC quase intacta (0,9391 → 0,9368). Conclusão correta: o número absoluto é parcialmente inflado pela alta prevalência do CA65926, mas a generalização do v3 é genuína (lift MAIOR nos demais 29 equipamentos). A limitação real é o **viés do rótulo CMA** (evidenciado pelo IF), não a fragilidade do classificador. Ver `controle_alteracoes.md` entrada 06/06.

**Trabalho Futuro registrado em CM 6.3:** investigação manual dos FPs do IF como possíveis "DGs perdidos pelo CMA" (leitura inversa do Risco 3.3) + validação prospectiva com dados de manutenção corretiva (registros de falha física).

**Resolvido em:** W6 — Isolation Forest em 25/05/2026. Detalhes em `controle_alteracoes.md` entrada "2026-05-25 — Diagnóstico do Risco 3.3 via Isolation Forest" + `hipoteses_eda.md` H6.1 atualizada para 🟡.

---

## 4. Onde encontrar observações já resolvidas

Conforme observações são investigadas e concluídas, elas são **movidas para o `PLANEJAMENTO.md`** na seção da semana em que foram resolvidas, sob o tópico **"Observações e Conclusões (W*)"** ao final de cada semana.

- **W1 (13-19/05/2026):** ver `PLANEJAMENTO.md` → seção W1 → "Observações e Conclusões (W1)"
  - Diferença de cobertura: 35 TAGs em telemetria vs 47 em apontamentos
  - `Id_Criticidade=4` = eventos de bypass manual do operador
  - `Valor` max=4347 = peso de carga com erro de unidade
  - Padrão emergente: frota LeTourneau L 1850 aparece em 3 achados independentes

- **W2 (16/05/2026 — investigado antecipadamente):** ver `PLANEJAMENTO.md` → seção W2 → "Observações e Conclusões (W2)"
  - Obs 2.2: `Informacional` = 0 DGs no semestre (36,6M eventos) → filtro habilitado em W3
  - Obs 2.1: Top 5 alarmes concentra 87,3% dos DGs (vs 88% jan); só 19 alarmes geram DG no semestre todo
  - Obs 2.5: `Nao_Critico` saltou de 20% para 48% dos DGs entre jan e semestre — rolling windows validadas como feature dominante; nova obs 2.6 gerada para investigar o salto
  - **Q4 (via join temporal):** distribuição completa Frota × Tipo × Estado operacional; achado novo: **12,65% dos DGs ocorrem em estado Manutenção** — gerou obs 2.7 e reforçou Risco 3.3 com evidência empírica; 4ª aparição independente da frota LeTourneau L 1850 (taxa de DG/equipamento ~22× menor que caminhões)
  - **Obs 2.6 (resolvida):** o salto 20%→48% Não-Crítico era média mentirosa que escondia **3 regimes distintos**: baseline (jan), anomalia Engine Coolant Não-Crítico em fev-mar (+ inversão de severidade 83%→6% Crítico), anomalia Right Front Brake Crítico em junho (151,7× baseline). Quantificou e CONFIRMOU o Risco 3.2 (drift). Gerou Obs 2.8 (mudança regra CMA fev?) e Obs 2.9 (contexto operacional jun?), além de identificar família nova de features para W4 (razão vs baseline do próprio alarme).
  - **Obs 2.7 (resolvida):** 12,65% DGs em Manutenção — analisados via posição relativa em [Inicio, Fim]. H1 (DG causou transição) contribui ~5%, H3 (bug CMA) rejeitada empiricamente. **H2 (uniforme) confirmada estatisticamente mas REINTERPRETADA**: não são falsos positivos de bancada — são DGs legítimos durante re-ativações de teste no ciclo de manutenção (Engine Coolant e termos de freio só disparam com equipamento operando). **Risco 3.3 parcialmente refutado** (perde a "primeira evidência direta"); validação do viés agora depende exclusivamente do Isolation Forest em W6. Geradas 3 tasks em W4 (`estado_pre_evento`), W5/W6 (variante `Is_Dont_Go_producao` para comparação) e W7 (métricas estratificadas por estado operacional).

- **W3 (17/05/2026 — investigado antecipadamente):** ver `PLANEJAMENTO.md` → seção W3 → "Observações e Conclusões (W3)"
  - **Sobreposições de apontamento (W3 etapa 10):** 340 sobreposições temporais detectadas (0,09%). Investigação dedicada (`exploracao_w3_sobreposicoes.py`) revelou que **100% vêm de UM ÚNICO equipamento (CA65789, frota 793-D 2S)**, com 90% concentradas em janeiro/2025 e 35% em estado `Hibernando`. Diagnóstico: bug pontual no registro do CA65789, NÃO padrão sistêmico. Vira recomendação operacional concreta para Vale (auditar pipeline de apontamentos do CA65789 em jan/2025). Nova hipótese **H1.4** registrada em `hipoteses_eda.md` (refutada com reinterpretação — refuta "padrão sistêmico" mas confirma "bug localizado"). Gerou obs pendente **2.10** para investigar se CA65789 tem outras anomalias além das sobreposições.

- **W4 (17/05/2026 — investigado antecipadamente):** ver `PLANEJAMENTO.md` → seção W4 → "Observações e Conclusões (W4)"
  - **Obs 2.3 (resolvida — refutada):** Investigação Fig Extra C (`exploracao_w4_ca65924.py`) comparou o caso paradigma CA65924 (147 eventos pré-DG, do `desenvolver_dontgo.xlsx`) com 3 DGs aleatórios de outros TAGs. Métrica de acúmulo: razão eventos_últimos_30min / eventos_primeiros_90min ≥ 2. **Apenas 1 de 4 painéis confirma o padrão de volume** (CA65908, razão=3,75). O próprio CA65924 não exibe acúmulo crescente (razão=0,39 — fluxo aproximadamente uniforme de ~1,25 eventos/min). **H5.2 refutada com reinterpretação:** padrão alternativo emergente é "acúmulo de **criticidade** pré-DG" (não de volume) — eventos `Critico` (vermelhos) concentram-se nos últimos minutos em 3 dos 4 painéis, mesmo quando volume total é uniforme. Nova obs **2.11** gerada para validação empírica via SHAP em W6. Implicação para modelo: rolling counts continuam úteis mas perdem força como família dominante; features regimais e estado_pre_evento provavelmente mais importantes.

- **W5 (22/05/2026 — pré-modelagem, quick wins enriquecedores):** ver `PLANEJAMENTO.md` → seção W5 → "Observações e Conclusões (W5)"
  - **Obs 2.4 (resolvida — Q3 do edital respondida):** Investigação via `exploracao_w5_obs_pendentes.py`. **OP_067 (operador do caso paradigma CA65924) NÃO é outlier extremo:** taxa 6,338% (1,73× baseline global de 3,664%), rank #76 de 394 operadores (top 19%); 152 operadores em faixa comparável (±50% da taxa de OP_067) — não é singular. **Resposta empírica para Q3:** comportamento do operador correlaciona com DG, mas de forma suave — distribuição assimétrica com mediana 2,99% / p95 10,87% / máx 83,77%, mas os extremos têm baixo volume (operadores raros / de teste). **OP_029 é o operador com maior massa estatística problemática** (taxa 32,5% sobre 3.125 eventos = 1.016 DGs absolutos). **Implicação para SHAP em W6:** feature `taxa_DG_operador_30d` é informativa mas não deve dominar o ranking; sinal real difuso, não concentrado. **H5.3 atualizada de 🔄 Pendente para 🟡 Refutada com reinterpretação.** Tabela `relatorio/tabelas/obs24_taxa_dg_por_operador.csv` (394 linhas) anexada.
  - **Obs 2.9 (resolvida — re-framing forte do drift):** Investigação via `exploracao_w5_obs_pendentes.py`. **A "anomalia RFB de junho" é a falha mecânica progressiva de UM ÚNICO equipamento (CA65926, frota 793-D 4S):** 98,53% dos 4.278 eventos RFB-Active de jun e 82,2% de TODOS os 5.226 DGs de jun vêm do CA65926. Top 3 TAGs concentram 99,8%. Decomposição temporal: onset abrupto (0% nos primeiros 5 dias, 41% no meio, 58,9% nos últimos 5 dias; picos dias 26-27-30). CA65926 já tinha sinal precursor em março (438 DGs, taxa 20,28%) mas via outros alarmes; RFB-Active saltou de 0-6/mês (jan-mai) para 4.215 em junho — **salto de ~700× no equipamento**, não nos 30 TAGs. **Refutadas:** H_recapagem em massa (só 1 TAG), H_sazonal térmica (não é rampa gradual), H_sensor em lote (lote afetaria múltiplos equipamentos). **Confirmada:** H_localizada (falha mecânica progressiva ou sensor defeituoso específico do CA65926). **H3.3 atualizada de 🔄 Pendente para 🟡 Refutada com reinterpretação.** Tabela `relatorio/tabelas/obs29_rfb_junho_decomposicao.csv` (34 linhas long-format) anexada. **Re-framing do Risco 3.2:** pergunta para o modelo deixa de ser "antecipar regime nunca visto" e vira "antecipar falha progressiva de equipamento específico com histórico no treino" (CA65926 tem 6.578 eventos / 625 DGs em jan-mai disponíveis). **Padrão emergente reforçado: equipamentos individuais problemáticos** — CA65926 aparece agora em DOIS contextos independentes (outlier de DGs em W2 + dominante na anomalia RFB em W5), análogo ao CA65789 (W3, 100% das sobreposições). Candidato a CM 6.1 (Insight Não Óbvio) + CM 6.3 (Recomendação Operacional: auditar sistema de freio dianteiro direito do CA65926).

- **W7 Grupo B (01/06/2026 — Análises complementares):** ver `PLANEJAMENTO.md` → seção W7
  - **B#2 — Tempo de antecipação (Qualidade B):** no limiar 0,5, **50% dos TPs são detecções diretas** (antecipação=0) e só 18% atingem 90 min. **Refinamento rigoroso de 07/06 (`23`/`25`/`26`):** a medição ingênua ("existe DG em [t+L,t+4h]", inclusiva) dá AUC-ROC 0,91 em L=90min, mas é inflada por **acerto via DG mais próximo** (o modelo dispara pelo iminente). No recorte **estrito** (próximo DG entre 90min e 4h, nada iminente antes), a AUC-ROC honesta é **0,82** com lift ~5× (Figura Extra K). Há antecipação genuína, porém modesta. **L12:** o limite real é o trade-off precisão × antecedência, gerenciável por ponto de operação (Vermelho 0,30: recall 43%/precisão 16% para 90min; Amarelo 0,145 pega mais ao custo de precisão). Mitigações CM 6.3: operação em dois níveis, target 8-12h, Frente 2 (Weibull AFT).
  - **B#3 — Top-100 FPs do IF:** 94 dos 100 FPs vêm da MESMA escavadeira (PE3797). Apenas 6% têm DG futuro em 4h, mas 99% têm eventos Críticos próximos. **6ª evidência convergente sobre LeTourneau** (junto com H4.1 + L11). Material para **CM 6.1** (Insight: IF revela regime anômalo em LeTourneau que CMA não classifica) + **CM 6.3** (auditoria manual dos 100 eventos + revisão regras CMA para escavadeiras).
  - **B#4 — Insights Não Óbvios consolidados (CM 6.1):** 11 insights documentados no rascunho.md (AUC-PR alto pode esconder estratégia errada, convergência triangular como validação, SHAP vs ablation = redundância, EDA agregada esconde indivíduos, features domain-specific vencem genéricas, unknown ≥ conhecido, IF revela regime LeTourneau, drift de calibração separado de AUC-PR, performance dirigida por poucos equipamentos, tempo de antecipação ≠ horizonte do target, refutação como sinal de qualidade).
  - **B#1 — Comparação T2/T4/T8 via CV:** em execução em background.

- **W7 (27/05/2026 — Avaliação estratificada + Grupo A):** ver `PLANEJAMENTO.md` → seção W7 → "Observações e Conclusões (W7)" (a preencher)
  - **Threshold operacional canônico definido = 0,30 (FN:FP = 5:1)** após análise de custo-benefício em 11 thresholds × 4 ratios. Maximiza F2 (0,783). TP=9.821, FP=4.764, FN=2.217 no test. Registrado em `controle_alteracoes.md`.
  - **Q6 (faixas Verde/Amarelo/Vermelho)** definidas: Verde < 0,145 (70% dos eventos, 2,78% prev), Amarelo 0,145-0,30 (9,5%, 12,37% prev), Vermelho ≥ 0,30 (20,5% do volume, **67,34% de DGs reais** — concentração 4× a base).
  - **Nova limitação L11** — modelo emite zero alertas em escavadeiras LeTourneau L 1850 (31.909 eventos = 45% do test, 92 DGs, AUC-PR=0,008). 5ª evidência empírica de H4.1. Mitigações em CM 6.3: modelo dedicado ou política via Weibull AFT.
  - **Insight contra-intuitivo registrado para CM 6.1:** modelo performa ligeiramente MELHOR em categorias unknown no treino (AUC-PR 0,89 vs 0,86 em conhecidas). Refuta expectativa W5 de degradação por extrapolação. Valida empiricamente a Opção 1 (freq=0) do encoding fix.
  - **Análise estratificada por estado pré-evento:** Operando 0,86 / Manutenção 0,79 / Parado 0,84 — modelo robusto a estado operacional. Confirma Obs 2.7 (DGs em Manutenção são legítimos) com nova evidência empírica.
  - **Fig 10 (matriz de confusão com impacto operacional)** gerada — material para CM 5.2.
  - **Em execução em paralelo:** Random Forest comparativo tunado (`16_random_forest_comparativo.py`) para reforçar Diferencial #1 do relatório.

- **W6 (24-25/05/2026 — modelagem completa + fechamento):** ver `PLANEJAMENTO.md` → seção W6 → "Observações e Conclusões (W6)"
  - **Obs 2.11 (resolvida — H5.2 sub-hipótese fracamente refutada via SHAP):** Análise SHAP de v2 (`08c_shap_v2.py`) e v3 (`08f_shap_v3.py`) mostrou que **TODAS as 15 features de rolling counts (Família 1) ficam em rank #15-#31 nos dois modelos canônicos**. Comparação `count_critico_Xh` vs `count_total_Xh` deu resultado misto (apenas 2h e 4h confirmam criticidade > volume; 1h, 8h e 24h fazem o oposto). **A versão domain-specific da Família 6 (`qtd_alarmes_nivel_muito_alto_360min`, que conta APENAS alarmes nas 82 regras CMA "Muito Alto") venceu com 41% do peso no v3** — 6× a soma de todas as 15 features da Família 1. **Ablation por grupo (`15_ablation_grupos.py`)** confirma: remover G2 (15 features rolling) tem Δ AUC-PR = +0,0032 (modelo melhora ligeiramente — Família 1 é redundante). **Lição metodológica forte para CM 6.1:** features genéricas perdem para versões *domain-specific* da mesma intuição. **H5.2 sub-hipótese atualizada para ❌ Fracamente refutada.**
  - **Obs 2.10 (parcialmente respondida via IF):** Análise estrutural por TAG do `11_isolation_forest.py` revelou que CA65789 (155 eventos no test, 6 DGs, prevalência 3,87% próxima da média) tem **AUC-ROC de 0,5794 (~aleatório, abaixo do limiar 0,75 de "sinal forte")**. **Implicação:** CA65789 NÃO é outlier estatístico no espaço de 34 features do v3 — o problema dele em W3 (sobreposições de apontamento em jan/2025) parece limitado ao registro de apontamentos, não comportamento operacional anômalo. Restam por investigar distribuição de alarmes + comportamento de operadores. Item permanece `[ ]` para análise complementar em W7 ou Trabalho Futuro CM 6.3.
  - **Risco 3.3 (resolvido — PARCIALMENTE MITIGADO assimétrico por regime):** Diagnóstico final via Isolation Forest não-supervisionado (`11_isolation_forest.py`). **Para anomalias dominantes (CA65926-like, AUC=0,90):** IF e CMA concordam fortemente → rótulo CMA captura anomalia estatisticamente real, Risco 3.3 mitigado. **Para DGs distribuídos (>88% das TAGs, AUC mediana=0,61):** IF e CMA discordam → Risco 3.3 parcialmente confirmado. **Convergência metodológica** (SHAP v3 + Weibull AFT + IF) valida que o test set é atípico — dominado pelo CA65926. **H6.1 atualizada de 🔄 Pendente para 🟡 Refutada com reinterpretação.** Nova limitação **L10** em CM 6.2.
  - **Modelo canônico promovido:** v2 → v3 (sem `horas_desde_ultimo_DG`) após SHAP revelar que v2 era cascade detector. v3 captura 5× mais primeiros DGs (Recall@0.5 de 4,3% → 21,1%) com AUC-PR test=0,8556 (−0,62pp vs v2). v2 preservado como modelo intermediário diagnóstico.
  - **3 modelos canônicos finalizados:** LightGBM v3 (alerta operacional 4h, AUC-PR=0,8556) + Weibull AFT (sobrevivência, C-index=0,7444) + Isolation Forest (diagnóstico do label, não-supervisionado).
  - **4 análises de fechamento de W6:** validação cruzada SHAP×HR (`12`), Fig 9 comparativa (`13`), calibração + Platt scaling (`14` — Platt rejeitado por drift val→test), ablation por grupo (`15` — revelou alta redundância do modelo, insight para CM 6.1).

Este arquivo (`observacoes_importantes.md`) é **temporário** — contém apenas itens `[ ]` ainda em aberto.

---

**Última atualização:** 2026-06-01 (W7 COMPLETO — Grupo A + Grupo B + Item 6 todos concluídos. L12 nova, 6ª evidência LeTourneau, 12 insights consolidados em CM 6.1, Cenário 1 confirmado para horizontes (T2≈T4≈T8) + insight #12 sobre colapso fold 4, RF tunado em 0,8541 vs v3 em 0,8556 — diferença de 0,15 pp confirma empiricamente que algoritmo não é o diferencial.)
