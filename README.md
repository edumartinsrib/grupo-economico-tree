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
- `docs/tutorial-atualizacao-dados-reais.md`: roteiro operacional de atualização com dados reais.

## Scripts disponíveis

```bash
npm run generate:test-data     # gera massa sintética em dados/
npm run validate:data          # valida os 4 arquivos em dados/
npm run check:data             # valida e encerra
npm run process:data           # processa sem build do frontend
npm run refresh:data           # valida + limpa + processa + build
npm run reprocess              # alias operacional curto: processa + build
npm run backend                # sobe a API FastAPI (porta 8000)
npm run dev                    # sobe o frontend Vite
```

## Atualização com dados reais

Se for reutilizar com base real, use o fluxo abaixo:

```bash
mkdir -p /tmp/entrega_real
cp /origem/stg_pessoa_fisica_atual_202606191707.csv /tmp/entrega_real/
cp /origem/denodo_base_cadastral.csv /tmp/entrega_real/
cp /origem/stg_cadastro_socio_pj_202606191707.csv /tmp/entrega_real/
cp /origem/mv_movimentacoes.csv /tmp/entrega_real/

scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

Mais detalhes operacionais em:

- `docs/tutorial-atualizacao-dados-reais.md`

## Comandos rápidos para recálculo completo

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree

# Reprocessa toda a árvore com dados já em dados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild

# Reprocessa a partir de uma pasta de entrega
scripts/reprocessar_arvore_reais.sh /caminho/da/entrega_real
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

## Recomendação de segurança

- Não versionar arquivos reais em `dados/` e `resultados/`.
- Manter backup de entrada/saída antes de cada carga.
- A validação e a revisão de `resultados/fila_revisao.csv` devem ser parte do
  fluxo de homologação.
