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

```powershell
uv run python Projeto/codigo/02_correcao_tipos.py    # próximo no pipeline
uv run python Projeto/codigo/03_limpeza.py
uv run python Projeto/codigo/04_eda.py
# ... seguir numeração até 11_isolation_forest.py (planejados em W3-W7)
```

A ordem dos scripts segue a numeração (01_ → 11_). Detalhe completo dos scripts, semana de implementação e saídas em [`Projeto/relatorio/rascunho.md`](Projeto/relatorio/rascunho.md) (Anexo A — Reprodutibilidade).

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
