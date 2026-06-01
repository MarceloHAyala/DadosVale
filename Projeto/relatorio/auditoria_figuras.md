# Auditoria de Figuras — 2026-05-27 (W6 → W7)

Auditoria completa das figuras do projeto, classificadas em **Negócio** (gerente entende em 5s), **Técnica** (anexo técnico, analista) ou **Reserva** (movida para subpasta `figuras/reserva/`, pode ter uso depois).

**Decisão geral aplicada:** nenhuma figura é descartada. Candidatas a remoção foram movidas para `Projeto/relatorio/figuras/reserva/` e podem ser reaproveitadas se surgir contexto novo.

**Atualização 27/05 (segunda rodada):** 3 figuras de NEGÓCIO criadas + Fig 9 regenerada + Fig 4 ajustada + Fig 5 movida para reserva + seção "Resultados — leitura para o time de negócio e operacional" inserida no rascunho com promoção das figs ExA e ExG para o corpo principal.

---

## Sumário executivo

| Categoria | Quantidade | Figuras |
|---|---:|---|
| **Negócio** (alto impacto, narrativa principal) | 12 | 1, 3, 4, 6, 8, 9, **Neg01, Neg02, Neg03**, ExA, ExB, ExG |
| **Técnica** (anexo, rigor metodológico) | 7 | 2, 7, 9c, 9d, ExC, ExD, ExE, ExF |
| **Reserva** (movida para `/reserva/`) | 5 | 9a, 9b, 10, 10b, **5** |
| **Total** | 24 | — (1 a mais que antes, dado que somamos 3 figs novas e movemos 1) |

**Mudanças aplicadas em 27/05:**

1. ✅ **Fig 5 (heatmap correlação) movida para `/reserva/`** — redundante com Fig 9c (SHAP bar v3 do canônico).
2. ✅ **Fig 9 (curvas comparativas) REGENERADA** com `figsize=(16, 7)`, `dpi=150`, acentos completos, linhas mais grossas. Texto agora claramente legível.
3. ✅ **Fig 4 (série temporal de DGs) AJUSTADA** — removido "Obs 2.6" do título (jargão interno), adicionada anotação visual em vermelho destacando a explosão de junho com explicação direta (CA65926 falha mecânica progressiva), acentos completos, dpi=150.
4. ✅ **3 figuras de NEGÓCIO criadas** (alto impacto operacional):
   - `figNeg01_timeline_ca65926.png` — Deterioração progressiva do CA65926 (jan-jun, janela de antecipação de 3 meses)
   - `figNeg02_ranking_risco_operacional.png` — Ranking dos 33 equipamentos do parque com ação recomendada (ALTO/MÉDIO/BAIXO)
   - `figNeg03_horas_parada_evitavel.png` — Tradução das métricas em valor operacional (10.480h–43.582h evitáveis, 3 cenários com premissas declaradas)
5. ✅ **Fig ExA e ExG promovidas** para a nova seção "Resultados — leitura para o time de negócio e operacional" no `rascunho.md` (antes só eram referenciadas no anexo de sobrevivência e Q4 da EDA).

**Problemas transversais ainda em aberto:**

- Acentos faltando em ~10 figuras técnicas (todas as do ciclo W2 EDA exceto Fig 4 que foi regenerada; também as figs SHAP do v2 que estão em /reserva/). Para o relatório final em W8, recomendado regenerar essas figuras com strings com acento se forem usadas no corpo principal. Para as que ficaram em anexo técnico, opcional.

---

## Detalhamento por figura

### 1️⃣ Negócio (12 figuras)

#### Figura 1 — Fluxo operacional ✨ **ATUALIZADA (27/05)**
- **Arquivo:** `fig01_fluxo_de_apontamentos.png`
- **Estado:** Excelente após correção. Cabeçalho honesto ("fluxo reconstruído a partir do dicionário... bloco G é a proposta deste estudo"), separação visual clara entre descritivo (A-F) e prescritivo (G, verde tracejado), legenda de cores no canto.

#### Figura 3 — Tipo × Criticidade
- **Arquivo:** `fig03_tipo_x_criticidade.png`
- **Acentos:** ainda em ASCII. Em aberto para regeneração se for usar no corpo do relatório final.

#### Figura 4 — Série temporal de DGs ✨ **REGENERADA (27/05)**
- **Arquivo:** `fig04_serie_temporal_dgs.png`
- **Mudanças:** título limpo ("Série temporal de DGs jan-jun/2025" — sem "Obs 2.6"); anotação visual em vermelho destacando explosão de junho ("82% dos DGs do mês vêm de UM equipamento (CA65926) — falha mecânica progressiva"); acentos completos; dpi=150.

