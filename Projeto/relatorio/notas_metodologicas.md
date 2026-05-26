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

---

## 13. Como o modelo de Sobrevivência Weibull AFT é construído e avaliado (`09_sobrevivencia.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Modelo de Sobrevivência — Weibull AFT como segunda leitura".

**Script:** `Projeto/codigo/09_sobrevivencia.py` (7 etapas)
**Comando:** `PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/09_sobrevivencia.py`
**Tempo:** ~56 s (Weibull fit 37 s + avaliação/figuras 19 s)

### Entrada e saídas

**Entrada:**
- `dados/features/v3.parquet` (544.885 × 58)

**Saídas:**
- `modelos/sobrevivencia.joblib` (14,5 MB) — dict com `modelo`, `tipo` (Weibull/Cox), `features`, `scaler`, `imputacao`, `horizonte_horas`
- `relatorio/tabelas/sobrevivencia_metricas.csv` — C-index + AUC-PR por split
- `relatorio/tabelas/sobrevivencia_hazard_ratios.csv` — 32 features × TR + IC 95% + p-valor + interpretação
- `relatorio/tabelas/sobrevivencia_features_excluidas_corr.csv` — 6 features removidas pelo filtro de correlação
- `relatorio/figuras/figExA_kaplan_meier_por_frota.png` — Kaplan-Meier por frota (5 curvas até 168 h)

### Construção (T, E) por evento

Para cada evento (linha) do `v3.parquet`:

```python
# 1. Sort por TAG, Data_Evento
df = df.sort(["TAG", "Data_Evento"])

# 2. Pre-extrair DGs por TAG (rename Data_Evento → data_proximo_dg)
dgs = df.filter(pl.col("Is_Dont_Go") == 1).select(["TAG", "Data_Evento"]) \
        .rename({"Data_Evento": "data_proximo_dg"})

# 3. join_asof forward: para cada evento, achar o proximo DG da mesma TAG
df = df.join_asof(dgs, left_on="Data_Evento", right_on="data_proximo_dg",
                  by="TAG", strategy="forward")

# 4. Validar: data_proximo_dg deve ser ESTRITAMENTE > Data_Evento
#    (se o proprio evento e DG, queremos o PROXIMO, nao ele mesmo)
df = df.with_columns(
    pl.when(pl.col("data_proximo_dg") > pl.col("Data_Evento"))
    .then(pl.col("data_proximo_dg")).otherwise(None)
    .alias("data_proximo_dg_validada")
)

# 5. T e E
df = df.with_columns(
    pl.when(pl.col("data_proximo_dg_validada").is_not_null())
    .then((pl.col("data_proximo_dg_validada") - pl.col("Data_Evento"))
          .dt.total_seconds() / 3600.0)  # horas ate proximo DG
    .otherwise((pl.col("ultima_obs_tag") - pl.col("Data_Evento"))
               .dt.total_seconds() / 3600.0)  # horas ate fim de observacao
    .alias("T_horas"),
    pl.when(pl.col("data_proximo_dg_validada").is_not_null())
    .then(1).otherwise(0).alias("E")
)

# 6. Filtrar T > 0 (eventos finais sem DG futuro tem T=0 — descartar)
df = df.filter(pl.col("T_horas") > 0)
```

**Resultado:** 544.722 eventos finais (163 descartados por T = 0). Distribuição de E:

| Split | Total | E = 1 | E = 0 (censurado) | % censurado |
|---|---:|---:|---:|---:|
| train | 394.863 | 331.619 | 63.244 | 16,0% |
| val | 78.816 | 60.159 | 18.657 | 23,7% |
| test | 71.043 | 30.184 | 40.859 | **57,5%** |

### Imputação de NaN (Cox/Weibull não toleram NaN)

| Feature | n_nulls | Estratégia | Valor |
|---|---:|---|---:|
| `razao_alarme_7d_vs_30d_anterior` | 404.795 | 1,0 (neutro semântico) | 1,0 |
| `razao_severidade_14d_vs_60d` | 1.232 | 1,0 (neutro semântico) | 1,0 |
| `taxa_DG_operador_30d` | 704 | mediana do treino | 0,0197 |
| `horas_desde_ultimo_critico` | 1.071 | max do treino (*worst case*) | 2.177,4 h |

**Por que essas escolhas:**
- Para *features* de razão (`razao_*`), o valor neutro é 1.0 (mesma taxa que baseline). Outras escolhas (0, mediana) introduziriam viés semântico.
- Para `taxa_DG_operador_30d`, mediana captura o operador "típico".
- Para `horas_desde_ultimo_critico`, max do treino representa "sem evento recente registrado" — *worst case* sensato.

A imputação é salva no `.joblib` para reprodutibilidade (mesmos valores aplicados em deployment).

### Filtro de correlação > 0,9 (Cox/Weibull são sensíveis a multicolinearidade)

