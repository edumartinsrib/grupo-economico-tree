import agregacoesCsv from "../../resultados/agregacoes_financeiras_grupos.csv?raw";
import entidadesCsv from "../../resultados/entidades.csv?raw";
import filaRevisaoCsv from "../../resultados/fila_revisao.csv?raw";
import gruposCsv from "../../resultados/grupos.csv?raw";
import membrosCsv from "../../resultados/membros_grupo.csv?raw";
import relacoesGruposCsv from "../../resultados/relacoes_entre_grupos.csv?raw";
import vinculosCsv from "../../resultados/vinculos.csv?raw";
import denodoCsv from "../../dados/denodo_base_cadastral.csv?raw";
import { parseCsv, normalizeSearch } from "../lib/csv";

export type Entity = {
  entidade_id: string;
  tipo_entidade: string;
  cpf_cnpj: string;
  nome_canonico: string;
  nome_original: string;
  data_nascimento: string;
  data_obito: string;
  status_entidade: string;
  documento_valido: string;
  entidade_provisoria: string;
  fonte_principal: string;
  data_atualizacao: string;
  alertas: string;
};

export type LinkRecord = {
  vinculo_id: string;
  entidade_origem: string;
  entidade_destino: string;
  tipo_vinculo: string;
  direcional: string;
  percentual_participacao: string;
  confianca_vinculo: string;
  relevancia_familiar: string;
  relevancia_societaria: string;
  relevancia_regulatoria: string;
  data_inicio: string;
  data_fim: string;
  data_observacao: string;
  codigo_regra: string;
  arquivo_fonte: string;
  campos_fonte: string;
  evidencias: string;
  requer_revisao: string;
};

export type Group = {
  grupo_id: string;
  tipo_grupo: string;
  entidade_ancora: string;
  nome_grupo: string;
  data_corte: string;
  quantidade_membros_core: string;
  quantidade_membros_associados: string;
  quantidade_candidatos: string;
  confianca_grupo: string;
  status_grupo: string;
  grupo_regulatorio: string;
  requer_revisao: string;
  motivo_revisao: string;
};

export type GroupMember = {
  grupo_id: string;
  entidade_id: string;
  papel_no_grupo: string;
  nivel_membro: string;
  vinculo_direto_ou_indireto: string;
  entidade_ponte: string;
  caminho_vinculo: string;
  profundidade: string;
  confianca_inclusao: string;
  relevancia_economica: string;
  codigos_regras: string;
  arquivos_fonte: string;
  data_inicio: string;
  data_fim: string;
  requer_revisao: string;
  justificativa_textual: string;
};

export type GroupRelation = {
  grupo_origem: string;
  grupo_destino: string;
  tipo_relacao: string;
  entidade_ponte: string;
  confianca: string;
  relevancia: string;
  evidencias: string;
  data_referencia: string;
};

export type Aggregation = {
  grupo_id: string;
  tipo_grupo: string;
  saldo_total: string;
  saldo_credito_rural: string;
  saldo_credito_comercial: string;
  saldo_credito_direcionado: string;
  limite_cheque_especial: string;
  limite_cartao: string;
  valor_bens: string;
  quantidade_contas_ativas: string;
  quantidade_contas_encerradas: string;
  quantidade_membros_falecidos: string;
  pior_faixa_risco: string;
  exposicao_pf: string;
  exposicao_pj: string;
  observacao_sobreposicao: string;
  data_corte: string;
};

export type ReviewItem = {
  objeto_tipo: string;
  objeto_id: string;
  codigo_alerta: string;
  severidade: string;
  descrição: string;
  entidades_envolvidas: string;
  "evidências disponíveis": string;
  "ação recomendada": string;
};

export type BankRecord = {
  cpf_cnpj: string;
  status_conta: string;
  tipo_pessoa: string;
  nome_razao_social: string;
  num_matricula: string;
  cod_conglomerado: string;
  faixa_risco: string;
  saldo: string;
};

export type SearchResult = {
  entity: Entity;
  bank?: BankRecord;
  groups: Group[];
  score: number;
  reason: string;
};

export type AppData = {
  entities: Entity[];
  links: LinkRecord[];
  groups: Group[];
  members: GroupMember[];
  groupRelations: GroupRelation[];
  aggregations: Aggregation[];
  reviews: ReviewItem[];
  bankRows: BankRecord[];
  entityById: Map<string, Entity>;
  groupById: Map<string, Group>;
  aggregationByGroupId: Map<string, Aggregation>;
  bankByDoc: Map<string, BankRecord>;
  membersByEntity: Map<string, GroupMember[]>;
  membersByGroup: Map<string, GroupMember[]>;
  linksByEntity: Map<string, LinkRecord[]>;
  reviewsByObject: Map<string, ReviewItem[]>;
};

function byKey<T extends Record<string, string>>(rows: T[], key: keyof T): Map<string, T> {
  return new Map(rows.filter((row) => row[key]).map((row) => [row[key], row]));
}

