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
import shutil
import subprocess
import sqlite3
from pathlib import Path


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


def print_processing_stats() -> None:
    db_path = OUT_DIR / "grafo_resultado.sqlite"
    if not db_path.exists():
        print("Arquivo de saída sqlite não encontrado para gerar estatísticas: grafo_resultado.sqlite")
        return

    conn = sqlite3.connect(db_path)
    try:
        print(f"Banco gerado: {db_path} ({db_path.stat().st_size / 1024 / 1024:.3f} MB)")
        for table in [
            "entidades",
            "vinculos",
            "grupos",
            "membros_grupo",
            "relacoes_entre_grupos",
            "fila_revisao",
        ]:
            total = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()[0]
            print(f"  {table}: {total}")
    except Exception as exc:
        print(f"Não foi possível ler estatísticas do banco: {exc}")
    finally:
        conn.close()


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


def validate_inputs(data_dir: Path | None = None) -> None:
    base_dir = data_dir or DATA_DIR

    errors: list[str] = []

    for filename, required in REQUIRED_FILES.items():
        path = base_dir / filename
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

    print(f"\nTodos os 4 arquivos passaram na validação mínima em: {base_dir}")


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


def sync_input_data_to_dados(input_dir: Path) -> None:
    for filename in REQUIRED_FILES:
        source = input_dir / filename
        target = DATA_DIR / filename
        if not source.exists():
            raise FileNotFoundError(f"Arquivo obrigatório ausente no diretório de origem: {source}")
        shutil.copy2(source, target)


def process_data(clean: bool, rebuild: bool, input_dir: Path | None = None) -> None:
    if input_dir is not None and input_dir.resolve() != DATA_DIR.resolve():
        print("\nSincronizando novos arquivos para dados/ antes do processamento.")
        sync_input_data_to_dados(input_dir)

    if clean:
        print("\nLimpando arquivos de saída antigos...")
        clean_outputs()

    _run(["python3", "scripts/construir_rede_grupos.py"])

    if rebuild:
        _run(["npm", "run", "build"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validação e reprocessamento da árvore com dados reais")
    parser.add_argument(
        "--input-dir",
        dest="input_dir",
        default=str(DATA_DIR),
        help="Diretório com os 4 arquivos CSV de entrada. Se diferente de dados/, os arquivos são copiados para dados/.",
    )
    parser.add_argument("--skip-validation", action="store_true", help="Pula a validação dos CSVs de entrada.")
    parser.add_argument("--process", action="store_true", help="Executa o processamento do grafo após validação.")
    parser.add_argument("--clean", action="store_true", help="Remove saídas anteriores antes de processar.")
    parser.add_argument("--rebuild", action="store_true", help="Executa build do frontend após processar.")
    parser.add_argument("--check-only", action="store_true", help="Apenas valida e encerra sem processar.")
    parser.add_argument("--print-stats", action="store_true", help="Exibe estatísticas básicas do grafo gerado.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Diretório de entrada inválido: {input_dir}")
        raise SystemExit(1)

    if not args.skip_validation:
        print(f"Validando pacote de dados em: {input_dir} ...")
        validate_inputs(input_dir)
    else:
        print("Validação de entrada ignorada por argumento.")

    if args.check_only:
        print("Validação concluída. Encerrando por --check-only.")
        return

    if args.process:
        process_data(clean=args.clean, rebuild=args.rebuild, input_dir=input_dir)
        print("\nReprocessamento concluído.")
        if args.print_stats:
            print_processing_stats()
        print("\nPara visualizar, execute: npm run dev")


if __name__ == "__main__":
    main()
