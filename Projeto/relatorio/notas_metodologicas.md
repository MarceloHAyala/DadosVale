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

**Última atualização:** 2026-05-22 (W5 — Obs 2.4 e 2.9 resolvidas + verificação empírica do tratamento de categorias unknown no encoding fix)
