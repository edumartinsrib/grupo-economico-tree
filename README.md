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
```

Fluxo recomendado com dados reais:

```bash
scripts/reprocessar_arvore_reais.sh /caminho/da/entrega_real
```

- `--skip-validation`: pula validação dos cabeçalhos.
- `--skip-build`: processa sem rodar `vite build`.

Consulte o guia completo de operação:

- `docs/tutorial-atualizacao-dados-reais.md`

## Comandos rápidos para recálculo completo

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree

# reprocessa toda a árvore com dados já em dados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild

# reprocessa a partir de uma pasta de entrega
scripts/reprocessar_arvore_reais.sh /caminho/da/entrega_real
```

## Recomendação de segurança

- Não versionar arquivos reais em `dados/` e `resultados/`.
- Manter backup de entrada/saída antes de cada carga.
- A validação e a revisão de `resultados/fila_revisao.csv` devem ser parte do
  fluxo de homologação.
