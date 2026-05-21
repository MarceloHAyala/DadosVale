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

### - [ ] 2.4 Operador OP_067 (do caso CA65924) tem taxa de DG anormal?

**Contexto:** O caso paradigma envolve um operador específico. Vale checar se OP_067 tem mais DGs que a média.

**Por que importa:** Responde diretamente a **Q3** (operador correlaciona com alertas?).

**Investigar:**
- Taxa de DG por operador (DGs / total de eventos do operador)
- OP_067 está no top? É outlier?
- Distribuição geral: alguns operadores são sistematicamente piores?

**Onde resolver:** W4 (criação da feature `taxa_DG_operador_30d`) ou W7 (análise de Q3 via SHAP).

---

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

### - [ ] 2.11 Validar empiricamente a sub-hipótese "acúmulo de criticidade pré-DG" (reinterpretação de H5.2)

**Contexto:** Investigação W4 da Fig Extra C (`exploracao_w4_ca65924.py`, 17/05/2026) **refutou** a hipótese H5.2 na forma original ("calmaria → acúmulo de volume → disparo" como padrão universal nos DGs). Apenas 1 dos 4 painéis comparativos (CA65924 + 3 amostras aleatórias) confirmou o padrão pela métrica de volume (razão eventos_30min/eventos_90min ≥ 2). O próprio CA65924 (caso paradigma original) apresenta fluxo aproximadamente uniforme de ~1,25 eventos/min nas 2h pré-DG.

**Reinterpretação visual emergente:** análise dos pontos coloridos por Criticidade na figura sugere padrão alternativo — **acúmulo de criticidade**, não de volume. Em 3 dos 4 painéis (CA65924, CA5927, CA65908), eventos Crítico (vermelhos na figura) concentram-se nos últimos minutos pré-DG, mesmo quando o volume total é distribuído uniformemente. O CA65924, por exemplo, tem 138 eventos Informacional + 7 Não-Crítico + 1 Crítico — e o único Crítico ocorre próximo ao DG.

**Por que importa:**
- Se o sub-padrão se confirmar, a família de features `count_critico_*h` (Família 1 do `05_features.py`) será **mais preditiva** que `count_total_*h` para antecipar DG, com implicação direta para a interpretação do modelo
- Se NÃO se confirmar, o sinal preditivo principal vem de outras famílias (regimal, estado_pre_evento, operador) e rolling deixa de ser família dominante — mudaria a narrativa do relatório (CM 6.1)
- A própria família de features regimais (`razao_severidade_14d_vs_60d`) já é uma operacionalização parcial dessa intuição em janela maior

**Investigar (a fazer em W6, após o modelo LightGBM estar treinado):**
- Análise SHAP global das 29 features de v2.parquet
- Comparar importância (mean |SHAP|) de `count_critico_1h` vs `count_total_1h`, `count_critico_4h` vs `count_total_4h`, `count_critico_24h` vs `count_total_24h`
- Hipótese a testar: `count_critico_*` aparece sistematicamente acima de `count_total_*` no ranking de importância
- Se confirmada: validação empírica da reinterpretação de H5.2; entra como insight não óbvio em CM 6.1
- Se não confirmada: registrar limitação e considerar features explícitas de "fração Crítico nos últimos N min" como adição opcional

**Onde resolver:** W6 (análise SHAP do modelo principal) ou W7 (análise final).

---

### - [ ] 2.10 O equipamento CA65789 apresenta outras anomalias além das sobreposições de apontamento?

**Contexto:** Investigação W3 (`exploracao_w3_sobreposicoes.py`, 2026-05-17) revelou que **100% das 340 sobreposições de ciclo no semestre vêm de um único equipamento — CA65789** (frota 793-D 2S), com 90% concentradas em janeiro/2025 e 35% em estado `Hibernando`. Confirmado bug pontual no registro de apontamentos desse equipamento, não padrão sistêmico.

**Por que importa:** O CA65789 acabou de ser identificado como "outlier de qualidade de dados de apontamento". É natural verificar se essa anomalia se estende para outras dimensões — pode haver um perfil completo de "equipamento problemático" análogo ao do CA65926 (W2, outlier de DGs). Se sim, vira recomendação operacional duplamente fundamentada.