#### Figura 6 — Heatmap hora × dia (Q5)
- **Arquivo:** `fig06_heatmap_hora_dia.png`
- **Pendente (baixa prioridade):** mudar título para incluir a conclusão ("variação 2-6% sem padrão sistemático").

#### Figura 8 — Split temporal + drift
- **Arquivo:** `fig08_split_temporal.png`
- **Pendente (baixa prioridade):** acentos no eixo (`Estrategia`, `validacao`).

#### Figura 9 — Curvas ROC + PR comparativas ✨ **REGENERADA (27/05)**
- **Arquivo:** `fig09_curvas_comparativas.png`
- **Mudanças:** `figsize=(16, 7)` (era 15×6), `dpi=150` (era 130), linhas com `linewidth=2.5`, todos os textos em PT-BR com acento (Aleatório, Precisão, Verdadeiros Positivos, Prevalência), legenda com `framealpha=0.95`.

#### 🆕 Figura Neg01 — Timeline CA65926 ⭐ **NOVA (27/05)**
- **Arquivo:** `figNeg01_timeline_ca65926.png`
- **Script:** `Projeto/codigo/figneg_01_timeline_ca65926.py`
- **O que comunica:** Deterioração progressiva do CA65926. Painel (a) — DGs por mês empilhados (RFB vs outros alarmes) com anotação do sinal precursor de março (438 DGs, taxa 20,28%, **3 meses antes da crise**) e da crise de junho (4.298 DGs via RFB). Painel (b) — taxa mensal de DG com linha de referência da taxa global do parque (3,66%) mostrando que março já estava **5× acima do parque**.
- **Função no relatório:** primeira figura da seção "Resultados — leitura para o time de negócio e operacional". Justifica a recomendação de **monitoramento estratificado por equipamento**.

#### 🆕 Figura Neg02 — Ranking de risco operacional ⭐ **NOVA (27/05)**
- **Arquivo:** `figNeg02_ranking_risco_operacional.png`
- **Script:** `Projeto/codigo/figneg_02_ranking_risco.py`
- **O que comunica:** 33 equipamentos do parque ranqueados por volume de DGs + taxa, com 3 níveis de risco (ALTO/MÉDIO/BAIXO) e ação recomendada por equipamento. **5 ALTO / 18 MÉDIO / 10 BAIXO.**
- **Função:** traduz a heterogeneidade do parque em decisão operacional concreta. Foca onde a auditoria deve agir.
- **Saída adicional:** `relatorio/tabelas/ranking_risco_operacional.csv` (tabela completa).

#### 🆕 Figura Neg03 — Horas de parada evitável ⭐ **NOVA (27/05)**
- **Arquivo:** `figNeg03_horas_parada_evitavel.png`
- **Script:** `Projeto/codigo/figneg_03_horas_evitaveis.py`
- **O que comunica:** tradução das métricas técnicas (Recall, AUC-PR) em horas-equipamento de parada não planejada evitáveis. **3 cenários com premissas declaradas:** Conservador (10.480h), Realista (37.429h), Otimista (43.582h).
- **Honestidade:** premissas (4h de parada corretiva, 1,5h preventiva) declaradas explicitamente. Cenários documentam fontes.
- **Saída adicional:** `relatorio/tabelas/horas_evitaveis_cenarios.csv`.

#### Figura Extra A — Kaplan-Meier por frota ⭐ **PROMOVIDA (27/05)** para Resultados
- **Arquivo:** `figExA_kaplan_meier_por_frota.png`
- **Mudança:** antes só era referenciada no anexo de sobrevivência (Weibull AFT). Agora também aparece na seção "Resultados — leitura para o time de negócio".

#### Figura Extra B — Pareto top-10 alarmes
- **Arquivo:** `figExB_pareto_alarmes.png`
- **Pendente (baixa prioridade):** acentos no eixo.

#### Figura Extra G — Pareto top-15 TAGs ⭐ **PROMOVIDA (27/05)** para Resultados
- **Arquivo:** `figExG_pareto_tags.png`
- **Mudança:** antes só era referenciada no anexo de Q4. Agora também aparece na seção "Resultados — leitura para o time de negócio" (concentração dos DGs em poucos equipamentos).

---

### 2️⃣ Técnica — anexo técnico (8 figuras)

