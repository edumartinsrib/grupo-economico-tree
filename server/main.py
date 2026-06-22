from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import re
import sqlite3
import unicodedata

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "resultados" / "grafo_resultado.sqlite"

app = FastAPI(
    title="Grupo Econômico Tree API",
    version="6.0.0",
    description="API sob demanda para consulta de vínculos com pessoas e empresas.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Conjunto de vínculos usados na interface
FAMILY_RELATIONS = {
    "FILHO_DE",
    "PAI_DE",
    "MAE_DE",
    "IRMAO_DE",
    "CONJUGE_DE",
    "CONJUGE_NOME_CANDIDATO",
    "PARENTESCO_AMBIGUO",
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
    "ENDERECO_COMPARTILHADO",
    "CONTATO_COMPARTILHADO",
}

REVIEW_ONLY = {
    "PARENTESCO_AMBIGUO",
    "POSSIVEL_MESMO_GENITOR",
}

RELATION_BY_SCOPE = {
    "family": FAMILY_RELATIONS,
    "business": BUSINESS_RELATIONS,
    "financial": FINANCIAL_RELATIONS,
    "other": OTHER_RELATIONS,
}
RELATION_BY_SCOPE["all"] = {
    *FAMILY_RELATIONS,
    *BUSINESS_RELATIONS,
    *FINANCIAL_RELATIONS,
    *OTHER_RELATIONS,
}

RELATION_LABEL = {
    "FILHO_DE": "Pai/Mãe",
    "PAI_DE": "Pai/Mãe",
    "MAE_DE": "Pai/Mãe",
    "IRMAO_DE": "Irmão(a)",
    "CONJUGE_DE": "Cônjuge",
    "CONJUGE_NOME_CANDIDATO": "Cônjuge (candidato)",
    "SOCIO_DE": "Sócio(a)",
    "SOCIO_COTISTA": "Sócio(a)",
    "CONTROLADOR_DIRETO": "Controlador(a)",
    "CONTROLADOR_CONJUNTO_CANDIDATO": "Controle conjunto",
    "INFLUENCIA_RELEVANTE": "Participação societária relevante",
    "SOCIO_MINORITARIO": "Sócio(a)",
    "PARTICIPACAO_INDIRETA": "Participação societária indireta",
    "ENDERECO_COMPARTILHADO": "Endereço compartilhado",
    "CONTATO_COMPARTILHADO": "Contato compartilhado",
    "EMPREGADO_DE": "Relação de emprego",
    "TIO_TIA_DE": "Tio(a)",
    "ESPOLIO_DE": "Espólio",
    "TRANSFERIU_PARA": "Fluxo financeiro",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA": "Dependência financeira sugerida",
    "DEPENDENCIA_FINANCEIRA_CONFIRMADA": "Dependência financeira confirmada",
    "PARENTESCO_AMBIGUO": "Parentesco ambíguo",
    "POSSIVEL_MESMO_GENITOR": "Possível mesmo genitor",
}

MAX_NODE_LIMIT = 1500
MAX_SEARCH_LIMIT = 120
MAX_RELATIONS_PER_NODE = 40
DEFAULT_TREE_PAGE_SIZE = 8


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
    next_up_offset: int
    next_down_offset: int
    next_same_offset: int
    max_depth: int
    max_per_node: int
    scope: str
    include_weak: bool
    include_type: str
    summary: dict[str, int | str]


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


def normalize_for_search(value: str) -> str:
    if not value:
        return ""
    lowered = value.strip().lower()
    plain = "".join(
        ch for ch in unicodedata.normalize("NFKD", lowered) if unicodedata.category(ch) != "Mn"
    )
    return " ".join(plain.split())


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "sim", "yes", "y"}


def parse_scope(scope: str) -> list[str]:
    if not scope:
        return sorted(FAMILY_RELATIONS)

    result: set[str] = set()
    for token in scope.split(","):
        cleaned = token.strip().lower()
        if not cleaned:
            continue
        if cleaned in {"all", "*", "completo"}:
            return sorted(RELATION_BY_SCOPE["all"])
        if cleaned in RELATION_BY_SCOPE:
            result |= set(RELATION_BY_SCOPE[cleaned])
    if not result:
        return sorted(FAMILY_RELATIONS)
    return sorted(result)


