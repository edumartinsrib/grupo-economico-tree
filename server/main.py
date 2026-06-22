from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import unicodedata

import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "resultados" / "grafo_resultado.sqlite"

app = FastAPI(
    title="Grupo Econômico Tree API",
    version="5.0.0",
    description="API simples para explorar vínculos familiares e empresariais sob demanda.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conjunto de vínculos por escopo.
FAMILY_RELATIONS = {
    "FILHO_DE",
    "PAI_DE",
    "MAE_DE",
    "IRMAO_DE",
    "CONJUGE_DE",
    "CONJUGE_NOME_CANDIDATO",
}

WEAK_FAMILY_RELATIONS = {
    "PARENTESCO_AMBIGUO",
    "POSSIVEL_MESMO_GENITOR",
    "ENDERECO_COMPARTILHADO",
    "CONTATO_COMPARTILHADO",
}

BUSINESS_RELATIONS = {
    "SOCIO_DE",
    "SOCIO_COTISTA",
    "CONTROLADOR_DIRETO",
    "CONTROLADOR_CONJUNTO_CANDIDATO",
    "INFLUENCIA_RELEVANTE",
    "SOCIO_MINORITARIO",
    "PARTICIPACAO_INDIRETA",
}

FINANCIAL_RELATIONS = {
    "TRANSFERIU_PARA",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA",
    "DEPENDENCIA_FINANCEIRA_CONFIRMADA",
}

OTHER_RELATIONS = {
    "EMPREGADO_DE",
    "TIO_TIA_DE",
    "ESPOLIO_DE",
}

RELATION_BY_SCOPE = {
    "family": FAMILY_RELATIONS | WEAK_FAMILY_RELATIONS,
    "business": BUSINESS_RELATIONS,
    "financial": FINANCIAL_RELATIONS,
    "other": OTHER_RELATIONS,
}
RELATION_BY_SCOPE["all"] = set().union(*RELATION_BY_SCOPE.values())


RELATION_LABEL = {
    "FILHO_DE": "pai/mãe",
    "PAI_DE": "pai/mãe",
    "MAE_DE": "pai/mãe",
    "IRMAO_DE": "irmão(a)",
    "CONJUGE_DE": "cônjuge",
    "CONJUGE_NOME_CANDIDATO": "cônjuge (candidato)",
    "SOCIO_DE": "sócio",
    "SOCIO_COTISTA": "sócio",
    "CONTROLADOR_DIRETO": "controlador",
    "CONTROLADOR_CONJUNTO_CANDIDATO": "controle conjunto",
    "INFLUENCIA_RELEVANTE": "participação relevante",
    "SOCIO_MINORITARIO": "sócio",
    "PARTICIPACAO_INDIRETA": "participação indireta",
    "ENDERECO_COMPARTILHADO": "endereço em comum",
    "CONTATO_COMPARTILHADO": "contato compartilhado",
    "EMPREGADO_DE": "vínculo de emprego",
    "TIO_TIA_DE": "tio/tia",
    "ESPOLIO_DE": "espólio",
    "PARENTESCO_AMBIGUO": "parentesco ambíguo",
    "POSSIVEL_MESMO_GENITOR": "possível mesmo genitor",
    "TRANSFERIU_PARA": "fluxo de recursos",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA": "dependência financeira sugerida",
    "DEPENDENCIA_FINANCEIRA_CONFIRMADA": "dependência financeira confirmada",
}


def relation_role(rel_type: str, source_is_current: bool, direction_delta: int) -> str:
    if rel_type == "FILHO_DE":
        if direction_delta < 0:
            return "filho(a)"
        if direction_delta > 0:
            return "pai/mãe"
        return "filiação"

    if rel_type in {"PAI_DE", "MAE_DE"}:
        if direction_delta > 0:
            return "pai/mãe"
        if direction_delta < 0:
            return "filho(a)"
        return "filiação"

    if rel_type in {"CONJUGE_DE", "CONJUGE_NOME_CANDIDATO"}:
        return "cônjuge"

    if rel_type == "IRMAO_DE":
        return "irmão(a)"

    if rel_type in {"SOCIO_DE", "SOCIO_COTISTA"}:
        return "sócio"

    if rel_type in {"CONTROLADOR_DIRETO", "CONTROLADOR_CONJUNTO_CANDIDATO", "INFLUENCIA_RELEVANTE", "SOCIO_MINORITARIO", "PARTICIPACAO_INDIRETA"}:
        if direction_delta > 0:
            return "sociedade na origem"
        if direction_delta < 0:
            return "sociedade no destino"
        return "sociedade"

    if rel_type == "TRANSFERIU_PARA":
        return "fluxo financeiro"

    if rel_type in {"ENDERECO_COMPARTILHADO", "CONTATO_COMPARTILHADO"}:
        return "evidência compartilhada"

    return RELATION_LABEL.get(rel_type, rel_type.lower().replace("_", " "))


def relation_role_for_endpoint(rel_type: str, endpoint_is_source: bool, direction_delta: int) -> str:
    if endpoint_is_source:
        return relation_role(rel_type, True, direction_delta)

    return relation_role(rel_type, False, -direction_delta)


MAX_NODE_LIMIT = 2500
MAX_SEARCH_LIMIT = 60
NAME_NORMALIZED_BATCH = 1200


def _normalize_for_search(value: str) -> str:
    lowered = (value or "").strip().lower()
    if not lowered:
        return ""
    without_accents = "".join(
        ch for ch in unicodedata.normalize("NFKD", lowered) if unicodedata.category(ch) != "Mn"
    )
    return " ".join(without_accents.split())


class HealthResponse(BaseModel):
    status: str
    db_status: str


class MetadataResponse(BaseModel):
    total_entidades: int
    total_vinculos: int
    total_grupos: int
    total_revisao: int
    total_pessoas: int
    total_empresas: int
    tipo_entidade: dict[str, int]


class SearchItem(BaseModel):
    entidade_id: str
    nome: str
    cpf_cnpj: str
    tipo_entidade: str
    status_entidade: str
    data_nascimento: str
    documento_valido: str
    score: float
    motivo: str


class SearchResponse(BaseModel):
    query: str
    total: int
    limit: int
    offset: int
    items: list[SearchItem]


class RelationItem(BaseModel):
    id: str
    source: str
    target: str
    tipo_vinculo: str
    tipo_nome: str
    relation_depth_delta: int
    role_from_source: str
    role_from_target: str
    confianca_vinculo: float
    requer_revisao: bool


class EntityNode(BaseModel):
    id: str
    nome: str
    cpf_cnpj: str
    tipo_entidade: str
    status_entidade: str
    data_nascimento: str
    data_obito: str
    documento_valido: str
    alerta: str
    depth: int
    total_vizinhos: int
    hidden_vizinhos: int
    roles: list[str]


class TreeResponse(BaseModel):
    root_id: str
    nodes: list[EntityNode]
    relations: list[RelationItem]
    has_more_up: bool
    has_more_down: bool
    has_more_same: bool = False
    max_depth: int
    next_up_offset: int = 0
    next_down_offset: int = 0
    next_same_offset: int = 0
    max_per_node: int
    scope: str
    include_weak: bool
    include_type: str
    summary: dict[str, int | float]


class GroupItem(BaseModel):
    grupo_id: str
    tipo_grupo: str
    nome_grupo: str
    status_grupo: str
    grupo_regulatorio: str
    requer_revisao: bool
    confianca_grupo: str


class EntityDetailResponse(BaseModel):
    entidade_id: str
    tipo_entidade: str
    nome_canonico: str
    nome_original: str
    cpf_cnpj: str
    status_entidade: str
    documento_valido: str
    data_nascimento: str
    data_obito: str
    fonte_principal: str
    data_atualizacao: str
    alertas: str
    graus_conexao: int
    total_vinculos: int
    total_grupos: int
    conexoes_por_tipo: dict[str, int]
    grupos: list[GroupItem]


class Neighbor:
    relation_id: str
    source: str
    target: str
    tipo_vinculo: str
    neighbor_id: str
    current_id: str
    source_is_current: bool
    direction_delta: int
    confianca: float
    requer_revisao: bool
    data_observacao: str
    total_candidates: int = 0


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Banco não encontrado: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_indexes(conn: sqlite3.Connection) -> None:
    ddl = [
        "CREATE INDEX IF NOT EXISTS idx_entidades_id ON entidades (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_tipo ON entidades (tipo_entidade)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_can ON entidades (nome_canonico)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_ori ON entidades (nome_original)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_can_norm ON entidades (nome_canonico_normalizado)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_ori_norm ON entidades (nome_original_normalizado)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_can_lower ON entidades (lower(nome_canonico))",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_ori_lower ON entidades (lower(nome_original))",
        "CREATE INDEX IF NOT EXISTS idx_entidades_cpf ON entidades (cpf_cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_status ON entidades (status_entidade)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_updated ON entidades (data_atualizacao)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_origem_tipo ON vinculos (entidade_origem, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_destino_tipo ON vinculos (entidade_destino, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_origem_tipo_destino ON vinculos (entidade_origem, tipo_vinculo, entidade_destino)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_destino_tipo_origem ON vinculos (entidade_destino, tipo_vinculo, entidade_origem)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_revisao ON vinculos (requer_revisao)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_tipos ON vinculos (tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_membro_ent ON membros_grupo (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_membro_grp ON membros_grupo (grupo_id)",
    ]
    for statement in ddl:
        conn.execute(statement)

    ensure_entity_name_columns(conn)


def ensure_entity_name_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(entidades)").fetchall()
    }

    changed = False
    if "nome_canonico_normalizado" not in columns:
        conn.execute("ALTER TABLE entidades ADD COLUMN nome_canonico_normalizado TEXT")
        changed = True

    if "nome_original_normalizado" not in columns:
        conn.execute("ALTER TABLE entidades ADD COLUMN nome_original_normalizado TEXT")
        changed = True

    if not changed:
        return

    rows = conn.execute(
        "SELECT entidade_id, nome_canonico, nome_original FROM entidades WHERE "
        "nome_canonico_normalizado IS NULL OR nome_original_normalizado IS NULL"
    ).fetchall()

    for start in range(0, len(rows), NAME_NORMALIZED_BATCH):
        batch = rows[start : start + NAME_NORMALIZED_BATCH]
        update = []
        for row in batch:
            update.append(
                (
                    _normalize_for_search(row["nome_canonico"] or ""),
                    _normalize_for_search(row["nome_original"] or ""),
                    row["entidade_id"],
                )
            )
        conn.executemany(
            "UPDATE entidades SET nome_canonico_normalizado = ?, nome_original_normalizado = ? WHERE entidade_id = ?",
            update,
        )
    conn.commit()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "sim", "y", "yes"}



