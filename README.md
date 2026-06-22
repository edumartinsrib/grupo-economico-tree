# Grupo Economico Tree

Massa de teste ficticia e deterministica para analise de grupos economicos em grafo.

O projeto contem:

- `scripts/gerar_csvs_teste.py`: gerador dos CSVs de teste.
- `scripts/construir_rede_grupos.py`: processador que gera entidades, vinculos, grupos, membros, fila de revisao, agregacoes e SQLite.
- `dados/*.csv`: arquivos gerados para exercitar regras de entidade, familia, sociedade, movimentacoes financeiras e revisao.
- `resultados/*.csv`: tabelas processadas consumidas pelo frontend.
- `docs/tutorial-atualizacao-dados-reais.md`: passo a passo para substituir os CSVs por dados reais e reprocessar a arvore.

Os nomes, documentos, emails, telefones e enderecos foram criados para teste e usam dominios/intervalos sinteticos.

## Gerar os CSVs

```bash
npm run generate:test-data
```

Os arquivos sao gravados em `dados/`.

Comando equivalente:

```bash
python3 scripts/gerar_csvs_teste.py
```

## Reprocessar a rede (dados de teste)

```bash
npm run process:data
```

Esse comando le os quatro CSVs de `dados/` e sobrescreve as saidas em
`resultados/`, incluindo `resultados/grafo_resultado.sqlite` e
`resultados/relatorio_analise.md`.

Comandos úteis:

```bash
npm run validate:data
npm run check:data
npm run refresh:data
npm run reprocess
```

## Usar dados reais

Use dados reais com segurança e controle de rastreabilidade:

```text
docs/tutorial-atualizacao-dados-reais.md
```

Fluxo resumido (dados reais):

1. Copiar os quatro CSVs reais para `dados/` com os nomes esperados pelo script.
2. Rodar `npm run validate:data`.
3. Rodar `npm run refresh:data` para recomputar tudo e validar build.
4. Conferir `resultados/relatorio_analise.md` e `resultados/fila_revisao.csv`.
5. Abrir o frontend com `npm run dev`.

Consulte também:

`docs/tutorial-atualizacao-dados-reais.md`

Nao publique `dados/` nem `resultados/` com dados reais em repositorios publicos.

## Fluxo operacional recomendado (produtivo)

1. Mantenha uma cópia dos sintéticos (`dados/`) antes da troca.
2. Substitua os arquivos em `dados/` pelos CSVs reais (nomes fixos).
3. Rode:

```bash
npm run process:data
```

4. Valide:

```bash
wc -l resultados/*.csv
sed -n '1,120p' resultados/relatorio_analise.md
sed -n '1,120p' resultados/fila_revisao.csv
```

5. Abra:

```bash
npm run dev
```

6. Para reprocessar tudo em um comando (inclui compilação do frontend):

```bash
npm run reprocess
```

7. Para voltar ao ambiente de testes:

```bash
git restore dados resultados
npm run process:data
npm run build
```

## Comandos úteis de operação real

```bash
npm run validate:data   # valida somente os 4 CSVs de entrada
npm run process:data    # processa e atualiza as saídas em resultados/
npm run refresh:data    # valida + limpa saídas + recompila o frontend
npm run check:data      # apenas valida
```
