# Notas Metodológicas — Programa Desenvolver 2026

Documento de referência sobre **como** as investigações empíricas foram conduzidas no projeto — não o quê (resultados), mas o método. Útil para auto-revisão, para registrar lições metodológicas, e para entender o raciocínio analítico por trás de cada conclusão.

**Convenção:** cada entrada documenta uma investigação completa com passos numerados, raciocínio explicitado, e seção "o que NÃO testei" para reconhecimento honesto dos limites.

---

## 1. Investigação das Obs 2.4 e 2.9 (W5, 2026-05-22)

A metodologia foi diferente para cada uma, refletindo a natureza das perguntas. Os passos abaixo são explícitos para que o raciocínio fique reproduzível.

### Obs 2.4 — OP_067 é outlier de DGs?

**Pergunta original:** o caso paradigma do `desenvolver_dontgo.xlsx` envolve o operador OP_067. Ele tem taxa de DG anormal? Por extensão: o comportamento do operador correlaciona com DG (Q3 do edital)?

**Dado disponível:** `v2_split.parquet` (544.885 eventos × 52 colunas no momento da investigação; matriz expandida posteriormente em 23/05 para 58 colunas após a adição das janelas 2h e 8h à Família 1 — mas a investigação de Obs 2.4 foi feita sobre o schema de 52 colunas), com `Nome_Operador_Anon` e `Is_Dont_Go` para cada evento.

#### Passo 1 — Reformulação rigorosa da pergunta

"Outlier" não é binário — depende de uma referência. Defini operacionalmente: **"OP_067 é outlier de DG se sua `taxa_dg = n_DGs / n_eventos` está estatisticamente fora da distribuição da taxa de DG entre todos os 394 operadores"**.

#### Passo 2 — Agregação per-operador

```python
stats = df.group_by("Nome_Operador_Anon").agg(
    n_eventos = pl.len(),
    n_dgs = (Is_Dont_Go == 1).sum(),
).with_columns(
    taxa_dg_pct = n_dgs / n_eventos * 100
)
```

#### Passo 3 — Caracterizar a distribuição

Quantis q25 / q50 / q75 / q90 / q95 / q99 / máximo. **Esse passo foi decisivo:** descobri que a distribuição é fortemente assimétrica (mediana 2,99%, p99 35,08%, máximo 83,77%). Sem isso, eu poderia confundir "OP_067 com 6,338% está bem acima da média" com "outlier extremo" — quando na verdade há muitos operadores muito acima.

#### Passo 4 — Posicionar OP_067 contra a distribuição

- **Rank:** #76 de 394 (top 19%)
- **Razão vs baseline global:** 1,73× (não 5×, 10× ou 50×)
- **Teste de unicidade:** contei operadores em faixa de ±50% da taxa de OP_067. Resultado: **152 outros operadores** em faixa comparável. Isso mata definitivamente a tese de "outlier" — não é raro, é um perfil compartilhado.

#### Passo 5 — Verificar se a cauda de taxas extremas é genuína

Top 10 por taxa mostrou OP_004 com 83,77% mas apenas 154 eventos. **Desconfiei imediatamente** — taxas extremas em baixo volume são ruído de pequena amostra (operadores raros, de teste, ou que rodaram só equipamentos problemáticos). Para validar, fiz o **top 10 por VOLUME absoluto de DGs** (não por taxa). Aí emergiu OP_029: 1.016 DGs absolutos sobre 3.125 eventos, taxa 32,5%. Esse sim é robusto — alta exposição + alta taxa.

#### Conclusão derivada

Não testada explicitamente, mas inferida pela combinação dos resultados: **Q3 tem resposta empírica difusa**. Sinal real existe (variação 30× entre p25 e p95), mas não está concentrado em 1-2 operadores. O "caso OP_029" emerge como recomendação concreta independente, sem ter sido hipotetizado a priori.

#### O que eu NÃO testei (e poderia)

Significância estatística da diferença OP_067 vs baseline (chi-quadrado, Wilson interval, etc.). Não fiz porque o efeito é tão modesto que rigorismo estatístico não muda a interpretação prática — está acima do baseline, mas em faixa povoada por 150+ outros operadores.

---

### Obs 2.9 — Causa do pico RFB em junho

**Pergunta original:** 4.247 eventos RFB-Active em junho vs média 28/mês jan-mai. Qual evento operacional disparou isso?

**Dado disponível:** mesmo `v2_split.parquet` (na versão de 52 colunas — pré-expansão da Família 1 que ocorreria em 23/05), filtrado para `Alarme == "Right Front Brake Temperature - Active"` e `split == "test"`.

#### Passo 1 — Pré-formular hipóteses com assinatura empírica falsificável

**Esse foi o passo metodológico mais importante.** Listei 4 hipóteses operacionais possíveis e — para cada uma — defini a **assinatura empírica esperada se aquela hipótese fosse verdadeira**:

| Hipótese | Assinatura esperada |
|---|---|
| H_recapagem em massa | distribuição espalhada por muitas TAGs, onset sincronizado |
| H_sazonal térmica | rampa gradual ao longo de junho, distribuída entre TAGs |
| H_sensor em lote | poucas TAGs específicas com onset abrupto em data única |
| H_localizada | concentração extrema em 1-2 TAGs |

Sem essa lista a priori, eu teria entrado na análise "pesquisando padrões" — abordagem que enviesa para encontrar o que se procura. **Com a lista a priori, transformei a análise em teste falsificável**: bastava medir as dimensões esperadas e ver qual assinatura batia.

#### Passo 2 — Decomposição multi-dimensional

Não escolhi uma dimensão única e fui fundo nela. Fiz **4 decomposições em paralelo**:

- **Por TAG:** revela H_localizada
- **Por dia de junho:** revela H_sazonal vs H_recapagem (gradual vs súbito)
- **Por frota:** redundante com TAG (frota é derivada), mas valida coerência
- **Por operador:** poderia revelar viés operacional

#### Passo 3 — Leitura cruzada das 4 decomposições contra as 4 hipóteses

Esse foi o passo decisivo:

- **TAG** mostrou 98,53% em CA65926 → mata H_recapagem (não tem espalhamento) e H_sensor em lote (lote afetaria múltiplos)
- **Dia** mostrou 0% nos primeiros 5 dias / 58,9% nos últimos 5 → mata H_sazonal (não é rampa)
- Sobra apenas **H_localizada** — não como sobrevivente "por eliminação", mas porque sua assinatura esperada (concentração extrema) **bate perfeitamente** com 98,53% em uma TAG

#### Passo 4 — Análise complementar para validar

Aqui foi a chave de "passar de 'H_localizada é compatível' para 'CA65926 tem deterioração progressiva real'". Olhei o histórico do CA65926 mês a mês — descobri:

- 438 DGs em março (taxa 20,28%) — já era um equipamento problemático
- 0/3/6/0/0/4.215 RFB-Active jan a jun — explosão localizada no sensor específico em junho
- Falha mecânica progressiva (sinal em março → manifestação no RFB em junho) faz sentido fisicamente

#### Conclusão derivada

Não testada diretamente, mas inferida: a causa é **falha mecânica do sistema de freio dianteiro direito do CA65926** (ou sensor defeituoso específico). Eu não posso confirmar isso só com os dados de telemetria — precisaria dos registros de manutenção da Vale. Vira recomendação para CM 6.3 (auditar fisicamente).

