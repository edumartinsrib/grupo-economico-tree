from __future__ import annotations

from collections import deque
from dataclasses import dataclass
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
    version="3.0.0",
    description="API sob demanda para consulta de rede familiar e societária.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


FAMILY_RELATIONS = {
    "FILHO_DE",
    "PAI_DE",
    "MAE_DE",
    "IRMAO_DE",
    "CONJUGE_DE",
    "CONJUGE_NOME_CANDIDATO",
    "PARENTESCO_AMBIGUO",
    "POSSIVEL_MESMO_GENITOR",
}

SOFT_RELATIONS = {
    "ENDERECO_COMPARTILHADO",
    "CONTATO_COMPARTILHADO",
}

SOCIAL_RELATIONS = {
    "CONJUGE_DE",
    "CONJUGE_NOME_CANDIDATO",
    "IRMAO_DE",
}

BUSINESS_RELATIONS = {
    "SOCIO_DE",
    "CONTROLADOR_DIRETO",
    "CONTROLADOR_CONJUNTO_CANDIDATO",
    "INFLUENCIA_RELEVANTE",
    "SOCIO_MINORITARIO",
    "SOCIO_COTISTA",
    "PARTICIPACAO_INDIRETA",
}

FINANCIAL_RELATIONS = {
    "TRANSFERIU_PARA",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA",
    "DEPENDENCIA_FINANCEIRA_CONFIRMADA",
}

RELATION_LABEL = {
    "FILHO_DE": "pai/mãe",
    "PAI_DE": "filho(a)",
    "MAE_DE": "filho(a)",
    "IRMAO_DE": "irmão(a)",
    "CONJUGE_DE": "cônjuge",
    "CONJUGE_NOME_CANDIDATO": "cônjuge (candidato)",
    "SOCIO_DE": "sócio",
    "CONTROLADOR_DIRETO": "controle total",
    "CONTROLADOR_CONJUNTO_CANDIDATO": "controle conjunto",
    "INFLUENCIA_RELEVANTE": "sócio influente",
    "SOCIO_MINORITARIO": "sócio minoritário",
    "PARTICIPACAO_INDIRETA": "participação indireta",
    "ENDERECO_COMPARTILHADO": "endereço compartilhado",
    "CONTATO_COMPARTILHADO": "contato compartilhado",
    "EMPREGADO_DE": "emprego",
    "TIO_TIA_DE": "tio/tia",
    "ESPOLIO_DE": "espólio",
    "PARENTESCO_AMBIGUO": "parentesco em revisão",
    "POSSIVEL_MESMO_GENITOR": "parentesco em revisão",
    "TRANSFERIU_PARA": "transferência",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA": "dependência sugerida",
}

WEAK_HINT_RELATIONS = {
    "ENDERECO_COMPARTILHADO",
    "CONTATO_COMPARTILHADO",
    "TRANSFERIU_PARA",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA",
    "PARENTESCO_AMBIGUO",
    "POSSIVEL_MESMO_GENITOR",
}

MAX_NODE_LIMIT = 900


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
    max_asc: int
    max_desc: int
    relation_scope: str
    include_indirect: bool
    nodes: list[EntityNode]
    relations: list[RelationItem]
    has_more_up: bool = False
    has_more_down: bool = False
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



def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0



def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default



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
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome ON entidades (nome_canonico)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_nome_original ON entidades (nome_original)",
        "CREATE INDEX IF NOT EXISTS idx_entidades_cpf ON entidades (cpf_cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_origem_tipo ON vinculos (entidade_origem, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_destino_tipo ON vinculos (entidade_destino, tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_tipo ON vinculos (tipo_vinculo)",
        "CREATE INDEX IF NOT EXISTS idx_vinc_revisao ON vinculos (requer_revisao)",
        "CREATE INDEX IF NOT EXISTS idx_membro_ent ON membros_grupo (entidade_id)",
        "CREATE INDEX IF NOT EXISTS idx_membro_grp ON membros_grupo (grupo_id)",
    ]
    for ddl_stmt in ddl:
        conn.execute(ddl_stmt)



