import {
  Bank,
  Buildings,
  CaretRight,
  Eye,
  FunnelSimple,
  IdentificationCard,
  LinkSimple,
  MagnifyingGlass,
  Network,
  Rows,
  Table,
  TreeStructure,
  UsersThree,
  Warning,
  X,
} from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import { appData, formatEntityName, groupTone, groupsForEntity, searchEntities } from "./data/graphData";
import type { AppData, Entity, Group, LinkRecord, ReviewItem, SearchResult } from "./data/graphData";
import { buildTreeGraph, membershipForEntityInGroup } from "./data/treeGraph";
import type { GraphEdge, GraphNode } from "./data/treeGraph";
import { cn } from "./lib/cn";
import { money, normalizeSearch } from "./lib/csv";

type ViewMode = "graph" | "table";
type TableTab = "grupos" | "entidades" | "vinculos" | "revisao";
type Selection =
  | { type: "entity"; id: string }
  | { type: "group"; id: string }
  | { type: "edge"; id: string };

const DEFAULT_ENTITY = appData.entities.find((entity) => entity.nome_canonico === "CARLOS ALMEIDA")?.entidade_id ?? appData.entities[0]?.entidade_id ?? "";
const GROUP_TYPES = ["TODOS", ...Array.from(new Set(appData.groups.map((group) => group.tipo_grupo))).sort()];

const toneClasses = {
  person: "border-emerald-300 bg-emerald-50 text-emerald-950",
  family: "border-amber-300 bg-amber-50 text-amber-950",
  business: "border-sky-300 bg-sky-50 text-sky-950",
  risk: "border-rose-300 bg-rose-50 text-rose-950",
  candidate: "border-zinc-300 bg-zinc-100 text-zinc-800",
  historic: "border-stone-300 bg-stone-100 text-stone-800",
  provisional: "border-dashed border-zinc-300 bg-white text-zinc-700",
  neutral: "border-zinc-300 bg-white text-zinc-800",
} as const;

const nodeFill = {
  person: "#ecfdf5",
  family: "#fffbeb",
  business: "#f0f9ff",
  risk: "#fff1f2",
  candidate: "#f4f4f5",
  historic: "#f5f5f4",
  provisional: "#ffffff",
  neutral: "#ffffff",
} as const;

const nodeStroke = {
  person: "#059669",
  family: "#d97706",
  business: "#0284c7",
  risk: "#e11d48",
  candidate: "#71717a",
  historic: "#78716c",
  provisional: "#a1a1aa",
  neutral: "#71717a",
} as const;

function short(value: string, length = 30): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function pct(value: string | number | undefined): string {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? `${numeric.toFixed(0)}%` : "0%";
}

function AppShell({
  children,
  activeEntity,
  viewMode,
  setViewMode,
}: {
  children: React.ReactNode;
  activeEntity?: Entity;
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
}) {
  const regulatoryGroups = appData.groups.filter((group) => group.grupo_regulatorio === "true").length;
  const candidateGroups = appData.groups.filter((group) => group.status_grupo === "CANDIDATO" || group.requer_revisao === "true").length;
  const dataCorte = appData.groups[0]?.data_corte ?? appData.aggregations[0]?.data_corte ?? "";

  return (
    <div className="min-h-[100dvh] bg-zinc-50 text-zinc-950">
      <div className="mx-auto grid min-h-[100dvh] w-full min-w-0 max-w-[1680px] grid-rows-[auto_1fr] gap-4 px-4 py-4 md:px-6">
        <header className="grid min-w-0 gap-4 border-b border-zinc-200 pb-4 lg:grid-cols-[1.1fr_1fr] lg:items-end">
          <div className="v-stack min-w-0 gap-3">
            <div className="h-stack w-fit items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
              <Network size={16} weight="duotone" />
              Rede explicável
            </div>
            <div className="v-stack gap-2">
              <h1 className="max-w-4xl break-words text-3xl font-semibold tracking-tight text-zinc-950 md:text-4xl">
                Grupos econômicos sobrepostos, em árvore navegável
              </h1>
              <p className="max-w-3xl text-sm leading-6 text-zinc-600">
                Núcleo ativo: <strong className="font-semibold text-zinc-900">{formatEntityName(activeEntity)}</strong>. A visualização preserva papéis, regras, fontes e revisão manual.
              </p>
            </div>
          </div>
          <div className="grid w-full min-w-0 grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-4">
            <Metric label="Entidades" value={String(appData.entities.length)} icon={<IdentificationCard size={18} />} />
            <Metric label="Grupos" value={String(appData.groups.length)} icon={<UsersThree size={18} />} />
            <Metric label="Regulatórios" value={String(regulatoryGroups)} icon={<Buildings size={18} />} />
            <Metric label="Revisão" value={String(candidateGroups)} icon={<Warning size={18} />} />
          </div>
          <div className="grid w-full min-w-0 grid-cols-1 gap-2 sm:flex sm:flex-wrap sm:items-center lg:col-span-2">
            <span className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-center text-xs font-medium text-zinc-600">Data de corte: {dataCorte}</span>
            <button
              className={cn("ui-button justify-center", viewMode === "graph" && "ui-button-active")}
              onClick={() => setViewMode("graph")}
              type="button"
            >
              <TreeStructure size={17} />
              Grafo
            </button>
            <button
              className={cn("ui-button justify-center", viewMode === "table" && "ui-button-active")}
              onClick={() => setViewMode("table")}
              type="button"
            >
              <Table size={17} />
              Tabelas
            </button>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg border border-zinc-200 bg-white px-3 py-3 shadow-[0_12px_34px_-28px_rgba(39,39,42,0.55)]">
      <div className="h-stack items-center gap-2 text-zinc-500">
        {icon}
        <span className="truncate text-xs font-medium">{label}</span>
      </div>
      <div className="mt-2 font-mono text-2xl font-semibold text-zinc-950">{value}</div>
    </div>
  );
}

