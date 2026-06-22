from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

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


# Regras de direção semântica
# -1 -> para cima (ascendente), +1 -> para baixo (descendente), 0 -> mesmo nível
FAMILY_DIRECTION_TYPES = {"FILHO_DE", "PAI_DE", "MAE_DE", "IRMAO_DE", "CONJUGE_DE", "CONJUGE_NOME_CANDIDATO"}


def relation_direction_delta(rel_type: str, source_is_current: bool) -> int:
    if rel_type == "FILHO_DE":
        return -1 if source_is_current else 1
    if rel_type in {"PAI_DE", "MAE_DE"}:
        return 1 if source_is_current else -1
    return 0


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
    max_depth: int
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
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_can_lower ON entidades (lower(nome_canonico))",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_ori_lower ON entidades (lower(nome_original))",
        "CREATE INDEX IF NOT EXISTS idx_entidades_cpf ON entidades (cpf_cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_status ON entidades (status_entidade)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_updated ON entidades (data_atualizacao)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_origem_tipo ON vinculos (entidade_origem, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_destino_tipo ON vinculos (entidade_destino, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_revisao ON vinculos (requer_revisao)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_tipos ON vinculos (tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_membro_ent ON membros_grupo (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_membro_grp ON membros_grupo (grupo_id)",
    ]
    for statement in ddl:
        conn.execute(statement)


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


def build_tree_payload(
    conn: sqlite3.Connection,
    root_id: str,
    max_depth: int,
    max_per_node: int,
    relation_types: list[str],
    include_weak: bool,
    direction: str,
) -> TreeResponse:
    if max_depth < 0:
        raise HTTPException(status_code=400, detail="max_depth deve ser >= 0")
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

    def add_relation(neighbor: Neighbor, depth_delta: int, current_depth: int) -> None:
        nonlocal reached

        direction_delta = depth_delta
        role = relation_role(neighbor.tipo_vinculo, neighbor.source_is_current, direction_delta)
        node_roles[neighbor.neighbor_id].add(role)

        rel_key = (neighbor.relation_id, neighbor.source, neighbor.target)
        if rel_key not in relations:
            relations[rel_key] = RelationItem(
                id=neighbor.relation_id,
                source=neighbor.source,
                target=neighbor.target,
                tipo_vinculo=neighbor.tipo_vinculo,
                tipo_nome=RELATION_LABEL.get(neighbor.tipo_vinculo, neighbor.tipo_vinculo.lower()),
                relation_depth_delta=direction_delta,
                role_from_source=relation_role_for_endpoint(neighbor.tipo_vinculo, True, direction_delta),
                role_from_target=relation_role_for_endpoint(neighbor.tipo_vinculo, False, direction_delta),
                confianca_vinculo=neighbor.confianca,
                requer_revisao=neighbor.requer_revisao,
            )

    def expand_direction(frontier: set[str], direction_hint: str, expected_depth: int) -> set[str]:
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
            if current_depth is None or current_depth != expected_depth:
                continue

            add_relation(neighbor, neighbor.direction_delta, current_depth)
            if reached >= MAX_NODE_LIMIT:
                break

            new_depth = current_depth + neighbor.direction_delta
            if neighbor.neighbor_id not in node_depth:
                if reached >= MAX_NODE_LIMIT:
                    continue
                node_depth[neighbor.neighbor_id] = new_depth
                reached += 1
            elif abs(new_depth) < abs(node_depth[neighbor.neighbor_id]):
                node_depth[neighbor.neighbor_id] = new_depth
            elif new_depth != node_depth[neighbor.neighbor_id]:
                continue

            if direction_hint == "up" and new_depth == expected_depth - 1:
                next_frontier.add(neighbor.neighbor_id)
            elif direction_hint == "down" and new_depth == expected_depth + 1:
                next_frontier.add(neighbor.neighbor_id)
            elif direction_hint == "same" and new_depth == expected_depth:
                next_frontier.add(neighbor.neighbor_id)
            elif direction_hint == "both":
                if new_depth == expected_depth - 1:
                    next_frontier.add(neighbor.neighbor_id)
                elif new_depth == expected_depth + 1:
                    next_frontier.add(neighbor.neighbor_id)
                elif new_depth == expected_depth:
                    next_frontier.add(neighbor.neighbor_id)

        return next_frontier

    if include_up and max_depth > 0:
        frontier_up = {root_id}
        for depth_level in range(1, max_depth + 1):
            next_frontier = expand_direction(frontier_up, "up", -(depth_level - 1))
            if not next_frontier or reached >= MAX_NODE_LIMIT:
                break
            frontier_up = next_frontier

    if include_down and max_depth > 0:
        frontier_down = {root_id}
        for depth_level in range(1, max_depth + 1):
            next_frontier = expand_direction(frontier_down, "down", (depth_level - 1))
            if not next_frontier or reached >= MAX_NODE_LIMIT:
                break
            frontier_down = next_frontier

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
                add_relation(neighbor, 0, node_depth[current])
                if neighbor.neighbor_id not in node_depth and reached < MAX_NODE_LIMIT:
                    node_depth[neighbor.neighbor_id] = node_depth[current]
                    reached += 1

    node_rows = fetch_entities(conn, set(node_depth.keys()))
    if node_rows:
        totals = count_neighbors(conn, set(node_depth.keys()), relation_types, include_weak)
    else:
        totals = {}

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
                roles=_role_text_for_node(node_roles[node_id]) if node_id in node_roles else ["selecionado" if node_id == root_id else "vínculo"],
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
        has_more_up=max_depth > max_up,
        has_more_down=max_depth > max_down,
        max_depth=max_depth,
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
            query_like = f"%{normalize_term_for_like(query_text)}%"
            query_prefix = f"{normalize_term_for_like(query_text)}%"

            conditions = ["1 = 1"]
            params: dict[str, Any] = {
                "limit": limit,
                "offset": offset,
                "q_like": query_like,
                "q_prefix": query_prefix,
                "q_eq": normalize_term_for_like(query_text),
            }

            name_contains = " OR ".join(
                [
                    "LOWER(COALESCE(nome_canonico, '')) LIKE :q_like ESCAPE '\\'",
                    "LOWER(COALESCE(nome_original, '')) LIKE :q_like ESCAPE '\\'",
                ]
            ) if len(query_text) >= 3 else ""
            text_conditions = [
                "LOWER(COALESCE(entidade_id, '')) = :q_eq",
                "LOWER(COALESCE(cpf_cnpj, '')) = :q_eq",
                "LOWER(COALESCE(nome_canonico, '')) LIKE :q_prefix ESCAPE '\\'",
                "LOWER(COALESCE(nome_original, '')) LIKE :q_prefix ESCAPE '\\'",
            ]
            if name_contains:
                text_conditions.append(f"({name_contains})")
            conditions.append("(" + " OR ".join(text_conditions) + ")")

            if tipo:
                conditions.append("tipo_entidade = :tipo")
                params["tipo"] = tipo

            if not include_external:
                conditions.append("tipo_entidade NOT LIKE '%EXTERNA%'")

            if only_active:
                conditions.append("status_entidade = 'ATIVO'")

            where_sql = " WHERE " + " AND ".join(conditions)

            order = ""
            if query_text:
                order = (
                    "CASE WHEN LOWER(COALESCE(entidade_id, '')) = :q_eq THEN 0 ELSE 1 END, "
                    "CASE WHEN LOWER(COALESCE(cpf_cnpj, '')) = :q_eq THEN 0 ELSE 1 END, "
                    "CASE WHEN LOWER(COALESCE(nome_canonico, '')) LIKE :q_prefix ESCAPE '\\' OR "
                    "LOWER(COALESCE(nome_original, '')) LIKE :q_prefix ESCAPE '\\' THEN 0 ELSE 1 END, "
                    "nome_canonico ASC"
                )
                order = ",".join(order)
            else:
                order = "nome_canonico ASC"

            total = conn.execute(f"SELECT COUNT(*) AS total FROM entidades{where_sql}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM entidades{where_sql} ORDER BY {order} LIMIT :limit OFFSET :offset", params).fetchall()
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
            score=95.0 if row["entidade_id"] == q else (90.0 if str(row["cpf_cnpj"]).lower() == q.lower() else 80.0),
            motivo="registro confirmado" if row["documento_valido"] == "true" else "confirmação recomendada",
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


