# Atualização com dados reais e reprocessamento completo da árvore

Este projeto já está preparado para reutilizar bases reais.  
Este fluxo reconstrói **toda** a rede e os 6 grupos/ tabelas em `resultados/`.

## 1) O que você precisa antes de começar

- Python 3 e Node + npm instalados.
- Acesso de escrita em `dados/`, `resultados/`, `backups/`.
- Backend da API funcional (`npm run backend`) para visualização.
- Quatro arquivos de entrada com `;` como delimitador e UTF-8:
  - `stg_pessoa_fisica_atual_202606191707.csv`
  - `denodo_base_cadastral.csv`
  - `stg_cadastro_socio_pj_202606191707.csv`
  - `mv_movimentacoes.csv`

## 2) Preparar lote real (recomendado)

Monte uma pasta separada para não misturar entregas.

```bash
TS="$(date +%Y%m%d_%H%M%S)"
LOTE_DIR="/tmp/entrega_real_${TS}"
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
cd "$LOTE_DIR"
sha256sum *.csv > checksums.sha256
```

> Se o caminho de origem for SFTP/compartilhado, copie primeiro o lote para local e só depois valide.

## 3) Validar entrada (obrigatório)

Validação mínima de arquivo/colunas antes de qualquer processamento:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Também é possível validar apenas `dados/` atual:

```bash
python3 scripts/reprocessar_dados_reais.py --check-only
```

## 4) Reprocessar a árvore inteira com backup (fluxo recomendado)

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Esse comando executa, em ordem:

1. Backup de `dados/` e `resultados/` em `backups/reprocessamento_<TIMESTAMP>/`.
2. Validação do lote (a menos que `--skip-validation`).
3. Cópia dos 4 arquivos para `dados/`.
4. Geração completa da rede via `python3 scripts/construir_rede_grupos.py`.
5. Atualização dos CSVs de saída e `resultados/grafo_resultado.sqlite`.
6. `npm run build` (frontend) por padrão, salvo `--skip-build`.

Comando alternativo curto (via npm):

```bash
npm run process:real -- "$LOTE_DIR"
```

## 5) Opções úteis

```bash
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"      # atualiza dados, sem rebuild
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR" # pular validação (só se já validado)
```

Ou modo explícito da CLI:

```bash
python3 scripts/reprocessar_dados_reais.py \
  --input-dir "$LOTE_DIR" \
  --process \
  --clean \
  --rebuild \
  --print-stats
```

## 6) Reprocessar usando `dados/` sem novo lote

Se os 4 CSVs já foram copiados manualmente para `dados/`:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 7) Validar o resultado do recálculo

### 7.1 Conferência técnica do banco

```bash
python3 - <<'PY'
import sqlite3, json
from pathlib import Path

path = Path("resultados/grafo_resultado.sqlite")
print(f"Arquivo: {path}")
print(f"MB: {path.stat().st_size / 1024 / 1024:.2f}")

conn = sqlite3.connect(path)
tables = ["entidades","vinculos","grupos","membros_grupo","relacoes_entre_grupos","fila_revisao"]
print(json.dumps({t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}, ensure_ascii=False, indent=2))
conn.close()
PY
```

### 7.2 Conferência da API

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/metadata
curl -s "http://127.0.0.1:8000/api/tree/family/1?max_per_node=8"
```

## 8) Resultado que deve existir em `resultados/`

- `entidades.csv`
- `vinculos.csv`
- `grupos.csv`
- `membros_grupo.csv`
- `relacoes_entre_grupos.csv`
- `fila_revisao.csv`
- `agregacoes_financeiras_grupos.csv`
- `relatorio_analise.md`
- `grafo_resultado.sqlite`

## 9) Visualizar a árvore após atualização

```bash
npm run backend   # porta 8000
npm run dev       # interface em modo desenvolvimento
```

Abra a busca, escolha uma pessoa/empresa e use:

- **Expandir para cima**: mostra nós ancestrais/parentais.
- **Expandir para baixo**: mostra filhos e conexões novas.
- Área do grafo com arraste (pan) para navegar em árvores grandes.

## 10) Rollback de segurança

Em caso de problema, restaure o backup mais recente listado em `backups/`:

```bash
TS=20260622_120000
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --process --clean
```

## 11) Boas práticas de operação real

- Não versionar dados reais de produção em `dados/` e `resultados/`.
- Manter lote/backup com timestamp e checksum.
- Revisar `resultados/fila_revisao.csv` antes de homologar.
- Manter lote de produção e homologação em pastas distintas.
- Tratar divergências de estrutura antes de `--skip-validation`.