#### Passo 5 — Implicação para o framing do problema (re-framing do Risco 3.2)

Esse passo foi **o mais consequente para o projeto inteiro**. Quando confirmei H_localizada, percebi que isso muda completamente como o relatório fala sobre drift:

- **Framing antigo:** "drift estrutural difícil de antecipar"
- **Framing novo:** "deterioração progressiva de equipamento com histórico no treino"
- Pergunta para o modelo muda radicalmente — vira problema *much more tractable* dentro do paradigma supervisionado.

#### O que eu NÃO testei (e poderia)

Cruzar com `Tag_Operador` para validar se a falha está em alguma fase específica do turno (manhã vs noite — pode indicar temperatura ambiente vs falha estrutural). Pode ser feito mais tarde em W7 se SHAP mostrar que `turno` ou `hora_dia` ranqueia alto no CA65926.

---

### Pontos metodológicos comuns às duas investigações

Esses 4 pontos resumem padrões metodológicos que valem ser internalizados para futuras investigações:

1. **Comparação contra distribuição, não contra média.** Em ambas, a distribuição revelou mais do que pontos isolados (cauda assimétrica em 2.4; concentração extrema em 2.9). A média é informação incompleta sobre uma distribuição; quantis são informação muito mais rica.

2. **Hipóteses falsificáveis a priori.** Em 2.9 foi explícito (4 hipóteses com assinaturas esperadas distintas); em 2.4 foi mais sutil (operacionalizei "outlier" antes de testar). Sem hipóteses a priori, a análise vira *fishing expedition* — você encontra o que procura, e perde a capacidade de ser surpreendido pelos dados.

3. **Análise complementar para sair de "compatível" para "provavelmente causal".** Em 2.4: top 10 por volume absoluto (separar sinal robusto de ruído de pequena amostra). Em 2.9: histórico jan-mai do CA65926 (validar que a falha é progressiva e não súbita). Uma análise inicial mostra "o quê"; a análise complementar mostra "por quê" provavelmente acontece.

4. **Reconhecimento explícito do que não testei.** Em ambos os casos terminei listando o que ficou de fora — sinal de que a investigação não é exaustiva, mas é honesta sobre seus limites. Em ambiente acadêmico ou de auditoria, essa honestidade é distintiva.

---

### Implicação para o relatório final (CM 6.1)

A metodologia das duas investigações tem valor narrativo independente das conclusões. **A história "investigação rigorosa refuta hipótese inicial e gera achado melhor"** é candidata direta a CM 6.1 (Insights Não Óbvios) — tanto em Obs 2.4 (refuta "OP_067 é singular", revela OP_029 como caso real) quanto em Obs 2.9 (refuta 3 hipóteses macro, revela problema localizado de UM equipamento).

A lição metodológica subjacente — **a EDA rigorosa gera valor mesmo (especialmente) quando refuta premissas iniciais** — é o tipo de elemento que diferencia trabalho premiável de trabalho mediano. Vale ser tornado explícito no texto do relatório final.

---

---

## 2. Verificação empírica antes de escolher tratamento de categorias unknown no encoding fix (W5, 2026-05-22)

**Contexto:** durante o planejamento do `06b_fix_encoding_leakage.py` (W5, pré-modelagem), surgiu a decisão sobre como tratar categorias (TAGs / operadores) que aparecem em val/teste mas não em treino — situação inevitável porque o *split* temporal não preserva a presença de todas as categorias em todos os *splits*.

Três opções foram colocadas na mesa:

- **Opção 1:** `tag_freq = 0` e `operador_freq = 0` para categorias unknown — simples, mas pode esconder informação.
- **Opção 2:** `tag_freq = média_global_do_treino` — robusto a *outliers*, mas mascara a novidade.
- **Opção 3:** `tag_freq = 0` + nova *feature* binária `is_tag_unknown_in_train` — mais informativa, mais código.

A intuição inicial sugeria que Opção 3 entregaria mais qualidade ("adiciona informação ao modelo"). Mas o caso foi tratado em duas etapas: análise teórica primeiro, verificação empírica depois.

### Passo 1 — Análise teórica (a priori)

A *feature* `is_tag_unknown_in_train` tem propriedade peculiar **por construção**:

- Eventos do **TREINO:** `is_tag_unknown = 0` para todos os 394.971 eventos (por definição — se está no treino, não é unknown).
- Eventos de **VAL/TEST:** `is_tag_unknown ∈ {0, 1}`.

**Consequência crítica:** a *feature* é **constante = 0** em 100% dos eventos do treino. LightGBM (e qualquer árvore de decisão) calcula *information gain* para escolher *splits* — uma *feature* constante tem IG = 0 e é ignorada para *splitting*. **O modelo nunca aprende a usar a *feature*** porque nunca vê variação nela durante o treino.

A Opção 3 só entrega valor preditivo real em duas condições:

1. Com **TimeSeriesSplit CV** (Mitigação 1 prevista para W6) — alguns *folds* têm TAGs que outros não têm, gerando variação intra-treino que torna a *feature* aprendível.
2. Com **target encoding com KFold temporal** (refinamento agendado para W5/W6) — mesma lógica.

Em *single-fold* (configuração de W5: treino jan-abr / val mai / teste jun), Opção 1 e Opção 3 produzem **predições matematicamente equivalentes**.

### Passo 2 — Verificação empírica (a posteriori)

Antes de descartar a Opção 3 só com base teórica, fiz verificação empírica da magnitude do problema. A pergunta operacional: *"quantos eventos de val/test efetivamente caem em categorias unknown?"* — se for irrisório, decisão é trivial; se for substancial, vale revisar a análise teórica.

| Categoria | VAL (78.825 eventos) | TEST (71.089 eventos) |
|---|---:|---:|
| Eventos com TAG unknown | 12 (0,02%) | 1.394 (1,96%) |
| Eventos com operador unknown | 154 (0,20%) | 418 (0,59%) |
| Eventos com **qualquer** unknown | 166 (0,21%) | **1.812 (2,55%)** |
| **DGs** com qualquer unknown | 2 de 1.280 (0,16%) | **133 de 5.226 (2,54%)** |

- **TAGs unknown identificadas:** `CA65916` (em val e em test), `CA65791` (apenas em test).
- **Operadores unknown:** 6 em val, 7 em test.

### Passo 3 — Veredito e decisão final

**VAL é negligível** (0,21% dos eventos, 2 DGs). Praticamente nenhum impacto preditivo.

**TEST é moderado** (2,55% dos eventos, 133 DGs). Não é desprezível — equivale a aproximadamente 2,5% da AUC-PR do teste sendo dirigida por categorias nunca vistas no treino. Mas tampouco é dominante: os outros 97,45% dos eventos do teste estão em território conhecido.

**A maior parcela vem da TAG `CA65791`** (1.394 eventos de TAG unknown contra 418 de operador unknown).

**A magnitude de 2,55% em TEST não muda a recomendação** porque a *feature* binária da Opção 3 continua sendo constante no treino. Mesmo com mais eventos afetados, o LightGBM em *single-fold* é matematicamente incapaz de aprender a usar a *feature*. **Decisão final: Opção 1** (`tag_freq = 0` e `operador_freq = 0` para unknowns).

