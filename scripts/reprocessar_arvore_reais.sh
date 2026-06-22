#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SOURCE_DIR=""
SKIP_VALIDATION=false
SKIP_BUILD=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-validation)
      SKIP_VALIDATION=true
      ;;
    --skip-build)
      SKIP_BUILD=true
      ;;
    --help|-h)
      cat <<'EOF'
Uso: reprocessar_arvore_reais.sh [opcoes] /caminho/para/arquivos_reais
Opcao:
  --skip-validation  Pula a validacao de entrada
  --skip-build       Pula o build do frontend apos reprocessar
EOF
      exit 0
      ;;
    *)
      if [[ -z "${SOURCE_DIR}" ]]; then
        SOURCE_DIR="$1"
      else
        echo "Parametro invalido ou duplicado: $1"
        exit 1
      fi
      ;;
  esac
  shift
done

if [[ -z "${SOURCE_DIR}" ]]; then
  echo "Uso: $0 /caminho/para/arquivos_reais"
  echo "Arquivos esperados:"
  echo "  stg_pessoa_fisica_atual_202606191707.csv"
  echo "  denodo_base_cadastral.csv"
  echo "  stg_cadastro_socio_pj_202606191707.csv"
  echo "  mv_movimentacoes.csv"
  exit 1
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Diretorio de origem invalido: ${SOURCE_DIR}"
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
    echo "Arquivo ausente em ${SOURCE_DIR}: ${arquivo}"
    exit 1
  fi
done

TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${ROOT_DIR}/backups/reprocessamento_${TS}"
mkdir -p "${BACKUP_DIR}/dados" "${BACKUP_DIR}/resultados"

cp "${ROOT_DIR}/dados"/*.csv "${BACKUP_DIR}/dados/"
cp "${ROOT_DIR}/resultados"/* "${BACKUP_DIR}/resultados/" 2>/dev/null || true

for arquivo in "${REQUIRED[@]}"; do
  cp "${SOURCE_DIR}/${arquivo}" "${ROOT_DIR}/dados/${arquivo}"
done

cd "${ROOT_DIR}"
if [[ "${SKIP_VALIDATION}" == true ]]; then
  echo "Validacao do pacote de entrada ignorada por opcao."
  ARGS=(--skip-validation)
else
  ARGS=()
fi
if [[ "${SKIP_BUILD}" == true ]]; then
  ARGS+=(--process --clean)
  echo "Iniciando reprocessamento sem build do frontend (modo rapido)."
  python3 scripts/reprocessar_dados_reais.py "${ARGS[@]}" 
else
  ARGS+=(--process --clean --rebuild)
  echo "Iniciando reprocessamento completo com build."
  python3 scripts/reprocessar_dados_reais.py "${ARGS[@]}"
fi

echo "Reprocessamento concluido."
echo "Backup dos dados antigos em: ${BACKUP_DIR}"
echo "Execute: npm run dev"