def role_from_type(relation_type: str, direction_delta: int) -> str:
    if relation_type == "FILHO_DE":
        return "filho(a)" if direction_delta < 0 else "pai/mãe" if direction_delta > 0 else "filiação"

    if relation_type in {"PAI_DE", "MAE_DE"}:
        return "pai/mãe" if direction_delta > 0 else "filho(a)" if direction_delta < 0 else "filiação"

    if relation_type == "CONJUGE_DE":
        return "cônjuge"

    if relation_type == "CONJUGE_NOME_CANDIDATO":
        return "cônjuge (candidato)"

    if relation_type == "IRMAO_DE":
        return "irmão(a)"

    if relation_type in {"SOCIO_DE", "SOCIO_COTISTA"}:
        return "sócio(a)"

    if relation_type == "CONTROLADOR_DIRETO":
        return "controlador(a)"

    if relation_type == "CONTROLADOR_CONJUNTO_CANDIDATO":
        return "controle conjunto"

    if relation_type == "INFLUENCIA_RELEVANTE":
        return "sócio(a) com participação relevante"

    if relation_type == "SOCIO_MINORITARIO":
        return "sócio(a) minoritário(a)"

    if relation_type == "PARTICIPACAO_INDIRETA":
        return "sócio(a) indireto(a)"

    if relation_type == "TIO_TIA_DE":
        return "tio(a)"

    if relation_type == "PARENTESCO_AMBIGUO":
        return "parente (possível)"

    if relation_type == "POSSIVEL_MESMO_GENITOR":
        return "possível mesmo genitor"

    if relation_type in {"DEPENDENCIA_FINANCEIRA_CANDIDATA", "DEPENDENCIA_FINANCEIRA_CONFIRMADA"}:
        return "dependência financeira"

    if relation_type == "TRANSFERIU_PARA":
        return "fluxo financeiro"

    if relation_type in {"ENDERECO_COMPARTILHADO", "CONTATO_COMPARTILHADO"}:
        return "evidência compartilhada"

    return RELATION_LABEL.get(relation_type, relation_type.lower().replace("_", " "))


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
        "CREATE INDEX IF NOT EXISTS idx_entidades_cpf ON entidades (cpf_cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_updated ON entidades (data_atualizacao)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_canonico_normalizado ON entidades (nome_canonico_normalizado)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_original_normalizado ON entidades (nome_original_normalizado)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_origem ON vinculos (entidade_origem)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_destino ON vinculos (entidade_destino)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_tipo_origem ON vinculos (tipo_vinculo, entidade_origem)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_tipo_destino ON vinculos (tipo_vinculo, entidade_destino)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_revisao ON vinculos (requer_revisao)",
        "CREATE INDEX IF NOT EXISTS idx_membro_entidade ON membros_grupo (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_membro_grupo ON membros_grupo (grupo_id)",
    ]

    for statement in ddl:
        conn.execute(statement)

    _ensure_normalized_columns(conn)


def _ensure_normalized_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(entidades)").fetchall()}

    altered = False
    if "nome_canonico_normalizado" not in columns:
        conn.execute("ALTER TABLE entidades ADD COLUMN nome_canonico_normalizado TEXT")
        altered = True
    if "nome_original_normalizado" not in columns:
        conn.execute("ALTER TABLE entidades ADD COLUMN nome_original_normalizado TEXT")
        altered = True

    if altered:
        rows = conn.execute(
            "SELECT entidade_id, nome_canonico, nome_original FROM entidades WHERE nome_canonico_normalizado IS NULL OR nome_original_normalizado IS NULL"
        ).fetchall()

        for idx in range(0, len(rows), 500):
            batch = rows[idx : idx + 500]
            prepared = [
                (
                    normalize_for_search(row["nome_canonico"] or row["entidade_id"]),
                    normalize_for_search(row["nome_original"] or row["entidade_id"]),
                    row["entidade_id"],
                )
                for row in batch
            ]
            conn.executemany(
                "UPDATE entidades SET nome_canonico_normalizado = ?, nome_original_normalizado = ? WHERE entidade_id = ?",
                prepared,
            )
        conn.commit()


