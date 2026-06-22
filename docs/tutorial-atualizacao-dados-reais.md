# Tutorial de Atualização com Dados Reais

Esse fluxo permite reutilizar o projeto com novos lotes reais e recalcular a
árvore inteira sem perder rastreabilidade.

## 1) Entregáveis obrigatórios

Use sempre os mesmos 4 arquivos:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

Formato esperado: `UTF-8`, separador `;`, cabeçalhos com os nomes acima.

## 2) Fluxo padrão (recebida nova)

1. Copiar a entrega para uma pasta temporária (não mexer no fonte).
2. Rodar o script de recarga.
3. O script cria backup automático em `backups/reprocessamento_<timestamp>`.
4. O projeto é processado novamente e a árvore é recalculada.

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

Sem build de frontend (mais rápido):

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-build
```

Pulando validação (somente se já conferido previamente):

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-validation
```

## 3) Reprocessar toda a árvore (sem nova entrega)

Quando os 4 CSVs já estiverem em `dados/`, rode:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Ou pelo atalho:

```bash
npm run refresh:data
```

Opção manual sem build:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean
```

Somente validação:

```bash
npm run check:data
```

## 4) Validação pós-processamento

Verificar contagens dos 6+ produtos:

```bash
python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for tabela in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    total = conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    print(f"{tabela}: {total}")
conn.close()
PY
```

Conferir arquivos de revisão:

```bash
sed -n '1,160p' resultados/fila_revisao.csv
sed -n '1,120p' resultados/relatorio_analise.md
```

## 5) Subir árvore no navegador

```bash
# API
npm run backend

# Frontend (em outra aba)
npm run dev
```

Selecione uma entidade e acompanhe:

- árvore expandida por laço
- novos vínculos após recálculo
- indicadores de revisão

## 6) Rollback

Liste os backups recentes:

```bash
ls -1 backups | grep reprocessamento_ | sort | tail
```

Restaure o pacote anterior:

```bash
ts=YYYYMMDD_HHMMSS
cp -r backups/reprocessamento_${ts}/dados/* dados/
cp -r backups/reprocessamento_${ts}/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 7) Boas práticas para dados reais

- Não versionar CSVs reais em `dados/` ou `resultados/`.
- Trabalhar sempre com pasta de entrega fora do repositório (`/tmp/entrega_real`).
- Rodar `check:data` antes de publicar.
- Registrar data/hora da execução e parâmetros usados para rastreabilidade.
- Revisar `fila_revisao.csv` em toda carga.
