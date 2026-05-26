# Análise Avançada de Dados — Programa Desenvolver 2026

Desafio: **Antecipação de Alertas Críticos (Don't Go) em Frotas de Mineração** (Vale, região de Itabira).

**Participante:** Marcelo Ayala
**Entrega:** 20/07/2026
**Repositório:** privado

---

## Onde começar

👉 **[PLANEJAMENTO.md](PLANEJAMENTO.md)** — escopo, cronograma W1-W10, marcos e bitácora semanal.

## Estrutura

A raiz do repositório contém apenas arquivos de configuração e documentação. Todo o conteúdo de trabalho (código, dados, modelos, relatório) está em **`Projeto/`**.

```
AnaliseDadosVale/                          ← raiz do repo Git
├── pyproject.toml, uv.lock, .python-version, .gitignore    (config)
├── README.md, PLANEJAMENTO.md             (docs)
├── Original/                              (backup intocado)
└── Projeto/                               ← código + dados + entregáveis
    ├── Alterado/                          (dados de trabalho)
    ├── codigo/                            (scripts numerados 01→10)
    ├── dados/intermediarios/              (parquets pós-ingestão — gitignored)
    ├── dados/features/                    (matriz para modelo — gitignored)
    ├── modelos/                           (artifacts — gitignored)
    └── relatorio/                         (figuras, tabelas, relatório final)
```

| Pasta | Conteúdo | Versionado no Git? |
|---|---|---|
| `Projeto/Alterado/` | Dados brutos (intocados) — telemetria, apontamentos, regras de negócio | ✅ Sim |
| `Original/` | Backup dos dados originais | ✅ Sim |
| `Projeto/codigo/` | Scripts Python numerados por ordem de execução | ✅ Sim |
| `Projeto/dados/intermediarios/` | Parquets pós-ingestão e limpeza | ❌ Não (reproduzível) |
| `Projeto/dados/features/` | Matrizes de features para os modelos | ❌ Não (reproduzível) |
| `Projeto/modelos/` | Artifacts dos modelos treinados | ❌ Não (reproduzível) |
| `Projeto/relatorio/figuras/` | PNGs finais para o relatório | ✅ Sim (entrega) |
| `Projeto/relatorio/tabelas/` | CSVs finais para o relatório | ✅ Sim (entrega) |
| `Projeto/relatorio/rascunho.md` | Escrita progressiva W2→W8 | ✅ Sim |
| `Projeto/relatorio/relatorio_final.docx` | Entrega final (W9) | ✅ Sim |

---

## Setup em uma máquina nova (passo a passo)

### Pré-requisitos

- **Git** instalado
- **Python NÃO precisa estar instalado** — o `uv` baixa Python 3.13 automaticamente
- **Windows:** Microsoft Visual C++ Redistributable (passo 2 abaixo)

### Passo 1 — Instalar uv

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verificar:
```powershell
uv --version
```

Esperado: `uv 0.11.x` ou superior.

### Passo 2 — (Windows apenas) Microsoft Visual C++ Redistributable

Necessário para o `lightgbm` carregar suas DLLs nativas (OpenMP, runtime C++).

```powershell
Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile "$env:TEMP\vc_redist.x64.exe"
Start-Process "$env:TEMP\vc_redist.x64.exe" -ArgumentList "/install /quiet /norestart" -Wait
Remove-Item "$env:TEMP\vc_redist.x64.exe"
```

Não precisa reiniciar o computador.

### Passo 3 — (Conexão lenta) Aumentar timeout do uv

Default do uv é 30s por arquivo. Em conexão lenta (< 1 MB/s), pacotes grandes como `polars_runtime` (52 MB) timeout. Configura 5 minutos:

```powershell
[Environment]::SetEnvironmentVariable("UV_HTTP_TIMEOUT", "300", "User")
```

**Feche e reabra o terminal** para a variável fazer efeito.

### Passo 4 — Clonar e sincronizar dependências

```powershell
git clone <url-do-repo>
cd AnaliseDadosVale
uv sync
```

O comando `uv sync` vai:
- Baixar Python 3.13 (se não tiver) — gerenciado pelo uv, não afeta seu Python do sistema
- Resolver as 144 dependências do `uv.lock` (versões exatas)
- Criar `.venv/` local com tudo instalado

Tempo esperado: **3-6 minutos** dependendo da conexão.

### Passo 5 — Validar ambiente

```powershell
uv run python -c "import polars, pandas, lightgbm, shap, lifelines, optuna, numba; print('OK -', polars.__version__, pandas.__version__, lightgbm.__version__, shap.__version__, lifelines.__version__)"
```

Esperado:
```
OK - 1.40.1 2.3.3 4.6.0 0.51.0 0.30.3
```

Se erro de DLL no `lightgbm`: voltar ao Passo 2 e instalar VC++ Redistributable.

### Passo 6 — Reconstruir dados intermediários

Os parquets consolidados **não estão no Git** (gitignored porque pesam ~200 MB e são reproduzíveis). Para reconstruir a partir dos dados brutos:

```powershell
uv run python Projeto/codigo/01_ingestao.py
```

Tempo: ~35 segundos. Cria `Projeto/dados/intermediarios/telemetria_consolidado.parquet`.

### Passo 7 — Rodar os próximos scripts em ordem

**Pipeline principal (rodar em ordem):**
```powershell
uv run python Projeto/codigo/01_ingestao.py             # W1 - ingestão + consolida 6 parquets mensais → telemetria_consolidado.parquet (37,16M linhas)
uv run python Projeto/codigo/02_correcao_tipos.py       # W1 - corrige tipos (datetime, float BR com vírgula decimal) → telemetria_tipada.parquet
uv run python Projeto/codigo/03_limpeza.py              # W1+W3 - limpeza completa em 12 etapas (filtro Informacional, outliers, missings, sobreposições) → telemetria_limpa.parquet (544.885 linhas) + apontamentos_limpo.parquet + controle_alteracoes.csv
uv run python Projeto/codigo/04_eda.py                  # W2 - EDA visual (7 figuras fig02-fig06 + figExB + figExG) + tabela Q4 (dgs_por_frota_tipo_classe.csv)
uv run python Projeto/codigo/05_features.py             # W3+W4+W5 - 7 famílias de features (35 cols, com Família 1 expandida em W5 para 5 janelas 1h/2h/4h/8h/24h) + 3 targets (target_2h/4h/8h) → v1.parquet (5 básicas) + v2_parcial.parquet (25, 21,6 MB) + v2.parquet (35 + 3 targets, 24,4 MB, 57 cols) + documentacao_features.csv (CM 3.2, 35 entradas) + sensibilidade_janela.csv
uv run python Projeto/codigo/06_split.py                # W4 - split temporal walk-forward jan-abr / mai / jun + Fig 7 (janela predição) + Fig 8 (drift mensal) → v2_split.parquet (58 cols, 16,3 MB) + split_temporal.csv (CM 4.1)
uv run python Projeto/codigo/06b_fix_encoding_leakage.py # W5 - fix do leakage subtil de frequency encoding (tag_freq, operador_freq recomputadas sobre treino apenas; categorias unknown recebem freq=0) → v3.parquet (58 cols, 16,3 MB, input canônico para modelagem)
uv run python Projeto/codigo/07_baseline.py             # W5 - baseline heurístico para target_4h (count_critico_4h >= threshold) com métricas estratificadas mai vs jun (Mitigação 3) → baseline_metricas.csv (8 linhas: 4 thresholds × 2 splits)
uv run python Projeto/codigo/08_lightgbm.py             # W5 - LightGBM v1 (5 variantes A/B/C/T2/T8) com parâmetros default → 5 modelos em modelos/lightgbm_v1_*.txt + 4 tabelas (métricas, vs baseline, horizontes, GATE). GATE MARCO 1: PASS. Tempo: ~17,5s
uv run python Projeto/codigo/08b_lightgbm_v2.py         # W6 - LightGBM v2 (modelo intermediário diagnóstico, ex-canônico): Optuna 50 trials + TimeSeriesSplit CV 4 folds + deterministic=True → lightgbm_v2.txt + optuna_study_v2.pkl + 3 tabelas. AUC-PR val=0,7801 / test=0,8618. SHAP revelou cascade prediction, motivando v3. Tempo: ~28,7 min
uv run python Projeto/codigo/08c_shap_v2.py             # W6 - Análise SHAP do v2 (diagnóstica) via TreeSHAP sobre 71.089 eventos → matriz shap_values_v2_test.npy (19 MB) + 2 tabelas + 3 figuras (9a/9b/10). Top 3 features: horas_desde_ultimo_DG (39%) / qtd_alarmes_muito_alto (31%) / razao_alarme_7d_vs_30d (8,6%). **Achado crítico:** mini-diagnose revelou que feature #1 é cascade detector (motivou v3). Tempo: ~1 min
uv run python Projeto/codigo/08e_lightgbm_v2_no_cascade.py # W6 - **LightGBM v3 (canônico promovido em 24/05)** sem horas_desde_ultimo_DG (34 features). AUC-PR test=0,8556 (−0,62pp vs v2) mas Recall@0.5 geral +7,24pp e primeiro DG +16,72pp (5× mais primeiros DGs capturados). Trial #41 best, scale_pos_weight=2,40. → lightgbm_v2_no_cascade.txt + 3 tabelas (inclui v2_vs_v2_no_cascade.csv decisória). Tempo: ~25,7 min
uv run python Projeto/codigo/08f_shap_v3.py             # W6 - Análise SHAP do v3 canônico via TreeSHAP. Top 3: qtd_alarmes_muito_alto (41%) / tipo_caminhao (24%) / razao_alarme_7d_vs_30d (11%) — todas antecipativas (modelo NÃO é mais cascade detector). horas_desde_ultimo_critico não herdou papel (rank #11, 1,1%). → shap_values_v3_test.npy (18 MB) + 2 tabelas + 3 figuras (9c/9d/10b). Requer PYTHONIOENCODING=utf-8 no Windows. Tempo: ~1,7 min
uv run python Projeto/codigo/09_sobrevivencia.py        # W6 - **Modelo de Sobrevivência Weibull AFT (segundo modelo canônico)** com fallback automático Cox PH. Constrói (T, E) por evento via join_asof forward por TAG; filtro correlação >0,9 (remove 6 features Família 1); imputação NaN para razao_*/taxa/horas_critico. **Resultados:** C-index test=0,7444 / AUC-PR(4h) test=0,3153. **Top TRs:** tipo_caminhao 0,038 (caminhão sobrevida 3% escavadeira), frota_793D_5S 0,169, tag_freq 1,432. **Concordância forte com SHAP v3** (CM 5.3 validação cruzada). → sobrevivencia.joblib (14,5 MB) + 3 tabelas + Fig Extra A (Kaplan-Meier por frota). Requer PYTHONIOENCODING=utf-8 no Windows. Tempo: ~56 s
uv run python Projeto/codigo/11_isolation_forest.py     # W6 - **Isolation Forest diagnóstico do Risco 3.3 (viés do label CMA)**. Treinado NÃO-SUPERVISIONADO (sem Is_Dont_Go), 200 árvores, 34 features alinhadas ao v3. **Achados em 3 camadas:** (i) AUC-ROC por split assimétrico (train=0,58 / val=0,60 / test=0,86); (ii) CA65926 sozinho AUC=0,897 vs resto AUC=0,541; (iii) **análise estrutural por TAG: AUC mediana=0,6060, apenas 3 TAGs com sinal forte E sample significativo (CA65926, CA65932, CA65924). CA65924 (paradigma de W4) validado pelo IF sem usar o rótulo.** **Veredito:** Risco 3.3 PARCIALMENTE MITIGADO — CMA captura anomalias em poucos equipamentos mas é aleatório em >88% das TAGs. **Implicação (L10 em CM 6.2):** performance alta do v3 em test dirigida por poucos equipamentos. **Convergência:** SHAP v3, Weibull AFT, IF chegam à mesma conclusão (CM 6.1). → isolation_forest.joblib (0,58 MB) + 5 tabelas (inclui `if_auc_por_tag.csv`) + Fig Extra D (4 painéis, com barras por TAG). Requer PYTHONIOENCODING=utf-8 no Windows. Tempo: ~9,2 s
uv run python Projeto/codigo/12_validacao_sentido_features.py # W6 (fechamento) - **Validação cruzada SHAP × Hazard Ratios (CM 5.3)**. Cruza top features do v3 (SHAP) com top TRs do Weibull AFT. **4 features no top 10 de AMBOS** (estruturais): tipo_caminhao, tag_freq, frota_793D_4S, frota_793D_5S. Divergências instrutivas: SHAP destaca antecipativas, Weibull destaca base rate (os dois modelos respondem perguntas diferentes — CM 6.1). → validacao_sentido_features.csv. Tempo: < 5 s
uv run python Projeto/codigo/13_curvas_comparativas.py  # W6 (fechamento) - **Fig 9 — Curvas ROC + PR comparativas (CM 5.1)**. Compara baseline / v3 / Weibull AFT no test. **AUC-PR test:** baseline=0,5803, **v3=0,8556**, Weibull=0,3148. v3 domina em AUC-PR (+27,5pp vs baseline, +54pp vs Weibull). → fig09_curvas_comparativas.png (2 painéis) + comparacao_modelos_test.csv. Tempo: ~30 s
uv run python Projeto/codigo/14_calibracao_v3.py        # W6 (fechamento) - **Calibração do v3 + Platt scaling (Qualidade A, CM 5.2)**. v3 raw: Brier test=0,05745 (skill +0,59), ECE=3,78pp. **Platt scaling melhora val (3,70→1,87pp) MAS piora test (3,78→4,76pp)** — drift de calibração val→test (nota adicional em L4). **Recomendação: NÃO aplicar Platt em deployment**, manter v3 raw. → calibracao_v3.csv + figExF_calibracao_v3.png (2 painéis) + calibrador_v3_platt.joblib (flag "não usar"). Tempo: ~15 s
uv run python Projeto/codigo/15_ablation_grupos.py      # W6 (fechamento) - **Ablation por grupo de features (Profundidade 2, CM 6.1)**. Retreina v3 com hiperparams FIXOS removendo cada um de 7 grupos. **Achado surpreendente:** nenhum grupo é estritamente necessário (variação máxima ±0,01 AUC-PR). Apenas G7 regimal causa queda real (−0,0044). G4 operador e G6 categóricas MELHORAM (+0,0064). **Insight metodológico:** SHAP mede atribuição, ablation mede necessidade — diferença = redundância. v3 prediz por múltiplas rotas redundantes. **Implicação operacional (CM 6.3):** v3 robusto a perda de features em deployment. → ablation_grupos.csv + figExE_ablation_grupos.png. Tempo: ~110 s
# ... 10_evaluation (W7)
```

**Scripts auxiliares (investigações ad-hoc, rodam independentemente):**
```powershell
uv run python Projeto/codigo/exploracao_w2_obs.py             # W2 - investiga obs 2.1, 2.2, 2.5, 2.6, 2.7 (impressões no terminal)
uv run python Projeto/codigo/exploracao_w3_sobreposicoes.py   # W3 - investiga 340 sobreposições → bug pontual no CA65789 (H1.4)
uv run python Projeto/codigo/exploracao_w4_ca65924.py         # W4 - investiga H5.2 / Obs 2.3 → Fig Extra C (figExC_ca65924_cadeia.png) — refuta padrão "calmaria → acúmulo" universal; gera Obs 2.11 (sub-hipótese de acúmulo de criticidade)
uv run python Projeto/codigo/exploracao_w5_obs_pendentes.py   # W5 - resolve Obs 2.4 (operador OP_067 não é outlier — Q3 respondida com sinal difuso) e Obs 2.9 (anomalia RFB jun é falha localizada do CA65926 — 98,5%) → obs24_taxa_dg_por_operador.csv + obs29_rfb_junho_decomposicao.csv
uv run python Projeto/codigo/extrai_eventos_muito_alto.py     # W2 - extrai eventos_muito_alto.csv (CM 1.1, 82 regras CMA Muito Alto)
```

A ordem dos scripts principais segue a numeração (01_ → 11_). Detalhe completo dos scripts, semana de implementação, saídas e tempo estimado em [`Projeto/relatorio/rascunho.md`](Projeto/relatorio/rascunho.md) (Anexo A — Reprodutibilidade).

---

## Comandos do dia a dia

```powershell
# Rodar qualquer script (usa o .venv automaticamente, sem precisar ativar)
uv run python Projeto/codigo/01_ingestao.py

# Adicionar pacote novo (atualiza pyproject.toml + uv.lock automaticamente)
uv add ruff

# Atualizar uma dependência específica
uv lock --upgrade-package polars

# Reinstalar tudo do zero (raro)
Remove-Item -Recurse -Force .venv
uv sync
```

Os scripts em `Projeto/codigo/` resolvem caminhos relativamente a `Projeto/` (não à raiz do repo) usando `Path(__file__).resolve().parents[1]`. Por isso eles funcionam independentemente de onde você está rodando o comando.

---

## Sincronização entre máquinas via GitHub

**Antes de sair da máquina atual:**
```powershell
git add .
git commit -m "checkpoint: <o que terminou>"
git push
```

**Na máquina nova:**
```powershell
git clone <repo-url>
cd AnaliseDadosVale
uv sync                                              # instala ambiente exato via uv.lock
uv run python Projeto/codigo/01_ingestao.py          # regera Projeto/dados/intermediarios/
```

Pronto — ambiente idêntico bit-a-bit graças ao `uv.lock`.

---

## Troubleshooting

### `Could not find module ... lib_lightgbm.dll`
**Causa:** VC++ Redistributable ausente no Windows.
**Fix:** Passo 2 acima.

### `uv sync` falha com timeout
**Causa:** Conexão lenta + pacote grande.
**Fix:** Aumentar timeout e tentar de novo:
```powershell
$env:UV_HTTP_TIMEOUT = "600"
uv sync
```

### `Cannot install on Python version 3.13.12; only versions >=3.6,<3.10 are supported`
**Causa:** Resolver pegou `llvmlite` antigo (já corrigido no `pyproject.toml` com pin de `numba>=0.60`).
**Fix:** Forçar refresh do cache:
```powershell
uv sync --refresh
```

### Quero rodar Jupyter / VSCode com este ambiente
**No VSCode:**
1. Abrir o projeto
2. `Ctrl+Shift+P` → "Python: Select Interpreter"
3. Selecionar `.venv/Scripts/python.exe`

**No terminal (Jupyter):**
```powershell
uv run jupyter lab
```

---

## Documentos de referência

- `Projeto/Alterado/Estudo Guiado - Análise Avançada de Dados.pdf` — critérios e conteúdos mínimos
- `Projeto/Alterado/Desenvolver_Template.docx` — template do relatório final
- `Projeto/Alterado/Base de Dados/Dicionario_Dados.xlsx` — dicionário de colunas
- `Projeto/Alterado/Base de Dados/Alarmes - Regra de Negocio.xlsx` — regras CMA
- [PLANEJAMENTO.md](PLANEJAMENTO.md) — plano de execução completo W1-W10