### Passo 4 — O que ACONTECE com os 1.812 eventos unknown durante predição

Importante entender o comportamento esperado do modelo nesses eventos para evitar surpresas em W6/W7:

- Eventos com `TAG = CA65791` ou `TAG = CA65916` recebem `tag_freq = 0`.
- O modelo, durante o treino, viu TAGs com `tag_freq` variando entre algo como 0,3% e 18% (TAGs raras existem no treino, então o modelo viu valores baixos).
- Quando vê `tag_freq = 0` no teste, **extrapola a partir do que aprendeu sobre TAGs de baixa frequência** — comportamento natural de árvores de decisão (que dividem o espaço de *features* em regiões).
- Essa extrapolação é **exatamente igual** em Opção 1 e Opção 3 porque a *feature* binária não muda nada no treino.

### Passo 5 — Onde os 2,55% importam mesmo (informação para W6, W7, CM 6.3)

A magnitude empírica é relevante NÃO para a escolha de encoding, mas para decisões posteriores:

1. **W6 (SHAP estratificado):** análise de erro separando "eventos com categoria conhecida" vs "unknown" — diagnostica se o modelo extrapola bem para esses casos.
2. **W6 (reconsideração da Opção 3):** quando TimeSeriesSplit CV estiver implementado (Mitigação 1), reavaliar se Opção 3 entrega valor — agora a *feature* binária pode variar entre *folds* do treino. Critério empírico: se a AUC-PR dos 1.812 eventos unknown for substancialmente menor que o restante, valeria criar a *feature*; se comparável, descartar definitivamente.
3. **W7 (análise estratificada obrigatória):** reportar AUC-PR / *Recall* / Precisão **separadamente** para os 1.812 eventos / 133 DGs unknown vs os 69.277 eventos / 5.093 DGs em categorias conhecidas. Se a *performance* cair muito no subgrupo unknown, vira limitação concreta em **CM 6.2**.
4. **CM 6.3 (Recomendação Operacional):** **argumento empírico** concreto para a recomendação de retreino *rolling* mensal — "~2,5% dos eventos em produção virão de equipamentos / operadores que não existiam no treino atual". Sem retreino periódico, o modelo terá *blind spot* crescente.

### Lição metodológica desta investigação

Este caso ilustra um padrão metodológico que vale ser internalizado:

1. **Não confiar na intuição inicial.** "Opção 3 parece melhor por adicionar informação" é uma intuição razoável mas incorreta no caso.
2. **Análise teórica primeiro.** Entender por que a *feature* seria constante no treino é o passo decisivo — a verificação empírica não muda essa conclusão fundamental.
3. **Verificação empírica depois.** Mesmo quando a teoria já indica uma direção, medir a magnitude tem valor para informar decisões futuras (W6/W7/CM 6.3) e para validar que a teoria se aplica ao caso concreto.
4. **Reconhecer quando a complexidade adicional é cosmética.** A Opção 3 adicionaria 2 *features* (uma para TAG, uma para operador) ao `documentacao_features.csv` e código adicional, sem ganho preditivo — custo de manutenção sem retorno.
5. **Magnitude empírica não muda raciocínio teórico fundamental.** A intuição "mais dados afetados → mudar decisão" é incorreta quando o problema é estrutural (a *feature* é constante por construção, independente de quantos eventos a usem).
6. **Identificar onde a *feature* TERIA valor.** Mesmo descartando a Opção 3 para W5, listar os 4 contextos futuros (W6 reconsideração, W6 SHAP, W7 estratificada, CM 6.3 retreino) onde o estudo informa decisões posteriores. **A investigação não é descartada — é re-aproveitada.**

### Pontos metodológicos comuns à investigação da Seção 1

- **"Análise teórica/empírica em duas etapas"** — comum em ambas: pré-formulação (a priori) seguida de verificação (a posteriori).
- **"Hipóteses falsificáveis a priori"** — comum (Seção 1 Obs 2.9 tinha 4 hipóteses operacionais; aqui tinham 3 opções com previsões teóricas distintas).
- **"Reconhecer onde a investigação informa decisões futuras"** — em ambas terminamos com lista explícita do que fica de fora ou onde o estudo será re-aproveitado.

---

---

## 3. Mitigação 2 — test set peeking aceito conscientemente em v1, corrigido em v2 (W5, 2026-05-23)

**Contexto.** A Variante B do LightGBM v1 (Mitigação 2) usa `scale_pos_weight ≈ 4,65` calculado sobre a taxa de positivos da união val+test. Tecnicamente é uma forma **branda** de *test set peeking*: usamos **uma única estatística agregada** (taxa de positivos) do conjunto de teste para calibrar **um único hiperparâmetro**. Não é treino em dados de teste, nem seleção de modelo via test, nem otimização de AUC-PR sobre test.

**Magnitude esperada do viés.** A Variante B fica **otimisticamente inflada em aproximadamente 1-3 pontos percentuais de AUC-PR** vs um cálculo honesto sem peeking. A Variante A (usa só treino para `scale_pos_weight`) NÃO tem esse viés.

**Diagnóstico implícito via comparação A vs B:**

| Resultado observado | Interpretação |
|---|---|
| B vence A por > 5pp | ganho real provavelmente ~2-4pp (resto é viés) |
| B vence A por ~1-2pp | marginal — provavelmente só o viés |
| A vence B | viés insuficiente para inflar B além de A → Mitigação 2 descartada |

**Estratégia de correção planejada (não improvisada):**

1. **W5 v1 (agora):** documenta a limitação no docstring do `08_lightgbm.py`, em `controle_alteracoes.md` (após execução), e na seção CM 6.2 do `rascunho.md`. Reporta A vs B com a nota "B usa estimativa de val+test para `scale_pos_weight` — viés esperado 1-3pp em favor de B".
2. **W6 v2:** Optuna + TimeSeriesSplit CV (Mitigação 1) tuna `scale_pos_weight` **dentro da CV** — cada *fold* usa só dados de treino. Sem peeking. **Resultado canônico** que vai para o relatório final.
3. **W7 (análise final):** compara v1 A (sem peeking) vs v1 B (com peeking) vs v2 (CV-tunado). **Diff entre B e v2 = magnitude empírica do viés do peeking.** Vira material direto para CM 6.2 — exemplo concreto de boas práticas metodológicas.

**Por que aceitar o peeking em v1 é defensável:**

- **Mitigação 2 é hipótese operacional, não estatística pura.** Para testar "calibrar para taxa de produção vence?", precisamos de alguma estimativa da taxa de produção esperada. Sem fonte externa, val+test foi nossa opção pragmática.
- **No deployment real na Vale (retreino *rolling* mensal), test set não existe no sentido estrito.** Junho/2025 é só "o passado mais recente"; em produção contínua, o modelo seria treinado com dados até N-1 e deployado em N, sem "test set" preservado.
- **Transparência total compensa o compromisso.** A revisão técnica aceita "limitação documentada + plano de correção em W6 + análise honesta em W7" muito melhor que "fingir que não houve peeking" ou "evitar a Mitigação 2 inteira por purismo".
- **A própria existência de v1 vs v2 demonstra rigor.** Sem v1, o trabalho perderia a discussão de "o que acontece quando se toma atalho metodológico" — discussão metodológica valiosa por si.