@app.get("/api/tree/family/{entidade_id}", response_model=TreeResponse)
def tree_family_view(
    entidade_id: str,
    max_depth: int = Query(default=2, ge=0, le=8),
    max_per_node: int = Query(default=12, ge=1, le=80),
    include_weak: bool = False,
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            return build_tree_payload(
                conn=conn,
                root_id=entidade_id,
                max_depth=max_depth,
                max_per_node=max_per_node,
                relation_types=parse_scope("family"),
                include_weak=include_weak,
                direction="both",
            )
    finally:
        conn.close()


@app.get("/api/tree/seed/{entidade_id}", response_model=TreeResponse)
def tree_seed(entidade_id: str, max_per_node: int = Query(default=12, ge=1, le=80), include_weak: bool = False, include_business: bool = False):
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scope = "family,business" if include_business else "family"
            return build_tree_payload(
                conn=conn,
                root_id=entidade_id,
                max_depth=1,
                max_per_node=max_per_node,
                relation_types=parse_scope(scope),
                include_weak=include_weak,
                direction="all",
            )
    finally:
        conn.close()


@app.get("/api/tree/entity/{entidade_id}", response_model=TreeResponse)
def tree_from_entity(
    entidade_id: str,
    max_depth: int = Query(default=2, ge=0, le=12),
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_weak: bool = False,
    relation_scope: str = "family,business",
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scope_types = parse_scope(relation_scope)
            return build_tree_payload(
                conn=conn,
                root_id=entidade_id,
                max_depth=max_depth,
                max_per_node=max_per_node,
                relation_types=scope_types,
                include_weak=include_weak,
                direction="both",
            )
    finally:
        conn.close()


@app.get("/api/tree/branch/{entidade_id}", response_model=TreeResponse)
def tree_branch(
    entidade_id: str,
    max_depth: int = Query(default=1, ge=0, le=8),
    max_per_node: int = Query(default=12, ge=1, le=80),
    include_weak: bool = False,
    direction: str = "all",
    relation_scope: str = "family,business",
) -> TreeResponse:
    normalized_direction = (direction or "all").lower()
    if normalized_direction not in {"all", "up", "down", "both"}:
        raise HTTPException(status_code=400, detail="direction deve ser all, up, down ou both")

    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scope_types = parse_scope(relation_scope)
            return build_tree_payload(
                conn=conn,
                root_id=entidade_id,
                max_depth=max_depth,
                max_per_node=max_per_node,
                relation_types=scope_types,
                include_weak=include_weak,
                direction=normalized_direction,
            )
    finally:
        conn.close()


@app.exception_handler(HTTPException)
def http_exception_handler(_: Any, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
