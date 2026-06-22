# Tutorial de Reuso com Dados Reais

Este tutorial descreve o fluxo recomendado para substituir os dados de entrada e
reprocessar a árvore explicável por completo.

## 1) Arquivos obrigatórios

Mantenha sempre os nomes abaixo:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

Padronização necessária:

- `UTF-8`
- separador `;`
- cabeçalhos esperados conforme o processo de validação mínima

## 2) Atualizar com novo lote de dados reais (recomendado)

1. Copie os quatro arquivos para uma pasta de entrega fora do repositório.
2. Rode o script de recarga real.
3. O script valida (ou pode pular validação), faz backup e recompila `resultados/` e `dados/`.
4. Aguarde a conclusão do processamento e do build.

Exemplo:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree

mkdir -p /tmp/entrega_real
cp "/origem/stg_pessoa_fisica_atual_202606191707.csv" /tmp/entrega_real/
cp "/origem/denodo_base_cadastral.csv" /tmp/entrega_real/
cp "/origem/stg_cadastro_socio_pj_202606191707.csv" /tmp/entrega_real/
cp "/origem/mv_movimentacoes.csv" /tmp/entrega_real/

scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

Flags úteis:

- `--skip-validation`: pula validação de cabeçalhos de entrada.
- `--skip-build`: processa sem `npm run build` (mais rápido).

## 3) Reprocessar toda a árvore (sem nova pasta de entrega)

Quando os arquivos já estiverem em `dados/`:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Alias equivalente:

```bash
npm run refresh:data
```

Execução sem build:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean
```

Somente validação:

```bash
npm run check:data
```

## 4) Fluxo de validação pós-processamento

### 4.1 Verificar saúde dos arquivos

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for tabela in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{tabela}: {conn.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0]}")
conn.close()
PY
```

### 4.2 Revisão manual

```bash
sed -n '1,160p' resultados/fila_revisao.csv
sed -n '1,120p' resultados/relatorio_analise.md
```

## 5) Publicar para visualização local

```bash
# API
npm run backend

# em outra aba
npm run dev
```

Após subir, selecione uma entidade e valide:

- expansão por nível (pai/filho e irmãos)
- vínculos carregados conforme `includeWeak`
- revisão de candidaturas em relações ambíguas

## 6) Rollback (seguro)

1. Liste backups:

```bash
ls -1 backups | grep reprocessamento_ | sort | tail
```

2. Recupere uma versão anterior:

```bash
TS=YYYYMMDD_HHMMSS
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 7) Boas práticas

- Não versionar CSVs reais em `dados/` e `resultados/`.
- Usar sempre pasta de entrega fora do projeto para origem real.
- Registrar timestamp da execução, origem do lote e flags usadas.
- Revisar `fila_revisao.csv` antes de fechar homologação.