```python
corr_abs = pdf.loc[train_mask, features].corr().abs()
# Iteracao em ordem: para cada feature, ver quais features POSTERIORES
# tem correlacao > 0.9 e dropar a com maior correlacao
i = 0
while i < len(features_finais):
    feat = features_finais[i]
    high_partners = [(other, corr_abs.loc[feat, other])
                     for other in features_finais[i + 1:]
                     if corr_abs.loc[feat, other] > 0.9]
    if high_partners:
        partner, corr_val = max(high_partners, key=lambda x: x[1])
        features_finais.remove(partner)
    else:
        i += 1
```

**6 features removidas** (todas Família 1 rolling counts, esperado dado que janelas adjacentes são quase idênticas):

| Feature removida | Correlacionada com | corr |
|---|---|---:|
| `count_critico_2h` | `count_critico_1h` | 0,944 |
| `count_critico_8h` | `count_critico_4h` | 0,944 |
| `count_nao_critico_2h` | `count_nao_critico_1h` | 0,942 |
| `count_total_1h` | `count_nao_critico_1h` | 0,912 |
| `count_nao_critico_8h` | `count_nao_critico_4h` | 0,931 |
| `count_total_4h` | `count_total_2h` | 0,926 |

**Restam 31 features** para o fit (de 37 após one-hot).

### Fallback automático Cox PH

```python
try:
    weibull = WeibullAFTFitter(penalizer=0.01)
    weibull.fit(train, duration_col="T_horas", event_col="E")
    # C-index na val (predict_expectation retorna TEMPO esperado — alto = sobrevida longa)
    val_pred = weibull.predict_expectation(val)
    c_val = concordance_index(val["T_horas"], val_pred, val["E"])
    if c_val >= 0.6:
        modelo, tipo = weibull, "WeibullAFT"
    else:
        # fallback
        ...
except (ConvergenceError, Exception):
    # fallback
    ...

# fallback para Cox PH
cox = CoxPHFitter(penalizer=0.01)
cox.fit(train, duration_col="T_horas", event_col="E")
modelo, tipo = cox, "CoxPH"
```

**Resultado da execução final:** Weibull AFT convergiu com C-index val = 0,7097 (passa threshold 0,6). Fallback **não acionado**. Cox PH testado em iteração anterior (C-index test = 0,7539, AUC-PR(4h) = 0,2635) — Weibull AFT venceu em ambas as métricas.

### Bug do C-index do Weibull corrigido durante execução

**Erro inicial:** na primeira tentativa, o cálculo de C-index dentro do `fit_modelo` negativava `predict_expectation`:

```python
# ERRADO (resíduo de adaptação do Cox PH que usa -partial_hazard)
val_pred = -weibull.predict_expectation(val)
```

Isso resultou em C-index val = 0,2903 (quase perfeitamente inverso de 0,71) — porque `concordance_index` espera valores onde **alto = sobrevida longa** (que é exatamente o que `predict_expectation` retorna nativamente, sem negativação).

**Correção:**
```python
# CORRETO
val_pred = weibull.predict_expectation(val)
c_val = concordance_index(val["T_horas"], val_pred, val["E"])
```

A diferença com Cox PH: `predict_partial_hazard` retorna o hazard relativo (alto = curto). Para `concordance_index` precisamos do inverso → `-partial_hazard`. Para Weibull AFT, `predict_expectation` já vem no formato certo.

**Lição metodológica:** ao adaptar código entre modelos com APIs similares mas semânticas diferentes (Cox usa hazard, Weibull AFT usa tempo de sobrevida), preferir testes unitários simples (rodar em um subconjunto onde a resposta esperada é conhecida) antes de aceitar resultados.

### Conversão para AUC-PR (comparação com LightGBM)

```python
# Probabilidade de DG ocorrer em <= 4h:
# P(T <= 4h) = 1 - S(4h)
surv_at_4h = modelo.predict_survival_function(sub, times=[4.0]).iloc[0].values
prob_dg_4h = 1.0 - surv_at_4h

# Comparavel com target_4h do LightGBM
auc_pr = average_precision_score(sub["target_4h"], prob_dg_4h)
```

**Por que AUC-PR(4h) é baixa apesar de C-index alto:** o C-index mede ranking de tempos de sobrevida (qualquer horizonte). A AUC-PR(4h) mede classificação binária em um horizonte específico (4 h). O Weibull AFT é otimizado para o primeiro, não o segundo. **Material para CM 6.1.**

### Cálculo dos hazard ratios (Time Ratios para Weibull AFT)

No Weibull AFT, o coeficiente `coef` se interpreta como **multiplicador do tempo de sobrevida**:

- `exp(coef) = TR` (Time Ratio)
- **TR < 1** → aumentar a feature **reduz** a sobrevida (= maior risco)
- **TR > 1** → aumentar a feature **aumenta** a sobrevida (= menor risco)

Isso é o **inverso** dos Hazard Ratios do Cox PH (onde HR > 1 = maior risco). O script reporta TR para Weibull AFT e HR para Cox PH, com coluna `interpretacao` explícita.

