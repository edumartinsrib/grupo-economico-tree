from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import sqlite3
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "resultados" / "grafo_resultado.sqlite"


app = FastAPI(
    title="Grupo Econômico Tree API",
    version="2.1.0",
    description="Consulta sob demanda para rede de entidades, vínculos e grupos.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


RELATION_LABEL = {
    "FILHO_DE": "pai ou mãe",
    "PAI_DE": "filho(a)",
    "MAE_DE": "filho(a)",
    "IRMAO_DE": "irmão(a)",
    "CONJUGE_DE": "cônjuge",
    "CONJUGE_NOME_CANDIDATO": "cônjuge candidato(a)",
    "SOCIO_DE": "sócio",
    "CONTROLADOR_DIRETO": "controlador",
    "CONTROLADOR_CONJUNTO_CANDIDATO": "controle conjunto",
    "INFLUENCIA_RELEVANTE": "sócio com influência",
    "SOCIO_MINORITARIO": "sócio minoritário",
    "TRANSFERIU_PARA": "fluxo financeiro",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA": "dependência econômica",
    "ENDERECO_COMPARTILHADO": "mesmo endereço",
    "CONTATO_COMPARTILHADO": "contato compartilhado",
    "EMPREGADO_DE": "emprego",
    "TIO_TIA_DE": "tio(a)/irmao(a)",
    "ESPOLIO_DE": "espólio",
    "PARENTESCO_AMBIGUO": "parentesco em análise",
    "POSSIVEL_MESMO_GENITOR": "parentesco em análise",
    "PARTICIPACAO_INDIRETA": "participação indireta",
}

WEAK_HINT_RELATIONS = {
    "ENDERECO_COMPARTILHADO",
    "CONTATO_COMPARTILHADO",
    "TRANSFERIU_PARA",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA",
    "PARENTESCO_AMBIGUO",
    "POSSIVEL_MESMO_GENITOR",
}


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
    relevancia: int
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
    tipo_descritivo: str
    relation_direction: str
    relation_depth_delta: int
    confianca_vinculo: float
    relevancia_familiar: float
    relevancia_societaria: float
    relevancia_regulatoria: float
    data_observacao: str
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
    link_relevance_hint: int


class TreeResponse(BaseModel):
    root_id: str
    max_depth: int
    include_indirect: bool
    nodes: list[EntityNode]
    relations: list[RelationItem]
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
    other: str
    link_id: str
    tipo_vinculo: str
    source_id: str
    target_id: str
    depth_delta: int
    confianca: float
    relevancia_familiar: float
    relevancia_societaria: float
    relevancia_regulatoria: float
    data_observacao: str
    requer_revisao: bool



def relation_depth_delta(tipo: str, source_is_current: bool) -> int:
    if tipo == "FILHO_DE":
        return -1 if source_is_current else 1
    if tipo in {"PAI_DE", "MAE_DE"}:
        return 1 if source_is_current else -1
    return 0


def relation_direction(tipo: str, source_is_current: bool) -> str:
    if tipo == "FILHO_DE":
        return "pai/mãe" if source_is_current else "filho(a)"
    if tipo in {"PAI_DE", "MAE_DE"}:
        return "filho(a)" if source_is_current else "pai/mãe"
    return RELATION_LABEL.get(tipo, tipo.replace("_", " "))


def relation_is_weak(row: sqlite3.Row, include_indirect: bool) -> bool:
    if include_indirect:
        return False

    if row["requer_revisao"] == "true":
        return True

    if row["tipo_vinculo"] in WEAK_HINT_RELATIONS:
        return True

    return False


def safe_float(value: str | int | float | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Banco não encontrado: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_neighbors(conn: sqlite3.Connection, entity_id: str, include_indirect: bool) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM vinculos WHERE entidade_origem = ? OR entidade_destino = ?",
        (entity_id, entity_id),
    ).fetchall()
    if include_indirect:
        return rows
    return [row for row in rows if not relation_is_weak(row, include_indirect=False)]


def get_entity(conn: sqlite3.Connection, entity_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (entity_id,)).fetchone()


def ensure_indexes(conn: sqlite3.Connection) -> None:
    ddl = [
        "CREATE INDEX IF NOT EXISTS idx_entidades_id ON entidades (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_tipo ON entidades (tipo_entidade)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome ON entidades (nome_canonico)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_origem ON vinculos (entidade_origem)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_destino ON vinculos (entidade_destino)",
        "CREATE INDEX IF NOT EXISTS idx_membro_ent ON membros_grupo (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_membro_grp ON membros_grupo (grupo_id)",
    ]
    for ddl_stmt in ddl:
        conn.execute(ddl_stmt)
    conn.commit()


def iter_neighbor_rows(conn: sqlite3.Connection, entity_id: str, include_indirect: bool) -> Iterator[Neighbor]:
    for row in get_neighbors(conn, entity_id, include_indirect):
        source = row["entidade_origem"]
        target = row["entidade_destino"]
        source_is_current = source == entity_id
        other = target if source_is_current else source
        yield Neighbor(
            other=other,
            link_id=row["vinculo_id"],
            tipo_vinculo=row["tipo_vinculo"],
            source_id=source,
            target_id=target,
            depth_delta=relation_depth_delta(row["tipo_vinculo"], source_is_current),
            confianca=safe_float(row["confianca_vinculo"]),
            relevancia_familiar=safe_float(row["relevancia_familiar"]),
            relevancia_societaria=safe_float(row["relevancia_societaria"]),
            relevancia_regulatoria=safe_float(row["relevancia_regulatoria"]),
            data_observacao=row["data_observacao"] or "",
            requer_revisao=row["requer_revisao"] == "true",
        )


def relevance_hint_from_node(row: sqlite3.Row, depth: int) -> int:
    base = 90 if row["status_entidade"] == "ATIVO" else 75
    if row["documento_valido"] == "false":
        base -= 20
    if depth != 0:
        base = max(40, base - abs(depth) * 10)
    return base


def build_tree_payload(
    conn: sqlite3.Connection,
    root_id: str,
    max_depth: int,
    max_per_node: int,
    include_indirect: bool,
) -> TreeResponse:
    if max_per_node <= 0:
        raise HTTPException(status_code=400, detail="max_per_node precisa ser positivo")

    total_links_seen: dict[str, int] = {}
    node_depth: dict[str, int] = {root_id: 0}
    queue = deque([root_id])

    nodes_to_load: set[str] = {root_id}
    relation_map: dict[tuple[str, str], tuple[str, Neighbor]] = {}

    while queue:
        current_id = queue.popleft()
        current_depth = node_depth[current_id]

        if abs(current_depth) > max_depth:
            continue

        raw_neighbors = list(iter_neighbor_rows(conn, current_id, include_indirect))
        total_links_seen[current_id] = len(raw_neighbors)

        visible_neighbors = raw_neighbors[:max_per_node]

        for neigh in visible_neighbors:
            if neigh.other not in total_links_seen:
                pass

            next_depth = current_depth + neigh.depth_delta
            if abs(next_depth) > max_depth:
                continue

            # evita duplicidade de arestas
            key = (neigh.source_id, neigh.target_id, neigh.link_id)
            if key not in relation_map:
                relation_map[key] = (current_id, neigh)

            if neigh.other not in node_depth or abs(next_depth) < abs(node_depth[neigh.other]):
                node_depth[neigh.other] = next_depth

            if neigh.other not in nodes_to_load:
                nodes_to_load.add(neigh.other)
                queue.append(neigh.other)

    nodes_payload: list[EntityNode] = []
    for node_id, depth in sorted(node_depth.items(), key=lambda item: (abs(item[1]), item[0])):
        row = get_entity(conn, node_id)
        if not row:
            continue

        total = total_links_seen.get(node_id, 0)
        # total neighbors from DB (sem recorte) para saber o que ficou oculto
        visible = min(total, max_per_node)

        nodes_payload.append(
            EntityNode(
                id=node_id,
                nome=row["nome_canonico"] or row["nome_original"] or node_id,
                cpf_cnpj=row["cpf_cnpj"],
                tipo_entidade=row["tipo_entidade"],
                status_entidade=row["status_entidade"],
                data_nascimento=row["data_nascimento"] or "",
                data_obito=row["data_obito"] or "",
                documento_valido=row["documento_valido"] or "false",
                alerta=row["alertas"] or "",
                depth=depth,
                total_vizinhos=total,
                hidden_vizinhos=max(0, total - visible),
                link_relevance_hint=relevance_hint_from_node(row, depth),
            )
        )

    relations_payload: list[RelationItem] = []
    seen_edges = set[str]()
    for (_, _), (_anchor, neigh) in relation_map.items():
        source_is_current = neigh.source_id == _anchor
        direction = relation_direction(neigh.tipo_vinculo, source_is_current)
        rel_delta = neigh.depth_delta
        edge_key = f"{neigh.link_id}:{neigh.source_id}:{neigh.target_id}"
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        relations_payload.append(
            RelationItem(
                id=neigh.link_id,
                source=neigh.source_id,
                target=neigh.target_id,
                tipo_vinculo=neigh.tipo_vinculo,
                tipo_descritivo=RELATION_LABEL.get(neigh.tipo_vinculo, neigh.tipo_vinculo.replace("_", " ")),
                relation_direction=direction,
                relation_depth_delta=rel_delta,
                confianca_vinculo=neigh.confianca,
                relevancia_familiar=neigh.relevancia_familiar,
                relevancia_societaria=neigh.relevancia_societaria,
                relevancia_regulatoria=neigh.relevancia_regulatoria,
                data_observacao=neigh.data_observacao,
                requer_revisao=neigh.requer_revisao,
            )
        )

    summary = {
        "total_nodos": len(nodes_payload),
        "total_relacoes": len(relations_payload),
        "max_depth_atingido": max((abs(node.depth) for node in nodes_payload), default=0),
    }

    return TreeResponse(
        root_id=root_id,
        max_depth=max_depth,
        include_indirect=include_indirect,
        nodes=nodes_payload,
        relations=relations_payload,
        summary=summary,
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        db_status="disponivel" if DB_PATH.exists() else "ausente",
    )


@app.get("/api/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            total_entidades = conn.execute("SELECT COUNT(*) AS total FROM entidades").fetchone()[0]
            total_vinculos = conn.execute("SELECT COUNT(*) AS total FROM vinculos").fetchone()[0]
            total_grupos = conn.execute("SELECT COUNT(*) AS total FROM grupos").fetchone()[0]
            total_revisao = conn.execute("SELECT COUNT(*) AS total FROM fila_revisao").fetchone()[0]
            dist = conn.execute("SELECT tipo_entidade, COUNT(*) AS total FROM entidades GROUP BY tipo_entidade").fetchall()
            tipos = {row["tipo_entidade"]: int(row["total"]) for row in dist}
    finally:
        conn.close()

    return MetadataResponse(
        total_entidades=int(total_entidades),
        total_vinculos=int(total_vinculos),
        total_grupos=int(total_grupos),
        total_revisao=int(total_revisao),
        total_pessoas=int(tipos.get("PF", 0)) + int(tipos.get("PF_EXTERNA", 0)),
        total_empresas=int(tipos.get("PJ", 0)) + int(tipos.get("PJ_EXTERNA", 0)),
        tipo_entidade=tipos,
    )


@app.get("/api/entities/search", response_model=SearchResponse)
def search_entities(
    q: str = "",
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    tipo: str | None = None,
    include_external: bool = True,
) -> SearchResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            normalized = (q or "").strip().lower()

            conditions = ["1 = 1"]
            params: list[Any] = []

            if normalized:
                like = f"%{normalized}%"
                conditions.append(
                    "(LOWER(COALESCE(nome_canonico, '')) LIKE ? OR LOWER(COALESCE(nome_original, '')) LIKE ? OR LOWER(COALESCE(cpf_cnpj, '')) LIKE ? OR LOWER(entidade_id) LIKE ?)")
                params.extend([like, like, like, like])

            if tipo:
                conditions.append("tipo_entidade = ?")
                params.append(tipo)

            if not include_external:
                conditions.append("tipo_entidade NOT LIKE '%EXTERNA%'")

            where = " WHERE " + " AND ".join(conditions)
            count = conn.execute(f"SELECT COUNT(*) AS total FROM entidades{where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM entidades{where} ORDER BY nome_canonico LIMIT ? OFFSET ?",
                [*params, limit, offset],
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
            relevancia=90 if row["documento_valido"] == "true" else 50,
            motivo="registro com documento válido" if row["documento_valido"] == "true" else "confirmação documental recomendada",
        )
        for row in rows
    ]

    return SearchResponse(query=q, total=int(count), limit=limit, offset=offset, items=items)


@app.get("/api/entities/{entidade_id}", response_model=EntityDetailResponse)
def entity_detail(entidade_id: str) -> EntityDetailResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            entity = get_entity(conn, entidade_id)
            if not entity:
                raise HTTPException(status_code=404, detail="Entidade não encontrada")

            links_count = conn.execute(
                "SELECT COUNT(*) AS total FROM vinculos WHERE entidade_origem = ? OR entidade_destino = ?",
                (entidade_id, entidade_id),
            ).fetchone()[0]

            links_by_type = conn.execute(
                """
                SELECT tipo_vinculo, COUNT(*) AS total
                FROM vinculos
                WHERE entidade_origem = ? OR entidade_destino = ?
                GROUP BY tipo_vinculo
                ORDER BY total DESC
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

            total_groups = conn.execute(
                "SELECT COUNT(DISTINCT grupo_id) AS total FROM membros_grupo WHERE entidade_id = ?",
                (entidade_id,),
            ).fetchone()[0]
    finally:
        conn.close()

    return EntityDetailResponse(
        entidade_id=entity["entidade_id"],
        tipo_entidade=entity["tipo_entidade"],
        nome_canonico=entity["nome_canonico"],
        nome_original=entity["nome_original"],
        cpf_cnpj=entity["cpf_cnpj"],
        status_entidade=entity["status_entidade"],
        documento_valido=entity["documento_valido"],
        data_nascimento=entity["data_nascimento"] or "",
        data_obito=entity["data_obito"] or "",
        fonte_principal=entity["fonte_principal"],
        data_atualizacao=entity["data_atualizacao"] or "",
        alertas=entity["alertas"] or "",
        graus_conexao=links_count,
        total_vinculos=links_count,
        total_grupos=int(total_groups),
        conexoes_por_tipo={row["tipo_vinculo"]: int(row["total"]) for row in links_by_type},
        grupos=[
            GroupItem(
                grupo_id=row["grupo_id"],
                tipo_grupo=row["tipo_grupo"],
                nome_grupo=row["nome_grupo"],
                status_grupo=row["status_grupo"],
                grupo_regulatorio=row["grupo_regulatorio"],
                requer_revisao=(row["requer_revisao"] == "true"),
                confianca_grupo=row["confianca_grupo"],
            )
            for row in groups
        ],
    )


@app.get("/api/tree/entity/{entidade_id}", response_model=TreeResponse)
def tree_from_entity(
    entidade_id: str,
    max_depth: int = Query(default=2, ge=1, le=8),
    include_indirect: bool = False,
    max_per_node: int = Query(default=10, ge=1, le=60),
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            if not get_entity(conn, entidade_id):
                raise HTTPException(status_code=404, detail="Entidade não localizada")
            return build_tree_payload(
                conn,
                root_id=entidade_id,
                max_depth=max_depth,
                max_per_node=max_per_node,
                include_indirect=include_indirect,
            )
    finally:
        conn.close()


@app.get("/api/tree/branch/{entidade_id}", response_model=TreeResponse)
def tree_branch(
    entidade_id: str,
    max_depth: int = Query(default=1, ge=1, le=4),
    include_indirect: bool = False,
    max_per_node: int = Query(default=10, ge=1, le=60),
) -> TreeResponse:
    return tree_from_entity(entidade_id, max_depth=max_depth, include_indirect=include_indirect, max_per_node=max_per_node)


@app.exception_handler(HTTPException)
def http_exception_handler(_: Any, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
