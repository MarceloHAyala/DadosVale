# Planejamento — Desafio Análise Avançada de Dados

**Programa Desenvolver 2026 | Vale**
**Participante:** Marcelo Ayala
**Data de início:** 13/05/2026
**Data de entrega:** 20/07/2026 (envio para `projetodesenvolver@vale.com`)
**Janela útil:** 10 semanas

---

## 1. Contexto

Desafio aberto de antecipação de alertas críticos (Don't Go) em frotas de mineração da região de Itabira, com 6 meses de dados (jan-jun/2025): ~37 milhões de eventos de telemetria + ~378 mil ciclos de apontamento.

**Fluxo do programa:**
1. ✅ Verificar arquivos
2. ⏳ Preparar e checar os dados
3. ⏳ Desenvolver o Desafio
4. ⏳ Gerar Relatório final
5. ⏳ Enviar solução por e-mail

**Marcos do programa:**
- 27/04/2026 — Pacote de dados recebido
- 28/04 a 20/07/2026 — Desenvolvimento
- 27/07/2026 — Divulgação dos Finalistas
- 24/08/2026 — Evento de Encerramento

---

## 2. Escopo: 6 perguntas analíticas

### Pergunta primária (foco do modelo)

**Q1** — Dado o histórico recente de telemetria, qual a probabilidade do equipamento gerar um alerta Don't Go nas próximas 4 horas?

Justificativa da janela de 4h:
- Tempo suficiente para a manutenção mobilizar peça/equipe
- Curto o bastante para que o estado atual ainda seja preditivo
- Compatível com o ciclo médio de turno em Itabira

### Perguntas secundárias (subprodutos do mesmo pipeline)

| # | Pergunta | Como será respondida |
|---|---|---|
| Q3 | Comportamento do operador correlaciona com alertas? | Feature `taxa_DG_operador_30d` + SHAP |
| Q4 | Perfil dos equipamentos com mais alertas (frota/tipo)? | EDA + análise de importância por frota |
| Q5 | Alertas concentram em turnos/dias/períodos? | Heatmap hora × dia da semana |
| Q6 | Recomendação de ação (continuar/preventiva/parar)? | Limiar da curva PR + tabela custo-benefício |
| Q7 | Como priorizar fila de inspeção da manutenção? | Ranking pelo score do modelo de Q1 |

### Pergunta fora de escopo

**Q2** — Prever o **tipo** do próximo alerta (motor vs. transmissão).

Justificativa: exige modelo multi-classe separado com tratamento específico de classes raras (alguns tipos têm < 50 ocorrências). Fora de escopo dado o tempo disponível e o trabalho ser individual. **Vai para Trabalhos Futuros.**

### Métrica de sucesso de negócio

- **Recall** sobre Don't Go (perder alerta = parada não planejada)
- **Precision** aceitável (falsos positivos geram inspeção desnecessária)
- **Tempo médio de antecipação** do alerta

---

## 3. Decisões técnicas (fixas — não trocar depois)

| Decisão | Escolha | Justificativa |
|---|---|---|
| Engine de dados | **Polars** | 37M linhas em pandas = 24GB RAM; Polars roda em 4GB |
| Modelo principal | **LightGBM** | Rápido, lida com desbalanceamento, SHAP funciona nativo |
| Modelo alternativo | **Modelo de Sobrevivência (Weibull AFT, fallback Cox PH)** | Prevê *tempo até* próximo DG (não só vai/não vai) — narrativa quantitativamente distinta e mais rica que classificação binária. Listado no CM 4.3 como caminho válido |
| 3ª abordagem (não supervisionada) | **Isolation Forest** treinado sem `Is_Dont_Go` | Resposta empírica direta ao viés inerente do label CMA: se IF recupera os DGs sem ver o rótulo, há sinal estrutural além da regra; se não recupera, a regra é o único sinal visível nos dados disponíveis. Diagnóstico complementar, não modelo competidor (CM 4.3 — "label de anomalia") |
| Biblioteca de sobrevivência | **lifelines** | Padrão Python para Cox/Weibull/Kaplan-Meier; documentação madura |
| Validação | Split temporal fixo + walk-forward final | jan-abr / mai / jun |
| Tuning | **Optuna**, 50 trials | Mais eficiente que GridSearch em poucos dias |
| Estratégia de desbalanceamento | `class_weight='balanced'` no LightGBM | Padrão para prevalência ~0,05%; comparação SMOTE/sem balanceamento descartada por retorno marginal frente ao custo — espaço de W5/W6 redirecionado para Isolation Forest |
| Interpretabilidade | **SHAP** (LightGBM) + coeficientes/HR (sobrevivência) | Padrão da indústria; sobrevivência permite interpretação direta de hazard ratio |
| Visualização | **matplotlib + seaborn** (não plotly) | Exporta PNG limpo para Word |
| Versionamento | Git local + push semanal para GitHub privado | Backup + sync entre máquinas |
| Gerenciador de pacotes | **uv** (pyproject.toml + uv.lock) | Reprodutibilidade exata entre máquinas; downloads paralelos; pina versão do Python |

---

## 4. Estrutura do projeto

```
AnaliseDadosVale/                            ← raiz do repositório Git
├── .gitignore
├── .python-version                          (Python 3.13 pinado)
├── pyproject.toml                           (deps gerenciadas via uv)
├── uv.lock                                  (versões exatas — versionado no Git)
├── README.md                                (como rodar em outra máquina)
├── PLANEJAMENTO.md                          (este arquivo)
├── Original/                                (backup intocado dos dados originais)
└── Projeto/                                 ← código + dados + entregáveis
    ├── Alterado/                            (dados de trabalho — base utilizada)
    │   ├── Base de Dados/
    │   │   ├── datasets/
    │   │   │   ├── apontamentos/desenvolver_apontamentos.parquet
    │   │   │   └── telemetria/telemetry_{jan,feb,mar,abr,may,jun}.parquet
    │   │   ├── Alarmes - Regra de Negocio.xlsx
    │   │   └── Dicionario_Dados.xlsx
    │   ├── Estudo Guiado - Análise Avançada de Dados.pdf
    │   └── Desenvolver_Template.docx
    ├── codigo/
    │   ├── 01_ingestao.py                   (W1)
    │   ├── 02_eda.py                        (W2)
    │   ├── 03_limpeza.py                    (W3)
    │   ├── 04_features.py                   (W3-W4)
    │   ├── 05_split.py                      (W4)
    │   ├── 06_baseline.py                   (W5)
    │   ├── 07_lightgbm.py                   (W5-W6)
    │   ├── 08_sobrevivencia.py              (W6 — Weibull AFT / Cox)
    │   ├── 09_evaluation.py                 (W7)
    │   ├── 10_isolation_forest.py           (W6 — 3ª abordagem não supervisionada)
    │   └── utils.py
    ├── dados/
    │   ├── intermediarios/                  (parquets pós-ingestão e limpeza — gitignored)
    │   └── features/                        (matriz pronta para modelo — gitignored)
    ├── modelos/                             (artifacts pickle/joblib — gitignored)
    └── relatorio/
        ├── figuras/                         (PNGs finais — 13 do guia + 3 extras)
        ├── tabelas/                         (CSVs: estatisticas, features, controle_alteracoes)
        ├── controle_alteracoes.md           (ANTES/DEPOIS de toda decisão metodológica)
        ├── hipoteses_eda.md                 (hipóteses levantadas na EDA)
        ├── rascunho.md                      (escrita progressiva W2→W8)
        └── relatorio_final.docx             (W9)
```

**Convenção:** todos os scripts dentro de `Projeto/codigo/` usam `Path(__file__).resolve().parents[1]` como raiz — ou seja, resolvem caminhos relativos a `Projeto/`. Por isso `Projeto/codigo/01_ingestao.py` lê de `Projeto/Alterado/...` e escreve em `Projeto/dados/...` sem hardcoded paths.

---

## 5. Cronograma resumo

| Semana | Datas | Foco | Marco |
|---|---|---|---|
| W1 | 13-19/05 | Setup + ingestão | |
| W2 | 20-26/05 | EDA visual | |
| W3 | 27/05-02/06 | Limpeza + features básicas | |
| W4 | 03-09/06 | Features avançadas + split | |
| W5 | 10-16/06 | Baseline + LightGBM v1 | **MARCO 1** |
| W6 | 17-23/06 | Tuning + Sobrevivência + SHAP + Ablation | |
| W7 | 24-30/06 | Análise + respostas Q3/Q6/Q7 | **MARCO 2** |
| W8 | 01-07/07 | Escrita do relatório | **MARCO 3** |
| W9 | 08-14/07 | Migração para template + revisão | |
| W10 | 15-20/07 | Buffer + entrega (enviar 18 ou 19/07) | |

**Carga média:** 10-12h/semana (W4-W6 com pico ~15h). Total estimado: ~122h (+10h vs. baseline por itens de profundidade: sensibilidade de janela, ablation, sobrevivência, e Isolation Forest como diagnóstico complementar não supervisionado; balanceamento comparativo removido em favor de `class_weight='balanced'` direto — trade de ~2h de documentação metodológica por ~5h de evidência empírica sobre o viés inerente do label).

---

## 6. Plano detalhado por semana

### W1 (13-19/05) — Setup + ingestão eficiente

**Objetivo:** ler todos os parquets com tipos corretos, sample pronto para iterar rápido.

- [X] Criar estrutura de pastas + `git init` + `pyproject.toml` + `.python-version`
- [X] Instalar `uv` e configurar `UV_HTTP_TIMEOUT`
- [X] Rodar `uv sync` (gerou `uv.lock` com 144 pacotes em `.venv/`)
- [X] Instalar VC++ Redistributable 2015-2022 (dep nativa do lightgbm no Windows)
- [X] Validar imports: polars 1.40.1 / pandas 2.3.3 / lightgbm 4.6.0 / shap 0.51.0 / lifelines 0.30.3
- [X] Configurar repositório privado no GitHub e fazer primeiro push (incluir `uv.lock`)
- [X] `Projeto/codigo/01_ingestao.py`: ler 6 telemetry_*.parquet + apontamentos.parquet com Polars
- [ ] Corrigir tipos: `Inicio_Turno`, `Fim_Turno`, `Valor` → datetime/float
- [ ] Normalizar `Criticidade` (caracteres corrompidos)
- [X] Salvar `Projeto/dados/intermediarios/telemetria_consolidado.parquet`
- [ ] Validar: 37.164.054 linhas, taxa DG ≈ 0,05%
- ~~Criar sample de 500k linhas para desenvolvimento rápido~~ — **DESCARTADO** (13/05/2026): os parquets mensais em `Projeto/Alterado/Base de Dados/datasets/telemetria/` (5-7M linhas, 33-43 MB cada) já servem ao duplo propósito de visualização (abrem no VSCode) e iteração rápida em scripts (~2s para carregar). Sample 500k adicional seria redundância sem ganho prático.
- [ ] **Verificação de duplicados** (CM 2.1): contar registros duplicados por dataset (apontamentos e telemetria), registrar quantidade e decisão de tratamento em `controle_alteracoes.md`
- [ ] **Frequência média de registros** (CM 2.1): calcular registros/dia, registros/hora e registros/equipamento (TAG) para apontamentos e telemetria → reportar no rascunho como característica do volume bruto
- [ ] **Tabela de estatísticas descritivas** (CM 2.1): para cada variável numérica gerar coluna/tipo/% nulos/min/max/média/mediana/desvio padrão → `Projeto/relatorio/tabelas/estatisticas_descritivas.csv`
- [ ] Inicializar `Projeto/relatorio/controle_alteracoes.md` com primeira decisão (filtragem Informacional, normalização Criticidade)

**Entregável:** parquet consolidado + script reproduzível + tabela estatísticas + controle_alteracoes iniciado.

---

### W2 (20-26/05) — EDA visual

**Objetivo:** todas as figuras de EDA prontas. Q4 e Q5 respondidas em rascunho. Hipóteses registradas.

**Figuras obrigatórias do Estudo Guiado (numeração segue o guia):**

- [ ] **Fig 1** — Diagrama do fluxo operacional: ciclo de apontamento → telemetria → alerta (CM 1.1)
- [ ] **Fig 2** — Distribuição temporal dos registros de apontamentos (volume por dia/hora) (CM 2.1)
- [ ] **Fig 3** — Distribuição de alertas por TIPO × NÍVEL de criticidade (CM 2.2)
- [ ] **Fig 4** — Série temporal: frequência de alertas DG ao longo do período (CM 2.2)
- [ ] **Fig 5** — Heatmap de correlação entre features numéricas (CM 2.3)
- [ ] **Fig 6** — Taxa de alertas por hora do dia e dia da semana (CM 2.3) → responde **Q5**

**Figuras extras (agregam valor — fazer se tempo permitir, senão vão para anexo):**

- [ ] Extra A — Sobrevivência empírica por frota: P(novo DG > t)
- [ ] **Extra B — Pareto top-10 alarmes precursores** *(promovido a obrigatório — alimenta diretamente a análise "o que a regra não vê" do W7, parte do diagnóstico K via Isolation Forest)*
- [ ] Extra C — Cadeia de eventos no caso CA65924 (do `desenvolver_dontgo.xlsx`)

**Outros entregáveis da semana:**

- [ ] Análise da distribuição por **Frota / Tipo / Classe** → responde **Q4**
- [ ] **Distribuição de alertas por TAG de equipamento** (Pareto/bar plot) — CM 2.2 pede explicitamente
- [ ] **Tabela `eventos_muito_alto.csv`** listando eventos da CMA com NIVEL "Muito Alto" (CM 1.1) — colunas: TIPO / EVENTO / SITUACAO / QTD / TEMPO / NIVEL
- [ ] Escrever em `Projeto/relatorio/rascunho.md` seção EDA + achados de Q4 e Q5
- [ ] **`Projeto/relatorio/hipoteses_eda.md`** — registrar TODAS as hipóteses levantadas (confirmadas e não confirmadas) com 1 parágrafo cada

**Entregável:** 6 figuras obrigatórias + extras desejáveis + hipoteses_eda.md + eventos_muito_alto.csv + rascunho EDA.

---

### W3 (27/05-02/06) — Limpeza + features básicas

**Objetivo:** matriz v1 com 10-15 features documentadas.

- [ ] `Projeto/codigo/03_limpeza.py`: tratar outliers em `Valor` (IQR + flag, manter linhas)
- [ ] **Estratégia de missing values por coluna** (CM 3.1): para cada coluna com nulos, decidir e justificar — remoção de linhas, imputação por mediana/moda, forward-fill (séries temporais) ou flag de ausência. Registrar tabela coluna×estratégia em `controle_alteracoes.md`
- [ ] Tratar registros com `Inicio > Fim` nos apontamentos
- [ ] **Detecção de sobreposições de ciclo** (CM 3.1): identificar registros onde ciclos do mesmo TAG se sobrepõem no tempo; reportar quantidade e decisão (manter / merge / descartar com justificativa)
- [ ] Filtrar `Criticidade = "Informacional"` (não tem positivos, economiza ~80% do volume)
- [ ] Tabela ANTES/DEPOIS em `Projeto/relatorio/tabelas/controle_alteracoes.csv` com **colunas exatas do CM 3.1**: Campo / Problema Identificado / Qtd. Registros / Tratamento Aplicado / Justificativa
- [ ] `Projeto/codigo/04_features.py` — features básicas:
  - [ ] `hora_dia`, `dia_semana`, `turno`, `mes`
  - [ ] **Encoding categórico documentado para as 5 categorias** (CM 3.2) — decisão por cardinalidade:
    - `Tag` (alta cardinalidade, ~centenas de equipamentos) → **target encoding** com smoothing + KFold para evitar leakage
    - `Frota` (média cardinalidade) → **target encoding**
    - `Tipo` (baixa cardinalidade, ~5-10 categorias) → **one-hot**
    - `Classe` (baixa-média cardinalidade) → **one-hot** ou **frequency encoding** conforme contagem distinta
    - `Operador` (alta cardinalidade, anonimizado) → **frequency encoding** + feature derivada `taxa_DG_operador_30d` (semântica útil sem one-hot explodindo dimensão)
  - [ ] Registrar a justificativa de cada escolha em `documentacao_features.csv` (coluna Motivação)
- [ ] Salvar `Projeto/dados/features/v1.parquet`
- [ ] Iniciar **`Projeto/relatorio/tabelas/documentacao_features.csv`** (CM 3.2): para cada feature criada — nome, descrição, fórmula/lógica, motivação/hipótese
- [ ] Registrar em `controle_alteracoes.md` decisões de limpeza (filtros, outliers, encoding)

**Entregável:** matriz v1 + tabela ANTES/DEPOIS + documentacao_features.csv iniciado.

---

### W4 (03-09/06) — Features avançadas + definição do target + split

**Objetivo:** matriz final v2 + datas de corte definidas + target documentado.

- [ ] Rolling windows por TAG: contagem de eventos por criticidade nas últimas 1h, 4h, 24h
- [ ] Features de recência: `horas_desde_ultimo_DG`, `horas_desde_ultimo_critico`
- [ ] Features de operador: `taxa_DG_operador_30d` → base para **Q3**
- [ ] Features de regra de negócio: `qtd_alarmes_nivel_muito_alto_360min`
- [ ] **Finalizar `documentacao_features.csv`** com fórmula+motivação de TODAS as features (CM 3.2 nota)
- [ ] Construir target: `y = 1` se houver evento DG na janela de +0 a +4h do equipamento (CM 3.3)
- [ ] **[Profundidade 1] Análise de sensibilidade da janela de predição** (~2h): gerar targets paralelos para janelas de **2h, 4h e 8h**; treinar LightGBM com parâmetros default em cada um e comparar AUC-PR/Recall no conjunto de validação. Tabela `sensibilidade_janela.csv` → justificar empiricamente a escolha de 4h em vez de só argumentar com motivos operacionais. Registrar conclusão em `controle_alteracoes.md`
- [ ] **Fig 7** — Diagrama da janela de predição: instante de decisão → janela 4h → evento alvo (CM 3.3)
- [ ] `Projeto/codigo/05_split.py` — split: treino jan-abr, val mai, teste jun
- [ ] **Fig 8** — Diagrama da estratégia de validação temporal (CM 4.1)
- [ ] Escrever justificativa explícita do porquê não usar k-fold aleatório (data leakage)
- [ ] Salvar `Projeto/dados/features/v2.parquet`
- [ ] Registrar decisões em `controle_alteracoes.md` (janela 4h, definição target, datas de corte)

**Entregável:** matriz v2 + documentacao_features.csv completa + Fig 7 + Fig 8.

---

### W5 (10-16/06) — Baseline + LightGBM v1 → MARCO 1

**Objetivo:** modelo principal funcionando, batendo o baseline.

- [ ] `Projeto/codigo/06_baseline.py` — heurística: DG=1 se houve crítico nas últimas 4h do mesmo TAG
- [ ] Métricas baseline no teste de jun: Precision, Recall, F1, AUC-PR
- [ ] `Projeto/codigo/07_lightgbm.py` — LightGBM v1 com `class_weight='balanced'`, parâmetros default
- [ ] **Documentar pré-processamento específico do baseline e do LightGBM** (CM 4.3): baseline usa só `Criticidade` e `TAG`; LightGBM usa matriz completa v2
- [ ] Comparar com baseline
- [ ] 🚦 **GATE MARCO 1: LightGBM bate baseline em AUC-PR?**
  - SIM → avança para W6
  - NÃO → pare. Reveja features antes de tunar parâmetros

**Entregável:** tabela comparativa baseline×LightGBM + modelos serializados em `Projeto/modelos/` + pré-processamento documentado.

---

### W6 (17-23/06) — Tuning + Sobrevivência + Isolation Forest + SHAP + Ablation

**Objetivo:** LightGBM otimizado + modelo de sobrevivência + diagnóstico não supervisionado (K) + interpretabilidade + ablation. Semana mais carregada do projeto (~15h).

- [ ] Optuna no LightGBM: 50 trials sobre validação (mai)
- [ ] LightGBM v2 com melhores parâmetros, avaliar no teste
- [ ] `Projeto/codigo/08_sobrevivencia.py` — **Modelo de Sobrevivência (Weibull AFT, fallback Cox PH)** com `lifelines`:
  - [ ] **Reformatar dados para análise de sobrevivência**: para cada equipamento (TAG), construir tuplas (T, E, X) onde T = tempo até o próximo DG (em horas), E = 1 se evento observado / 0 se censurado (fim da janela jan-jun sem DG), X = features no instante de referência
  - [ ] Treinar `WeibullAFTFitter` no treino (jan-abr), avaliar **C-index** em validação (mai) e teste (jun)
  - [ ] Se WeibullAFT não convergir ou C-index < 0.6 → fallback para `CoxPHFitter` (CM 4.3 nota: dois modelos bem feitos > cinco superficiais)
  - [ ] **Pré-processamento específico de sobrevivência** (CM 4.3): mesma matriz numérica v2, mas exclui features com colinearidade > 0.9 (Cox/Weibull são sensíveis); StandardScaler em features contínuas
  - [ ] Converter saída em probabilidade-em-4h: `P(T ≤ 4h | X)` → comparável com LightGBM em AUC-PR
  - [ ] **Interpretação via hazard ratios**: tabela top-10 features com HR e IC 95% — interpretação direta sem SHAP
- [ ] **Fig 9** — Curvas ROC + Precision-Recall comparando baseline × LightGBM × Sobrevivência (CM 5.1)
- [ ] **Fig 11** — SHAP summary plot do LightGBM (CM 5.3)
- [ ] **Fig 12** — SHAP waterfall de 1 predição individual (CM 5.3)
- [ ] **Validação de sentido das features** (CM 5.3): comparar top-10 do SHAP (LightGBM) com top-10 dos hazard ratios (sobrevivência) — concordância entre dois métodos independentes é evidência forte de validade
- [ ] **[Profundidade 2] Ablation por grupo de features** (~3h): retreinar o LightGBM v2 (parâmetros fixos do Optuna) removendo cada família e medir queda de AUC-PR no teste. Grupos:
  - (G1) Temporais (`hora_dia`, `dia_semana`, `turno`, `mes`)
  - (G2) Rolling windows 1h/4h/24h
  - (G3) Recência (`horas_desde_ultimo_DG`, `horas_desde_ultimo_critico`)
  - (G4) Operador (`taxa_DG_operador_30d`, `Operador_freq`)
  - (G5) Regra de negócio (`qtd_alarmes_nivel_muito_alto_360min`)
  - (G6) Categóricas codificadas (`Tag`, `Frota`, `Tipo`, `Classe`)
  - Tabela `ablation_grupos.csv` com ΔAUC-PR e ΔRecall por grupo. **Fig Extra E** — gráfico de barras. Vira insight de produto (qual sinal carrega o modelo)
- [ ] **[Qualidade A] Calibração do modelo escolhido**: calibration plot + Brier score → Fig Extra D. Se descalibrado, aplicar Platt scaling
- [ ] **[K — Isolation Forest, 3ª abordagem não supervisionada] (~3h)**: `Projeto/codigo/10_isolation_forest.py`
  - [ ] Treinar `IsolationForest(n_estimators=200, contamination=0.001)` em jan-abr **sem usar `Is_Dont_Go`** (matriz v2 — mesma feature engineering dos outros modelos)
  - [ ] Scoring em validação (mai) e teste (jun); converter anomaly score em ranking
  - [ ] AUC-PR e **Recall@K** (top 1%, 5%, 10%) usando `Is_Dont_Go` apenas como ground truth de validação (CM 4.3 — abordagem "label de anomalia")
  - [ ] **Critério de abort (hora 1)**: se IF não rodar em tempo viável (> 1h em matriz v2 completa) ou Recall@10% < baseline aleatório, abandonar e registrar tentativa em `controle_alteracoes.md` — sem custo afundado significativo
  - [ ] Enquadrar no relatório como **diagnóstico complementar**, NÃO modelo competidor — tabela à parte, não entra na ROC/PR principal junto a LightGBM/Sobrevivência (comparação seria enviesada)
  - [ ] Salvar `Projeto/modelos/isolation_forest.joblib` + `Projeto/relatorio/tabelas/if_diagnostico.csv`
- [ ] Registrar em `controle_alteracoes.md` escolha de hiperparâmetros, modelo vencedor (LightGBM ou Sobrevivência), decisão de calibração, e resultado do IF (convergiu / aborted)

**Entregável:** 3 modelos supervisionados/sobrevivência (baseline + LightGBM + Sobrevivência) + Isolation Forest como diagnóstico complementar + Fig 9, Fig 11, Fig 12 + ablation_grupos.csv + calibração + tabela de hazard ratios + tabela IF (AUC-PR / Recall@K).

---

### W7 (24-30/06) — Análise final + respostas Q3/Q6/Q7 → MARCO 2

**Objetivo:** pipeline analítico fechado. A partir daqui só escrita.

- [ ] `Projeto/codigo/09_evaluation.py`:
  - [ ] **Fig 10** — Matriz de confusão do modelo escolhido com anotações de impacto operacional (CM 5.2)
  - [ ] Análise dos falsos negativos: que TAGs/frotas/operadores escapam?
  - [ ] **[Qualidade C] Análise de erro estratificada**: matriz de confusão e métricas por **frota** e por **tipo** (Caminhão vs. Escavadeira) — modelo não pode falhar mais em uma frota
  - [ ] Drift mensal: AUC-PR mês a mês no teste
  - [ ] Tabela custo-benefício: FN × FP × limiar ótimo
- [ ] **Fig 13** — Comparação visual de performance: baseline vs. modelos desenvolvidos (CM 6.1)
- [ ] **Q3:** análise da feature `taxa_DG_operador_30d` via SHAP
- [ ] **Q6:** definir faixas de probabilidade → ações (continuar/preventiva/parar)
- [ ] **Q7:** ranking priorizado de inspeção por turno (top 5 TAGs)
- [ ] Tradução de Recall/Precision em horas de parada evitada e custo monetário estimado
- [ ] **[Qualidade B] Distribuição do tempo de antecipação**: P25 / mediana / P75 / P95 — não só média. Histograma do tempo entre predição positiva e DG real
- [ ] **[Qualidade E] Sanity check do viés inerente**: discussão honesta de que `Is_Dont_Go` é gerado pelas regras CMA, então o modelo aprende a antecipar a regra (não a falha física real). **Agora reforçado empiricamente pelo Isolation Forest do W6** — não é só retórica
- [ ] **[K — análise "o que a regra não vê"] (~2h)**: a partir dos resultados do IF no teste (jun):
  - [ ] Selecionar top-100 TAG×timestamp com maior anomaly score que **não** dispararam `Is_Dont_Go`
  - [ ] Examinar eventos/criticidades nas 4h seguintes — há concentração de níveis Alto/Muito Alto acima da base?
  - [ ] Cruzar com TAGs/frotas — algum grupo específico aparece desproporcionalmente?
  - [ ] **Fig Extra F** — barplot top-N TAGs anômalos × prevalência de eventos não cobertos pela regra
  - [ ] Conclusão honesta em 1 parágrafo: o sinal não supervisionado **complementa** (encontra modos de falha além da regra), **dispensa** (recupera os mesmos DGs sem ver rótulo), ou apenas **duplica** o sinal da regra?
- [ ] **Insights não óbvios** (CM 6.1): seção específica em rascunho com 3-5 achados surpreendentes ou contra-intuitivos da análise
- [ ] Atualizar `rascunho.md` com seção Avaliação e Resultados
- [ ] Registrar em `controle_alteracoes.md` escolha do limiar de operação

**Entregável:** todas as 6 perguntas respondidas + Fig 10 + Fig 13 + Fig Extra F + análise estratificada + distribuição de antecipação + análise "o que a regra não vê" + seção de insights.

---

### W8 (01-07/07) — Escrita do relatório → MARCO 3

**Objetivo:** rascunho completo em markdown.

- [ ] Introdução (1-2 pp)
- [ ] Entendimento do Negócio (2-3 pp) — incluir obrigatoriamente:
  - [ ] **Cenário de aplicação operacional concreto** (CM 1.2): descrever como o modelo entra no fluxo da operação — ex: "score recalculado a cada início de turno, top-N TAGs com probabilidade > limiar aparecem no painel do dispatcher de Itabira com 4h de antecedência, gerando ordem de inspeção para a manutenção". Definir cadência, consumidor (dispatcher / manutenção / planejamento), e ação esperada
- [ ] Metodologia (8-10 pp) — EDA + Preparação + Modelagem
- [ ] Resultados e Discussões (5-7 pp) — Avaliação + respostas Q1-Q7
- [ ] **Limitações (seção própria, ~0,5-1 p)** (CM 6.2) — discussão honesta e explícita: volume coberto (6 meses, jan-jun/2025), região única (Itabira), features ausentes (manutenção preventiva, clima, sensores de vibração), generalização para outras frotas/regiões, viés inerente do `Is_Dont_Go`. **A inclusão do Isolation Forest não supervisionado (W6/W7) endereça parcialmente esse viés ao mostrar empiricamente quanto da estrutura dos DGs é recuperável sem ver o rótulo — limitação fica discutida com evidência, não só com retórica.**
- [ ] Conclusão (1 p) + Trabalhos Futuros (1 p) — **mínimo 3 propostas concretas e justificadas** (CM 6.3):
  - [ ] Q2 (modelo multi-classe para tipo do alerta)
  - [ ] Integração de dados externos (manutenção preventiva, condições climáticas)
  - [ ] Modelo online com retraining mensal para combater drift detectado em W7
  - [ ] **Autoencoder LSTM** sobre série temporal bruta de telemetria — extensão natural do Isolation Forest já entregue, mas com estrutura temporal explícita; requer GPU não disponível neste ciclo
  - [ ] **Validação prospectiva com dados de manutenção corretiva**: usar registros de intervenção física (não disponíveis no escopo atual) para validar se as anomalias detectadas pelo IF correspondem a falhas reais, fechando o ciclo do diagnóstico complementar
- [ ] **Resumo (500 palavras) — escrever por último**
- [ ] Revisar todas as figuras: legendas, eixos, fontes grandes para .docx

**Entregável:** `rascunho.md` ~25 páginas equivalentes.

---

### W9 (08-14/07) — Migração para template + revisão

**Objetivo:** versão `.docx` final pronta.

- [ ] Migrar markdown → `Projeto/Alterado/Desenvolver_Template.docx`
- [ ] Inserir figuras com legenda numerada
- [ ] Formatar tabelas
- [ ] 2 leituras críticas (manhã + tarde de dias diferentes)
- [ ] Checklist dos 6 CMs cobertos
- [ ] Anexos: dicionário de features + tabela ANTES/DEPOIS
- [ ] Validar referências bibliográficas

**Entregável:** `Projeto/relatorio/relatorio_final.docx`.

---

### W10 (15-20/07) — Buffer + entrega

**Objetivo:** enviar entre 18-19/07 (não deixar para 20/07).

- [ ] Última revisão completa (1 dia de leitura corrida)
- [ ] Empacotar: relatório.docx + código.zip + README
- [ ] Backup OneDrive/Drive antes de enviar
- [ ] Enviar para `projetodesenvolver@vale.com`
- [ ] Salvar confirmação de envio

**Entregável:** e-mail enviado.

---

## 7. Marcos e gates

| Marco | Quando | Critério de passagem |
|---|---|---|
| **MARCO 1** | Fim W5 (16/06) | LightGBM bate o baseline em AUC-PR no teste |
| **MARCO 2** | Fim W7 (30/06) | Pipeline analítico fechado; respostas Q1-Q7 prontas |
| **MARCO 3** | Fim W8 (07/07) | Rascunho completo em markdown |

Se algum gate falhar: **pare, diagnostique, ajuste plano antes de avançar.**

---

## 8. Controle de Alterações (prática contínua)

O Estudo Guiado exige (Nota da página 1):
> *"Sempre que uma alteração, exclusão ou decisão metodológica relevante for tomada, registre o ANTES e o DEPOIS com a justificativa correspondente."*

Por isso, **`Projeto/relatorio/controle_alteracoes.md`** é alimentado durante TODO o projeto (não só na limpeza). Toda vez que uma decisão metodológica for tomada — janela de predição, definição do target, filtro de classe, escolha de modelo, limiar — registrar com o template:

```markdown
### [Data] — [Tema da decisão]
- **ANTES:** estado anterior / opção descartada
- **DEPOIS:** estado novo / opção escolhida
- **Justificativa:** por que mudou
- **Impacto:** o que isso afeta (volume, métrica, escopo)
```

Exemplos do que entra:
- W1: filtro de `Criticidade = Informacional` (perde 80% do volume mas zero positivos)
- W3: critério de outlier (IQR vs. ±3σ)
- W3: estratégia de imputação por coluna
- W4: definição da janela de predição (por que 4h, não 8h)
- W4: datas de corte do split
- W5: escolha do modelo baseline
- W6: hiperparâmetros vencedores do Optuna
- W7: limiar de probabilidade adotado

Esse arquivo é **anexo do relatório final** e mostra rastro analítico — diferencial em banca.

---

## 9. Plano B — cortes em caso de atraso

Cortar na ordem abaixo (do menos crítico para o mais crítico):

1. ✂️ **[Profundidade 1]** Sensibilidade de janela → manter só 4h argumentada operacionalmente
2. ✂️ **[Qualidade A]** Calibração → mencionar que "modelo requer Platt scaling em produção" (cortar **apenas** se Q6 puder operar com probabilidade bruta — verificar antes)
3. ✂️ **[Qualidade C]** Análise estratificada por frota → vira "limitação reconhecida"
4. ✂️ **[Profundidade 2]** Ablation por grupo de features → manter só importância via SHAP
5. ✂️ **[Qualidade B]** Distribuição do tempo de antecipação → fica só com média
6. ✂️ **[K — análise]** Encurtar "o que a regra não vê" para tabela top-10 sem investigação por TAG/frota (mantém treino IF + AUC-PR/Recall@K; perde só a profundidade analítica do W7)
7. ✂️ **[Profundidade 3]** Modelo de Sobrevivência → "abordagem alternativa discutida em Trabalhos Futuros" (custo de saída em W6 ~6h)
8. ✂️ **[K — completo]** Isolation Forest inteiro → vai para Trabalhos Futuros (cortar só se W6 estourar e o abort de hora 1 não tiver sido acionado; perde-se a evidência empírica do viés inerente)
9. ✂️ Walk-forward mensal → manter só split fixo jan-abr/mai/jun
10. ✂️ Análise de operador (Q3) → vira "limitação reconhecida"

**Não cortar nunca:**
- EDA com 6 figuras obrigatórias
- LightGBM com tuning
- SHAP
- Validação temporal
- Conclusão com impacto em horas de parada evitada
- Sanity check do viés inerente (custa só escrita, agrega muito)
- Insights não óbvios (CM 6.1 explicita)
- Cenário de aplicação concreto (CM 1.2)
- Seção de Limitações explícita (CM 6.2)
- Pelo menos a **tentativa documentada** do Isolation Forest (mesmo se aborted, o registro em `controle_alteracoes.md` mostra exploração metodológica)

---

## 10. Bitácora semanal

Toda **sexta-feira, 15 minutos**, preencher abaixo.

### Semana 1 (13-19/05)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 2 (20-26/05)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 3 (27/05-02/06)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 4 (03-09/06)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 5 (10-16/06) — MARCO 1
- Entregável feito? [ ]
- LightGBM bateu baseline em AUC-PR? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 6 (17-23/06)
- Entregável feito? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 7 (24-30/06) — MARCO 2
- Entregável feito? [ ]
- Todas as 6 perguntas respondidas? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 8 (01-07/07) — MARCO 3
- Rascunho completo? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 9 (08-14/07)
- .docx pronto? [ ]
- Bloqueador:
- Ajuste W+1:
- Horas reais investidas:

### Semana 10 (15-20/07)
- E-mail enviado? [ ] Data: ___/___/2026
- Confirmação salva? [ ]
- Horas reais investidas:
