# Tutorial: atualizar dados reais e reprocessar a arvore

Este projeto foi publicado com dados sinteticos. Para usar dados reais, substitua os
quatro CSVs de entrada em `dados/`, rode o processamento e abra o frontend. O
frontend nao calcula os grupos em tempo real: ele le os CSVs ja processados em
`resultados/`.

## Aviso de seguranca

O repositorio pode estar em um remoto publico. Dados reais de clientes,
documentos, saldos, telefones, e-mails e enderecos nao devem ser commitados nem
enviados para o GitHub.

Antes de trabalhar com dados reais:

```bash
git status --short
```

Depois de substituir arquivos reais, evite comandos como:

```bash
git add dados resultados
git add .
```

Para publicar apenas codigo ou documentacao, adicione os arquivos
explicitamente, por exemplo:

```bash
git add README.md docs/tutorial-atualizacao-dados-reais.md package.json
```

## Como o fluxo funciona

1. CSVs brutos entram em `dados/`.
2. `scripts/construir_rede_grupos.py` le os quatro arquivos de entrada.
3. O script gera tabelas analiticas em `resultados/`.
4. O frontend React importa os CSVs de `resultados/` e monta a visualizacao.
5. Ao trocar os dados, e necessario reprocessar antes de abrir a arvore.

## Arquivos de entrada obrigatorios

Os nomes dos arquivos estao fixos no script de processamento. Para usar dados
reais, grave exatamente estes nomes em `dados/`:

```text
dados/stg_pessoa_fisica_atual_202606191707.csv
dados/denodo_base_cadastral.csv
dados/stg_cadastro_socio_pj_202606191707.csv
dados/mv_movimentacoes.csv
```

Todos os arquivos devem estar em UTF-8, com separador `;`. CPFs e CNPJs devem
permanecer como texto. Nao converta documentos para numero.

## Colunas esperadas

### `stg_pessoa_fisica_atual_202606191707.csv`

Colunas usadas pelo processador:

```text
id
nome_pessoa
cpf_cnpj
dat_nascimento
tipo_sexo
dat_obito
nom_estado_civil
des_regime_bem
nom_pai
nom_mae
cidade_natal
estado_natal
des_empregador
cpf_cnpj_empregador
des_email
num_ddd
num_telefone
des_logradouro
num_endereco
des_complemento
des_cep
des_bairro
des_cidade
sgl_uf
nome_pessoa_normalizado
nom_mae_normalizado
nom_pai_normalizado
blocking_key
updated_at
```

Outras colunas podem existir e ser preservadas no arquivo, mas nao sao
necessarias para as regras atuais.

### `denodo_base_cadastral.csv`

Colunas usadas pelo processador e pelo frontend:

```text
cpf_cnpj
status_conta
tipo_pessoa
nome_razao_social
data_nascimento
cod_conglomerado
tel_cel
endereco_completo
nome_pessoa_conj
cpf_conj
estado_civil
nome_regime_bem
num_matricula
sld_cred_rural
sld_cred_comercial
sld_cred_direcionados
vlr_limite_cheque_especial
vlr_limite_cartao_liberado
vlr_bens_total
faixa_risco
last_update
saldo
des_pessoa
endereco
numero
complemento
bairro
municipio
estado
cep
```

Campos ambiguos como `cpf_cnpj_titular`, `num_cpf_cnpj`,
`cpf_corrent`, `num_cpf_cnpj_x` e `num_cpf_cnpj_y` podem estar presentes, mas
nao sao usados para criar vinculos sem dicionario de dados.

### `stg_cadastro_socio_pj_202606191707.csv`

Colunas usadas:

```text
id
dat_competencia
cnpj_associado
cpf_cnpj_socio
per_capital
updated_at
```

`per_capital` aceita ponto ou virgula decimal. O script preserva participacoes
invalidas para revisao, em vez de descartar a linha.

### `mv_movimentacoes.csv`

Colunas usadas:

```text
cpf_cnpj_origem
cpf_cnpj_destino
competencia_inicial
competencia_final
qtd_movimentacoes
vlr_total_transferido
qtd_competencias
tipos_operacao
tipos_transferencia
tipos_envolvimento
```

`competencia_inicial` e `competencia_final` devem estar no formato `AAAAMM`,
por exemplo `202601`.

