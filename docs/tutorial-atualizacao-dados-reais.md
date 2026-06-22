# Atualização com dados reais e reprocessamento completo da árvore

Este projeto já roda com os CSVs de teste. Para reutilizar com dados reais, o fluxo
é: **substituir os 4 arquivos de entrada → validar → reprocessar → recarregar a árvore**.

## 1) O que você precisa ter pronto

- 1 pasta com os 4 arquivos recebidos:
  - `stg_pessoa_fisica_atual_202606191707.csv`
  - `denodo_base_cadastral.csv`
  - `stg_cadastro_socio_pj_202606191707.csv`
  - `mv_movimentacoes.csv`
- Encoding `UTF-8` e separador `;`
- Projeto já inicializado na pasta:
  - `/home/eduardo/Documents/002-projetos/grupo-economico-tree`

## 2) Reprocessamento completo (recomendado)

Use esse fluxo toda vez que vier uma nova entrega completa:

```bash
mkdir -p /tmp/entrega_real
cp /origem/stg_pessoa_fisica_atual_202606191707.csv /tmp/entrega_real/
cp /origem/denodo_base_cadastral.csv /tmp/entrega_real/
cp /origem/stg_cadastro_socio_pj_202606191707.csv /tmp/entrega_real/
cp /origem/mv_movimentacoes.csv /tmp/entrega_real/

cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real
```

Esse script faz:

1. backup de `dados/` e `resultados/` em `backups/reprocessamento_<data>/`
2. valida se os 4 arquivos existem e têm cabeçalhos mínimos esperados
3. substitui os arquivos em `dados/`
4. executa: `python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild`
5. reconstrói `resultados/grafo_resultado.sqlite` e `npm run build`

### Opções úteis

```bash
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-validation
scripts/reprocessar_arvore_reais.sh /tmp/entrega_real --skip-build
```

## 3) Reprocessar a árvore sem trocar arquivos

Se os 4 CSVs já estiverem em `dados/` e você só quiser recalcular tudo:

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Sem rebuild (mais rápido, só backend):

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean
```

## 4) Comandos rápidos

```bash
npm run validate:data    # apenas valida os 4 CSVs de dados/
npm run check:data       # validação + saída sem processamento
npm run process:data     # processa a rede sem build
npm run refresh:data     # valida + limpa + processa + build
python3 scripts/construir_rede_grupos.py # execução direta do motor
```

## 5) Confirmar que a recarga deu certo

1. Validar contagens por tabela:

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("resultados/grafo_resultado.sqlite")
for t in ["entidades", "vinculos", "grupos", "membros_grupo", "relacoes_entre_grupos", "fila_revisao"]:
    print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY
```

2. Revisar resumo e fila de revisão:

```bash
sed -n '1,120p' resultados/relatorio_analise.md
sed -n '1,120p' resultados/fila_revisao.csv
```

3. Subir serviços:

```bash
npm run backend   # http://localhost:8000
npm run dev       # http://localhost:5173
```

## 6) Rollback rápido

Sempre que precisar voltar para o estado anterior:

```bash
ls -1 backups | grep reprocessamento_ | tail -n 5
ts=YYYYMMDD_HHMMSS
rm -rf dados resultados
cp -r backups/reprocessamento_$ts/dados dados
cp -r backups/reprocessamento_$ts/resultados resultados
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 7) Boas práticas com dados reais

- Não versionar CSVs reais.
- Manter a pasta de entrega recebida como imutável.
- Validar `resultados/fila_revisao.csv` antes de qualquer decisão operacional.
- Salvar backups entre versões (`backups/reprocessamento_*`) até o fechamento.