def normalize_relation_scope(scope: str | None) -> list[str]:
    if not scope:
        return ["family"]

    requested = [item.strip().lower() for item in str(scope).split(",") if item.strip()]
    resolved: set[str] = set()

    for item in requested:
        if item in {"all", "*", "completo"}:
            return ["family", "business", "financial", "other", "soft"]

        if item in {"family", "familiar"}:
            resolved.add("family")
        elif item in {"business", "societario", "societária", "societario"}:
            resolved.add("business")
        elif item in {"financial", "financeiro", "financeiro"}:
            resolved.add("financial")
        elif item in {"soft", "fraco", "r"}:
            resolved.add("soft")
        elif item == "other":
            resolved.add("other")

    if not resolved:
        resolved = {"family"}

    return sorted(resolved)



def allowed_relations(scope_parts: list[str], include_all_types: bool) -> list[str]:
    if include_all_types:
        rows = FAMILY_RELATIONS | BUSINESS_RELATIONS | FINANCIAL_RELATIONS | SOFT_RELATIONS | {"EMPREGADO_DE", "TIO_TIA_DE", "ESPOLIO_DE", "SOCIO_COTISTA", "CONTROLADOR_DIRETO", "CONTROLADOR_CONJUNTO_CANDIDATO", "INFLUENCIA_RELEVANTE", "SOCIO_MINORITARIO", "PARTICIPACAO_INDIRETA"}
        return sorted(rows)

    relation_types: set[str] = set()
    for scope in scope_parts:
        if scope == "family":
            relation_types |= FAMILY_RELATIONS | {"CONJUGE_DE", "IRMAO_DE", "TIO_TIA_DE"}
        elif scope == "business":
            relation_types |= BUSINESS_RELATIONS
        elif scope == "financial":
            relation_types |= FINANCIAL_RELATIONS
        elif scope == "soft":
            relation_types |= SOFT_RELATIONS

    return sorted(relation_types)



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
    if tipo in {"CONJUGE_DE", "CONJUGE_NOME_CANDIDATO"}:
        return "cônjuge"
    return RELATION_LABEL.get(tipo, tipo.replace("_", " "))



def relation_is_weak(row: sqlite3.Row, include_indirect: bool) -> bool:
    if include_indirect:
        return False

    if row["requer_revisao"] == "true":
        return True

    if row["tipo_vinculo"] in WEAK_HINT_RELATIONS:
        return True

    return False



def get_entity(conn: sqlite3.Connection, entidade_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (entidade_id,)).fetchone()



def count_neighbors(conn: sqlite3.Connection, entidade_id: str, relation_types: list[str], include_indirect: bool) -> int:
    if relation_types:
        placeholders = ",".join("?" * len(relation_types))
        params = relation_types + [entidade_id, entidade_id]
        query = f"SELECT COUNT(*) AS total FROM vinculos WHERE tipo_vinculo IN ({placeholders}) AND (entidade_origem = ? OR entidade_destino = ?)"
    else:
        query = "SELECT COUNT(*) AS total FROM vinculos WHERE entidade_origem = ? OR entidade_destino = ?"
        params = [entidade_id, entidade_id]

    if not include_indirect:
        query += " AND requer_revisao <> 'true'"

    return safe_int(conn.execute(query, params).fetchone()[0])