def parse_scope(scope: str) -> list[str]:
    if not scope:
        return sorted(FAMILY_RELATIONS | WEAK_FAMILY_RELATIONS)

    requested: set[str] = set()
    for item in scope.split(","):
        value = item.strip().lower()
        if not value:
            continue
        if value in {"all", "*", "completo"}:
            return sorted(RELATION_BY_SCOPE["all"])

        if value in {"familia", "familiares", "family"}:
            requested |= RELATION_BY_SCOPE["family"]
            continue

        if value in RELATION_BY_SCOPE:
            requested |= RELATION_BY_SCOPE[value]

    if not requested:
        return sorted(FAMILY_RELATIONS | WEAK_FAMILY_RELATIONS)
    return sorted(requested)


def get_entity(conn: sqlite3.Connection, entidade_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (entidade_id,)).fetchone()


def fetch_entities(conn: sqlite3.Connection, entity_ids: set[str]) -> dict[str, sqlite3.Row]:
    if not entity_ids:
        return {}

    placeholder = ",".join("?" * len(entity_ids))
    rows = conn.execute(
        f"SELECT * FROM entidades WHERE entidade_id IN ({placeholder})",
        tuple(entity_ids),
    ).fetchall()
    return {row["entidade_id"]: row for row in rows}


def normalize_term_for_like(value: str) -> str:
    return value.replace("%", "\\%").replace("_", "\\_").strip().lower()


