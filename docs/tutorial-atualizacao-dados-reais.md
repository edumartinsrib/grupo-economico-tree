# Como usar dados reais e reprocessar toda a árvore

Este projeto pode ser reutilizado com base real sem alterar código.
O fluxo abaixo gera a árvore completa a partir de 4 CSVs de entrada.

## 1) Pré-requisitos

- Ambiente Node + npm e Python 3.
- Backend da API rodando com acesso ao banco `resultados/grafo_resultado.sqlite`.
- Arquivos de entrada com `;` (ponto e vírgula) e UTF-8:
  - `stg_pessoa_fisica_atual_202606191707.csv`
  - `denodo_base_cadastral.csv`
  - `stg_cadastro_socio_pj_202606191707.csv`
  - `mv_movimentacoes.csv`

## 2) Preparar lote de atualização

Monte uma pasta de entrega separada, sem misturar versões:

```bash
TS="$(date +%Y%m%d_%H%M%S)"
LOTE_DIR="/tmp/entrega_real_${TS}"
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
```

## 3) Validar lote antes de processar (obrigatório)

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Esse comando valida:

- presença dos 4 arquivos;
- cabeçalhos mínimos esperados;
- leitura básica do arquivo (estrutura CSV).

Se quiser validar também o diretório padrão `dados/`:

```bash
python3 scripts/reprocessar_dados_reais.py --check-only
```

## 4) Reprocessar a árvore inteira com backup

Use o script principal (recomendado):

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Com isso, o script faz:

1. backup de `dados/` e `resultados/` em `backups/reprocessamento_<TIMESTAMP>/`;
2. validação do lote (a menos que use `--skip-validation`);
3. sincroniza os 4 CSVs para `dados/`;
4. roda `python3 scripts/construir_rede_grupos.py`;
5. gera `resultados/grafo_resultado.sqlite` e CSVs finais;
6. executa `npm run build` (a menos que use `--skip-build`).

Alternativa via npm:

```bash
npm run process:real -- "$LOTE_DIR"
```

## 5) Opções úteis

```bash
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"   # só processa dados e banco
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"  # pula validação (só use se já validado)
```

Ou o fluxo explícito da CLI:

```bash
python3 scripts/reprocessar_dados_reais.py \
  --input-dir "$LOTE_DIR" \
  --process \
  --clean \
  --rebuild \
  --print-stats
```

## 6) Conferir resultado do recálculo

### 6.1 Validação técnica do banco

```bash
python3 - <<'PY'
import sqlite3
from pathlib import Path

path = Path("resultados/grafo_resultado.sqlite")
print(f"Arquivo: {path}")
print(f"Tamanho MB: {path.stat().st_size / 1024 / 1024:.3f}")

conn = sqlite3.connect(path)
for tabela in [
    "entidades",
    "vinculos",
    "grupos",
    "membros_grupo",
    "relacoes_entre_grupos",
    "fila_revisao",
]:
    total = conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    print(f"{tabela}: {total}")
conn.close()
PY
```

### 6.2 Validação da API

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/metadata
```

Exemplo de consulta da árvore (sem abrir o navegador):

```bash
curl -s "http://127.0.0.1:8000/api/tree/family/entidade_id?max_per_node=20"
```

## 7) Conferir arquivos de saída esperados

- `resultados/entidades.csv`
- `resultados/vinculos.csv`
- `resultados/grupos.csv`
- `resultados/membros_grupo.csv`
- `resultados/relacoes_entre_grupos.csv`
- `resultados/fila_revisao.csv`
- `resultados/agregacoes_financeiras_grupos.csv`
- `resultados/relatorio_analise.md`
- `resultados/grafo_resultado.sqlite`

## 8) Iniciar serviços para visualizar a árvore

```bash
npm run backend   # FastAPI em 8000
npm run dev       # Frontend Vite
```

## 9) Recarregar base local com novos arquivos (sem novo lote)

Se já copiou manualmente novos CSVs em `dados/`, rode:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 10) Rollback (caso necessário)

Localize a pasta de backup mais recente em `backups/` e restaure:

```bash
TS=20260622_120000
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --process --clean
```

## 11) Boas práticas para operação com dados reais

- Não versionar arquivos reais em `dados/` e `resultados/`.
- Manter lote por data e checksum em local seguro.
- Revisar `resultados/fila_revisao.csv` antes de homologar.
- Não misturar lote de homologação e produção no mesmo diretório.