```python
summary = modelo.summary.copy().reset_index()
# Para Weibull AFT, a tabela tem coluna 'param' indicando qual parametro
# (lambda_ = scale, rho_ = shape). Filtramos so lambda_ (covariates).
df_hr = summary[summary["param"] == "lambda_"][
    ["covariate", "coef", "exp(coef)",
     "coef lower 95%", "coef upper 95%", "p", ...]
].rename(columns={"exp(coef)": "time_ratio_TR", ...})
df_hr["interpretacao"] = df_hr["time_ratio_TR"].apply(
    lambda tr: "RISCO MAIOR (sobrevida menor)" if tr < 1
               else "RISCO MENOR (sobrevida maior)" if tr > 1
               else "neutro"
)
```

### Kaplan-Meier por frota (Fig Extra A)

```python
for frota in sorted(pdf["Tag_Frota"].unique()):
    sub = pdf[pdf["Tag_Frota"] == frota]
    kmf = KaplanMeierFitter()
    kmf.fit(durations=sub["T_horas"], event_observed=sub["E"],
            label=f"{frota} (n={sub.shape[0]:,})")
    kmf.plot_survival_function(ax=ax, ci_show=True)
ax.set_xlim(0, 168)  # 7 dias
```

A curva KM é **não-paramétrica** (sem assumir distribuição) e **não ajustada por covariates** — captura apenas a heterogeneidade marginal entre frotas. Valida visualmente H4.1 (LeTourneau bem acima das 793-D).

### Concordância forte com SHAP v3 — material para CM 5.3

Comparação direta dos top features entre os dois métodos:

| Feature | SHAP v3 (LightGBM) | Weibull AFT (TR) | Convergência |
|---|---|---|---|
| `tipo_caminhao` | #2 (23,9%) | TR=0,038, rank #2 | ✅ ambos top |
| Família frota (dummies) | distribuída #7/#9 | ranks #4–#7 (TR 0,17–0,45) | ✅ ambos top |
| `razao_alarme_7d_vs_30d_anterior` | #3 (11,1%) | p < 0,0001 | ✅ ambos significativos |
| `tag_freq` | #4 (3,3%) | rank #1 (TR=1,43) | ✅ ambos no top |
| `operador_freq` | #12 (0,84%) | rank #8 (TR=1,12) | ✅ ambos modestos significativos |
| `qtd_alarmes_muito_alto_360min` | **#1 (41,0%)** | NÃO está no top 10 | ⚠️ **divergência metodológica** |

**Divergência interpretativa instrutiva:** LightGBM v3 prediz "DG em 4 h" especificamente; Weibull AFT modela "tempo até qualquer DG futuro". Features que sinalizam DG iminente (Família 6) brilham no LightGBM; features de base rate estrutural (frota, tipo, operador) brilham no Weibull. **Os dois modelos respondem perguntas diferentes** — usá-los em conjunto fortalece a entrega.

### Limitações específicas do Weibull AFT (CM 6.2)

- **Censoring assimétrico** (16% train / 57,5% test) — janela de 6 meses é curta. Registrado como L9.
- **AUC-PR(4h) baixa** — não é o modelo adequado para alerta operacional de curto prazo (papel do LightGBM v3).
- **Multicolinearidade** — 6 features Família 1 perdidas, granularidade temporal fina reduzida vs LightGBM.
- **Tratamento de NaN como imputação** — diferente do LightGBM que aprende com NaN nativo; introduz suposição (imputar com 1.0 / mediana / max do treino) que pode ser questionada.

### Quando re-rodar `09_sobrevivencia.py`

- Quando `v3.parquet` mudar (novas features, novo split)
- Quando o set de FEATURES for ajustado (manter alinhado ao LightGBM canônico)
- A análise SHAP do v3 (Seção 12) deve sempre ser executada em paralelo — comparação cruzada SHAP × HR é parte essencial da entrega

---

---

## 14. Como o Isolation Forest é construído e como ele diagnostica o Risco 3.3 (`11_isolation_forest.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Isolation Forest — diagnóstico do Risco 3.3".

**Script:** `Projeto/codigo/11_isolation_forest.py` (6 etapas)
**Comando:** `PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/11_isolation_forest.py`
**Tempo:** ~10,8 s (Isolation Forest é dramaticamente mais rápido que LightGBM e Weibull)

### Diferença fundamental vs LightGBM v3 e Weibull AFT

| Modelo | Supervisão | Usa `Is_Dont_Go`? | Pergunta que responde |
|---|---|---|---|
| LightGBM v3 | Supervisionado | ✅ Sim (target) | "Esse evento vai ter DG em 4 h?" |
| Weibull AFT | Supervisionado | ✅ Sim (deriva T, E) | "Quando vai ser o próximo DG?" |
| **Isolation Forest** | **Não-supervisionado** | ❌ **Não** | **"Esse evento é anômalo no espaço de features?"** |

Por isso o IF **não é um modelo concorrente** dos dois primeiros — é uma ferramenta de **auditoria do rótulo**. Se as anomalias detectadas pelo IF coincidem com os DGs reais (sem ele saber quais são), o rótulo CMA é validado empiricamente.

### Configuração