def direction_delta_set(direction: str) -> set[int]:
    if direction == "up":
        return {-1}
    if direction == "down":
        return {1}
    if direction == "both":
        return {-1, 1}
    if direction in {"all", "full", "other"}:
        return {-1, 0, 1}
    if direction == "same":
        return {0}
    return {-1, 0, 1}


def fetch_neighbors_batch(
    conn: sqlite3.Connection,
    frontier: set[str],
    rel_types: list[str],
    include_weak: bool,
    max_per_node: int,
    direction: str = "both",
) -> list[Neighbor]:
    if not frontier or not rel_types:
        return []

    ids = sorted(frontier)
    rel_placeholders = ",".join("?" * len(rel_types))
    id_placeholders = ",".join("?" * len(ids))
    allowed_dirs = sorted(direction_delta_set(direction))
    direction_placeholders = ",".join("?" * len(allowed_dirs))

    params: list[Any] = [
        *ids,
        *rel_types,
        *ids,
        *rel_types,
        *allowed_dirs,
        max_per_node,
    ]

    query = f"""
    WITH ranked AS (
      SELECT
        vinculo_id,
        entidade_origem AS source,
        entidade_destino AS target,
        entidade_origem AS current_id,
        entidade_destino AS neighbor_id,
        1 AS source_is_current,
        tipo_vinculo,
        CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
        COALESCE(requer_revisao, 'false') AS requer_revisao,
        COALESCE(data_observacao, '') AS data_observacao,
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN -1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 1
          ELSE 0
        END AS direction_delta
      FROM vinculos
      WHERE entidade_origem IN ({id_placeholders})
        AND tipo_vinculo IN ({rel_placeholders})

      UNION ALL

      SELECT
        vinculo_id,
        entidade_origem AS source,
        entidade_destino AS target,
        entidade_destino AS current_id,
        entidade_origem AS neighbor_id,
        0 AS source_is_current,
        tipo_vinculo,
        CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
        COALESCE(requer_revisao, 'false') AS requer_revisao,
        COALESCE(data_observacao, '') AS data_observacao,
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN 1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN -1
          ELSE 0
        END AS direction_delta
      FROM vinculos
      WHERE entidade_destino IN ({id_placeholders})
        AND tipo_vinculo IN ({rel_placeholders})
    )
    SELECT *
    FROM (
      SELECT
        ranked.*,
        ROW_NUMBER() OVER (
          PARTITION BY current_id, direction_delta
          ORDER BY CAST(COALESCE(confianca_vinculo, '0') AS REAL) DESC, vinculo_id ASC
        ) AS row_num
      FROM ranked
      WHERE direction_delta IN ({direction_placeholders})
        {"" if include_weak else "AND LOWER(COALESCE(requer_revisao, 'false')) NOT IN ('true', '1', 't', 'sim')"}
    ) x
    WHERE row_num <= ?
    ORDER BY current_id, direction_delta, row_num, vinculo_id
    """

    rows = conn.execute(query, params).fetchall()
    return [
        Neighbor(
            relation_id=row["vinculo_id"],
            source=row["source"],
            target=row["target"],
            tipo_vinculo=row["tipo_vinculo"],
            neighbor_id=row["neighbor_id"],
            current_id=row["current_id"],
            source_is_current=bool(int(row["source_is_current"])),
            direction_delta=safe_int(row["direction_delta"], 0),
            confianca=safe_float(row["confianca_vinculo"]),
            requer_revisao=safe_bool(row["requer_revisao"]),
            data_observacao=row["data_observacao"] or "",
        )
        for row in rows
    ]


def fetch_neighbors_paginated(
    conn: sqlite3.Connection,
    entity_id: str,
    rel_types: list[str],
    include_weak: bool,
    direction: str,
    max_per_node: int,
    offset: int = 0,
) -> tuple[list[Neighbor], int]:
    if not rel_types:
        return [], 0

    if direction == "all":
        raise HTTPException(status_code=400, detail="direction deve ser up, down, same ou both.")

    allowed_dirs = sorted(direction_delta_set(direction))
    if not allowed_dirs:
        allowed_dirs = [0]

    rel_placeholders = ",".join("?" * len(rel_types))
    direction_placeholders = ",".join("?" * len(allowed_dirs))
    all_conditions = []

    if not include_weak:
        all_conditions.append("LOWER(COALESCE(requer_revisao, 'false')) NOT IN ('true', '1', 't', 'sim')")

    filter_clause = ""
    if all_conditions:
        filter_clause = " AND " + " AND ".join(all_conditions)

    query = f"""
    WITH ordered AS (
      SELECT
        vinculo_id,
        entidade_origem AS source,
        entidade_destino AS target,
        entidade_origem AS current_id,
        entidade_destino AS neighbor_id,
        1 AS source_is_current,
        tipo_vinculo,
        CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
        COALESCE(requer_revisao, 'false') AS requer_revisao,
        COALESCE(data_observacao, '') AS data_observacao,
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN -1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 1
          ELSE 0
        END AS direction_delta
      FROM vinculos
      WHERE entidade_origem = ?
        AND tipo_vinculo IN ({rel_placeholders})

      UNION ALL

      SELECT
        vinculo_id,
        entidade_origem AS source,
        entidade_destino AS target,
        entidade_destino AS current_id,
        entidade_origem AS neighbor_id,
        0 AS source_is_current,
        tipo_vinculo,
        CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
        COALESCE(requer_revisao, 'false') AS requer_revisao,
        COALESCE(data_observacao, '') AS data_observacao,
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN 1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN -1
          ELSE 0
        END AS direction_delta
      FROM vinculos
      WHERE entidade_destino = ?
        AND tipo_vinculo IN ({rel_placeholders})
    )
    SELECT *
    FROM (
      SELECT
        *,
        ROW_NUMBER() OVER (
          PARTITION BY direction_delta
          ORDER BY CAST(confianca_vinculo AS REAL) DESC, vinculo_id ASC
        ) AS row_num,
        COUNT(*) OVER (PARTITION BY direction_delta) AS total_count
      FROM ordered
      WHERE direction_delta IN ({direction_placeholders})
        {filter_clause}
    ) x
    WHERE current_id = ?
      AND row_num > ?
      AND row_num <= ?
    ORDER BY direction_delta ASC, row_num ASC
    """

    limit = max_per_node
    end = offset + limit

    params = [entity_id, *rel_types, entity_id, *rel_types, *allowed_dirs, entity_id, offset, end]
    rows = conn.execute(query, params).fetchall()

    if not rows:
        return [], 0

    total = safe_int(rows[0]["total_count"])
    return [
        Neighbor(
            relation_id=row["vinculo_id"],
            source=row["source"],
            target=row["target"],
            tipo_vinculo=row["tipo_vinculo"],
            neighbor_id=row["neighbor_id"],
            current_id=row["current_id"],
            source_is_current=bool(int(row["source_is_current"])),
            direction_delta=safe_int(row["direction_delta"], 0),
            confianca=safe_float(row["confianca_vinculo"]),
            requer_revisao=safe_bool(row["requer_revisao"]),
            data_observacao=row["data_observacao"] or "",
            total_candidates=total,
        )
        for row in rows
    ], total


