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

### - [ ] 2.1 Top 5 alarmes concentram 88% dos DGs no semestre completo?

**Contexto:** No relatório inicial (apenas janeiro), 5 alarmes concentraram 88% dos Don't Go:
1. Engine Coolant Level - Active (1.505)
2. Aftercooler Level - Active (249)
3. Transmission Oil Level - Active (205)
4. Left Rear Brake Temperature - Active (160)
5. Right Front Brake Temperature - Active (116)

**Por que importa:** Se a concentração se mantém no semestre, foca feature engineering nesses 5 (vs criar features para 4.402 alarmes únicos).

**Investigar:** Mesma análise sobre `telemetria_limpa.parquet` (6 meses).

**Onde resolver:** W2 (EDA).

---

### - [ ] 2.2 `Informacional` continua sendo 0% de DGs no semestre completo?

**Contexto:** No relatório inicial (janeiro), 5.319.047 eventos Informacionais geraram **0** DGs.

**Por que importa:** Se a propriedade se mantém no semestre, podemos filtrar Informacional na limpeza (W3), economizando ~98,5% do volume sem perder positivos.

**Investigar:** Contar `Is_Dont_Go=1` quando `Criticidade='Informacional'` em todo o semestre.

**Onde resolver:** W2 ou W3.

---

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

### - [ ] 2.5 504 DGs com `Nao_Critico` se mantêm como acumulação no semestre?

**Contexto:** No relatório inicial (janeiro), 80% dos DGs vieram de `Critico` e 20% (504) de `Nao_Critico`. Os de `Nao_Critico` são alertas que só viram DG **por acúmulo** (regra `QTD > 1` na aba CMA).

**Por que importa:** Confirma necessidade de features de rolling window. Quantifica a proporção do problema que depende de padrão temporal vs. estado instantâneo.

**Investigar:** Mesma análise no semestre completo. Comparar proporção Critico × Nao_Critico nos DGs.

**Onde resolver:** W2.

---

## 3. Riscos a monitorar (não são observações, mas precisam vigilância)

### - [ ] 3.1 Estouro de memória em W4 (features com rolling windows)

**Risco:** Features de rolling 1h/4h/24h sobre 37M linhas vão multiplicar colunas. RAM pode estourar 4GB do `.venv` se não usar lazy mode.

**Monitorar:** Ao iniciar W4, primeiro teste com uma janela e medir uso de RAM antes de escalar.

**Mitigação se acontecer:** Migrar para `pl.scan_parquet().collect()` (lazy).

**Onde resolver:** W4.

---

### - [ ] 3.2 Drift temporal do modelo (jan-abr → jun)

**Risco:** Operação de mineração tem sazonalidade (chuva, troca de equipamentos, recapagem de pneus). Modelo treinado em jan-abr pode degradar em jun.

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

Este arquivo (`observacoes_importantes.md`) é **temporário** — contém apenas itens `[ ]` ainda em aberto.

---

**Última atualização:** 2026-05-16
