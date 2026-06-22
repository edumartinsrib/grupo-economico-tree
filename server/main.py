from __future__ import annotations

from collections import deque
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Iterable

import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "resultados" / "grafo_resultado.sqlite"


app = FastAPI(
    title="Grupo Econômico Tree API",
    version="4.0.0",
    description="API simples para consulta sob demanda da rede familiar e societária.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

ALL_RELATIONS = set().union(*RELATION_BY_SCOPE.values())

RELATION_LABEL = {
    "FILHO_DE": "pai/mãe",
    "PAI_DE": "filho(a)",
    "MAE_DE": "filho(a)",
    "IRMAO_DE": "irmão(a)",
    "CONJUGE_DE": "cônjuge",
    "CONJUGE_NOME_CANDIDATO": "cônjuge (candidato)",
    "SOCIO_DE": "sócio",
    "SOCIO_COTISTA": "sócio-cotista",
    "CONTROLADOR_DIRETO": "controlador",
    "CONTROLADOR_CONJUNTO_CANDIDATO": "controle conjunto",
    "INFLUENCIA_RELEVANTE": "participação relevante",
    "SOCIO_MINORITARIO": "participação minoritária",
    "PARTICIPACAO_INDIRETA": "participação indireta",
    "ENDERECO_COMPARTILHADO": "endereço em comum",
    "CONTATO_COMPARTILHADO": "contato compartilhado",
    "EMPREGADO_DE": "vínculo de emprego",
    "TIO_TIA_DE": "tio/tia",
    "ESPOLIO_DE": "espólio",
    "PARENTESCO_AMBIGUO": "parentesco ambíguo",
    "POSSIVEL_MESMO_GENITOR": "possível mesmo genitor",
    "TRANSFERIU_PARA": "fluxo financeiro",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA": "dependência financeira sugerida",
    "DEPENDENCIA_FINANCEIRA_CONFIRMADA": "dependência financeira confirmada",
}

MAX_NODE_LIMIT = 2500


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
    score: int
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


@dataclass
class Neighbor:
    relation_id: str
    source: str
    target: str
    tipo_vinculo: str
    confianca: float
    requer_revisao: bool
    data_observacao: str


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


ndefloat = 0.0

def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Banco não encontrado: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn



def ensure_indexes(conn: sqlite3.Connection) -> None:
    index_ddl = [
        "CREATE INDEX IF NOT EXISTS idx_entidades_id ON entidades (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_tipo ON entidades (tipo_entidade)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_can ON entidades (nome_canonico)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_ori ON entidades (nome_original)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_cpf ON entidades (cpf_cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_origem_tipo ON vinculos (entidade_origem, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_destino_tipo ON vinculos (entidade_destino, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_revisao ON vinculos (requer_revisao)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_tipos ON vinculos (tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_membro_ent ON membros_grupo (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_membro_grp ON membros_grupo (grupo_id)",
    ]
    for ddl in index_ddl:
        conn.execute(ddl)


def parse_scope(scope: str) -> list[str]:
    if not scope:
        return list(FAMILY_RELATIONS | WEAK_FAMILY_RELATIONS)

    requested: set[str] = set()
    for item in scope.split(","):
        value = item.strip().lower()
        if not value:
            continue

        if value in {"all", "*", "completo", "completo"}:
            requested = set(ALL_RELATIONS)
            break

        if value in RELATION_BY_SCOPE:
            requested |= RELATION_BY_SCOPE[value]

        if value == "familia" or value == "family":
            requested |= RELATION_BY_SCOPE["family"]

    if not requested:
        return list(FAMILY_RELATIONS | WEAK_FAMILY_RELATIONS)

    return sorted(requested)


def relation_direction_delta(rel_type: str, source_is_current: bool) -> int:
    if rel_type == "FILHO_DE":
        return -1 if source_is_current else 1
    if rel_type in {"PAI_DE", "MAE_DE"}:
        return 1 if source_is_current else -1
    return 0


def get_entity(conn: sqlite3.Connection, entidade_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (entidade_id,)).fetchone()


def fetch_neighbors(
    conn: sqlite3.Connection,
    entidade_id: str,
    rel_types: list[str],
    include_weak: bool,
    max_per_node: int,
) -> list[Neighbor]:
    if not rel_types:
        return []

    placeholders = ",".join("?" * len(rel_types))
    query = f"""
    SELECT vinculo_id, entidade_origem, entidade_destino, tipo_vinculo,
           CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
           CAST(COALESCE(requer_revisao, 'false') AS TEXT) AS requer_revisao,
           COALESCE(data_observacao, '') AS data_observacao
      FROM vinculos
     WHERE (entidade_origem = ? OR entidade_destino = ?)
       AND tipo_vinculo IN ({placeholders})
    """

    params: list[Any] = [entidade_id, entidade_id, *rel_types]

    if not include_weak:
        query += " AND (CAST(COALESCE(requer_revisao, 'false') AS TEXT) <> 'true' )"

    query += " ORDER BY confianca_vinculo DESC, vinculo_id ASC LIMIT ?"
    params.append(max_per_node)

    rows = conn.execute(query, params).fetchall()
    return [
        Neighbor(
            relation_id=row["vinculo_id"],
            source=row["entidade_origem"],
            target=row["entidade_destino"],
            tipo_vinculo=row["tipo_vinculo"],
            confianca=safe_float(row["confianca_vinculo"]),
            requer_revisao=(str(row["requer_revisao"]).lower() == "true"),
            data_observacao=row["data_observacao"] or "",
        )
        for row in rows
    ]


def relation_count(conn: sqlite3.Connection, entidade_id: str, rel_types: list[str], include_weak: bool) -> int:
    if not rel_types:
        return 0

    placeholders = ",".join("?" * len(rel_types))
    query = f"""
    SELECT COUNT(*) AS total
      FROM vinculos
     WHERE (entidade_origem = ? OR entidade_destino = ?)
       AND tipo_vinculo IN ({placeholders})
    """
    params: list[Any] = [entidade_id, entidade_id, *rel_types]

    if not include_weak:
        query += " AND (CAST(COALESCE(requer_revisao, 'false') AS TEXT) <> 'true')"

    return safe_int(conn.execute(query, params).fetchone()[0])


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

    # Cada nó guarda a menor profundidade encontrada.
    node_depth: dict[str, int] = {root_id: 0}
    frontier_up = {root_id}
    frontier_down = {root_id}
    max_reached = 1

    relations: dict[tuple[str, str, str], RelationItem] = {}

    allowed_up = direction in {"both", "up", "all"}
    allowed_down = direction in {"both", "down", "all"}

    # Subir (pais, ascendentes)
    if allowed_up and max_depth > 0:
        for depth in range(1, max_depth + 1):
            next_frontier: set[str] = set()
            for current in list(frontier_up):
                if max_reached >= MAX_NODE_LIMIT:
                    break
                if node_depth.get(current, 0) != -depth + 1:
                    continue

                for neigh in fetch_neighbors(conn, current, relation_types, include_weak, max_per_node):
                    source_is_current = neigh.source == current
                    delta = relation_direction_delta(neigh.tipo_vinculo, source_is_current)
                    if delta != -1:
                        continue

                    neighbor_id = neigh.target if source_is_current else neigh.source
                    relation_depth = node_depth[current] - 1
                    relation_key = (neigh.relation_id, neigh.source, neigh.target)
                    if relation_key not in relations:
                        relations[relation_key] = RelationItem(
                            id=neigh.relation_id,
                            source=neigh.source,
                            target=neigh.target,
                            tipo_vinculo=neigh.tipo_vinculo,
                            tipo_nome=RELATION_LABEL.get(neigh.tipo_vinculo, neigh.tipo_vinculo.lower()),
                            relation_depth_delta=delta,
                            confianca_vinculo=neigh.confianca,
                            requer_revisao=neigh.requer_revisao,
                        )

                    if neighbor_id not in node_depth:
                        node_depth[neighbor_id] = relation_depth
                        max_reached += 1
                        if max_reached >= MAX_NODE_LIMIT:
                            break
                        if relation_depth == -depth:
                            next_frontier.add(neighbor_id)
                    elif abs(relation_depth) < abs(node_depth[neighbor_id]):
                        node_depth[neighbor_id] = relation_depth

                if max_reached >= MAX_NODE_LIMIT:
                    break
            frontier_up = next_frontier
            if not frontier_up:
                break

    # Descer (filhos e descendentes)
    if allowed_down and max_depth > 0:
        for depth in range(1, max_depth + 1):
            next_frontier: set[str] = set()
            for current in list(frontier_down):
                if max_reached >= MAX_NODE_LIMIT:
                    break
                if node_depth.get(current, 0) != depth - 1:
                    continue

                for neigh in fetch_neighbors(conn, current, relation_types, include_weak, max_per_node):
                    source_is_current = neigh.source == current
                    delta = relation_direction_delta(neigh.tipo_vinculo, source_is_current)
                    if delta != 1:
                        continue

                    neighbor_id = neigh.target if source_is_current else neigh.source
                    relation_key = (neigh.relation_id, neigh.source, neigh.target)
                    if relation_key not in relations:
                        relations[relation_key] = RelationItem(
                            id=neigh.relation_id,
                            source=neigh.source,
                            target=neigh.target,
                            tipo_vinculo=neigh.tipo_vinculo,
                            tipo_nome=RELATION_LABEL.get(neigh.tipo_vinculo, neigh.tipo_vinculo.lower()),
                            relation_depth_delta=delta,
                            confianca_vinculo=neigh.confianca,
                            requer_revisao=neigh.requer_revisao,
                        )

                    relation_depth = node_depth[current] + 1
                    if neighbor_id not in node_depth:
                        node_depth[neighbor_id] = relation_depth
                        max_reached += 1
                        if max_reached >= MAX_NODE_LIMIT:
                            break
                        if relation_depth == depth:
                            next_frontier.add(neighbor_id)
                    elif abs(relation_depth) < abs(node_depth[neighbor_id]):
                        node_depth[neighbor_id] = relation_depth

                if max_reached >= MAX_NODE_LIMIT:
                    break
            frontier_down = next_frontier
            if not frontier_down:
                break

    # Relações paralelas no mesmo nível (cônjuge, irmãos, etc.) para o próprio nó e vizinhos já carregados.
    if direction == "all":
        same_level_nodes = [node_id for node_id, d in node_depth.items() if d != 0]
        same_level_nodes.append(root_id)
        for current in same_level_nodes:
            if max_reached >= MAX_NODE_LIMIT:
                break
            for neigh in fetch_neighbors(conn, current, relation_types, include_weak, max_per_node):
                source_is_current = neigh.source == current
                delta = relation_direction_delta(neigh.tipo_vinculo, source_is_current)
                if delta != 0:
                    continue

                neighbor_id = neigh.target if source_is_current else neigh.source
                relation_key = (neigh.relation_id, neigh.source, neigh.target)
                if relation_key not in relations:
                    relations[relation_key] = RelationItem(
                        id=neigh.relation_id,
                        source=neigh.source,
                        target=neigh.target,
                        tipo_vinculo=neigh.tipo_vinculo,
                        tipo_nome=RELATION_LABEL.get(neigh.tipo_vinculo, neigh.tipo_vinculo.lower()),
                        relation_depth_delta=delta,
                        confianca_vinculo=neigh.confianca,
                        requer_revisao=neigh.requer_revisao,
                    )

                if neighbor_id not in node_depth and max_reached < MAX_NODE_LIMIT:
                    node_depth[neighbor_id] = node_depth[current]
                    max_reached += 1

    nodes_payload: list[EntityNode] = []
    max_depth_reached = 0
    min_depth = 0
    for node_id, depth in node_depth.items():
        entity = get_entity(conn, node_id)
        if not entity:
            continue
        total_links = relation_count(conn, node_id, relation_types, include_weak)
        hidden = max(0, total_links - max_per_node)
        if total_links > max_per_node:
            # evita contar como oculto para nós que já aparecem no limite de BFS se conexão fraca for removida.
            hidden = max(0, total_links - max_per_node)

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
                total_vizinhos=total_links,
                hidden_vizinhos=hidden,
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
        max_depth=max_depth,
        max_per_node=max_per_node,
        has_more_up=max_depth > max_up,
        has_more_down=max_depth > max_down,
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


def _order_search(query_like: str, query_norm: str) -> str:
    # Ordenação simples e eficiente para operação.
    return (
        "CASE WHEN LOWER(COALESCE(entidade_id, '')) = :q_eq THEN 0 ELSE 1 END, "
        "CASE WHEN LOWER(COALESCE(cpf_cnpj, '')) = :q_eq THEN 1 ELSE 2 END, "
        "LOWER(COALESCE(nome_canonico, '')) LIKE :q_like DESC, "
        "nome_canonico ASC"
    )


@app.get("/api/entities/search", response_model=SearchResponse)
def search_entities(
    q: str = "",
    limit: int = Query(default=12, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    tipo: str | None = None,
    include_external: bool = True,
    only_active: bool = False,
) -> SearchResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            query = (q or "").strip()
            query_norm = query.lower()
            query_like = f"%{query_norm}%"

            where = ["1 = 1"]
            params: dict[str, Any] = {
                "limit": limit,
                "offset": offset,
                "q_like": query_like,
                "q_eq": query_norm,
            }

            if query_norm:
                where.append(
                    "(" +
                    "LOWER(COALESCE(cpf_cnpj, '')) LIKE :q_like OR "
                    "LOWER(COALESCE(entidade_id, '')) LIKE :q_like OR "
                    "LOWER(COALESCE(nome_canonico, '')) LIKE :q_like OR "
                    "LOWER(COALESCE(nome_original, '')) LIKE :q_like" +
                    ")"
                )

            if tipo:
                where.append("tipo_entidade = :tipo")
                params["tipo"] = tipo

            if not include_external:
                where.append("tipo_entidade NOT LIKE '%EXTERNA%'")

            if only_active:
                where.append("status_entidade = 'ATIVO'")

            where_sql = " WHERE " + " AND ".join(where)
            order_expr = (
                "CASE WHEN LOWER(COALESCE(cpf_cnpj, '')) = :q_eq THEN 0 ELSE 1 END, "
                "CASE WHEN LOWER(COALESCE(nome_canonico, '')) LIKE :q_like THEN 0 ELSE 1 END, "
                "nome_canonico ASC"
            )

            order_clause = ", ".join(order_expr)

            total = conn.execute(f"SELECT COUNT(*) AS total FROM entidades{where_sql}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM entidades{where_sql} ORDER BY {order_clause} LIMIT :limit OFFSET :offset",
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
            score=96 if row["entidade_id"] == q else (90 if str(row["cpf_cnpj"]).lower() == query_norm and query else 75),
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
                requer_revisao=(str(row["requer_revisao"]).lower() == "true"),
                confianca_grupo=row["confianca_grupo"] or "",
            )
            for row in groups
        ],
    )


@app.get("/api/tree/family/{entidade_id}")
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
            scope_types = parse_scope("family")
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
    norm_direction = (direction or "all").lower()
    if norm_direction not in {"all", "up", "down"}:
        raise HTTPException(status_code=400, detail="direction deve ser all, up ou down")

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
                direction=norm_direction,
            )
    finally:
        conn.close()


@app.exception_handler(HTTPException)
def http_exception_handler(_: Any, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