**Investigar:**
- **Taxa de DG do CA65789** comparada com os outros 34 equipamentos com telemetria (lembrar: CA65789 está em apontamentos, mas verificar se tem telemetria — pode estar entre os 12 sem instrumentação)
- **Distribuição de alarmes do CA65789** (se tiver telemetria): top alarmes, padrão temporal, comparação com os caminhões 793-D 2S restantes
- **Comportamento dos operadores que rodaram CA65789** em jan/2025 (operadores específicos? mudança de turno problemática?)
- **CA65789 está entre os 12 equipamentos sem telemetria contínua** (H1.1)? Se sim, é mais uma evidência de instrumentação problemática nesse equipamento.

**Onde resolver:** W4 (ao construir features por TAG, naturalmente surge a comparação) ou W7 (análise estratificada por equipamento — Qualidade C).

---

### - [ ] 2.9 Qual evento operacional disparou o pico de Right Front Brake Temperature em junho?

**Contexto:** Investigação Obs 2.6 extensão (16/05/2026) revelou que `Right Front Brake Temperature - Active` teve em junho:
- 4.247 ocorrências (87,7% de todos os DGs Crítico de junho)
- Média jan-mai: 28 ocorrências/mês
- **Salto de 151,7×** — não é gradiente, é evento estrutural pontual

**Por que importa:**
- O alarme era **estatisticamente invisível** no período de treino (3-67 ocorrências/mês de jan a mai). O modelo dificilmente vai antecipá-lo no teste de junho — efeito direto do drift estrutural (Risco 3.2).
- Se foi recapagem em massa, sazonalidade térmica ou troca de sensor, vira contexto importante para o relatório e para a recomendação operacional.

**Investigar:**
- Distribuição dos 4.247 DGs por **TAG**: foi concentrado em poucos equipamentos (sugere troca de sensor/falha localizada) ou difuso (sugere sazonalidade/política operacional)?
- Distribuição dentro de junho: foi um dia específico (evento único) ou difuso ao longo do mês?
- Cruzar com `Tag_Frota`: foi só frota 793-D 5S/4S ou difuso?
- Cruzar com `Operador`: foi turno/operador específico?

**Sem registros de manutenção/operação da Vale**, parte dessa investigação vira Limitação. O que dá pra fazer com os dados existentes alimenta narrativa do relatório.

**Onde resolver:** W2 (EDA — alimenta a Fig Extra C — Cadeia de eventos) ou W7 (análise de erro estratificada e narrativa de drift).

---

## 3. Riscos a monitorar (não são observações, mas precisam vigilância)

### - [x] 3.1 Estouro de memória em W4 (features com rolling windows) — RISCO DESATIVADO

**Risco original:** Features de rolling 1h/4h/24h sobre 37M linhas vão multiplicar colunas. RAM pode estourar 4GB do `.venv` se não usar lazy mode.

**Conclusão (16/05/2026):** Risco desativado pela decisão de filtrar `Criticidade = Informacional` em W3 (registrada em `controle_alteracoes.md`, validada na Obs 2.2). Pós-filtro o dataset cai para ~544.885 linhas (de 37.164.054) — rolling windows passam a caber confortavelmente em RAM. Nova posição: monitorar memória só se algum experimento exigir reincluir `Informacional` (não previsto no plano).

---

### - [ ] 3.2 Drift temporal do modelo (jan-abr → jun) — RISCO CONFIRMADO E QUANTIFICADO

**Risco:** Operação de mineração tem sazonalidade (chuva, troca de equipamentos, recapagem de pneus). Modelo treinado em jan-abr pode degradar em jun.

**Quantificação completa (16/05/2026 — Obs 2.6 e extensão):** O drift **não é hipotético — está medido**. A análise mensal identificou **3 regimes distintos** com 2 anomalias em alarmes diferentes:

- **Jan:** baseline normal (19,5% Não-Crítico)
- **Fev-Mar:** Anomalia A — Engine Coolant Level Não-Crítico explode (9,3-10,6× baseline), com inversão simultânea de severidade (volume +79%, mix Crítico 83% → 6%)
- **Jun:** Anomalia B — Right Front Brake Temperature Crítico explode (4.247 ocorrências vs média 28/mês jan-mai = 151,7× baseline)

