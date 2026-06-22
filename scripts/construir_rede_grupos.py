#!/usr/bin/env python3
"""Constroi rede explicavel de entidades, vinculos e grupos economicos.

Entrada: quatro CSVs em dados/.
Saida: tabelas analiticas em resultados/ e grafo_resultado.sqlite.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "dados"
OUT_DIR = ROOT / "resultados"

PF_FILE = "stg_pessoa_fisica_atual_202606191707.csv"
DENODO_FILE = "denodo_base_cadastral.csv"
SOCIO_FILE = "stg_cadastro_socio_pj_202606191707.csv"
MOV_FILE = "mv_movimentacoes.csv"

INFLUENCE_LIMIT = 20.0
CONTROL_LIMIT = 50.0
INDIRECT_MAX_DEPTH = 4
ECO_MIN_COMPETENCIAS = 3
ECO_MIN_MOVIMENTOS = 3.0
ECO_MIN_COBERTURA = 0.60
ECO_MIN_VALOR = 10_000.0
ECO_MODERATE_SHARE = 0.30
ECO_STRONG_SHARE = 0.50

ENTIDADES_COLUMNS = [
    "entidade_id",
    "tipo_entidade",
    "cpf_cnpj",
    "nome_canonico",
    "nome_original",
    "data_nascimento",
    "data_obito",
    "status_entidade",
    "documento_valido",
    "entidade_provisoria",
    "fonte_principal",
    "data_atualizacao",
    "alertas",
]

VINCULOS_COLUMNS = [
    "vinculo_id",
    "entidade_origem",
    "entidade_destino",
    "tipo_vinculo",
    "direcional",
    "percentual_participacao",
    "confianca_vinculo",
    "relevancia_familiar",
    "relevancia_societaria",
    "relevancia_regulatoria",
    "data_inicio",
    "data_fim",
    "data_observacao",
    "codigo_regra",
    "arquivo_fonte",
    "campos_fonte",
    "evidencias",
    "requer_revisao",
]

GRUPOS_COLUMNS = [
    "grupo_id",
    "tipo_grupo",
    "entidade_ancora",
    "nome_grupo",
    "data_corte",
    "quantidade_membros_core",
    "quantidade_membros_associados",
    "quantidade_candidatos",
    "confianca_grupo",
    "status_grupo",
    "grupo_regulatorio",
    "requer_revisao",
    "motivo_revisao",
]

MEMBROS_COLUMNS = [
    "grupo_id",
    "entidade_id",
    "papel_no_grupo",
    "nivel_membro",
    "vinculo_direto_ou_indireto",
    "entidade_ponte",
    "caminho_vinculo",
    "profundidade",
    "confianca_inclusao",
    "relevancia_economica",
    "codigos_regras",
    "arquivos_fonte",
    "data_inicio",
    "data_fim",
    "requer_revisao",
    "justificativa_textual",
]

RELACOES_GRUPOS_COLUMNS = [
    "grupo_origem",
    "grupo_destino",
    "tipo_relacao",
    "entidade_ponte",
    "confianca",
    "relevancia",
    "evidencias",
    "data_referencia",
]

FILA_REVISAO_COLUMNS = [
    "objeto_tipo",
    "objeto_id",
    "codigo_alerta",
    "severidade",
    "descrição",
    "entidades_envolvidas",
    "evidências disponíveis",
    "ação recomendada",
]

AGREGACOES_COLUMNS = [
    "grupo_id",
    "tipo_grupo",
    "saldo_total",
    "saldo_credito_rural",
    "saldo_credito_comercial",
    "saldo_credito_direcionado",
    "limite_cheque_especial",
    "limite_cartao",
    "valor_bens",
    "quantidade_contas_ativas",
    "quantidade_contas_encerradas",
    "quantidade_membros_falecidos",
    "pior_faixa_risco",
    "exposicao_pf",
    "exposicao_pj",
    "observacao_sobreposicao",
    "data_corte",
]


def read_csv(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / name
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def write_csv(name: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: serialize(row.get(col, "")) for col in columns})


def serialize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def norm_text(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def parse_float(value: str | None) -> float:
    if value is None or value == "":
        return 0.0
    return float(str(value).replace(",", "."))


def parse_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{6}", raw):
        year = int(raw[:4])
        month = int(raw[4:6])
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1).replace(day=1) - timedelta_days(1)
    raw = raw.replace(" -0300", "").replace("-0300", "").strip()
    raw = raw.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:26], fmt).date()
        except ValueError:
            pass
    return None


def timedelta_days(days: int):
    from datetime import timedelta

    return timedelta(days=days)


def iso_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def month_span(ini: str, fim: str) -> int:
    if not re.fullmatch(r"\d{6}", ini or "") or not re.fullmatch(r"\d{6}", fim or ""):
        return 0
    y1, m1 = int(ini[:4]), int(ini[4:])
    y2, m2 = int(fim[:4]), int(fim[4:])
    return max(1, (y2 - y1) * 12 + (m2 - m1) + 1)


def cpf_valid(doc: str) -> bool:
    if len(doc) != 11 or not doc.isdigit() or len(set(doc)) == 1:
        return False
    nums = [int(c) for c in doc]
    d1 = (sum(nums[i] * (10 - i) for i in range(9)) * 10) % 11
    d1 = 0 if d1 == 10 else d1
    d2 = (sum(nums[i] * (11 - i) for i in range(10)) * 10) % 11
    d2 = 0 if d2 == 10 else d2
    return nums[9] == d1 and nums[10] == d2


def cnpj_valid(doc: str) -> bool:
    if len(doc) != 14 or not doc.isdigit() or len(set(doc)) == 1:
        return False
    nums = [int(c) for c in doc]
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = 11 - (sum(nums[i] * w1[i] for i in range(12)) % 11)
    d1 = 0 if d1 >= 10 else d1
    w2 = [6, *w1]
    d2 = 11 - (sum(nums[i] * w2[i] for i in range(13)) % 11)
    d2 = 0 if d2 >= 10 else d2
    return nums[12] == d1 and nums[13] == d2


def doc_valid(doc: str) -> bool:
    return cpf_valid(doc) if len(doc) == 11 else cnpj_valid(doc) if len(doc) == 14 else False


def doc_entity_id(doc: str, entity_type: str | None = None) -> str:
    if entity_type == "PJ" or len(doc) == 14:
        return f"PJ:{doc}"
    if entity_type == "PF" or len(doc) == 11:
        return f"PF:{doc}"
    return f"DOC:{doc}"


def external_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(norm_text(p) for p in parts).encode("utf-8")).hexdigest()[:14]
    return f"{prefix}:{digest}"


def build_data_corte(*tables: list[dict[str, str]]) -> str:
    dates: list[date] = []
    for table in tables:
        for row in table:
            for col in ("updated_at", "last_update", "dat_competencia", "competencia_final"):
                d = parse_date(row.get(col))
                if d:
                    dates.append(d)
    return max(dates).isoformat() if dates else date.today().isoformat()


class GraphBuilder:
    def __init__(self) -> None:
        self.pf_rows = read_csv(PF_FILE)
        self.denodo_rows = read_csv(DENODO_FILE)
        self.socio_rows = read_csv(SOCIO_FILE)
        self.mov_rows = read_csv(MOV_FILE)
        self.data_corte = build_data_corte(self.pf_rows, self.denodo_rows, self.socio_rows, self.mov_rows)
        self.entities: dict[str, dict[str, Any]] = {}
        self.vinculos: list[dict[str, Any]] = []
        self.groups: list[dict[str, Any]] = []
        self.members: list[dict[str, Any]] = []
        self.group_relations: list[dict[str, Any]] = []
        self.review: list[dict[str, Any]] = []
        self.vseq = 1
        self.gseq = 1
        self.pf_by_doc: dict[str, dict[str, str]] = {}
        self.denodo_by_doc: dict[str, dict[str, str]] = {}
        self.parent_map: dict[str, dict[str, str]] = defaultdict(dict)
        self.spouses: dict[str, set[str]] = defaultdict(set)
        self.direct_socios: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self.indirect_participations: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.group_ids_by_tag: dict[str, str] = {}

    def add_review(
        self,
        objeto_tipo: str,
        objeto_id: str,
        codigo: str,
        severidade: str,
        descricao: str,
        entidades: list[str],
        evidencias: str,
        acao: str,
    ) -> None:
        self.review.append(
            {
                "objeto_tipo": objeto_tipo,
                "objeto_id": objeto_id,
                "codigo_alerta": codigo,
                "severidade": severidade,
                "descrição": descricao,
                "entidades_envolvidas": "|".join(entidades),
                "evidências disponíveis": evidencias,
                "ação recomendada": acao,
            }
        )

    def add_entity(
        self,
        entity_id: str,
        tipo: str,
        cpf_cnpj: str,
        nome: str,
        fonte: str,
        *,
        nome_original: str | None = None,
        nascimento: str = "",
        obito: str = "",
        status: str = "ATIVO",
        provisoria: bool = False,
        atualizacao: str = "",
        alertas: list[str] | None = None,
    ) -> dict[str, Any]:
        alerts = set(alertas or [])
        doc = digits(cpf_cnpj)
        valid = bool(doc and doc_valid(doc))
        if not doc:
            alerts.add("DOCUMENTO_AUSENTE")
        elif not valid:
            alerts.add("DOCUMENTO_SINTETICO_OU_INVALIDO")

        existing = self.entities.get(entity_id)
        if not existing:
            existing = {
                "entidade_id": entity_id,
                "tipo_entidade": tipo,
                "cpf_cnpj": doc,
                "nome_canonico": norm_text(nome),
                "nome_original": nome_original or nome,
                "data_nascimento": nascimento,
                "data_obito": obito,
                "status_entidade": status,
                "documento_valido": valid,
                "entidade_provisoria": provisoria,
                "fonte_principal": fonte,
                "data_atualizacao": atualizacao,
                "alertas": set(alerts),
            }
            self.entities[entity_id] = existing
            return existing

        # Canonical value uses later update when available. Values are not split.
        existing["alertas"].update(alerts)
        if tipo in {"PF_EXTERNA", "PJ_EXTERNA"} and existing["tipo_entidade"] in {"PF", "PJ"}:
            pass
        elif existing["tipo_entidade"] in {"PF_EXTERNA", "PJ_EXTERNA"} and tipo in {"PF", "PJ"}:
            existing["tipo_entidade"] = tipo
            existing["entidade_provisoria"] = provisoria
        if atualizacao and (not existing["data_atualizacao"] or atualizacao > existing["data_atualizacao"]):
            existing["nome_canonico"] = norm_text(nome) or existing["nome_canonico"]
            existing["nome_original"] = nome_original or nome or existing["nome_original"]
            existing["data_nascimento"] = nascimento or existing["data_nascimento"]
            existing["data_obito"] = obito or existing["data_obito"]
            existing["status_entidade"] = status or existing["status_entidade"]
            existing["fonte_principal"] = fonte
            existing["data_atualizacao"] = atualizacao
        return existing

    def add_vinculo(
        self,
        origem: str,
        destino: str,
        tipo: str,
        regra: str,
        fonte: str,
        campos: str,
        evidencias: str,
        *,
        direcional: str = "SIM",
        percentual: str = "",
        confianca: int = 90,
        rel_fam: int = 0,
        rel_soc: int = 0,
        rel_reg: int = 0,
        data_inicio: str = "",
        data_fim: str = "",
        data_obs: str | None = None,
        revisao: bool = False,
    ) -> str:
        vinculo_id = f"V{self.vseq:05d}"
        self.vseq += 1
        self.vinculos.append(
            {
                "vinculo_id": vinculo_id,
                "entidade_origem": origem,
                "entidade_destino": destino,
                "tipo_vinculo": tipo,
                "direcional": direcional,
                "percentual_participacao": percentual,
                "confianca_vinculo": confianca,
                "relevancia_familiar": rel_fam,
                "relevancia_societaria": rel_soc,
                "relevancia_regulatoria": rel_reg,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "data_observacao": data_obs or self.data_corte,
                "codigo_regra": regra,
                "arquivo_fonte": fonte,
                "campos_fonte": campos,
                "evidencias": evidencias,
                "requer_revisao": revisao,
            }
        )
        return vinculo_id

    def prepare_entities(self) -> None:
        for row in self.pf_rows:
            doc = digits(row["cpf_cnpj"])
            eid = doc_entity_id(doc, "PF")
            status = "FALECIDO" if row.get("dat_obito") else "ATIVO"
            self.pf_by_doc[doc] = row
            self.add_entity(
                eid,
                "PF",
                doc,
                row["nome_pessoa_normalizado"] or row["nome_pessoa"],
                PF_FILE,
                nome_original=row["nome_pessoa"],
                nascimento=row["dat_nascimento"],
                obito=row["dat_obito"],
                status=status,
                atualizacao=row["updated_at"],
            )
            if row.get("dat_obito"):
                esp_id = f"ESPOLIO:{doc}"
                self.add_entity(
                    esp_id,
                    "ESPOLIO",
                    doc,
                    f"ESPOLIO DE {row['nome_pessoa']}",
                    PF_FILE,
                    status="HISTORICO",
                    provisoria=False,
                    atualizacao=row["updated_at"],
                    alertas=["PESSOA_FALECIDA_COM_REPRESENTACAO_HISTORICA"],
                )
                self.add_vinculo(
                    esp_id,
                    eid,
                    "ESPOLIO_DE",
                    "ID_CPF_EXATO",
                    PF_FILE,
                    "cpf_cnpj;dat_obito",
                    "Pessoa falecida mantida no historico por entidade de espolio.",
                    confianca=95,
                    rel_fam=70,
                    revisao=False,
                )

        for row in self.denodo_rows:
            doc = digits(row.get("cpf_cnpj"))
            if not doc:
                eid = external_id("PJX", row.get("nome_razao_social", ""), row.get("endereco_completo", ""))
                tipo = "PJ_EXTERNA"
            else:
                tipo_denodo = (row.get("tipo_pessoa") or "").upper()
                tipo = "PJ" if tipo_denodo == "PJ" or len(doc) == 14 else "PF"
                eid = doc_entity_id(doc, tipo)
            self.denodo_by_doc[doc] = row
            self.add_entity(
                eid,
                tipo,
                doc,
                row.get("nome_razao_social") or row.get("des_pessoa") or "",
                DENODO_FILE,
                nome_original=row.get("nome_razao_social") or row.get("des_pessoa") or "",
                nascimento=row.get("data_nascimento", ""),
                status="CONTA_ATIVA" if row.get("status_conta") == "CONTA ATIVA" else "CONTA_ENCERRADA",
                atualizacao=row.get("last_update", ""),
                provisoria=tipo.endswith("_EXTERNA"),
                alertas=["EMPRESA_SEM_NOME"] if tipo.startswith("PJ") and not row.get("nome_razao_social") else [],
            )

        # CNPJs and socios that occur only in societary data.
        known_denodo_docs = {digits(row.get("cpf_cnpj")) for row in self.denodo_rows if digits(row.get("cpf_cnpj"))}
        for row in self.socio_rows:
            company = digits(row["cnpj_associado"])
            if company and company not in self.entities:
                self.add_entity(
                    doc_entity_id(company, "PJ"),
                    "PJ_EXTERNA",
                    company,
                    "",
                    SOCIO_FILE,
                    provisoria=True,
                    atualizacao=row["updated_at"],
                    alertas=["CNPJ_SEM_CADASTRO"] if company not in known_denodo_docs else [],
                )
            socio = digits(row["cpf_cnpj_socio"])
            if socio and doc_entity_id(socio) not in self.entities:
                tipo = "PJ_EXTERNA" if len(socio) == 14 else "PF"
                self.add_entity(
                    doc_entity_id(socio),
                    tipo,
                    socio,
                    "",
                    SOCIO_FILE,
                    provisoria=tipo.endswith("_EXTERNA"),
                    atualizacao=row["updated_at"],
                )

        self.detect_entity_alerts()

    def detect_entity_alerts(self) -> None:
        pf_names: dict[str, set[str]] = defaultdict(set)
        for row in self.pf_rows:
            pf_names[norm_text(row["nome_pessoa"])].add(doc_entity_id(digits(row["cpf_cnpj"]), "PF"))

        for name, eids in pf_names.items():
            if name and len(eids) > 1:
                self.add_review(
                    "ENTIDADE",
                    name,
                    "MESMO_NOME_MULTIPLOS_CPFS",
                    "MEDIA",
                    "Mesmo nome associado a multiplos CPFs; nao foi feito merge por nome.",
                    sorted(eids),
                    f"nome={name}; cpfs={len(eids)}",
                    "Manter entidades separadas e revisar apenas se houver documento oficial.",
                )
                for eid in eids:
                    self.entities[eid]["alertas"].add("MESMO_NOME_MULTIPLOS_CPFS")

        denodo_by_doc = {digits(row["cpf_cnpj"]): row for row in self.denodo_rows if digits(row.get("cpf_cnpj"))}
        for doc, pf in self.pf_by_doc.items():
            denodo = denodo_by_doc.get(doc)
            if not denodo:
                continue
            pf_name = norm_text(pf["nome_pessoa"])
            de_name = norm_text(denodo.get("nome_razao_social") or denodo.get("des_pessoa"))
            pf_birth = pf["dat_nascimento"][:10]
            de_birth = (denodo.get("data_nascimento") or "")[:10]
            if de_name and de_name != pf_name or de_birth and de_birth != pf_birth:
                eid = doc_entity_id(doc, "PF")
                self.entities[eid]["alertas"].add("REV_CONFLITO_CADASTRAL")
                self.add_review(
                    "ENTIDADE",
                    eid,
                    "REV_CONFLITO_CADASTRAL",
                    "ALTA",
                    "Mesmo CPF possui nome ou data de nascimento divergente entre fontes.",
                    [eid],
                    f"PF=({pf_name},{pf_birth}); DENODO=({de_name},{de_birth})",
                    "Selecionar valor canonico pela fonte mais recente e preservar alternativos.",
                )

        for eid, entity in self.entities.items():
            alerts = entity["alertas"]
            if "DOCUMENTO_AUSENTE" in alerts:
                self.add_review(
                    "ENTIDADE",
                    eid,
                    "DOCUMENTO_AUSENTE",
                    "MEDIA",
                    "Entidade sem CPF/CNPJ informado.",
                    [eid],
                    f"fonte={entity['fonte_principal']}; nome={entity['nome_canonico']}",
                    "Solicitar identificador antes de uso regulatorio.",
                )
            elif "DOCUMENTO_SINTETICO_OU_INVALIDO" in alerts:
                self.add_review(
                    "ENTIDADE",
                    eid,
                    "DOCUMENTO_SINTETICO_OU_INVALIDO",
                    "MEDIA",
                    "CPF/CNPJ nao passou no digito verificador; mantido por ser dado de teste/entrada.",
                    [eid],
                    f"documento={entity['cpf_cnpj']}",
                    "Validar contra fonte oficial antes de qualquer decisao final.",
                )
            if "EMPRESA_SEM_NOME" in alerts:
                self.add_review(
                    "ENTIDADE",
                    eid,
                    "EMPRESA_SEM_NOME",
                    "MEDIA",
                    "CNPJ cadastrado sem nome empresarial.",
                    [eid],
                    "nome_razao_social vazio em denodo.",
                    "Complementar cadastro da PJ.",
                )

    def build_family_links(self) -> None:
        pf_candidates_by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.pf_rows:
            pf_candidates_by_name[norm_text(row["nome_pessoa"])].append(row)

        for child in self.pf_rows:
            child_doc = digits(child["cpf_cnpj"])
            child_eid = doc_entity_id(child_doc, "PF")
            child_birth = parse_date(child["dat_nascimento"])
            for role, col, inverse, sex_expected, other_col in [
                ("PAI", "nom_pai", "PAI_DE", "MASCULINO", "nom_mae"),
                ("MAE", "nom_mae", "MAE_DE", "FEMININO", "nom_pai"),
            ]:
                parent_name = norm_text(child.get(col))
                if not parent_name:
                    continue
                if parent_name == norm_text(child["nome_pessoa"]):
                    self.add_review(
                        "VINCULO",
                        child_eid,
                        "PARENTESCO_AUTO_REFERENTE",
                        "ALTA",
                        "Pessoa aparece como seu proprio pai ou mae.",
                        [child_eid],
                        f"{col}={parent_name}",
                        "Corrigir cadastro de filiacao.",
                    )
                    self.entities[child_eid]["alertas"].add("PARENTESCO_AUTO_REFERENTE")

                candidates = []
                for cand in pf_candidates_by_name.get(parent_name, []):
                    cand_doc = digits(cand["cpf_cnpj"])
                    if cand_doc == child_doc:
                        continue
                    cand_birth = parse_date(cand["dat_nascimento"])
                    age_diff = (child_birth.year - cand_birth.year) if child_birth and cand_birth else 0
                    sex_ok = cand.get("tipo_sexo") == sex_expected
                    plausible = 13 <= age_diff <= 70
                    same_city = cand.get("des_cidade") == child.get("des_cidade")
                    candidates.append((cand, sex_ok, plausible, same_city, age_diff))

                if len(candidates) == 1:
                    cand, sex_ok, plausible, same_city, age_diff = candidates[0]
                    parent_eid = doc_entity_id(digits(cand["cpf_cnpj"]), "PF")
                    confidence = 90 if sex_ok and plausible and same_city else 45
                    review = confidence < 70
                    code = "FAM_PAI_DECLARADO" if role == "PAI" else "FAM_MAE_DECLARADA"
                    if review:
                        code = "PARENTESCO_AMBIGUO"
                        self.add_review(
                            "VINCULO",
                            f"{child_eid}->{parent_eid}",
                            "DIFERENCA_ETARIA_PARENTAL_IMPLAUSIVEL",
                            "ALTA",
                            "Candidato a genitor tem diferenca etaria biologicamente implausivel ou evidencia fraca.",
                            [child_eid, parent_eid],
                            f"idade_diferenca={age_diff}; sexo_ok={sex_ok}; mesma_cidade={same_city}",
                            "Revisar documento de filiacao antes de confirmar parentesco.",
                        )
                    self._add_parent_links(child_eid, parent_eid, role, inverse, code, confidence, review, f"{col};cpf_cnpj;nome_pessoa")
                    if not review:
                        self.parent_map[child_eid][role] = parent_eid
                elif len(candidates) > 1:
                    candidate_ids = [doc_entity_id(digits(c[0]["cpf_cnpj"]), "PF") for c in candidates]
                    self.add_review(
                        "VINCULO",
                        f"{child_eid}:{role}",
                        "PARENTESCO_AMBIGUO",
                        "ALTA",
                        "Nome de genitor possui multiplos candidatos equivalentes.",
                        [child_eid, *candidate_ids],
                        f"{col}={parent_name}; candidatos={len(candidate_ids)}",
                        "Solicitar evidencia adicional; nao escolher arbitrariamente.",
                    )
                    for cand, sex_ok, plausible, same_city, age_diff in candidates:
                        parent_eid = doc_entity_id(digits(cand["cpf_cnpj"]), "PF")
                        self.add_vinculo(
                            child_eid,
                            parent_eid,
                            "PARENTESCO_AMBIGUO",
                            "REV_AMBIGUIDADE_IDENTIDADE",
                            PF_FILE,
                            f"{col};nome_pessoa;data_nascimento",
                            f"Nome do genitor coincide com PF existente; idade_diff={age_diff}; sexo_ok={sex_ok}; mesma_cidade={same_city}.",
                            confianca=45,
                            rel_fam=40,
                            revisao=True,
                        )
                else:
                    parent_eid = external_id("PFX", role, parent_name, child.get(other_col, ""), child.get("des_cidade", ""), child.get("sgl_uf", ""))
                    self.add_entity(
                        parent_eid,
                        "PF_EXTERNA",
                        "",
                        parent_name,
                        PF_FILE,
                        provisoria=True,
                        alertas=["PF_EXTERNA_SEM_CPF"],
                    )
                    code = "FAM_PAI_DECLARADO" if role == "PAI" else "FAM_MAE_DECLARADA"
                    self._add_parent_links(child_eid, parent_eid, role, inverse, code, 70, True, col)
                    self.parent_map[child_eid][role] = parent_eid

        self.detect_half_sibling_ambiguity()
        self.build_sibling_links()
        self.build_conjugal_links()
        self.build_contact_links()

    def _add_parent_links(
        self,
        child_eid: str,
        parent_eid: str,
        role: str,
        inverse: str,
        code: str,
        confidence: int,
        review: bool,
        campos: str,
    ) -> None:
        rel_fam = 90 if confidence >= 85 else 60
        self.add_vinculo(
            child_eid,
            parent_eid,
            "FILHO_DE",
            code,
            PF_FILE,
            campos,
            f"Filiacao declarada no cadastro PF; papel={role}.",
            confianca=confidence,
            rel_fam=rel_fam,
            revisao=review,
        )
        self.add_vinculo(
            parent_eid,
            child_eid,
            inverse,
            code,
            PF_FILE,
            campos,
            f"Vinculo inverso derivado de FILHO_DE; papel={role}.",
            confianca=confidence,
            rel_fam=rel_fam,
            revisao=review,
        )

    def detect_half_sibling_ambiguity(self) -> None:
        by_parent_name: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in self.pf_rows:
            for role, col in (("PAI", "nom_pai"), ("MAE", "nom_mae")):
                if row.get(col):
                    by_parent_name[(role, norm_text(row[col]))].append(row)
        for (role, name), rows in by_parent_name.items():
            other_names = {
                norm_text(row["nom_mae"] if role == "PAI" else row["nom_pai"])
                for row in rows
                if row.get("nom_mae" if role == "PAI" else "nom_pai")
            }
            if name and len(rows) > 1 and len(other_names) > 1:
                eids = [doc_entity_id(digits(row["cpf_cnpj"]), "PF") for row in rows]
                self.add_review(
                    "VINCULO",
                    f"{role}:{name}",
                    "POSSIVEL_MESMO_GENITOR",
                    "MEDIA",
                    "Mesmo nome de genitor aparece com diferentes conjuges/outro genitor; nao foi assumida identidade unica.",
                    eids,
                    f"genitor={name}; outro_genitor_distintos={len(other_names)}",
                    "Revisar se genitor e a mesma pessoa antes de formar meios-irmaos confirmados.",
                )
                for a in range(len(eids)):
                    for b in range(a + 1, len(eids)):
                        self.add_vinculo(
                            eids[a],
                            eids[b],
                            "POSSIVEL_MESMO_GENITOR",
                            "FAM_MEIO_IRMAO_UM_PAI",
                            PF_FILE,
                            "nom_pai;nom_mae",
                            f"Compartilham nome de {role.lower()}={name}, mas outro genitor difere.",
                            direcional="NAO",
                            confianca=45,
                            rel_fam=45,
                            revisao=True,
                        )

    def build_sibling_links(self) -> None:
        pair_to_children: dict[tuple[str, str], list[str]] = defaultdict(list)
        for child, parents in self.parent_map.items():
            if parents.get("PAI") and parents.get("MAE"):
                pair_to_children[(parents["PAI"], parents["MAE"])].append(child)
        for parents, children in pair_to_children.items():
            if len(children) < 2:
                continue
            for i, a in enumerate(children):
                for b in children[i + 1 :]:
                    self.add_vinculo(
                        a,
                        b,
                        "IRMAO_DE",
                        "FAM_IRMAOS_DOIS_PAIS",
                        PF_FILE,
                        "nom_pai;nom_mae;cpf_cnpj",
                        f"Irmaos completos por pais resolvidos: {parents[0]} e {parents[1]}.",
                        direcional="NAO",
                        confianca=82,
                        rel_fam=85,
                        revisao=False,
                    )
                    # Tios/sobrinhos derivados.
                    for nephew, pmap in self.parent_map.items():
                        if pmap.get("PAI") == a or pmap.get("MAE") == a:
                            self.add_vinculo(
                                b,
                                nephew,
                                "TIO_TIA_DE",
                                "FAM_PARENTESCO_DERIVADO",
                                PF_FILE,
                                "FILHO_DE;IRMAO_DE",
                                f"Caminho: {nephew} -> FILHO_DE -> {a} -> IRMAO_DE -> {b}.",
                                confianca=78,
                                rel_fam=65,
                            )
                        if pmap.get("PAI") == b or pmap.get("MAE") == b:
                            self.add_vinculo(
                                a,
                                nephew,
                                "TIO_TIA_DE",
                                "FAM_PARENTESCO_DERIVADO",
                                PF_FILE,
                                "FILHO_DE;IRMAO_DE",
                                f"Caminho: {nephew} -> FILHO_DE -> {b} -> IRMAO_DE -> {a}.",
                                confianca=78,
                                rel_fam=65,
                            )

    def build_conjugal_links(self) -> None:
        active_spouses: dict[str, set[str]] = defaultdict(set)
        seen_pairs: set[tuple[str, str]] = set()
        for row in self.denodo_rows:
            doc = digits(row.get("cpf_cnpj"))
            if len(doc) != 11:
                continue
            src = doc_entity_id(doc, "PF")
            spouse_doc = digits(row.get("cpf_conj"))
            spouse_name = norm_text(row.get("nome_pessoa_conj"))
            regime = row.get("nome_regime_bem") or row.get("estado_civil") or ""
            rel_reg = 70 if "UNIVERSAL" in norm_text(regime) else 60 if "PARCIAL" in norm_text(regime) else 35 if "SEPARACAO" in norm_text(regime) else 45
            if spouse_doc:
                dst = doc_entity_id(spouse_doc, "PF")
                if spouse_doc not in self.pf_by_doc:
                    self.add_entity(dst, "PF_EXTERNA", spouse_doc, spouse_name, DENODO_FILE, provisoria=True, alertas=["CONJUGE_CPF_SEM_CADASTRO_PF"])
                pair = tuple(sorted([src, dst]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    self.add_vinculo(
                        src,
                        dst,
                        "CONJUGE_DE",
                        "FAM_CONJUGE_CPF",
                        DENODO_FILE,
                        "cpf_cnpj;cpf_conj;nome_pessoa_conj;nome_regime_bem",
                        f"Conjuge informado por CPF; regime={regime}.",
                        direcional="NAO",
                        confianca=95,
                        rel_fam=95,
                        rel_reg=rel_reg,
                    )
                self.spouses[src].add(dst)
                self.spouses[dst].add(src)
                active_spouses[src].add(dst)
            elif spouse_name:
                dst = external_id("PFX", "CONJUGE_NOME", spouse_name, src)
                self.add_entity(dst, "PF_EXTERNA", "", spouse_name, DENODO_FILE, provisoria=True, alertas=["CONJUGE_APENAS_NOME"])
                self.add_vinculo(
                    src,
                    dst,
                    "CONJUGE_NOME_CANDIDATO",
                    "FAM_CONJUGE_NOME_CANDIDATO",
                    DENODO_FILE,
                    "nome_pessoa_conj;estado_civil;nome_regime_bem",
                    "Conjuge informado somente por nome; nao resolvido para PF existente.",
                    direcional="NAO",
                    confianca=50,
                    rel_fam=55,
                    rel_reg=30,
                    revisao=True,
                )

        for eid, spouses in active_spouses.items():
            if len(spouses) > 1:
                self.add_review(
                    "VINCULO",
                    eid,
                    "MULTIPLOS_CONJUGES_ATUAIS",
                    "ALTA",
                    "Entidade possui multiplos conjuges atuais informados por CPF.",
                    [eid, *sorted(spouses)],
                    f"qtd_conjuges={len(spouses)}",
                    "Revisar vigencia dos vinculos conjugais.",
                )

    def build_contact_links(self) -> None:
        pf_entities = [(doc_entity_id(digits(r["cpf_cnpj"]), "PF"), r) for r in self.pf_rows]
        for key_fields, tipo, code in [
            (("des_logradouro", "num_endereco", "des_complemento", "des_cep", "des_cidade", "sgl_uf"), "ENDERECO_COMPARTILHADO", "CAD_ENDERECO_EXATO"),
            (("des_email",), "CONTATO_COMPARTILHADO", "CAD_CONTATO_COMPARTILHADO"),
            (("num_ddd", "num_telefone"), "CONTATO_COMPARTILHADO", "CAD_CONTATO_COMPARTILHADO"),
        ]:
            buckets: dict[tuple[str, ...], list[str]] = defaultdict(list)
            for eid, row in pf_entities:
                key = tuple(norm_text(row.get(f)) for f in key_fields)
                if all(key):
                    buckets[key].append(eid)
            for key, eids in buckets.items():
                if len(eids) < 2:
                    continue
                for i, a in enumerate(eids):
                    for b in eids[i + 1 :]:
                        self.add_vinculo(
                            a,
                            b,
                            tipo,
                            code,
                            PF_FILE,
                            ";".join(key_fields),
                            f"Valor compartilhado: {'|'.join(key)}. Evidencia complementar, nao transitiva.",
                            direcional="NAO",
                            confianca=72,
                            rel_fam=35,
                            rel_reg=20,
                            revisao=True,
                        )

    def build_societary_links(self) -> None:
        sums: dict[str, float] = defaultdict(float)
        for row in self.socio_rows:
            company_doc = digits(row["cnpj_associado"])
            socio_doc = digits(row["cpf_cnpj_socio"])
            company = doc_entity_id(company_doc, "PJ")
            socio = doc_entity_id(socio_doc)
            percent = parse_float(row["per_capital"])
            sums[company] += percent
            self.direct_socios[company].append((socio, percent))
            role = "SOCIO_MINORITARIO"
            rel_soc = 40
            if percent > CONTROL_LIMIT:
                role = "CONTROLADOR_DIRETO"
                rel_soc = 95
            elif percent == CONTROL_LIMIT:
                role = "CONTROLE_CONJUNTO_CANDIDATO"
                rel_soc = 75
            elif percent >= INFLUENCE_LIMIT:
                role = "INFLUENCIA_RELEVANTE"
                rel_soc = 70
            if percent <= 0:
                role = "PARTICIPACAO_INVALIDA"
                rel_soc = 0
                self.add_review(
                    "VINCULO",
                    f"{socio}->{company}",
                    "PARTICIPACAO_ZERO_NEGATIVA",
                    "ALTA",
                    "Participacao societaria zero ou negativa.",
                    [socio, company],
                    f"per_capital={percent}",
                    "Corrigir base societaria antes de classificar papel.",
                )
            if company == socio:
                self.add_review(
                    "VINCULO",
                    f"{socio}->{company}",
                    "SOCIO_IGUAL_PROPRIA_EMPRESA",
                    "ALTA",
                    "CNPJ aparece como socio de si mesmo.",
                    [socio, company],
                    f"cnpj_associado={company_doc}",
                    "Revisar cadeia societaria e remover ciclo auto-referente se indevido.",
                )
            self.add_vinculo(
                socio,
                company,
                "SOCIO_DE",
                "SOC_SOCIO_DIRETO",
                SOCIO_FILE,
                "cnpj_associado;cpf_cnpj_socio;per_capital;dat_competencia",
                f"Papel analitico={role}; per_capital={percent:.2f}.",
                percentual=f"{percent:.2f}",
                confianca=90 if percent > 0 else 40,
                rel_soc=rel_soc,
                rel_reg=rel_soc if percent > CONTROL_LIMIT else 35,
                data_inicio=(parse_date(row["dat_competencia"]) or date.fromisoformat(self.data_corte)).isoformat(),
                data_obs=iso_date(parse_date(row["updated_at"])) or self.data_corte,
                revisao=percent <= 0 or company == socio,
            )
            if percent > CONTROL_LIMIT:
                self.add_vinculo(
                    socio,
                    company,
                    "CONTROLADOR_DIRETO",
                    "SOC_CONTROLADOR_DIRETO",
                    SOCIO_FILE,
                    "per_capital",
                    f"Participacao direta superior a {CONTROL_LIMIT:.0f}%.",
                    percentual=f"{percent:.2f}",
                    confianca=88,
                    rel_soc=95,
                    rel_reg=85,
                    data_inicio=(parse_date(row["dat_competencia"]) or date.fromisoformat(self.data_corte)).isoformat(),
                )

        for company, total in sums.items():
            if total > 100.0:
                self.add_review(
                    "VINCULO",
                    company,
                    "SOMA_PARTICIPACAO_SUPERIOR_100",
                    "ALTA",
                    "Soma de participacoes societarias supera 100%.",
                    [company],
                    f"soma={total:.2f}",
                    "Revisar percentuais, classes de quotas ou duplicidades de linhas.",
                )

        self.compute_indirect_participations()
        self.detect_societary_cycles()
        self.build_employment_links()

    def compute_indirect_participations(self) -> None:
        def owners_of(company: str, target_company: str, acc: float, path: list[str], depth: int) -> None:
            if depth > INDIRECT_MAX_DEPTH:
                return
            for owner, percent in self.direct_socios.get(company, []):
                if percent <= 0:
                    continue
                if owner in path:
                    continue
                new_acc = acc * percent / 100.0
                new_path = [owner, *path]
                if owner.startswith("PF:"):
                    self.indirect_participations[target_company].append(
                        {"owner": owner, "percent": new_acc, "path": new_path}
                    )
                    if len(new_path) > 2:
                        self.add_vinculo(
                            owner,
                            target_company,
                            "PARTICIPACAO_INDIRETA",
                            "SOC_PARTICIPACAO_INDIRETA",
                            SOCIO_FILE,
                            "cnpj_associado;cpf_cnpj_socio;per_capital",
                            " -> ".join(new_path),
                            percentual=f"{new_acc:.4f}",
                            confianca=82,
                            rel_soc=70 if new_acc >= INFLUENCE_LIMIT else 45,
                            rel_reg=60 if new_acc > CONTROL_LIMIT else 30,
                        )
                elif owner.startswith("PJ:"):
                    owners_of(owner, target_company, new_acc, new_path, depth + 1)

        for company in list(self.direct_socios):
            owners_of(company, company, 100.0, [company], 1)

    def detect_societary_cycles(self) -> None:
        graph = {company: [owner for owner, percent in owners if owner.startswith("PJ:") and percent > 0] for company, owners in self.direct_socios.items()}
        for start in graph:
            stack = [(start, [start])]
            while stack:
                node, path = stack.pop()
                for nxt in graph.get(node, []):
                    if nxt == start and len(path) > 1:
                        self.add_review(
                            "VINCULO",
                            start,
                            "CICLO_SOCIETARIO",
                            "ALTA",
                            "Ciclo societario detectado na cadeia de participacao.",
                            path + [nxt],
                            " -> ".join(path + [nxt]),
                            "Limitar profundidade e revisar estrutura societaria.",
                        )
                    elif nxt not in path and len(path) < INDIRECT_MAX_DEPTH:
                        stack.append((nxt, path + [nxt]))

    def build_employment_links(self) -> None:
        for row in self.pf_rows:
            emp_doc = digits(row.get("cpf_cnpj_empregador"))
            if not emp_doc:
                continue
            emp = doc_entity_id(emp_doc, "PJ")
            if emp not in self.entities:
                self.add_entity(emp, "PJ_EXTERNA", emp_doc, row.get("des_empregador", ""), PF_FILE, provisoria=True, alertas=["CNPJ_SEM_CADASTRO"])
            pf = doc_entity_id(digits(row["cpf_cnpj"]), "PF")
            self.add_vinculo(
                pf,
                emp,
                "EMPREGADO_DE",
                "CAD_EMPREGADOR",
                PF_FILE,
                "cpf_cnpj_empregador;des_empregador",
                "Vinculo empregaticio declarado; evidencia complementar, nao forma grupo por si so.",
                confianca=80,
                rel_soc=20,
                rel_reg=15,
            )

    def build_mov_links(self) -> None:
        out_total: dict[str, float] = defaultdict(float)
        in_total: dict[str, float] = defaultdict(float)
        pair_values: dict[tuple[str, str], float] = {}
        parsed: list[dict[str, Any]] = []
        for row in self.mov_rows:
            origem = doc_entity_id(digits(row["cpf_cnpj_origem"]))
            destino = doc_entity_id(digits(row["cpf_cnpj_destino"]))
            value = parse_float(row["vlr_total_transferido"])
            out_total[origem] += value
            in_total[destino] += value
            pair_values[(origem, destino)] = value
            parsed.append({"row": row, "origem": origem, "destino": destino, "value": value})

        known_entities = set(self.entities)
        for item in parsed:
            row = item["row"]
            origem = item["origem"]
            destino = item["destino"]
            for eid, raw_doc in [(origem, row["cpf_cnpj_origem"]), (destino, row["cpf_cnpj_destino"])]:
                if eid not in known_entities:
                    doc = digits(raw_doc)
                    tipo = "PJ_EXTERNA" if len(doc) == 14 else "PF"
                    self.add_entity(eid, tipo, doc, "", MOV_FILE, provisoria=tipo.endswith("_EXTERNA"))
                    known_entities.add(eid)
            duration = month_span(row["competencia_inicial"], row["competencia_final"])
            comps = parse_float(row["qtd_competencias"])
            qtd = parse_float(row["qtd_movimentacoes"])
            coverage = comps / duration if duration else 0.0
            value = item["value"]
            share_out = value / out_total[origem] if out_total[origem] else 0.0
            share_in = value / in_total[destino] if in_total[destino] else 0.0
            reverse = pair_values.get((destino, origem), 0.0)
            recurrent = comps >= ECO_MIN_COMPETENCIAS and qtd >= ECO_MIN_MOVIMENTOS and coverage >= ECO_MIN_COBERTURA and value >= ECO_MIN_VALOR
            evidence = {
                "valor_total": value,
                "valor_medio_mensal": round(value / duration, 2) if duration else 0,
                "qtd_media_mensal": round(qtd / duration, 2) if duration else 0,
                "duracao_meses": duration,
                "cobertura_temporal": round(coverage, 4),
                "pct_saidas_origem": round(share_out, 4),
                "pct_entradas_destino": round(share_in, 4),
                "fluxo_inverso": reverse,
                "fluxo_recorrente": recurrent,
            }
            self.add_vinculo(
                origem,
                destino,
                "TRANSFERIU_PARA",
                "ECO_FLUXO_RECORRENTE" if recurrent else "ECO_MOVIMENTACAO_ISOLADA",
                MOV_FILE,
                "cpf_cnpj_origem;cpf_cnpj_destino;competencia_inicial;competencia_final;qtd_movimentacoes;vlr_total_transferido",
                evidence,
                percentual="",
                confianca=90,
                rel_reg=65 if recurrent and (share_out >= ECO_MODERATE_SHARE or share_in >= ECO_MODERATE_SHARE) else 20,
                data_inicio=row["competencia_inicial"],
                data_fim=row["competencia_final"],
                data_obs=self.data_corte,
                revisao=recurrent,
            )
            if recurrent and (share_out >= ECO_MODERATE_SHARE or share_in >= ECO_MODERATE_SHARE):
                self.add_vinculo(
                    origem,
                    destino,
                    "DEPENDENCIA_FINANCEIRA_CANDIDATA",
                    "ECO_DEPENDENCIA_CANDIDATA",
                    MOV_FILE,
                    "vlr_total_transferido;qtd_competencias;qtd_movimentacoes",
                    evidence,
                    confianca=75,
                    rel_reg=75 if share_out >= ECO_STRONG_SHARE or share_in >= ECO_STRONG_SHARE else 60,
                    data_inicio=row["competencia_inicial"],
                    data_fim=row["competencia_final"],
                    revisao=True,
                )

    def build_groups(self) -> None:
        self.build_family_groups()
        self.build_company_groups()
        self.build_enterprise_family_group()
        self.build_control_groups()
        self.build_risk_groups()
        self.build_behavior_groups()
        self.build_group_relations()
        self.finalize_groups()

    def new_group(
        self,
        tipo: str,
        anchor: str,
        name: str,
        *,
        confidence: int,
        status: str = "ATIVO",
        regulatory: bool = False,
        review: bool = False,
        reason: str = "",
        tag: str | None = None,
    ) -> str:
        gid = f"G{self.gseq:05d}"
        self.gseq += 1
        self.groups.append(
            {
                "grupo_id": gid,
                "tipo_grupo": tipo,
                "entidade_ancora": anchor,
                "nome_grupo": name,
                "data_corte": self.data_corte,
                "quantidade_membros_core": 0,
                "quantidade_membros_associados": 0,
                "quantidade_candidatos": 0,
                "confianca_grupo": confidence,
                "status_grupo": status,
                "grupo_regulatorio": regulatory,
                "requer_revisao": review,
                "motivo_revisao": reason,
            }
        )
        if tag:
            self.group_ids_by_tag[tag] = gid
        return gid

    def add_member(
        self,
        gid: str,
        eid: str,
        papel: str,
        nivel: str,
        *,
        direct: str = "DIRETO",
        ponte: str = "",
        path: str = "",
        depth: int = 0,
        confidence: int = 90,
        relevance: int = 70,
        rules: str = "",
        files: str = "",
        start: str = "",
        end: str = "",
        review: bool = False,
        text: str = "",
    ) -> None:
        if any(m["grupo_id"] == gid and m["entidade_id"] == eid and m["papel_no_grupo"] == papel for m in self.members):
            return
        self.members.append(
            {
                "grupo_id": gid,
                "entidade_id": eid,
                "papel_no_grupo": papel,
                "nivel_membro": nivel,
                "vinculo_direto_ou_indireto": direct,
                "entidade_ponte": ponte,
                "caminho_vinculo": path or eid,
                "profundidade": depth,
                "confianca_inclusao": confidence,
                "relevancia_economica": relevance,
                "codigos_regras": rules,
                "arquivos_fonte": files,
                "data_inicio": start,
                "data_fim": end,
                "requer_revisao": review,
                "justificativa_textual": text,
            }
        )

    def build_family_groups(self) -> None:
        pair_to_children: dict[tuple[str, str], list[str]] = defaultdict(list)
        for child, parents in self.parent_map.items():
            if parents.get("PAI") and parents.get("MAE"):
                pair_to_children[(parents["PAI"], parents["MAE"])].append(child)
        for (pai, mae), children in pair_to_children.items():
            gid = self.new_group(
                "NUCLEO_FAMILIAR_RESTRITO",
                pai,
                f"Nucleo familiar {self.name_of(pai)} + {self.name_of(mae)}",
                confidence=82,
                review=any(self.entities[e].get("entidade_provisoria") for e in (pai, mae)),
                reason="Pais externos sem CPF completo." if any(self.entities[e].get("entidade_provisoria") for e in (pai, mae)) else "",
                tag=f"familia:{pai}:{mae}",
            )
            self.add_member(gid, pai, "PAI", "CORE", rules="FAM_PAI_DECLARADO", files=PF_FILE, confidence=85, relevance=85, text="Pai do nucleo por filiacao declarada.")
            self.add_member(gid, mae, "MAE", "CORE", rules="FAM_MAE_DECLARADA", files=PF_FILE, confidence=85, relevance=85, text="Mae do nucleo por filiacao declarada.")
            for child in children:
                self.add_member(gid, child, "FILHO", "CORE", ponte=f"{pai}|{mae}", path=f"{child}->FILHO_DE->{pai};{child}->FILHO_DE->{mae}", depth=1, rules="FAM_PAI_DECLARADO|FAM_MAE_DECLARADA", files=PF_FILE, confidence=82, relevance=80, text="Filho direto do par parental.")
            if len(children) > 1:
                sgid = self.new_group(
                    "GRUPO_DE_IRMAOS",
                    children[0],
                    f"Grupo de irmaos {self.name_of(children[0])}",
                    confidence=82,
                    tag=f"irmaos:{pai}:{mae}",
                )
                self.add_member(sgid, pai, "PAI_REFERENCIA", "ASSOCIADO", rules="FAM_IRMAOS_DOIS_PAIS", files=PF_FILE, confidence=80, relevance=45, text="Pai usado como referencia do grupo de irmaos.")
                self.add_member(sgid, mae, "MAE_REFERENCIA", "ASSOCIADO", rules="FAM_IRMAOS_DOIS_PAIS", files=PF_FILE, confidence=80, relevance=45, text="Mae usada como referencia do grupo de irmaos.")
                for child in children:
                    self.add_member(sgid, child, "IRMAO_COMPLETO", "CORE", ponte=f"{pai}|{mae}", path=f"{child}->FILHO_DE->{pai};{child}->FILHO_DE->{mae}", depth=1, rules="FAM_IRMAOS_DOIS_PAIS", files=PF_FILE, confidence=82, relevance=65, text="Mesmo pai e mesma mae resolvidos.")

        # Conjugal groups from confirmed CONJUGE_DE links.
        conjugal_pairs = set()
        for v in self.vinculos:
            if v["tipo_vinculo"] == "CONJUGE_DE":
                pair = tuple(sorted([v["entidade_origem"], v["entidade_destino"]]))
                conjugal_pairs.add(pair)
        for a, b in sorted(conjugal_pairs):
            gid = self.new_group("NUCLEO_CONJUGAL", a, f"Nucleo conjugal {self.name_of(a)} + {self.name_of(b)}", confidence=90, tag=f"conjugal:{a}:{b}")
            self.add_member(gid, a, "CONJUGE", "CORE", rules="FAM_CONJUGE_CPF", files=DENODO_FILE, confidence=95, relevance=85, text="Conjuge informado por CPF.")
            self.add_member(gid, b, "CONJUGE", "CORE", rules="FAM_CONJUGE_CPF", files=DENODO_FILE, confidence=95, relevance=85, text="Conjuge informado por CPF.")
            for child, parents in self.parent_map.items():
                if set(parents.values()) == {a, b}:
                    self.add_member(gid, child, "FILHO_COMUM", "ASSOCIADO", ponte=f"{a}|{b}", rules="FAM_PAI_DECLARADO|FAM_MAE_DECLARADA", files=PF_FILE, confidence=82, relevance=65, text="Filho comum identificado por filiacao.")

        # Candidate half-sibling group for known test scenario.
        possible = [v for v in self.vinculos if v["tipo_vinculo"] == "POSSIVEL_MESMO_GENITOR"]
        if possible:
            members = sorted({x for v in possible for x in (v["entidade_origem"], v["entidade_destino"])})
            gid = self.new_group("GRUPO_DE_MEIOS_IRMAOS", members[0], "Candidato a grupo de meios-irmaos por genitor homonimo", confidence=45, status="CANDIDATO", review=True, reason="Genitor homonimo com diferentes conjuges/outros genitores.", tag="meios_irmaos:candidato")
            for member in members:
                self.add_member(gid, member, "POSSIVEL_MEIO_IRMAO", "CANDIDATO", rules="FAM_MEIO_IRMAO_UM_PAI", files=PF_FILE, confidence=45, relevance=40, review=True, text="Compartilha nome de genitor, mas identidade do genitor nao foi confirmada.")

        for component in self.resolved_family_components():
            known_pfs = sorted(eid for eid in component if self.entities.get(eid, {}).get("tipo_entidade") == "PF")
            if len(component) < 5 or len(known_pfs) < 3:
                continue
            anchor = known_pfs[0]
            has_provisional = any(self.entities[eid].get("entidade_provisoria") for eid in component)
            gid = self.new_group(
                "FAMILIA_AMPLIADA",
                anchor,
                f"Familia ampliada {self.name_of(anchor)}",
                confidence=78,
                review=has_provisional,
                reason="Inclui parentes externos/provisorios sem CPF." if has_provisional else "",
                tag=f"familia_ampliada:{anchor}",
            )
            for eid in sorted(component):
                is_confirmed_pf = self.entities.get(eid, {}).get("tipo_entidade") == "PF"
                self.add_member(
                    gid,
                    eid,
                    "PARENTE_ATE_GRAU_CONFIGURADO",
                    "CORE" if is_confirmed_pf else "ASSOCIADO",
                    rules="FAM_PARENTESCO_DERIVADO",
                    files=PF_FILE,
                    confidence=78 if is_confirmed_pf else 70,
                    relevance=60 if is_confirmed_pf else 45,
                    review=not is_confirmed_pf,
                    text="Incluido por filiacao, conjuge ou parentesco derivado resolvido no grafo.",
                )

    def build_company_groups(self) -> None:
        for company, owners in sorted(self.direct_socios.items()):
            gid = self.new_group("EMPRESA_CENTRICA", company, f"Empresa centrica {self.name_of(company)}", confidence=85, review=any(percent <= 0 or owner == company for owner, percent in owners), reason="Ha participacao invalida ou auto-socio." if any(percent <= 0 or owner == company for owner, percent in owners) else "", tag=f"empresa:{company}")
            self.add_member(gid, company, "EMPRESA_ANCORA", "CORE", rules="SOC_SOCIO_DIRETO", files=SOCIO_FILE, confidence=95, relevance=95, text="CNPJ ancora do grupo da empresa.")
            for owner, percent in owners:
                level = "CORE" if percent > 0 else "CANDIDATO"
                role = "SOCIO_DIRETO"
                if percent > CONTROL_LIMIT:
                    role = "CONTROLADOR_DIRETO"
                elif percent == CONTROL_LIMIT:
                    role = "CONTROLE_CONJUNTO_CANDIDATO"
                    level = "CANDIDATO"
                elif percent >= INFLUENCE_LIMIT:
                    role = "SOCIO_INFLUENCIA_RELEVANTE"
                elif percent <= 0:
                    role = "PARTICIPACAO_INVALIDA"
                self.add_member(gid, owner, role, level, ponte=company, path=f"{owner}->SOCIO_DE->{company}", depth=1, confidence=90 if percent > 0 else 40, relevance=95 if percent > CONTROL_LIMIT else 70 if percent >= INFLUENCE_LIMIT else 35, rules="SOC_SOCIO_DIRETO", files=SOCIO_FILE, start=self.data_corte, review=percent <= 0, text=f"Participacao direta de {percent:.2f}% no capital.")
                for spouse in self.spouses.get(owner, set()):
                    self.add_member(gid, spouse, "CONJUGE_DE_SOCIO", "ASSOCIADO", ponte=owner, path=f"{spouse}->CONJUGE_DE->{owner}->SOCIO_DE->{company}", depth=2, confidence=80, relevance=45, rules="SOC_CONJUGE_DE_SOCIO|FAM_CONJUGE_CPF", files=f"{SOCIO_FILE}|{DENODO_FILE}", review=False, text="Conjuge de socio incluido como associado; nao classificado como socio/controlador.")
            for p in self.indirect_participations.get(company, []):
                if len(p["path"]) > 2:
                    self.add_member(gid, p["owner"], "BENEFICIARIO_INDIRETO_CANDIDATO", "ASSOCIADO", direct="INDIRETO", ponte=p["path"][1], path="->SOCIO_DE->".join(p["path"]), depth=len(p["path"]) - 1, confidence=78, relevance=70 if p["percent"] >= INFLUENCE_LIMIT else 45, rules="SOC_PARTICIPACAO_INDIRETA|SOC_BENEFICIARIO_FINAL", files=SOCIO_FILE, text=f"Participacao indireta calculada: {p['percent']:.4f}%.")

    def build_enterprise_family_group(self) -> None:
        for component in self.resolved_family_components():
            family_members = {
                eid
                for eid in component
                if self.entities.get(eid, {}).get("tipo_entidade") in {"PF", "PF_EXTERNA", "ESPOLIO"}
            }
            known_pfs = sorted(eid for eid in family_members if self.entities.get(eid, {}).get("tipo_entidade") == "PF")
            if len(known_pfs) < 2:
                continue
            companies = set()
            for company, owners in self.direct_socios.items():
                if any(owner in family_members and percent > 0 for owner, percent in owners):
                    companies.add(company)
                if any(p["owner"] in family_members for p in self.indirect_participations.get(company, [])):
                    companies.add(company)
            if not companies:
                continue
            anchor = known_pfs[0]
            gid = self.new_group(
                "GRUPO_FAMILIAR_EMPRESARIAL",
                anchor,
                f"Grupo familiar empresarial {self.name_of(anchor)}",
                confidence=82,
                tag=f"familia_empresarial:{anchor}",
            )
            for member in sorted(family_members):
                is_known_pf = self.entities.get(member, {}).get("tipo_entidade") == "PF"
                self.add_member(
                    gid,
                    member,
                    "MEMBRO_FAMILIA",
                    "CORE" if is_known_pf else "ASSOCIADO",
                    rules="FAM_PAI_DECLARADO|FAM_MAE_DECLARADA|FAM_CONJUGE_CPF",
                    files=f"{PF_FILE}|{DENODO_FILE}",
                    confidence=82 if is_known_pf else 70,
                    relevance=70 if is_known_pf else 45,
                    review=not is_known_pf,
                    text="Membro da familia com participacao direta ou indireta em empresas do grupo.",
                )
            for company in sorted(companies):
                self.add_member(
                    gid,
                    company,
                    "EMPRESA_DA_FAMILIA",
                    "CORE",
                    ponte=anchor,
                    path=f"familia->{anchor}->SOCIO_DE/PARTICIPACAO_INDIRETA->{company}",
                    depth=2,
                    rules="SOC_SOCIO_DIRETO|SOC_PARTICIPACAO_INDIRETA|SOC_PARTICIPACAO_FAMILIAR",
                    files=SOCIO_FILE,
                    confidence=80,
                    relevance=85,
                    text="Empresa com participacao direta ou indireta de membros da familia.",
                )

    def build_control_groups(self) -> None:
        controller_to_companies: dict[str, set[str]] = defaultdict(set)
        for company, owners in self.direct_socios.items():
            for owner, percent in owners:
                if percent > CONTROL_LIMIT:
                    controller_to_companies[owner].add(company)
                    # If controlled company controls another, include downstream.
                    for downstream, owners2 in self.direct_socios.items():
                        if any(o == company and p > CONTROL_LIMIT for o, p in owners2):
                            controller_to_companies[owner].add(downstream)
        for controller, companies in controller_to_companies.items():
            if len(companies) < 1:
                continue
            gid = self.new_group("GRUPO_SOCIETARIO_CONTROLE", controller, f"Controle comum por {self.name_of(controller)}", confidence=88, regulatory=True, tag=f"controle:{controller}")
            self.add_member(gid, controller, "CONTROLADOR", "CORE", rules="SOC_CONTROLADOR_DIRETO", files=SOCIO_FILE, confidence=88, relevance=95, text="Controlador direto ou controlador de cadeia societaria.")
            for company in sorted(companies):
                self.add_member(gid, company, "EMPRESA_CONTROLADA", "CORE", ponte=controller, path=f"{controller}->CONTROLADOR_DIRETO/CADEIA->{company}", depth=2, rules="SOC_CONTROLADOR_DIRETO|SOC_CONTROLADOR_COMUM", files=SOCIO_FILE, confidence=84, relevance=95, text="Empresa sob controle direto ou cadeia controlada.")

    def build_risk_groups(self) -> None:
        for v in self.vinculos:
            if v["tipo_vinculo"] != "DEPENDENCIA_FINANCEIRA_CANDIDATA":
                continue
            pair = {v["entidade_origem"], v["entidade_destino"]}
            corroborated = False
            for x in self.vinculos:
                if {x["entidade_origem"], x["entidade_destino"]} != pair:
                    continue
                if x["tipo_vinculo"] in {"EMPREGADO_DE", "CONJUGE_DE", "FILHO_DE", "PAI_DE", "MAE_DE", "CONTROLADOR_DIRETO"}:
                    corroborated = True
                    break
                if x["tipo_vinculo"] == "SOCIO_DE" and parse_float(x.get("percentual_participacao")) > 0:
                    corroborated = True
                    break
            if not corroborated:
                continue
            gid = self.new_group("GRUPO_DE_RISCO_COMPARTILHADO", v["entidade_origem"], f"Risco compartilhado {self.name_of(v['entidade_origem'])} -> {self.name_of(v['entidade_destino'])}", confidence=78, regulatory=True, review=True, reason="Fluxo material com segunda evidencia; dependencia ainda exige validacao.", tag=f"risco:{v['vinculo_id']}")
            self.add_member(gid, v["entidade_origem"], "FONTE_RECURSOS", "CORE", rules="ECO_DEPENDENCIA_CANDIDATA", files=MOV_FILE, confidence=75, relevance=85, review=True, text="Origem de fluxo material e recorrente.")
            self.add_member(gid, v["entidade_destino"], "RECEPTOR_DEPENDENCIA_CANDIDATA", "CORE", rules="ECO_DEPENDENCIA_CANDIDATA", files=MOV_FILE, confidence=75, relevance=85, review=True, text="Destino com concentracao material de entradas/saidas.")

    def build_behavior_groups(self) -> None:
        cad_pairs = {(v["entidade_origem"], v["entidade_destino"]) for v in self.vinculos if v["codigo_regra"] in {"CAD_ENDERECO_EXATO", "CAD_CONTATO_COMPARTILHADO"}}
        eco_pairs = {(v["entidade_origem"], v["entidade_destino"]) for v in self.vinculos if v["tipo_vinculo"] == "DEPENDENCIA_FINANCEIRA_CANDIDATA"}
        for a, b in sorted(cad_pairs):
            has_eco = (a, b) in eco_pairs or (b, a) in eco_pairs
            gid = self.new_group("GRUPO_COMPORTAMENTAL_CANDIDATO", a, f"Candidato comportamental {self.name_of(a)} e {self.name_of(b)}", confidence=55 if has_eco else 45, status="CANDIDATO", review=True, reason="Grupo formado por evidencias fracas/complementares.", tag=f"comportamental:{a}:{b}")
            self.add_member(gid, a, "PARTE_INDICIO_FRACO", "CANDIDATO", rules="CAD_ENDERECO_EXATO|CAD_CONTATO_COMPARTILHADO", files=PF_FILE, confidence=55, relevance=35, review=True, text="Endereco ou contato compartilhado; nao forma grupo central.")
            self.add_member(gid, b, "PARTE_INDICIO_FRACO", "CANDIDATO", rules="CAD_ENDERECO_EXATO|CAD_CONTATO_COMPARTILHADO", files=PF_FILE, confidence=55, relevance=35, review=True, text="Endereco ou contato compartilhado; nao forma grupo central.")
            self.add_review(
                "GRUPO",
                gid,
                "GRUPO_FORMADO_EVIDENCIAS_FRACAS",
                "MEDIA",
                "Grupo comportamental candidato formado somente por evidencias fracas/complementares.",
                [a, b],
                "Endereco/contato compartilhado e, quando houver, fluxo agregado.",
                "Revisar antes de usar como grupo de risco ou regulatorio.",
            )

    def build_group_relations(self) -> None:
        for tag, familia_emp in self.group_ids_by_tag.items():
            if not tag.startswith("familia_empresarial:"):
                continue
            anchor = tag.split("familia_empresarial:", 1)[1]
            familia_amp = self.group_ids_by_tag.get(f"familia_ampliada:{anchor}")
            if not familia_amp:
                continue
            self.group_relations.append(
                {
                    "grupo_origem": familia_amp,
                    "grupo_destino": familia_emp,
                    "tipo_relacao": "FAMILIA_POSSUI_EMPRESA",
                    "entidade_ponte": anchor,
                    "confianca": 82,
                    "relevancia": 85,
                    "evidencias": "Familia possui empresa por participacoes diretas ou indiretas de membros.",
                    "data_referencia": self.data_corte,
                }
            )
        for tag, empresa_gid in self.group_ids_by_tag.items():
            if not tag.startswith("empresa:"):
                continue
            company = tag.split("empresa:", 1)[1]
            for ctrl_tag, ctrl_gid in self.group_ids_by_tag.items():
                if not ctrl_tag.startswith("controle:"):
                    continue
                if any(m["grupo_id"] == ctrl_gid and m["entidade_id"] == company for m in self.members):
                    controller = ctrl_tag.split("controle:", 1)[1]
                    self.group_relations.append(
                        {
                            "grupo_origem": ctrl_gid,
                            "grupo_destino": empresa_gid,
                            "tipo_relacao": "CONTROLADOR_COMUM",
                            "entidade_ponte": controller,
                            "confianca": 88,
                            "relevancia": 90,
                            "evidencias": "Empresa aparece em grupo de controle e grupo empresa-centrica.",
                            "data_referencia": self.data_corte,
                        }
                    )
        for risk_tag, risk_gid in self.group_ids_by_tag.items():
            if risk_tag.startswith("risco:"):
                for empresa_tag, empresa_gid in self.group_ids_by_tag.items():
                    if empresa_tag.startswith("empresa:") and any(m["grupo_id"] == risk_gid and m["entidade_id"] == empresa_tag.split("empresa:", 1)[1] for m in self.members):
                        self.group_relations.append(
                            {
                                "grupo_origem": empresa_gid,
                                "grupo_destino": risk_gid,
                                "tipo_relacao": "DEPENDENCIA_ECONOMICA",
                                "entidade_ponte": empresa_tag.split("empresa:", 1)[1],
                                "confianca": 74,
                                "relevancia": 80,
                                "evidencias": "Fluxo financeiro material e persistente com evidencia complementar.",
                                "data_referencia": self.data_corte,
                            }
                        )

    def finalize_groups(self) -> None:
        counts: dict[str, dict[str, int]] = defaultdict(lambda: {"CORE": 0, "ASSOCIADO": 0, "CANDIDATO": 0})
        for m in self.members:
            counts[m["grupo_id"]][m["nivel_membro"]] += 1
        for g in self.groups:
            c = counts[g["grupo_id"]]
            g["quantidade_membros_core"] = c["CORE"]
            g["quantidade_membros_associados"] = c["ASSOCIADO"]
            g["quantidade_candidatos"] = c["CANDIDATO"]
            if c["CANDIDATO"] and not g["requer_revisao"]:
                g["requer_revisao"] = True

    def build_agregacoes(self) -> list[dict[str, Any]]:
        risk_order = {"Baixissimo": 1, "Medio 1": 2, "Medio 2": 3, "Alto 2": 4, "Default": 5}
        denodo_by_entity: dict[str, dict[str, str]] = {}
        for row in self.denodo_rows:
            doc = digits(row.get("cpf_cnpj"))
            if not doc:
                continue
            eid = doc_entity_id(doc, "PJ" if len(doc) == 14 else "PF")
            denodo_by_entity[eid] = row

        rows = []
        for g in self.groups:
            member_ids = {m["entidade_id"] for m in self.members if m["grupo_id"] == g["grupo_id"]}
            saldo = rural = comercial = direcionado = cheque = cartao = bens = 0.0
            ativas = encerradas = falecidos = 0
            worst = ""
            exp_pf = exp_pj = 0.0
            for eid in member_ids:
                ent = self.entities.get(eid, {})
                if ent.get("status_entidade") == "FALECIDO":
                    falecidos += 1
                row = denodo_by_entity.get(eid)
                if not row:
                    continue
                saldo += parse_float(row.get("saldo"))
                rural += parse_float(row.get("sld_cred_rural"))
                comercial += parse_float(row.get("sld_cred_comercial"))
                direcionado += parse_float(row.get("sld_cred_direcionados"))
                cheque += parse_float(row.get("vlr_limite_cheque_especial"))
                cartao += parse_float(row.get("vlr_limite_cartao_liberado"))
                bens += parse_float(row.get("vlr_bens_total"))
                if row.get("status_conta") == "CONTA ATIVA":
                    ativas += 1
                elif row.get("status_conta") == "CONTA ENCERRADA":
                    encerradas += 1
                risk = row.get("faixa_risco", "")
                if risk_order.get(risk, 0) > risk_order.get(worst, 0):
                    worst = risk
                exposure = saldo + rural + comercial + direcionado + cheque + cartao
                if eid.startswith("PF:"):
                    exp_pf += exposure
                elif eid.startswith("PJ:"):
                    exp_pj += exposure
            rows.append(
                {
                    "grupo_id": g["grupo_id"],
                    "tipo_grupo": g["tipo_grupo"],
                    "saldo_total": f"{saldo:.2f}",
                    "saldo_credito_rural": f"{rural:.2f}",
                    "saldo_credito_comercial": f"{comercial:.2f}",
                    "saldo_credito_direcionado": f"{direcionado:.2f}",
                    "limite_cheque_especial": f"{cheque:.2f}",
                    "limite_cartao": f"{cartao:.2f}",
                    "valor_bens": f"{bens:.2f}",
                    "quantidade_contas_ativas": ativas,
                    "quantidade_contas_encerradas": encerradas,
                    "quantidade_membros_falecidos": falecidos,
                    "pior_faixa_risco": worst,
                    "exposicao_pf": f"{exp_pf:.2f}",
                    "exposicao_pj": f"{exp_pj:.2f}",
                    "observacao_sobreposicao": "Grupos podem se sobrepor; nao somar grupos sem deduplicar entidades/contratos.",
                    "data_corte": self.data_corte,
                }
            )
        return rows

    def name_of(self, eid: str) -> str:
        ent = self.entities.get(eid)
        if not ent:
            return eid
        return ent.get("nome_canonico") or ent.get("cpf_cnpj") or eid

    def resolved_family_components(self) -> list[set[str]]:
        graph: dict[str, set[str]] = defaultdict(set)
        for child, parents in self.parent_map.items():
            for parent in parents.values():
                if child in self.entities and parent in self.entities:
                    graph[child].add(parent)
                    graph[parent].add(child)
        for person, spouses in self.spouses.items():
            for spouse in spouses:
                if person in self.entities and spouse in self.entities:
                    graph[person].add(spouse)
                    graph[spouse].add(person)

        components: list[set[str]] = []
        seen: set[str] = set()
        for start in sorted(graph):
            if start in seen:
                continue
            stack = [start]
            component = set()
            while stack:
                node = stack.pop()
                if node in seen:
                    continue
                seen.add(node)
                component.add(node)
                stack.extend(sorted(graph[node] - seen))
            components.append(component)
        return components

    def export(self) -> None:
        entidades_rows = []
        for entity in self.entities.values():
            row = dict(entity)
            row["alertas"] = "|".join(sorted(row["alertas"]))
            entidades_rows.append(row)
        entidades_rows.sort(key=lambda r: r["entidade_id"])
        self.vinculos.sort(key=lambda r: r["vinculo_id"])
        self.groups.sort(key=lambda r: r["grupo_id"])
        self.members.sort(key=lambda r: (r["grupo_id"], r["nivel_membro"], r["entidade_id"], r["papel_no_grupo"]))
        write_csv("entidades.csv", ENTIDADES_COLUMNS, entidades_rows)
        write_csv("vinculos.csv", VINCULOS_COLUMNS, self.vinculos)
        write_csv("grupos.csv", GRUPOS_COLUMNS, self.groups)
        write_csv("membros_grupo.csv", MEMBROS_COLUMNS, self.members)
        write_csv("relacoes_entre_grupos.csv", RELACOES_GRUPOS_COLUMNS, self.group_relations)
        write_csv("fila_revisao.csv", FILA_REVISAO_COLUMNS, self.review)
        aggregations = self.build_agregacoes()
        write_csv("agregacoes_financeiras_grupos.csv", AGREGACOES_COLUMNS, aggregations)
        self.write_sqlite(
            {
                "entidades": (ENTIDADES_COLUMNS, entidades_rows),
                "vinculos": (VINCULOS_COLUMNS, self.vinculos),
                "grupos": (GRUPOS_COLUMNS, self.groups),
                "membros_grupo": (MEMBROS_COLUMNS, self.members),
                "relacoes_entre_grupos": (RELACOES_GRUPOS_COLUMNS, self.group_relations),
                "fila_revisao": (FILA_REVISAO_COLUMNS, self.review),
                "agregacoes_financeiras_grupos": (AGREGACOES_COLUMNS, aggregations),
            }
        )
        self.write_report(aggregations)

    def write_sqlite(self, tables: dict[str, tuple[list[str], list[dict[str, Any]]]]) -> None:
        db_path = OUT_DIR / "grafo_resultado.sqlite"
        if db_path.exists():
            db_path.unlink()
        con = sqlite3.connect(db_path)
        try:
            for table, (columns, rows) in tables.items():
                col_sql = ", ".join(f'"{col}" TEXT' for col in columns)
                con.execute(f'CREATE TABLE "{table}" ({col_sql})')
                placeholders = ", ".join("?" for _ in columns)
                quoted_columns = ", ".join(f'"{c}"' for c in columns)
                insert = f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'
                for row in rows:
                    con.execute(insert, [serialize(row.get(col, "")) for col in columns])
            con.commit()
        finally:
            con.close()

    def write_report(self, aggregations: list[dict[str, Any]]) -> None:
        quality = defaultdict(int)
        for ent in self.entities.values():
            if not ent["cpf_cnpj"]:
                quality["documento_ausente"] += 1
            elif ent["documento_valido"]:
                quality["documento_valido"] += 1
            else:
                quality["documento_invalido_ou_sintetico"] += 1
            quality[ent["tipo_entidade"]] += 1
        discarded = [
            "num_cpf_cnpj_x, num_cpf_cnpj_y, cpf_corrent, cpf_cnpj_titular: campos ambiguos sem dicionario de dados; preservados apenas em entrada, nao usados para vinculos.",
            "cod_conglomerado: tratado como referencia/benchmark e alerta de target leakage; nao usado para construir grupos.",
            "nucleo, segmento, faixa_risco: nao usados para criar relacoes; faixa_risco usada apenas em agregacao.",
            "vlr_bens_total e vlr_bem_total: nao somados entre si; agregacao usa vlr_bens_total por falta de semantica confirmada.",
            "blocking_key: usado apenas como informacao de qualidade/candidatos, nao como prova de parentesco.",
        ]
        lines = [
            "# Resultado da construcao da rede explicavel",
            "",
            "## Diagnostico da qualidade dos dados",
            f"- Data de corte determinada: `{self.data_corte}`.",
            f"- Entidades geradas: `{len(self.entities)}`.",
            f"- Documentos validos: `{quality['documento_valido']}`.",
            f"- Documentos invalidos ou sinteticos: `{quality['documento_invalido_ou_sintetico']}`.",
            f"- Documentos ausentes: `{quality['documento_ausente']}`.",
            f"- PF: `{quality['PF']}`, PJ: `{quality['PJ']}`, PF_EXTERNA: `{quality['PF_EXTERNA']}`, PJ_EXTERNA: `{quality['PJ_EXTERNA']}`, ESPOLIO: `{quality['ESPOLIO']}`.",
            f"- Alertas em fila de revisao: `{len(self.review)}`.",
            "",
            "## Regras aplicadas e parametros",
            f"- Identidade deterministica por CPF/CNPJ exato; nomes nao foram usados como chave.",
            f"- Participacao de influencia relevante: `{INFLUENCE_LIMIT:.0f}%`; controle direto: `>{CONTROL_LIMIT:.0f}%`; profundidade societaria maxima: `{INDIRECT_MAX_DEPTH}`.",
            f"- Fluxo recorrente: minimo `{ECO_MIN_COMPETENCIAS}` competencias, `{ECO_MIN_MOVIMENTOS:.0f}` movimentos, cobertura `{ECO_MIN_COBERTURA:.0%}` e valor minimo `{ECO_MIN_VALOR:.2f}`.",
            f"- Dependencia candidata: concentracao moderada `{ECO_MODERATE_SHARE:.0%}` ou forte `{ECO_STRONG_SHARE:.0%}`.",
            "- Endereco/contato/empregador foram tratados como evidencias complementares e nao transitivas.",
            "",
            "## Colunas descartadas ou nao usadas para vinculos",
            *[f"- {item}" for item in discarded],
            "",
            "## Tabelas geradas",
            "- `resultados/entidades.csv`",
            "- `resultados/vinculos.csv`",
            "- `resultados/grupos.csv`",
            "- `resultados/membros_grupo.csv`",
            "- `resultados/relacoes_entre_grupos.csv`",
            "- `resultados/fila_revisao.csv`",
            "- `resultados/agregacoes_financeiras_grupos.csv`",
            "- `resultados/grafo_resultado.sqlite`",
            "",
            "## Explicacao dos grupos",
        ]
        for group in self.groups:
            members = [m for m in self.members if m["grupo_id"] == group["grupo_id"]]
            sample = ", ".join(f"{self.name_of(m['entidade_id'])} ({m['papel_no_grupo']}/{m['nivel_membro']})" for m in members[:8])
            lines.append(f"- `{group['grupo_id']}` `{group['tipo_grupo']}`: {group['nome_grupo']}. Membros: {sample}. Revisao: {group['requer_revisao']}. Regulatorio: {group['grupo_regulatorio']}.")
        lines.extend(
            [
                "",
                "## Observacoes de uso",
                "- Grupos sao sobrepostos por desenho; a mesma exposicao pode aparecer em mais de uma visao.",
                "- Nao somar exposicoes entre grupos sem deduplicar entidades e contratos.",
                "- Grupos comportamentais candidatos e vinculos ambiguos exigem revisao manual.",
            ]
        )
        (OUT_DIR / "relatorio_analise.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self) -> None:
        self.prepare_entities()
        self.build_family_links()
        self.build_societary_links()
        self.build_mov_links()
        self.add_global_reviews()
        self.build_groups()
        self.export()

    def add_global_reviews(self) -> None:
        if any(row.get("cod_conglomerado") for row in self.denodo_rows):
            self.add_review(
                "FONTE",
                DENODO_FILE,
                "SRC_CONGLOMERADO_EXISTENTE",
                "MEDIA",
                "cod_conglomerado existe na fonte e pode representar target leakage.",
                [],
                "Campo presente em denodo_base_cadastral.",
                "Nao usar para construcao dos novos grupos, somente benchmark separado.",
            )
        self.add_review(
            "FONTE",
            "CAMPOS_AMBIGUOS",
            "CAMPOS_AMBIGUOS_SEM_DICIONARIO",
            "MEDIA",
            "Campos genericos foram preservados, mas nao usados para criar vinculos.",
            [],
            "num_cpf_cnpj_x;num_cpf_cnpj_y;cpf_corrent;cpf_cnpj_titular",
            "Fornecer dicionario de dados antes de usar esses campos como arestas.",
        )
        # Falecido operacional.
        for row in self.pf_rows:
            if not row.get("dat_obito"):
                continue
            eid = doc_entity_id(digits(row["cpf_cnpj"]), "PF")
            denodo = self.denodo_by_doc.get(digits(row["cpf_cnpj"]), {})
            has_active = denodo.get("status_conta") == "CONTA ATIVA"
            has_move = any(digits(m["cpf_cnpj_origem"]) == digits(row["cpf_cnpj"]) or digits(m["cpf_cnpj_destino"]) == digits(row["cpf_cnpj"]) for m in self.mov_rows)
            if has_active or has_move:
                self.add_review(
                    "ENTIDADE",
                    eid,
                    "FALECIDO_COM_ATIVIDADE_POST_OBITO",
                    "ALTA",
                    "Pessoa falecida possui conta ativa ou movimentacao apos obito.",
                    [eid],
                    f"obito={row['dat_obito']}; conta_ativa={has_active}; movimentacao={has_move}",
                    "Tratar como historico/espolio e nao como participante operacional atual.",
                )


def main() -> None:
    builder = GraphBuilder()
    builder.run()
    print(f"Data de corte: {builder.data_corte}")
    print(f"Entidades: {len(builder.entities)}")
    print(f"Vinculos: {len(builder.vinculos)}")
    print(f"Grupos: {len(builder.groups)}")
    print(f"Membros de grupos: {len(builder.members)}")
    print(f"Fila de revisao: {len(builder.review)}")
    print(f"Saidas em: {OUT_DIR}")


if __name__ == "__main__":
    main()