def _build_entity_label(entity: sqlite3.Row) -> str:
    return (
        (entity["nome_canonico"] or "").strip()
        or (entity["nome_original"] or "").strip()
        or entity["entidade_id"]
    )


def _safe_like_pattern(raw: str) -> str:
    return raw.replace("%", "\\%").replace("_", "\\_").strip().lower()


def _split_placeholders(count: int) -> str:
    return ",".join("?" * count) if count else "''"


def _normalize_raw_term(raw: str) -> str:
    return normalize_for_search(raw)


def _is_numeric_string(raw: str) -> bool:
    return bool(raw and raw.isdigit())


def _fetch_entity_rows(conn: sqlite3.Connection, entity_ids: set[str]) -> dict[str, sqlite3.Row]:
    if not entity_ids:
        return {}
    placeholders = _split_placeholders(len(entity_ids))
    rows = conn.execute(
        f"SELECT * FROM entidades WHERE entidade_id IN ({placeholders})", tuple(entity_ids)
    ).fetchall()
    return {row["entidade_id"]: row for row in rows}


def _include_weak_clause(include_weak: bool) -> str:
    if include_weak:
        return ""
    return "AND LOWER(COALESCE(requer_revisao, 'false')) NOT IN ('true', '1', 't', 'sim')"


def _neighbor_query_sql(
    relation_types: list[str],
    include_weak: bool,
    allowed_directions: set[int],
) -> str:
    relation_types_clause = _split_placeholders(len(relation_types))
    direction_expr = (
        "direction_delta IN (" + ",".join(str(v) for v in sorted(allowed_directions)) + ")"
        if allowed_directions
        else "1=1"
    )
    weak_clause = _include_weak_clause(include_weak)

    return f"""
    WITH directed AS (
      SELECT
        vinculo_id,
        entidade_origem AS source,
        entidade_destino AS target,
        entidade_origem AS current_id,
        entidade_destino AS neighbor_id,
        tipo_vinculo,
        CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
        COALESCE(requer_revisao, 'false') AS requer_revisao,
        COALESCE(data_observacao, '') AS data_observacao,
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN -1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 1
          WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 0
          ELSE 0
        END AS direction_delta
      FROM vinculos
      WHERE entidade_origem = ?
        AND tipo_vinculo IN ({relation_types_clause})

      UNION ALL

      SELECT
        vinculo_id,
        entidade_origem AS source,
        entidade_destino AS target,
        entidade_destino AS current_id,
        entidade_origem AS neighbor_id,
        tipo_vinculo,
        CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
        COALESCE(requer_revisao, 'false') AS requer_revisao,
        COALESCE(data_observacao, '') AS data_observacao,
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN 1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN -1
          WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 0
          ELSE 0
        END AS direction_delta
      FROM vinculos
      WHERE entidade_destino = ?
        AND tipo_vinculo IN ({relation_types_clause})
    )
    SELECT *
    FROM (
      SELECT
        vinculo_id,
        source,
        target,
        tipo_vinculo,
        confianca_vinculo,
        requer_revisao,
        data_observacao,
        direction_delta,
        neighbor_id,
        current_id,
        ROW_NUMBER() OVER (
          PARTITION BY current_id, direction_delta
          ORDER BY CAST(COALESCE(confianca_vinculo, '0') AS REAL) DESC, vinculo_id ASC
        ) AS row_num
      FROM directed
      WHERE {direction_expr}
        {weak_clause}
    )
    ORDER BY current_id, direction_delta, row_num
    """


def fetch_neighbors_paginated(
    conn: sqlite3.Connection,
    entity_id: str,
    relation_types: list[str],
    include_weak: bool,
    direction: str,
    max_per_node: int,
    offset: int,
) -> list[sqlite3.Row]:
    if not relation_types:
        return []

    if direction == "up":
        allowed = {-1}
    elif direction == "down":
        allowed = {1}
    elif direction == "same":
        allowed = {0}
    else:
        allowed = {-1, 0, 1}

    base_sql = _neighbor_query_sql(
        relation_types=relation_types,
        include_weak=include_weak,
        allowed_directions=allowed,
    )

    limit_clause = f" LIMIT {max_per_node} OFFSET {offset}" if max_per_node > 0 else ""
    sql = base_sql + limit_clause
    params = [entity_id, *relation_types, entity_id, *relation_types]
    rows = conn.execute(sql, params).fetchall()

    return rows


