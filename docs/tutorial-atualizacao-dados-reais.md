# Como atualizar com dados reais e reprocessar a árvore

Este projeto é reutilizável com novas extrações reais.  
Todo o output é recalculado em `resultados/` a partir dos 4 CSVs em `dados/`.

## 1) O que é necessário

Arquivos obrigatórios em `dados/`:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

Observação: os nomes devem ser mantidos.  
Se o provedor chega com nomes diferentes, padronize antes de copiar.

## 2) Antes de processar (importante)

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
git status --short
```

- Não suba CSVs reais para o Git.
- Faça backup da base atual (dados + resultados).
- Confirme formato CSV `;` e UTF-8.

## 3) Substituir arquivos reais (sem tocar arquivos antigos)

Crie a pasta de origem com os 4 arquivos:

```bash
mkdir -p /tmp/entrada_reais
# copie os 4 arquivos reais para /tmp/entrada_reais
```

Em seguida execute:

```bash
cp /tmp/entrada_reais/stg_pessoa_fisica_atual_202606191707.csv dados/
cp /tmp/entrada_reais/denodo_base_cadastral.csv dados/
cp /tmp/entrada_reais/stg_cadastro_socio_pj_202606191707.csv dados/
cp /tmp/entrada_reais/mv_movimentacoes.csv dados/
```

## 4) Reprocessar toda a árvore (recomendado)

Use o fluxo completo:

```bash
npm run refresh:data
```

Esse comando já faz:

1. validação mínima dos 4 CSVs;
2. limpeza de `resultados/` antigo;
3. novo processamento;
4. build do frontend.

## 5) Script único de atualização + backup (fluxo operacional)

Para reduzir erro manual use:

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrada_reais
```

Opções:

- `--skip-validation` : pula validação de formato/cabeçalhos;
- `--skip-build` : processa rápido e não gera build;
- `-h` ou `--help`.

O script faz:

- backup de `dados/` e `resultados/` em `backups/reprocessamento_<timestamp>/`;
- cópia dos 4 arquivos novos para `dados/`;
- validação + reprocessamento + build (ou apenas reprocessamento, se `--skip-build`).

## 6) Conferência mínima da qualidade da saída

```bash
wc -l resultados/entidades.csv resultados/vinculos.csv resultados/grupos.csv resultados/fila_revisao.csv
sed -n '1,140p' resultados/relatorio_analise.md
sed -n '1,120p' resultados/fila_revisao.csv
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
cur = conn.cursor()
for t in ["entidades","vinculos","grupos","fila_revisao","membros_grupo"]:
    print(f"{t}: {cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
print("OK:", "resultados carregado")
PY
```

## 7) Abrir e validar visão

```bash
npm run dev
```

- Acesse `http://localhost:5173`.
- Se a árvore estiver grande, navegue por níveis no painel, use busca e filtros.

## 8) Recuperar versão anterior (rollback)

Você pode restaurar rapidamente o snapshot:

```bash
ls -1 backups | grep reprocessamento_ | tail -n 5
ts=YYYYMMDD_HHMMSS  # substituir pelo timestamp do backup desejado
cp backups/reprocessamento_$ts/dados/* dados/
cp backups/reprocessamento_$ts/resultados/* resultados/
npm run process:data
```

## 9) Observações de governança de dados

- Nunca comitar dados reais de produção (nem em `dados/` nem `resultados/`).
- Nome, parentesco e vínculos não são normalizados por identidade de texto puro; o pipeline aplica as regras de resolução da base.
- Ao comparar versões, trate os outputs como visões regeneradas (não incrementalmente atualizados).

## 10) Comandos úteis

```bash
npm run validate:data    # valida apenas os 4 arquivos de entrada
npm run check:data       # valida e encerra
npm run process:data     # roda script gerador (sem rebuild)
npm run refresh:data     # valida + clean + reprocessa + rebuild
```

Fluxo recomendado para produção mensal:

1. `scripts/reprocessar_arvore_reais.sh /caminho/da/entrega`
2. `npm run validate:data` (se não rodou no fluxo automático)
3. `npm run refresh:data`
4. revisar `resultados/relatorio_analise.md` e `resultados/fila_revisao.csv`
