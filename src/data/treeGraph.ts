import type { AppData, Entity, Group, GroupMember, LinkRecord } from "./graphData";
import { formatEntityName, groupTone } from "./graphData";

export type GraphNodeKind = "entity" | "group";
export type GraphEdgeKind = "membership" | "relationship" | "group-relation";

export type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  entityId?: string;
  groupId?: string;
  label: string;
  subtitle: string;
  tone: string;
  depth: number;
  x: number;
  y: number;
  size: number;
  status: string;
  requiresReview: boolean;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
  kind: GraphEdgeKind;
  confidence: number;
  relevance: number;
  linkId?: string;
  groupId?: string;
};

export type TreeGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width: number;
  height: number;
};

export type BuildGraphOptions = {
  activeEntityId: string;
  expandedIds: Set<string>;
  groupType: string;
  maxDepth: number;
};

function numeric(value: string | undefined): number {
  return Number(value || 0);
}

function entityTone(entity: Entity): string {
  if (entity.status_entidade.includes("FALECIDO")) return "historic";
  if (entity.entidade_provisoria === "true") return "provisional";
  if (entity.tipo_entidade === "PJ" || entity.tipo_entidade === "PJ_EXTERNA") return "business";
  if (entity.tipo_entidade === "ESPOLIO") return "historic";
  return "person";
}

function shouldIncludeGroup(group: Group, groupType: string): boolean {
  return groupType === "TODOS" || group.tipo_grupo === groupType;
}

function linkOtherSide(link: LinkRecord, entityId: string): string {
  return link.entidade_origem === entityId ? link.entidade_destino : link.entidade_origem;
}

function rankLink(link: LinkRecord): number {
  return (
    numeric(link.relevancia_regulatoria) +
    numeric(link.relevancia_societaria) +
    numeric(link.relevancia_familiar) +
    numeric(link.confianca_vinculo)
  );
}