```python
IsolationForest(
    n_estimators=200,        # Default 100 OK; 200 dá +precisão sem custo significativo
    contamination="auto",    # Threshold padrão; thresholds específicos derivados depois
    random_state=42,
    n_jobs=-1,
)
```

**Features:** mesmas 34 do v3 canônico (alinhamento direto para comparabilidade) + 5 dummies de one-hot (`turno` 1 dummy + `estado_pre_evento` 4 dummies) = **37 features finais**.

**Pré-processamento idêntico ao `09_sobrevivencia.py`:** mesma imputação NaN (`razao_*`→1,0; `taxa_DG_operador_30d`→0,0197 mediana train; `horas_desde_ultimo_critico`→2.177,4 h max train) + StandardScaler. Isso garante que diferenças nos resultados venham do **método** (anomaly detection vs survival), não do **input**.

**Diferença vs 09:** IF **não** aplica filtro de correlação (anomaly detection tolera multicolinearidade melhor que Cox/Weibull; manter granularidade temporal fina aumenta a sensibilidade).

### Como o anomaly_score é computado

`IsolationForest.decision_function` retorna um *score* onde **alto = normal**, **baixo = anômalo**. Para uniformidade com a convenção "alto = pior" usada em hazard ratios e SHAP, o script inverte:

```python
decision = iforest.decision_function(X)  # alto = normal
anomaly_score = -decision                 # alto = anomalo
```

O `anomaly_score` é então comparado com `Is_Dont_Go` (binário) via:
1. **AUC-ROC** (contínuo, threshold-independent)
2. **Precision/Recall** em 4 thresholds (curva, threshold-dependent)
3. **Tabela de contingência 2×2** em cada threshold

### Por que múltiplas contaminations (curva), não um único valor

Reportar apenas um número (`contamination='auto'`) seria perda de qualidade. A curva [0,01; 0,03; 0,05; 0,10] expõe:

- Como Precision **decai** quando flexibilizamos o threshold (alto threshold = poucas anomalias, alta P)
- Como Recall **sobe** com threshold mais frouxo
- O ponto onde F1 máximo balanceia P e R
- A natureza do trade-off operacional para deployment

### Estratificação por CA65926 (Etapa 3b — hipótese ad-hoc)

A primeira execução revelou padrão suspeito: AUC train=0,58 / val=0,60 / **test=0,86**. Como train/val ficaram quase aleatórios e test ficou forte, a hipótese imediata foi: **o sinal de test vem da anomalia dominante do CA65926** (Obs 2.9 W5 — 82,2% dos DGs de jun vêm desse único equipamento).

A validação foi adicionada como **Etapa 3b** do script (rodando após o AUC global, dentro do test apenas):

```python
mask_ca = (test["TAG"] == "CA65926")
auc_ca = roc_auc_score(y[mask_ca], scores[mask_ca])
auc_resto = roc_auc_score(y[~mask_ca], scores[~mask_ca])
```

**Resultado:**
| Subgrupo | n | AUC-ROC |
|---|---:|---:|
| Test completo | 71.089 | 0,860 |
| CA65926 apenas | 7.083 | **0,897** |
| Test sem CA65926 | 64.006 | **0,541** |

A estratificação **transformou um achado simples em um achado nuançado e mais valioso**. **Mas é teste de hipótese ad-hoc** — vale a pena complementar com análise estrutural (Etapa 3c).

### Análise estrutural — AUC-ROC por TAG (Etapa 3c)

A Etapa 3b testa uma hipótese específica (CA65926). A Etapa 3c é **estruturalmente mais robusta**: computa AUC-ROC para **cada uma das 30 TAGs** presentes no test, sem premissa prévia.

```python
for t in sorted(np.unique(tag)):
    mask = tag == t
    n_dg = int(y[mask].sum())
    if n_dg == 0 or n_dg == len(y[mask]):
        # AUC indefinido — sem variabilidade no target
        continue
    auc = roc_auc_score(y[mask], scores[mask])
```

**Resultados consolidados:**

| Estatística | Valor |
|---|---:|
| TAGs no test | 30 |
| TAGs com AUC válido (variabilidade no target) | 26 |
| AUC mediana | **0,6060** |
| AUC média | 0,6377 |
| AUC máximo | 0,9263 (PE3797, n_DG=1 — artefato amostral) |
| AUC mínimo | 0,3510 (CA65931) |
| TAGs com AUC ≥ 0,75 | 5 de 26 |
| **TAGs com AUC ≥ 0,75 E n_DG ≥ 10** | **3 de 26 (CA65926, CA65932, CA65924)** |
| TAGs com AUC < 0,55 (~aleatório) | 8 de 26 |

**Três insights críticos só visíveis na análise estrutural:**

1. **AUC agregado vs mediana** — o agregado 0,86 vem de média ponderada por número de eventos; CA65926 (10% dos eventos, 82% dos DGs) domina. **A mediana por TAG (0,61) é a medida honesta** do sinal *típico* — o que o IF entrega em deployment para um equipamento arbitrário.