def fetch_neighbors(
    conn: sqlite3.Connection,
    entidade_id: str,
    rel_types: list[str],
    include_weak: bool,
    max_per_node: int,
) -> list[Neighbor]:
    return fetch_neighbors_batch(
        conn=conn,
        frontier={entidade_id},
        rel_types=rel_types,
        include_weak=include_weak,
        max_per_node=max_per_node,
        direction="all",
    )


def count_neighbors(conn: sqlite3.Connection, entity_ids: set[str], rel_types: list[str], include_weak: bool) -> dict[str, int]:
    if not entity_ids or not rel_types:
        return {entity_id: 0 for entity_id in entity_ids}

    placeholder = ",".join("?" * len(entity_ids))
    rel_placeholder = ",".join("?" * len(rel_types))

    where_filters = [f"tipo_vinculo IN ({rel_placeholder})"]
    if not include_weak:
        where_filters.append("LOWER(COALESCE(requer_revisao, 'false')) NOT IN ('true', '1', 't', 'sim')")

    filters = " AND ".join(where_filters)

    query = f"""
    WITH all_counts AS (
      SELECT entidade_origem AS entidade_id
        FROM vinculos
       WHERE entidade_origem IN ({placeholder})
         AND {filters}
      UNION ALL
      SELECT entidade_destino AS entidade_id
        FROM vinculos
       WHERE entidade_destino IN ({placeholder})
         AND {filters}
    )
    SELECT entidade_id, COUNT(*) AS total
      FROM all_counts
     GROUP BY entidade_id
    """

    rows = conn.execute(query, [*entity_ids, *rel_types, *entity_ids, *rel_types]).fetchall()

    totals = {entity_id: 0 for entity_id in entity_ids}
    for row in rows:
        totals[row["entidade_id"]] = safe_int(row["total"])

    return totals


def _role_text_for_node(roles: set[str]) -> list[str]:
    return sorted(roles, key=lambda item: ("pai/mãe" != item, item))


def _role_for_node(node_id: str, relation: RelationItem) -> str:
    if node_id == relation.source:
        return relation.role_from_source
    if node_id == relation.target:
        return relation.role_from_target
    return "vínculo"


def build_entity_node(
    entity: sqlite3.Row,
    depth: int,
    totals: dict[str, int],
    max_per_node: int,
    roles: set[str] | None,
):
    total_neighbors = totals.get(entity["entidade_id"], 0)
    hidden = max(0, total_neighbors - max_per_node)
    return EntityNode(
        id=entity["entidade_id"],
        nome=entity["nome_canonico"] or entity["nome_original"] or entity["entidade_id"],
        cpf_cnpj=entity["cpf_cnpj"] or "",
        tipo_entidade=entity["tipo_entidade"] or "",
        status_entidade=entity["status_entidade"] or "",
        data_nascimento=entity["data_nascimento"] or "",
        data_obito=entity["data_obito"] or "",
        documento_valido=entity["documento_valido"] or "false",
        alerta=entity["alertas"] or "",
        depth=depth,
        total_vizinhos=total_neighbors,
        hidden_vizinhos=hidden,
        roles=sorted(roles) if roles else ["selecione para mais detalhes"],
    )


