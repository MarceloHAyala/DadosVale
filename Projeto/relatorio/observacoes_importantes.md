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

### - [ ] 2.3 Padrão "calmaria → acúmulo → disparo" do caso CA65924 aparece em outros equipamentos?

**Contexto:** O arquivo `desenvolver_dontgo.xlsx` traz 147 eventos consecutivos do caminhão CA65924 culminando em um DG, com narrativa clara de acúmulo gradual.

**Por que importa:** Se o padrão é universal, valida o uso de **rolling windows** como feature dominante (W4). Se é caso isolado, precisa estratégia alternativa.

**Investigar:** Para cada DG no semestre, contar eventos do mesmo TAG nos 60min anteriores. Distribuição esperada: se padrão CA65924 é universal, a maioria dos DGs deve ter pico de eventos pré-disparo.

**Onde resolver:** W2 (EDA) ou W4 (validação de features).

---

### - [ ] 2.4 Operador OP_067 (do caso CA65924) tem taxa de DG anormal?

**Contexto:** O caso paradigma envolve um operador específico. Vale checar se OP_067 tem mais DGs que a média.

**Por que importa:** Responde diretamente a **Q3** (operador correlaciona com alertas?).

**Investigar:**
- Taxa de DG por operador (DGs / total de eventos do operador)
- OP_067 está no top? É outlier?
- Distribuição geral: alguns operadores são sistematicamente piores?

**Onde resolver:** W4 (criação da feature `taxa_DG_operador_30d`) ou W7 (análise de Q3 via SHAP).

---

### - [ ] 2.6 Por que `Nao_Critico` saltou de 20% para 48% dos DGs entre janeiro e o semestre?

**Contexto:** Investigação de Obs 2.5 (16/05/2026) revelou mudança radical na composição dos DGs entre janeiro (80% `Critico` / 20% `Nao_Critico`, total 2.509 DGs) e o semestre completo (51,5% / 48,5%, total 19.962 DGs). Fev-jun acumulou 9.172 DGs `Nao_Critico` — média de 1.834/mês, **3,6× a taxa de janeiro**.

**Por que importa:**
- Se for crescimento mensal sustentado, indica **mudança estrutural** (mais equipamentos, mudança de regra CMA, deriva operacional) que afeta diretamente a generalização do modelo treinado em jan-abr para o teste em jun.
- Se for picos isolados em meses específicos, indica eventos pontuais (ex: 1 frota em ramp-up, 1 problema sazonal) — modelo precisa lidar com não estacionariedade.
- Conecta com risco 3.2 (drift temporal): se a distribuição dos DGs muda mês a mês, validação por split temporal precisa ser interpretada com cautela.

**Investigar:**
- Distribuição mensal de DGs `Nao_Critico` (jan, fev, mar, abr, mai, jun) — tendência linear, exponencial ou picos?
- Quebrar por **frota / tipo / alarme**: o salto vem de toda a operação ou de subgrupo específico?
- Cruzar com calendário operacional da Vale se possível (não disponível neste escopo)

**Onde resolver:** W2 (EDA visual — alimenta Fig 4 do guia: série temporal de DGs).

---

## 3. Riscos a monitorar (não são observações, mas precisam vigilância)

### - [x] 3.1 Estouro de memória em W4 (features com rolling windows) — RISCO DESATIVADO

**Risco original:** Features de rolling 1h/4h/24h sobre 37M linhas vão multiplicar colunas. RAM pode estourar 4GB do `.venv` se não usar lazy mode.

**Conclusão (16/05/2026):** Risco desativado pela decisão de filtrar `Criticidade = Informacional` em W3 (registrada em `controle_alteracoes.md`, validada na Obs 2.2). Pós-filtro o dataset cai para ~544.885 linhas (de 37.164.054) — rolling windows passam a caber confortavelmente em RAM. Nova posição: monitorar memória só se algum experimento exigir reincluir `Informacional` (não previsto no plano).

---

### - [ ] 3.2 Drift temporal do modelo (jan-abr → jun)

**Risco:** Operação de mineração tem sazonalidade (chuva, troca de equipamentos, recapagem de pneus). Modelo treinado em jan-abr pode degradar em jun.

**Reforço (16/05/2026):** Obs 2.5 já mostrou mudança radical na composição dos DGs entre janeiro e o semestre — o risco de drift **não é teórico**, é empiricamente provável. Investigação 2.6 vai quantificar.

**Monitorar:** Análise de drift mensal (AUC-PR por mês no teste de junho).

**Mitigação se acontecer:** Discussão honesta no relatório (W8) + recomendação de retraining mensal nos Trabalhos Futuros.

**Onde resolver:** W7.

---

### - [ ] 3.3 Viés inerente do label CMA

**Risco:** `Is_Dont_Go` é gerado pelas regras CMA, não pela falha física real. Modelo aprende a antecipar a regra, não o evento de campo.

**Monitorar:** Treinar Isolation Forest SEM o label e ver se recupera os DGs. Se sim, há sinal estrutural além da regra. Se não, modelo está limitado ao escopo da regra.

**Mitigação se acontecer:** Sanity check honesto no relatório (W7-W8), CM 6.1.

**Onde resolver:** W6 (Isolation Forest diagnóstico).

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

Este arquivo (`observacoes_importantes.md`) é **temporário** — contém apenas itens `[ ]` ainda em aberto.

---

**Última atualização:** 2026-05-16