2. **Artefatos amostrais nos top AUCs** — as escavadeiras LeTourneau PE3797 (AUC=0,93) e PE3795 (AUC=0,93) parecem ter sinal forte mas têm apenas 1 e 3 DGs respectivamente. **Restringindo a sample significativo (n_DG ≥ 10), restam apenas 3 TAGs com sinal forte.**

3. **Validação independente do W4 — CA65924.** O IF, sem usar o rótulo, identifica o CA65924 como anômalo (AUC=0,79). Esse é o caso paradigma da Obs 2.3 (refutação parcial do padrão "calmaria → acúmulo" universal). **A escolha de W4 foi vindicada por método independente.**

**Lição metodológica importante:** estratificar **por todas as classes** (todas as TAGs) é mais rigoroso que estratificar **por uma classe suspeita** (CA65926 vs resto). A análise estrutural por TAG revela a distribuição completa; a análise por hipótese ad-hoc só responde "essa hipótese é verdade?". Para qualidade máxima em projetos futuros, **começar pela estrutura** evita viés de confirmação de hipóteses prévias.

**Trade-off da escolha de métricas no `11_isolation_forest.py`:**

Após análise honesta, as três métricas escolhidas inicialmente (AUC-ROC + P/R por threshold + contingência 2×2) tinham **leve redundância** — P/R por contamination repetia informação contida no AUC-ROC. A escolha **ótima** teria sido AUC-ROC + Contingência + **AUC-ROC por TAG (estrutural)**. A análise por TAG foi adicionada *post-hoc* depois desse reconhecimento — está documentada como a Etapa 3c. Material direto para reflexão metodológica no relatório final.

### Interpretação do veredito

O script implementa lógica condicional na função `sintese_risco_33`:

```python
if auc_ca >= 0.75 and auc_resto < 0.60:
    print("ASSIMETRIA FORTE entre regimes:")
    print("- CA65926: CMA-IF concordam (rótulo captura anomalia real)")
    print("- Resto:   CMA-IF discordam (rótulo pode ser arbitrário aí)")
    print("VEREDITO: Risco 3.3 PARCIALMENTE MITIGADO (assimétrico por regime).")
```

Esta interpretação é **mais honesta** do que um veredito binário "mitigado / confirmado" — captura a heterogeneidade real do problema.

### Análise dos FPs como possíveis "DGs perdidos pelo CMA"

A tabela de contingência mostra os 4 quadrantes (TN, FP, FN, TP). O quadrante FP (eventos com `anomaly_score` alto que **não** foram rotulados como DG) é interessante: são candidatos a **DGs que escaparam das 82 regras CMA**. Análise manual de uma amostra desses eventos seria material valioso para a Vale.

No threshold 0,01 (top 1% das anomalias), tivemos 70 FPs em test. Esses 70 eventos têm `anomaly_score` no top 1% mas o sistema CMA não os classificou como DG. Possibilidades:

- (a) Anomalia estatística sem significado mecânico (sensor disponível anomalamente, padrão de tempo incomum)
- (b) Falha mecânica real que escapou das regras CMA (validaria leitura inversa do Risco 3.3)

Sem inspeção manual com domínio especialista, não se pode discriminar (a) de (b). **Trabalho Futuro registrado em CM 6.3.**

### Por que `contamination='auto'` no fit (e não fixo)

Uma alternativa seria fixar `contamination=0.0341` (taxa real de DG no train). Isso **forçaria** o IF a flagar exatamente 3,41% como anômalo — e introduziria viés circular (usar conhecimento sobre o rótulo para calibrar o modelo que deveria ser não-supervisionado).

Usando `contamination='auto'`, o sklearn calibra via estatística da amostra. Os thresholds reportados na curva são derivados **depois**, via quantis do `anomaly_score` em test. Isso é metodologicamente mais limpo.

### Coerência com SHAP do v3 e Weibull AFT

Três técnicas independentes chegam ao mesmo achado:

| Técnica | Métrica | Sobre CA65926 |
|---|---|---|
| **LightGBM v3 + SHAP** | `tipo_caminhao` 24% peso, `frota_793D_5S` no top | Modelo aprende que esse tipo/frota tem falha distinta |
| **Weibull AFT** | TR `tipo_caminhao` = 0,038 (sobrevida 3% da escavadeira) | Equipamento-específico domina hazard |
| **Isolation Forest** | AUC CA65926=0,897 vs resto=0,541 | Equipamento-específico domina anomalia |

**Esse alinhamento é evidência forte de uma realidade subjacente:** o test set é dominado pela anomalia do CA65926. Três métodos com fundamentação matemática completamente diferente (Shapley values + maximum likelihood paramétrico + isolation tree não-supervisionado) chegam à mesma conclusão. Material direto para **CM 6.1 (Insight Não Óbvio — convergência metodológica como validação)**.

### Limitações específicas do Isolation Forest (CM 6.2)

