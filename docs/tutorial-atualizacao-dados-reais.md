# Tutorial: atualizar com dados reais e reprocessar a árvore

Este projeto foi preparado para ser reutilizado com novas bases reais, mantendo o mesmo fluxo de geração de saída (`resultados/*`) e da visualização.

## 1) Arquivos de entrada obrigatórios

Os 4 CSVs devem existir em `dados/` com os nomes:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

Formato esperado: `;` (ponto e vírgula), UTF-8.

## 2) Segurança e operação

- **Não commit** arquivos reais de produção.
- Sempre valide antes de processar.
- Sempre faça backup da pasta `dados/` e `resultados/` antes da carga.
- A validação não é punitiva para campos ausentes, mas exige headers mínimos esperados.

## 3) Atualizar com uma nova entrega de dados

1. Copie os arquivos da entrega para uma pasta temporária:

```bash
mkdir -p /tmp/entrega_real
# ...cole aqui os 4 CSVs
```

2. Rode o fluxo operacional (com backup automático):

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

Opcional:
- `--skip-validation` (pula checagem de headers)
- `--skip-build` (sem `vite build` no final)

Exemplo sem build (apenas dados + sqlite):

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-build
```

## 4) Fluxo manual (alternativo)

Se você preferir passos separados:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree

# 1) Validar somente entrada
python3 scripts/reprocessar_dados_reais.py

# 2) Reprocessar tudo com limpeza e build
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Atalhos npm:

```bash
npm run validate:data    # valida headers mínimos
npm run process:data     # executa construtor sem rebuild
npm run refresh:data     # valida + limpa + processa + build
```

## 5) Reprocessar “toda a árvore” (sem trocar arquivos)

Depois de já ter os CSVs atualizados em `dados/`, rode:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Isso regenera:

- `resultados/entidades.csv`
- `resultados/vinculos.csv`
- `resultados/grupos.csv`
- `resultados/membros_grupo.csv`
- `resultados/relacoes_entre_grupos.csv`
- `resultados/fila_revisao.csv`
- `resultados/agregacoes_financeiras_grupos.csv`
- `resultados/relatorio_analise.md`
- `resultados/grafo_resultado.sqlite`

## 6) Conferência pós-reprocessamento

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "fila_revisao", "relacoes_entre_grupos"]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
PY

sed -n '1,140p' resultados/relatorio_analise.md
sed -n '1,120p' resultados/fila_revisao.csv
wc -l resultados/entidades.csv resultados/vinculos.csv resultados/grupos.csv
```

## 7) Restaurar versão anterior (rollback)

```bash
ls -1 backups | grep reprocessamento_ | tail -n 5
ts=YYYYMMDD_HHMMSS  # timestamp exibido no backup
cp backups/reprocessamento_$ts/dados/* dados/
cp backups/reprocessamento_$ts/resultados/* resultados/
npm run process:data
```

## 8) Iniciar a visualização

- Backend: `npm run backend`
- Frontend: `npm run dev`

## 9) O que muda para a árvore depois da recarga

- A árvore passa a refletir os vínculos novos dos arquivos de entrada.
- A navegação permite expansão progressiva por perna (cima/baixo/toda).
- O painel de detalhes da entidade atualiza conforme a raiz/seleção.