**Registro cruzado:** docstring do `08_lightgbm.py` (explicação técnica), `controle_alteracoes.md` (decisão metodológica datada, registrada após execução), `rascunho.md → CM 6.2 (Limitações)` (declaração honesta no relatório final).

---

---

## 4. Como o Feature Engineering é calculado (`05_features.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 2 → seção "Feature Engineering".

**Script:** `Projeto/codigo/05_features.py` (11 etapas)
**Comando:** `uv run python Projeto/codigo/05_features.py`
**Tempo:** ~7 segundos

**Entradas:**
- `dados/intermediarios/telemetria_limpa.parquet` (544.885 eventos, pós-filtro Informacional)
- `dados/intermediarios/apontamentos_limpo.parquet` (377.907 ciclos)

**Saídas:**
- `dados/features/v1.parquet` (5 features básicas)
- `dados/features/v2_parcial.parquet` (25 features das Famílias 0-4)
- `dados/features/v2.parquet` (35 features + 3 targets — 57 colunas, 24,4 MB)
- `relatorio/tabelas/documentacao_features.csv` (35 entradas: nome, tipo, fórmula, motivação)
- `relatorio/tabelas/sensibilidade_janela.csv` (taxa de positivos por mês × janela)

**Como cada família é calculada:**

- **Família 0 — Básicas (5 features):** extrações simples de `Data_Evento` (`hora_dia`, `dia_semana`, `mes`) e flags binárias (`turno` por `Inicio_Turno.dt.hour() == 6`, `valor_disponivel = Valor.is_not_null()`).
- **Família 1 — Rolling windows (15 features = 3 criticidades × 5 janelas):** para cada evento, conta eventos do mesmo TAG nas últimas N horas, separado por criticidade. Implementação: `rolling_sum_by(by="Data_Evento", window_size, closed="left").over("TAG")`. O parâmetro `closed="left"` é crítico — define a janela como `[t-N, t)`, excluindo o evento atual. Sem isso, haveria *data leakage* (o modelo veria a si mesmo).
- **Família 2 — Recência (2 features):** horas desde o último DG / último Crítico do mesmo TAG. Implementação: `shift(1).forward_fill().over("TAG")` sobre coluna auxiliar com timestamps de eventos-alvo.
- **Família 3 — Estado pré-evento (1 feature):** estado operacional do equipamento 1 hora antes do evento, via `join_asof(strategy="backward")` com `apontamentos_limpo.parquet`. Para eventos sem apontamento ativo: sentinela `"SEM_APONTAMENTO"` (106 eventos, 0,02%).
- **Família 4 — Regimal (2 features):** `razao_alarme_7d_vs_30d_anterior` compara frequência do alarme nos últimos 7 dias contra os 30 anteriores (mesmo TAG); `razao_severidade_14d_vs_60d` compara mix Crítico/Não-Crítico em 14d vs 60d.
- **Família 5 — Operador (2 features):** `taxa_DG_operador_30d` (rolling 30 dias por operador); `n_bypasses_operador_7d` (contagem de bypasses do operador em 7d, derivada de `Id_Criticidade=4`).
- **Família 6 — Regra de negócio (1 feature):** `qtd_alarmes_nivel_muito_alto_360min` — quantos eventos cujo alarme está nas 82 regras CMA "Muito Alto" ocorreram no mesmo TAG nos últimos 360 min.
- **Família 7 — Encoding categórico (7 features):** `tag_freq` e `operador_freq` (frequency encoding sobre dataset global — *fix de leakage em 06b*); `frota_793D_2S/3S/4S/5S` (one-hot, LeTourneau como referência); `tipo_caminhao` (binário).
- **Targets (3 colunas, etapa 11):** padrão `_dg_ts.reverse().shift(1).forward_fill().reverse().over("TAG")` para localizar o próximo DG futuro de cada equipamento; `target_Nh = 1 se proximo_dg está em (t, t+N h]`.

**Asserções defensivas (8 grupos):** shape esperado, DGs preservados (19.962), zero NULLs em features básicas e rolling, coerência `count_total = count_critico + count_nao_critico`, **monotonicidade entre janelas** (`count_X_1h ≤ ... ≤ count_X_24h`), domínio fechado de `estado_pre_evento`, razões não-negativas. Falha qualquer asserção → script aborta com exceção explícita.

---

## 5. Como o split temporal é construído (`06_split.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 2 → seção "Split temporal walk-forward (CM 4.1)".

**Script:** `Projeto/codigo/06_split.py` (5 etapas)
**Comando:** `uv run python Projeto/codigo/06_split.py`
**Tempo:** ~3 segundos

**Entrada:** `dados/features/v2.parquet` (544.885 × 57)

**Saídas:**
- `dados/features/v2_split.parquet` (544.885 × 58 = +coluna `split`)
- `relatorio/tabelas/split_temporal.csv` (3 linhas — sumário por split)
- `relatorio/figuras/fig07_janela_predicao.png` (diagrama conceitual do target)
- `relatorio/figuras/fig08_split_temporal.png` (barras mensais + drift)

**Como o split é calculado:**

Cortes nos limites de mês (alinhados com Fig 2 mensal):
```
when(Data_Evento <  2025-05-01).then("train")
when(Data_Evento <  2025-06-01).then("val")
otherwise("test")
```

**Resultados validados via asserção:**
- `train` (jan-abr): 394.971 eventos, 13.456 DGs (3,41%)
- `val` (mai): 78.825 eventos, 1.280 DGs (1,62%)
- `test` (jun): 71.089 eventos, 5.226 DGs (7,35%)
- Total: 544.885 eventos / 19.962 DGs (asserção: somas exatas).

A escolha de cortar em limite de mês (em vez de fim de turno 18:00) preserva coerência visual direta com Fig 2 e simplifica narrativa do relatório. Implicações estão documentadas em `controle_alteracoes.md` 2026-05-17.

---

## 6. Como o fix de leakage de encoding é aplicado (`06b_fix_encoding_leakage.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 2 → "Estado da matriz de features" + nota sobre `v3.parquet` como input canônico. **Contexto analítico em Seção 2 deste documento.**

**Script:** `Projeto/codigo/06b_fix_encoding_leakage.py` (4 etapas)
**Comando:** `uv run python Projeto/codigo/06b_fix_encoding_leakage.py`
**Tempo:** ~1,5 segundos

**Entrada:** `dados/features/v2_split.parquet`

**Saída:** `dados/features/v3.parquet` (544.885 × 58 — mesma shape, `tag_freq` e `operador_freq` recomputadas)

**Como o fix é calculado:**

1. Filtra `split == 'train'` (394.971 eventos).
2. Recomputa `tag_freq = count(TAG) / N_train` para cada TAG presente no treino.
3. Recomputa `operador_freq = count(Matricula_Operador_Hash) / N_train` para cada operador presente no treino.
4. Aplica via `join` por chave a todas as 544.885 linhas (treino + val + teste).
5. **Categorias unknown no treino** (2 TAGs `CA65791`/`CA65916` + 13 operadores em val/teste mas não em treino): recebem `freq = 0` por convenção (decisão Opção C-1, ver Seção 2 acima).