export function buildTreeGraph(data: AppData, options: BuildGraphOptions): TreeGraph {
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();
  const queue: Array<{ id: string; kind: GraphNodeKind; depth: number }> = [];
  const visitedAtDepth = new Map<string, number>();

  function addEntity(entityId: string, depth: number): void {
    const entity = data.entityById.get(entityId);
    if (!entity) return;
    const nodeId = `entity:${entityId}`;
    const previousDepth = visitedAtDepth.get(nodeId);
    if (previousDepth !== undefined && previousDepth <= depth) return;
    visitedAtDepth.set(nodeId, depth);
    nodes.set(nodeId, {
      id: nodeId,
      kind: "entity",
      entityId,
      label: formatEntityName(entity),
      subtitle: `${entity.tipo_entidade}${entity.cpf_cnpj ? ` · ${entity.cpf_cnpj}` : ""}`,
      tone: entityTone(entity),
      depth,
      x: 0,
      y: 0,
      size: depth === 0 ? 68 : entity.tipo_entidade.startsWith("PJ") ? 54 : 48,
      status: entity.status_entidade,
      requiresReview: entity.alertas.length > 0 || entity.entidade_provisoria === "true",
    });
    queue.push({ id: entityId, kind: "entity", depth });
  }

  function addGroup(groupId: string, depth: number): void {
    const group = data.groupById.get(groupId);
    if (!group || !shouldIncludeGroup(group, options.groupType)) return;
    const nodeId = `group:${groupId}`;
    const previousDepth = visitedAtDepth.get(nodeId);
    if (previousDepth !== undefined && previousDepth <= depth) return;
    visitedAtDepth.set(nodeId, depth);
    nodes.set(nodeId, {
      id: nodeId,
      kind: "group",
      groupId,
      label: group.nome_grupo,
      subtitle: `${group.tipo_grupo} · ${group.grupo_id}`,
      tone: groupTone(group.tipo_grupo),
      depth,
      x: 0,
      y: 0,
      size: group.grupo_regulatorio === "true" ? 58 : 52,
      status: group.status_grupo,
      requiresReview: group.requer_revisao === "true",
    });
    queue.push({ id: groupId, kind: "group", depth });
  }

  function addEdge(edge: GraphEdge): void {
    if (edge.source === edge.target) return;
    edges.set(edge.id, edge);
  }

  addEntity(options.activeEntityId, 0);

  while (queue.length > 0) {
    const item = queue.shift();
    if (!item || item.depth >= options.maxDepth) continue;
    const treeNodeId = `${item.kind}:${item.id}`;
    const isExpanded = item.depth === 0 || options.expandedIds.has(treeNodeId) || options.expandedIds.has(item.id);

    if (item.kind === "entity") {
      const groupMemberships = (data.membersByEntity.get(item.id) ?? [])
        .filter((member) => shouldIncludeGroup(data.groupById.get(member.grupo_id) as Group, options.groupType))
        .sort((a, b) => numeric(b.relevancia_economica) - numeric(a.relevancia_economica))
        .slice(0, item.depth === 0 ? 14 : 8);

      for (const member of groupMemberships) {
        addGroup(member.grupo_id, item.depth + 1);
        addEdge({
          id: `member:${item.id}:${member.grupo_id}`,
          source: treeNodeId,
          target: `group:${member.grupo_id}`,
          label: member.papel_no_grupo,
          kind: "membership",
          confidence: numeric(member.confianca_inclusao),
          relevance: numeric(member.relevancia_economica),
          groupId: member.grupo_id,
        });
      }

      if (!isExpanded) continue;

      const directLinks = (data.linksByEntity.get(item.id) ?? [])
        .filter((link) => data.entityById.has(linkOtherSide(link, item.id)))
        .sort((a, b) => rankLink(b) - rankLink(a))
        .slice(0, item.depth === 0 ? 12 : 7);

      for (const link of directLinks) {
        const other = linkOtherSide(link, item.id);
        addEntity(other, item.depth + 1);
        addEdge({
          id: `link:${link.vinculo_id}:${item.id}:${other}`,
          source: treeNodeId,
          target: `entity:${other}`,
          label: link.tipo_vinculo,
          kind: "relationship",
          confidence: numeric(link.confianca_vinculo),
          relevance: Math.max(
            numeric(link.relevancia_regulatoria),
            numeric(link.relevancia_societaria),
            numeric(link.relevancia_familiar),
          ),
          linkId: link.vinculo_id,
        });
      }
    }

    if (item.kind === "group") {
      if (!isExpanded) continue;

      const groupMembers = (data.membersByGroup.get(item.id) ?? [])
        .sort((a, b) => {
          const level = { CORE: 3, ASSOCIADO: 2, CANDIDATO: 1 } as Record<string, number>;
          return (level[b.nivel_membro] ?? 0) - (level[a.nivel_membro] ?? 0) || numeric(b.relevancia_economica) - numeric(a.relevancia_economica);
        })
        .slice(0, 24);

      for (const member of groupMembers) {
        addEntity(member.entidade_id, item.depth + 1);
        addEdge({
          id: `group-member:${item.id}:${member.entidade_id}:${member.papel_no_grupo}`,
          source: treeNodeId,
          target: `entity:${member.entidade_id}`,
          label: member.papel_no_grupo,
          kind: "membership",
          confidence: numeric(member.confianca_inclusao),
          relevance: numeric(member.relevancia_economica),
          groupId: item.id,
        });
      }

      for (const relation of data.groupRelations.filter((relation) => relation.grupo_origem === item.id || relation.grupo_destino === item.id).slice(0, 4)) {
        const otherGroup = relation.grupo_origem === item.id ? relation.grupo_destino : relation.grupo_origem;
        addGroup(otherGroup, item.depth + 1);
        addEdge({
          id: `group-relation:${relation.grupo_origem}:${relation.grupo_destino}:${relation.tipo_relacao}`,
          source: treeNodeId,
          target: `group:${otherGroup}`,
          label: relation.tipo_relacao,
          kind: "group-relation",
          confidence: numeric(relation.confianca),
          relevance: numeric(relation.relevancia),
        });
      }
    }
  }

  const columns = new Map<number, GraphNode[]>();
  for (const node of nodes.values()) {
    const column = columns.get(node.depth) ?? [];
    column.push(node);
    columns.set(node.depth, column);
  }

  const depthCount = Math.max(1, ...Array.from(columns.keys()));
  const maxColumnSize = Math.max(1, ...Array.from(columns.values()).map((column) => column.length));
  const width = Math.max(980, depthCount * 310 + 360);
  const height = Math.max(640, maxColumnSize * 86 + 120);

  for (const [depth, column] of columns) {
    column.sort((a, b) => {
      const toneRank = ["person", "family", "business", "risk", "candidate", "historic", "provisional", "neutral"];
      return toneRank.indexOf(a.tone) - toneRank.indexOf(b.tone) || a.label.localeCompare(b.label);
    });
    const gap = height / (column.length + 1);
    column.forEach((node, index) => {
      node.x = 92 + depth * 300;
      node.y = gap * (index + 1);
      if (depth === 0) node.y = Math.min(height / 2, 260);
    });
  }

  return {
    nodes: Array.from(nodes.values()),
    edges: Array.from(edges.values()).filter((edge) => nodes.has(edge.source) && nodes.has(edge.target)),
    width,
    height,
  };
}

export function membershipForEntityInGroup(data: AppData, entityId: string, groupId: string): GroupMember | undefined {
  return data.membersByEntity.get(entityId)?.find((member) => member.grupo_id === groupId);
}