def iter_neighbors(
    conn: sqlite3.Connection,
    entidade_id: str,
    include_indirect: bool,
    relation_types: list[str],
    max_per_node: int,
) -> list[Neighbor]:
    if relation_types:
        placeholders = ",".join("?" * len(relation_types))
        query = f"""
        SELECT *
        FROM vinculos
        WHERE (entidade_origem = ? OR entidade_destino = ?)
          AND tipo_vinculo IN ({placeholders})
        ORDER BY CASE WHEN CAST(requer_revisao AS TEXT)='true' THEN 0 ELSE 1 END DESC,
                 CAST(COALESCE(confianca_vinculo, '0') AS REAL) DESC,
                 vinculo_id ASC
        """
        params: list[Any] = [entidade_id, entidade_id, *relation_types]
    else:
        query = """
        SELECT *
        FROM vinculos
        WHERE entidade_origem = ? OR entidade_destino = ?
        ORDER BY CAST(COALESCE(confianca_vinculo, '0') AS REAL) DESC,
                 vinculo_id ASC
        """
        params = [entidade_id, entidade_id]

    if not include_indirect:
        query += " AND requer_revisao <> 'true'"

    rows = conn.execute(query, params).fetchall()
    result: list[Neighbor] = []

    for row in rows[:max_per_node]:
        if not include_indirect and relation_is_weak(row, include_indirect=False):
            continue

        source = row["entidade_origem"]
        target = row["entidade_destino"]
        source_is_current = source == entidade_id
        other = target if source_is_current else source

        result.append(
            Neighbor(
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
        )

    return result



def relevance_hint(row: sqlite3.Row, depth: int) -> int:
    base = 90 if row["status_entidade"] == "ATIVO" else 75
    if row["documento_valido"] == "false":
        base -= 18
    return max(20, base - abs(depth) * 8)



def build_tree_payload(
    conn: sqlite3.Connection,
    root_id: str,
    max_asc: int,
    max_desc: int,
    max_per_node: int,
    include_indirect: bool,
    relation_types: list[str],
) -> TreeResponse:
    if max_asc < 0 or max_desc < 0:
        raise HTTPException(status_code=400, detail="max_asc e max_desc precisam ser >= 0")

    if max_per_node <= 0:
        raise HTTPException(status_code=400, detail="max_per_node precisa ser positivo")

    if not get_entity(conn, root_id):
        raise HTTPException(status_code=404, detail="Entidade não localizada")

    max_node_reached = 1
    nodes_depth: dict[str, int] = {root_id: 0}
    relation_map: dict[tuple[str, str, str], RelationItem] = {}
    nodes_to_load: set[str] = {root_id}

    # BFS em camadas separadas: pais (profundidade negativa) e filhos (profundidade positiva).
    up_frontier = [root_id]
    for depth in range(1, max_asc + 1):
        target_depth = -depth
        next_frontier: list[str] = []

        for current in up_frontier:
            if current not in nodes_to_load:
                continue

            current_depth = nodes_depth[current]
            if current_depth < 0:
                continue

            for neigh in iter_neighbors(conn, current, include_indirect, relation_types, max_per_node):
                if max_node_reached >= MAX_NODE_LIMIT:
                    break

                if neigh.depth_delta != -1:
                    continue

                next_depth = current_depth - 1
                if next_depth != target_depth:
                    continue

                edge_key = (neigh.link_id, neigh.source_id, neigh.target_id)
                if edge_key not in relation_map:
                    relation_map[edge_key] = RelationItem(
                        id=neigh.link_id,
                        source=neigh.source_id,
                        target=neigh.target_id,
                        tipo_vinculo=neigh.tipo_vinculo,
                        tipo_descritivo=RELATION_LABEL.get(neigh.tipo_vinculo, neigh.tipo_vinculo.replace("_", " ")),
                        relation_direction=relation_direction(neigh.tipo_vinculo, neigh.source_id == current),
                        relation_depth_delta=neigh.depth_delta,
                        confianca_vinculo=neigh.confianca,
                        relevancia_familiar=neigh.relevancia_familiar,
                        relevancia_societaria=neigh.relevancia_societaria,
                        relevancia_regulatoria=neigh.relevancia_regulatoria,
                        data_observacao=neigh.data_observacao,
                        requer_revisao=neigh.requer_revisao,
                    )

                if neigh.other not in nodes_depth or abs(nodes_depth[neigh.other]) > abs(next_depth):
                    nodes_depth[neigh.other] = next_depth
                    if neigh.other not in nodes_to_load:
                        nodes_to_load.add(neigh.other)
                        next_frontier.append(neigh.other)
                        max_node_reached += 1

                if max_node_reached >= MAX_NODE_LIMIT:
                    break

        up_frontier = next_frontier

    down_frontier = [root_id]
    for depth in range(1, max_desc + 1):
        target_depth = depth
        next_frontier: list[str] = []

        for current in down_frontier:
            if current not in nodes_to_load:
                continue

            current_depth = nodes_depth[current]
            if current_depth > 0:
                continue

            for neigh in iter_neighbors(conn, current, include_indirect, relation_types, max_per_node):
                if max_node_reached >= MAX_NODE_LIMIT:
                    break

                if neigh.depth_delta != 1:
                    continue

                next_depth = current_depth + 1
                if next_depth != target_depth:
                    continue

                edge_key = (neigh.link_id, neigh.source_id, neigh.target_id)
                if edge_key not in relation_map:
                    relation_map[edge_key] = RelationItem(
                        id=neigh.link_id,
                        source=neigh.source_id,
                        target=neigh.target_id,
                        tipo_vinculo=neigh.tipo_vinculo,
                        tipo_descritivo=RELATION_LABEL.get(neigh.tipo_vinculo, neigh.tipo_vinculo.replace("_", " ")),
                        relation_direction=relation_direction(neigh.tipo_vinculo, neigh.source_id == current),
                        relation_depth_delta=neigh.depth_delta,
                        confianca_vinculo=neigh.confianca,
                        relevancia_familiar=neigh.relevancia_familiar,
                        relevancia_societaria=neigh.relevancia_societaria,
                        relevancia_regulatoria=neigh.relevancia_regulatoria,
                        data_observacao=neigh.data_observacao,
                        requer_revisao=neigh.requer_revisao,
                    )

                if neigh.other not in nodes_depth or abs(nodes_depth[neigh.other]) > abs(next_depth):
                    nodes_depth[neigh.other] = next_depth
                    if neigh.other not in nodes_to_load:
                        nodes_to_load.add(neigh.other)
                        next_frontier.append(neigh.other)
                        max_node_reached += 1

                if max_node_reached >= MAX_NODE_LIMIT:
                    break

        down_frontier = next_frontier

    # Expansão lateral (filhos/irmãos/conjugues no mesmo nível) sem abrir novas profundidades.
    for node_id, depth in list(nodes_depth.items()):
        if max_node_reached >= MAX_NODE_LIMIT:
            break

        if depth == 0:
            continue

        for neigh in iter_neighbors(conn, node_id, include_indirect, relation_types, max_per_node):
            if neigh.depth_delta != 0:
                continue

            edge_key = (neigh.link_id, neigh.source_id, neigh.target_id)
            if edge_key not in relation_map:
                relation_map[edge_key] = RelationItem(
                    id=neigh.link_id,
                    source=neigh.source_id,
                    target=neigh.target_id,
                    tipo_vinculo=neigh.tipo_vinculo,
                    tipo_descritivo=RELATION_LABEL.get(neigh.tipo_vinculo, neigh.tipo_vinculo.replace("_", " ")),
                    relation_direction=relation_direction(neigh.tipo_vinculo, neigh.source_id == node_id),
                    relation_depth_delta=neigh.depth_delta,
                    confianca_vinculo=neigh.confianca,
                    relevancia_familiar=neigh.relevancia_familiar,
                    relevancia_societaria=neigh.relevancia_societaria,
                    relevancia_regulatoria=neigh.relevancia_regulatoria,
                    data_observacao=neigh.data_observacao,
                    requer_revisao=neigh.requer_revisao,
                )

            if neigh.other not in nodes_depth and max_node_reached < MAX_NODE_LIMIT:
                nodes_depth[neigh.other] = depth
                nodes_to_load.add(neigh.other)
                max_node_reached += 1

    nodes_payload: list[EntityNode] = []
    total_links_seen: dict[str, int] = {}

    for node_id in nodes_depth:
        total_links_seen[node_id] = count_neighbors(conn, node_id, relation_types, include_indirect)

    # Ordena por nível e depois nome para layout estável.
    for node_id, depth in sorted(nodes_depth.items(), key=lambda item: (item[1], str(item[0]))):
        row = get_entity(conn, node_id)
        if not row:
            continue

        total = total_links_seen.get(node_id, 0)
        visible = min(total, max_per_node)

        nodes_payload.append(
            EntityNode(
                id=node_id,
                nome=row["nome_canonico"] or row["nome_original"] or node_id,
                cpf_cnpj=row["cpf_cnpj"] or "",
                tipo_entidade=row["tipo_entidade"],
                status_entidade=row["status_entidade"],
                data_nascimento=row["data_nascimento"] or "",
                data_obito=row["data_obito"] or "",
                documento_valido=row["documento_valido"] or "false",
                alerta=row["alertas"] or "",
                depth=depth,
                total_vizinhos=total,
                hidden_vizinhos=max(0, total - visible),
                link_relevance_hint=relevance_hint(row, depth),
            )
        )

    reached_depth = {"asc": 0, "desc": 0}
    for depth in nodes_depth.values():
        if depth < 0:
            reached_depth["asc"] = max(reached_depth["asc"], abs(depth))
        elif depth > 0:
            reached_depth["desc"] = max(reached_depth["desc"], depth)

    return TreeResponse(
        root_id=root_id,
        max_asc=max_asc,
        max_desc=max_desc,
        relation_scope=",".join(list(relation_types)) if relation_types else "all",
        include_indirect=include_indirect,
        nodes=nodes_payload,
        relations=list(relation_map.values()),
        has_more_up=reached_depth["asc"] < max_asc,
        has_more_down=reached_depth["desc"] < max_desc,
        summary={
            "total_nodos": len(nodes_payload),
            "total_relacoes": len(relation_map),
            "max_prof": reached_depth["asc"] + reached_depth["desc"],
        },
    )



def search_order_case(q_raw: str, q_like: str) -> list[str]:
    if not q_raw:
        return ["nome_canonico", "entidade_id"]

    q_clean = q_raw.strip().lower()
    return [
        f"CASE WHEN LOWER(COALESCE(cpf_cnpj, '')) = '{q_clean}' THEN 0 ELSE 1 END",
        f"CASE WHEN LOWER(COALESCE(nome_canonico, '')) LIKE '{q_like}' THEN 0 ELSE 1 END",
        f"CASE WHEN LOWER(COALESCE(nome_original, '')) LIKE '{q_like}' THEN 0 ELSE 1 END",
        "1",
    ]


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", db_status="disponivel" if DB_PATH.exists() else "ausente")


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
    limit: int = Query(default=20, ge=1, le=60),
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
            like_pattern = f"%{query_norm}%"

            where = ["1 = 1"]
            params: list[Any] = []

            if query_norm:
                where.append(
                    "(" +
                    "LOWER(COALESCE(cpf_cnpj, '')) LIKE ? OR "
                    "LOWER(COALESCE(entidade_id, '')) LIKE ? OR "
                    "LOWER(COALESCE(nome_canonico, '')) LIKE ? OR "
                    "LOWER(COALESCE(nome_original, '')) LIKE ?" +
                    ")"
                )
                params.extend([like_pattern, like_pattern, like_pattern, like_pattern])

            if tipo:
                where.append("tipo_entidade = ?")
                params.append(tipo)

            if not include_external:
                where.append("tipo_entidade NOT LIKE '%EXTERNA%'")

            if only_active:
                where.append("status_entidade = 'ATIVO'")

            where_sql = " WHERE " + " AND ".join(where)
            order_expr = ", ".join(search_order_case(query_norm, like_pattern))

            total = conn.execute(f"SELECT COUNT(*) AS total FROM entidades{where_sql}", params).fetchone()[0]

            rows = conn.execute(
                f"SELECT * FROM entidades{where_sql} "
                f"ORDER BY {order_expr}, nome_canonico LIMIT ? OFFSET ?",
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
            score=92 if row["documento_valido"] == "true" else 72,
            motivo="registro confirmado" if row["documento_valido"] == "true" else "confirmação recomendada",
        )
        for row in rows
    ]

    return SearchResponse(query=q, total=int(total), limit=limit, offset=offset, items=items)


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
        graus_conexao=int(links_count),
        total_vinculos=int(links_count),
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
                confianca_grupo=row["confianca_grupo"] or "",
            )
            for row in groups
        ],
    )