**Asserções defensivas:**
- 12 eventos com `tag_freq=0` em val ✓ (CA65916)
- 1.394 eventos com `tag_freq=0` em test ✓ (CA65791 + CA65916)
- 154 eventos com `operador_freq=0` em val ✓
- 418 eventos com `operador_freq=0` em test ✓
- Zero eventos com `freq=0` no treino ✓ (por construção)

---

## 7. Como o baseline heurístico é avaliado (`07_baseline.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Baseline heurístico".

**Script:** `Projeto/codigo/07_baseline.py` (3 etapas)
**Comando:** `uv run python Projeto/codigo/07_baseline.py`
**Tempo:** ~0,4 segundos

**Entrada:** `dados/features/v3.parquet`

**Saída:** `relatorio/tabelas/baseline_metricas.csv` (8 linhas: 4 thresholds × 2 splits)

**Como o baseline funciona:**

Não há treino, não há modelo de ML — apenas aplicação de regra. Para cada evento de val e test:

```
predito = (count_critico_4h >= threshold).cast(Int8)
```

**Para AUC-PR** (métrica threshold-independente): usa-se a própria *feature* `count_critico_4h` como **score raw contínuo** — interpretação direta "mais Críticos recentes → maior probabilidade de DG nas próximas 4h".

**Para Precision/Recall/F1**: aplica-se 4 thresholds (1, 2, 3, 5) sobre o score, gerando uma curva operacional. Cada threshold representa intensidade diferente de alerta (`thr=1` é permissivo: qualquer Crítico dispara; `thr=5` é restritivo: precisa de 5 Críticos em 4h).

**Por que `target_4h` apenas?** A análise de sensibilidade entre horizontes (`target_2h`, `target_8h`) **não entra** no baseline porque exigiria *features* adjacentes mal-alinhadas (`count_critico_1h` para 2h, `count_critico_24h` para 8h), introduzindo viés metodológico. A comparação entre horizontes migrou para `08_lightgbm.py` (Variantes T2/T4/T8), onde o LightGBM tem acesso a *features* perfeitamente alinhadas após a expansão da Família 1 em W5.

---

## 8. Como o LightGBM v1 é treinado e avaliado (`08_lightgbm.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "LightGBM v1 — modelo principal de classificação supervisionada".

**Script:** `Projeto/codigo/08_lightgbm.py` (6 etapas)
**Comando:** `uv run python Projeto/codigo/08_lightgbm.py`
**Tempo:** ~17,5 segundos (5 modelos)

**Entrada:** `dados/features/v3.parquet` + `baseline_metricas.csv` (referência GATE).

**Saídas:**
- `Projeto/modelos/lightgbm_v1_{A,B,C,T2,T8}.txt` (5 modelos, formato texto nativo LightGBM, ~350 KB cada)
- `relatorio/tabelas/lightgbm_v1_metricas.csv` (10 linhas: 5 variantes × 2 splits)
- `relatorio/tabelas/lightgbm_v1_vs_baseline.csv` (6 linhas: A/B/C × val/test)
- `relatorio/tabelas/comparacao_horizontes_lightgbm.csv` (6 linhas: T2/T4=A/T8 × val/test)
- `relatorio/tabelas/gate_marco_1.csv` (verdict + critérios)

**Como o LightGBM é treinado:**

LightGBM é um algoritmo de **gradient boosting com árvores de decisão**. Treina 100 árvores sequencialmente, cada uma corrigindo erros das anteriores. Hiperparâmetros default usados:

```
objective: binary
n_estimators: 100
learning_rate: 0.1
num_leaves: 31
min_child_samples: 20
random_state: 42
```

**As 5 variantes** treinadas (cada uma é uma `LGBMClassifier.fit()` independente):

| Variante | Target | `scale_pos_weight` | Pergunta |
|---|---|---|---|
| **A** (canônica) | `target_4h` | 1,972 (taxa treino) | Padrão para GATE MARCO 1 |
| **B** (Mitigação 2) | `target_4h` | 4,653 (taxa val+test) | Calibrar para produção ajuda? |
| **C** (Obs 2.7) | `target_4h_producao` | 2,096 | Filtrar DGs em Manutenção ajuda? |
| **T2** (Profundidade 1) | `target_2h` | 2,360 | Horizonte 2h tem melhor sinal? |
| **T8** (Profundidade 1) | `target_8h` | 1,585 | Horizonte 8h tem melhor sinal? |

**Categóricas** (`turno`, `estado_pre_evento`) são convertidas para `pd.Categorical` e passadas via `categorical_feature=` para que o LightGBM aplique *split handling* otimizado.

**`target_4h_producao` é reconstruído inline** (Variante C): mesma rotina `reverse → shift(1) → forward_fill → reverse` da etapa 11 do `05_features.py`, mas filtrando `Is_Dont_Go = 1 AND estado_pre_evento ≠ 'Manutenção'`.

**Avaliação por split:** AUC-PR sobre score contínuo (`predict_proba`) + Precision/Recall/F1 em threshold = 0.5. Métricas estratificadas val (mai) vs test (jun) já no script (Mitigação 3).

**GATE MARCO 1** (verdict no final): Variante A deve atingir AUC-PR ≥ 0,2897 em val **E** ≥ 0,6303 em test (re-calibrado em 22/05 após resultado contra-intuitivo do baseline).

---

## 9. Como o LightGBM v2 com Optuna é treinado (`08b_lightgbm_v2.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "LightGBM v2 — tuning de hiperparâmetros via Optuna sobre TimeSeriesSplit CV".
>
> *(Esta seção descreve a arquitetura técnica do script. Resultados empíricos serão preenchidos após a execução terminar.)*

**Script:** `Projeto/codigo/08b_lightgbm_v2.py` (7 etapas)
**Comando:** `uv run python Projeto/codigo/08b_lightgbm_v2.py`
**Tempo estimado:** ~10 minutos (50 trials × 4 folds + treino final)

**Entrada:** `dados/features/v3.parquet` + `lightgbm_v1_metricas.csv` (referência v1 A) + `baseline_metricas.csv` (referência baseline).

**Saídas:**
- `Projeto/modelos/lightgbm_v2.txt` (modelo canônico para o relatório)
- `Projeto/modelos/optuna_study_v2.pkl` (study completo para auditoria via `joblib.load`)
- `relatorio/tabelas/lightgbm_v2_metricas.csv` (val + test + média CV)
- `relatorio/tabelas/lightgbm_v2_hiperparametros.csv` (best params + range buscado)
- `relatorio/tabelas/optuna_trials.csv` (50 trials, hiperparâmetros + score, para auditoria)

**Como v2 difere de v1:**

| Aspecto | v1 (`08_lightgbm.py`) | v2 (`08b_lightgbm_v2.py`) |
|---|---|---|
| Hiperparâmetros | Default fixo | Tunado por Optuna (50 trials, TPE sampler) |
| Validação | Single-fold (mai) | TimeSeriesSplit CV de 4 folds expandidos (Mitigação 1) |
| Variantes | 5 (A/B/C/T2/T8) | 1 canônica (target_4h, sem peeking) |
| Reprodutibilidade | `n_jobs=-1` (variação microscópica entre runs) | `deterministic=True` + `force_col_wise=True` (bit-exact) |

**TimeSeriesSplit walk-forward expandido (Mitigação 1):**