function addToMap<T>(map: Map<string, T[]>, key: string, value: T): void {
  const list = map.get(key) ?? [];
  list.push(value);
  map.set(key, list);
}

const entities = parseCsv(entidadesCsv) as Entity[];
const links = parseCsv(vinculosCsv) as LinkRecord[];
const groups = parseCsv(gruposCsv) as Group[];
const members = parseCsv(membrosCsv) as GroupMember[];
const groupRelations = parseCsv(relacoesGruposCsv) as GroupRelation[];
const aggregations = parseCsv(agregacoesCsv) as Aggregation[];
const reviews = parseCsv(filaRevisaoCsv) as ReviewItem[];
const bankRows = parseCsv(denodoCsv) as BankRecord[];

const entityById = byKey(entities, "entidade_id");
const groupById = byKey(groups, "grupo_id");
const aggregationByGroupId = byKey(aggregations, "grupo_id");
const bankByDoc = byKey(bankRows, "cpf_cnpj");
const membersByEntity = new Map<string, GroupMember[]>();
const membersByGroup = new Map<string, GroupMember[]>();
const linksByEntity = new Map<string, LinkRecord[]>();
const reviewsByObject = new Map<string, ReviewItem[]>();

for (const member of members) {
  addToMap(membersByEntity, member.entidade_id, member);
  addToMap(membersByGroup, member.grupo_id, member);
}

for (const link of links) {
  addToMap(linksByEntity, link.entidade_origem, link);
  addToMap(linksByEntity, link.entidade_destino, link);
}

for (const review of reviews) {
  addToMap(reviewsByObject, review.objeto_id, review);
  for (const entityId of review.entidades_envolvidas.split("|").filter(Boolean)) {
    addToMap(reviewsByObject, entityId, review);
  }
}

export const appData: AppData = {
  entities,
  links,
  groups,
  members,
  groupRelations,
  aggregations,
  reviews,
  bankRows,
  entityById,
  groupById,
  aggregationByGroupId,
  bankByDoc,
  membersByEntity,
  membersByGroup,
  linksByEntity,
  reviewsByObject,
};

export function searchEntities(data: AppData, query: string, limit = 12): SearchResult[] {
  const term = normalizeSearch(query);
  if (!term) {
    return data.entities
      .filter((entity) => entity.tipo_entidade === "PF" || entity.tipo_entidade === "PJ")
      .slice(0, limit)
      .map((entity) => ({
        entity,
        bank: data.bankByDoc.get(entity.cpf_cnpj),
        groups: groupsForEntity(data, entity.entidade_id),
        score: 1,
        reason: "amostra inicial",
      }));
  }

  const matches: Array<SearchResult | null> = data.entities.map((entity) => {
      const bank = data.bankByDoc.get(entity.cpf_cnpj);
      const groupList = groupsForEntity(data, entity.entidade_id);
      const haystack = [
        entity.entidade_id,
        entity.tipo_entidade,
        entity.cpf_cnpj,
        entity.nome_canonico,
        entity.nome_original,
        entity.status_entidade,
        entity.alertas,
        bank?.num_matricula,
        bank?.status_conta,
        bank?.cod_conglomerado,
        bank?.faixa_risco,
        ...groupList.map((group) => `${group.grupo_id} ${group.nome_grupo} ${group.tipo_grupo}`),
      ]
        .map(normalizeSearch)
        .join(" ");

      if (!haystack.includes(term)) return null;

      const exactDoc = normalizeSearch(entity.cpf_cnpj) === term;
      const exactName = normalizeSearch(entity.nome_canonico) === term;
      return {
        entity,
        bank,
        groups: groupList,
        score: exactDoc ? 100 : exactName ? 80 : entity.tipo_entidade === "PF" ? 50 : 40,
        reason: exactDoc ? "CPF/CNPJ exato" : exactName ? "nome exato" : "correspondência em cadastro, conta ou grupo",
      };
    });

  return matches
    .filter((item): item is SearchResult => Boolean(item))
    .sort((a, b) => b.score - a.score || a.entity.nome_canonico.localeCompare(b.entity.nome_canonico))
    .slice(0, limit);
}

export function groupsForEntity(data: AppData, entityId: string): Group[] {
  return (data.membersByEntity.get(entityId) ?? [])
    .map((member) => data.groupById.get(member.grupo_id))
    .filter((group): group is Group => Boolean(group));
}

export function formatEntityName(entity?: Entity): string {
  if (!entity) return "Entidade não localizada";
  return entity.nome_canonico || entity.nome_original || entity.cpf_cnpj || entity.entidade_id;
}

export function groupTone(type: string): string {
  if (type.includes("RISCO")) return "risk";
  if (type.includes("EMPRESA") || type.includes("SOCIETARIO")) return "business";
  if (type.includes("COMPORTAMENTAL")) return "candidate";
  if (type.includes("CONJUGAL") || type.includes("FAMILIAR") || type.includes("IRMAOS")) return "family";
  return "neutral";
}
