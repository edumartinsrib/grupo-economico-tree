# Reutilizando com dados reais

Este projeto foi pensado para trabalhar com os 4 arquivos de origem abaixo.
Use este fluxo para **atualizar o lote de dados** e **reprocessar a árvore inteira** antes de abrir a visualização.

Saídas geradas a cada reprocessamento:

- `resultados/entidades.csv`
- `resultados/vinculos.csv`
- `resultados/grupos.csv`
- `resultados/membros_grupo.csv`
- `resultados/relacoes_entre_grupos.csv`
- `resultados/fila_revisao.csv`
- `resultados/agregacoes_financeiras_grupos.csv`
- `resultados/relatorio_analise.md`
- `resultados/grafo_resultado.sqlite`

## 1) Arquivos exigidos

Cada lote deve conter:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

Formato esperado:

- UTF-8
- Separador `;`
- Um CPF/CNPJ por linha nas colunas de documento (quando existir)

## 2) Montar pasta de lote

Use uma pasta por carga para manter trilha e rollback.

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
LOTE_DIR="/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOTE_DIR"

# Exemplo de cópia do lote
cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"

cd "$LOTE_DIR"
sha256sum *.csv > checksums.sha256
```

Se vier por compartilhamento de rede, copie para local antes de validar.

## 3) Validar lote antes de processar (recomendado)

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Interrompa aqui se houver erro de cabeçalho ou arquivo ausente.

## 4) Reprocessar toda a árvore

Com backup automático e rebuild:

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Ou atalho npm:

```bash
npm run process:real -- "$LOTE_DIR"
```

Esse passo faz:

1. Backup de `dados/` e `resultados/` em `backups/reprocessamento_<TIMESTAMP>/`
2. Validação dos arquivos do lote
3. Cópia dos 4 CSVs para `dados/`
4. Execução do processador (`scripts/construir_rede_grupos.py`)
5. Geração/atualização dos CSVs em `resultados/`
6. `npm run build` (gera frontend atualizado)

## 5) Reprocessar com opções

```bash
# sem validação (use só se já validou)
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"

# sem build do frontend (mais rápido para testes técnicos)
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"

# equivalente direto no python
python3 scripts/reprocessar_dados_reais.py \
  --input-dir "$LOTE_DIR" \
  --process \
  --clean \
  --rebuild \
  --print-stats
```

## 6) Reprocessar usando `dados/` já carregados

Quando os 4 CSVs já estiverem em `dados/`, rode:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 7) Conferir saúde e consistência

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --check-only

curl -s http://127.0.0.1:8000/api/health | jq
curl -s http://127.0.0.1:8000/api/metadata | jq

python3 - <<'PY'
import sqlite3
from pathlib import Path

db = Path("resultados/grafo_resultado.sqlite")
print(f"DB: {db} ({db.stat().st_size / 1024 / 1024:.2f} MB)")
with sqlite3.connect(db) as conn:
    for table in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
        print(f"{table:30}: {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
PY
```

## 8) Visualizar

```bash
npm run backend  # API: http://127.0.0.1:8000
npm run dev      # Front: http://127.0.0.1:5173
```

Abra uma entidade pela busca e use:
- expansão para cima/baixo por "pernas"
- arraste no painel da árvore para navegar por grandes volumes
- detalhe de nó para validar vínculo/alertas

## 9) Rollback

Se o resultado não ficar bom, restaure o backup mais recente:

```bash
TS=20260622_120000   # ajuste para pasta real do backup
cp -r "backups/reprocessamento_${TS}/dados/"* dados/
cp -r "backups/reprocessamento_${TS}/resultados/"* resultados/
```

## 10) Boas práticas de operação

- `dados/` e `resultados/` podem conter carga real: não compartilhe fora do ambiente seguro.
- Mantenha `checksums.sha256` junto do lote.
- Não use `--skip-validation` no fluxo padrão.
- Revise sempre `resultados/fila_revisao.csv` antes de homologar.
- Inicie com `max_per_node` baixo no frontend para não “estourar” tela com lotes grandes.
