# Reutilização com dados reais

Este guia descreve como substituir os dados de exemplo por arquivos reais e
reprocessar toda a árvore sem quebrar o ambiente atual.

## Objetivo

- Trocar os 4 arquivos de entrada em lote.
- Validar estrutura antes de substituir dados em produção.
- Reprocessar rede completa (entidades, vínculos, grupos e relações).
- Regerar o frontend e a árvore para refletir o novo lote.
- Manter histórico de rollback por lote processado.

## 0) O que precisa existir

- `dados/` (entrada):
  - `stg_pessoa_fisica_atual_202606191707.csv`
  - `denodo_base_cadastral.csv`
  - `stg_cadastro_socio_pj_202606191707.csv`
  - `mv_movimentacoes.csv`

- `resultados/` (saída):
  - `entidades.csv`
  - `vinculos.csv`
  - `grupos.csv`
  - `membros_grupo.csv`
  - `relacoes_entre_grupos.csv`
  - `fila_revisao.csv`
  - `agregacoes_financeiras_grupos.csv`
  - `relatorio_analise.md`
  - `grafo_resultado.sqlite`

- Scripts de operação:
  - `scripts/reprocessar_dados_reais.py`
  - `scripts/reprocessar_arvore_reais.sh`
  - `scripts/construir_rede_grupos.py`

## 1) Preparar lote (recomendado)

Crie uma pasta por lote para manter rastreabilidade:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
LOTE_DIR="/tmp/lote_real_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOTE_DIR"
```

Copie os arquivos para `"$LOTE_DIR"` com nome exato:

```bash
cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
```

Gerar assinatura de integridade (opcional, recomendado):

```bash
cd "$LOTE_DIR"
sha256sum stg_pessoa_fisica_atual_202606191707.csv denodo_base_cadastral.csv \
  stg_cadastro_socio_pj_202606191707.csv mv_movimentacoes.csv > checksums.sha256
```

Cheque visual rápido:

```bash
for f in stg_pessoa_fisica_atual_202606191707.csv denodo_base_cadastral.csv stg_cadastro_socio_pj_202606191707.csv mv_movimentacoes.csv; do
  echo "=> $(wc -l "$f") linhas: $f"
done
```

Observação: arquivos devem ser **UTF-8** com separador `;`.

## 2) Validar lote (obrigatório)

```bash
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Regras da validação:

- cabeçalhos mínimos obrigatórios;
- alerta de colunas recomendadas ausentes;
- falha em erro estrutural.

## 2.1) Rotina de reuso com dados reais (resumo curto)

Para reutilizar com uma nova entrega:

```bash
# 1) preparar pasta do lote (fora do repositório)
mkdir -p /tmp/lote_cliente_$(date +%Y%m%d_%H%M%S)

# 2) validar pacote
python3 scripts/reprocessar_dados_reais.py --input-dir /tmp/lote_cliente_XXXX --check-only

# 3) reprocessar tudo
scripts/reprocessar_arvore_reais.sh /tmp/lote_cliente_XXXX

# 4) conferência rápida
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY
```

Observação: mantenha os arquivos do lote em pasta separada para trilhar fonte/retrocessão.

## 3) Reprocessar árvore (padrão operacional)

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Ou via npm:

```bash
npm run process:real -- "$LOTE_DIR"
```

O fluxo realiza:

1. backup automático de `dados/` e `resultados/` em:
   `backups/reprocessamento_<YYYYmmdd_HHMMSS>/`
2. validação do lote (salvo `--skip-validation`)
3. cópia dos 4 CSVs para `dados/`
4. reconstrução via `scripts/construir_rede_grupos.py`
5. geração de todas as tabelas e CSVs de saída
6. `npm run build` (salvo `--skip-build`)

## 4) Fluxos alternativos úteis

- Processar lote já validado sem validação:

  ```bash
  scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"
  ```

- Processar sem rebuild do frontend:

  ```bash
  scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"
  ```

- Executar diretamente no Python (equivalente):

  ```bash
  python3 scripts/reprocessar_dados_reais.py \
    --input-dir "$LOTE_DIR" \
    --process --clean --rebuild --print-stats
  ```

- Reprocessar usando os arquivos já presentes em `dados/`:

  ```bash
  python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild --print-stats
  ```

## 5) Verificar resultado

1. Status do grafo:

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

2. Health e metadados:

```bash
curl -s http://127.0.0.1:8000/api/health | jq
curl -s http://127.0.0.1:8000/api/metadata | jq
```

3. Conferir arquivos de saída:

```bash
ls -1 resultados/*.csv
ls -1 resultados/grafo_resultado.sqlite
```

## 6) Publicar para inspeção da árvore

```bash
npm run backend   # http://127.0.0.1:8000
npm run dev       # http://127.0.0.1:5173
```

Use busca de um CPF/CNPJ já conhecido para confirmar a nova base.

## 7) Rollback rápido

Cada reprocessamento salva uma pasta em `backups/`. Para restaurar:

```bash
TS="20260622_130000"  # troque pelo timestamp real
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
```

Depois execute:

```bash
npm run build
npm run backend
```

## 8) Erros comuns

- Lote com nomes diferentes: nenhum arquivo bate com o nome esperado.
- Encoding inválido: parser do CSV falha.
- colunas mínimas ausentes: validação cancela o fluxo.
- Falta de permissão de escrita em `resultados/` ou `dados/`.
- banco travado (`grafo_resultado.sqlite` aberto): feche API/frontend e rode novamente.

## 9) Check-list final antes de liberar

- lote em pasta auditável com checksums;
- validação sem erro;
- backup automático criado;
- tabelas de saída verificadas;
- revisão inicial da `resultados/fila_revisao.csv`;
- smoke-test da árvore no frontend.
