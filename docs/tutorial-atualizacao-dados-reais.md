# Tutorial de atualização com dados reais

Este procedimento é o roteiro para reutilizar o projeto com dados reais e
reprocessar toda a árvore de vínculos.

## Pré-requisitos

- Python 3.8+
- Node.js 20+
- `resultados/grafo_resultado.sqlite` pode ser sobrescrito durante a recarga
- Delimitador dos CSVs: `;` (ponto e vírgula)
- Codificação: UTF-8

Arquivos obrigatórios:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

## 1) Montar pasta do lote real

Prepare uma pasta fora do repositório (idealmente com timestamp):

```bash
LOTE_DIR=/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
```

> Use os nomes exatos acima. Se o fornecedor entregar nomes diferentes,
> normalize para estes nomes antes do processamento.

## 2) Validar lote antes de carregar na árvore

Validação mínima dos 4 arquivos (headers, separador, leitura):

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Se falhar, corrija o lote e repita a validação.

## 3) Reprocessar tudo (recomendado)

Esse fluxo cria backup automático de `dados/` e `resultados/`, substitui os
4 CSVs de entrada, processa e faz build da interface.

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

### Opções úteis do fluxo

- `--skip-validation`: pula validação de entrada no script.
- `--skip-build`: processa sem `npm run build` (mais rápido).

Exemplos:

```bash
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"
```

## 4) Reprocessar sem trocar pasta de entrada

Se os arquivos já estiverem em `dados/`, use:

```bash
python3 scripts/reprocessar_dados_reais.py --check-only
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild

# sem rebuild:
python3 scripts/reprocessar_dados_reais.py --process --clean
```

Alias equivalentes:

```bash
npm run check:data        # validação rápida
npm run refresh:data      # valida + limpa + processa + build
```

## 5) Validar resultado da árvore

### 5.1 contagem das saídas principais

```bash
python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for tabela in [
    "entidades",
    "vinculos",
    "grupos",
    "membros_grupo",
    "relacoes_entre_grupos",
    "fila_revisao",
]:
    print(f"{tabela:24} {conn.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0]}")
conn.close()
PY
```

### 5.2 revisão inicial de alertas

```bash
sed -n '1,180p' resultados/fila_revisao.csv
sed -n '1,140p' resultados/relatorio_analise.md
```

### 5.3 saúde da API

```bash
npm run backend
# em outra aba
curl http://127.0.0.1:8000/api/health
```

## 6) Reprocessar a visualização

```bash
npm run backend       # terminal 1
npm run dev           # terminal 2
```

Na tela, escolha a entidade e expanda os níveis conforme necessário.

## 7) Rollback de segurança

Backups ficam em `backups/reprocessamento_AAAA...`. Para restaurar:

```bash
TS=YYYYMMDD_HHMMSS
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
npm run refresh:data
```

## 8) Boas práticas obrigatórias

- Não versionar CSVs reais ou arquivos de saída com dados sensíveis.
- Guardar lote original fora do repositório com identificador e timestamp.
- Sempre revisar `resultados/fila_revisao.csv` antes de liberar homologação.
- Manter backup antes de cada recarga.
