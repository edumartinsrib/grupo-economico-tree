# Tutorial: atualização para dados reais e reprocessamento completo da árvore

Este projeto foi criado com dados sintéticos para demonstração.  
Para usar dados reais da sua instituição, você deve substituir os 4 CSVs de entrada em `dados/`, processar tudo de novo e validar o relatório de qualidade antes de usar os resultados.

## 1) O que o projeto precisa para funcionar

- `dados/stg_pessoa_fisica_atual_202606191707.csv`
- `dados/denodo_base_cadastral.csv`
- `dados/stg_cadastro_socio_pj_202606191707.csv`
- `dados/mv_movimentacoes.csv`

O script de processamento espera **exatamente esses nomes**.  
Seus arquivos reais precisam estar em **UTF-8** e com separador `;`.

Observação importante: CPF e CNPJ devem continuar como texto (`string`), não como número.

## 2) Segurança e compliance antes de manipular

1. Não commitar `dados/` nem `resultados/` com dados reais.
2. Trabalhe primeiro em cópia local protegida.
3. Se a máquina for compartilhada, garanta permissões restritas na pasta `dados/`.
4. Não use `git add dados resultados` com arquivo real.

## 3) Preparar ambiente (antes de substituir)

```bash
cd /home/eduardo/Documents/002-projetos/grupo-economico-tree
mkdir -p backups/dados-sinteticos-$(date +%Y%m%d-%H%M%S)
cp dados/*.csv backups/dados-sinteticos-$(date +%Y%m%d-%H%M%S)/
```

Opcional (se quiser manter a saída atual para comparação):

```bash
mkdir -p backups/resultados-anteriores-$(date +%Y%m%d-%H%M%S)
cp -r resultados/*.csv resultados/relatorio_analise.md backups/resultados-anteriores-$(date +%Y%m%d-%H%M%S)/
```

## 4) Substituir arquivos de entrada

Copie os quatro CSVs reais para `dados/` com os nomes abaixo:

```bash
cp /caminho/real/stg_pessoa_fisica_atual_202606191707.csv dados/
cp /caminho/real/denodo_base_cadastral.csv dados/
cp /caminho/real/stg_cadastro_socio_pj_202606191707.csv dados/
cp /caminho/real/mv_movimentacoes.csv dados/
```

Confirme que estão com os cabeçalhos esperados:

```bash
head -1 dados/stg_pessoa_fisica_atual_202606191707.csv
head -1 dados/denodo_base_cadastral.csv
head -1 dados/stg_cadastro_socio_pj_202606191707.csv
head -1 dados/mv_movimentacoes.csv
```

## 5) Validar pré-processamento rápido (recomendado)

Use este script simples para checar cabeçalho e encoding do pacote de entrada:

```bash
python3 - <<'PY'
import csv
import pathlib
import sys

root = pathlib.Path("dados")
required = {
    "stg_pessoa_fisica_atual_202606191707.csv": {"cpf_cnpj", "nome_pessoa", "dat_nascimento", "nome_pessoa_normalizado"},
    "denodo_base_cadastral.csv": {"cpf_cnpj", "cod_conglomerado", "status_conta"},
    "stg_cadastro_socio_pj_202606191707.csv": {"cnpj_associado", "cpf_cnpj_socio", "per_capital"},
    "mv_movimentacoes.csv": {"cpf_cnpj_origem", "cpf_cnpj_destino", "competencia_inicial", "competencia_final", "qtd_movimentacoes"},
}

for name, cols in required.items():
    path = root / name
    try:
        with path.open(encoding="utf-8", newline="") as f:
            header = set(next(csv.reader(f, delimiter=";")))
    except FileNotFoundError:
        print(f"ERRO: arquivo ausente -> {path}")
        sys.exit(1)

    missing = cols - header
    if missing:
        print(f"ERRO: {name} sem colunas obrigatórias: {sorted(missing)}")
        sys.exit(1)
    print(f"OK: {name}")

print("Conjunto de entrada validado com sucesso.")
PY
```

## 6) Reprocessar a rede e a árvore (fluxo completo)

### Opção 1 — apenas recalcular dados (recomendado para validação incremental)

```bash
npm run process:data
```

### Opção 2 — recalcular + validar build do frontend

```bash
npm run reprocess
```

### Opção 3 — recomputação limpa (remove saída antiga antes de gerar)

```bash
rm -f resultados/entidades.csv resultados/vinculos.csv resultados/grupos.csv resultados/membros_grupo.csv \
  resultados/relacoes_entre_grupos.csv resultados/fila_revisao.csv resultados/agregacoes_financeiras_grupos.csv \
  resultados/relatorio_analise.md resultados/grafo_resultado.sqlite
npm run process:data
```

## 7) O que validar depois do processamento

Confira:

```bash
wc -l resultados/entidades.csv resultados/vinculos.csv resultados/grupos.csv resultados/fila_revisao.csv
sed -n '1,120p' resultados/relatorio_analise.md
sed -n '1,120p' resultados/fila_revisao.csv
```

Validação em SQLite (opcional):

```bash
sqlite3 resultados/grafo_resultado.sqlite ".tables"
sqlite3 resultados/grafo_resultado.sqlite "select tipo_grupo, count(*) from grupos group by tipo_grupo;"
sqlite3 resultados/grafo_resultado.sqlite "select codigo_alerta, count(*) from fila_revisao group by codigo_alerta order by count(*) desc;"
```

## 8) Abrir a árvore com dados reais

```bash
npm run dev
```

URL local:

```text
http://localhost:5173/
```

Comportamento importante:

- A árvore sempre lê `resultados/`.
- Troca de arquivo em `dados/` não reflete no app até executar `npm run process:data` novamente.
- No modo de árvore:
  - clique nos `+` para abrir uma perna;
  - arraste o canvas para acompanhar grandes componentes;
  - use **Mostrar vínculos indiretos** para incluir/excluir evidências fracas antes de interpretar estrutura.

## 9) Checklist operacional antes de uso analítico

- Conferir a coluna de data de corte no relatório.
- Conferir conflitos em `resultados/fila_revisao.csv`.
- Revisar vínculos com baixa confiança e vínculos sem fonte robusta.
- Validar que CPFs/CNPJs estão normalizados e sem duplicação indevida.
- Confirmar que documentos inválidos foram marcados com revisão.

## 10) Voltar para os dados de teste do repositório

```bash
git restore dados resultados
npm run process:data
npm run build
```

Esse comando descarta os arquivos reais da cópia local e retorna ao estado de treino.  
Use apenas se você não quiser manter a base real nesta pasta local.
