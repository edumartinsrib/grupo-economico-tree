# Reuso com dados reais: atualização e reprocessamento completo da árvore

Este tutorial descreve o fluxo recomendado para substituir os arquivos de teste
por dados reais e reconstruir toda a base da visualização.

## Resumo do processo

1. **Preparar lote** em uma pasta separada (`LOTE_DIR`).
2. **Validar** o lote antes de qualquer sobrescrita.
3. **Reprocessar** com backup automático.
4. **Verificar saída** (banco e arquivos CSV).
5. **Subir serviços** e validar na interface.

## 1) Arquivos mínimos esperados

- `stg_pessoa_fisica_atual_202606191707.csv`
- `denodo_base_cadastral.csv`
- `stg_cadastro_socio_pj_202606191707.csv`
- `mv_movimentacoes.csv`

## 2) Colunas mínimas obrigatórias

| Arquivo | Colunas mínimas obrigatórias |
|---|---|
| stg_pessoa_fisica_atual_202606191707.csv | `cpf_cnpj`, `nome_pessoa`, `nome_pessoa_normalizado`, `dat_nascimento` |
| denodo_base_cadastral.csv | `cpf_cnpj`, `cod_conglomerado`, `status_conta` |
| stg_cadastro_socio_pj_202606191707.csv | `cnpj_associado`, `cpf_cnpj_socio`, `per_capital` |
| mv_movimentacoes.csv | `cpf_cnpj_origem`, `cpf_cnpj_destino`, `competencia_inicial`, `competencia_final`, `qtd_movimentacoes`, `vlr_total_transferido` |

Observações:

- Delimitador usado pelo projeto: `;` (ponto e vírgula).
- Encoding esperado: UTF-8.

## 3) Preparar lote (não sobrescrever o que já existe)

Sempre trabalhe com uma pasta nova por entrega:

```bash
LOTE_DIR=/tmp/entrega_real_$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOTE_DIR"

cp /origem/stg_pessoa_fisica_atual_202606191707.csv "$LOTE_DIR/"
cp /origem/denodo_base_cadastral.csv "$LOTE_DIR/"
cp /origem/stg_cadastro_socio_pj_202606191707.csv "$LOTE_DIR/"
cp /origem/mv_movimentacoes.csv "$LOTE_DIR/"
```

Não misture versões diferentes no mesmo diretório.

## 4) Validar lote antes de processar

```bash
python3 scripts/reprocessar_dados_reais.py --input-dir "$LOTE_DIR" --check-only
```

Esse passo checa existência dos 4 arquivos, cabeçalhos mínimos e leitura dos
arquivos.

## 5) Reprocessamento completo

Use este comando para:

- validar o lote (se não usar `--skip-validation`);
- copiar para `dados/`;
- gerar `resultados/*` novamente;
- salvar backup automático em `backups/reprocessamento_<timestamp>/`;
- e executar build do frontend.

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
scripts/reprocessar_arvore_reais.sh "$LOTE_DIR"
```

Ou por npm:

```bash
npm run process:real -- "$LOTE_DIR"
```

## 6) Opções operacionais

- Pular validação (somente se o lote já for validado em outro ponto):
  ```bash
  scripts/reprocessar_arvore_reais.sh --skip-validation "$LOTE_DIR"
  ```
- Reprocessar sem build (mais rápido para conferência de saída):
  ```bash
  scripts/reprocessar_arvore_reais.sh --skip-build "$LOTE_DIR"
  ```

## 7) Verificação imediata (pós-processamento)

### 7.1 Banco de saída

```bash
python3 - <<'PY'
import sqlite3
from pathlib import Path

path = Path("resultados/grafo_resultado.sqlite")
conn = sqlite3.connect(path)
print(f"Banco: {path}")
for tabela in [
    "entidades",
    "vinculos",
    "grupos",
    "membros_grupo",
    "relacoes_entre_grupos",
    "fila_revisao",
]:
    total = conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    print(f"{tabela}: {total}")
print(f"tamanho_mb: {path.stat().st_size / 1024 / 1024:.3f}")
conn.close()
PY

curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/metadata
```

### 7.2 Arquivos gerados em `resultados/`

- `entidades.csv`
- `vinculos.csv`
- `grupos.csv`
- `membros_grupo.csv`
- `relacoes_entre_grupos.csv`
- `fila_revisao.csv`
- `agregacoes_financeiras_grupos.csv`
- `relatorio_analise.md`

## 8) Conferência na aplicação

```bash
npm run backend  # porta 8000
npm run dev      # frontend
```

Selecione uma pessoa/empresa da nova base e confirme:

- pais e cônjuge;
- filhos e vínculos familiares;
- empresas, sócios e vínculos financeiros.

## 9) Rollback seguro

Se necessário, restaure o último backup gerado pelo script:

```bash
TS=AAAA_MMDD_HHMMSS  # nome da pasta backups/reprocessamento_...
cp -r backups/reprocessamento_${TS}/dados/* dados/
cp -r backups/reprocessamento_${TS}/resultados/* resultados/
```

Em seguida:

```bash
python3 scripts/reprocessar_dados_reais.py --input-dir dados --process --clean
```

## 10) Regras de operação em produção

- Não versionar arquivos reais (`dados/`, `resultados/`) no Git.
- Manter lote original (ou checksum) para trilha de auditoria.
- Tratar `resultados/fila_revisao.csv` como parte obrigatória da análise.
- Preferir lotes por data/horário na pasta de entrada e manter o backup por uma
  janela definida pela operação.
