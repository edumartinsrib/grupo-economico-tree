# Grupo Econômico Tree

Projeto para construção de rede explicável de pessoas físicas, pessoas jurídicas,
vínculos familiares, societários e indícios econômicos.

## Estrutura do projeto

- `scripts/gerar_csvs_teste.py`: gera massa de dados sintéticos de referência.
- `scripts/construir_rede_grupos.py`: constrói entidades, vínculos, grupos e
  banco `resultados/grafo_resultado.sqlite`.
- `scripts/reprocessar_dados_reais.py`: orquestra validação e reprocessamento.
- `scripts/reprocessar_arvore_reais.sh`: fluxo de atualização com backup para dados reais.
- `dados/*.csv`: 4 arquivos de entrada.
- `resultados/*.csv`: saídas do processamento usadas no frontend.
- `docs/tutorial-atualizacao-dados-reais.md`: tutorial completo para reutilizar com
  dados reais (validação, reprocessamento, rollback e checagens).

## Reuso com dados reais (resumo rápido)

1. Monte um diretório de lote com os 4 CSVs de entrada.
2. Valide: `python3 scripts/reprocessar_dados_reais.py --input-dir <LOTE_DIR> --check-only`
3. Reprocesse: `scripts/reprocessar_arvore_reais.sh <LOTE_DIR>`
4. Confirme saúde da API e quantidades no banco.

Consulte o tutorial completo em:

- `docs/tutorial-atualizacao-dados-reais.md`

## Scripts disponíveis

```bash
npm run generate:test-data     # gera massa sintética em dados/
npm run validate:data          # valida os 4 arquivos em dados/
npm run check:data             # valida e encerra
npm run process:data           # processa sem build do frontend
npm run refresh:data           # valida + limpa + processa + build
npm run reprocess              # alias operacional curto: processa + build
npm run process:real           # atalho: scripts/reprocessar_arvore_reais.sh com lote externo
npm run backend                # sobe a API FastAPI (porta 8000)
npm run dev                    # sobe o frontend Vite
```

## Como usar dados reais (comandos oficiais)

```bash
# 1) preparar lote em pasta separada (LOTE_DIR)
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only

# 2) reprocessar tudo (com validação, backup, sync + build)
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"

# atalho npm
npm run process:real -- "$LOTE_DIR"
```

## Comandos rápidos para recálculo completo

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree

# Reprocessa toda a árvore com dados já em dados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild

# Reprocessa a partir de uma pasta de entrega
scripts/reprocessar_arvore_reais.sh /caminho/da/entrega_real

# Reprocessa lote diretamente com opções de CLI e sem passar pelo shell wrapper
python3 scripts/reprocessar_dados_reais.py --input-dir /caminho/da/entrega_real --process --clean --rebuild --print-stats
```

Checklist rápido após recálculo:

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY
```

## Validação da árvore após reload

```bash
curl http://127.0.0.1:8000/api/health
curl "http://127.0.0.1:8000/api/metadata"
```

## Recomendação de segurança

- Não versionar arquivos reais em `dados/` e `resultados/`.
- Manter backup de entrada/saída antes de cada carga.
- A validação e a revisão de `resultados/fila_revisao.csv` devem ser parte do
  fluxo de homologação.
