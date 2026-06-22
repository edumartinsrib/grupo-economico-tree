# Tutorial: atualização com dados reais

Este projeto pode ser reutilizado para um novo lote de dados reais sem alterar código.

## O que você vai fazer

1. Colocar os 4 arquivos da entrega em uma pasta.
2. Rodar o reprocessador.
3. Recarregar a árvore na interface.
4. Validar saídas + fila de revisão.
5. (Opcional) restaurar backup caso necessário.

## Arquivos obrigatórios

```
stg_pessoa_fisica_atual_202606191707.csv
denodo_base_cadastral.csv
stg_cadastro_socio_pj_202606191707.csv
mv_movimentacoes.csv
```

Formato esperado:
- UTF-8
- separador `;`
- cabeçalhos conforme os nomes acima (o processador valida apenas campos mínimos)

## Estrutura de diretórios do projeto

- `dados/` → entrada do motor (CSVs usados na execução).
- `resultados/` → saída (`entidades.csv`, `vinculos.csv`, `grupos.csv` ...).
- `backups/reprocessamento_YYYYMMDD_HHMMSS/` → backup automático a cada carga.

## Fluxo recomendado (nova entrega completa)

Use esse fluxo quando chegar uma carga nova e completa:

```bash
mkdir -p /tmp/entrega_real
cp /origem/stg_pessoa_fisica_atual_202606191707.csv /tmp/entrega_real/
cp /origem/denodo_base_cadastral.csv /tmp/entrega_real/
cp /origem/stg_cadastro_socio_pj_202606191707.csv /tmp/entrega_real/
cp /origem/mv_movimentacoes.csv /tmp/entrega_real/

cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

O script já faz:

1. `backups/reprocessamento_<data>/` de `dados/` e `resultados/`.
2. validação mínima dos 4 arquivos.
3. troca os CSVs em `dados/`.
4. processamento completo (`--process --clean --rebuild`).
5. build da UI.

## Reprocessar sem trocar arquivos de entrada

Quando os 4 CSVs já estiverem em `dados/` e você quer só recalcular:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## Comandos rápidos úteis

```bash
npm run validate:data     # valida os 4 CSVs em dados/
npm run check:data        # valida e encerra
npm run process:data      # roda somente o motor (sem build)
npm run refresh:data      # valida + limpa + processa + build
npm run backend          # sobe API em http://localhost:8000
npm run dev              # sobe frontend em http://localhost:5173
```

## Verificação mínima após reprocessar

1) Conferir cardinalidade das tabelas do grafo:

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY
```

2) Conferir documentação de saída:

```bash
sed -n '1,120p' resultados/relatorio_analise.md
sed -n '1,160p' resultados/fila_revisao.csv
```

3) Abrir a árvore e validar a visualização:

```bash
npm run backend
npm run dev
```

## Opções do script de carga

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-validation
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-build
```

- `--skip-validation`: usar apenas quando já sabe que o cabeçalho está ok.
- `--skip-build`: acelera o ciclo para validar somente árvore/API (sem gerar bundle).

## Rollback (voltar à versão anterior)

Se precisar reverter:

```bash
ls -1 backups | grep reprocessamento_ | tail -n 5
ts=YYYYMMDD_HHMMSS
cp -r backups/reprocessamento_$ts/dados dados
cp -r backups/reprocessamento_$ts/resultados resultados
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## Boas práticas com dados reais

- Nunca versionar dados reais.
- Não sobrescrever os arquivos originais recebidos (`/tmp/entrega_real`).
- Sempre validar e revisar a `fila_revisao.csv`.
- Guardar pelo menos 2 backups antes de publicar.
- Rodar reprocessamento completo após qualquer troca de estrutura dos 4 CSVs.