#### Figura 2 — Distribuição temporal apontamentos
- **Arquivo:** `fig02_distribuicao_temporal_apontamentos.png`
- **Função:** Sanidade — confirma cobertura temporal estável. Anexo.

#### Figura 7 — Janela de predição
- **Arquivo:** `fig07_janela_predicao.png`
- **Função:** Explica visualmente o conceito de `target_4h`. Anexo metodológico.

#### Figura 9c — SHAP bar v3 (canônico)
- **Arquivo:** `fig09c_shap_bar_v3.png`
- **Função:** Top features do v3 final. Anexo técnico (CM 5.3).

#### Figura 9d — SHAP beeswarm v3
- **Arquivo:** `fig09d_shap_beeswarm_v3.png`
- **Função:** Direção do efeito. Anexo técnico (CM 5.3).

#### Figura Extra C — Cadeia CA65924
- **Arquivo:** `figExC_ca65924_cadeia.png`
- **Função:** Validação empírica W4 da H5.2. Anexo.

#### Figura Extra D — Isolation Forest (4 painéis)
- **Arquivo:** `figExD_isolation_forest_diagnostico.png`
- **Função:** Diagnóstico do Risco 3.3. Anexo técnico (CM 6.2).

#### Figura Extra E — Ablation por grupo
- **Arquivo:** `figExE_ablation_grupos.png`
- **Função:** Robustez do modelo. Anexo técnico (CM 6.1).

#### Figura Extra F — Calibração v3
- **Arquivo:** `figExF_calibracao_v3.png`
- **Função:** Honestidade metodológica (Brier + ECE + Platt rejeitado). Anexo (CM 5.2).

---

### 3️⃣ Reserva — movidas para `figuras/reserva/` (5 figuras)

Pasta `Projeto/relatorio/figuras/reserva/`. Nenhuma figura foi deletada. Podem ser reaproveitadas se surgir contexto novo.

| Figura | Razão para reserva |
|---|---|
| `fig05_heatmap_correlacao.png` | Redundante com Fig 9c (SHAP bar v3). Movida em 27/05 a pedido do usuário. |
| `fig09a_shap_bar.png` | SHAP do v2 (modelo intermediário descontinuado pela promoção do v3). |
| `fig09b_shap_beeswarm.png` | Mesma razão + redundância com 9d. |
| `fig10_shap_dependence_top3.png` | Dependence plots v2, vertical pequeno, inclui feature que não está mais no v3. |
| `fig10b_shap_dependence_top3_v3.png` | Dependence plots v3, vertical pequeno + `tipo_caminhao` binário não comunica em dependence plot. |

---

## Scripts criados/atualizados em 27/05

| Script | Função |
|---|---|
| `Projeto/codigo/13_curvas_comparativas.py` | Regenerada Fig 9 (figsize 16×7, dpi 150, acentos) |
| `Projeto/codigo/_regen_fig4.py` | Wrapper standalone para regenerar Fig 4 sem rodar EDA completa |
| `Projeto/codigo/04_eda.py` (função `fig4_serie_temporal_dgs`) | Editada com anotação CA65926 + acentos |
| `Projeto/codigo/figneg_01_timeline_ca65926.py` | NOVA — Fig Neg01 |
| `Projeto/codigo/figneg_02_ranking_risco.py` | NOVA — Fig Neg02 + tabela ranking_risco_operacional.csv |
| `Projeto/codigo/figneg_03_horas_evitaveis.py` | NOVA — Fig Neg03 + tabela horas_evitaveis_cenarios.csv |

---

## Próximos passos sugeridos (W7-W8)

Em ordem de prioridade:

1. **Acertar acentos das figuras técnicas restantes** se forem usadas no corpo do relatório final (W8). Para as que ficarem só em anexo, opcional.
2. **Validar a Fig Neg03 (horas evitáveis) com o time operacional da Vale** — as premissas de 4h corretiva / 1,5h preventiva são estimativas razoáveis, mas o time operacional pode ter números mais precisos.
3. **(Opcional) Adicionar SHAP waterfall** (Fig 12 do plano) de uma predição específica do CA65926, mostrando como o modelo chegou ao score alto — fortalece a narrativa de interpretabilidade individual. ~30 min.

---

**Última atualização:** 2026-05-27 (segunda rodada de auditoria — 3 figs de negócio criadas, Fig 9 regenerada, Fig 4 ajustada com anotação CA65926, Fig 5 para /reserva/, ExA e ExG promovidas para Resultados)