**Impacto direto no split planejado (jan-abr / mai / jun):**
- Treino contém Anomalia A
- Teste contém Anomalia B
- Right Front Brake Temperature Crítico tem 3-67 ocorrências/mês no treino → estatisticamente invisível para o modelo
- O alarme dominante do teste é praticamente desconhecido no treino

**Decisão metodológica de hoje (16/05/2026):** manter split fixo jan-abr/mai/jun e tratar o drift como tema central em W7 (análise de erro mensal) e W8 (Limitações). Decisão final entrará em `controle_alteracoes.md` quando W4 implementar o split.

**Monitorar:** Análise de drift mensal (AUC-PR por mês no teste de junho) — agora com **expectativa empírica clara** de que o desempenho cairá no alarme Right Front Brake Temperature.

**Mitigação se acontecer:** (i) Reportar métricas mês a mês obrigatoriamente em W7; (ii) Discussão honesta no relatório (W8) sobre o impacto dos 2 regimes; (iii) Recomendação de retraining mensal nos Trabalhos Futuros; (iv) Família nova de features regimais em W4 (`razao_vs_baseline_proprio_alarme`) que pode mitigar parcialmente.

**Onde resolver:** W7 (análise) + W8 (escrita).

---

### - [ ] 3.3 Viés inerente do label CMA

**Risco:** `Is_Dont_Go` é gerado pelas regras CMA, não pela falha física real. Modelo aprende a antecipar a regra, não o evento de campo.

**Atualização (16/05/2026 — pós-Obs 2.7):** A hipótese inicial de que os 2.525 DGs em estado `Manutenção` (12,65%) eram "primeira evidência direta" do viés foi **PARCIALMENTE REFUTADA pela investigação Obs 2.7**:
- Distribuição quase-uniforme com viés ligeiro inicial (não concentrada em 0-10% como H1 esperaria)
- Top 10 alarmes em Manutenção = top 5 produção do semestre (Engine Coolant, Brake Temps...) — 86,1% vêm de alarmes operacionais legítimos
- Zero alarmes de diagnóstico/bypass no top 10

**Reinterpretação:** os 2.525 DGs em Manutenção são DGs REAIS ocorrendo durante re-ativações de teste no ciclo de manutenção (Engine Coolant e termos de freio só disparam com equipamento operando). Não são falsos positivos de bancada.

**O Risco 3.3 continua existindo** (a regra CMA define o positivo, não a falha física real), mas **perde essa quantificação fácil**. A validação empírica do viés agora depende exclusivamente do diagnóstico do **Isolation Forest** em W6 — se o IF treinado sem `Is_Dont_Go` recupera os mesmos DGs, há sinal estrutural além da regra; se não, modelo está limitado ao escopo da regra.

**Reforço lateral (extração `eventos_muito_alto.csv`, 16/05/2026):** Dos 82 eventos CMA com nível "Muito Alto", **95,12% vêm de `ALARME OEM`** (alarmes nativos do fabricante — Caterpillar, etc), só 3,66% de `TENDÊNCIA` (análise sobreposta) e 1,22% de `SISTEMA`. Isso significa que a CMA é majoritariamente um **wrapper sobre o sistema de alarmes do fabricante** — o "viés inerente" do label não vem só das regras da Vale, mas também herda toda a calibração de fábrica, que foi otimizada para garantia/proteção do equipamento, não para manutenção preditiva. Reforça a importância do IF como teste de viés (se IF não recupera os DGs, modelo está aprendendo a previsão de regra OEM + regra Vale, não falha física).

**Monitorar:** Isolation Forest em W6 — agora é o ÚNICO teste empírico planejado para esse risco. Se IF performar mal sem o label, o Risco 3.3 ganha evidência. Se performar bem, o Risco 3.3 é majoritariamente refutado.

**Mitigação se acontecer:** Sanity check honesto no relatório (W7-W8), CM 6.1. Discussão honesta da natureza do label como artefato regulatório (CMA define o que é DG, não falha física).

**Onde resolver:** W6 (Isolation Forest diagnóstico — agora teste único) + W7 (análise "o que a regra não vê") + W8 (Limitações).

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

Este arquivo (`observacoes_importantes.md`) é **temporário** — contém apenas itens `[ ]` ainda em aberto.

---

**Última atualização:** 2026-05-17 (W4 — Fig Extra C / refutação H5.2 + Obs 2.3 resolvida + Obs 2.11 gerada)
