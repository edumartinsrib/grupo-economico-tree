# Reutilização com dados reais

Este tutorial padroniza como substituir a base de exemplo por dados reais e reprocessar
toda a árvore de vínculos do projeto.

## Objetivo

- **Atualizar os 4 CSVs de entrada** com nova entrega real.
- **Validar o lote** antes de sobrescrever o ambiente.
- **Reprocessar a rede completa** (entidades, vínculos, grupos e relações).
- **Disponibilizar a nova árvore** no frontend sem necessidade de edição manual de dados.

## 0) Estrutura atual do projeto

- `dados/` → entrada do processador (4 arquivos esperados)
- `resultados/` → saídas usadas pelo frontend/API
- `scripts/reprocessar_dados_reais.py` → validação + orquestração do processamento
- `scripts/reprocessar_arvore_reais.sh` → fluxo operacional completo (com backup)
- `scripts/construir_rede_grupos.py` → motor principal de geração da árvore
- `server/main.py` → API que lê `resultados/grafo_resultado.sqlite`

## 1) Preparar pasta de lote

Crie uma pasta por carga para rastreabilidade e rollback:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
LOTE_DIR="/tmp/lote_real_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOTE_DIR"
```

Copie os arquivos abaixo para `"$LOTE_DIR"` com nome exato:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

Exemplo:

```bash
cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"

cd "$LOTE_DIR"
sha256sum stg_pessoa_fisica_atual_202606191707.csv denodo_base_cadastral.csv \
  stg_cadastro_socio_pj_202606191707.csv mv_movimentacoes.csv > checksums.sha256
```

Observação: os arquivos devem ser CSV UTF-8 com `;` como separador.

## 2) Validar lote (obrigatório)

Antes de trocar o ambiente atual, valide estrutura e cabeçalhos:

```bash
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Saída esperada:

- `OK: arquivo (N registros)` para cada arquivo.
- Se faltar coluna obrigatória, o comando encerra com erro.
- Se faltar coluna recomendada, segue com alerta de observação.

## 3) Reprocessar toda a árvore

Com validação aprovada, execute:

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

ou:

```bash
npm run process:real -- "$LOTE_DIR"
```

Esse fluxo faz:

1. backup automático de `dados/` e `resultados/` em `backups/reprocessamento_<TIMESTAMP>/`;
2. validação do lote;
3. sincronização dos 4 CSVs para `dados/`;
4. reconstrução do grafo (`scripts/construir_rede_grupos.py`);
5. geração de `resultados/`;
6. `npm run build` (pode ser pulado via `--skip-build`).

## 4) Fluxos úteis do shell

```bash
# processa sem validação (use apenas se já validou antes)
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"

# processa mais rápido, sem rebuild do frontend
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"

# equivalente em um passo no python
python3 scripts/reprocessar_dados_reais.py \
  --input-dir "$LOTE_DIR" \
  --process --clean --rebuild --print-stats

# equivalente direto no código dos 4 CSVs já em dados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 5) Reprocessar com dados já carregados em `dados/`

Se você já substituiu os 4 arquivos em `dados/`, rode:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild --print-stats
```

## 6) Verificar saúde da carga

1. Verificar banco e contagens das tabelas:

```bash
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

2. Conferir saúde da API:

```bash
curl -s http://127.0.0.1:8000/api/health | jq
curl -s http://127.0.0.1:8000/api/metadata | jq
```

3. Conferir arquivos de saída esperados:

```bash
ls -1 resultados/*.csv
ls -1 resultados/grafo_resultado.sqlite
```

Saídas geradas no processamento:

- `resultados/entidades.csv`
- `resultados/vinculos.csv`
- `resultados/grupos.csv`
- `resultados/membros_grupo.csv`
- `resultados/relacoes_entre_grupos.csv`
- `resultados/fila_revisao.csv`
- `resultados/agregacoes_financeiras_grupos.csv`
- `resultados/relatorio_analise.md`
- `resultados/grafo_resultado.sqlite`

## 7) Subir visualização

```bash
npm run backend  # API: http://127.0.0.1:8000
npm run dev      # Frontend: http://127.0.0.1:5173
```

Inicie pelo backend primeiro. Após a árvore recarregar, teste uma busca por CPF/CNPJ conhecido.

## 8) Rollback (se necessário)

Sempre que houve reprocessamento, um backup fica em:

`backups/reprocessamento_<YYYYmmdd_HHMMSS>/`

Para voltar ao estado anterior:

```bash
TS=20260622_130000  # ajuste para timestamp real
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
```

Depois disso, rode `npm run build` ou `npm run backend && npm run dev`.

## 9) Resumo de decisão (operacional)

Use estes 3 passos como rotina padrão:

1. **Validar:** `python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only`
2. **Reprocessar:** `scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"`
3. **Conferir:** endpoints + contagem de tabelas + revisar `resultados/fila_revisao.csv`

Se algum desses passos falhar, não entregue a carga e restaure o backup anterior.