```
Fold 1: treino = jan        | val = fev
Fold 2: treino = jan-fev    | val = mar
Fold 3: treino = jan-fev-mar | val = abr
Fold 4: treino = jan-abr    | val = mai (split original)
```

Métrica de tuning: **AUC-PR média dos 4 folds**. O test set (jun) **nunca** entra na CV — só no treino final + avaliação.

**Espaço de busca (7 hiperparâmetros, Optuna TPESampler seed=42):**

| Hiperparâmetro | Faixa | Distribuição |
|---|---|---|
| `n_estimators` | [50, 500] | int uniform |
| `learning_rate` | [0.01, 0.3] | log uniform |
| `num_leaves` | [15, 127] | int uniform |
| `min_child_samples` | [10, 100] | int uniform |
| `scale_pos_weight` | **[0.5, 3.0]** | uniform (refinado pela Mitigação 2 descartada — antes era [0.5, 6.0]) |
| `lambda_l1` | [0.001, 10] | log uniform |
| `lambda_l2` | [0.001, 10] | log uniform |

**Treino final:** com `best_params` do Optuna, sobre treino completo (jan-abr), avaliado em val (mai) e test (jun). Modelo salvo em `lightgbm_v2.txt`.

**Resultados empíricos (execução em 24/05/2026):**

| Métrica | Valor |
|---|---:|
| Tempo total | 1.722 s (~28,7 min — Optuna 28,5 min + treino final 8,2 s) |
| **Best AUC-PR CV (média 4 folds)** | **0,8834** |
| AUC-PR train | 0,9658 |
| AUC-PR val (mai) | 0,7801 |
| AUC-PR test (jun) | 0,8618 |
| Best trial | #34 de 50 |

**Best hiperparâmetros encontrados:**

| Hiperparâmetro | Default (v1) | Best (v2) | Sentido |
|---|---:|---:|---|
| `n_estimators` | 100 | 199 | +99% (mais árvores) |
| `learning_rate` | 0,1 | 0,013 | −87% (muito mais lento) |
| `num_leaves` | 31 | 61 | +97% (árvores mais complexas) |
| `min_child_samples` | 20 | 60 | +200% (regularização) |
| `scale_pos_weight` | 1,972 | 0,513 | −74% (downweight de positivos!) |
| `lambda_l1` | 0 | 0,32 | regularização L1 |
| `lambda_l2` | 0 | 1,82 | regularização L2 |

**Achado importante sobre `scale_pos_weight`:** Optuna escolheu valor **menor** que 1 (0,513), enquanto v1 A usava 1,972. Isso reforça a conclusão empírica da Mitigação 2 (W5): pesar positivos para cima **não ajuda** neste *dataset*. Na verdade, o ótimo está **abaixo** do que sairia da fórmula clássica `(1-taxa) / taxa = 1,97`. Provavelmente porque a taxa "real" de positivos efetivos é menor que 33,64% após considerar a distribuição não-uniforme dos DGs nos equipamentos.

**Ganho de v2 sobre v1 A:**
- val: +2,78pp (0,7523 → 0,7801)
- test: +0,52pp (0,8566 → 0,8618)

Ganho modesto em test (+0,52pp) — esperado, pois o regime de teste já era fácil para v1 graças à anomalia CA65926 (Obs 2.9). Ganho maior em val (+2,78pp) confirma que Optuna ajuda mais no regime mais difícil (mai distribuído). **GATE MARCO 1: PASS** (folga val +49,0pp, folga test +23,1pp).

**`scale_pos_weight = 0,513` confirma empiricamente:** a hipótese da Mitigação 2 (calibrar para cima → para taxa de produção ~17%) era exatamente o oposto do ótimo. A direção correta era **calibrar para baixo**, sugerindo que o LightGBM se beneficia de tratar positivos como menos importantes (provavelmente porque os positivos compartilham assinatura mecânica forte do CA65926 em test, tornando-os "fáceis" e exigindo menos peso explícito).

---

---

## 10. Como a análise SHAP é computada e interpretada (`08c_shap_v2.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Análise SHAP do LightGBM v2".

**Script:** `Projeto/codigo/08c_shap_v2.py` (6 etapas)
**Comando:** `uv run python Projeto/codigo/08c_shap_v2.py`
**Tempo:** ~1 min (TreeSHAP é eficiente em LightGBM)

**Entradas:**
- `dados/features/v3.parquet` (filtro pelo `split == 'test'` interno, 71.089 eventos)
- `modelos/lightgbm_v2.txt` (modelo canônico salvo por `08b`)

**Saídas:**
- `modelos/shap_values_v2_test.npy` (19 MB) — matriz SHAP completa [71.089 × 35], formato NumPy auditável
- `relatorio/tabelas/shap_global_v2.csv` (35 linhas — ranking global)
- `relatorio/tabelas/shap_estratificado_v2.csv` (50 linhas — 5 subgrupos × top 10)
- `relatorio/figuras/fig09a_shap_bar.png` — bar plot importância
- `relatorio/figuras/fig09b_shap_beeswarm.png` — distribuição SHAP por feature
- `relatorio/figuras/fig10_shap_dependence_top3.png` — 3 dependence plots (vertical)

### Como TreeSHAP computa as importâncias

TreeSHAP (Lundberg et al., 2018) é o algoritmo nativo de SHAP para modelos baseados em árvore — é **exato** (não aproximação como KernelSHAP) e **eficiente** (complexidade polinomial no número de nós das árvores). Para cada predição individual, decompõe o *log-odds* da saída do LightGBM em **contribuições aditivas de cada *feature***. A soma das contribuições + valor base = saída do modelo (verificação por *additivity check*).

Implementação no script:

```python
explainer = shap.TreeExplainer(booster)
shap_arr = explainer.shap_values(X, check_additivity=False)
```

O parâmetro `check_additivity=False` desabilita o check porque pode causar warnings com features categóricas. A consistência é garantida pela formulação do TreeSHAP.

**Saída:** matriz `shap_arr` com shape `[N, F]` onde `N` é o número de eventos e `F` é o número de features. `shap_arr[i, j]` = contribuição da *feature j* para a predição do evento `i` (em escala log-odds).

### Como derivamos o ranking global

```python
mean_abs_shap = np.abs(shap_arr).mean(axis=0)  # [N, F] -> [F]
ranking = np.argsort(mean_abs_shap)[::-1]
```

**Interpretação:** `mean(|SHAP|)` mede o impacto médio da feature na predição, independente da direção (positivo ou negativo). É a métrica padrão de importância global na literatura SHAP.

### Estratificações aplicadas (5 subgrupos)

Cada subgrupo recebe seu próprio ranking top-10 para identificar mudanças de comportamento do modelo entre regimes:

1. **`test_completo`** (71.089 eventos) — baseline
2. **`CA65926`** (7.083 eventos, 9,96%) — equipamento dominante em junho via Obs 2.9
3. **`resto_test (sem CA65926)`** (64.006 eventos) — para comparação direta
4. **`categorias_conhecidas (treino)`** (69.277 eventos) — onde o modelo viu as TAGs/operadores
5. **`categorias_unknown (1.812 eventos, 2,55%)`** — TAGs (`CA65791`, `CA65916`) ou operadores que não estão no treino

