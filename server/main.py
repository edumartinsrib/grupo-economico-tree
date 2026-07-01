from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Literal
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
    version="7.1.0",
    description="API sob demanda para consulta de vínculos com pessoas e empresas.",
)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_PREPARED = False


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    "PARENTESCO_AMBIGUO",
    "POSSIVEL_MESMO_GENITOR",
}

BUSINESS_RELATIONS = {
    "SOCIO_DE",
    "SOCIO_COTISTA",
    "CONTROLADOR_DIRETO",
    "CONTROLADOR_CONJUNTO_CANDIDATO",
    "INFLUENCIA_RELEVANTE",
    "SOCIO_MINORITARIO",
    "PARTICIPACAO_INDIRETA",
    "PERTENCE_A_GRUPO_EXISTENTE",
    "GRUPO_VINCULADO_POR_PESSOA",
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

RELATION_BY_SCOPE = {
    "family": sorted(FAMILY_RELATIONS),
    "business": sorted(BUSINESS_RELATIONS),
    "financial": sorted(FINANCIAL_RELATIONS),
    "other": sorted(OTHER_RELATIONS),
}
RELATION_BY_SCOPE["all"] = sorted(
    FAMILY_RELATIONS | BUSINESS_RELATIONS | FINANCIAL_RELATIONS | OTHER_RELATIONS
)

RELATION_LABEL = {
    "FILHO_DE": "Pai/Mãe",
    "PAI_DE": "Filho(a)",
    "MAE_DE": "Filho(a)",
    "IRMAO_DE": "Irmão(a)",
    "CONJUGE_DE": "Cônjuge",
    "CONJUGE_NOME_CANDIDATO": "Cônjuge (candidato)",
    "SOCIO_DE": "Sócio(a)",
    "SOCIO_COTISTA": "Sócio(a)",
    "CONTROLADOR_DIRETO": "Controlador(a)",
    "CONTROLADOR_CONJUNTO_CANDIDATO": "Controle conjunto",
    "INFLUENCIA_RELEVANTE": "Sócio(a) relevante",
    "SOCIO_MINORITARIO": "Sócio(a) minoritário(a)",
    "PARTICIPACAO_INDIRETA": "Sócio(a) indireto(a)",
    "PERTENCE_A_GRUPO_EXISTENTE": "Grupo econômico existente",
    "GRUPO_VINCULADO_POR_PESSOA": "Grupo vinculado",
    "ENDERECO_COMPARTILHADO": "Endereço compartilhado",
    "CONTATO_COMPARTILHADO": "Contato compartilhado",
    "EMPREGADO_DE": "Relação de emprego",
    "TIO_TIA_DE": "Tio(a)",
    "ESPOLIO_DE": "Espólio",
    "TRANSFERIU_PARA": "Fluxo financeiro",
    "DEPENDENCIA_FINANCEIRA_CANDIDATA": "Dependência financeira",
    "DEPENDENCIA_FINANCEIRA_CONFIRMADA": "Dependência financeira confirmada",
    "PARENTESCO_AMBIGUO": "Possível parentesco",
    "POSSIVEL_MESMO_GENITOR": "Possível mesmo genitor",
}


MAX_RESULTS = 120
MAX_LINKS_PER_REQUEST = 16


class HealthResponse(BaseModel):
    status: str
    db_status: str


class MetadataResponse(BaseModel):
    total_entidades: int
    total_vinculos: int
    total_grupos: int
    total_pessoas: int
    total_empresas: int
    total_revisao: int
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


class TreeNode(BaseModel):
    id: str
    nome: str
    cpf_cnpj: str
    tipo_entidade: str
    status_entidade: str
    data_nascimento: str
    data_obito: str
    documento_valido: str
    alerta: str
    nivel: int
    relacao_com_ancora: str
    total_vizinhos: int
    ocultos: int


class TreeRelation(BaseModel):
    id: str
    source: str
    target: str
    tipo_vinculo: str
    tipo_nome: str
    direcao_para_ancora: Literal["up", "down", "same"]
    confianca_vinculo: float
    requer_revisao: bool


class TreeResponse(BaseModel):
    anchor_id: str
    nodes: list[TreeNode]
    relations: list[TreeRelation]
    max_por_lote: int
    up_total: int
    down_total: int
    same_total: int
    next_up_offset: int
    next_down_offset: int
    next_same_offset: int
    has_more_up: bool
    has_more_down: bool
    has_more_same: bool


class GroupItem(BaseModel):
    grupo_id: str
    tipo_grupo: str
    nome_grupo: str
    status_grupo: str
    grupo_regulatorio: str
    requer_revisao: bool
    confianca_grupo: str
    papel_no_grupo: str = ""
    nivel_membro: str = ""
    justificativa_textual: str = ""


class GroupRelationItem(BaseModel):
    grupo_origem: str
    grupo_origem_nome: str
    grupo_origem_tipo: str
    grupo_destino: str
    grupo_destino_nome: str
    grupo_destino_tipo: str
    tipo_relacao: str
    entidade_ponte: str
    entidade_ponte_nome: str
    confianca: float
    relevancia: float
    evidencias: str
    data_referencia: str


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
    total_vizinhos: int
    total_grupos: int
    conexoes_por_tipo: dict[str, int]
    grupos: list[GroupItem]
    vinculos_grupos: list[GroupRelationItem]


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Banco não encontrado: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_text(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    cleaned = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return " ".join(cleaned.split())


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "sim", "yes", "y"}


def _like_escape(raw: str) -> str:
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def ensure_indexes(conn: sqlite3.Connection) -> None:
    global _SCHEMA_PREPARED
    if _SCHEMA_PREPARED:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_PREPARED:
            return

        ddl = [
            "CREATE INDEX IF NOT EXISTS idx_entidades_id ON entidades (entidade_id)",
            "CREATE INDEX IF NOT EXISTS idx_entidades_tipo ON entidades (tipo_entidade)",
            "CREATE INDEX IF NOT EXISTS idx_entidades_cpf ON entidades (cpf_cnpj)",
            "CREATE INDEX IF NOT EXISTS idx_entidades_status ON entidades (status_entidade)",
            "CREATE INDEX IF NOT EXISTS idx_entidades_data_atualizacao ON entidades (data_atualizacao)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_origem ON vinculos (entidade_origem)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_destino ON vinculos (entidade_destino)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_tipo_origem ON vinculos (tipo_vinculo, entidade_origem)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_tipo_destino ON vinculos (tipo_vinculo, entidade_destino)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_origem_tipo ON vinculos (entidade_origem, tipo_vinculo)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_destino_tipo ON vinculos (entidade_destino, tipo_vinculo)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_revisao ON vinculos (requer_revisao)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_revisao_tipo ON vinculos (requer_revisao, tipo_vinculo)",
            "CREATE INDEX IF NOT EXISTS idx_vinc_revisao_origem_destino ON vinculos (requer_revisao, entidade_origem, entidade_destino)",
            "CREATE INDEX IF NOT EXISTS idx_membros_entidade ON membros_grupo (entidade_id)",
            "CREATE INDEX IF NOT EXISTS idx_membros_grupo ON membros_grupo (grupo_id)",
            "CREATE INDEX IF NOT EXISTS idx_grupos_id ON grupos (grupo_id)",
            "CREATE INDEX IF NOT EXISTS idx_rel_grupo_origem ON relacoes_entre_grupos (grupo_origem)",
            "CREATE INDEX IF NOT EXISTS idx_rel_grupo_destino ON relacoes_entre_grupos (grupo_destino)",
            "CREATE INDEX IF NOT EXISTS idx_rel_grupo_ponte ON relacoes_entre_grupos (entidade_ponte)",
        ]
        for statement in ddl:
            conn.execute(statement)

        table_info = {row["name"] for row in conn.execute("PRAGMA table_info(entidades)").fetchall()}
        if "nome_canonico_normalizado" not in table_info:
            conn.execute("ALTER TABLE entidades ADD COLUMN nome_canonico_normalizado TEXT")
        if "nome_original_normalizado" not in table_info:
            conn.execute("ALTER TABLE entidades ADD COLUMN nome_original_normalizado TEXT")
        conn.commit()

        rows = conn.execute(
            "SELECT entidade_id, nome_canonico, nome_original FROM entidades "
            "WHERE nome_canonico_normalizado IS NULL OR nome_original_normalizado IS NULL"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE entidades SET nome_canonico_normalizado = ?, nome_original_normalizado = ? WHERE entidade_id = ?",
                (
                    normalize_text(row["nome_canonico"] or row["entidade_id"]),
                    normalize_text(row["nome_original"] or row["entidade_id"]),
                    row["entidade_id"],
                ),
            )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_entidades_nome_canonico_normalizado ON entidades (nome_canonico_normalizado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entidades_nome_original_normalizado ON entidades (nome_original_normalizado)")
        conn.commit()
        _SCHEMA_PREPARED = True


def _parse_scope(scope: str) -> list[str]:
    if not scope:
        return RELATION_BY_SCOPE["family"]

    result: set[str] = set()
    for token in scope.split(","):
        token = token.strip().lower()
        if not token:
            continue
        if token in {"all", "*", "completo"}:
            return RELATION_BY_SCOPE["all"]
        if token in RELATION_BY_SCOPE:
            result.update(RELATION_BY_SCOPE[token])
            continue

        token_upper = token.upper()
        known = RELATION_LABEL.get(token_upper)
        if known is not None:
            result.add(token_upper)

    if not result:
        return RELATION_BY_SCOPE["family"]
    return sorted(result)


def _anchor_label_for_direction(relation_type: str, direction: str) -> str:
    if relation_type == "CONJUGE_DE" or relation_type == "CONJUGE_NOME_CANDIDATO":
        return "cônjuge"

    if direction == "up":
        if relation_type == "FILHO_DE":
            return "pai/mãe"
        if relation_type == "PAI_DE":
            return "pai"
        if relation_type == "MAE_DE":
            return "mãe"
        return RELATION_LABEL.get(relation_type, relation_type.lower().replace("_", " "))

    if direction == "down":
        if relation_type in {"FILHO_DE", "PAI_DE", "MAE_DE"}:
            return "filho(a)"
        return RELATION_LABEL.get(relation_type, relation_type.lower().replace("_", " "))

    return RELATION_LABEL.get(relation_type, relation_type.lower().replace("_", " "))


def _build_entity_label(row: sqlite3.Row) -> str:
    return (row["nome_canonico"] or "").strip() or (row["nome_original"] or "").strip() or row["entidade_id"]


def _direction_sql(where_dir: str | None) -> str:
    if not where_dir:
        return ""
    if where_dir == "up":
        return "direction = 'up'"
    if where_dir == "down":
        return "direction = 'down'"
    return "direction = 'same'"


def _build_direction_neighbors_sql(include_weak: bool, direction_filter: str, relation_count: int) -> str:
    weak_clause = (
        ""
        if include_weak
        else "AND LOWER(COALESCE(requer_revisao, 'false')) NOT IN ('true','1','t','sim','yes','y')"
    )
    relation_clause = ",".join("?" for _ in range(relation_count))

    return f"""
      WITH directed AS (
        SELECT
          vinculo_id,
          entidade_origem AS fonte_origem,
          entidade_destino AS alvo_origem,
          entidade_origem AS source,
          entidade_destino AS target,
          tipo_vinculo,
          CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
          COALESCE(requer_revisao, 'false') AS requer_revisao,
          1 AS is_anchor_source,
          CASE
            WHEN tipo_vinculo = 'FILHO_DE' THEN 'up'
            WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 'down'
            WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 'same'
            WHEN tipo_vinculo = 'PERTENCE_A_GRUPO_EXISTENTE' THEN 'up'
            WHEN tipo_vinculo = 'GRUPO_VINCULADO_POR_PESSOA' THEN 'down'
            ELSE 'same'
          END AS direction
        FROM vinculos
        WHERE entidade_origem = ? AND tipo_vinculo IN ({relation_clause})

        UNION ALL

        SELECT
          vinculo_id,
          entidade_origem AS fonte_origem,
          entidade_destino AS alvo_origem,
          entidade_destino AS source,
          entidade_origem AS target,
          tipo_vinculo,
          CAST(COALESCE(confianca_vinculo, '0') AS REAL) AS confianca_vinculo,
          COALESCE(requer_revisao, 'false') AS requer_revisao,
          0 AS is_anchor_source,
          CASE
            WHEN tipo_vinculo = 'FILHO_DE' THEN 'down'
            WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 'up'
            WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 'same'
            WHEN tipo_vinculo IN ('PERTENCE_A_GRUPO_EXISTENTE', 'GRUPO_VINCULADO_POR_PESSOA') THEN 'down'
            ELSE 'same'
          END AS direction
        FROM vinculos
        WHERE entidade_destino = ? AND tipo_vinculo IN ({relation_clause})
      )
      , ranked AS (
        SELECT
          vinculo_id,
          fonte_origem,
          alvo_origem,
          source,
          target,
          tipo_vinculo,
          confianca_vinculo,
          requer_revisao,
          direction,
          CASE WHEN is_anchor_source = 1 THEN alvo_origem ELSE fonte_origem END AS neighbor_id,
          ROW_NUMBER() OVER (
            PARTITION BY direction, CASE WHEN is_anchor_source = 1 THEN alvo_origem ELSE fonte_origem END
            ORDER BY
              CASE
                WHEN tipo_vinculo = 'PAI_DE' THEN 1
                WHEN tipo_vinculo = 'MAE_DE' THEN 1
                WHEN tipo_vinculo = 'FILHO_DE' THEN 2
                ELSE 3
              END,
              confianca_vinculo DESC,
              vinculo_id
          ) AS rn
        FROM directed
        WHERE ({_direction_sql(direction_filter)}) {weak_clause}
      )
      SELECT
        vinculo_id,
        fonte_origem,
        alvo_origem,
        source,
        target,
        tipo_vinculo,
        confianca_vinculo,
        requer_revisao,
        direction,
        neighbor_id
      FROM ranked
      WHERE rn = 1
      ORDER BY
        confianca_vinculo DESC,
        vinculo_id
      LIMIT ? OFFSET ?
    """


def _count_direction_sql(include_weak: bool, relation_count: int) -> str:
    weak_clause = (
        ""
        if include_weak
        else "AND LOWER(COALESCE(requer_revisao, 'false')) NOT IN ('true','1','t','sim','yes','y')"
    )
    relation_clause = ",".join("?" for _ in range(relation_count))
    return f"""
      WITH directed AS (
        SELECT
          entidade_destino AS neighbor_id,
          CASE
            WHEN tipo_vinculo = 'FILHO_DE' THEN 'up'
            WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 'down'
            WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 'same'
            WHEN tipo_vinculo = 'PERTENCE_A_GRUPO_EXISTENTE' THEN 'up'
            WHEN tipo_vinculo = 'GRUPO_VINCULADO_POR_PESSOA' THEN 'down'
            ELSE 'same'
          END AS direction,
          COALESCE(requer_revisao, 'false') AS requer_revisao
        FROM vinculos
        WHERE entidade_origem = ? AND tipo_vinculo IN ({relation_clause})
        UNION ALL
        SELECT
          entidade_origem AS neighbor_id,
          CASE
            WHEN tipo_vinculo = 'FILHO_DE' THEN 'down'
            WHEN tipo_vinculo IN ('PAI_DE', 'MAE_DE') THEN 'up'
            WHEN tipo_vinculo IN ('CONJUGE_DE', 'CONJUGE_NOME_CANDIDATO') THEN 'same'
            WHEN tipo_vinculo IN ('PERTENCE_A_GRUPO_EXISTENTE', 'GRUPO_VINCULADO_POR_PESSOA') THEN 'down'
            ELSE 'same'
          END AS direction,
          COALESCE(requer_revisao, 'false') AS requer_revisao
        FROM vinculos
        WHERE entidade_destino = ? AND tipo_vinculo IN ({relation_clause})
      )
      SELECT
        direction,
        COUNT(DISTINCT neighbor_id) AS total
      FROM directed
      WHERE 1=1
        {weak_clause}
      GROUP BY direction
    """


def _direction_labels_by_relation(direction: str, relation_type: str) -> str:
    return _anchor_label_for_direction(relation_type, direction)


def _fetch_neighbor_rows(
    conn: sqlite3.Connection,
    anchor_id: str,
    relation_types: list[str],
    include_weak: bool,
    direction: str | None,
    max_items: int,
    offset: int,
) -> list[sqlite3.Row]:
    if not relation_types:
        return []
    sql = _build_direction_neighbors_sql(include_weak, direction or "", len(relation_types))
    params = [anchor_id, *relation_types, anchor_id, *relation_types, max_items, max(offset, 0)]
    return conn.execute(sql, params).fetchall()


def _count_neighbors_by_direction(
    conn: sqlite3.Connection,
    anchor_id: str,
    relation_types: list[str],
    include_weak: bool,
) -> dict[str, int]:
    if not relation_types:
        return {"up": 0, "down": 0, "same": 0}
    sql = _count_direction_sql(include_weak, len(relation_types))
    rows = conn.execute(sql, [anchor_id, *relation_types, anchor_id, *relation_types]).fetchall()
    counts = {"up": 0, "down": 0, "same": 0}
    for row in rows:
        direction = row["direction"]
        counts[direction] = _safe_int(row["total"])
    return counts


def _fetch_entities(conn: sqlite3.Connection, ids: set[str]) -> dict[str, sqlite3.Row]:
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT * FROM entidades WHERE entidade_id IN ({placeholders})", tuple(ids)).fetchall()
    return {row["entidade_id"]: row for row in rows}


def build_tree_payload(
    conn: sqlite3.Connection,
    anchor_id: str,
    relation_types: list[str],
    include_weak: bool,
    max_up_per_node: int,
    max_down_per_node: int,
    max_same_per_node: int,
    up_offset: int = 0,
    down_offset: int = 0,
    same_offset: int = 0,
    include_up: bool = True,
    include_down: bool = True,
    include_same: bool = False,
) -> TreeResponse:
    anchor = conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (anchor_id,)).fetchone()
    if not anchor:
        raise HTTPException(status_code=404, detail="Entidade não localizada")

    all_rows: list[sqlite3.Row] = []
    if include_up:
        all_rows.extend(
            _fetch_neighbor_rows(
                conn=conn,
                anchor_id=anchor_id,
                relation_types=relation_types,
                include_weak=include_weak,
                direction="up",
                max_items=max_up_per_node,
                offset=up_offset,
            )
        )
    if include_down:
        all_rows.extend(
            _fetch_neighbor_rows(
                conn=conn,
                anchor_id=anchor_id,
                relation_types=relation_types,
                include_weak=include_weak,
                direction="down",
                max_items=max_down_per_node,
                offset=down_offset,
            )
        )
    if include_same:
        all_rows.extend(
            _fetch_neighbor_rows(
                conn=conn,
                anchor_id=anchor_id,
                relation_types=relation_types,
                include_weak=include_weak,
                direction="same",
                max_items=max_same_per_node,
                offset=same_offset,
            )
        )

    totals = _count_neighbors_by_direction(conn, anchor_id, relation_types, include_weak)

    entity_ids = {anchor_id}
    for row in all_rows:
        entity_ids.add(row["neighbor_id"])
    entities = _fetch_entities(conn, entity_ids)

    level_map = {"up": -1, "same": 0, "down": 1}
    visible_by_dir = {"up": 0, "down": 0, "same": 0}
    relation_count_visible = {"up": 0, "down": 0, "same": 0}
    for row in all_rows:
        direction = row["direction"]
        visible_by_dir[direction] += 1

    nodes_by_id: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        direction = row["direction"]
        neighbor_id = row["neighbor_id"]

        relation_count_visible[direction] += 1

        level = level_map.get(direction, 0)
        previous = nodes_by_id.get(neighbor_id)
        if previous is None or abs(level) < abs(previous["nivel"]):
            nodes_by_id[neighbor_id] = {
                "nivel": level,
                "relacao": _anchor_label_for_direction(row["tipo_vinculo"], direction),
            }

    anchor_node = {
        "nivel": 0,
        "relacao": "selecionado",
        "total_vizinhos": totals["up"] + totals["down"] + totals["same"],
        "ocultos": max(0, (totals["up"] + totals["down"] + totals["same"]) - len(all_rows)),
    }

    nodes_payload: list[TreeNode] = []
    for node_id, meta in nodes_by_id.items():
        ent = entities.get(node_id)
        if not ent:
            continue
        is_anchor = node_id == anchor_id
        total_vizinhos = anchor_node["total_vizinhos"] if is_anchor else 0
        ocultos = anchor_node["ocultos"] if is_anchor else 0

        nodes_payload.append(
            TreeNode(
                id=node_id,
                nome=_build_entity_label(ent),
                cpf_cnpj=ent["cpf_cnpj"] or "",
                tipo_entidade=ent["tipo_entidade"] or "",
                status_entidade=ent["status_entidade"] or "",
                data_nascimento=ent["data_nascimento"] or "",
                data_obito=ent["data_obito"] or "",
                documento_valido=ent["documento_valido"] or "false",
                alerta=ent["alertas"] or "",
                nivel=meta["nivel"] if not is_anchor else 0,
                relacao_com_ancora=(meta["relacao"] if not is_anchor else "selecionado"),
                total_vizinhos=total_vizinhos,
                ocultos=ocultos,
            )
        )

    if anchor_id not in nodes_by_id:
        nodes_payload.insert(
            0,
            TreeNode(
                id=anchor_id,
                nome=_build_entity_label(anchor),
                cpf_cnpj=anchor["cpf_cnpj"] or "",
                tipo_entidade=anchor["tipo_entidade"] or "",
                status_entidade=anchor["status_entidade"] or "",
                data_nascimento=anchor["data_nascimento"] or "",
                data_obito=anchor["data_obito"] or "",
                documento_valido=anchor["documento_valido"] or "false",
                alerta=anchor["alertas"] or "",
                nivel=0,
                relacao_com_ancora="selecionado",
                total_vizinhos=anchor_node["total_vizinhos"],
                ocultos=anchor_node["ocultos"],
            ),
        )

    relations: list[TreeRelation] = []
    for row in all_rows:
        direction = row["direction"]
        relations.append(
            TreeRelation(
                id=row["vinculo_id"],
                source=row["source"],
                target=row["target"],
                tipo_vinculo=row["tipo_vinculo"],
                tipo_nome=RELATION_LABEL.get(row["tipo_vinculo"], row["tipo_vinculo"]),
                direcao_para_ancora=direction,
                confianca_vinculo=_safe_float(row["confianca_vinculo"]),
                requer_revisao=_safe_bool(row["requer_revisao"]),
            )
        )

    up_limit = len([r for r in all_rows if r["direction"] == "up"])
    down_limit = len([r for r in all_rows if r["direction"] == "down"])
    same_limit = len([r for r in all_rows if r["direction"] == "same"])

    return TreeResponse(
        anchor_id=anchor_id,
        nodes=nodes_payload,
        relations=relations,
        max_por_lote=max(max_up_per_node, max_down_per_node, max_same_per_node),
        up_total=totals["up"],
        down_total=totals["down"],
        same_total=totals["same"],
        next_up_offset=up_offset + max_up_per_node if include_up else 0,
        next_down_offset=down_offset + max_down_per_node if include_down else 0,
        next_same_offset=same_offset + max_same_per_node if include_same else 0,
        has_more_up=totals["up"] > up_offset + (up_limit if include_up else 0),
        has_more_down=totals["down"] > down_offset + (down_limit if include_down else 0),
        has_more_same=totals["same"] > same_offset + (same_limit if include_same else 0),
    )


def _resolve_max_per_node(max_per_node: int, max_por_lote: int | None) -> int:
    if max_por_lote is not None:
        return max_por_lote
    return max_per_node


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

    normalized = normalize_text(q)
    raw_numbers = re.sub(r"\D+", "", q)
    where_parts: list[str] = []
    params: list[Any] = []
    search_parts: list[str] = []

    if raw_numbers:
        search_parts.append("(cpf_cnpj = ? OR entidade_id = ? OR cpf_cnpj LIKE ?)")
        params.extend([raw_numbers, raw_numbers, f"{raw_numbers}%"])

    if normalized and not raw_numbers:
        search_parts.append(
            "(COALESCE(nome_canonico_normalizado, '') LIKE ? ESCAPE '\\' OR "
            "COALESCE(nome_original_normalizado, '') LIKE ? ESCAPE '\\')"
        )
        like_term = f"{_like_escape(normalized)}%"
        params.extend([like_term, like_term])

    if search_parts:
        where_parts.append("(" + " OR ".join(search_parts) + ")")

    if only_active:
        where_parts.append("LOWER(COALESCE(status_entidade, '')) = 'ativo'")

    if tipo:
        where_parts.append("tipo_entidade = ?")
        params.append(tipo)

    if not include_external:
        where_parts.append("tipo_entidade NOT LIKE '%EXTERNA%'")

    if not where_parts:
        return SearchResponse(query=q, total=0, limit=limit, offset=offset, items=[])

    where_sql = " WHERE " + " AND ".join(where_parts)
    total = _safe_int(conn.execute(f"SELECT COUNT(*) AS total FROM entidades {where_sql}", params).fetchone()[0])

    order = (
        "cpf_cnpj = ? DESC, "
        "COALESCE(nome_canonico_normalizado, '') LIKE ? ESCAPE '\\' DESC, "
        "COALESCE(nome_original_normalizado, '') LIKE ? ESCAPE '\\' DESC, "
        "COALESCE(nome_canonico_normalizado, '') ASC"
    )
    rows = conn.execute(
        f"SELECT * FROM entidades {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
        [
            *params,
            (raw_numbers.lower() if raw_numbers else ""),
            f"{_like_escape(normalized)}%" if normalized else "%%",
            f"{_like_escape(normalized)}%" if normalized else "%%",
            limit,
            offset,
        ],
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
            score=98.0 if raw_numbers and (row["cpf_cnpj"] == raw_numbers or row["entidade_id"] == raw_numbers) else 75.0,
            motivo="Documento localizado" if raw_numbers and (row["cpf_cnpj"] == raw_numbers or row["entidade_id"] == raw_numbers) else "Nome/campo localizado",
        )
        for row in rows
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
            rows = conn.execute("SELECT tipo_entidade, COUNT(*) AS total FROM entidades GROUP BY tipo_entidade").fetchall()
            tipos = {row["tipo_entidade"]: _safe_int(row["total"]) for row in rows}
            total_pendentes = _safe_int(
                conn.execute(
                    "SELECT COUNT(*) AS total FROM fila_revisao"
                ).fetchone()[0]
            )
    finally:
        conn.close()

    return MetadataResponse(
        total_entidades=total_entidades,
        total_vinculos=total_vinculos,
        total_grupos=total_grupos,
        total_pessoas=_safe_int(tipos.get("PF", 0)) + _safe_int(tipos.get("PF_EXTERNA", 0)),
        total_empresas=_safe_int(tipos.get("PJ", 0)) + _safe_int(tipos.get("PJ_EXTERNA", 0)),
        total_revisao=total_pendentes,
        tipo_entidade=tipos,
    )


@app.get("/api/search", response_model=SearchResponse)
def search_entities(
    q: str,
    limit: int = Query(default=20, ge=1, le=MAX_RESULTS),
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


@app.get("/api/entity/{entidade_id}", response_model=EntityDetailResponse)
def entity_detail(entidade_id: str) -> EntityDetailResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            entity = conn.execute("SELECT * FROM entidades WHERE entidade_id = ?", (entidade_id,)).fetchone()
            if not entity:
                raise HTTPException(status_code=404, detail="Entidade não encontrada")

            total_vizinhos = _safe_int(
                conn.execute("SELECT COUNT(*) AS total FROM vinculos WHERE entidade_origem = ? OR entidade_destino = ?", (entidade_id, entidade_id)).fetchone()[0]
            )

            by_type = conn.execute(
                """
                SELECT tipo_vinculo, COUNT(*) AS total
                FROM vinculos
                WHERE entidade_origem = ? OR entidade_destino = ?
                GROUP BY tipo_vinculo
                """,
                (entidade_id, entidade_id),
            ).fetchall()

            grupos = conn.execute(
                """
                SELECT g.grupo_id, g.tipo_grupo, g.nome_grupo, g.status_grupo,
                       g.grupo_regulatorio, g.requer_revisao, g.confianca_grupo,
                       m.papel_no_grupo, m.nivel_membro, m.justificativa_textual
                FROM membros_grupo m
                INNER JOIN grupos g ON g.grupo_id = m.grupo_id
                WHERE m.entidade_id = ?
                ORDER BY
                  CASE WHEN g.grupo_id LIKE 'GE:%' THEN 0 ELSE 1 END,
                  g.nome_grupo
                """,
                (entidade_id,),
            ).fetchall()

            total_grupos = _safe_int(
                conn.execute("SELECT COUNT(DISTINCT grupo_id) AS total FROM membros_grupo WHERE entidade_id = ?", (entidade_id,)).fetchone()[0]
            )

            group_ids = {row["grupo_id"] for row in grupos}
            if (entity["tipo_entidade"] or "") == "GRUPO_ECONOMICO":
                group_ids.add(entidade_id)

            if group_ids:
                ordered_group_ids = sorted(group_ids)
                placeholders = ",".join("?" for _ in ordered_group_ids)
                group_relation_rows = conn.execute(
                    f"""
                    SELECT
                      r.grupo_origem,
                      COALESCE(go.nome_grupo, r.grupo_origem) AS grupo_origem_nome,
                      COALESCE(go.tipo_grupo, '') AS grupo_origem_tipo,
                      r.grupo_destino,
                      COALESCE(gd.nome_grupo, r.grupo_destino) AS grupo_destino_nome,
                      COALESCE(gd.tipo_grupo, '') AS grupo_destino_tipo,
                      r.tipo_relacao,
                      r.entidade_ponte,
                      COALESCE(NULLIF(e.nome_canonico, ''), NULLIF(e.nome_original, ''), r.entidade_ponte) AS entidade_ponte_nome,
                      r.confianca,
                      r.relevancia,
                      r.evidencias,
                      r.data_referencia
                    FROM relacoes_entre_grupos r
                    LEFT JOIN grupos go ON go.grupo_id = r.grupo_origem
                    LEFT JOIN grupos gd ON gd.grupo_id = r.grupo_destino
                    LEFT JOIN entidades e ON e.entidade_id = r.entidade_ponte
                    WHERE r.grupo_origem IN ({placeholders})
                       OR r.grupo_destino IN ({placeholders})
                       OR r.entidade_ponte = ?
                    ORDER BY
                      CAST(COALESCE(r.relevancia, '0') AS REAL) DESC,
                      r.tipo_relacao,
                      r.grupo_origem,
                      r.grupo_destino
                    LIMIT 80
                    """,
                    [*ordered_group_ids, *ordered_group_ids, entidade_id],
                ).fetchall()
            else:
                group_relation_rows = conn.execute(
                    """
                    SELECT
                      r.grupo_origem,
                      COALESCE(go.nome_grupo, r.grupo_origem) AS grupo_origem_nome,
                      COALESCE(go.tipo_grupo, '') AS grupo_origem_tipo,
                      r.grupo_destino,
                      COALESCE(gd.nome_grupo, r.grupo_destino) AS grupo_destino_nome,
                      COALESCE(gd.tipo_grupo, '') AS grupo_destino_tipo,
                      r.tipo_relacao,
                      r.entidade_ponte,
                      COALESCE(NULLIF(e.nome_canonico, ''), NULLIF(e.nome_original, ''), r.entidade_ponte) AS entidade_ponte_nome,
                      r.confianca,
                      r.relevancia,
                      r.evidencias,
                      r.data_referencia
                    FROM relacoes_entre_grupos r
                    LEFT JOIN grupos go ON go.grupo_id = r.grupo_origem
                    LEFT JOIN grupos gd ON gd.grupo_id = r.grupo_destino
                    LEFT JOIN entidades e ON e.entidade_id = r.entidade_ponte
                    WHERE r.entidade_ponte = ?
                    ORDER BY CAST(COALESCE(r.relevancia, '0') AS REAL) DESC
                    LIMIT 80
                    """,
                    (entidade_id,),
                ).fetchall()
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
        total_vizinhos=total_vizinhos,
        total_grupos=total_grupos,
        conexoes_por_tipo={row["tipo_vinculo"]: _safe_int(row["total"]) for row in by_type},
        grupos=[
            GroupItem(
                grupo_id=row["grupo_id"],
                tipo_grupo=row["tipo_grupo"],
                nome_grupo=row["nome_grupo"],
                status_grupo=row["status_grupo"],
                grupo_regulatorio=row["grupo_regulatorio"],
                requer_revisao=_safe_bool(row["requer_revisao"]),
                confianca_grupo=row["confianca_grupo"] or "",
                papel_no_grupo=row["papel_no_grupo"] or "",
                nivel_membro=row["nivel_membro"] or "",
                justificativa_textual=row["justificativa_textual"] or "",
            )
            for row in grupos
        ],
        vinculos_grupos=[
            GroupRelationItem(
                grupo_origem=row["grupo_origem"] or "",
                grupo_origem_nome=row["grupo_origem_nome"] or "",
                grupo_origem_tipo=row["grupo_origem_tipo"] or "",
                grupo_destino=row["grupo_destino"] or "",
                grupo_destino_nome=row["grupo_destino_nome"] or "",
                grupo_destino_tipo=row["grupo_destino_tipo"] or "",
                tipo_relacao=row["tipo_relacao"] or "",
                entidade_ponte=row["entidade_ponte"] or "",
                entidade_ponte_nome=row["entidade_ponte_nome"] or "",
                confianca=_safe_float(row["confianca"]),
                relevancia=_safe_float(row["relevancia"]),
                evidencias=row["evidencias"] or "",
                data_referencia=row["data_referencia"] or "",
            )
            for row in group_relation_rows
        ],
    )


@app.get("/api/tree/{entidade_id}", response_model=TreeResponse)
def tree_view(
    entidade_id: str,
    relation_scope: str = Query(default="family"),
    include_business: bool = False,
    include_weak: bool = False,
    max_per_node: int = Query(default=10, ge=1, le=MAX_LINKS_PER_REQUEST),
    max_por_lote: int | None = Query(default=None, alias="max_por_lote", ge=1, le=MAX_LINKS_PER_REQUEST),
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    resolved_max_per_node = _resolve_max_per_node(max_per_node, max_por_lote)
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scopes = relation_scope
            if include_business and "business" not in scopes:
                scopes = f"{scopes},business"
            response = build_tree_payload(
                conn=conn,
                anchor_id=entidade_id,
                relation_types=_parse_scope(scopes),
                include_weak=include_weak,
                max_up_per_node=resolved_max_per_node,
                max_down_per_node=resolved_max_per_node,
                max_same_per_node=resolved_max_per_node,
                up_offset=up_offset,
                down_offset=down_offset,
                same_offset=same_offset,
                include_up=True,
                include_down=True,
                include_same=False,
            )
    finally:
        conn.close()
    return response


@app.get("/api/tree/{entidade_id}/neighbors", response_model=TreeResponse)
def tree_neighbors(
    entidade_id: str,
    direction: Literal["up", "down", "same", "both"] = "both",
    relation_scope: str = Query(default="family"),
    include_business: bool = False,
    include_weak: bool = False,
    max_per_node: int = Query(default=10, ge=1, le=MAX_LINKS_PER_REQUEST),
    max_por_lote: int | None = Query(default=None, alias="max_por_lote", ge=1, le=MAX_LINKS_PER_REQUEST),
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    normalized = direction
    include_up = normalized in {"up", "both"}
    include_down = normalized in {"down", "both"}
    include_same = normalized == "same"
    resolved_max_per_node = _resolve_max_per_node(max_per_node, max_por_lote)

    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scopes = relation_scope
            if include_business and "business" not in scopes:
                scopes = f"{scopes},business"
            response = build_tree_payload(
                conn=conn,
                anchor_id=entidade_id,
                relation_types=_parse_scope(scopes),
                include_weak=include_weak,
                max_up_per_node=resolved_max_per_node,
                max_down_per_node=resolved_max_per_node,
                max_same_per_node=resolved_max_per_node,
                up_offset=up_offset if include_up else 0,
                down_offset=down_offset if include_down else 0,
                same_offset=same_offset if include_same else 0,
                include_up=include_up,
                include_down=include_down,
                include_same=include_same,
            )
    finally:
        conn.close()
    return response


@app.get("/api/tree/{entidade_id}/seed", response_model=TreeResponse)
def tree_seed(
    entidade_id: str,
    relation_scope: str = Query(default="family"),
    include_business: bool = False,
    include_weak: bool = False,
    max_up_per_node: int = Query(default=2, ge=1, le=MAX_LINKS_PER_REQUEST),
    max_down_per_node: int = Query(default=10, ge=1, le=MAX_LINKS_PER_REQUEST),
    max_same_per_node: int = Query(default=0, ge=0, le=MAX_LINKS_PER_REQUEST),
) -> TreeResponse:
    conn = get_connection()
    try:
        with conn:
            ensure_indexes(conn)
            scopes = relation_scope
            if include_business and "business" not in scopes:
                scopes = f"{scopes},business"
            response = build_tree_payload(
                conn=conn,
                anchor_id=entidade_id,
                relation_types=_parse_scope(scopes),
                include_weak=include_weak,
                max_up_per_node=max_up_per_node,
                max_down_per_node=max_down_per_node,
                max_same_per_node=max_same_per_node,
                up_offset=0,
                down_offset=0,
                same_offset=0,
                include_up=True,
                include_down=True,
                include_same=True,
            )
    finally:
        conn.close()
    return response


# Compatibilidade com front-end legado e integração antiga
@app.get("/api/entities/search", response_model=SearchResponse)
def search_entities_legacy(
    q: str,
    limit: int = Query(default=20, ge=1, le=MAX_RESULTS),
    offset: int = Query(default=0, ge=0),
    tipo: str | None = None,
    include_external: bool = True,
    only_active: bool = False,
) -> SearchResponse:
    return search_entities(q=q, limit=limit, offset=offset, tipo=tipo, include_external=include_external, only_active=only_active)


@app.get("/api/entities/{entidade_id}", response_model=EntityDetailResponse)
def entity_detail_legacy(entidade_id: str) -> EntityDetailResponse:
    return entity_detail(entidade_id=entidade_id)


@app.get("/api/tree/context/{entidade_id}", response_model=TreeResponse)
def tree_context(entidade_id: str, include_business: bool = True, include_weak: bool = False, relation_scope: str = "family,business") -> TreeResponse:
    return tree_view(
        entidade_id=entidade_id,
        relation_scope=relation_scope,
        include_business=include_business,
        include_weak=include_weak,
        max_per_node=10,
        up_offset=0,
        down_offset=0,
        same_offset=0,
    )


@app.get("/api/tree/expand/{entidade_id}", response_model=TreeResponse)
def tree_expand(
    entidade_id: str,
    direction: Literal["up", "down", "same", "both"] = "both",
    include_business: bool = True,
    include_weak: bool = False,
    relation_scope: str = "family,business",
    max_per_node: int = Query(default=10, ge=1, le=MAX_LINKS_PER_REQUEST),
    max_por_lote: int | None = Query(default=None, alias="max_por_lote", ge=1, le=MAX_LINKS_PER_REQUEST),
    up_offset: int = Query(default=0, ge=0),
    down_offset: int = Query(default=0, ge=0),
    same_offset: int = Query(default=0, ge=0),
) -> TreeResponse:
    resolved_max_per_node = _resolve_max_per_node(max_per_node, max_por_lote)
    response = tree_neighbors(
        entidade_id=entidade_id,
        direction=direction,
        relation_scope=relation_scope,
        include_business=include_business,
        include_weak=include_weak,
        max_per_node=resolved_max_per_node,
        max_por_lote=None,
        up_offset=up_offset,
        down_offset=down_offset,
        same_offset=same_offset,
    )
    return response


@app.get("/api/tree/family/{entidade_id}", response_model=TreeResponse)
def tree_family(entidade_id: str, max_per_node: int = Query(default=10, ge=1, le=MAX_LINKS_PER_REQUEST), include_weak: bool = False) -> TreeResponse:
    return tree_view(entidade_id=entidade_id, relation_scope="family", include_business=False, include_weak=include_weak, max_per_node=max_per_node)


@app.exception_handler(HTTPException)
def http_exception_handler(_: Any, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
