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

## Processar a rede

```bash
npm run process:data
```

Esse comando le os quatro CSVs de `dados/` e sobrescreve as saidas em
`resultados/`, incluindo `resultados/grafo_resultado.sqlite` e
`resultados/relatorio_analise.md`.

Para processar e validar o build do frontend:

```bash
npm run reprocess
```

## Usar dados reais

Leia o tutorial antes de substituir arquivos:

```text
docs/tutorial-atualizacao-dados-reais.md
```

Resumo do fluxo:

1. Copiar os quatro CSVs reais para `dados/` com os nomes esperados pelo script.
2. Rodar `npm run process:data`.
3. Conferir `resultados/relatorio_analise.md` e `resultados/fila_revisao.csv`.
4. Abrir o frontend com `npm run dev`.

Nao publique `dados/` nem `resultados/` com dados reais em repositorios publicos.