- **Não é otimizado para classificação binária** — usa estrutura intrínseca dos dados (até onde uma árvore consegue isolar um ponto). AUC-ROC não é interpretável como performance preditiva.
- **Sensível a escala** (mitigado pelo StandardScaler, mas vale registrar).
- **Sem labels = sem garantia** de que "anomalia estatística" e "anomalia mecânica" sejam o mesmo. É exatamente essa diferença que o teste mede.

### Quando re-rodar `11_isolation_forest.py`

- Quando `v3.parquet` mudar (novas features, novo split)
- Após mudanças no conjunto de features do v3 (manter alinhamento)
- Em diagnósticos periódicos de deployment: rodar IF em novos dados de produção para detectar mudança de regime (se AUC com label começar a divergir, é sinal de drift ou novos tipos de anomalia)

---

---

## 15. Como a validação cruzada SHAP × HR é construída (`12_validacao_sentido_features.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Fechamento de W6 — análises complementares" → subseção "Validação cruzada SHAP × Hazard Ratios". CM 5.3 do relatório final.

**Script:** `Projeto/codigo/12_validacao_sentido_features.py`
**Comando:** `PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/12_validacao_sentido_features.py`
**Tempo:** < 5 s (apenas leitura de CSVs + join)

### Por que comparar duas técnicas em vez de confiar em uma

O LightGBM v3 com SHAP entrega um ranking de importância via Shapley values. Mas Shapley values têm uma propriedade conhecida: **atribuem peso baseado em uso, não em causalidade ou necessidade**. Se duas features são fortemente correlacionadas, o modelo pode usar uma e ignorar a outra, e o SHAP atribui ao usado.

O Weibull AFT (lifelines) entrega coeficientes interpretáveis como *time ratios* (TR) com IC 95% e p-valor. A formulação paramétrica é completamente diferente da árvore-baseada do LightGBM. Se ambas técnicas convergem sobre as mesmas features, isso é evidência forte de **validade estatística** — não é artefato do método específico.

### Como o ranking do Weibull é gerado

```python
# log|TR| captura a magnitude do efeito independente da direção
hr_clean = hr_clean.with_columns(
    pl.col("weibull_TR").log().abs().alias("log_TR_abs")
).sort("log_TR_abs", descending=True).with_row_index("weibull_rank", offset=1)
```

Importante: rank baseado em `|log(TR)|` (não em p-valor). Por que: com n=395k no train, *qualquer* feature minimamente diferente de zero tem p<0,001 (significância estatística é trivial em datasets grandes). O critério honesto é **magnitude do efeito**, capturada por `|log(TR)|`.

### Por que 4 features no top 10 de AMBOS é "concordância forte"

Considere: temos 34 features no v3, das quais 32 entram na tabela Weibull (descontando Intercept e + dummies). A probabilidade de uma feature aleatória aparecer no top 10 de uma das tabelas é 10/32 ≈ 31%. A probabilidade conjunta independente seria 0,31² ≈ 10%. Esperaríamos 32 × 0,10 ≈ 3 features no top 10 de ambos por acaso.

**Resultado observado: 4 features no top 10 de AMBOS.** Marginalmente acima do esperado por acaso, mas todas as 4 são **estruturais** (`tipo_caminhao`, `tag_freq`, `frota_793D_4S`, `frota_793D_5S`) — não é um conjunto aleatório, é um *cluster semântico* (identidade do equipamento). A coerência semântica é o que dá confiança, não apenas a contagem.

### Por que as divergências são informativas