## Atualizar os dados reais

1. Salve uma copia dos dados sinteticos, se quiser voltar ao exemplo depois:

```bash
mkdir -p backups/dados-sinteticos
cp dados/*.csv backups/dados-sinteticos/
```

2. Copie os arquivos reais para `dados/` usando os nomes obrigatorios:

```bash
cp /caminho/real/stg_pessoa_fisica_atual_202606191707.csv dados/
cp /caminho/real/denodo_base_cadastral.csv dados/
cp /caminho/real/stg_cadastro_socio_pj_202606191707.csv dados/
cp /caminho/real/mv_movimentacoes.csv dados/
```

3. Confira se o delimitador e o cabecalho estao corretos:

```bash
head -1 dados/stg_pessoa_fisica_atual_202606191707.csv
head -1 dados/denodo_base_cadastral.csv
head -1 dados/stg_cadastro_socio_pj_202606191707.csv
head -1 dados/mv_movimentacoes.csv
```

## Reprocessar a rede e a arvore

Rode o processamento:

```bash
npm run process:data
```

Comando equivalente:

```bash
python3 scripts/construir_rede_grupos.py
```

O comando deve mostrar um resumo parecido com:

```text
Data de corte: 2026-06-30
Entidades: ...
Vinculos: ...
Grupos: ...
Membros de grupos: ...
Fila de revisao: ...
Saidas em: .../resultados
```

Para reprocessar e validar o frontend em uma unica etapa:

```bash
npm run reprocess
```

Esse comando executa o processamento e depois `npm run build`.

## Saidas geradas

O processamento sobrescreve estes arquivos:

```text
resultados/entidades.csv
resultados/vinculos.csv
resultados/grupos.csv
resultados/membros_grupo.csv
resultados/relacoes_entre_grupos.csv
resultados/fila_revisao.csv
resultados/agregacoes_financeiras_grupos.csv
resultados/grafo_resultado.sqlite
resultados/relatorio_analise.md
```

O arquivo `resultados/relatorio_analise.md` e o melhor ponto inicial para
validar qualidade dos dados, regras aplicadas, colunas nao usadas e explicacao
dos grupos.

## Abrir a arvore no navegador

Depois de reprocessar:

```bash
npm run dev
```

Abra:

```text
http://localhost:5173/
```

Use a busca por CPF, CNPJ, nome, matricula ou grupo. A arvore usa os dados de
`resultados/`, portanto qualquer troca em `dados/` so aparece depois de rodar
novamente `npm run process:data`.

## Validacoes recomendadas

Confira quantidades e alertas:

```bash
wc -l resultados/entidades.csv resultados/vinculos.csv resultados/grupos.csv resultados/fila_revisao.csv
sed -n '1,80p' resultados/relatorio_analise.md
```

Consulte o SQLite gerado:

```bash
sqlite3 resultados/grafo_resultado.sqlite ".tables"
sqlite3 resultados/grafo_resultado.sqlite "select tipo_grupo, count(*) from grupos group by tipo_grupo;"
sqlite3 resultados/grafo_resultado.sqlite "select codigo_alerta, count(*) from fila_revisao group by codigo_alerta order by count(*) desc;"
```

Valide o frontend:

```bash
npm run build
```

## Voltar para os dados sinteticos do repositorio

Se voce substituiu os dados localmente e quer voltar aos arquivos do Git:

```bash
git restore dados resultados
npm run process:data
npm run build
```

Esse comando descarta alteracoes locais em `dados/` e `resultados/`. Use apenas
se nao precisar manter os arquivos reais nessa copia de trabalho.

## Checklist antes de usar dados reais em producao

- Confirmar que os quatro CSVs estao em UTF-8 com separador `;`.
- Confirmar que CPFs/CNPJs foram tratados como texto.
- Confirmar que `updated_at`, `last_update`, `dat_competencia` e
  `competencia_final` existem quando disponiveis, pois influenciam a data de
  corte.
- Revisar `resultados/fila_revisao.csv` antes de tomar decisao operacional.
- Validar grupos grandes, vinculos ambiguos e documentos invalidos.
- Nao publicar `dados/` nem `resultados/` com dados reais em repositorio publico.
