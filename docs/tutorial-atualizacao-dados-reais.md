# Tutorial de atualização com dados reais

Este guia é para reusar o projeto com lote real e reconstruir a árvore inteira
de relacionamento de ponta a ponta.

## Pré-requisitos

- Python 3.8+
- Node.js 20+
- `resultados/grafo_resultado.sqlite` pode ser sobrescrito (é gerado no processamento).
- Os 4 arquivos devem estar em UTF-8 e separados por `;`.

Arquivos obrigatórios:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

## 1) Preparar lote real

Crie uma pasta de entrada fora do repositório (recomendado para rastreabilidade):

```bash
mkdir -p /tmp/entrega_real
cp /origem/stg_pessoa_fisica_atual_202606191707.csv /tmp/entrega_real/
cp /origem/denodo_base_cadastral.csv /tmp/entrega_real/
cp /origem/stg_cadastro_socio_pj_202606191707.csv /tmp/entrega_real/
cp /origem/mv_movimentacoes.csv /tmp/entrega_real/
```

## 2) Validar lote (antes de sobrescrever dados)

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --check-only
```

Observação: `--skip-validation` abaixo é opcional e útil apenas em ambiente de
homologação quando as rotinas de controle já foram validadas na origem.

### Validação com os nomes e requisitos mínimos

Se tudo estiver correto:

```bash
python3 scripts/reprocessar_dados_reais.py
```

Saída esperada: mensagem de OK para os 4 arquivos.

## 3) Reprocessar tudo (dados novos)

### Opção A — substituir arquivos pelo lote real e processar (padrão recomendado)

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

Esse fluxo faz:

1. backup de `dados/` e `resultados/`
2. substituição dos 4 CSVs em `dados/`
3. validação (ou não, se usar `--skip-validation`)
4. recomposição completa do grafo em `resultados/`
5. build do frontend

### Opção B — reprocessar a árvore já com arquivos em `dados/`

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Alias equivalente:

```bash
npm run refresh:data
```

## 4) Modos úteis

- `--skip-validation`: pula validação de headers mínimos.
- `--skip-build`: processa sem rodar `npm run build` (mais rápido).
- `--check-only`: só valida e encerra.
- `--process`: obrigatório para reconstruir saída.
- `--clean`: remove saídas anteriores antes de processar.
- `--rebuild`: recompila o frontend.

Exemplos:

```bash
scripts/reprocessar_arvore_reais.sh --skip-validation /tmp/entrega_real
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild --skip-validation
npm run process:data   # apenas reprocessa sem rebuild do frontend
npm run check:data     # validação mínima + encerramento
```

## 5) Validar a árvore gerada

1) Conferir contagem de entidades/vínculos/grupos:

```bash
python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for tabela in [
    "entidades",
    "vinculos",
    "grupos",
    "membros_grupo",
    "relacoes_entre_grupos",
    "fila_revisao",
]:
    total = conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    print(f"{tabela:24} {total}")
conn.close()
PY
```

2) Revisão inicial de filas e alertas:

```bash
sed -n '1,180p' resultados/fila_revisao.csv
sed -n '1,160p' resultados/relatorio_analise.md
```

3) Conferir saúde da API:

```bash
npm run backend
# em outra aba
curl http://127.0.0.1:8000/api/health
```

## 6) Subir a visualização

```bash
npm run backend   # terminal 1
npm run dev       # terminal 2
```

No front:
- escolha uma entidade pelo buscador,
- abra por nível (pai/filho acima/abaixo),
- use `Definir este como centro` para trocar o nó raiz,
- use `Ver acima` / `Ver abaixo` para navegar em componentes maiores,
- ajuste “Quantidade por pessoa” e escopo de relação conforme necessário.

## 7) Rollback (seguro)

Backups são criados em `backups/reprocessamento_AAAA...` quando se usa o script
`reprocessar_arvore_reais.sh`.

```bash
ls -1 backups | grep reprocessamento_ | sort | tail

TS=YYYYMMDD_HHMMSS
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
```

Após restaurar, recompile:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 8) Boas práticas obrigatórias

- Não versionar CSVs reais em `dados/` e `resultados/`.
- Guardar origem/lote + timestamp fora do repositório.
- Validar e revisar `resultados/fila_revisao.csv` antes de homologar.
- Manter backup sempre antes de cada recarga.