@app.get("/api/tree/entity/{entidade_id}", response_model=TreeResponse)
def tree_from_entity(
    entidade_id: str,
    max_depth: int = Query(default=3, ge=0, le=12),
    max_per_node: int = Query(default=10, ge=1, le=80),
    include_indirect: bool = False,
    relation_scope: str = "family",
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scope_parts = normalize_relation_scope(relation_scope)
            relation_types = allowed_relations(scope_parts, include_all_types=False)
            return build_tree_payload(
                conn=conn,
                root_id=entidade_id,
                max_asc=max_depth,
                max_desc=max_depth,
                max_per_node=max_per_node,
                include_indirect=include_indirect,
                relation_types=relation_types,
            )
    finally:
        conn.close()


@app.get("/api/tree/branch/{entidade_id}", response_model=TreeResponse)
def tree_branch(
    entidade_id: str,
    max_depth: int = Query(default=1, ge=0, le=8),
    max_per_node: int = Query(default=12, ge=1, le=80),
    include_indirect: bool = False,
    direction: str = "all",
    relation_scope: str = "family",
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scope_parts = normalize_relation_scope(relation_scope)
            relation_types = allowed_relations(scope_parts, include_all_types=False)
            up = max_depth if direction in {"all", "up", "parent", "parents", "ancestral", "cima"} else 0
            down = max_depth if direction in {"all", "down", "child", "children", "desc", "descend"} else 0

            return build_tree_payload(
                conn=conn,
                root_id=entidade_id,
                max_asc=up,
                max_desc=down,
                max_per_node=max_per_node,
                include_indirect=include_indirect,
                relation_types=relation_types,
            )
    finally:
        conn.close()


@app.exception_handler(HTTPException)
def http_exception_handler(_: Any, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
