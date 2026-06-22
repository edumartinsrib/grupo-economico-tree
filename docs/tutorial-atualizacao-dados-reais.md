# Tutorial para atualizar com dados reais e recarregar a árvore

Este passo a passo mostra como **reaproveitar a mesma instalação** com uma nova entrega de dados reais.

## O que eu preciso ter pronto

1. Pasta com os 4 arquivos abaixo, com exatamente estes nomes:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

2. Os arquivos devem estar em UTF-8 e separados por `;` (ponto e vírgula).

## 1) Atualizar dados reais e gerar tudo de novo (recomendado)

Use esse fluxo quando você recebeu uma nova entrega completa.

```bash
mkdir -p /tmp/entrega_real
cp /origem/stg_pessoa_fisica_atual_202606191707.csv /tmp/entrega_real/
cp /origem/denodo_base_cadastral.csv /tmp/entrega_real/
cp /origem/stg_cadastro_socio_pj_202606191707.csv /tmp/entrega_real/
cp /origem/mv_movimentacoes.csv /tmp/entrega_real/

cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

O que este fluxo faz:

- Faz backup automático de `dados/` e `resultados/` em `backups/reprocessamento_<data>/`.
- Copia os 4 CSVs para `dados/`.
- Valida cabeçalhos mínimos esperados.
- Reprocessa os arquivos, regenerando `resultados/grafo_resultado.sqlite`.
- Compila o frontend (`npm run build`) ao final.

Parâmetros úteis:

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-validation
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-build
```

## 1.1) Fluxo curto "reutilizar sem trocar nome dos arquivos"

Quando você já recebeu uma nova entrega com os **mesmos nomes de arquivo** e quer apenas substituir os dados antigos:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree

# manter o que está hoje como backup
ts=$(date +%Y%m%d_%H%M%S)
mkdir -p "backups/manual_${ts}"
cp -r dados "backups/manual_${ts}/"
cp -r resultados "backups/manual_${ts}/"

# substituir os 4 arquivos
cp /origem/stg_pessoa_fisica_atual_202606191707.csv dados/
cp /origem/denodo_base_cadastral.csv dados/
cp /origem/stg_cadastro_socio_pj_202606191707.csv dados/
cp /origem/mv_movimentacoes.csv dados/

# recompor tudo e reconstruir API/Frontend
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 2) Reprocessar a árvore sem trocar arquivos

Se os 4 arquivos já estiverem em `dados/` com os nomes corretos e você só quiser recalcular:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Sem rebuild (mais rápido):

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean
```

## 3) Atalhos rápidos (npm)

```bash
npm run validate:data    # valida arquivos de entrada em dados/
npm run check:data       # valida e encerra sem processar
npm run process:data     # processa sem rebuild
npm run refresh:data     # valida + limpa + processa + rebuild
```

## 4) Conferir se a recarga foi aplicada

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()

print("\nResumo:")
print(open("resultados/relatorio_analise.md", encoding="utf-8").read()[:1800])
print("\nFila de revisão (topo):")
print(open("resultados/fila_revisao.csv", encoding="utf-8").read().splitlines()[:12])
PY
```

## 5) Rollback (voltar para versão anterior)

```bash
ls -1 backups | grep reprocessamento_ | tail -n 5
ts=YYYYMMDD_HHMMSS
cp backups/reprocessamento_$ts/dados/* dados/
cp backups/reprocessamento_$ts/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --process --clean
```

## 6) Subir os serviços da árvore

```bash
npm run backend   # API em http://localhost:8000
npm run dev       # interface em http://localhost:5173
```

## 8) Reprocessar após mudança manual (toda a árvore)

Sempre que você atualizar os CSVs e quiser forçar a árvore completa:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Esse comando recalcula:
- Entidades
- Vínculos
- Grupos
- Membros dos grupos
- Relações entre grupos
- Fila de revisão
- Agregações financeiras

Ao final, recarregue o frontend. A árvore em memória é recalculada sob demanda e
pode crescer a partir do nó selecionado sem perder os dados de revisão e regras.

## 7) Boas práticas para produção real

- Não versionar arquivos reais sensíveis (`git add`/`git commit` destes CSVs).
- Manter uma pasta de entrega imutável (não editar os CSVs recebidos).
- Guardar a pasta `backups/` até a validação ser concluída.
- Revisar `resultados/fila_revisao.csv` e corrigir inconsistências críticas antes de uso operacional.