def count_neighbors(
    conn: sqlite3.Connection,
    entity_id: str,
    relation_types: list[str],
    include_weak: bool,
    allowed_directions: set[int] | None = None,
) -> dict[int, int]:
    if not relation_types:
        return {-1: 0, 0: 0, 1: 0}

    relation_types_clause = _split_placeholders(len(relation_types))
    weak_clause = _include_weak_clause(include_weak)
    direction_filter = ""
    if allowed_directions:
        direction_filter = "AND direction_delta IN (" + ",".join(str(v) for v in sorted(allowed_directions)) + ")"

    sql = f"""
    WITH directed AS (
      SELECT
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN -1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 1
          WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 0
          ELSE 0
        END AS direction_delta,
        CAST(COALESCE(requer_revisao, 'false') AS TEXT) AS requer_revisao
      FROM vinculos
      WHERE entidade_origem = ?
        AND tipo_vinculo IN ({relation_types_clause})
      UNION ALL
      SELECT
        CASE
          WHEN tipo_vinculo = 'FILHO_DE' THEN 1
          WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN -1
          WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 0
          ELSE 0
        END AS direction_delta,
        CAST(COALESCE(requer_revisao, 'false') AS TEXT) AS requer_revisao
      FROM vinculos
      WHERE entidade_destino = ?
        AND tipo_vinculo IN ({relation_types_clause})
    )
    SELECT direction_delta, COUNT(*) AS total
    FROM directed
    WHERE ({weak_clause})
    {direction_filter}
    GROUP BY direction_delta
    """

    rows = conn.execute(sql, [entity_id, *relation_types, entity_id, *relation_types]).fetchall()
    result = {-1: 0, 0: 0, 1: 0}
    for row in rows:
        result[_safe_int(row["direction_delta"])] = _safe_int(row["total"])
    return result


