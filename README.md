# Análise Avançada de Dados — Programa Desenvolver 2026

Desafio: **Antecipação de Alertas Críticos (Don't Go) em Frotas de Mineração** (Vale, região de Itabira).

**Participante:** Marcelo Ayala
**Entrega:** 20/07/2026

---

## Onde começar

👉 **[PLANEJAMENTO.md](PLANEJAMENTO.md)** — escopo, cronograma, marcos e bitácora semanal.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `Alterado/` | Dados de trabalho (intocados) — telemetria, apontamentos, regras de negócio |
| `Original/` | Cópia de backup dos dados originais |
| `codigo/` | Scripts Python (numerados por ordem de execução) |
| `dados/` | Parquets intermediários e matriz de features |
| `modelos/` | Modelos treinados (LightGBM, Isolation Forest) |
| `relatorio/` | Figuras, tabelas, rascunho e relatório final |

## Reproduzindo o trabalho

```bash
pip install -r requirements.txt
python codigo/01_ingestao.py
# ... seguir ordem numérica
```

## Documentos de referência

- `Alterado/Estudo Guiado - Análise Avançada de Dados.pdf` — critérios e conteúdos mínimos
- `Alterado/Desenvolver_Template.docx` — template do relatório final
- `Alterado/Base de Dados/Dicionario_Dados.xlsx` — dicionário de colunas
- `Alterado/Base de Dados/Alarmes - Regra de Negocio.xlsx` — regras CMA