Features com alto SHAP mas baixo Weibull (`qtd_alarmes_muito_alto_360min` SHAP #1 com 41%, Weibull #26) não são "erros" — são **sinais antecipativos**. LightGBM v3 prediz target_4h (DG em 4h). Esses sinais brilham nesse horizonte. Weibull modela tempo até qualquer DG futuro — sinais imediatos perdem peso para sinais de base rate.

**Os dois modelos respondem perguntas diferentes** — usar ambos no relatório dá ao leitor uma visão dupla do problema, não conflitante mas complementar.

---

## 16. Como as curvas ROC + PR comparativas são geradas (`13_curvas_comparativas.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Fechamento de W6" → "Fig 9 — Curvas ROC + Precision-Recall comparativas". CM 5.1 do relatório.

**Script:** `Projeto/codigo/13_curvas_comparativas.py`
**Tempo:** ~30 s (3 inferências em test + plotagem)

### Por que 3 modelos no mesmo gráfico

Os três modelos têm objetivos diferentes:
- **Baseline** (`count_critico_4h ≥ threshold`): heurística operacional simples; serve como referência mínima
- **LightGBM v3:** classificação supervisionada para target_4h; modelo canônico para deployment 4 h
- **Weibull AFT:** sobrevivência; otimiza ranking de tempos de vida

Mostrar os 3 lado a lado deixa visualmente claro que o v3 vence em AUC-PR (caso de uso operacional), enquanto Weibull oferece outro valor (ranking ordinal robusto + interpretabilidade + censoring rigoroso). Não é "competição"; é "complementaridade" — formato perfeito para o CM 5.1.

### Detalhe técnico — predição do Weibull para 4h

O Weibull AFT retorna função de sobrevivência S(t). Para comparação com `target_4h`, convertemos:

```python
# P(T <= 4h | X) = 1 - S(4h | X)
surv_at_4h = modelo.predict_survival_function(pdf_scaled, times=[4.0]).iloc[0].values
prob_dg_4h = 1.0 - surv_at_4h
```

Essa probabilidade é usada como score de classificação. A curva PR resultante é menor que do v3 porque o Weibull não foi otimizado especificamente para o horizonte 4 h.

### Pequena curiosidade reportada

A prevalência reportada (16,93% de target_4h positivo no test) é maior que a taxa de DG bruta (7,35% Is_Dont_Go=1 no test) porque target_4h captura "**qualquer DG nas próximas 4h**" (não apenas o evento DG instantâneo). Coerente com a definição da target em CM 4.1.

---

## 17. Como a calibração do v3 é avaliada (`14_calibracao_v3.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Fechamento de W6" → "Calibração do v3 + Platt scaling". CM 5.2 do relatório + nota em L4 (CM 6.2).

**Script:** `Projeto/codigo/14_calibracao_v3.py`
**Tempo:** ~15 s

### O que é ECE e por que ele importa

ECE (Expected Calibration Error) é definido como a média ponderada da distância entre a probabilidade média predita em um bin e a fração real de positivos nesse bin:

```python
ece = sum_{i=1..N_bins} (n_bin / n_total) * |acc - conf|
```

Onde:
- `conf` = média da probabilidade predita no bin i
- `acc` = fração real de positivos no bin i

Um modelo perfeitamente calibrado teria `acc = conf` em todos os bins → ECE = 0.

**Por que importa operacionalmente:** quando a Vale opera o modelo, espera que "probabilidade 0,30" signifique "30% de chance de DG". Se o modelo é confiante mas mal calibrado (ex: prediz 0,30 mas a fração real é 0,15), os alertas são **2× mais frequentes** que necessário. Calibração afeta diretamente o custo operacional.

### Por que limiar a priori de 2pp

ECE de 2pp = "em média, a probabilidade predita está ±2pp da fração real". É a fronteira aceitável para deployment em domínios sensíveis (saúde, manutenção crítica) segundo a literatura padrão. Definido a priori antes da execução para evitar racionalização post-hoc.

### Brier score + skill — leitura honesta

`Brier = mean((p_pred - y_true)²)` mede erro quadrático médio. **Brier baseline** = `prev × (1 − prev)` é o Brier de uma predição constante igual à prevalência. **Skill** = `1 − Brier/Brier_baseline`:
- Skill > 0: modelo melhor que baseline constante
- Skill = 0: modelo igual a baseline
- Skill < 0: modelo pior que baseline

O v3 tem **skill = +0,59 no test** — substancialmente melhor que predição constante. O Brier raw (0,05745) é baixo absolutamente. **O modelo discrimina bem.** O problema é apenas calibração (overconfidence em algumas regiões).

### Platt scaling — implementação

```python
platt = LogisticRegression(max_iter=1000)
platt.fit(p_val_raw.reshape(-1, 1), y_val)  # 1 feature: prob raw -> y
p_test_cal = platt.predict_proba(p_test_raw.reshape(-1, 1))[:, 1]
```

É uma transformação **monotônica** (sigmoid de uma transformação linear da prob raw). Preserva o ranking (AUC-PR / AUC-ROC inalterados), só estica/comprime a escala de probabilidade. Por isso é "calibração" e não "novo modelo".

### Por que Platt funcionou no val mas falhou no test

Platt foi fitado no val. No val, o ajuste reduz ECE de 3,70pp para 1,87pp (esperado — ajuste sobre a própria amostra). No test, o ECE **aumenta** de 3,78pp para 4,76pp.

Interpretação: a **distribuição de calibração** do v3 é diferente entre val (mai/2025) e test (jun/2025). No val, o modelo é overconfident em uma direção; no test, overconfident em outra direção (provavelmente influenciado pelo CA65926). A regressão logística do Platt aprende a correção do val e aplica ao test — mas a correção do val é exatamente a errada para o test.

**Isto é um sinal direto do drift mai→jun (L4) afetando a calibração**, não apenas a métrica AUC-PR. **Material para CM 6.2.**

### Recomendação operacional

Não usar Platt scaling em deployment. Em produção a Vale enfrentará regimes possivelmente diferentes do test set (que é jun/2025 dominado pelo CA65926). Aplicar uma correção fitada no val (mai/2025, regime distribuído) sobre dados de produção em um regime futuro seria arbitrariedade. **Manter v3 raw é a escolha conservadora e empiricamente justificada.**

O calibrador Platt fica salvo em `modelos/calibrador_v3_platt.joblib` como artefato auditável, mas com "nota explícita de não usar" no JSON do artefato.

---

## 18. Como a ablation por grupo de features é construída (`15_ablation_grupos.py`)

> **Onde os resultados aparecem em `rascunho.md`:** Metodologia Parte 3 → seção "Fechamento de W6" → "Ablation por grupo de features". CM 6.1 (Insight Não Óbvio) + CM 6.3 (robustez operacional).

**Script:** `Projeto/codigo/15_ablation_grupos.py`
**Tempo:** ~110 s (8 retreinos × ~13 s cada com `lgb.LGBMClassifier`)

### Por que hiperparâmetros FIXOS

O plano original previa Optuna por ablation (6 × 25 min ≈ 2,5 h). Decisão consciente: usar os best params do v3 fixos. Razões:

1. **Comparabilidade**: queremos medir o efeito de remover features, não de re-tuning. Fixar params controla a variável "hiperparâmetros".
2. **Custo**: 110 s vs 2,5 h = 80× mais rápido.
3. **Trade-off honesto**: com menos features, params ligeiramente diferentes seriam ótimos. O sinal NEGATIVO desse compromisso é que ablations marginais podem mostrar `delta > 0` apenas porque os params estão sub-otimizados para o feature set reduzido. **Documentamos isso explicitamente como interpretação alternativa.**

### Como os grupos foram definidos

7 grupos disjuntos cobrindo as 34 features do v3 + dummies das categóricas (turno, estado_pre_evento):

| Grupo | Features |
|---|---|
| G1 temporais | hora_dia, dia_semana, turno, mes |
| G2 rolling | 15 features `count_*_*h` (Família 1 inteira) |
| G3 recência | horas_desde_ultimo_critico (v3 já não tem horas_desde_ultimo_DG) |
| G4 operador | taxa_DG_operador_30d, n_bypasses_operador_7d, operador_freq |
| G5 regra de negócio | qtd_alarmes_nivel_muito_alto_360min |
| G6 categóricas codificadas | tag_freq, 4 frotas, tipo_caminhao, estado_pre_evento, valor_disponivel |
| G7 regimal | razao_alarme_7d_vs_30d_anterior, razao_severidade_14d_vs_60d |

Critério: grupos *semanticamente coerentes* (Família + suas variantes). Reflete a categorização original das 7 famílias de features do `05_features.py`.

### Achado surpreendente — SHAP × ablation revelando redundância

A maior contribuição metodológica desta análise:

**SHAP atribui peso a features pelo USO dentro de árvores treinadas.** Se duas features fortemente correlacionadas estão disponíveis, o modelo usa uma e o SHAP atribui à usada.

**Ablation mede o que acontece quando removemos um conjunto.** Se há features alternativas que capturam o mesmo sinal, o modelo simplesmente "muda de rota" e a performance se mantém.

**A diferença entre SHAP e ablation é a medida quantitativa da REDUNDÂNCIA do feature set.**

No v3:
- `qtd_alarmes_muito_alto_360min` SHAP 41%, ablation +0,18% → **alta redundância** (modelo encontra outras rotas)
- `tipo_caminhao` SHAP 24%, ablation (G6 inteiro) +0,75% → **alta redundância**
- Família 4 regimal SHAP 13% conjunto, ablation −0,51% → **ÚNICO grupo necessário**

Essa decomposição é original e valiosa para CM 6.1.

### Por que vários grupos melhoram quando removidos

Três hipóteses (não mutuamente exclusivas):

1. **Regularização efetiva** — remover features age como L1 implícito; modelo overfita menos
2. **Ruído correlacionado** — features redundantes adicionam ruído; removê-las reduz variância
3. **Hiperparams não-otimais para o reduzido** — params do Optuna otimizados para 34 features. Com menos, params ligeiramente diferentes seriam melhores. Esse efeito **artificialmente** infla os deltas positivos. Não é regularização perfeita.

**Hipótese 3 é importante**: significa que melhorias de +0,005 não são necessariamente "remover essa feature melhora o modelo" — podem ser "remover essa feature e re-tunar daria a mesma performance". O sinal honesto é que essas features **não são necessárias**, não que sejam **prejudiciais**.

### Implicação operacional crítica

O v3 é **robusto a perda de features** em deployment. Mesmo removendo 8 das 34 (G6 inteiro), mantém AUC-PR=0,86. Para a Vale, isso significa que:
- Falha temporária de sensores (perda de `valor_disponivel`) não derruba o modelo
- Categorias unknown em deployment (TAG nova, frota nova) não causam degradação catastrófica
- Múltiplas rotas redundantes = sistema mais resiliente

**Material direto para CM 6.3 (Trabalhos Futuros — robustez operacional).**

### Quando re-rodar `15_ablation_grupos.py`

- Quando o conjunto de features do v3 mudar substancialmente
- Quando o test set mudar (novos meses adicionados, regime diferente)
- Em análises de robustez para defesa do modelo (showcase de resiliência)

---

**Última atualização:** 2026-05-25 (W6 — Seções 15, 16, 17, 18 adicionadas: validação cruzada SHAP × HR, Fig 9 (curvas comparativas), calibração + Platt scaling, ablation por grupo. **Insight metodológico central:** SHAP mede atribuição, ablation mede necessidade — a diferença é redundância. v3 é robusto por múltiplas rotas redundantes.)