def _prepare_tree_payload(
    conn: sqlite3.Connection,
    root_id: str,
    relation_types: list[str],
    include_weak: bool,
    max_per_node: int,
    up_offset: int = 0,
    down_offset: int = 0,
    same_offset: int = 0,
    include_up: bool = True,
    include_down: bool = True,
    include_same: bool = False,
    anchor_label: str = "root",
) -> TreeResponse:
    root = conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (root_id,)).fetchone()
    if not root:
        raise HTTPException(status_code=404, detail="Entidade não localizada")

    all_rows: list[sqlite3.Row] = []
    # paginação por direção já resolve volume para o nó de ancora no padrão on-demand
    totals_by_direction: dict[int, int] = {-1: 0, 0: 0, 1: 0}

    if include_up:
        up_rows = fetch_neighbors_paginated(
            conn=conn,
            entity_id=root_id,
            relation_types=relation_types,
            include_weak=include_weak,
            direction="up",
            max_per_node=max_per_node,
            offset=up_offset,
        )
        all_rows.extend(up_rows)
        totals_by_direction.update(count_neighbors(conn, root_id, relation_types, include_weak, {-1}))

    if include_down:
        down_rows = fetch_neighbors_paginated(
            conn=conn,
            entity_id=root_id,
            relation_types=relation_types,
            include_weak=include_weak,
            direction="down",
            max_per_node=max_per_node,
            offset=down_offset,
        )
        all_rows.extend(down_rows)
        totals_by_direction.update(count_neighbors(conn, root_id, relation_types, include_weak, {1}))

    if include_same:
        same_rows = fetch_neighbors_paginated(
            conn=conn,
            entity_id=root_id,
            relation_types=relation_types,
            include_weak=include_weak,
            direction="same",
            max_per_node=max_per_node,
            offset=same_offset,
        )
        all_rows.extend(same_rows)
        totals_by_direction.update(count_neighbors(conn, root_id, relation_types, include_weak, {0}))

    node_ids = {root_id}
    for row in all_rows:
        node_ids.add(row["neighbor_id"])

    nodes_db = _fetch_entity_rows(conn, node_ids)

    relation_totals = count_neighbors(conn, root_id, relation_types, include_weak)
    visible_by_direction = defaultdict(int)
    for row in all_rows:
        visible_by_direction[_safe_int(row["direction_delta"])] += 1

    relations: dict[tuple[str, str, str], RelationItem] = {}
    node_roles: dict[str, set[str]] = defaultdict(set)
    depth_by_node: dict[str, int] = {root_id: 0}
    for row in all_rows:
        direction_delta = _safe_int(row["direction_delta"])
        source_is_current = row["current_id"] == row["source"]

        role_from_current = role_from_type(row["tipo_vinculo"], direction_delta)
        role_from_neighbor = role_from_type(row["tipo_vinculo"], -direction_delta)

        key = (row["vinculo_id"], row["source"], row["target"])
        relations[key] = RelationItem(
            id=row["vinculo_id"],
            source=row["source"],
            target=row["target"],
            tipo_vinculo=row["tipo_vinculo"],
            tipo_nome=RELATION_LABEL.get(row["tipo_vinculo"], row["tipo_vinculo"]),
            relation_depth_delta=direction_delta,
            role_from_source=role_from_current if source_is_current else role_from_neighbor,
            role_from_target=role_from_neighbor if source_is_current else role_from_current,
            confianca_vinculo=_safe_float(row["confianca_vinculo"]),
            requer_revisao=_safe_bool(row["requer_revisao"]),
        )

        node_roles[row["source"]].add(role_from_current if source_is_current else role_from_neighbor)
        node_roles[row["target"]].add(role_from_neighbor if source_is_current else role_from_current)
        if row["current_id"] == root_id:
            depth_by_node[row["neighbor_id"]] = direction_delta

    node_payload: list[EntityNode] = []
    for node_id in node_ids:
        entity = nodes_db.get(node_id)
        if not entity:
            continue

        role_set = node_roles[node_id] if node_id in node_roles else {"selecionado" if node_id == root_id else "vínculo"}
        depth = depth_by_node.get(node_id, 0)

        if node_id == root_id:
            visible = visible_by_direction.get(-1, 0) + visible_by_direction.get(0, 0) + visible_by_direction.get(1, 0)
            total = _safe_int(relation_totals.get(-1, 0)) + _safe_int(relation_totals.get(0, 0)) + _safe_int(relation_totals.get(1, 0))
            hidden = max(0, total - visible)
        else:
            hidden = 0

        node_payload.append(
            EntityNode(
                id=node_id,
                nome=_build_entity_label(entity),
                cpf_cnpj=entity["cpf_cnpj"] or "",
                tipo_entidade=entity["tipo_entidade"] or "",
                status_entidade=entity["status_entidade"] or "",
                data_nascimento=entity["data_nascimento"] or "",
                data_obito=entity["data_obito"] or "",
                documento_valido=entity["documento_valido"] or "false",
                alerta=entity["alertas"] or "",
                depth=depth,
                total_vizinhos=(
                    _safe_int(relation_totals.get(-1, 0))
                    + _safe_int(relation_totals.get(0, 0))
                    + _safe_int(relation_totals.get(1, 0))
                    if node_id == root_id
                    else 0
                ),
                hidden_vizinhos=hidden,
                roles=sorted(role_set),
            )
        )

    max_depth = 0
    if node_payload:
        max_depth = max(abs(n.depth) for n in node_payload)

    return TreeResponse(
        root_id=root_id,
        nodes=node_payload,
        relations=list(relations.values()),
        has_more_up=totals_by_direction.get(-1, 0) > up_offset + (len([x for x in all_rows if x["direction_delta"] == -1]) if all_rows else 0),
        has_more_down=totals_by_direction.get(1, 0) > down_offset + (len([x for x in all_rows if x["direction_delta"] == 1]) if all_rows else 0),
        has_more_same=totals_by_direction.get(0, 0) > same_offset + (len([x for x in all_rows if x["direction_delta"] == 0]) if all_rows else 0),
        next_up_offset=up_offset + max_per_node if include_up else 0,
        next_down_offset=down_offset + max_per_node if include_down else 0,
        next_same_offset=same_offset + max_per_node if include_same else 0,
        max_depth=max_depth,
        max_per_node=max_per_node,
        scope=",".join(relation_types),
        include_weak=include_weak,
        include_type=("up+down" if include_up and include_down else "up" if include_up else "down" if include_down else "same"),
        summary={
            "total_nodos": len(node_payload),
            "total_relacoes": len(relations),
            "nivel_max": max_depth,
            "up_total": _safe_int(relation_totals.get(-1, 0)),
            "down_total": _safe_int(relation_totals.get(1, 0)),
            "same_total": _safe_int(relation_totals.get(0, 0)),
            "modo": anchor_label,
        },
    )


