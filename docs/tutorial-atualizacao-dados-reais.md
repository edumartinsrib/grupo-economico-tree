# Tutorial: atualizar dados reais e reprocessar toda a árvore

Este projeto funciona com os CSVs de entrada na pasta `dados/`. A árvore exibida no frontend é gerada a partir de `resultados/`.

## 1) Estrutura esperada

- `dados/stg_pessoa_fisica_atual_202606191707.csv`
- `dados/denodo_base_cadastral.csv`
- `dados/stg_cadastro_socio_pj_202606191707.csv`
- `dados/mv_movimentacoes.csv`

Os nomes dos arquivos são fixos porque o script de processamento espera exatamente estes nomes.

## 2) Antes de substituir os dados (segurança)

1. Trabalhe em cópia local protegida.
2. Não versionar dados reais:
   - `dados/`
   - `resultados/`
3. Faça backup do dataset sintético atual (opcional, recomendado):

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
mkdir -p backups/dados-sinteticos-$(date +%Y%m%d-%H%M%S)
cp dados/*.csv backups/dados-sinteticos-$(date +%Y%m%d-%H%M%S)/
mkdir -p backups/resultados-antigos-$(date +%Y%m%d-%H%M%S)
cp resultados/* backups/resultados-antigos-$(date +%Y%m%d-%H%M%S)/
```

## 3) Substituir os quatro CSVs reais

Caminho de origem pode mudar conforme sua origem; os nomes no destino precisam ser os mesmos.

```bash
cp /caminho/dados/novos/stg_pessoa_fisica_atual_202606191707.csv dados/
cp /caminho/dados/novos/denodo_base_cadastral.csv dados/
cp /caminho/dados/novos/stg_cadastro_socio_pj_202606191707.csv dados/
cp /caminho/dados/novos/mv_movimentacoes.csv dados/
```

## 4) Validação de entrada (obrigatória)

Execute a validação antes de processar:

```bash
npm run validate:data
```

A validação checa:
- existência dos 4 arquivos;
- encoding UTF-8;
- separador `;` e presença de colunas mínimas;
- falha rápida com mensagem dos campos faltantes.

Se quiser só validar sem processar:

```bash
npm run check:data
```

## 5) Reprocessar a árvore completa

### Opção rápida (somente dados)

```bash
npm run process:data
```

### Opção completa (recomendado para ambiente real)

```bash
npm run refresh:data
```

Esse comando faz:
1. validação de entrada;
2. limpeza de outputs antigos;
3. processamento do grafo;
4. build do frontend (útil para validar que a saída ainda abre).

Se preferir separar em etapas:

```bash
npm run validate:data
npm run process:data
npm run build
npm run dev
```

## 6) Conferir saída e qualidade

Após o processamento, validar:

```bash
wc -l resultados/entidades.csv resultados/vinculos.csv resultados/grupos.csv resultados/fila_revisao.csv
sed -n '1,140p' resultados/relatorio_analise.md
sed -n '1,140p' resultados/fila_revisao.csv
```

Consulta rápida no SQLite (opcional):

```bash
sqlite3 resultados/grafo_resultado.sqlite ".tables"
sqlite3 resultados/grafo_resultado.sqlite "select tipo_grupo, count(*) from grupos group by tipo_grupo;"
sqlite3 resultados/grafo_resultado.sqlite "select codigo_alerta, count(*) from fila_revisao group by codigo_alerta order by 2 desc;"
```

## 7) Abrir a visualização

```bash
npm run dev
```

URL local:

`http://localhost:5173/`

Para acompanhar componentes grandes:

- use `+` nos nós da árvore para abrir perna por perna;
- use arraste (drag) da árvore;
- use o checkbox de vínculos indiretos para incluir/excluir evidências fracas.

## 8) Reprocessar novamente sempre que houver atualização

Quando chegar uma nova remessa de dados, repetir:

1. substituir os 4 CSVs;
2. `npm run refresh:data`;
3. abrir `npm run dev`.

## 9) Reverter para dados de treino (se necessário)

```bash
cp backups/dados-sinteticos-<TIMESTAMP>/* dados/
rm -f resultados/*
cp backups/resultados-antigos-<TIMESTAMP>/* resultados/
npm run process:data
```

Substitua `<TIMESTAMP>` pelo nome da pasta do backup.

Observação: essa etapa só é segura se você realmente fez backup completo dos arquivos anteriores.
