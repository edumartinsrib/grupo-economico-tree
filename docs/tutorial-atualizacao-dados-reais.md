# Como atualizar com dados reais e reprocessar toda a árvore

## Objetivo
Utilizar novos arquivos reais de cadastro e reconstruir a visão de rede sem precisar alterar código.

## 1) O que precisa existir

Os 4 arquivos abaixo são obrigatórios:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

## 2) Estrutura de nomes/colunas (mínimo exigido)

| Arquivo | Colunas mínimas obrigatórias |
|---|---|
| stg_pessoa_fisica_atual_202606191707.csv | `cpf_cnpj`, `nome_pessoa`, `nome_pessoa_normalizado`, `dat_nascimento` |
| denodo_base_cadastral.csv | `cpf_cnpj`, `cod_conglomerado`, `status_conta` |
| stg_cadastro_socio_pj_202606191707.csv | `cnpj_associado`, `cpf_cnpj_socio`, `per_capital` |
| mv_movimentacoes.csv | `cpf_cnpj_origem`, `cpf_cnpj_destino`, `competencia_inicial`, `competencia_final`, `qtd_movimentacoes`, `vlr_total_transferido` |

> O validador atual é operacional (estrutura/headers + presença de arquivo). Para regras mais fortes de qualidade, use a etapa manual de revisão da saída (`fila_revisao.csv`).

## 3) Criar lote de entrada para não misturar versões

```bash
LOTE_DIR=/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
```

## 4) Validação (recomendado antes de qualquer processamento)

```bash
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

## 5) Reprocessamento completo (produção/reprocessamento padrão)

Use este fluxo para sobrescrever `dados/`, limpar saídas antigas e refazer árvore + build:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

O que acontece:
1. validação do lote;
2. backup automático de `dados/` e `resultados/` em `backups/reprocessamento_<timestamp>/`;
3. copia do lote para `dados/`;
4. limpeza dos resultados antigos;
5. processamento (`scripts/construir_rede_grupos.py`);
6. build do frontend (`npm run build`).

## 6) Fluxo com opções rápidas

- Ignorar validação (somente após carga já validada em ambiente controlado):
  ```bash
  scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"
  ```

- Pular build para conferir só geração dos dados (mais rápido em bancada):
  ```bash
  scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"
  ```

- Via npm:
  ```bash
  npm run process:real -- "$LOTE_DIR"
  ```

## 7) Subir serviços para consultar

```bash
npm run backend   # porta 8000
npm run dev       # frontend
```

## 8) Checagens obrigatórias após processamento

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('resultados/grafo_resultado.sqlite')
for t in [
    'entidades', 'vinculos', 'grupos', 'membros_grupo', 'relacoes_entre_grupos', 'fila_revisao'
]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY

curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/metadata
```

Arquivos principais gerados em `resultados/`:
- `entidades.csv`
- `vinculos.csv`
- `grupos.csv`
- `membros_grupo.csv`
- `relacoes_entre_grupos.csv`
- `fila_revisao.csv`
- `agregacoes_financeiras_grupos.csv`
- `relatorio_analise.md`

## 9) Rollback com segurança

Se algo não ficar como esperado, recupere o backup criado automaticamente:

```bash
TS=AAAA_MMDD_HHMMSS  # do diretório de backup
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --input-dir dados --process --clean
```

## 10) Observações para operação diária

- Mantenha dados reais fora do Git.
- Não reutilize a pasta `dados/` como arquivo de origem final; use sempre um diretório de lote.
- `resultados/` é saída: pode ser sobrescrita por lote.
- A revisão humana parte prioritária é `fila_revisao.csv`.