export function App() {
  const [query, setQuery] = useState("");
  const [activeEntityId, setActiveEntityId] = useState(DEFAULT_ENTITY);
  const [selected, setSelected] = useState<Selection>({ type: "entity", id: DEFAULT_ENTITY });
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set([DEFAULT_ENTITY, `entity:${DEFAULT_ENTITY}`]));
  const [groupType, setGroupType] = useState("TODOS");
  const [maxDepth, setMaxDepth] = useState(3);
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [tableTab, setTableTab] = useState<TableTab>("grupos");

  const activeEntity = appData.entityById.get(activeEntityId);
  const searchResults = useMemo(() => {
    const results = searchEntities(appData, query);
    return results.sort((a, b) => {
      if (a.entity.entidade_id === activeEntityId) return -1;
      if (b.entity.entidade_id === activeEntityId) return 1;
      return b.score - a.score;
    });
  }, [activeEntityId, query]);
  const graph = useMemo(
    () =>
      buildTreeGraph(appData, {
        activeEntityId,
        expandedIds,
        groupType,
        maxDepth,
      }),
    [activeEntityId, expandedIds, groupType, maxDepth],
  );

  function centerEntity(entityId: string) {
    setActiveEntityId(entityId);
    setSelected({ type: "entity", id: entityId });
    setExpandedIds(new Set([entityId, `entity:${entityId}`]));
    setViewMode("graph");
  }

  function toggleExpansion(id: string) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function expandNextLevel() {
    setExpandedIds((current) => {
      const next = new Set(current);
      for (const node of graph.nodes) {
        if (node.depth <= maxDepth - 1) {
          next.add(node.id);
          if (node.entityId) next.add(node.entityId);
          if (node.groupId) next.add(node.groupId);
        }
      }
      return next;
    });
  }

  function collapseToCore() {
    setExpandedIds(new Set([activeEntityId, `entity:${activeEntityId}`]));
    setMaxDepth(3);
  }

  return (
    <AppShell activeEntity={activeEntity} viewMode={viewMode} setViewMode={setViewMode}>
      <main className="grid min-h-0 min-w-0 gap-4 overflow-hidden xl:grid-cols-[360px_minmax(0,1fr)_380px]">
        <SearchPanel
          query={query}
          setQuery={setQuery}
          results={searchResults}
          activeEntityId={activeEntityId}
          onSelect={centerEntity}
          groupType={groupType}
          setGroupType={setGroupType}
          maxDepth={maxDepth}
          setMaxDepth={setMaxDepth}
          expandNextLevel={expandNextLevel}
          collapseToCore={collapseToCore}
        />

        <section className="min-h-[620px] min-w-0 rounded-lg border border-zinc-200 bg-white shadow-[0_24px_80px_-60px_rgba(39,39,42,0.55)]">
          {viewMode === "graph" ? (
            <TreeView
              graph={graph}
              selected={selected}
              expandedIds={expandedIds}
              onNodeClick={(node) => {
                setSelected(node.kind === "entity" ? { type: "entity", id: node.entityId ?? "" } : { type: "group", id: node.groupId ?? "" });
                toggleExpansion(node.id);
                if (node.entityId) toggleExpansion(node.entityId);
                if (node.groupId) toggleExpansion(node.groupId);
              }}
              onEdgeClick={(edge) => setSelected({ type: "edge", id: edge.id })}
            />
          ) : (
            <TableMode
              data={appData}
              query={query}
              tab={tableTab}
              setTab={setTableTab}
              onSelectEntity={centerEntity}
              onSelectGroup={(groupId) => setSelected({ type: "group", id: groupId })}
            />
          )}
        </section>

        <DetailsPanel
          data={appData}
          selection={selected}
          activeEntityId={activeEntityId}
          expandedIds={expandedIds}
          onCenterEntity={centerEntity}
          onToggleExpansion={toggleExpansion}
          graphEdges={graph.edges}
        />
      </main>
    </AppShell>
  );
}

