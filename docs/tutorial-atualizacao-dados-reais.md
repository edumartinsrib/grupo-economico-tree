# Tutorial de atualização com dados reais

Este roteiro é o procedimento para reutilizar o projeto com dados reais e
reprocessar toda a árvore de vínculos de uma vez (entidades, vínculos, grupos,
exposição e relações de revisão).

> Objetivo: substituir o lote de entrada e gerar novamente o grafo completo sem
> alterar código.

## Pré-requisitos

- Python 3.8+
- Node.js 20+
- `resultados/grafo_resultado.sqlite` pode ser sobrescrito durante a recarga
- CSVs em UTF-8, delimitador `;` (ponto e vírgula)
- Espaço em disco para backup temporário (pelo menos 500MB para lotes grandes)

## 1) Arquivos obrigatórios

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

## 2) Montar a pasta do lote real

Crie uma pasta de entrega (idealmente com timestamp), com os **nomes exatos** acima:

```bash
LOTE_DIR=/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
```

## 3) Validar lote antes de carregar

Valida apenas presença dos 4 arquivos e colunas mínimas esperadas.

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

## 4) Reprocessar tudo (recomendado)

Fluxo recomendado para produção/homologação:

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Esse fluxo faz:

1. validação da pasta de entrada;
2. backup automático de `dados/` e `resultados/`;
3. cópia dos 4 CSVs para `dados/`;
4. limpeza de saídas antigas;
5. processamento completo (`scripts/construir_rede_grupos.py`);
6. build do frontend (para disponibilizar a UI atualizada).

## 5) Opções úteis do fluxo principal

- `--skip-validation`: pula validação de entrada;
- `--skip-build`: processa sem `npm run build` (mais rápido para testes);
- `--help`: mostra ajuda.

Exemplos:

```bash
scripts/reprocessar_arvore_reais.sh --skip-validation /tmp/entrega_real
scripts/reprocessar_arvore_reais.sh --skip-build /tmp/entrega_real
```

## 6) Reprocessar sem trocar pasta de entrada

Se você já copiou os arquivos para `dados/`, pode reprocessar diretamente dali:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild

# sem rebuild:
python3 scripts/reprocessar_dados_reais.py --process --clean
```

Atalho via `npm`:

```bash
npm run refresh:data      # valida + limpa + processa + build
npm run process:real -- /tmp/entrega_real
```

## 7) Validar saídas do processamento

### 7.1 Tabelas no SQLite

```bash
python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{t:24} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY
```

### 7.2 Alertas e relatório

```bash
awk 'NR<=140 {print}' resultados/relatorio_analise.md
awk 'NR<=180 {print}' resultados/fila_revisao.csv
```

### 7.3 Validação da API

```bash
npm run backend
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/metadata
```

Resposta esperada de saúde:  
`{"status":"ok","db_status":"available"}`

## 8) Rodar a árvore atualizada

```bash
npm run backend   # terminal 1
npm run dev       # terminal 2
```

No frontend, localize a entidade de entrada e use a expansão por nível para
acompanhar a nova árvore construída.

## 9) Rollback de segurança

O fluxo automático já gera:

- `backups/reprocessamento_AAAA_MMDD_HHMMSS/dados`
- `backups/reprocessamento_AAAA_MMDD_HHMMSS/resultados`

Para reverter:

```bash
TS=YYYYMMDD_HHMMSS
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 10) Checklists operacionais obrigatórios

- Não versionar dados reais em `dados/` e `resultados/`.
- Manter o backup de entrada/saída a cada recarga.
- Revisar `resultados/fila_revisao.csv` antes de homologação.
- Não pular a validação no primeiro ciclo de um lote novo.

## 11) Erros mais comuns

- Falha de coluna obrigatória: conferir nomes no cabeçalho.
- Processo lento: rodar com `--skip-build` até validar os dados e só depois fazer
  build.
- API sem nova árvore: conferir que `resultados/grafo_resultado.sqlite` foi
  recriado e que o backend foi reiniciado (ou subir novo processo).
- Erro de path em produção: executar sempre no diretório raiz do projeto.