def build_context_payload(
    conn: sqlite3.Connection,
    root_id: str,
    relation_types: list[str],
    include_weak: bool,
    max_per_node: int,
    include_up: bool,
    include_down: bool,
    include_same: bool = False,
    up_offset: int = 0,
    down_offset: int = 0,
    same_offset: int = 0,
) -> TreeResponse:
    root = get_entity(conn, root_id)
    if not root:
        raise HTTPException(status_code=404, detail="Entidade não localizada")

    up_neighbors: list[Neighbor] = []
    down_neighbors: list[Neighbor] = []
    same_neighbors: list[Neighbor] = []

    if include_up:
        up_neighbors, up_total = fetch_neighbors_paginated(
            conn=conn,
            entity_id=root_id,
            rel_types=relation_types,
            include_weak=include_weak,
            direction="up",
            max_per_node=max_per_node,
            offset=up_offset,
        )
    else:
        up_total = 0

    if include_down:
        down_neighbors, down_total = fetch_neighbors_paginated(
            conn=conn,
            entity_id=root_id,
            rel_types=relation_types,
            include_weak=include_weak,
            direction="down",
            max_per_node=max_per_node,
            offset=down_offset,
        )
    else:
        down_total = 0

    if include_same:
        same_neighbors, same_total = fetch_neighbors_paginated(
            conn=conn,
            entity_id=root_id,
            rel_types=relation_types,
            include_weak=include_weak,
            direction="same",
            max_per_node=max_per_node,
            offset=same_offset,
        )
    else:
        same_total = 0

    current_neighbors = up_neighbors + down_neighbors + same_neighbors
    relation_items: list[RelationItem] = []
    relation_keys: set[tuple[str, str, str]] = set()

    for neighbor in current_neighbors:
        rel_key = (neighbor.relation_id, neighbor.source, neighbor.target)
        if rel_key in relation_keys:
            continue
        relation_keys.add(rel_key)
        relation_items.append(
            RelationItem(
                id=neighbor.relation_id,
                source=neighbor.source,
                target=neighbor.target,
                tipo_vinculo=neighbor.tipo_vinculo,
                tipo_nome=RELATION_LABEL.get(neighbor.tipo_vinculo, neighbor.tipo_vinculo.lower()),
                relation_depth_delta=neighbor.direction_delta,
                role_from_source=relation_role_for_endpoint(neighbor.tipo_vinculo, True, neighbor.direction_delta),
                role_from_target=relation_role_for_endpoint(neighbor.tipo_vinculo, False, neighbor.direction_delta),
                confianca_vinculo=neighbor.confianca,
                requer_revisao=neighbor.requer_revisao,
            )
        )

    node_ids = {root_id} | {n.neighbor_id for n in current_neighbors}
    node_rows = fetch_entities(conn, node_ids)
    if root_id not in node_rows:
        node_rows[root_id] = root

    totals = count_neighbors(conn, node_ids, relation_types, include_weak)
    node_roles: dict[str, set[str]] = defaultdict(set)

    for item in relation_items:
        node_roles[item.source].add(item.role_from_source)
        node_roles[item.target].add(item.role_from_target)

    if root_id not in node_roles:
        node_roles[root_id].add("selecionado(a)")

    node_payload: list[EntityNode] = []
    node_depth = {root_id: 0}

    for nid in node_ids:
        rel = node_rows.get(nid)
        if not rel:
            continue

        if nid == root_id:
            depth = 0
        else:
            related = [n for n in current_neighbors if n.neighbor_id == nid]
            if related:
                depth = node_depth[root_id] + related[0].direction_delta
            else:
                depth = node_depth[root_id]
            node_depth[nid] = depth

        node_payload.append(build_entity_node(rel, depth, totals, max_per_node, node_roles.get(nid, set())))

    return TreeResponse(
        root_id=root_id,
        nodes=node_payload,
        relations=relation_items,
        has_more_up=up_total > up_offset + max_per_node,
        has_more_down=down_total > down_offset + max_per_node,
        has_more_same=same_total > same_offset + max_per_node,
        max_depth=max(abs(node_depth[root_id]), *(abs(v) for v in node_depth.values()), 1),
        next_up_offset=up_offset + max_per_node if include_up else 0,
        next_down_offset=down_offset + max_per_node if include_down else 0,
        next_same_offset=same_offset + max_per_node if include_same else 0,
        max_per_node=max_per_node,
        scope=",".join(relation_types),
        include_weak=include_weak,
        include_type=("up+down" if include_up and include_down else "up" if include_up else "down" if include_down else "same"),
        summary={
            "total_nodos": len(node_payload),
            "total_relacoes": len(relation_items),
            "nivel_max": max(abs(depth) for depth in node_depth.values()) if node_depth else 0,
            "up_total": up_total,
            "down_total": down_total,
            "same_total": same_total,
        },
    )