A estratificação responde duas perguntas:
- O modelo usa **a mesma estratégia** para predizer DGs do CA65926 vs resto? (resposta SHAP: sim, top 3 idênticos; só pesos relativos mudam)
- O modelo extrapola **diferente** para categorias unknown? (a análise stratificada por unknown está nos dados; pequena diferença observada — material para W7)

### Como a mini-diagnose de cascata foi feita

Quando o SHAP revelou que `horas_desde_ultimo_DG` tinha 39% do peso (rank #1), surgiu suspeita de "predição de cascata" (modelo prevê DG porque o último DG foi recente — autocorrelação trivial da regra CMA `QTD > 1`).

Diagnóstico (inline, ~10 linhas de Python):

```python
shap_horas = shap_arr[:, IDX_HORAS]                # SHAP da feature problemática
horas_vals = test['horas_desde_ultimo_DG'].to_numpy()
y_true = test['target_4h'].to_numpy()

# Top 10% eventos com maior SHAP POSITIVO de horas_desde_ultimo_DG
mask_top = shap_horas >= np.percentile(shap_horas, 90)
horas_top = horas_vals[mask_top]
# -> 100% têm horas_desde_ultimo_DG <= 2h, mediana = 1 minuto
# -> 94% são DG real -> modelo está acertando, mas via cascata

# Eventos SEM DG anterior (NULL): modelo consegue prever?
mask_null = np.isnan(horas_vals)
positivos_null = y_true[mask_null].sum()  # 101 positivos sem histórico
shap_total_null_pos = shap_arr[mask_null & (y_true==1)].sum(axis=1)
recovery = (shap_total_null_pos >= 0).mean()  # 1% — modelo cego sem histórico
```

**Interpretação dos números:**
- Top 10% SHAP+ → 100% tem DG recente → modelo decide via cascata
- Sem histórico → 1% recall → modelo cego para "primeiro DG"

Esse diagnóstico é o que motivou a decisão de treinar v3 sem essa feature (`08e_lightgbm_v2_no_cascade.py`).

### Status posterior: a análise SHAP do v2 motivou a promoção do v3

A *mini-diagnose* de cascata (`horas_desde_ultimo_DG` = 39% como detector de continuação, não de primeiro DG) foi a evidência empírica que motivou a decisão de treinar a Variante v3 sem essa *feature* (`08e_lightgbm_v2_no_cascade.py` — Seção 11) e, posteriormente, promovê-la a modelo canônico do relatório (D-promoção, 24/05/2026). A análise SHAP do v3 está documentada na Seção 12 — confirma que a remoção redistribuiu o peso para *features* antecipativas legítimas (Família 6 Regra de Negócio sobe para 41%, sem cascade).

A análise do v2 continua relevante como **diagnóstico que motivou a decisão** e como **comparação empírica** (modelos com AUC-PR similar podem ter estratégias internas radicalmente diferentes — lição metodológica para CM 6.1).

### Quando re-rodar `08c_shap_v2.py`

- Quando o modelo `lightgbm_v2.txt` mudar (re-tuning, novas features, novo split)
- Quando v3 estiver pronto: rodar `08c_shap_v3.py` (clone) para comparar rankings v2 vs v3
- A matriz `shap_values_v2_test.npy` deve ser regenerada sempre que o modelo mudar

### Padrão metodológico: SHAP como teste de qualidade

O SHAP foi mais que análise de interpretabilidade — funcionou como **teste empírico das hipóteses metodológicas do projeto**:

| Hipótese de W4-W5 | Teste SHAP | Resultado |
|---|---|---|
| Família 4 regimal capturaria a anomalia RFB | razao_alarme_7d_vs_30d no top 3? | ✅ Sim, rank #3 (8,6%) |
| Modelo não seria "baseline glorificado" | count_critico_4h fora do top? | ✅ Sim, rank #29 |
| Obs 2.11 (criticidade > volume) | count_critico_*h ranqueia melhor que count_total_*h? | ⚠️ Misto (3 de 5 janelas) |
| H4.1 (LeTourneau distinta) | tipo_caminhao tem peso relevante? | ✅ Sim, rank #4 (5,0%) |
| Q3 (operador correlaciona difusamente com DG) | operador_freq baixo no ranking mas não nulo? | ✅ Sim, rank #13 (0,72%) |

Cinco hipóteses metodológicas testadas em uma única análise — eficiência rara.

---

## 11. Como o LightGBM v3 (sem `horas_desde_ultimo_DG`) é treinado (`08e_lightgbm_v2_no_cascade.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "LightGBM v3 — modelo canônico promovido".

**Script:** `Projeto/codigo/08e_lightgbm_v2_no_cascade.py` (clone de `08b_lightgbm_v2.py`)
**Comando:** `uv run python Projeto/codigo/08e_lightgbm_v2_no_cascade.py`
**Tempo:** ~25,7 min (Optuna 25,4 min + treino final 14 s)

### Entrada e saída

**Entrada:**
- `dados/features/v3.parquet` (544.885 × 58, mesmo input do v2)
- Constante `FEATURES`: lista de 34 *features* (35 do v2 menos `horas_desde_ultimo_DG`; `horas_desde_ultimo_critico` mantida)

**Saída:**
- `modelos/lightgbm_v2_no_cascade.txt` (2,3 MB, formato texto nativo LightGBM)
- `modelos/optuna_study_v2_no_cascade.pkl` (study completo, 50 trials)
- `relatorio/tabelas/lightgbm_v2_no_cascade_metricas.csv`
- `relatorio/tabelas/lightgbm_v2_no_cascade_hiperparametros.csv`
- `relatorio/tabelas/v2_vs_v2_no_cascade.csv` — **tabela decisória** (3 subgrupos × 2 modelos × 2 métricas)

### Justificativa metodológica para o nome do arquivo

O nome físico do modelo é `lightgbm_v2_no_cascade.txt`, mas no relatório ele é referenciado como **v3**. Razão: o script foi criado como variante experimental do v2 (cuja análise SHAP motivou a investigação), e o nome do artefato preservou essa origem para rastreabilidade técnica. A nomenclatura "v3" no relatório reflete o status final pós-promoção (D-promoção, 24/05/2026 — registrado em `controle_alteracoes.md`).

### Mudanças vs `08b_lightgbm_v2.py`

| Aspecto | v2 | v3 (no_cascade) |
|---|---|---|
| Número de features | 35 | 34 |
| Feature removida | — | `horas_desde_ultimo_DG` |
| Análise comparativa pós-treino | — | Sim — função dedicada que compara v2 vs v3 em 3 subgrupos (geral, primeiro_DG, cascata) |
| Path do modelo | `lightgbm_v2.txt` | `lightgbm_v2_no_cascade.txt` |
| Path do study | `optuna_study_v2.pkl` | `optuna_study_v2_no_cascade.pkl` |
| Optuna seed | 42 | 42 (mesmo, garante reprodutibilidade independente do v2) |
| Resto da configuração | — | Idêntico (TimeSeriesSplit CV 4 *folds*, determinism, espaço de busca) |

### Definição dos 3 subgrupos comparativos

A função `analise_comparativa` define três subgrupos disjuntos via *masks* sobre `horas_desde_ultimo_DG` (o valor original do `v3.parquet`, **antes** da remoção da *feature* do conjunto de entrada — ela é mantida no parquet para análise, removida apenas do treino do v3):

```python
mask_cascata    = (test["horas_desde_ultimo_DG"] <= 4.0).to_numpy()
mask_primeiro_DG = (test["horas_desde_ultimo_DG"].is_null() |
                    (test["horas_desde_ultimo_DG"] > 24.0)).to_numpy()
# Subgrupo intermediário (4h < x ≤ 24h) não é avaliado — caso de "cascata mais lenta",
# escopo fora da decisão atual.
```

**Por que essa definição:**
- **Cascata (≤ 4h):** corresponde à janela do `target_4h` — DGs que aconteceram dentro da janela onde o modelo deveria predizer.
- **Primeiro DG (NULL ou > 24h):** eventos onde o equipamento **não teve** DG recente (1 dia inteiro sem DG anterior) — o caso operacional valioso. NULL captura equipamentos que **nunca tiveram** DG no histórico observado.

### Por que `scale_pos_weight = 2,40` foi o ótimo para v3 (mas 0,513 para v2)

Optuna escolheu **scale_pos_weight quase 5× maior no v3** que no v2. Interpretação metodológica:

- No v2, `horas_desde_ultimo_DG` (cascade) fornecia sinal forte de fácil exploração. Não era preciso pesar positivos para cima — o modelo já recuperava cascatas com facilidade.
- No v3, sem essa *feature*, o modelo precisa **aprender a ser mais sensível** para manter *recall*. Pesar positivos para cima funciona porque agora a tarefa é mais "honesta" (predição antecipativa, não detecção de cascata).

**Implicação:** o `scale_pos_weight = 2,40` é alto, próximo do limite superior do espaço refinado [0,5; 3,0]. Mas o test AUC-PR = 0,8556 confirma que não é *overfitting* — é calibração legítima.

### Lição metodológica para CM 6.1

**Mesma configuração (Optuna + CV + determinism), mesmo dataset, mesmo seed — só uma *feature* removida — produz dois modelos com estratégias internas radicalmente diferentes.** A análise comparativa estratificada (3 subgrupos × 2 modelos) é o que torna a diferença visível: AUC-PR agregado quase idêntico (0,8618 vs 0,8556) esconde diferença operacional gritante (+16,72pp Recall em primeiro DG).

**Padrão metodológico exportável:** ao remover uma *feature* problemática, treinar variante e comparar **em subgrupos definidos pela própria *feature* removida** é a única forma de medir o efeito real da decisão.

---

## 12. Como a análise SHAP do v3 é computada (`08f_shap_v3.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Análise SHAP do LightGBM v3".

**Script:** `Projeto/codigo/08f_shap_v3.py` (clone funcional do `08c_shap_v2.py`)
**Comando:** `PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/08f_shap_v3.py`
**Tempo:** ~1,7 min (TreeSHAP 89s + restante)

### Diferenças vs `08c_shap_v2.py`

| Aspecto | 08c (v2) | 08f (v3) |
|---|---|---|
| Modelo carregado | `lightgbm_v2.txt` | `lightgbm_v2_no_cascade.txt` |
| Número de features | 35 | 34 |
| Sumário analítico — perguntas | 4 (baseline glorificado, Família 4, Obs 2.11, Famílias dominantes) | 4 (top 1 dominante, concentração vs v2, Família 4 subiu, herança por `horas_desde_ultimo_critico`) |
| Saídas (figuras) | `fig09a/9b`, `fig10` | `fig09c/9d`, `fig10b` |
| Saídas (tabelas) | `shap_global_v2.csv`, `shap_estratificado_v2.csv` | `shap_global_v3.csv`, `shap_estratificado_v3.csv` |
| Saídas (matriz) | `shap_values_v2_test.npy` (19 MB) | `shap_values_v3_test.npy` (18,4 MB) |
| Print do ranking | `print(df_ranking.head(15))` (polars Unicode box) | Loop explícito com formatação ASCII (evita erro cp1252 no Windows) |

### Por que o encoding cp1252 era um problema

A primeira execução do `08f_shap_v3.py` falhou na Etapa 4 (`UnicodeEncodeError: 'charmap' codec can't encode characters`). Causa: o Polars formata `DataFrame.head().print()` com caracteres Unicode de *box drawing* (`┌`, `─`, `│`, `┐`, etc.) que não estão no *codepage* cp1252 padrão do Windows. A matriz e o CSV já tinham sido salvos antes do crash — apenas o `print()` falhou.

**Correção aplicada:** substituí `print(df_ranking.head(15))` por um loop `for row in df_ranking.head(15).iter_rows(named=True)` com formatação ASCII pura (`|` em vez de `│`). **Lição metodológica:** scripts que rodam em ambiente Windows devem evitar dependência de Unicode no `print()` ou usar `PYTHONIOENCODING=utf-8` como prefixo de comando.

### Estratificações aplicadas (mesmas 5 do v2, para comparabilidade)

| Subgrupo | Tamanho | Critério |
|---|---:|---|
| test_completo | 71.089 | todos |
| CA65926 | 7.083 (9,96%) | TAG == "CA65926" |
| resto_test (sem CA65926) | 64.006 (90,04%) | TAG ≠ "CA65926" |
| categorias_conhecidas (treino) | 69.277 (97,45%) | `tag_freq > 0` AND `operador_freq > 0` |
| categorias_unknown | 1.812 (2,55%) | `tag_freq == 0` OR `operador_freq == 0` |

### Comparação SHAP v2 vs v3 (validação da promoção)

| Quesito | v2 | v3 | Veredito |
|---|---|---|---|
| Top 1 | `horas_desde_ultimo_DG` (39,3%) | `qtd_alarmes_nivel_muito_alto_360min` (41,0%) | ✅ Substituição por feature antecipativa |
| Top 2 | `qtd_alarmes_muito_alto` (31,1%) | `tipo_caminhao` (23,9%) | ⚠️ tipo_caminhao subiu 5x — registrado como L8 |
| Top 3 | `razao_alarme_7d_vs_30d` (8,6%) | `razao_alarme_7d_vs_30d` (11,1%) | ✅ Família 4 subiu |
| Top 10 acumulado | 91% | 89,9% | ✅ Concentração similar |
| `horas_desde_ultimo_critico` | rank #7 (1,0%) | rank #11 (1,1%) | ✅ Não herdou papel da feature removida |
| Família 6 (regra) | 31,1% | 41,0% | ✅ Domain-specific reforçada |
| Família 4 (regimal) | 9,6% | 13,1% | ✅ Regimal reforçada |
| Família 1 (rolling) | ~7% acumulado | ~7% acumulado | = Inalterada (continua marginal) |
| Família 2 (recência) | 40,3% (era cascade) | 1,1% | ✅ Reduzida drasticamente (correto, era o objetivo) |

**Conclusão validativa:** a remoção de `horas_desde_ultimo_DG` redistribuiu o peso para a Família 6 (Regra de Negócio, 41%) e Família 4 (Regimal, 13%), com peso adicional para `tipo_caminhao` (Família 7 Encoding) que se tornou a base rate per equipamento.

---

**Última atualização:** 2026-05-24 (W6 — Seção 11: 08e v3 training; Seção 12: 08f SHAP v3; D-promoção registrada)
