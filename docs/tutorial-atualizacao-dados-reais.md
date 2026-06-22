# Tutorial: atualização com dados reais

Você pode reutilizar esse projeto com novos lotes reais mantendo a mesma base de código.
O fluxo abaixo é o padrão operacional para atualização e reprocessamento completo da árvore.

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

## 1) Fluxo recomendado (nova entrega completa)

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

## 2) Reprocessamento manual (sem trocar arquivos)

Se os 4 CSVs já estiverem em `dados/` e você só quiser recalcular:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 3) Comandos mais usados no dia a dia

| Objetivo | Comando |
|---|---|
| Validar cabeçalhos e separadores | `npm run validate:data` |
| Só validar e encerrar | `npm run check:data` |
| Rodar só o motor (sem build) | `python3 scripts/construir_rede_grupos.py` ou `npm run process:data` |
| Processar + build do frontend | `python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild` |
| Executar script completo com pasta de origem | `scripts/reprocessar_arvore_reais.sh /caminho/entrega` |

## 4) Checklist mínimo após reprocessar

1. Confirmar contagens das tabelas:

   ```bash
   python3 - <<'PY'
   import sqlite3
   conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
   for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
       print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
   conn.close()
   PY
   ```

2. Ler os artefatos de revisão:

   ```bash
   sed -n '1,120p' resultados/relatorio_analise.md
   sed -n '1,160p' resultados/fila_revisao.csv
   ```

3. Iniciar visualização:

   ```bash
   npm run backend
   npm run dev
   ```

4. No frontend, carregar uma entidade e validar se a árvore cresce por níveis (pai/filho, irmãos, sócios) conforme esperado.

## Observação para reuso operacional

- Use sempre uma pasta temporária para a entrega (ex.: `/tmp/entrega_real`) e nunca altere os arquivos originais recebidos.
- Se houver erro de processamento, recupere o estado anterior com o backup de `backups/reprocessamento_<timestamp>`.
- Documente qual parâmetro de ambiguidade e validação foi aplicado em cada execução (importante para rastreabilidade).

## Comandos rápidos úteis

```bash
npm run validate:data     # valida os 4 CSVs em dados/
npm run check:data        # valida e encerra
npm run process:data      # roda somente o motor (sem build)
npm run refresh:data      # valida + limpa + processa + build
npm run backend           # sobe API em http://localhost:8000
npm run dev               # sobe frontend em http://localhost:5173
npm run process:real /tmp/entrega_real    # executa reprocessar_arvore_reais.sh
```

## Script de recálculo orientado para produção de lote

```bash
# Atualiza pasta temporária com arquivos reais recebidos
mkdir -p /tmp/entrega_real
cp /origem/stg_pessoa_fisica_atual_202606191707.csv /tmp/entrega_real/
cp /origem/denodo_base_cadastral.csv /tmp/entrega_real/
cp /origem/stg_cadastro_socio_pj_202606191707.csv /tmp/entrega_real/
cp /origem/mv_movimentacoes.csv /tmp/entrega_real/

# Reprocessa tudo (validação, rebuild e backup automático)
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

> Observação: quando precisar validar lógica do processamento mais rápido, use `--skip-build` e execute o build normalmente ao final.

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
