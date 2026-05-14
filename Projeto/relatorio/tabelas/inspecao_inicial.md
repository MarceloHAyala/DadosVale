# Inspecao Inicial dos Dados (CM 2.1)

Gerado por `Projeto/codigo/03_limpeza.py`. Consolida normalizacao da Criticidade,
verificacao de duplicados, frequencia de registros e taxa de Is_Dont_Go.

## 1. Normalizacao de Criticidade

Valores brutos encontrados antes da normalizacao:

| Valor original | Quantidade |
|---|---|
| `Informacional` | 36,619,169 |
| `Não Crítico` | 461,854 |
| `Critico` | 83,020 |
| `N??o Crítico` | 6 |
| `Não Cr??tico` | 5 |

Apos normalizacao todos os valores foram mapeados para: `Critico`, `Nao_Critico`, `Informacional`.

## 2. Duplicados

Verificacao feita pela chave primaria de cada dataset (dedup full-row em 37M
linhas e prohibitivo e nao agrega valor — linhas inteiramente identicas sao
praticamente impossiveis em telemetria por causa dos timestamps).

### Telemetria
- Total: **37,164,054**
- Chaves unicas em ['Id_Eventos_Telemetria']: **37,164,054**
- Duplicadas por chave: **0** (0.0000%)

### Apontamentos
- Total: **377,907**
- Chaves unicas em ['Id']: **377,907**
- Duplicadas por chave: **0** (0.0000%)

## 3. Frequencia media de registros

### Telemetria
- Total: **37,164,054** registros
- Dias cobertos: **180**
- Equipamentos (TAGs): **35**
- Registros/dia: **206,467**
- Registros/hora: **8,603**
- Registros/TAG/dia: **5,899**

### Apontamentos
- Total: **377,907** registros
- Dias cobertos: **181**
- Equipamentos (TAGs): **47**
- Registros/dia: **2,088**
- Registros/hora: **87**
- Registros/TAG/dia: **44**

## 4. Taxa Is_Dont_Go

- Total: **37,164,054**
- Don't Go (positivos): **19,962**
- Taxa: **0.0537%** (range esperado: 0.03% - 0.10%)