def search_entities_query(
    conn: sqlite3.Connection,
    q: str,
    limit: int,
    offset: int,
    tipo: str | None,
    include_external: bool,
    only_active: bool = False,
) -> SearchResponse:
    if not q or len(q.strip()) < 2:
        return SearchResponse(query=q, total=0, limit=limit, offset=offset, items=[])

    normalized = _normalize_raw_term(q)
    raw_numbers = re.sub(r"\D+", "", q)
    where_clauses: list[str] = []
    params: list[Any] = []

    if raw_numbers:
        where_clauses.append("(LOWER(cpf_cnpj) = ? OR CAST(entidade_id AS TEXT) LIKE ?)")
        params.extend([raw_numbers, f"%{raw_numbers}%"])

    safe = _safe_like_pattern(normalized) if normalized else ""
    if normalized:
        where_clauses.append(
            "(LOWER(nome_canonico_normalizado) LIKE ? ESCAPE '\\\\' OR LOWER(nome_original_normalizado) LIKE ? ESCAPE '\\\\' OR LOWER(cpf_cnpj) LIKE ? ESCAPE '\\\\')"
        )
        params.extend([f"{safe}%", f"{safe}%", f"{raw_numbers or ''}%"])

    if only_active:
        where_clauses.append("LOWER(COALESCE(status_entidade, '')) = 'ativo'")

    if not where_clauses:
        return SearchResponse(query=q, total=0, limit=limit, offset=offset, items=[])

    if tipo:
        where_clauses.append("tipo_entidade = ?")
        params.append(tipo)

    if not include_external:
        where_clauses.append("tipo_entidade NOT LIKE '%EXTERNA%'")

    where_sql = " WHERE " + " AND ".join(where_clauses)
    count_sql = f"SELECT COUNT(*) AS total FROM entidades {where_sql}"
    total = _safe_int(conn.execute(count_sql, params).fetchone()[0])

    order = (
        "LOWER(entidade_id) = ? DESC, "
        "LOWER(cpf_cnpj) = ? DESC, "
        f"LOWER(COALESCE(nome_canonico_normalizado, '')) LIKE ? ESCAPE '\\\\' DESC, "
        f"LOWER(COALESCE(nome_original_normalizado, '')) LIKE ? ESCAPE '\\\\' DESC, "
        "LOWER(COALESCE(nome_canonico, '')) ASC"
    )

    order_like = f"{safe}%" if safe else "%%"
    search_params = params + [
        raw_numbers.lower() if raw_numbers else "",
        raw_numbers.lower() if raw_numbers else "",
        order_like,
        order_like,
        order_like,
    ]
    data = conn.execute(
        f"SELECT * FROM entidades {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
        [*search_params, limit, offset],
    ).fetchall()

    items = [
        SearchItem(
            entidade_id=row["entidade_id"],
            nome=_build_entity_label(row),
            cpf_cnpj=row["cpf_cnpj"] or "",
            tipo_entidade=row["tipo_entidade"] or "",
            status_entidade=row["status_entidade"] or "",
            data_nascimento=row["data_nascimento"] or "",
            documento_valido=row["documento_valido"] or "false",
            score=95.0 if raw_numbers and (row["cpf_cnpj"] == raw_numbers or str(row["entidade_id"]) == raw_numbers) else 70.0,
            motivo="Documento localizado" if raw_numbers and (row["cpf_cnpj"] == raw_numbers or str(row["entidade_id"]) == raw_numbers) else "Nome ou documento encontrado",
        )
        for row in data
    ]
    return SearchResponse(query=q, total=total, limit=limit, offset=offset, items=items)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", db_status="disponivel" if DB_PATH.exists() else "ausente")


