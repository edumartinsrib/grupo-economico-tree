# Atualização com dados reais e reprocessamento da árvore

Este projeto consome as 6 tabelas/resultados para alimentar a visualização e permite
reprocessar a rede completa com novo lote real.

O fluxo abaixo gera:
- `resultados/entidades.csv`
- `resultados/vinculos.csv`
- `resultados/grupos.csv`
- `resultados/membros_grupo.csv`
- `resultados/relacoes_entre_grupos.csv`
- `resultados/fila_revisao.csv`
- `resultados/agregacoes_financeiras_grupos.csv`
- `resultados/relatorio_analise.md`
- `resultados/grafo_resultado.sqlite`

## 1) Pré-requisitos

- Python 3 e npm instalados.
- Permissão de escrita em `dados/`, `resultados/`, `backups/`.
- Backend/API funcionando (`npm run backend`) para validação final.
- Quatro arquivos de entrada em UTF-8 e com `;` como delimitador:
  - `stg_pessoa_fisica_atual_202606191707.csv`
  - `denodo_base_cadastral.csv`
  - `stg_cadastro_socio_pj_202606191707.csv`
  - `mv_movimentacoes.csv`

## 2) Preparar lote real (recomendado)

Monte uma pasta temporária por carga para evitar sobrescrever entradas históricas:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
LOTE_DIR="/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"

cd "$LOTE_DIR"
sha256sum *.csv > checksums.sha256
```

> Se o lote chegar via compartilhamento de rede, copie primeiro para local e depois valide.

## 3) Validar entrada

Valide os arquivos antes de processar (obrigatório no primeiro ciclo):

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Também funciona para dados já copiados em `dados/`:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --check-only
```

## 4) Reprocessar a árvore inteira (com backup)

Fluxo principal (recomendado):

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Ou atalho via npm:

```bash
npm run process:real -- "$LOTE_DIR"
```

Esse fluxo executa, em ordem:

1. Backup automático de `dados/` e `resultados/` em `backups/reprocessamento_<TIMESTAMP>/`.
2. Validação do lote.
3. Copia dos quatro CSVs para `dados/`.
4. Geração de toda a rede com `scripts/construir_rede_grupos.py`.
5. Atualização de todas as saídas em `resultados/`.
6. `npm run build` (salvo `--skip-build`).

## 5) Opções úteis

```bash
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR" # pula validação (somente se já validado)
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"       # sem rebuild do frontend
```

Ou comando explícito equivalente:

```bash
python3 scripts/reprocessar_dados_reais.py \
  --input-dir "$LOTE_DIR" \
  --process \
  --clean \
  --rebuild \
  --print-stats
```

## 6) Reprocessar usando `dados/` já existentes

Quando as 4 entradas já estiverem em `dados/`:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 7) Conferir saída e consistência

### Checagem do banco

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 - <<'PY'
import sqlite3
from pathlib import Path

db = Path("resultados/grafo_resultado.sqlite")
print(f"DB: {db} ({db.stat().st_size / 1024 / 1024:.2f} MB)")

conn = sqlite3.connect(db)
stats = {}
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
print(stats)
conn.close()
PY
```

### Checagem da API

```bash
curl -s http://127.0.0.1:8000/api/health | jq
curl -s http://127.0.0.1:8000/api/metadata | jq
```

Para validar uma árvore:

```bash
# troque 00000000101 pelo entidade_id real de uma entidade
curl -s "http://127.0.0.1:8000/api/tree/context/SEU_ENTIDADE_ID?max_per_node=8" | jq '.root_id,.summary'
```

## 8) Rodar visualização

```bash
npm run backend  # API em http://127.0.0.1:8000
npm run dev      # interface em modo desenvolvimento
```

A busca vai abrir uma nova raiz e a árvore crescerá em níveis (acima/abaixo) com
expansão por perna e arraste para navegação.

## 9) Rollback seguro

Se a carga não estiver aceitável, restaure o backup mais recente:

```bash
TS=20260622_120000   # troque pela pasta de backup desejada
cp -r "backups/reprocessamento_${TS}/dados/"* dados/
cp -r "backups/reprocessamento_${TS}/resultados/"* resultados/
```

## 10) Segurança e operação

- Não versionar dados reais de produção (nem `dados/`, nem `resultados/`).
- Mantenha lote e `checksums.sha256` por ciclo de processamento.
- Nunca use `--skip-validation` por padrão.
- Revise `resultados/fila_revisao.csv` antes de homologar.
