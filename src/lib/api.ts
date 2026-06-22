export type ApiMeta = {
  total_entidades: number;
  total_vinculos: number;
  total_grupos: number;
  total_revisao: number;
  total_pessoas: number;
  total_empresas: number;
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

export type RelationItem = {
  id: string;
  source: string;
  target: string;
  tipo_vinculo: string;
  tipo_nome: string;
  relation_depth_delta: number;
  role_from_source: string;
  role_from_target: string;
  confianca_vinculo: number;
  requer_revisao: boolean;
};

export type EntityNode = {
  id: string;
  nome: string;
  cpf_cnpj: string;
  tipo_entidade: string;
  status_entidade: string;
  data_nascimento: string;
  data_obito: string;
  documento_valido: string;
  alerta: string;
  depth: number;
  total_vizinhos: number;
  hidden_vizinhos: number;
  roles: string[];
};

export type TreeResponse = {
  root_id: string;
  max_depth: number;
  max_per_node: number;
  scope: string;
  include_weak: boolean;
  include_type: "up" | "down" | "up+down" | "all" | "same";
  has_more_up: boolean;
  has_more_down: boolean;
  has_more_same: boolean;
  next_up_offset: number;
  next_down_offset: number;
  next_same_offset: number;
  nodes: EntityNode[];
  relations: RelationItem[];
  summary: {
    total_nodos: number;
    total_relacoes: number;
    nivel_max: number;
    up_total?: number;
    down_total?: number;
    same_total?: number;
  };
};

export type GroupItem = {
  grupo_id: string;
  tipo_grupo: string;
  nome_grupo: string;
  status_grupo: string;
  grupo_regulatorio: string;
  requer_revisao: boolean;
  confianca_grupo: string;
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
  graus_conexao: number;
  total_vinculos: number;
  total_grupos: number;
  conexoes_por_tipo: Record<string, number>;
  grupos: GroupItem[];
};

type QueryValue = string | number | boolean | undefined;
type FetchParams = Record<string, QueryValue>;

type RequestMap = {
  [key: string]: QueryValue;
};

async function requestJson<T>(url: string, params?: FetchParams): Promise<T> {
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
  return requestJson("/api/entities/search", {
    q: params.q,
    limit: params.limit ?? 12,
    offset: params.offset ?? 0,
    tipo: params.tipo ?? "",
    include_external: params.include_external ?? true,
    only_active: params.only_active ?? false,
  });
}

export async function fetchEntityDetail(entityId: string): Promise<EntityDetailResponse> {
  return requestJson(`/api/entities/${encodeURIComponent(entityId)}`);
}

export type TreeDirection = "up" | "down" | "same" | "both" | "all";

export async function fetchTreeContext(params: {
  entidade_id: string;
  include_up: boolean;
  include_down: boolean;
  include_same?: boolean;
  relation_scope?: string;
  max_per_node?: number;
  include_weak?: boolean;
  up_offset?: number;
  down_offset?: number;
  same_offset?: number;
}): Promise<TreeResponse> {
  const payload: RequestMap = {
    include_up: params.include_up,
    include_down: params.include_down,
    include_same: params.include_same ?? false,
    relation_scope: params.relation_scope ?? "family,business",
    max_per_node: params.max_per_node ?? 10,
    include_weak: params.include_weak ?? false,
    up_offset: params.up_offset ?? 0,
    down_offset: params.down_offset ?? 0,
    same_offset: params.same_offset ?? 0,
  };

  return requestJson(`/api/tree/context/${encodeURIComponent(params.entidade_id)}`, payload);
}

export async function fetchTreeExpand(params: {
  entidade_id: string;
  direction?: TreeDirection;
  max_per_node?: number;
  include_weak?: boolean;
  relation_scope?: string;
  up_offset?: number;
  down_offset?: number;
  same_offset?: number;
}): Promise<TreeResponse> {
  const payload: RequestMap = {
    direction: params.direction ?? "both",
    max_per_node: params.max_per_node ?? 10,
    include_weak: params.include_weak ?? false,
    relation_scope: params.relation_scope ?? "family,business",
    up_offset: params.up_offset ?? 0,
    down_offset: params.down_offset ?? 0,
    same_offset: params.same_offset ?? 0,
  };

  return requestJson(`/api/tree/expand/${encodeURIComponent(params.entidade_id)}`, payload);
}

export async function fetchTreeSeed(params: {
  entidade_id: string;
  max_per_node: number;
  include_weak?: boolean;
  include_business?: boolean;
}): Promise<TreeResponse> {
  return requestJson(`/api/tree/seed/${encodeURIComponent(params.entidade_id)}`, {
    max_per_node: params.max_per_node,
    include_weak: params.include_weak ?? false,
    include_business: params.include_business ?? false,
  });
}