function SearchPanel({
  query,
  setQuery,
  results,
  activeEntityId,
  onSelect,
  groupType,
  setGroupType,
  maxDepth,
  setMaxDepth,
  expandNextLevel,
  collapseToCore,
}: {
  query: string;
  setQuery: (value: string) => void;
  results: SearchResult[];
  activeEntityId: string;
  onSelect: (entityId: string) => void;
  groupType: string;
  setGroupType: (value: string) => void;
  maxDepth: number;
  setMaxDepth: (value: number) => void;
  expandNextLevel: () => void;
  collapseToCore: () => void;
}) {
  return (
    <aside className="v-stack min-h-0 min-w-0 gap-4 overflow-hidden rounded-lg border border-zinc-200 bg-white p-4 shadow-[0_24px_80px_-64px_rgba(39,39,42,0.6)]">
      <div className="v-stack gap-2">
        <label className="break-words text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500" htmlFor="search">
          Buscar por CPF, CNPJ, nome, conta ou grupo
        </label>
        <div className="h-stack items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 focus-within:border-emerald-500 focus-within:bg-white">
          <MagnifyingGlass size={18} className="text-zinc-500" />
          <input
            id="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="w-full bg-transparent text-sm text-zinc-950 outline-none placeholder:text-zinc-400"
            placeholder="90000000175, Carlos, matrícula..."
          />
          {query ? (
            <button className="rounded-md p-1 text-zinc-500 transition hover:bg-zinc-200 active:translate-y-px" type="button" onClick={() => setQuery("")}>
              <X size={15} />
            </button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3">
        <label className="v-stack gap-2">
          <span className="h-stack items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">
            <FunnelSimple size={15} />
            Tipo de grupo
          </span>
          <select
            value={groupType}
            onChange={(event) => setGroupType(event.target.value)}
            className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm outline-none transition focus:border-emerald-500 focus:bg-white"
          >
            {GROUP_TYPES.map((type) => (
              <option value={type} key={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="v-stack gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Profundidade visual: {maxDepth}</span>
          <input
            type="range"
            min={2}
            max={5}
            value={maxDepth}
            onChange={(event) => setMaxDepth(Number(event.target.value))}
            className="accent-emerald-700"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <button className="ui-button justify-center" type="button" onClick={expandNextLevel}>
          <TreeStructure size={16} />
          Expandir
        </button>
        <button className="ui-button justify-center" type="button" onClick={collapseToCore}>
          <Rows size={16} />
          Núcleo
        </button>
      </div>

      <div className="v-stack min-h-0 gap-2">
        <div className="h-stack items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900">Resultados</h2>
          <span className="rounded-md bg-zinc-100 px-2 py-1 font-mono text-xs text-zinc-500">{results.length}</span>
        </div>
        <div className="v-stack max-h-[520px] gap-2 overflow-y-auto pr-1">
          {results.length === 0 ? (
            <div className="rounded-lg border border-dashed border-zinc-300 p-4 text-sm leading-6 text-zinc-500">
              Nenhuma entidade encontrada. Busque por documento, nome, matrícula, risco ou identificador de grupo.
            </div>
          ) : (
            results.map((result) => (
              <button
                key={result.entity.entidade_id}
                type="button"
                onClick={() => onSelect(result.entity.entidade_id)}
                className={cn(
                  "v-stack gap-2 rounded-lg border p-3 text-left transition duration-200 hover:-translate-y-0.5 hover:border-emerald-400 hover:bg-emerald-50/50 active:translate-y-px",
                  activeEntityId === result.entity.entidade_id ? "border-emerald-500 bg-emerald-50" : "border-zinc-200 bg-white",
                )}
              >
                <div className="h-stack items-start gap-2">
                  <span className={cn("mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full", result.entity.tipo_entidade.startsWith("PJ") ? "bg-sky-600" : "bg-emerald-600")} />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-zinc-950">{formatEntityName(result.entity)}</div>
                    <div className="font-mono text-xs text-zinc-500">{result.entity.cpf_cnpj || result.entity.entidade_id}</div>
                  </div>
                </div>
                <div className="h-stack flex-wrap gap-1">
                  <Pill>{result.entity.tipo_entidade}</Pill>
                  {result.bank?.num_matricula ? <Pill>mat. {result.bank.num_matricula}</Pill> : null}
                  {result.groups[0] ? <Pill>{result.groups[0].tipo_grupo}</Pill> : null}
                </div>
                <span className="text-xs text-zinc-500">{result.reason}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}

function TreeView({
  graph,
  selected,
  expandedIds,
  onNodeClick,
  onEdgeClick,
}: {
  graph: ReturnType<typeof buildTreeGraph>;
  selected: Selection;
  expandedIds: Set<string>;
  onNodeClick: (node: GraphNode) => void;
  onEdgeClick: (edge: GraphEdge) => void;
}) {
  const selectedNodeId = selected.type === "entity" ? `entity:${selected.id}` : selected.type === "group" ? `group:${selected.id}` : "";

  return (
    <div className="v-stack h-full min-h-[620px]">
      <div className="h-stack items-center justify-between border-b border-zinc-200 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-950">Árvore de vínculos</h2>
          <p className="text-xs text-zinc-500">Clique nos nós para expandir e ver detalhes. Linhas também são clicáveis.</p>
        </div>
        <div className="h-stack gap-2 text-xs text-zinc-500">
          <Legend tone="person" label="PF" />
          <Legend tone="business" label="PJ" />
          <Legend tone="family" label="Família" />
          <Legend tone="risk" label="Risco" />
        </div>
      </div>
      <div className="relative min-h-0 grow overflow-auto bg-[linear-gradient(#f4f4f5_1px,transparent_1px),linear-gradient(90deg,#f4f4f5_1px,transparent_1px)] bg-[size:28px_28px]">
        <svg width={graph.width} height={graph.height} viewBox={`0 0 ${graph.width} ${graph.height}`} className="block">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#a1a1aa" />
            </marker>
          </defs>
          {graph.edges.map((edge) => {
            const source = graph.nodes.find((node) => node.id === edge.source);
            const target = graph.nodes.find((node) => node.id === edge.target);
            if (!source || !target) return null;
            const midX = (source.x + target.x) / 2;
            const midY = (source.y + target.y) / 2;
            const path = `M ${source.x + source.size / 2} ${source.y} C ${midX} ${source.y}, ${midX} ${target.y}, ${target.x - target.size / 2} ${target.y}`;
            const active = selected.type === "edge" && selected.id === edge.id;
            return (
              <g key={edge.id} className="cursor-pointer" onClick={() => onEdgeClick(edge)}>
                <path
                  d={path}
                  fill="none"
                  stroke={active ? "#047857" : edge.kind === "relationship" ? "#a1a1aa" : "#d4d4d8"}
                  strokeWidth={active ? 2.6 : 1.6}
                  strokeDasharray={edge.kind === "group-relation" ? "6 6" : edge.kind === "relationship" ? "0" : "3 5"}
                  markerEnd="url(#arrow)"
                />
                <rect x={midX - 54} y={midY - 12} width={108} height={22} rx={7} fill="#ffffff" stroke="#e4e4e7" />
                <text x={midX} y={midY + 4} textAnchor="middle" className="fill-zinc-500 text-[10px] font-medium">
                  {short(edge.label, 16)}
                </text>
              </g>
            );
          })}
          {graph.nodes.map((node) => {
            const isSelected = selectedNodeId === node.id;
            const isExpanded = expandedIds.has(node.id) || (node.entityId ? expandedIds.has(node.entityId) : false) || (node.groupId ? expandedIds.has(node.groupId) : false);
            const stroke = nodeStroke[node.tone as keyof typeof nodeStroke] ?? nodeStroke.neutral;
            const fill = nodeFill[node.tone as keyof typeof nodeFill] ?? nodeFill.neutral;
            return (
              <g key={node.id} transform={`translate(${node.x}, ${node.y})`} className="cursor-pointer" onClick={() => onNodeClick(node)}>
                {node.kind === "group" ? (
                  <rect
                    x={-92}
                    y={-32}
                    width={184}
                    height={64}
                    rx={8}
                    fill={fill}
                    stroke={isSelected ? "#18181b" : stroke}
                    strokeWidth={isSelected ? 2.8 : node.requiresReview ? 2 : 1.4}
                    strokeDasharray={node.requiresReview ? "5 4" : "0"}
                  />
                ) : (
                  <circle
                    r={node.size / 2}
                    fill={fill}
                    stroke={isSelected ? "#18181b" : stroke}
                    strokeWidth={isSelected ? 2.8 : node.requiresReview ? 2 : 1.4}
                    strokeDasharray={node.requiresReview ? "5 4" : "0"}
                  />
                )}
                {node.kind === "group" ? (
                  <>
                    <text x={0} y={-4} textAnchor="middle" className="fill-zinc-950 text-[12px] font-semibold">
                      {short(node.label, 24)}
                    </text>
                    <text x={0} y={14} textAnchor="middle" className="fill-zinc-500 text-[10px] font-medium">
                      {short(node.subtitle, 28)}
                    </text>
                    <g transform="translate(72, -22)">
                      <circle r={10} fill={isExpanded ? "#047857" : "#ffffff"} stroke="#d4d4d8" />
                      <text y={4} textAnchor="middle" className={cn("text-[12px] font-bold", isExpanded ? "fill-white" : "fill-zinc-500")}>
                        {isExpanded ? "−" : "+"}
                      </text>
                    </g>
                  </>
                ) : (
                  <>
                    <text x={0} y={node.size / 2 + 18} textAnchor="middle" className="fill-zinc-950 text-[12px] font-semibold">
                      {short(node.label, 22)}
                    </text>
                    <text x={0} y={node.size / 2 + 34} textAnchor="middle" className="fill-zinc-500 text-[10px] font-medium">
                      {short(node.subtitle, 26)}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </svg>
        {graph.nodes.length === 0 ? (
          <div className="center absolute inset-0 p-8 text-center text-sm text-zinc-500">Nenhum vínculo encontrado para os filtros atuais.</div>
        ) : null}
      </div>
    </div>
  );
}

function DetailsPanel({
  data,
  selection,
  activeEntityId,
  expandedIds,
  onCenterEntity,
  onToggleExpansion,
  graphEdges,
}: {
  data: AppData;
  selection: Selection;
  activeEntityId: string;
  expandedIds: Set<string>;
  onCenterEntity: (entityId: string) => void;
  onToggleExpansion: (id: string) => void;
  graphEdges: GraphEdge[];
}) {
  if (selection.type === "group") {
    const group = data.groupById.get(selection.id);
    if (!group) return <EmptyDetails />;
    const aggregation = data.aggregationByGroupId.get(group.grupo_id);
    const members = data.membersByGroup.get(group.grupo_id) ?? [];
    const expanded = expandedIds.has(`group:${group.grupo_id}`) || expandedIds.has(group.grupo_id);
    return (
      <aside className="detail-panel">
        <PanelTitle icon={<UsersThree size={18} />} title={group.nome_grupo} subtitle={group.tipo_grupo} />
        <div className="h-stack flex-wrap gap-2">
          <ToneBadge tone={groupTone(group.tipo_grupo)}>{group.grupo_id}</ToneBadge>
          <Pill>{group.status_grupo}</Pill>
          {group.grupo_regulatorio === "true" ? <ToneBadge tone="risk">regulatório</ToneBadge> : <Pill>não regulatório</Pill>}
          {group.requer_revisao === "true" ? <ToneBadge tone="candidate">revisão</ToneBadge> : null}
        </div>
        <button className="ui-button justify-center" type="button" onClick={() => onToggleExpansion(`group:${group.grupo_id}`)}>
          <TreeStructure size={16} />
          {expanded ? "Recolher nó" : "Expandir membros"}
        </button>
        <InfoGrid
          rows={[
            ["Corte", group.data_corte],
            ["Confiança", pct(group.confianca_grupo)],
            ["Core", group.quantidade_membros_core],
            ["Associados", group.quantidade_membros_associados],
            ["Candidatos", group.quantidade_candidatos],
            ["Motivo revisão", group.motivo_revisao || "sem apontamento"],
          ]}
        />
        {aggregation ? (
          <Section title="Agregação financeira">
            <InfoGrid
              rows={[
                ["Saldo total", money(aggregation.saldo_total)],
                ["Exposição PF", money(aggregation.exposicao_pf)],
                ["Exposição PJ", money(aggregation.exposicao_pj)],
                ["Pior risco", aggregation.pior_faixa_risco || "sem faixa"],
                ["Contas ativas", aggregation.quantidade_contas_ativas],
                ["Membros falecidos", aggregation.quantidade_membros_falecidos],
              ]}
            />
            <p className="text-xs leading-5 text-zinc-500">{aggregation.observacao_sobreposicao}</p>
          </Section>
        ) : null}
        <Section title="Membros principais">
          <div className="v-stack gap-2">
            {members.slice(0, 12).map((member) => {
              const entity = data.entityById.get(member.entidade_id);
              return (
                <button key={`${member.entidade_id}-${member.papel_no_grupo}`} className="detail-row text-left" type="button" onClick={() => entity && onCenterEntity(entity.entidade_id)}>
                  <span>
                    <strong>{formatEntityName(entity)}</strong>
                    <small>{member.papel_no_grupo} · {member.nivel_membro}</small>
                  </span>
                  <CaretRight size={15} />
                </button>
              );
            })}
          </div>
        </Section>
      </aside>
    );
  }

  if (selection.type === "edge") {
    const edge = graphEdges.find((item) => item.id === selection.id);
    const link = edge?.linkId ? data.links.find((item) => item.vinculo_id === edge.linkId) : undefined;
    return (
      <aside className="detail-panel">
        <PanelTitle icon={<LinkSimple size={18} />} title={edge?.label ?? "Relação entre grupos"} subtitle={edge?.kind ?? "vínculo"} />
        {link ? <LinkDetails link={link} data={data} /> : <InfoGrid rows={[["Confiança", pct(edge?.confidence)], ["Relevância", pct(edge?.relevance)], ["Tipo", edge?.kind ?? ""]]} />}
      </aside>
    );
  }

  const entity = data.entityById.get(selection.id);
  if (!entity) return <EmptyDetails />;
  const bank = data.bankByDoc.get(entity.cpf_cnpj);
  const memberships = data.membersByEntity.get(entity.entidade_id) ?? [];
  const links = data.linksByEntity.get(entity.entidade_id) ?? [];
  const reviews = data.reviewsByObject.get(entity.entidade_id) ?? [];
  const expanded = expandedIds.has(`entity:${entity.entidade_id}`) || expandedIds.has(entity.entidade_id);

  return (
    <aside className="detail-panel">
      <PanelTitle icon={<IdentificationCard size={18} />} title={formatEntityName(entity)} subtitle={`${entity.tipo_entidade} · ${entity.status_entidade}`} />
      <div className="h-stack flex-wrap gap-2">
        <ToneBadge tone={entity.tipo_entidade.startsWith("PJ") ? "business" : "person"}>{entity.cpf_cnpj || entity.entidade_id}</ToneBadge>
        {entity.entidade_provisoria === "true" ? <ToneBadge tone="provisional">provisória</ToneBadge> : null}
        {entity.alertas ? <ToneBadge tone="candidate">alertas</ToneBadge> : null}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button className="ui-button justify-center" type="button" onClick={() => onCenterEntity(entity.entidade_id)} disabled={activeEntityId === entity.entidade_id}>
          <Eye size={16} />
          Centralizar
        </button>
        <button className="ui-button justify-center" type="button" onClick={() => onToggleExpansion(`entity:${entity.entidade_id}`)}>
          <TreeStructure size={16} />
          {expanded ? "Recolher" : "Expandir"}
        </button>
      </div>
      <InfoGrid
        rows={[
          ["Nascimento", entity.data_nascimento || "não informado"],
          ["Óbito", entity.data_obito || "não informado"],
          ["Documento válido", entity.documento_valido === "true" ? "sim" : "não"],
          ["Fonte principal", entity.fonte_principal],
          ["Atualização", entity.data_atualizacao || "sem data"],
          ["Alertas", entity.alertas || "sem alertas"],
        ]}
      />
      {bank ? (
        <Section title="Cadastro bancário">
          <InfoGrid
            rows={[
              ["Matrícula", bank.num_matricula || "não informada"],
              ["Conta", bank.status_conta || "não informada"],
              ["Conglomerado fonte", bank.cod_conglomerado || "sem código"],
              ["Faixa risco", bank.faixa_risco || "sem faixa"],
              ["Saldo", money(bank.saldo)],
            ]}
          />
        </Section>
      ) : null}
      <Section title="Grupos vinculados">
        <div className="v-stack gap-2">
          {memberships.slice(0, 10).map((member) => {
            const group = data.groupById.get(member.grupo_id);
            return (
              <button key={`${member.grupo_id}-${member.papel_no_grupo}`} className="detail-row text-left" type="button" onClick={() => group && onToggleExpansion(`group:${group.grupo_id}`)}>
                <span>
                  <strong>{group?.nome_grupo ?? member.grupo_id}</strong>
                  <small>{member.papel_no_grupo} · {member.nivel_membro}</small>
                </span>
                <CaretRight size={15} />
              </button>
            );
          })}
        </div>
      </Section>
      <Section title="Vínculos diretos">
        <div className="v-stack gap-2">
          {links.slice(0, 8).map((link) => {
            const otherId = link.entidade_origem === entity.entidade_id ? link.entidade_destino : link.entidade_origem;
            return (
              <button key={link.vinculo_id} className="detail-row text-left" type="button" onClick={() => data.entityById.has(otherId) && onCenterEntity(otherId)}>
                <span>
                  <strong>{formatEntityName(data.entityById.get(otherId))}</strong>
                  <small>{link.tipo_vinculo} · {link.codigo_regra}</small>
                </span>
                <CaretRight size={15} />
              </button>
            );
          })}
        </div>
      </Section>
      {reviews.length ? (
        <Section title="Fila de revisão">
          <ReviewList reviews={reviews.slice(0, 4)} />
        </Section>
      ) : null}
    </aside>
  );
}

function LinkDetails({ link, data }: { link: LinkRecord; data: AppData }) {
  return (
    <div className="v-stack gap-4">
      <InfoGrid
        rows={[
          ["Origem", formatEntityName(data.entityById.get(link.entidade_origem))],
          ["Destino", formatEntityName(data.entityById.get(link.entidade_destino))],
          ["Confiança", pct(link.confianca_vinculo)],
          ["Regra", link.codigo_regra],
          ["Fonte", link.arquivo_fonte],
          ["Revisão", link.requer_revisao === "true" ? "sim" : "não"],
          ["Participação", link.percentual_participacao || "não aplicável"],
        ]}
      />
      <Section title="Evidências">
        <p className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs leading-5 text-zinc-600">{link.evidencias}</p>
      </Section>
    </div>
  );
}

function TableMode({
  data,
  query,
  tab,
  setTab,
  onSelectEntity,
  onSelectGroup,
}: {
  data: AppData;
  query: string;
  tab: TableTab;
  setTab: (tab: TableTab) => void;
  onSelectEntity: (entityId: string) => void;
  onSelectGroup: (groupId: string) => void;
}) {
  const term = normalizeSearch(query);
  const groupRows = data.groups.filter((group) => normalizeSearch(Object.values(group).join(" ")).includes(term)).slice(0, 100);
  const entityRows = data.entities.filter((entity) => normalizeSearch(Object.values(entity).join(" ")).includes(term)).slice(0, 100);
  const linkRows = data.links.filter((link) => normalizeSearch(Object.values(link).join(" ")).includes(term)).slice(0, 100);
  const reviewRows = data.reviews.filter((review) => normalizeSearch(Object.values(review).join(" ")).includes(term)).slice(0, 100);

  return (
    <div className="v-stack h-full min-h-[620px]">
      <div className="h-stack flex-wrap items-center gap-2 border-b border-zinc-200 px-4 py-3">
        {[
          ["grupos", "Grupos"],
          ["entidades", "Entidades"],
          ["vinculos", "Vínculos"],
          ["revisao", "Revisão"],
        ].map(([id, label]) => (
          <button key={id} type="button" className={cn("ui-button", tab === id && "ui-button-active")} onClick={() => setTab(id as TableTab)}>
            <Rows size={16} />
            {label}
          </button>
        ))}
      </div>
      <div className="min-h-0 grow overflow-auto">
        {tab === "grupos" ? (
          <DataTable
            headers={["Grupo", "Tipo", "Membros", "Regulatório", "Exposição", "Revisão"]}
            rows={groupRows.map((group) => {
              const aggregation = data.aggregationByGroupId.get(group.grupo_id);
              return [
                <button className="table-link" onClick={() => onSelectGroup(group.grupo_id)} type="button">{group.nome_grupo}</button>,
                group.tipo_grupo,
                `${group.quantidade_membros_core}/${group.quantidade_membros_associados}/${group.quantidade_candidatos}`,
                group.grupo_regulatorio === "true" ? "sim" : "não",
                aggregation ? money(Number(aggregation.exposicao_pf) + Number(aggregation.exposicao_pj)) : "sem dado",
                group.motivo_revisao || "sem revisão",
              ];
            })}
          />
        ) : null}
        {tab === "entidades" ? (
          <DataTable
            headers={["Entidade", "Tipo", "Documento", "Conta", "Grupos", "Alertas"]}
            rows={entityRows.map((entity) => {
              const bank = data.bankByDoc.get(entity.cpf_cnpj);
              return [
                <button className="table-link" onClick={() => onSelectEntity(entity.entidade_id)} type="button">{formatEntityName(entity)}</button>,
                entity.tipo_entidade,
                entity.cpf_cnpj || entity.entidade_id,
                bank?.num_matricula || bank?.status_conta || "sem conta",
                String(groupsForEntity(data, entity.entidade_id).length),
                entity.alertas || "sem alertas",
              ];
            })}
          />
        ) : null}
        {tab === "vinculos" ? (
          <DataTable
            headers={["Tipo", "Origem", "Destino", "Confiança", "Regra", "Fonte"]}
            rows={linkRows.map((link) => [
              link.tipo_vinculo,
              formatEntityName(data.entityById.get(link.entidade_origem)),
              formatEntityName(data.entityById.get(link.entidade_destino)),
              pct(link.confianca_vinculo),
              link.codigo_regra,
              link.arquivo_fonte,
            ])}
          />
        ) : null}
        {tab === "revisao" ? (
          <DataTable
            headers={["Severidade", "Alerta", "Objeto", "Descrição", "Ação"]}
            rows={reviewRows.map((review) => [review.severidade, review.codigo_alerta, review.objeto_id, review.descrição, review["ação recomendada"]])}
          />
        ) : null}
      </div>
    </div>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: React.ReactNode[][] }) {
  return (
    <table className="w-full min-w-[860px] border-collapse text-left text-sm">
      <thead className="sticky top-0 bg-zinc-100 text-xs uppercase tracking-[0.14em] text-zinc-500">
        <tr>
          {headers.map((header) => (
            <th key={header} className="border-b border-zinc-200 px-4 py-3 font-semibold">
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-zinc-100">
        {rows.length ? (
          rows.map((row, index) => (
            <tr key={index} className="transition hover:bg-emerald-50/40">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="max-w-[360px] px-4 py-3 align-top text-zinc-700">
                  {cell}
                </td>
              ))}
            </tr>
          ))
        ) : (
          <tr>
            <td className="px-4 py-12 text-center text-zinc-500" colSpan={headers.length}>
              Nenhum registro encontrado para o filtro atual.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function PanelTitle({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <div className="v-stack gap-2">
      <div className="h-stack h-9 w-9 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-700">{icon}</div>
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-950">{title}</h2>
        <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>
      </div>
    </div>
  );
}

function InfoGrid({ rows }: { rows: Array<[string, React.ReactNode]> }) {
  return (
    <div className="grid grid-cols-1 overflow-hidden rounded-lg border border-zinc-200">
      {rows.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[120px_1fr] gap-3 border-b border-zinc-100 px-3 py-2 last:border-b-0">
          <dt className="text-xs font-medium text-zinc-500">{label}</dt>
          <dd className="min-w-0 break-words text-xs font-medium leading-5 text-zinc-800">{value}</dd>
        </div>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="v-stack gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">{title}</h3>
      {children}
    </section>
  );
}

function ReviewList({ reviews }: { reviews: ReviewItem[] }) {
  return (
    <div className="v-stack gap-2">
      {reviews.map((review) => (
        <div key={`${review.codigo_alerta}-${review.objeto_id}`} className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <div className="h-stack items-center justify-between gap-2">
            <strong className="text-xs text-amber-950">{review.codigo_alerta}</strong>
            <span className="rounded-md bg-white px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-700">{review.severidade}</span>
          </div>
          <p className="mt-2 text-xs leading-5 text-amber-900">{review.descrição}</p>
        </div>
      ))}
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return <span className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] font-medium text-zinc-600">{children}</span>;
}

function ToneBadge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={cn("rounded-md border px-2 py-1 text-[11px] font-semibold", toneClasses[tone as keyof typeof toneClasses] ?? toneClasses.neutral)}>{children}</span>;
}

function Legend({ tone, label }: { tone: keyof typeof nodeStroke; label: string }) {
  return (
    <span className="h-stack items-center gap-1">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: nodeStroke[tone] }} />
      {label}
    </span>
  );
}

function EmptyDetails() {
  return (
    <aside className="detail-panel center text-center">
      <div className="v-stack max-w-xs items-center gap-3">
        <Network size={32} className="text-zinc-400" />
        <p className="text-sm leading-6 text-zinc-500">Selecione uma entidade, grupo ou vínculo para ver a rastreabilidade completa.</p>
      </div>
    </aside>
  );
}