@app.get("/api/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            total_entidades = _safe_int(conn.execute("SELECT COUNT(*) AS total FROM entidades").fetchone()[0])
            total_vinculos = _safe_int(conn.execute("SELECT COUNT(*) AS total FROM vinculos").fetchone()[0])
            total_grupos = _safe_int(conn.execute("SELECT COUNT(*) AS total FROM grupos").fetchone()[0])
            total_revisao = _safe_int(conn.execute("SELECT COUNT(*) AS total FROM fila_revisao").fetchone()[0])
            rows = conn.execute("SELECT tipo_entidade, COUNT(*) AS total FROM entidades GROUP BY tipo_entidade").fetchall()
            tipos = {row["tipo_entidade"]: _safe_int(row["total"]) for row in rows}
    finally:
        conn.close()

    return MetadataResponse(
        total_entidades=total_entidades,
        total_vinculos=total_vinculos,
        total_grupos=total_grupos,
        total_revisao=total_revisao,
        total_pessoas=_safe_int(tipos.get("PF", 0)) + _safe_int(tipos.get("PF_EXTERNA", 0)),
        total_empresas=_safe_int(tipos.get("PJ", 0)) + _safe_int(tipos.get("PJ_EXTERNA", 0)),
        tipo_entidade=tipos,
    )


@app.get("/api/entities/search", response_model=SearchResponse)
def search_entities(
    q: str,
    limit: int = Query(default=20, ge=1, le=MAX_SEARCH_LIMIT),
    offset: int = Query(default=0, ge=0),
    tipo: str | None = None,
    include_external: bool = True,
    only_active: bool = False,
) -> SearchResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            response = search_entities_query(
                conn=conn,
                q=q,
                limit=limit,
                offset=offset,
                tipo=tipo,
                include_external=include_external,
                only_active=only_active,
            )
    finally:
        conn.close()
    return response


@app.get("/api/entities/{entidade_id}", response_model=EntityDetailResponse)
def entity_detail(entidade_id: str) -> EntityDetailResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            entity = conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (entidade_id,)).fetchone()
            if not entity:
                raise HTTPException(status_code=404, detail="Entidade não encontrada")

            links_count = _safe_int(
                conn.execute(
                    "SELECT COUNT(*) FROM vinculos WHERE entidade_origem = ? OR entidade_destino = ?",
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

            total_groups = _safe_int(
                conn.execute("SELECT COUNT(DISTINCT grupo_id) AS total FROM membros_grupo WHERE entidade_id = ?", (entidade_id,)).fetchone()[0]
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
        conexoes_por_tipo={row["tipo_vinculo"]: _safe_int(row["total"]) for row in links_by_type},
        grupos=[
            GroupItem(
                grupo_id=row["grupo_id"],
                tipo_grupo=row["tipo_grupo"],
                nome_grupo=row["nome_grupo"],
                status_grupo=row["status_grupo"],
                grupo_regulatorio=row["grupo_regulatorio"],
                requer_revisao=_safe_bool(row["requer_revisao"]),
                confianca_grupo=row["confianca_grupo"] or "",
            )
            for row in groups
        ],
    )


@app.get("/api/tree/family/{entidade_id}", response_model=TreeResponse)
def tree_family_view(
    entidade_id: str,
    max_per_node: int = Query(default=20, ge=1, le=MAX_RELATIONS_PER_NODE),
    include_weak: bool = False,
    relation_scope: str = "family",
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    """Retorno inicial para visualização amigável:
    traz pais/parentesco na parte superior e filhos na inferior.
    """

    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            relation_types = parse_scope(relation_scope)
            return _prepare_tree_payload(
                conn=conn,
                root_id=entidade_id,
                relation_types=relation_types,
                include_weak=include_weak,
                max_per_node=max_per_node,
                up_offset=up_offset,
                down_offset=down_offset,
                include_up=True,
                include_down=True,
                include_same=False,
                anchor_label="family",
            )
    finally:
        conn.close()


@app.get("/api/tree/branch/{entidade_id}", response_model=TreeResponse)
def tree_branch(
    entidade_id: str,
    direction: str = Query(default="down", description="up | down | same | both"),
    relation_scope: str = "family,business",
    max_per_node: int = Query(default=20, ge=1, le=MAX_RELATIONS_PER_NODE),
    include_weak: bool = False,
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    normalized_direction = direction.lower()
    if normalized_direction not in {"up", "down", "same", "both"}:
        raise HTTPException(status_code=400, detail="direction deve ser up, down, same ou both")

    include_up = normalized_direction in {"up", "both"}
    include_down = normalized_direction in {"down", "both"}
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            relation_types = parse_scope(relation_scope)
            return _prepare_tree_payload(
                conn=conn,
                root_id=entidade_id,
                relation_types=relation_types,
                include_weak=include_weak,
                max_per_node=max_per_node,
                up_offset=up_offset,
                down_offset=down_offset,
                same_offset=same_offset,
                include_up=include_up,
                include_down=include_down,
                include_same=False,
                anchor_label=f"branch:{normalized_direction}",
            )
    finally:
        conn.close()


@app.get("/api/tree/context/{entidade_id}", response_model=TreeResponse)
def tree_context(
    entidade_id: str,
    include_up: bool = Query(default=True),
    include_down: bool = Query(default=True),
    include_same: bool = Query(default=False),
    relation_scope: str = "family,business",
    max_per_node: int = Query(default=20, ge=1, le=MAX_RELATIONS_PER_NODE),
    include_weak: bool = False,
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            return _prepare_tree_payload(
                conn=conn,
                root_id=entidade_id,
                relation_types=parse_scope(relation_scope),
                include_weak=include_weak,
                max_per_node=max_per_node,
                up_offset=up_offset,
                down_offset=down_offset,
                same_offset=same_offset,
                include_up=include_up,
                include_down=include_down,
                include_same=include_same,
                anchor_label="context",
            )
    finally:
        conn.close()


# Compatibilidade com rotas anteriores
@app.get("/api/tree/seed/{entidade_id}", response_model=TreeResponse)
def tree_seed(
    entidade_id: str,
    max_per_node: int = Query(default=20, ge=1, le=MAX_RELATIONS_PER_NODE),
    include_weak: bool = False,
    include_business: bool = False,
):
    return tree_family_view(
        entidade_id=entidade_id,
        max_per_node=max_per_node,
        include_weak=include_weak,
        relation_scope="family,business" if include_business else "family",
    )


@app.get("/api/tree/entity/{entidade_id}", response_model=TreeResponse)
def tree_from_entity(
    entidade_id: str,
    max_per_node: int = Query(default=20, ge=1, le=MAX_RELATIONS_PER_NODE),
    include_weak: bool = False,
    relation_scope: str = "family,business",
):
    return tree_context(
        entidade_id=entidade_id,
        include_up=True,
        include_down=True,
        include_same=False,
        relation_scope=relation_scope,
        max_per_node=max_per_node,
        include_weak=include_weak,
    )


@app.get("/api/tree/expand/{entidade_id}", response_model=TreeResponse)
def tree_expand(
    entidade_id: str,
    direction: str = Query(default="both", description="up | down | same | both"),
    relation_scope: str = "family,business",
    max_per_node: int = Query(default=20, ge=1, le=MAX_RELATIONS_PER_NODE),
    include_weak: bool = False,
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
):
    return tree_branch(
        entidade_id=entidade_id,
        direction=direction,
        relation_scope=relation_scope,
        max_per_node=max_per_node,
        include_weak=include_weak,
        up_offset=up_offset,
        down_offset=down_offset,
        same_offset=same_offset,
    )


@app.exception_handler(HTTPException)
def http_exception_handler(_: Any, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
