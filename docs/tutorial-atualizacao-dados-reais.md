# Tutorial: Atualizar dados reais e reprocessar a árvore

Este projeto foi feito para rodar primeiro com dados sintéticos de teste e depois com dados reais.

Abaixo está o fluxo operacional para **substituir os dados de entrada** e **reprocessar toda a árvore** (entidades, vínculos, grupos, agregações financeiras e revisão).

## 1) Pré-requisitos

- Estar na raiz do projeto: `/home/eduardo/Documents/002-projetos/grupo-economico-tree`.
- Python 3.8+ e Node.js 20+ instalados.
- Dependências já instaladas (`npm install` já executado anteriormente).
- Banco da árvore anterior em `resultados/grafo_resultado.sqlite` pode ser sobrescrito durante o reload.

## 2) Formato mínimo do pacote de entrada

A pasta de entrada precisa conter **exatamente** estes 4 CSVs com `;`:

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

Camadas mínimas exigidas na validação:

- **CPF/CNPJ**, nome e data de nascimento em `stg_pessoa_fisica_atual_...`.
- **CPF/CNPJ**, `cod_conglomerado` e `status_conta` em `denodo_base_cadastral`.
- `cnpj_associado`, `cpf_cnpj_socio` e `per_capital` em `stg_cadastro_socio_pj`.
- `cpf_cnpj_origem`, `cpf_cnpj_destino`, `competencia_inicial`, `competencia_final`, `qtd_movimentacoes`, `vlr_total_transferido` em `mv_movimentacoes`.

> Observação: a validação é operacional (nome das colunas e presença de arquivos),
> não valida regras semânticas completas.

> Dica: para reuso com base real, mantenha os nomes das colunas exatamente como esperado e use cópia física dos arquivos, sem renomeação.

## 3) Montar uma pasta de lote

Use um diretório novo (idealmente com timestamp) para não misturar lotes.

```bash
LOTE_DIR=/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
```

> Dica operacional: nomeie a pasta com timestamp para rastreabilidade.

## 4) Validar o lote

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Se tiver sucesso, segue para o reprocessamento.

## 5) Reprocessar toda a árvore (fluxo recomendado)

### Opção completa (validação + backup + rebuild)

```bash
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Esse comando executa:

1. valida o pacote de entrada;
2. cria backup de `dados/` e `resultados/` em `backups/reprocessamento_<data>/`;
3. sobrescreve `dados/` com o lote validado;
4. limpa saídas anteriores;
5. roda `python3 scripts/construir_rede_grupos.py` (rebuild completo da árvore);
6. roda `npm run build` para atualizar frontend estático.

Depois dessa etapa, reinicie a API para a versão nova do grafo entrar em vigor:

```bash
npm run backend
```

## 6) Fluxo contínuo de atualização (reuso diário)

Para repetir a recarga em outro lote real, use:

```bash
LOTE_DIR=/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Em seguida, suba a visualização novamente:

```bash
npm run dev
```

### Opção rápida (sem build)

Use em homologação inicial quando os dados ainda estão em teste:

```bash
scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"
```

### Ignorar validação (somente após fluxo já aprovado)

```bash
scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"
```

## 7) Reprocessar sem pasta de lote

Se os 4 arquivos já estão em `dados/`, execute diretamente:

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

Opcional: sem build para checagens rápidas

```bash
python3 scripts/reprocessar_dados_reais.py --process --clean
```

Também há atalho npm:

```bash
npm run process:real -- "$LOTE_DIR"
```

## 8) Validação pós-processamento (checklist)

### 7.1 Contagens por tabela

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('resultados/grafo_resultado.sqlite')
for t in ['entidades', 'vinculos', 'grupos', 'membros_grupo', 'relacoes_entre_grupos', 'fila_revisao']:
    print(f"{t:22} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
conn.close()
PY
```

Também verifique no navegador:

```bash
curl -s http://127.0.0.1:8000/api/metadata
curl -s http://127.0.0.1:8000/api/health
```

### 7.2 Outputs importantes

- `resultados/entidades.csv`
- `resultados/vinculos.csv`
- `resultados/grupos.csv`
- `resultados/membros_grupo.csv`
- `resultados/relacoes_entre_grupos.csv`
- `resultados/relatorio_analise.md`
- `resultados/fila_revisao.csv`

> Em produção, a revisão de alertas em `fila_revisao.csv` costuma ter prioridade sobre o ajuste estético da árvore.

### 7.3 Conferir serviços

```bash
npm run backend
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/metadata
```

Saída de saúde esperada: `{"status":"ok","db_status":"available"}`.

Depois rode o frontend:

```bash
npm run dev
```

## 9) Iniciar a árvore atualizada no frontend

1. Busque uma entidade pelo CPF/CNPJ (ou nome).
2. Abra a árvore dessa entidade.
3. Valide visualmente grupos, vínculos e alertas de revisão.

## 10) Rollback de segurança

O fluxo anterior cria backup automático em:

- `backups/reprocessamento_AAAA_MMDD_HHMMSS/dados`
- `backups/reprocessamento_AAAA_MMDD_HHMMSS/resultados`

Para restaurar:

```bash
TS=AAAA_MMDD_HHMMSS
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
python3 scripts/reprocessar_dados_reais.py --process --clean --rebuild
```

## 11) Checklist de operação

- Não versionar dados reais em `dados/` e `resultados/`.
- Fazer backup antes de cada recarga.
- Não pular validação na primeira carga de um novo lote.
- Revisar `resultados/fila_revisao.csv` antes de homologação.
- Se a árvore parecer insuficiente, reprocessar com ajuste de `scripts/construir_rede_grupos.py` e repetir esse fluxo.

## 12) Reuso com novos lotes sem reinstalar

- Não é necessário alterar código para trocar massa.
- Copie apenas os 4 arquivos para nova pasta, valide, execute o script de reprocessamento e reinicie `backend` + `dev`.
- Os arquivos reais não devem entrar no versionamento do Git.
