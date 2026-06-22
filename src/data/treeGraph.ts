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
  childCount: number;
  hiddenChildren: number;
  isExpanded: boolean;
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
  hiddenIndirectCount: number;
  depthRange: [number, number];
};

export type BuildGraphOptions = {
  activeEntityId: string;
  expandedIds: Set<string>;
  groupType: string;
  maxDepth: number;
  showIndirect: boolean;
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

function isIndirectMember(member: GroupMember): boolean {
  return (
    member.vinculo_direto_ou_indireto === "INDIRETO" ||
    member.nivel_membro !== "CORE" ||
    /ASSOCIADO|CANDIDATO|INDIRETO|CONJUGE_DE_SOCIO|BENEFICIARIO|PARENTE_ATE|DEPENDENCIA/.test(member.papel_no_grupo)
  );
}

function isIndirectLink(link: LinkRecord): boolean {
  const strongDirect = new Set(["CONJUGE_DE", "FILHO_DE", "PAI_DE", "MAE_DE", "IRMAO_DE", "SOCIO_DE", "CONTROLADOR_DIRETO"]);
  if (strongDirect.has(link.tipo_vinculo) && link.requer_revisao !== "true") return false;
  return (
    link.requer_revisao === "true" ||
    link.tipo_vinculo.includes("INDIRETA") ||
    link.tipo_vinculo.includes("CANDIDATA") ||
    link.tipo_vinculo.includes("COMPARTILHADO") ||
    link.tipo_vinculo.includes("AMBIGUO") ||
    link.tipo_vinculo === "TRANSFERIU_PARA" ||
    link.tipo_vinculo === "EMPREGADO_DE" ||
    link.tipo_vinculo === "POSSIVEL_MESMO_GENITOR" ||
    link.tipo_vinculo === "TIO_TIA_DE" ||
    Math.max(numeric(link.relevancia_regulatoria), numeric(link.relevancia_societaria), numeric(link.relevancia_familiar)) < 60
  );
}

function relationDepthDelta(linkType: string, sourceIsCurrent: boolean): number {
  if (linkType === "FILHO_DE") {
    return sourceIsCurrent ? -1 : 1;
  }

  if (linkType === "PAI_DE" || linkType === "MAE_DE") {
    return sourceIsCurrent ? 1 : -1;
  }

  return 1;
}

function humanizeCode(value: string): string {
  return value
    .toLocaleLowerCase("pt-BR")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function memberLabel(role: string): string {
  const labels: Record<string, string> = {
    CONJUGE: "cônjuge",
    CONTROLADOR: "controlador",
    EMPRESA_CONTROLADA: "empresa controlada",
    EMPRESA_DA_FAMILIA: "empresa da família",
    FILHO: "filho",
    FILHO_COMUM: "filho comum",
    FONTE_RECURSOS: "fonte de recursos",
    IRMAO_COMPLETO: "irmão completo",
    MAE: "mãe",
    MAE_REFERENCIA: "mãe referência",
    MEMBRO_FAMILIA: "membro da família",
    PAI: "pai",
    PAI_REFERENCIA: "pai referência",
    PARTE_INDICIO_FRACO: "indício fraco",
    RECEPTOR_DEPENDENCIA_CANDIDATA: "recebe recursos",
    SOCIO: "sócio",
    SOCIO_DIRETO: "sócio direto",
  };
  return labels[role] ?? humanizeCode(role);
}

function linkLabel(type: string): string {
  const labels: Record<string, string> = {
    CONJUGE_DE: "cônjuge",
    CONJUGE_NOME_CANDIDATO: "cônjuge (candidato)",
    CONTATO_COMPARTILHADO: "contato compartilhado",
    CONTROLADOR_DIRETO: "controlador",
    EMPREGADO_DE: "empregado",
    ENDERECO_COMPARTILHADO: "endereço compartilhado",
    ESPOLIO_DE: "espólio",
    FILHO_DE: "filho de",
    IRMAO_DE: "irmão de",
    MAE_DE: "mãe de",
    PAI_DE: "pai de",
    PARENTESCO_AMBIGUO: "parentesco ambíguo",
    PARTICIPACAO_INDIRETA: "participação societária indireta",
    POSSIVEL_MESMO_GENITOR: "possível mesmo genitor",
    SOCIO_DE: "sócio",
    TIO_TIA_DE: "tio/tia de",
    TRANSFERIU_PARA: "fluxo de recursos",
  };
  return labels[type] ?? humanizeCode(type);
}

function linkLabelFromPerspective(tipo: string, sourceIsCurrent: boolean): string {
  if (!sourceIsCurrent) {
    const inverseMap: Record<string, string> = {
      CONJUGE_DE: "é cônjuge de",
      CONJUGE_NOME_CANDIDATO: "é cônjuge candidato de",
      FILHO_DE: "é pai ou mãe de",
      PAI_DE: "é filho(a) de",
      MAE_DE: "é filho(a) de",
      IRMAO_DE: "é irmão(a) de",
      TIO_TIA_DE: "é sobrinho(a) de",
      SOCIO_DE: "tem sociedade com",
      BENEFICIARIO_INDIRETO_CANDIDATO: "é beneficiário(a) potencial de",
      CONTROLE_CONJUNTO_CANDIDATO: "é controle conjunto com",
      INFLUENCIA_RELEVANTE: "tem influência societária com",
      SOCIO_MINORITARIO: "é sócio(a) minoritário(a) de",
      SOCIO_DE_FINANCEIRO: "é sócio(a) indireto(a) de",
      CONTROLADOR_DIRETO: "é controlado por",
      PARTICIPACAO_INDIRETA: "tem participação indireta em",
      PARENTESCO_AMBIGUO: "parentesco possível com",
      POSSIVEL_MESMO_GENITOR: "parentesco possível com",
      CAD_ENDERECO_EXATO: "endereço comum com",
      CAD_CONTATO_COMPARTILHADO: "contato em comum com",
      DEPENDENCIA_FINANCEIRA_CANDIDATA: "dependência econômica sugerida com",
      CONJUGE_DE_SOCIO: "é cônjuge de sócio de",
      ESPOLIO_DE: "é relacionado a",
      EMPREGADO_DE: "tem vínculo como empregado de",
      ENDERECO_COMPARTILHADO: "tem endereço em comum com",
      CONTATO_COMPARTILHADO: "tem contato em comum com",
      TRANSFERIU_PARA: "recebe fluxo de recursos de",
    };
    return inverseMap[tipo] ?? `recebe relação ${linkLabel(tipo)} de`;
  }

  const sourceMap: Record<string, string> = {
    CONJUGE_DE: "é cônjuge de",
    CONJUGE_NOME_CANDIDATO: "é cônjuge candidato de",
    FILHO_DE: "é filho(a) de",
    PAI_DE: "é pai de",
    MAE_DE: "é mãe de",
    IRMAO_DE: "é irmão(a) de",
    TIO_TIA_DE: "é tio(a) de",
    SOCIO_DE: "é sócio de",
    BENEFICIARIO_INDIRETO_CANDIDATO: "é beneficiário(a) potencial de",
    CONTROLADOR_DIRETO: "é controlador(a) de",
    CONTROLE_CONJUNTO_CANDIDATO: "tem controle conjunto de",
    INFLUENCIA_RELEVANTE: "é sócio com influência em",
    SOCIO_MINORITARIO: "é sócio minoritário de",
    SOCIO_DE_FINANCEIRO: "é sócio financeiro de",
    PARTICIPACAO_INDIRETA: "participa indiretamente em",
    PARENTESCO_AMBIGUO: "parentesco possível com",
    POSSIVEL_MESMO_GENITOR: "possível mesmo genitor com",
    CAD_ENDERECO_EXATO: "com endereço comum com",
    CAD_CONTATO_COMPARTILHADO: "com contato compartilhado com",
    DEPENDENCIA_FINANCEIRA_CANDIDATA: "sugere dependência econômica com",
    CONJUGE_DE_SOCIO: "é cônjuge de sócio de",
    ESPOLIO_DE: "é relacionado a",
    EMPREGADO_DE: "é empregado(a) de",
    TRANSFERIU_PARA: "transferiu para",
    ENDERECO_COMPARTILHADO: "compartilha endereço com",
    CONTATO_COMPARTILHADO: "compartilha contato com",
  };
  return sourceMap[tipo] ?? `é ${linkLabel(tipo)}`;
}

function groupRelationLabel(type: string): string {
  const labels: Record<string, string> = {
    CONTROLADOR_COMUM: "controlador comum",
    DEPENDENCIA_ECONOMICA: "dependência econômica",
    FAMILIA_POSSUI_EMPRESA: "família possui empresa",
    GRUPO_SOBREPOSTO: "grupo sobreposto",
    PESSOA_PONTE: "pessoa ponte",
    RELACAO_COMPORTAMENTAL: "relação comportamental",
    SUBGRUPO_DE: "subgrupo de",
  };
  return labels[type] ?? humanizeCode(type);
}

export function buildTreeGraph(data: AppData, options: BuildGraphOptions): TreeGraph {
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();
  const queue: Array<{ id: string; kind: GraphNodeKind; depth: number }> = [];
  const visitedAtDepth = new Map<string, number>();
  let hiddenIndirectCount = 0;

  function validGroupForMember(member: GroupMember): boolean {
    const group = data.groupById.get(member.grupo_id);
    return Boolean(group && shouldIncludeGroup(group, options.groupType));
  }

  function entityMemberships(entityId: string, depth: number): { visible: GroupMember[]; hidden: number; total: number } {
    const raw = (data.membersByEntity.get(entityId) ?? [])
      .filter(validGroupForMember)
      .sort((a, b) => numeric(b.relevancia_economica) - numeric(a.relevancia_economica));
    const filtered = options.showIndirect ? raw : raw.filter((member) => !isIndirectMember(member));
    const limit = options.showIndirect ? (depth === 0 ? 10 : 6) : depth === 0 ? 6 : 3;
    return {
      visible: filtered.slice(0, limit),
      hidden: raw.length - filtered.slice(0, limit).length,
      total: raw.length,
    };
  }

  function entityLinks(entityId: string, depth: number): { visible: LinkRecord[]; hidden: number; total: number } {
    const raw = (data.linksByEntity.get(entityId) ?? [])
      .filter((link) => data.entityById.has(linkOtherSide(link, entityId)))
      .sort((a, b) => rankLink(b) - rankLink(a));
    const filtered = options.showIndirect ? raw : raw.filter((link) => !isIndirectLink(link));
    const limit = options.showIndirect ? (depth === 0 ? 8 : 5) : depth === 0 ? 4 : 3;
    return {
      visible: filtered.slice(0, limit),
      hidden: raw.length - filtered.slice(0, limit).length,
      total: raw.length,
    };
  }

  function groupMembers(groupId: string, depth: number): { visible: GroupMember[]; hidden: number; total: number } {
    const raw = (data.membersByGroup.get(groupId) ?? []).sort((a, b) => {
      const level = { CORE: 3, ASSOCIADO: 2, CANDIDATO: 1 } as Record<string, number>;
      return (level[b.nivel_membro] ?? 0) - (level[a.nivel_membro] ?? 0) || numeric(b.relevancia_economica) - numeric(a.relevancia_economica);
    });
    const filtered = options.showIndirect ? raw : raw.filter((member) => !isIndirectMember(member));
    const limit = options.showIndirect ? (depth === 0 ? 18 : 10) : depth === 0 ? 10 : 6;
    return {
      visible: filtered.slice(0, limit),
      hidden: raw.length - filtered.slice(0, limit).length,
      total: raw.length,
    };
  }

  function groupRelationCount(groupId: string): number {
    return data.groupRelations.filter((relation) => relation.grupo_origem === groupId || relation.grupo_destino === groupId).length;
  }

  function addEntity(entityId: string, depth: number): void {
    const entity = data.entityById.get(entityId);
    if (!entity) return;
    const nodeId = `entity:${entityId}`;
    const previousDepth = visitedAtDepth.get(nodeId);
    if (previousDepth !== undefined && Math.abs(previousDepth) <= Math.abs(depth)) return;
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
      childCount: 0,
      hiddenChildren: 0,
      isExpanded: false,
    });
    queue.push({ id: entityId, kind: "entity", depth });
  }

  function addGroup(groupId: string, depth: number): void {
    const group = data.groupById.get(groupId);
    if (!group || !shouldIncludeGroup(group, options.groupType)) return;
    const nodeId = `group:${groupId}`;
    const previousDepth = visitedAtDepth.get(nodeId);
    if (previousDepth !== undefined && Math.abs(previousDepth) <= Math.abs(depth)) return;
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
      childCount: 0,
      hiddenChildren: 0,
      isExpanded: false,
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
    const queuedDepth = visitedAtDepth.get(treeNodeId);
    if (queuedDepth !== undefined && queuedDepth !== item.depth) continue;
    const isExpanded = item.depth === 0 || options.expandedIds.has(treeNodeId) || options.expandedIds.has(item.id);
    const currentNode = nodes.get(treeNodeId);

    if (item.kind === "entity") {
      const memberships = entityMemberships(item.id, item.depth);
      const directLinks = entityLinks(item.id, item.depth);
      if (currentNode) {
        currentNode.childCount = memberships.visible.length + directLinks.visible.length;
        currentNode.hiddenChildren = memberships.hidden + directLinks.hidden;
        currentNode.isExpanded = isExpanded;
      }
      hiddenIndirectCount += Math.max(0, memberships.hidden + directLinks.hidden);

      for (const member of memberships.visible) {
        addGroup(member.grupo_id, item.depth + 1);
        addEdge({
          id: `member:${item.id}:${member.grupo_id}`,
          source: treeNodeId,
          target: `group:${member.grupo_id}`,
          label: memberLabel(member.papel_no_grupo),
          kind: "membership",
          confidence: numeric(member.confianca_inclusao),
          relevance: numeric(member.relevancia_economica),
          groupId: member.grupo_id,
        });
      }

      if (!isExpanded) continue;

      for (const link of directLinks.visible) {
        const other = linkOtherSide(link, item.id);
        const sourceIsCurrent = link.entidade_origem === item.id;
        const targetDepth = item.depth + relationDepthDelta(link.tipo_vinculo, sourceIsCurrent);
        addEntity(other, targetDepth);
        const edgeSource = targetDepth > item.depth ? treeNodeId : `entity:${other}`;
        const edgeTarget = targetDepth > item.depth ? `entity:${other}` : treeNodeId;
        addEdge({
          id: `link:${link.vinculo_id}:${item.id}:${other}`,
          source: edgeSource,
          target: edgeTarget,
          label: linkLabelFromPerspective(link.tipo_vinculo, sourceIsCurrent),
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
      const members = groupMembers(item.id, item.depth);
      const relationCount = options.showIndirect ? groupRelationCount(item.id) : 0;
      if (currentNode) {
        currentNode.childCount = members.visible.length + relationCount;
        currentNode.hiddenChildren = members.hidden + (options.showIndirect ? 0 : groupRelationCount(item.id));
        currentNode.isExpanded = isExpanded;
      }
      hiddenIndirectCount += Math.max(0, members.hidden + (options.showIndirect ? 0 : groupRelationCount(item.id)));

      if (!isExpanded) continue;

      for (const member of members.visible) {
        addEntity(member.entidade_id, item.depth + 1);
        addEdge({
          id: `group-member:${item.id}:${member.entidade_id}:${member.papel_no_grupo}`,
          source: treeNodeId,
          target: `entity:${member.entidade_id}`,
          label: memberLabel(member.papel_no_grupo),
          kind: "membership",
          confidence: numeric(member.confianca_inclusao),
          relevance: numeric(member.relevancia_economica),
          groupId: item.id,
        });
      }

      if (!options.showIndirect) continue;

      for (const relation of data.groupRelations.filter((relation) => relation.grupo_origem === item.id || relation.grupo_destino === item.id).slice(0, 4)) {
        const otherGroup = relation.grupo_origem === item.id ? relation.grupo_destino : relation.grupo_origem;
        addGroup(otherGroup, item.depth + 1);
        addEdge({
          id: `group-relation:${relation.grupo_origem}:${relation.grupo_destino}:${relation.tipo_relacao}`,
          source: treeNodeId,
          target: `group:${otherGroup}`,
          label: groupRelationLabel(relation.tipo_relacao),
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

  const depthValues = Array.from(columns.keys());
  const minDepth = Math.min(...depthValues);
  const maxDepth = Math.max(...depthValues);
  const depthCount = Math.max(1, maxDepth - minDepth + 1);
  const maxRowSize = Math.max(1, ...Array.from(columns.values()).map((column) => column.length));
  const width = Math.max(980, maxRowSize * 230 + 180);
  const height = Math.max(720, depthCount * 210 + 260);

  for (const [depth, column] of columns) {
    column.sort((a, b) => {
      const toneRank = ["person", "family", "business", "risk", "candidate", "historic", "provisional", "neutral"];
      return toneRank.indexOf(a.tone) - toneRank.indexOf(b.tone) || a.label.localeCompare(b.label);
    });
    const horizontalGap = 240;
    const rowWidth = Math.max(0, (column.length - 1) * horizontalGap);
    const startX = Math.max(132, width / 2 - rowWidth / 2);
    column.forEach((node, index) => {
      node.x = startX + index * horizontalGap;
      node.y = 96 + (depth - minDepth) * 190;
      if (depth === 0) node.x = width / 2;
    });
  }

  return {
    nodes: Array.from(nodes.values()),
    edges: Array.from(edges.values()).filter((edge) => nodes.has(edge.source) && nodes.has(edge.target)),
    width,
    height,
    hiddenIndirectCount,
    depthRange: [minDepth, maxDepth],
  };
}

export function membershipForEntityInGroup(data: AppData, entityId: string, groupId: string): GroupMember | undefined {
  return data.membersByEntity.get(entityId)?.find((member) => member.grupo_id === groupId);
}