def build_tree_payload(
    conn: sqlite3.Connection,
    root_id: str,
    max_depth_up: int,
    max_depth_down: int,
    max_per_node: int,
    relation_types: list[str],
    include_weak: bool,
    direction: str,
) -> TreeResponse:
    if max_depth_up < 0 or max_depth_down < 0:
        raise HTTPException(status_code=400, detail="max_depth_up e max_depth_down devem ser >= 0")
    if max_per_node <= 0:
        raise HTTPException(status_code=400, detail="max_per_node deve ser > 0")

    root = get_entity(conn, root_id)
    if not root:
        raise HTTPException(status_code=404, detail="Entidade não localizada")

    include_up = direction in {"all", "up", "both"}
    include_down = direction in {"all", "down", "both"}
    include_same = direction == "all"

    node_depth: dict[str, int] = {root_id: 0}
    node_roles: dict[str, set[str]] = defaultdict(set)
    relations: dict[tuple[str, str, str], RelationItem] = {}
    reached = 1
    has_more_up = False
    has_more_down = False

    up_depth = max_depth_up if include_up else 0
    down_depth = max_depth_down if include_down else 0

    def add_relation(neighbor: Neighbor, depth_delta: int) -> None:
        role = relation_role(neighbor.tipo_vinculo, neighbor.source_is_current, depth_delta)
        node_roles[neighbor.neighbor_id].add(role)

        rel_key = (neighbor.relation_id, neighbor.source, neighbor.target)
        if rel_key not in relations:
            relations[rel_key] = RelationItem(
                id=neighbor.relation_id,
                source=neighbor.source,
                target=neighbor.target,
                tipo_vinculo=neighbor.tipo_vinculo,
                tipo_nome=RELATION_LABEL.get(neighbor.tipo_vinculo, neighbor.tipo_vinculo.lower()),
                relation_depth_delta=depth_delta,
                role_from_source=relation_role_for_endpoint(neighbor.tipo_vinculo, True, depth_delta),
                role_from_target=relation_role_for_endpoint(neighbor.tipo_vinculo, False, depth_delta),
                confianca_vinculo=neighbor.confianca,
                requer_revisao=neighbor.requer_revisao,
            )

    def should_take_for_direction(current_depth: int, new_depth: int, direction_hint: str) -> bool:
        if direction_hint == "up":
            return new_depth < current_depth <= 0
        if direction_hint == "down":
            return new_depth > current_depth >= 0
        return new_depth == current_depth

    def expand_layer(frontier: set[str], direction_hint: str) -> set[str]:
        if not frontier:
            return set()

        next_frontier: set[str] = set()
        for neighbor in fetch_neighbors_batch(
            conn=conn,
            frontier=frontier,
            rel_types=relation_types,
            include_weak=include_weak,
            max_per_node=max_per_node,
            direction=direction_hint,
        ):
            current_depth = node_depth.get(neighbor.current_id)
            if current_depth is None:
                continue

            add_relation(neighbor, neighbor.direction_delta)
            next_depth = current_depth + neighbor.direction_delta

            if not should_take_for_direction(current_depth, next_depth, direction_hint):
                continue

            existing = node_depth.get(neighbor.neighbor_id)
            if existing is None and reached < MAX_NODE_LIMIT:
                node_depth[neighbor.neighbor_id] = next_depth
                reached += 1
                next_frontier.add(neighbor.neighbor_id)
                continue

            if existing is not None and abs(next_depth) < abs(existing):
                node_depth[neighbor.neighbor_id] = next_depth
                next_frontier.add(neighbor.neighbor_id)

        return next_frontier

    def has_more_neighbors(frontier: set[str], direction_hint: str) -> bool:
        if not frontier or reached >= MAX_NODE_LIMIT:
            return False

        for neighbor in fetch_neighbors_batch(
            conn=conn,
            frontier=frontier,
            rel_types=relation_types,
            include_weak=include_weak,
            max_per_node=max_per_node,
            direction=direction_hint,
        ):
            current_depth = node_depth.get(neighbor.current_id)
            if current_depth is None:
                continue

            next_depth = current_depth + neighbor.direction_delta
            if not should_take_for_direction(current_depth, next_depth, direction_hint):
                continue

            if neighbor.neighbor_id not in node_depth:
                return True

        return False

    if include_up:
        frontier_up = {root_id}
        for _ in range(1, up_depth + 1):
            frontier_up = expand_layer(frontier_up, "up")
            if not frontier_up:
                break
        has_more_up = bool(frontier_up) and has_more_neighbors(frontier_up, "up") and up_depth >= 1

    if include_down:
        frontier_down = {root_id}
        for _ in range(1, down_depth + 1):
            frontier_down = expand_layer(frontier_down, "down")
            if not frontier_down:
                break
        has_more_down = bool(frontier_down) and has_more_neighbors(frontier_down, "down") and down_depth >= 1

    if include_same:
        same_level_nodes = [node_id for node_id, depth in node_depth.items() if depth == 0]
        for current in same_level_nodes:
            if reached >= MAX_NODE_LIMIT:
                break
            for neighbor in fetch_neighbors_batch(
                conn=conn,
                frontier={current},
                rel_types=relation_types,
                include_weak=include_weak,
                max_per_node=max_per_node,
                direction="same",
            ):
                add_relation(neighbor, 0)
                if neighbor.neighbor_id not in node_depth and reached < MAX_NODE_LIMIT:
                    node_depth[neighbor.neighbor_id] = 0
                    reached += 1

    node_ids = set(node_depth.keys())
    node_rows = fetch_entities(conn, node_ids)
    totals = count_neighbors(conn, node_ids, relation_types, include_weak) if node_rows else {}

    nodes_payload: list[EntityNode] = []
    max_depth_reached = 0
    min_depth = 0

    for node_id, depth in node_depth.items():
        entity = node_rows.get(node_id)
        if not entity:
            continue

        total_neighbors = totals.get(node_id, 0)
        hidden = max(0, total_neighbors - max_per_node)
        nodes_payload.append(
            EntityNode(
                id=node_id,
                nome=entity["nome_canonico"] or entity["nome_original"] or node_id,
                cpf_cnpj=entity["cpf_cnpj"] or "",
                tipo_entidade=entity["tipo_entidade"] or "",
                status_entidade=entity["status_entidade"] or "",
                data_nascimento=entity["data_nascimento"] or "",
                data_obito=entity["data_obito"] or "",
                documento_valido=entity["documento_valido"] or "false",
                alerta=entity["alertas"] or "",
                depth=depth,
                total_vizinhos=total_neighbors,
                hidden_vizinhos=hidden,
                roles=_role_text_for_node(node_roles[node_id]) if node_roles[node_id] else ["selecionado" if node_id == root_id else "vínculo"],
            )
        )
        max_depth_reached = max(max_depth_reached, abs(depth))
        min_depth = min(min_depth, depth)

    nodes_payload.sort(key=lambda item: (item.depth, item.nome))
    max_up = abs(min_depth)
    max_down = max((n.depth for n in nodes_payload), default=0)

    return TreeResponse(
        root_id=root_id,
        nodes=nodes_payload,
        relations=list(relations.values()),
        has_more_up=has_more_up and include_up,
        has_more_down=has_more_down and include_down,
        max_depth=max(max_up, max_down),
        max_per_node=max_per_node,
        scope=",".join(relation_types),
        include_weak=include_weak,
        include_type=direction,
        summary={
            "total_nodos": len(nodes_payload),
            "total_relacoes": len(relations),
            "nivel_max": max_depth_reached,
        },
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", db_status="disponivel" if DB_PATH.exists() else "ausente")


@app.get("/api/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            total_entidades = safe_int(conn.execute("SELECT COUNT(*) AS total FROM entidades").fetchone()[0])
            total_vinculos = safe_int(conn.execute("SELECT COUNT(*) AS total FROM vinculos").fetchone()[0])
            total_grupos = safe_int(conn.execute("SELECT COUNT(*) AS total FROM grupos").fetchone()[0])
            total_revisao = safe_int(conn.execute("SELECT COUNT(*) AS total FROM fila_revisao").fetchone()[0])
            dist = conn.execute("SELECT tipo_entidade, COUNT(*) AS total FROM entidades GROUP BY tipo_entidade").fetchall()
            tipos = {row["tipo_entidade"]: safe_int(row["total"]) for row in dist}
    finally:
        conn.close()

    return MetadataResponse(
        total_entidades=total_entidades,
        total_vinculos=total_vinculos,
        total_grupos=total_grupos,
        total_revisao=total_revisao,
        total_pessoas=safe_int(tipos.get("PF", 0)) + safe_int(tipos.get("PF_EXTERNA", 0)),
        total_empresas=safe_int(tipos.get("PJ", 0)) + safe_int(tipos.get("PJ_EXTERNA", 0)),
        tipo_entidade=tipos,
    )


@app.get("/api/entities/search", response_model=SearchResponse)
def search_entities(
    q: str = "",
    limit: int = Query(default=12, ge=1, le=MAX_SEARCH_LIMIT),
    offset: int = Query(default=0, ge=0),
    tipo: str | None = None,
    include_external: bool = True,
    only_active: bool = False,
) -> SearchResponse:
    query_text = (q or "").strip()
    if len(query_text) < 2:
        return SearchResponse(query=q, total=0, limit=limit, offset=offset, items=[])

    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            normalized_raw = _normalize_for_search(query_text)
            raw_number = "".join(ch for ch in query_text if ch.isdigit())
            raw_like = normalize_term_for_like(query_text.strip().lower())
            raw_like_any = f"%{raw_like}%"
            raw_like_prefix = f"{raw_like}%"
            normalized_like = normalize_term_for_like(normalized_raw)
            normalized_like_any = f"%{normalized_like}%"
            normalized_like_prefix = f"{normalized_like}%"

            conditions: list[str] = ["1 = 1"]
            params: dict[str, Any] = {
                "limit": limit,
                "offset": offset,
                "q_exact_norm": normalized_raw,
                "q_exact_num": raw_number,
                "raw_like": raw_like_any,
                "raw_prefix": raw_like_prefix,
                "norm_like": normalized_like_any,
                "norm_prefix": normalized_like_prefix,
            }

            name_conditions = [
                "LOWER(COALESCE(entidade_id, '')) = :q_exact_num",
                "LOWER(COALESCE(cpf_cnpj, '')) = :q_exact_num",
                "LOWER(COALESCE(cpf_cnpj, '')) LIKE :raw_prefix ESCAPE '\\'",
            ]

            if raw_like:
                name_conditions.append("LOWER(COALESCE(nome_canonico, '')) LIKE :raw_like ESCAPE '\\'")
                name_conditions.append("LOWER(COALESCE(nome_original, '')) LIKE :raw_like ESCAPE '\\'")
                name_conditions.append("LOWER(COALESCE(nome_canonico_normalizado, '')) LIKE :norm_like ESCAPE '\\'")
                name_conditions.append("LOWER(COALESCE(nome_original_normalizado, '')) LIKE :norm_like ESCAPE '\\'")

                if len(normalized_like_prefix) >= 3:
                    name_conditions.append(
                        "LOWER(COALESCE(nome_canonico_normalizado, '')) LIKE :norm_prefix ESCAPE '\\'"
                    )
                    name_conditions.append(
                        "LOWER(COALESCE(nome_original_normalizado, '')) LIKE :norm_prefix ESCAPE '\\'"
                    )

            conditions.append("(" + " OR ".join(name_conditions) + ")")

            if tipo:
                conditions.append("tipo_entidade = :tipo")
                params["tipo"] = tipo

            if not include_external:
                conditions.append("tipo_entidade NOT LIKE '%EXTERNA%'")

            if only_active:
                conditions.append("status_entidade = 'ATIVO'")

            where_sql = " WHERE " + " AND ".join(conditions)

            order = (
                "CASE WHEN LOWER(COALESCE(entidade_id, '')) = :q_exact_num THEN 0 ELSE 1 END, "
                "CASE WHEN LOWER(COALESCE(cpf_cnpj, '')) = :q_exact_num THEN 0 ELSE 1 END, "
                "CASE WHEN (LOWER(COALESCE(nome_canonico_normalizado, '')) LIKE :norm_prefix ESCAPE '\\' OR "
                "LOWER(COALESCE(nome_original_normalizado, '')) LIKE :norm_prefix ESCAPE '\\' OR "
                "LOWER(COALESCE(nome_canonico, '')) LIKE :raw_prefix ESCAPE '\\' OR "
                "LOWER(COALESCE(nome_original, '')) LIKE :raw_prefix ESCAPE '\\') THEN 0 ELSE 1 END, "
                "nome_canonico ASC",
            )
            order = "".join(order)

            total = conn.execute(f"SELECT COUNT(*) AS total FROM entidades{where_sql}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM entidades{where_sql} ORDER BY {order} LIMIT :limit OFFSET :offset",
                params,
            ).fetchall()
    finally:
        conn.close()

    items = [
        SearchItem(
            entidade_id=row["entidade_id"],
            nome=row["nome_canonico"] or row["nome_original"] or row["entidade_id"],
            cpf_cnpj=row["cpf_cnpj"] or "",
            tipo_entidade=row["tipo_entidade"],
            status_entidade=row["status_entidade"],
            data_nascimento=row["data_nascimento"] or "",
            documento_valido=row["documento_valido"] or "false",
            score=95.0
            if str(row["entidade_id"]).lower() == str(raw_number).lower()
            else 90.0 if str(row["cpf_cnpj"]).strip() == str(raw_number).strip() else 75.0,
            motivo="CPF/CNPJ informado" if str(row["cpf_cnpj"]) and str(row["cpf_cnpj"]).strip() == str(raw_number).strip() else "Nome ou documento encontrado",
        )
        for row in rows
    ]

    return SearchResponse(query=q, total=safe_int(total), limit=limit, offset=offset, items=items)


@app.get("/api/entities/{entidade_id}", response_model=EntityDetailResponse)
def entity_detail(entidade_id: str) -> EntityDetailResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            entity = get_entity(conn, entidade_id)
            if not entity:
                raise HTTPException(status_code=404, detail="Entidade não encontrada")

            links_count = safe_int(
                conn.execute(
                    "SELECT COUNT(*) AS total FROM vinculos WHERE entidade_origem = ? OR entidade_destino = ?",
                    (entidade_id, entidade_id),
                ).fetchone()[0]
            )

            links_by_type = conn.execute(
                """
                SELECT tipo_vinculo, COUNT(*) AS total
                FROM vinculos
                WHERE entidade_origem = ? OR entidade_destino = ?
                GROUP BY tipo_vinculo
                """,
                (entidade_id, entidade_id),
            ).fetchall()

            groups = conn.execute(
                """
                SELECT g.grupo_id, g.tipo_grupo, g.nome_grupo, g.status_grupo,
                       g.grupo_regulatorio, g.requer_revisao, g.confianca_grupo
                FROM membros_grupo m
                INNER JOIN grupos g ON g.grupo_id = m.grupo_id
                WHERE m.entidade_id = ?
                ORDER BY g.nome_grupo
                """,
                (entidade_id,),
            ).fetchall()

            total_groups = safe_int(
                conn.execute(
                    "SELECT COUNT(DISTINCT grupo_id) AS total FROM membros_grupo WHERE entidade_id = ?",
                    (entidade_id,),
                ).fetchone()[0]
            )
    finally:
        conn.close()

    return EntityDetailResponse(
        entidade_id=entity["entidade_id"],
        tipo_entidade=entity["tipo_entidade"] or "",
        nome_canonico=entity["nome_canonico"] or "",
        nome_original=entity["nome_original"] or "",
        cpf_cnpj=entity["cpf_cnpj"] or "",
        status_entidade=entity["status_entidade"] or "",
        documento_valido=entity["documento_valido"] or "false",
        data_nascimento=entity["data_nascimento"] or "",
        data_obito=entity["data_obito"] or "",
        fonte_principal=entity["fonte_principal"] or "",
        data_atualizacao=entity["data_atualizacao"] or "",
        alertas=entity["alertas"] or "",
        graus_conexao=links_count,
        total_vinculos=links_count,
        total_grupos=total_groups,
        conexoes_por_tipo={row["tipo_vinculo"]: safe_int(row["total"]) for row in links_by_type},
        grupos=[
            GroupItem(
                grupo_id=row["grupo_id"],
                tipo_grupo=row["tipo_grupo"],
                nome_grupo=row["nome_grupo"],
                status_grupo=row["status_grupo"],
                grupo_regulatorio=row["grupo_regulatorio"],
                requer_revisao=safe_bool(row["requer_revisao"]),
                confianca_grupo=row["confianca_grupo"] or "",
            )
            for row in groups
        ],
    )


@app.get("/api/tree/context/{entidade_id}", response_model=TreeResponse)
def tree_context(
    entidade_id: str,
    include_up: bool = Query(default=True),
    include_down: bool = Query(default=True),
    include_same: bool = Query(default=False),
    relation_scope: str = "family",
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_weak: bool = False,
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            return build_context_payload(
                conn=conn,
                root_id=entidade_id,
                relation_types=parse_scope(relation_scope),
                include_weak=include_weak,
                max_per_node=max_per_node,
                include_up=include_up,
                include_down=include_down,
                include_same=include_same,
                up_offset=up_offset,
                down_offset=down_offset,
                same_offset=same_offset,
            )
    finally:
        conn.close()


@app.get("/api/tree/expand/{entidade_id}", response_model=TreeResponse)
def tree_expand(
    entidade_id: str,
    direction: str = Query(default="both", description="up | down | same | both | all"),
    relation_scope: str = "family,business",
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_weak: bool = False,
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    normalized_direction = (direction or "both").lower()
    if normalized_direction not in {"up", "down", "same", "both", "all"}:
        raise HTTPException(status_code=400, detail="direction deve ser up, down, same, both ou all")

    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            return build_context_payload(
                conn=conn,
                root_id=entidade_id,
                relation_types=parse_scope(relation_scope),
                include_weak=include_weak,
                max_per_node=max_per_node,
                include_up=normalized_direction in {"up", "both", "all"},
                include_down=normalized_direction in {"down", "both", "all"},
                include_same=normalized_direction in {"same", "all"},
                up_offset=up_offset,
                down_offset=down_offset,
                same_offset=same_offset,
            )
    finally:
        conn.close()


@app.get("/api/tree/family/{entidade_id}", response_model=TreeResponse)
def tree_family_view(
    entidade_id: str,
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_weak: bool = False,
    include_business: bool = False,
    max_depth_up: int = Query(default=1, ge=0, le=1),
    max_depth_down: int = Query(default=1, ge=0, le=1),
) -> TreeResponse:
    # endpoint legado mantido para compatibilidade; agora atende a regra de carga sob demanda
    return tree_context(
        entidade_id=entidade_id,
        include_up=max_depth_up > 0,
        include_down=max_depth_down > 0,
        include_same=False,
        relation_scope="family,business" if include_business else "family",
        max_per_node=max_per_node,
        include_weak=include_weak,
        up_offset=0,
        down_offset=0,
        same_offset=0,
    )


@app.get("/api/tree/seed/{entidade_id}", response_model=TreeResponse)
def tree_seed(
    entidade_id: str,
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_weak: bool = False,
    include_business: bool = False,
):
    # compatibilidade: uma leitura inicial curta para bootstrap da visualização
    return tree_context(
        entidade_id=entidade_id,
        include_up=True,
        include_down=True,
        include_same=False,
        relation_scope="family,business" if include_business else "family",
        max_per_node=max_per_node,
        include_weak=include_weak,
        up_offset=0,
        down_offset=0,
        same_offset=0,
    )


@app.get("/api/tree/entity/{entidade_id}", response_model=TreeResponse)
def tree_from_entity(
    entidade_id: str,
    max_depth_up: int = Query(default=1, ge=0, le=1),
    max_depth_down: int = Query(default=1, ge=0, le=1),
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_weak: bool = False,
    relation_scope: str = "family,business",
) -> TreeResponse:
    # compatibilidade com contratos antigos; limites de profundidade acima de 1 foram migrados para expansão sob demanda
    return tree_context(
        entidade_id=entidade_id,
        include_up=max_depth_up > 0,
        include_down=max_depth_down > 0,
        include_same=False,
        relation_scope=relation_scope,
        max_per_node=max_per_node,
        include_weak=include_weak,
        up_offset=0,
        down_offset=0,
        same_offset=0,
    )


@app.get("/api/tree/branch/{entidade_id}", response_model=TreeResponse)
def tree_branch(
    entidade_id: str,
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_weak: bool = False,
    direction: str = "all",
    relation_scope: str = "family,business",
) -> TreeResponse:
    # endpoint legado com novo comportamento incremental por direção
    normalized_direction = (direction or "all").lower()
    if normalized_direction not in {"all", "up", "down", "both", "same"}:
        raise HTTPException(status_code=400, detail="direction deve ser all, up, down, both ou same")

    return tree_expand(
        entidade_id=entidade_id,
        direction=normalized_direction,
        relation_scope=relation_scope,
        max_per_node=max_per_node,
        include_weak=include_weak,
        up_offset=0,
        down_offset=0,
        same_offset=0,
    )


@app.exception_handler(HTTPException)
def http_exception_handler(_: Any, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
