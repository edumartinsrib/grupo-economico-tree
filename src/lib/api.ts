export type ApiMeta = {
  total_entidades: number;
  total_vinculos: number;
  total_grupos: number;
  total_pessoas: number;
  total_empresas: number;
  total_revisao: number;
  tipo_entidade: Record<string, number>;
};

export type SearchItem = {
  entidade_id: string;
  nome: string;
  cpf_cnpj: string;
  tipo_entidade: string;
  status_entidade: string;
  data_nascimento: string;
  documento_valido: string;
  score: number;
  motivo: string;
};

export type SearchResponse = {
  query: string;
  total: number;
  limit: number;
  offset: number;
  items: SearchItem[];
};

export type TreeNode = {
  id: string;
  nome: string;
  cpf_cnpj: string;
  tipo_entidade: string;
  status_entidade: string;
  data_nascimento: string;
  data_obito: string;
  documento_valido: string;
  alerta: string;
  nivel: number;
  relacao_com_ancora: string;
  total_vizinhos: number;
  ocultos: number;
};

export type TreeRelation = {
  id: string;
  source: string;
  target: string;
  tipo_vinculo: string;
  tipo_nome: string;
  direcao_para_ancora: "up" | "down" | "same";
  confianca_vinculo: number;
  requer_revisao: boolean;
};

export type TreeResponse = {
  anchor_id: string;
  nodes: TreeNode[];
  relations: TreeRelation[];
  max_por_lote: number;
  up_total: number;
  down_total: number;
  same_total: number;
  next_up_offset: number;
  next_down_offset: number;
  next_same_offset: number;
  has_more_up: boolean;
  has_more_down: boolean;
  has_more_same: boolean;
};

export type GroupItem = {
  grupo_id: string;
  tipo_grupo: string;
  nome_grupo: string;
  status_grupo: string;
  grupo_regulatorio: string;
  requer_revisao: boolean;
  confianca_grupo: string;
  papel_no_grupo: string;
  nivel_membro: string;
  justificativa_textual: string;
};

export type GroupRelationItem = {
  grupo_origem: string;
  grupo_origem_nome: string;
  grupo_origem_tipo: string;
  grupo_destino: string;
  grupo_destino_nome: string;
  grupo_destino_tipo: string;
  tipo_relacao: string;
  entidade_ponte: string;
  entidade_ponte_nome: string;
  confianca: number;
  relevancia: number;
  evidencias: string;
  data_referencia: string;
};

export type EntityDetailResponse = {
  entidade_id: string;
  tipo_entidade: string;
  nome_canonico: string;
  nome_original: string;
  cpf_cnpj: string;
  status_entidade: string;
  documento_valido: string;
  data_nascimento: string;
  data_obito: string;
  fonte_principal: string;
  data_atualizacao: string;
  alertas: string;
  total_vizinhos: number;
  total_grupos: number;
  conexoes_por_tipo: Record<string, number>;
  grupos: GroupItem[];
  vinculos_grupos: GroupRelationItem[];
};

type QueryValue = string | number | boolean | undefined;

type RequestMap = Record<string, QueryValue>;

async function requestJson<T>(url: string, params?: RequestMap): Promise<T> {
  const query = params
    ? Object.entries(params)
        .filter(([, value]) => value !== undefined)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
        .join("&")
    : "";

  const response = await fetch(query ? `${url}?${query}` : url);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`HTTP ${response.status}: ${message || response.statusText}`);
  }
  return response.json();
}

export async function fetchHealth(): Promise<{ status: string; db_status: string }> {
  return requestJson("/api/health");
}

export async function fetchMetadata(): Promise<ApiMeta> {
  return requestJson("/api/metadata");
}

export async function fetchSearch(params: {
  q: string;
  limit?: number;
  offset?: number;
  tipo?: string;
  include_external?: boolean;
  only_active?: boolean;
}): Promise<SearchResponse> {
  return requestJson("/api/search", {
    q: params.q,
    limit: params.limit ?? 12,
    offset: params.offset ?? 0,
    tipo: params.tipo ?? "",
    include_external: params.include_external ?? true,
    only_active: params.only_active ?? false,
  });
}

export async function fetchEntityDetail(entityId: string): Promise<EntityDetailResponse> {
  return requestJson(`/api/entity/${encodeURIComponent(entityId)}`);
}

export type TreeDirection = "up" | "down" | "same" | "both";

export async function fetchTreeRoot(params: {
  entidade_id: string;
  relation_scope?: string;
  include_business?: boolean;
  include_weak?: boolean;
  max_por_lote?: number;
  up_offset?: number;
  down_offset?: number;
  same_offset?: number;
}): Promise<TreeResponse> {
  return requestJson(`/api/tree/${encodeURIComponent(params.entidade_id)}`, {
    relation_scope: params.relation_scope ?? "family",
    include_business: params.include_business ?? false,
    include_weak: params.include_weak ?? false,
    max_por_lote: params.max_por_lote ?? 10,
    up_offset: params.up_offset ?? 0,
    down_offset: params.down_offset ?? 0,
    same_offset: params.same_offset ?? 0,
  });
}

export async function fetchTreeSeed(params: {
  entidade_id: string;
  relation_scope?: string;
  include_business?: boolean;
  include_weak?: boolean;
  max_up_per_node?: number;
  max_down_per_node?: number;
  max_same_per_node?: number;
}): Promise<TreeResponse> {
  return requestJson(`/api/tree/${encodeURIComponent(params.entidade_id)}/seed`, {
    relation_scope: params.relation_scope ?? "family",
    include_business: params.include_business ?? false,
    include_weak: params.include_weak ?? false,
    max_up_per_node: params.max_up_per_node ?? 2,
    max_down_per_node: params.max_down_per_node ?? 10,
    max_same_per_node: params.max_same_per_node ?? 0,
  });
}

export async function fetchTreeNeighbors(params: {
  entidade_id: string;
  direction: TreeDirection;
  relation_scope?: string;
  include_business?: boolean;
  include_weak?: boolean;
  max_por_lote?: number;
  up_offset?: number;
  down_offset?: number;
  same_offset?: number;
}): Promise<TreeResponse> {
  return requestJson(`/api/tree/${encodeURIComponent(params.entidade_id)}/neighbors`, {
    direction: params.direction,
    relation_scope: params.relation_scope ?? "family",
    include_business: params.include_business ?? false,
    include_weak: params.include_weak ?? false,
    max_por_lote: params.max_por_lote ?? 10,
    up_offset: params.up_offset ?? 0,
    down_offset: params.down_offset ?? 0,
    same_offset: params.same_offset ?? 0,
  });
}

// compatibilidade com front-end legado
export const fetchTreeContext = fetchTreeRoot;
export const fetchTreeExpand = fetchTreeNeighbors;
