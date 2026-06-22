#!/usr/bin/env python3
"""Gera CSVs de teste para analise de grupos economicos em grafo.

Os dados sao ficticios, deterministicos e desenhados para exercitar regras de
resolucao de entidades, familia, sociedade, movimentos financeiros e revisao.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dados"
EXECUTION_ID = "FULL_TESTE_GRAFO_KYC_20260619_ETL"


SOCIO_PJ_COLUMNS = [
    "id",
    "dat_competencia",
    "cnpj_associado",
    "cpf_cnpj_socio",
    "per_capital",
    "execution_id",
    "updated_at",
]

MOVIMENTACOES_COLUMNS = [
    "cpf_cnpj_origem",
    "cpf_cnpj_destino",
    "competencia_inicial",
    "competencia_final",
    "qtd_registros_agrupados",
    "qtd_movimentacoes",
    "vlr_total_transferido",
    "qtd_competencias",
    "tipos_operacao",
    "tipos_transferencia",
    "tipos_envolvimento",
]

DENODO_COLUMNS = [
    "cpf_cnpj",
    "status_conta",
    "tipo_pessoa",
    "des_segmento",
    "nome_razao_social",
    "dt_renovacao_cadastral",
    "des_email",
    "nucleo",
    "idade",
    "data_nascimento",
    "des_cbo",
    "cod_conglomerado",
    "flg_sexo",
    "tel_cel",
    "endereco_completo",
    "nome_pessoa_conj",
    "cpf_conj",
    "estado_civil",
    "nome_regime_bem",
    "vlr_saldo_atual_capital",
    "num_matricula",
    "dat_associacao",
    "nacionalidade",
    "faixa_principalidade",
    "sld_cred_rural",
    "sld_cred_comercial",
    "sld_cred_direcionados",
    "sld_cred_rural_direc",
    "vlr_limite_cheque_especial",
    "vlr_limite_cartao_liberado",
    "vlr_bens_total",
    "faixa_risco",
    "last_update",
    "saldo",
    "vlr_bem_total",
    "cpf_cnpj_titular",
    "num_cpf_cnpj",
    "cpf_corrent",
    "num_cpf_cnpj_y",
    "des_estado_civil",
    "des_pessoa",
    "num_cpf_cnpj_x",
    "endereco",
    "numero",
    "complemento",
    "bairro",
    "municipio",
    "estado",
    "cep",
    "flg_ativo",
]

PESSOA_FISICA_COLUMNS = [
    "id",
    "cod_cooperativa",
    "des_marca",
    "nome_pessoa",
    "cpf_cnpj",
    "dat_nascimento",
    "tipo_sexo",
    "num_idade",
    "dat_obito",
    "nom_estado_civil",
    "des_regime_bem",
    "nom_pai",
    "nom_mae",
    "cidade_natal",
    "estado_natal",
    "des_ocupacao",
    "des_empregador",
    "cpf_cnpj_empregador",
    "des_email",
    "num_ddd",
    "num_telefone",
    "tpo_endereco",
    "des_logradouro",
    "num_endereco",
    "des_complemento",
    "des_cep",
    "des_bairro",
    "des_cidade",
    "sgl_uf",
    "dat_cadastro",
    "nome_pessoa_normalizado",
    "nom_mae_normalizado",
    "nom_pai_normalizado",
    "primeiro_nome_mae",
    "dat_nascimento_normalizado",
    "hash_linha",
    "blocking_key",
    "execution_id",
    "updated_at",
]


def cpf_from_base(base9: str) -> str:
    digits = [int(c) for c in base9]
    first = (sum(d * w for d, w in zip(digits, range(10, 1, -1))) * 10) % 11
    first = 0 if first == 10 else first
    digits.append(first)
    second = (sum(d * w for d, w in zip(digits, range(11, 1, -1))) * 10) % 11
    second = 0 if second == 10 else second
    digits.append(second)
    return "".join(str(d) for d in digits)


def cnpj_from_base(base12: str) -> str:
    digits = [int(c) for c in base12]
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    first = 11 - (sum(d * w for d, w in zip(digits, weights1)) % 11)
    first = 0 if first >= 10 else first
    digits.append(first)
    weights2 = [6, *weights1]
    second = 11 - (sum(d * w for d, w in zip(digits, weights2)) % 11)
    second = 0 if second >= 10 else second
    digits.append(second)
    return "".join(str(d) for d in digits)


def fmt_dt(value: str) -> str:
    return value


def age_at_cutoff(birth: str) -> str:
    year = int(birth[:4])
    return str(2026 - year)


def normalize_name(value: str) -> str:
    return " ".join(value.upper().split())


def hash_line(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


CPF = {
    "carlos": cpf_from_base("900000001"),
    "maria": cpf_from_base("900000002"),
    "ana": cpf_from_base("900000003"),
    "bruno": cpf_from_base("900000004"),
    "eduardo": cpf_from_base("900000005"),
    "paula": cpf_from_base("900000006"),
    "marcelo": cpf_from_base("900000007"),
    "joao_investidor": cpf_from_base("900000008"),
    "roberto_falecido": cpf_from_base("900000009"),
    "lucia": cpf_from_base("900000010"),
    "marta": cpf_from_base("900000011"),
    "ricardo": cpf_from_base("900000012"),
    "silvia": cpf_from_base("900000013"),
    "claudia": cpf_from_base("900000014"),
    "daniel_a": cpf_from_base("900000015"),
    "daniel_b": cpf_from_base("900000016"),
    "antonio_1": cpf_from_base("900000017"),
    "antonio_2": cpf_from_base("900000018"),
    "filho_antonio": cpf_from_base("900000019"),
    "pedro_jovem": cpf_from_base("900000020"),
    "lucas_jovem": cpf_from_base("900000021"),
    "self_parent": cpf_from_base("900000022"),
    "shared_a": cpf_from_base("900000023"),
    "shared_b": cpf_from_base("900000024"),
    "socio_70": cpf_from_base("900000025"),
    "socio_40": cpf_from_base("900000026"),
}

CNPJ = {
    "holding": cnpj_from_base("901000010001"),
    "servicos": cnpj_from_base("901000020001"),
    "parceiro": cnpj_from_base("901000030001"),
    "joint": cnpj_from_base("901000040001"),
    "excedente": cnpj_from_base("901000050001"),
    "ciclo_a": cnpj_from_base("901000060001"),
    "ciclo_b": cnpj_from_base("901000070001"),
    "externa_sem_cadastro": cnpj_from_base("901000080001"),
    "empregador_pf": cnpj_from_base("901000090001"),
    "auto_socio": cnpj_from_base("901000100001"),
    "movimento_pj": cnpj_from_base("901000110001"),
    "sem_nome": cnpj_from_base("901000120001"),
}

INVALID_CPF = "00000000000"
INVALID_CNPJ = "11111111000111"


def pf_row(
    idx: int,
    key: str,
    nome: str,
    birth: str,
    sexo: str,
    estado_civil: str,
    regime: str,
    pai: str,
    mae: str,
    cidade: str,
    uf: str,
    ocupacao: str,
    empregador: str,
    empregador_cnpj: str,
    email: str,
    ddd: str,
    telefone: str,
    logradouro: str,
    numero: str,
    complemento: str,
    cep: str,
    bairro: str,
    obito: str = "",
    cadastro: str = "2025-10-29 11:49:11",
    updated: str = "2026-06-19 19:44:46.325",
) -> dict[str, str]:
    nome_norm = normalize_name(nome)
    mae_norm = normalize_name(mae)
    pai_norm = normalize_name(pai)
    birth_norm = birth[:10].replace("-", "")
    return {
        "id": str(3_400_000 + idx),
        "cod_cooperativa": str([737, 321, 555, 912][idx % 4]),
        "des_marca": ["LEGADO", "SICREDI", "COOP_TESTE"][idx % 3],
        "nome_pessoa": nome_norm,
        "cpf_cnpj": CPF.get(key, key),
        "dat_nascimento": birth,
        "tipo_sexo": sexo,
        "num_idade": age_at_cutoff(birth),
        "dat_obito": obito,
        "nom_estado_civil": estado_civil,
        "des_regime_bem": regime,
        "nom_pai": pai_norm,
        "nom_mae": mae_norm,
        "cidade_natal": cidade,
        "estado_natal": uf,
        "des_ocupacao": ocupacao,
        "des_empregador": empregador,
        "cpf_cnpj_empregador": empregador_cnpj,
        "des_email": email,
        "num_ddd": ddd,
        "num_telefone": telefone,
        "tpo_endereco": "RESIDENCIAL",
        "des_logradouro": logradouro,
        "num_endereco": numero,
        "des_complemento": complemento,
        "des_cep": cep,
        "des_bairro": bairro,
        "des_cidade": cidade,
        "sgl_uf": uf,
        "dat_cadastro": cadastro,
        "nome_pessoa_normalizado": nome_norm,
        "nom_mae_normalizado": mae_norm,
        "nom_pai_normalizado": pai_norm,
        "primeiro_nome_mae": mae_norm.split()[0] if mae_norm else "",
        "dat_nascimento_normalizado": birth_norm,
        "hash_linha": hash_line(CPF.get(key, key), nome_norm, birth_norm),
        "blocking_key": f"MAE={mae_norm}|PAI={pai_norm}|ANO={birth[:4]}|CID={cidade}",
        "execution_id": EXECUTION_ID,
        "updated_at": updated,
    }


def build_pf_rows() -> list[dict[str, str]]:
    same_addr = ("RUA FAMILIA ALMEIDA", "100", "CASA", "80000001", "CENTRO")
    rows = [
        pf_row(1, "carlos", "Carlos Almeida", "1972-03-10 00:00:00", "MASCULINO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Jose Almeida", "Helena Costa", "CURITIBA", "PR", "ADMINISTRADOR", "ALMEIDA HOLDING LTDA", CNPJ["holding"], "carlos.almeida@teste.local", "41", "999000001", *same_addr),
        pf_row(2, "maria", "Maria Souza Almeida", "1974-08-21 00:00:00", "FEMININO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Pedro Souza", "Olivia Ramos", "CURITIBA", "PR", "CONTADORA", "ALMEIDA SERVICOS LTDA", CNPJ["servicos"], "maria.almeida@teste.local", "41", "999000002", *same_addr),
        pf_row(3, "ana", "Ana Almeida", "1998-05-12 00:00:00", "FEMININO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Carlos Almeida", "Maria Souza Almeida", "CURITIBA", "PR", "ADVOGADA", "ALMEIDA SERVICOS LTDA", CNPJ["servicos"], "ana.almeida@teste.local", "41", "999000003", "RUA DAS FLORES", "210", "APTO 31", "80000002", "BATEL"),
        pf_row(4, "bruno", "Bruno Almeida", "2001-09-30 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Carlos Almeida", "Maria Souza Almeida", "CURITIBA", "PR", "ESTUDANTE", "", "", "bruno.almeida@teste.local", "41", "999000004", *same_addr),
        pf_row(5, "eduardo", "Eduardo Martins", "1996-11-02 00:00:00", "MASCULINO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Osvaldo Martins", "Denise Lima", "LONDRINA", "PR", "ENGENHEIRO", "ALMEIDA SERVICOS LTDA", CNPJ["servicos"], "eduardo.martins@teste.local", "43", "999000005", "RUA DAS FLORES", "210", "APTO 31", "80000002", "BATEL"),
        pf_row(6, "paula", "Paula Almeida", "1978-01-17 00:00:00", "FEMININO", "CASADO(A)", "SEPARACAO TOTAL DE BENS", "Jose Almeida", "Helena Costa", "CURITIBA", "PR", "MEDICA", "CLINICA EXTERNA LTDA", CNPJ["externa_sem_cadastro"], "paula.almeida@teste.local", "41", "999000006", "RUA DO LAGO", "55", "CASA", "80000003", "AHU"),
        pf_row(7, "marcelo", "Marcelo Almeida", "1980-06-25 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Jose Almeida", "Elvira Duarte", "CURITIBA", "PR", "COMERCIANTE", "", "", "marcelo.almeida@teste.local", "41", "999000007", "RUA DO LAGO", "58", "CASA", "80000003", "AHU"),
        pf_row(8, "joao_investidor", "Joao Investidor", "1969-04-01 00:00:00", "MASCULINO", "CASADO(A)", "COMUNHAO UNIVERSAL DE BENS", "Alberto Investidor", "Nair Investidor", "CAMPINAS", "SP", "EMPRESARIO", "COMERCIO PARCEIRO LTDA", CNPJ["parceiro"], "joao.investidor@teste.local", "19", "999000008", "AVENIDA PAULISTA", "1500", "CJ 90", "01310000", "BELA VISTA"),
        pf_row(9, "roberto_falecido", "Roberto Antigo", "1958-02-20 00:00:00", "MASCULINO", "VIUVO(A)", "", "Renato Antigo", "Tereza Antigo", "CASCAVEL", "PR", "EMPRESARIO", "ALMEIDA HOLDING LTDA", CNPJ["holding"], "roberto.antigo@teste.local", "45", "999000009", "RUA HISTORICA", "9", "CASA", "85800000", "CENTRO", obito="2025-03-10 00:00:00"),
        pf_row(10, "lucia", "Lucia Costa", "1984-12-11 00:00:00", "FEMININO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Mario Costa", "Celia Costa", "MARINGA", "PR", "GERENTE", "EMPRESA TESTE X", CNPJ["empregador_pf"], "lucia.costa@teste.local", "44", "999000010", "RUA CONFLITO", "10", "CASA", "87000000", "ZONA 1"),
        pf_row(11, "marta", "Marta Lima", "1985-07-03 00:00:00", "FEMININO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Sergio Lima", "Vera Lima", "MARINGA", "PR", "ANALISTA", "EMPRESA TESTE X", CNPJ["empregador_pf"], "marta.lima@teste.local", "44", "999000011", "RUA CONFLITO", "11", "CASA", "87000000", "ZONA 1"),
        pf_row(12, "ricardo", "Ricardo Dias", "1982-04-14 00:00:00", "MASCULINO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Ronaldo Dias", "Helena Dias", "MARINGA", "PR", "TECNICO", "", "", "ricardo.dias@teste.local", "44", "999000012", "RUA CONFLITO", "12", "CASA", "87000000", "ZONA 1"),
        pf_row(13, "silvia", "Silvia Ramos", "1987-09-09 00:00:00", "FEMININO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Rogerio Ramos", "Irene Ramos", "MARINGA", "PR", "PROFESSORA", "", "", "silvia.ramos@teste.local", "44", "999000013", "RUA CONFLITO", "13", "CASA", "87000000", "ZONA 1"),
        pf_row(14, "claudia", "Claudia Nunes", "1988-01-22 00:00:00", "FEMININO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Valter Nunes", "Nadia Nunes", "MARINGA", "PR", "ARQUITETA", "", "", "claudia.nunes@teste.local", "44", "999000014", "RUA CONFLITO", "14", "CASA", "87000000", "ZONA 1"),
        pf_row(15, "daniel_a", "Daniel Moraes", "1990-05-05 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Paulo Moraes", "Rita Moraes", "JOINVILLE", "SC", "MOTORISTA", "", "", "daniel.moraes.a@teste.local", "47", "999000015", "RUA DUPLICIDADE", "1", "CASA", "89200000", "CENTRO"),
        pf_row(16, "daniel_b", "Daniel Moraes", "1992-05-05 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Paulo Moraes", "Rita Moraes", "JOINVILLE", "SC", "MOTORISTA", "", "", "daniel.moraes.b@teste.local", "47", "999000016", "RUA DUPLICIDADE", "2", "CASA", "89200000", "CENTRO"),
        pf_row(17, "antonio_1", "Antonio Lima", "1962-01-02 00:00:00", "MASCULINO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Raul Lima", "Ivone Lima", "BLUMENAU", "SC", "APOSENTADO", "", "", "antonio.lima1@teste.local", "47", "999000017", "RUA AMBIGUA", "100", "CASA", "89000000", "VELHA"),
        pf_row(18, "antonio_2", "Antonio Lima", "1964-02-03 00:00:00", "MASCULINO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Raul Lima", "Ivone Lima", "BLUMENAU", "SC", "COMERCIANTE", "", "", "antonio.lima2@teste.local", "47", "999000018", "RUA AMBIGUA", "102", "CASA", "89000000", "VELHA"),
        pf_row(19, "filho_antonio", "Felipe Lima", "1995-08-16 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Antonio Lima", "Beatriz Lima", "BLUMENAU", "SC", "VENDEDOR", "", "", "felipe.lima@teste.local", "47", "999000019", "RUA AMBIGUA", "104", "CASA", "89000000", "VELHA"),
        pf_row(20, "pedro_jovem", "Pedro Jovem", "2000-01-01 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Carlos Jovem", "Lara Jovem", "CURITIBA", "PR", "AUXILIAR", "", "", "pedro.jovem@teste.local", "41", "999000020", "RUA IDADE", "77", "CASA", "80000004", "PORTAO"),
        pf_row(21, "lucas_jovem", "Lucas Jovem", "2008-04-01 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Pedro Jovem", "Larissa Jovem", "CURITIBA", "PR", "ESTUDANTE", "", "", "lucas.jovem@teste.local", "41", "999000021", "RUA IDADE", "77", "CASA", "80000004", "PORTAO"),
        pf_row(22, "self_parent", "Self Parent", "1990-10-10 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Self Parent", "Mae Self", "CURITIBA", "PR", "AUTONOMO", "", "", "self.parent@teste.local", "41", "999000022", "RUA SELF", "1", "CASA", "80000005", "CENTRO"),
        pf_row(23, "shared_a", "Nadia Compartilhada", "1989-06-06 00:00:00", "FEMININO", "SOLTEIRO(A)", "", "Pai Nadia", "Mae Nadia", "CAMPINAS", "SP", "ANALISTA", "", "", "contato.compartilhado@teste.local", "19", "999888777", "RUA CONTATO", "500", "APTO 12", "13000000", "CENTRO"),
        pf_row(24, "shared_b", "Otavio Compartilhado", "1986-07-07 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Pai Otavio", "Mae Otavio", "CAMPINAS", "SP", "CONSULTOR", "", "", "contato.compartilhado@teste.local", "19", "999888777", "RUA CONTATO", "500", "APTO 12", "13000000", "CENTRO"),
        pf_row(25, "socio_70", "Helio Excedente", "1979-03-03 00:00:00", "MASCULINO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Pai Helio", "Mae Helio", "LONDRINA", "PR", "EMPRESARIO", "", "", "helio.excedente@teste.local", "43", "999000025", "RUA EXCEDENTE", "70", "CASA", "86000000", "CENTRO"),
        pf_row(26, "socio_40", "Iara Excedente", "1981-04-04 00:00:00", "FEMININO", "CASADO(A)", "COMUNHAO PARCIAL DE BENS", "Pai Iara", "Mae Iara", "LONDRINA", "PR", "EMPRESARIA", "", "", "iara.excedente@teste.local", "43", "999000026", "RUA EXCEDENTE", "40", "CASA", "86000000", "CENTRO"),
        pf_row(27, INVALID_CPF, "Documento Invalido", "1999-09-09 00:00:00", "MASCULINO", "SOLTEIRO(A)", "", "Pai Invalido", "Mae Invalida", "CURITIBA", "PR", "TESTADOR", "", "", "doc.invalido@teste.local", "41", "999000027", "RUA INVALIDA", "0", "", "80000999", "CENTRO"),
    ]
    return rows


def denodo_pf_row(
    pf: dict[str, str],
    *,
    nome: str | None = None,
    birth: str | None = None,
    status: str = "CONTA ATIVA",
    cpf_conj: str = "",
    nome_conj: str = "",
    regime: str | None = None,
    cod_conglomerado: str = "",
    saldo: str = "1500.00",
    risco: str = "Medio 1",
    last_update: str = "2026-06-18 17:35:36.151",
) -> dict[str, str]:
    nome_canonico = normalize_name(nome or pf["nome_pessoa"])
    nascimento = birth or pf["dat_nascimento"].replace(".000", "")
    endereco = f"{pf['des_logradouro']}, {pf['num_endereco']}"
    if pf["des_complemento"]:
        endereco += f", {pf['des_complemento']}"
    return {
        "cpf_cnpj": pf["cpf_cnpj"],
        "status_conta": status,
        "tipo_pessoa": "PF",
        "des_segmento": "PF Urbano",
        "nome_razao_social": nome_canonico,
        "dt_renovacao_cadastral": "2026-01-23 00:00:00.000",
        "des_email": pf["des_email"],
        "nucleo": f"{int(pf['id']) % 900 + 1:03d}",
        "idade": pf["num_idade"] + ".0",
        "data_nascimento": nascimento if nascimento.endswith(".000") else nascimento + ".000",
        "des_cbo": pf["des_ocupacao"].title(),
        "cod_conglomerado": cod_conglomerado,
        "flg_sexo": pf["tipo_sexo"].lower(),
        "tel_cel": pf["num_ddd"] + pf["num_telefone"],
        "endereco_completo": f"{endereco} - {pf['des_bairro']} - {pf['des_cidade']}/{pf['sgl_uf']}",
        "nome_pessoa_conj": normalize_name(nome_conj),
        "cpf_conj": cpf_conj,
        "estado_civil": pf["nom_estado_civil"].title(),
        "nome_regime_bem": regime if regime is not None else pf["des_regime_bem"].title(),
        "vlr_saldo_atual_capital": saldo,
        "num_matricula": f"{int(pf['id']) % 1000000:09d}",
        "dat_associacao": "2017-08-22 00:00:00.000",
        "nacionalidade": "Brasileiro(a)",
        "faixa_principalidade": "Principal",
        "sld_cred_rural": "0.00",
        "sld_cred_comercial": "0.00",
        "sld_cred_direcionados": "0.00",
        "sld_cred_rural_direc": "0.00",
        "vlr_limite_cheque_especial": "600.00",
        "vlr_limite_cartao_liberado": "2500.00",
        "vlr_bens_total": "50000.00",
        "faixa_risco": risco,
        "last_update": last_update,
        "saldo": saldo,
        "vlr_bem_total": "50000.00",
        "cpf_cnpj_titular": "",
        "num_cpf_cnpj": pf["cpf_cnpj"],
        "cpf_corrent": pf["cpf_cnpj"],
        "num_cpf_cnpj_y": "",
        "des_estado_civil": pf["nom_estado_civil"].title(),
        "des_pessoa": nome_canonico,
        "num_cpf_cnpj_x": "",
        "endereco": pf["des_logradouro"],
        "numero": pf["num_endereco"],
        "complemento": pf["des_complemento"],
        "bairro": pf["des_bairro"],
        "municipio": pf["des_cidade"],
        "estado": pf["sgl_uf"],
        "cep": pf["des_cep"],
        "flg_ativo": "S" if status == "CONTA ATIVA" else "N",
    }


def denodo_pj_row(cnpj: str, nome: str, *, status: str = "CONTA ATIVA", saldo: str = "10000.00", risco: str = "Medio 2") -> dict[str, str]:
    return {
        "cpf_cnpj": cnpj,
        "status_conta": status,
        "tipo_pessoa": "PJ",
        "des_segmento": "PJ Empresas",
        "nome_razao_social": nome,
        "dt_renovacao_cadastral": "2026-02-10 00:00:00.000",
        "des_email": f"{nome.lower().replace(' ', '.')}@empresa.local",
        "nucleo": "900",
        "idade": "",
        "data_nascimento": "",
        "des_cbo": "",
        "cod_conglomerado": "99999",
        "flg_sexo": "",
        "tel_cel": "4133000000",
        "endereco_completo": "AVENIDA EMPRESARIAL, 1000 - CENTRO - CURITIBA/PR",
        "nome_pessoa_conj": "",
        "cpf_conj": "",
        "estado_civil": "",
        "nome_regime_bem": "",
        "vlr_saldo_atual_capital": saldo,
        "num_matricula": "",
        "dat_associacao": "2018-01-01 00:00:00.000",
        "nacionalidade": "",
        "faixa_principalidade": "Principal",
        "sld_cred_rural": "0.00",
        "sld_cred_comercial": "25000.00",
        "sld_cred_direcionados": "0.00",
        "sld_cred_rural_direc": "0.00",
        "vlr_limite_cheque_especial": "10000.00",
        "vlr_limite_cartao_liberado": "15000.00",
        "vlr_bens_total": "250000.00",
        "faixa_risco": risco,
        "last_update": "2026-06-18 18:00:00.000",
        "saldo": saldo,
        "vlr_bem_total": "250000.00",
        "cpf_cnpj_titular": "",
        "num_cpf_cnpj": cnpj,
        "cpf_corrent": "",
        "num_cpf_cnpj_y": "",
        "des_estado_civil": "",
        "des_pessoa": nome,
        "num_cpf_cnpj_x": "",
        "endereco": "AVENIDA EMPRESARIAL",
        "numero": "1000",
        "complemento": "",
        "bairro": "CENTRO",
        "municipio": "CURITIBA",
        "estado": "PR",
        "cep": "80000100",
        "flg_ativo": "S" if status == "CONTA ATIVA" else "N",
    }


def build_denodo_rows(pf_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_cpf = {row["cpf_cnpj"]: row for row in pf_rows}
    rows = [
        denodo_pf_row(by_cpf[CPF["carlos"]], cpf_conj=CPF["maria"], nome_conj="Maria Souza Almeida", cod_conglomerado="77701", saldo="12000.00", risco="Medio 1"),
        denodo_pf_row(by_cpf[CPF["maria"]], cpf_conj=CPF["carlos"], nome_conj="Carlos Almeida", cod_conglomerado="77701", saldo="9800.00", risco="Medio 1"),
        denodo_pf_row(by_cpf[CPF["ana"]], cpf_conj=CPF["eduardo"], nome_conj="Eduardo Martins", cod_conglomerado="77701", saldo="4500.00", risco="Baixissimo"),
        denodo_pf_row(by_cpf[CPF["bruno"]], cod_conglomerado="77701", saldo="900.00", risco="Medio 2"),
        denodo_pf_row(by_cpf[CPF["eduardo"]], cpf_conj=CPF["ana"], nome_conj="Ana Almeida", saldo="3800.00", risco="Baixissimo"),
        denodo_pf_row(by_cpf[CPF["paula"]], nome_conj="Roberto Pereira", cpf_conj="", regime="Separacao Total De Bens", saldo="7000.00", risco="Medio 2"),
        denodo_pf_row(by_cpf[CPF["marcelo"]], saldo="1100.00", risco="Alto 2"),
        denodo_pf_row(by_cpf[CPF["joao_investidor"]], cpf_conj=CPF["lucia"], nome_conj="Lucia Costa", saldo="20000.00", risco="Medio 1"),
        denodo_pf_row(by_cpf[CPF["roberto_falecido"]], status="CONTA ATIVA", saldo="5000.00", risco="Alto 2", last_update="2026-06-18 17:35:36.151"),
        denodo_pf_row(by_cpf[CPF["lucia"]], cpf_conj=CPF["joao_investidor"], nome_conj="Joao Investidor", saldo="2500.00"),
        denodo_pf_row(by_cpf[CPF["marta"]], cpf_conj=CPF["ricardo"], nome_conj="Ricardo Dias", saldo="2600.00"),
        denodo_pf_row(by_cpf[CPF["ricardo"]], cpf_conj=CPF["silvia"], nome_conj="Silvia Ramos", saldo="2700.00"),
        denodo_pf_row(by_cpf[CPF["silvia"]], cpf_conj=CPF["ricardo"], nome_conj="Ricardo Dias", saldo="2800.00"),
        denodo_pf_row(by_cpf[CPF["claudia"]], cpf_conj=CPF["ricardo"], nome_conj="Ricardo Dias", saldo="2900.00"),
        denodo_pf_row(by_cpf[CPF["daniel_a"]], nome="Danilo Moraes", birth="1988-05-05 00:00:00", saldo="1300.00"),
        denodo_pf_row(by_cpf[CPF["daniel_b"]], saldo="1400.00"),
        denodo_pf_row(by_cpf[CPF["antonio_1"]], saldo="800.00"),
        denodo_pf_row(by_cpf[CPF["antonio_2"]], saldo="850.00"),
        denodo_pf_row(by_cpf[CPF["filho_antonio"]], saldo="400.00"),
        denodo_pf_row(by_cpf[CPF["pedro_jovem"]], saldo="300.00"),
        denodo_pf_row(by_cpf[CPF["lucas_jovem"]], saldo="50.00"),
        denodo_pf_row(by_cpf[CPF["self_parent"]], saldo="60.00"),
        denodo_pf_row(by_cpf[CPF["shared_a"]], saldo="1700.00"),
        denodo_pf_row(by_cpf[CPF["shared_b"]], saldo="1800.00"),
        denodo_pf_row(by_cpf[CPF["socio_70"]], saldo="2200.00"),
        denodo_pf_row(by_cpf[CPF["socio_40"]], saldo="2300.00"),
        denodo_pf_row(by_cpf[INVALID_CPF], saldo="10.00", risco="Default"),
        denodo_pj_row(CNPJ["holding"], "ALMEIDA HOLDING LTDA", saldo="80000.00", risco="Medio 1"),
        denodo_pj_row(CNPJ["servicos"], "ALMEIDA SERVICOS LTDA", saldo="65000.00", risco="Medio 2"),
        denodo_pj_row(CNPJ["parceiro"], "COMERCIO PARCEIRO LTDA", saldo="120000.00", risco="Baixissimo"),
        denodo_pj_row(CNPJ["joint"], "ALMEIDA MARTINS PARTICIPACOES LTDA", saldo="45000.00", risco="Medio 1"),
        denodo_pj_row(CNPJ["excedente"], "SOMA EXCEDENTE LTDA", saldo="1000.00", risco="Alto 2"),
        denodo_pj_row(CNPJ["ciclo_a"], "CICLO A PARTICIPACOES LTDA", saldo="500.00", risco="Alto 2"),
        denodo_pj_row(CNPJ["ciclo_b"], "CICLO B PARTICIPACOES LTDA", saldo="600.00", risco="Alto 2"),
        denodo_pj_row(CNPJ["auto_socio"], "AUTO SOCIO LTDA", saldo="300.00", risco="Default"),
        denodo_pj_row(CNPJ["movimento_pj"], "PAGADORA MOVIMENTOS LTDA", saldo="150000.00", risco="Medio 1"),
        {**denodo_pj_row(CNPJ["sem_nome"], "", saldo="200.00", risco="Default"), "nome_razao_social": "", "des_pessoa": ""},
        denodo_pj_row(INVALID_CNPJ, "CNPJ INVALIDO TESTE LTDA", saldo="100.00", risco="Default"),
        {**denodo_pj_row("", "EMPRESA SEM DOCUMENTO TESTE", saldo="0.00", risco="Default"), "cpf_cnpj": ""},
    ]
    return rows


def socio_row(idx: int, empresa: str, socio: str, per: str, comp: str = "2026-06-18 00:00:00") -> dict[str, str]:
    return {
        "id": str(260000 + idx),
        "dat_competencia": comp,
        "cnpj_associado": empresa,
        "cpf_cnpj_socio": socio,
        "per_capital": per,
        "execution_id": EXECUTION_ID,
        "updated_at": "2026-06-19 16:44:46.325 -0300",
    }


def build_socio_rows() -> list[dict[str, str]]:
    return [
        socio_row(1, CNPJ["holding"], CPF["carlos"], "60.00"),
        socio_row(2, CNPJ["holding"], CPF["maria"], "20.00"),
        socio_row(3, CNPJ["holding"], CPF["roberto_falecido"], "20.00", "2024-12-31 00:00:00"),
        socio_row(4, CNPJ["servicos"], CNPJ["holding"], "70.00"),
        socio_row(5, CNPJ["servicos"], CPF["ana"], "30.00"),
        socio_row(6, CNPJ["parceiro"], CPF["joao_investidor"], "80.00"),
        socio_row(7, CNPJ["parceiro"], CPF["carlos"], "5.00"),
        socio_row(8, CNPJ["parceiro"], CPF["paula"], "15.00"),
        socio_row(9, CNPJ["joint"], CPF["ana"], "50.00"),
        socio_row(10, CNPJ["joint"], CPF["eduardo"], "50.00"),
        socio_row(11, CNPJ["excedente"], CPF["socio_70"], "70.00"),
        socio_row(12, CNPJ["excedente"], CPF["socio_40"], "40.00"),
        socio_row(13, CNPJ["ciclo_a"], CNPJ["ciclo_b"], "60.00"),
        socio_row(14, CNPJ["ciclo_b"], CNPJ["ciclo_a"], "60.00"),
        socio_row(15, CNPJ["auto_socio"], CNPJ["auto_socio"], "100.00"),
        socio_row(16, CNPJ["externa_sem_cadastro"], CPF["paula"], "80.00"),
        socio_row(17, CNPJ["externa_sem_cadastro"], CPF["marcelo"], "20.00"),
        socio_row(18, CNPJ["movimento_pj"], CPF["shared_a"], "0.00"),
        socio_row(19, CNPJ["movimento_pj"], CPF["shared_b"], "-5.00"),
        socio_row(20, CNPJ["holding"], INVALID_CPF, "1.00"),
        socio_row(21, INVALID_CNPJ, CPF["daniel_a"], "100.00"),
        socio_row(22, CNPJ["sem_nome"], CPF["carlos"], "100.00"),
    ]


def movimento(origem: str, destino: str, ini: str, fim: str, regs: str, qtd: str, valor: str, comps: str, op: str = "ENTRADA, EVASAO", transf: str = "PIX", envolv: str = "INTERNA") -> dict[str, str]:
    return {
        "cpf_cnpj_origem": origem,
        "cpf_cnpj_destino": destino,
        "competencia_inicial": ini,
        "competencia_final": fim,
        "qtd_registros_agrupados": regs,
        "qtd_movimentacoes": qtd,
        "vlr_total_transferido": valor,
        "qtd_competencias": comps,
        "tipos_operacao": op,
        "tipos_transferencia": transf,
        "tipos_envolvimento": envolv,
    }


def build_movimentacoes_rows() -> list[dict[str, str]]:
    return [
        movimento(CNPJ["servicos"], CPF["ana"], "202501", "202506", "6", "18.00", "54000.00", "6", envolv="EXTERNA"),
        movimento(CPF["ana"], CPF["eduardo"], "202501", "202506", "6", "12.00", "18000.00", "6"),
        movimento(CPF["eduardo"], CPF["ana"], "202502", "202506", "5", "8.00", "9000.00", "5"),
        movimento(CPF["carlos"], CPF["maria"], "202501", "202506", "6", "10.00", "25000.00", "6"),
        movimento(CPF["maria"], CPF["carlos"], "202503", "202506", "4", "6.00", "7000.00", "4"),
        movimento(CPF["shared_a"], CPF["shared_b"], "202501", "202506", "6", "20.00", "30000.00", "6"),
        movimento(CPF["shared_b"], CPF["shared_a"], "202504", "202506", "3", "3.00", "1500.00", "3"),
        movimento(CPF["joao_investidor"], CNPJ["parceiro"], "202501", "202506", "6", "9.00", "85000.00", "6"),
        movimento(CNPJ["parceiro"], CPF["joao_investidor"], "202501", "202506", "6", "9.00", "40000.00", "6"),
        movimento(CPF["roberto_falecido"], CNPJ["holding"], "202604", "202606", "3", "5.00", "12000.00", "3"),
        movimento(CPF["socio_70"], CNPJ["excedente"], "202501", "202506", "6", "6.00", "70000.00", "6"),
        movimento(CPF["socio_40"], CNPJ["excedente"], "202501", "202506", "6", "6.00", "40000.00", "6"),
        movimento(CPF["daniel_a"], CPF["daniel_b"], "202506", "202506", "1", "1.00", "80.00", "1"),
        movimento(CPF["carlos"], CPF["ana"], "202501", "202502", "2", "2.00", "600.00", "2"),
        movimento(CPF["ana"], CPF["bruno"], "202502", "202503", "2", "2.00", "500.00", "2"),
        movimento(CPF["bruno"], CPF["shared_a"], "202501", "202506", "6", "12.00", "15000.00", "6"),
        movimento(CNPJ["movimento_pj"], CPF["shared_a"], "202501", "202506", "6", "24.00", "96000.00", "6", envolv="EXTERNA"),
        movimento(CNPJ["movimento_pj"], CPF["shared_b"], "202501", "202506", "6", "24.00", "94000.00", "6", envolv="EXTERNA"),
        movimento(INVALID_CPF, CNPJ["holding"], "202501", "202502", "2", "2.00", "200.00", "2"),
        movimento(CPF["paula"], CNPJ["externa_sem_cadastro"], "202501", "202506", "6", "10.00", "15000.00", "6"),
    ]


def main() -> None:
    pf_rows = build_pf_rows()
    denodo_rows = build_denodo_rows(pf_rows)
    socio_rows = build_socio_rows()
    mov_rows = build_movimentacoes_rows()
    outputs = [
        ("stg_pessoa_fisica_atual_202606191707.csv", PESSOA_FISICA_COLUMNS, pf_rows),
        ("denodo_base_cadastral.csv", DENODO_COLUMNS, denodo_rows),
        ("stg_cadastro_socio_pj_202606191707.csv", SOCIO_PJ_COLUMNS, socio_rows),
        ("mv_movimentacoes.csv", MOVIMENTACOES_COLUMNS, mov_rows),
    ]
    for filename, columns, rows in outputs:
        write_csv(OUT_DIR / filename, columns, rows)
        print(f"{filename}: {len(rows)} registros, {len(columns)} colunas")


if __name__ == "__main__":
    main()
