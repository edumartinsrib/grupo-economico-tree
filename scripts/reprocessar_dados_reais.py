#!/usr/bin/env python3
"""Ferramenta operacional para validar e recomputar a árvore com dados reais.

Fluxo:
  - valida que os 4 CSVs esperados existem em dados/
  - valida as colunas mínimas para cada arquivo
  - opcionalmente limpa outputs antigos, processa e recompila o frontend

A validação é mínima e prática para operação: cabeçalhos e encoding UTF-8.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "dados"
OUT_DIR = ROOT / "resultados"


REQUIRED_FILES = {
    "stg_pessoa_fisica_atual_202606191707.csv": {
        "cpf_cnpj",
        "nome_pessoa",
        "nome_pessoa_normalizado",
        "dat_nascimento",
    },
    "denodo_base_cadastral.csv": {
        "cpf_cnpj",
        "cod_conglomerado",
        "status_conta",
    },
    "stg_cadastro_socio_pj_202606191707.csv": {
        "cnpj_associado",
        "cpf_cnpj_socio",
        "per_capital",
    },
    "mv_movimentacoes.csv": {
        "cpf_cnpj_origem",
        "cpf_cnpj_destino",
        "competencia_inicial",
        "competencia_final",
        "qtd_movimentacoes",
        "vlr_total_transferido",
    },
}


OUTPUT_FILES = [
    "entidades.csv",
    "vinculos.csv",
    "grupos.csv",
    "membros_grupo.csv",
    "relacoes_entre_grupos.csv",
    "fila_revisao.csv",
    "agregacoes_financeiras_grupos.csv",
    "relatorio_analise.md",
    "grafo_resultado.sqlite",
]


def _normalize(value: str) -> str:
    return value.strip().lower()


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        header = next(reader)
        return [_normalize(col) for col in header]


def _validate_required_columns(path: Path, required: set[str]) -> list[str]:
    header = _read_header(path)
    current = set(header)
    return sorted(required - current)


def validate_inputs() -> None:
    errors: list[str] = []

    for filename, required in REQUIRED_FILES.items():
        path = DATA_DIR / filename
        if not path.exists():
            errors.append(f"ARQUIVO AUSENTE: {filename}")
            continue

        try:
            missing = _validate_required_columns(path, required)
        except Exception as exc:
            errors.append(f"ERRO AO LER {filename}: {exc}")
            continue

        if missing:
            errors.append(f"{filename}: colunas ausentes -> {', '.join(missing)}")
            continue

        print(f"OK: {filename}")

    if errors:
        print("\nERROS de validação dos arquivos de entrada:")
        for item in errors:
            print(f" - {item}")
        print("\nVerifique cabeçalhos, delimitador ';' e encoding UTF-8.")
        raise SystemExit(1)

    print("\nTodos os 4 arquivos passaram na validação mínima.")


def _run(cmd: list[str]) -> None:
    print(f"\nExecutando: {' '.join(cmd)}")
    process = subprocess.run(cmd, cwd=ROOT)
    if process.returncode != 0:
        raise SystemExit(process.returncode)


def clean_outputs() -> None:
    for filename in OUTPUT_FILES:
        path = OUT_DIR / filename
        if path.exists():
            if path.is_file():
                path.unlink()
            else:
                # relatorio_analise.md é arquivo, demais não: preserva comportamento atual.
                pass


def process_data(clean: bool, rebuild: bool) -> None:
    if clean:
        print("\nLimpando arquivos de saída antigos...")
        clean_outputs()

    _run(["python3", "scripts/construir_rede_grupos.py"])

    if rebuild:
        _run(["npm", "run", "build"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validação e reprocessamento da árvore com dados reais")
    parser.add_argument("--skip-validation", action="store_true", help="Pula a validação dos CSVs de entrada.")
    parser.add_argument("--process", action="store_true", help="Executa o processamento do grafo após validação.")
    parser.add_argument("--clean", action="store_true", help="Remove saídas anteriores antes de processar.")
    parser.add_argument("--rebuild", action="store_true", help="Executa build do frontend após processar.")
    parser.add_argument("--check-only", action="store_true", help="Apenas valida e encerra sem processar.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.skip_validation:
        print("Validando pacote de dados em dados/...")
        validate_inputs()
    else:
        print("Validação de entrada ignorada por argumento.")

    if args.check_only:
        print("Validação concluída. Encerrando por --check-only.")
        return

    if args.process:
        process_data(clean=args.clean, rebuild=args.rebuild)
        print("\nReprocessamento concluído.")
        print("\nPara visualizar, execute: npm run dev")


if __name__ == "__main__":
    main()
