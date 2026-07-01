# Atualizar a base real e reprocessar a árvore

## Objetivo

Substituir os arquivos de teste pelos arquivos reais, regenerar completamente:

- `entidades.csv`
- `vinculos.csv`
- `grupos.csv`
- `membros_grupo.csv`
- `relacoes_entre_grupos.csv`
- `fila_revisao.csv`
- `agregacoes_financeiras_grupos.csv`
- `grafo_resultado.sqlite`

e manter o frontend apontando para a nova versão da árvore.

## O que você precisa

- Os 4 CSVs reais obrigatórios com nomes exatos:

  - `stg_pessoa_fisica_atual_202606191707.csv`
  - `denodo_base_cadastral.csv`
  - `stg_cadastro_socio_pj_202606191707.csv`
  - `mv_movimentacoes.csv`

- Opcional para importar grupos econômicos já existentes:

  - `denodo_pessoa_grupo.csv`

- Ambiente com:

  - `python3`
  - `npm`
  - `jq` (opcional, para leitura de JSON)

- API e frontend disponíveis para validação (`npm run backend` e `npm run dev`).

## 1) Preparar lote

Sempre trabalhe com uma pasta de lote externa (ou fora de `dados/`) para manter trilha.

```bash
LOTE_DIR="/tmp/lote_real_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOTE_DIR"

cp /caminho/real/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /caminho/real/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /caminho/real/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /caminho/real/mv_movimentacoes.csv "$LOTE_DIR/"
# Opcional, quando houver carga da view pessoa_grupo:
[[ -f /caminho/real/denodo_pessoa_grupo.csv ]] && cp /caminho/real/denodo_pessoa_grupo.csv "$LOTE_DIR/"

cd "$LOTE_DIR"
sha256sum *.csv > checksums.sha256
for f in *.csv; do
  echo "=> $(wc -l "$f") linhas: $f"
done
```

Critérios mínimos esperados: **UTF-8** e **separador `;`**.

## 2) Validar lote (obrigatório)

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Validações feitas:

- presença dos 4 arquivos obrigatórios no lote;
- estrutura do `denodo_pessoa_grupo.csv`, quando presente;
- cabeçalhos mínimos obrigatórios por arquivo;
- alertas para colunas recomendadas ausentes;
- estrutura básica de parsing.

Se houver erro, o fluxo para e o lote não é aplicado.

## 3) Reprocessar a árvore (fluxo completo)

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Comportamento do script:

1. Valida lote (a menos que `--skip-validation` seja usado);
2. Faz backup automático de `dados/` e `resultados/` em
   `backups/reprocessamento_<TIMESTAMP>/`;
3. Copia os arquivos do lote para `dados/`;
4. Executa limpeza dos resultados anteriores (`--clean`);
5. Reconstrói com `scripts/construir_rede_grupos.py`;
6. (opcional) executa `npm run build` para atualização do frontend (`--skip-build` desativa).

### Opções úteis

```bash
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"   # pular validação
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"         # sem rebuild frontend
```

Também por npm:

```bash
npm run process:real -- "$LOTE_DIR"
```

## 4) Reprocessamento apenas com arquivos já em `dados/`

Quando os 4 arquivos reais obrigatórios já foram copiados para `dados/` e não quer fazer copy do lote novamente:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild --print-stats
```

Isso é útil para ajustes de pipeline sem trocar lote.

## 5) Verificação pós-carga (obrigatória)

1) Conferir estado da API:

```bash
curl -s http://127.0.0.1:8000/api/health | jq
curl -s "http://127.0.0.1:8000/api/metadata" | jq
```

2) Conferir totais das tabelas principais:

```bash
python3 - <<'PY'
import sqlite3

db = 'resultados/grafo_resultado.sqlite'
conn = sqlite3.connect(db)
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY
```

3) Conferir árvore no frontend:

- `npm run backend`
- `npm run dev`
- Buscar um CPF/CNPJ conhecido e validar expansão por níveis.

4) Revisão inicial de consistência de risco:

- `resultados/fila_revisao.csv`
- `resultados/relatorio_analise.md`

Se `denodo_pessoa_grupo.csv` foi fornecido, valide também:

- pessoas ou empresas que aparecem em mais de um grupo oficial no painel de detalhes;
- relações `GRUPOS_VINCULADOS_POR_ENTIDADE` em `resultados/relacoes_entre_grupos.csv`;
- grupos oficiais com identificador `GE:<cooperativa>:<cod_grupo>` no banco SQLite.

## 6) Rollback rápido (se preciso)

Cada execução gera:

`backups/reprocessamento_<YYYYmmdd_HHMMSS>/dados` e `.../resultados`

Para voltar:

```bash
TS="20260622_130000"  # ajuste para o timestamp do backup
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
npm run build
npm run backend
```

## 7) Fluxo padrão de rotina

```bash
# exemplo operacional
LOTE_DIR="/tmp/lote_cliente_$(date +%Y%m%d_%H%M%S)"

# 1) montar lote com nomes corretos e checksums
# 2) validar
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only

# 3) reprocessar completo
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"

# 4) conferir API e contagem de nós
curl -s "http://127.0.0.1:8000/api/metadata" | jq
```

## Observações de governança

- Não versione `dados/` e `resultados/` reais.
- Use nomes exatos dos arquivos para o parser.
- Mantenha `checksums.sha256` e lote em pasta auditável para trilha regulatória.
- Se o lote falhar validação, corrija origem antes de reprocessar.
