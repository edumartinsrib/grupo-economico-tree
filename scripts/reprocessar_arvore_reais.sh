#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SOURCE_DIR=""
SKIP_VALIDATION=false
SKIP_BUILD=false

usage() {
  cat <<'EOF'
Uso:
  reprocessar_arvore_reais.sh [opcoes] /caminho/para/lote

Opcoes:
  --skip-validation  Pula a validacao de entrada.
  --skip-build       Pula o npm build (apenas gera resultados).
  --help             Exibe esta ajuda.

Arquivos obrigatorios no lote:
  stg_pessoa_fisica_atual_202606191707.csv
  denodo_base_cadastral.csv
  stg_cadastro_socio_pj_202606191707.csv
  mv_movimentacoes.csv

Arquivo opcional no lote:
  denodo_pessoa_grupo.csv

Exemplos:
  reprocessar_arvore_reais.sh /tmp/entrega_real
  reprocessar_arvore_reais.sh --skip-build /tmp/entrega_real
  reprocessar_arvore_reais.sh --skip-validation /tmp/entrega_real

Via npm:
  npm run process:real -- /tmp/entrega_real
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-validation)
      SKIP_VALIDATION=true
      ;;
    --skip-build)
      SKIP_BUILD=true
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      if [[ -z "${SOURCE_DIR}" ]]; then
        SOURCE_DIR="$1"
      else
        echo "Parametro invalido ou duplicado: ${1}" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
  shift
done

if [[ -z "${SOURCE_DIR}" ]]; then
  echo "Diretorio de lote nao informado." >&2
  usage >&2
  exit 1
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Diretorio de entrada invalido: ${SOURCE_DIR}" >&2
  exit 1
fi

REQUIRED=(
  "stg_pessoa_fisica_atual_202606191707.csv"
  "denodo_base_cadastral.csv"
  "stg_cadastro_socio_pj_202606191707.csv"
  "mv_movimentacoes.csv"
)

for arquivo in "${REQUIRED[@]}"; do
  if [[ ! -f "${SOURCE_DIR}/${arquivo}" ]]; then
    echo "Arquivo ausente no lote: ${arquivo}" >&2
    exit 1
  fi
done

TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${ROOT_DIR}/backups/reprocessamento_${TS}"
mkdir -p "${BACKUP_DIR}/dados" "${BACKUP_DIR}/resultados"

cp "${ROOT_DIR}/dados"/*.csv "${BACKUP_DIR}/dados/"
cp "${ROOT_DIR}/resultados"/* "${BACKUP_DIR}/resultados/" 2>/dev/null || true

cd "${ROOT_DIR}"

echo "Reprocessamento iniciado: lote=${SOURCE_DIR}"
if [[ "${SKIP_VALIDATION}" == true ]]; then
  echo "Validacao de entrada desativada por argumento."
else
  python3 scripts/reprocessar_dados_reais.py --input-dir "${SOURCE_DIR}" --check-only
fi

ARGS=(--input-dir "${SOURCE_DIR}" --process --clean --print-stats)
if [[ "${SKIP_VALIDATION}" == true ]]; then
  ARGS+=(--skip-validation)
fi

if [[ "${SKIP_BUILD}" == true ]]; then
  echo "Modo rapido: sem build do frontend."
else
  ARGS+=(--rebuild)
fi

python3 scripts/reprocessar_dados_reais.py "${ARGS[@]}"

echo "Reprocessamento concluido."
echo "Backup do estado anterior: ${BACKUP_DIR}"
echo "Banco sqlite atualizado: resultados/grafo_resultado.sqlite"
echo "Para visualizar:"
echo "  npm run backend"
echo "  npm run dev"
