import { MagnifyingGlass, Network, Eye, ArrowsOut, ArrowsIn, House } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent, WheelEvent } from "react";
import type {
  ApiMeta,
  EntityDetailResponse,
  EntityNode,
  RelationItem,
  SearchItem,
  SearchResponse,
  TreeResponse,
} from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchMetadata,
  fetchSearch,
  fetchTree,
  fetchTreeBranch,
} from "./lib/api";
import "./styles.css";

type TreeNodeLayout = EntityNode & {
  x: number;
  y: number;
};

type TreeState = {
  rootId: string;
  nodes: Map<string, EntityNode>;
  relations: Map<string, RelationItem>;
};

const HUMAN_RELATION_LABEL: Record<string, string> = {
  FILHO_DE: "pai/mãe",
  PAI_DE: "filho(a)",
  MAE_DE: "filho(a)",
  IRMAO_DE: "irmão(a)",
  CONJUGE_DE: "cônjuge",
  CONJUGE_NOME_CANDIDATO: "cônjuge candidato",
  SOCIO_DE: "sócio",
  CONTROLADOR_DIRETO: "controlador",
  CONTROLADOR_CONJUNTO_CANDIDATO: "controle conjunto",
  INFLUENCIA_RELEVANTE: "sócio com influência",
  SOCIO_MINORITARIO: "sócio minoritário",
  TRANSFERIU_PARA: "fluxo financeiro",
  DEPENDENCIA_FINANCEIRA_CANDIDATA: "dependência econômica",
  ENDERECO_COMPARTILHADO: "endereço em comum",
  CONTATO_COMPARTILHADO: "contato compartilhado",
  EMPREGADO_DE: "emprego",
  TIO_TIA_DE: "tio/zia",
  ESPOLIO_DE: "espólio",
  PARENTESCO_AMBIGUO: "parentesco em revisão",
  POSSIVEL_MESMO_GENITOR: "parentesco em revisão",
  PARTICIPACAO_INDIRETA: "participação societária indireta",
};

const HORIZONTAL_GAP = 240;
const VERTICAL_GAP = 200;

function relationLabel(type: string): string {
  return HUMAN_RELATION_LABEL[type] ?? type.toLowerCase().split("_").join(" ");
}

function entityTypeLabel(tipo: string): string {
  if (tipo === "PF") return "Pessoa física";
  if (tipo === "PJ") return "Empresa";
  if (tipo === "PF_EXTERNA") return "Pessoa física (externa)";
  if (tipo === "PJ_EXTERNA") return "Empresa (externa)";
  if (tipo === "ESPOLIO") return "Espólio";
  return tipo;
}

function getStatusLabel(status: string): string {
  if (status === "ATIVO") return "Ativo";
  if (status === "HISTORICO") return "Histórico";
  return status || "Sem status";
}

function statusToTone(status: string): string {
  if (status === "ATIVO") return "ring-emerald-300 bg-emerald-50 text-emerald-950";
  if (status === "HISTORICO") return "ring-stone-300 bg-stone-50 text-stone-900";
  return "ring-zinc-300 bg-zinc-50 text-zinc-900";
}

function normalizeLabel(label: string): string {
  return label.toLocaleLowerCase("pt-BR");
}

export function App() {
  const [query, setQuery] = useState("");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchBusyMore, setSearchBusyMore] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchItem[]>([]);
  const [meta, setMeta] = useState<ApiMeta | null>(null);

  const [selectedEntityId, setSelectedEntityId] = useState("PF:90000000175");
  const [selectedDetail, setSelectedDetail] = useState<EntityDetailResponse | null>(null);

  const [tree, setTree] = useState<TreeState>({
    rootId: "PF:90000000175",
    nodes: new Map(),
    relations: new Map(),
  });
  const [loadingTree, setLoadingTree] = useState(false);
  const [error, setError] = useState<string>("");

  const [maxDepth, setMaxDepth] = useState(2);
  const [maxPerNode, setMaxPerNode] = useState(10);
  const [includeIndirect, setIncludeIndirect] = useState(false);

  const [viewport, setViewport] = useState({ x: 20, y: 20, scale: 1 });
  const [dragging, setDragging] = useState(false);
  const [dragPoint, setDragPoint] = useState({ x: 0, y: 0 });

  const canvasRef = useRef<HTMLDivElement>(null);

  const treeNodes = useMemo(() => Array.from(tree.nodes.values()), [tree]);

  const layout = useMemo(() => {
    const byDepth = new Map<number, string[]>();
    for (const node of treeNodes) {
      const list = byDepth.get(node.depth) ?? [];
      list.push(node.id);
      byDepth.set(node.depth, list);
    }

    const depths = Array.from(byDepth.keys()).sort((a, b) => a - b);
    if (depths.length === 0) {
      return {
        nodes: [] as TreeNodeLayout[],
        height: VERTICAL_GAP,
        width: 1000,
        minY: 0,
        minDepth: 0,
      };
    }

    const minDepth = depths[0];
    const maxDepthValue = depths[depths.length - 1];

    const layoutNodes: TreeNodeLayout[] = [];
    let maxPerRow = 0;

    for (const depth of depths) {
      const ids = byDepth.get(depth) ?? [];
      maxPerRow = Math.max(maxPerRow, ids.length);
      for (let index = 0; index < ids.length; index += 1) {
        const node = tree.nodes.get(ids[index]);
        if (!node) {
          continue;
        }

        const y = (depth - minDepth) * VERTICAL_GAP + 50;
        const rowCount = ids.length;
        const startX = -((rowCount - 1) * HORIZONTAL_GAP) / 2;
        const x = startX + index * HORIZONTAL_GAP;
        layoutNodes.push({
          ...node,
          x,
          y,
        });
      }
    }

    return {
      nodes: layoutNodes,
      width: Math.max(900, maxPerRow * HORIZONTAL_GAP + 320),
      height: (maxDepthValue - minDepth + 1) * VERTICAL_GAP + 220,
      minY: 0,
      minDepth,
    };
  }, [treeNodes, tree.nodes]);

  const nodeLookup = useMemo(() => {
    const map = new Map<string, TreeNodeLayout>();
    for (const node of layout.nodes) {
      map.set(node.id, node);
    }
    return map;
  }, [layout.nodes]);

  const clearError = () => setError("");

  const performSearch = useCallback(
    async (term: string, offset = 0, append = false) => {
      if (!term || term.length < 2) {
        if (!append) {
          setSearchResult([]);
        }
        return;
      }
      clearError();
      if (append) setSearchBusyMore(true);
      else setSearchBusy(true);

      try {
        const response: SearchResponse = await fetchSearch({
          q: term,
          limit: 20,
          offset,
          tipo: undefined,
          include_external: true,
        });

        setSearchResult((current) => {
          if (append) {
            const map = new Map<string, SearchItem>(current.map((item) => [item.entidade_id, item]));
            for (const item of response.items) {
              map.set(item.entidade_id, item);
            }
            return [...map.values()].slice(0, 30);
          }
          return response.items;
        });
      } catch {
        if (!append) {
          setSearchResult([]);
        }
      } finally {
        setSearchBusy(false);
        setSearchBusyMore(false);
      }
    },
    [],
  );

  const loadMetadata = useCallback(async () => {
    try {
      const data = await fetchMetadata();
      setMeta(data);
    } catch {
      setMeta(null);
    }
  }, []);

  const normalizeRelationDirection = useCallback((node: TreeNodeLayout) => {
    if (node.depth < 0) return "ascendente";
    if (node.depth > 0) return "descendente";
    return "referência";
  }, []);

  const loadTree = useCallback(
    async (rootId: string, merge = false) => {
      clearError();
      setLoadingTree(true);

      try {
        const payload = await fetchTree({
          entidade_id: rootId,
          max_depth: maxDepth,
          include_indirect: includeIndirect,
          max_per_node: maxPerNode,
        });

        const nextNodes = new Map<string, EntityNode>();
        const nextRelations = new Map<string, RelationItem>(merge ? tree.relations : []);

        if (merge && rootId === tree.rootId) {
          for (const node of tree.nodes.values()) {
            nextNodes.set(node.id, node);
          }
        }

        let rootDepth = 0;
        if (merge) {
          const existingRoot = nextNodes.get(rootId);
          if (existingRoot) {
            rootDepth = existingRoot.depth;
          }
        }

        for (const node of payload.nodes) {
          if (!merge || node.id === tree.rootId) {
            nextNodes.set(node.id, node);
            continue;
          }

          const shifted: EntityNode = {
            ...node,
            depth: rootDepth + node.depth,
          };
          const current = nextNodes.get(node.id);
          if (!current || Math.abs(shifted.depth) < Math.abs(current.depth)) {
            nextNodes.set(node.id, shifted);
          }
        }

        for (const rel of payload.relations) {
          nextRelations.set(`${rel.id}:${rel.source}:${rel.target}`, rel);
        }

        setTree((current) => {
          if (!merge) {
            return {
              rootId,
              nodes: new Map(payload.nodes.map((node) => [node.id, node])),
              relations: new Map(payload.relations.map((rel) => [`${rel.id}:${rel.source}:${rel.target}`, rel])),
            };
          }

          if (tree.rootId === rootId) {
            const changed = new Map(current.nodes);
            for (const node of nextNodes.values()) {
              changed.set(node.id, node);
            }
            return {
              ...current,
              nodes: changed,
              relations: nextRelations,
            };
          }

          const changed = new Map(current.nodes);
          const targetDepth = current.nodes.get(rootId)?.depth ?? 0;
          for (const node of payload.nodes) {
            const shifted = { ...node, depth: targetDepth + node.depth };
            const currentNode = changed.get(shifted.id);
            if (!currentNode || Math.abs(shifted.depth) < Math.abs(currentNode.depth)) {
              changed.set(shifted.id, shifted);
            }
          }

          return {
            ...current,
            relations: nextRelations,
            nodes: changed,
            rootId: current.rootId,
          };
        });

        setSelectedEntityId(rootId);
      } catch (err) {
        setError("Erro ao carregar árvore. Verifique se o backend está disponível em /api.");
      } finally {
        setLoadingTree(false);
      }
    },
    [includeIndirect, maxDepth, maxPerNode, tree.nodes, tree.relations, tree.rootId],
  );

  const loadNodeDetail = useCallback(
    async (entityId: string) => {
      try {
        const detail = await fetchEntityDetail(entityId);
        setSelectedDetail(detail);
      } catch {
        setSelectedDetail(null);
      }
    },
    [],
  );

  const openBranch = useCallback(
    async (entityId: string) => {
      const anchor = tree.nodes.get(entityId);
      if (!anchor) {
        return;
      }

      const payload = await fetchTreeBranch({
        entidade_id: entityId,
        max_depth: 2,
        include_indirect: includeIndirect,
        max_per_node: maxPerNode,
      });

      setTree((current) => {
        const nextNodes = new Map(current.nodes);
        const nextRelations = new Map(current.relations);
        const anchorDepth = current.nodes.get(entityId)?.depth ?? 0;

        for (const node of payload.nodes) {
          const finalDepth = node.id === entityId ? anchorDepth : anchorDepth + node.depth;
          const existing = nextNodes.get(node.id);
          const normalized = {
            ...node,
            depth: finalDepth,
          };

          if (!existing || Math.abs(normalized.depth) < Math.abs(existing.depth)) {
            nextNodes.set(node.id, normalized);
          }
        }

        for (const rel of payload.relations) {
          nextRelations.set(`${rel.id}:${rel.source}:${rel.target}`, rel);
        }

        return {
          ...current,
          nodes: nextNodes,
          relations: nextRelations,
        };
      });
    },
    [includeIndirect, maxPerNode, tree.nodes],
  );

  const handleSelectEntity = useCallback(
    async (entityId: string) => {
      setSelectedEntityId(entityId);
      await loadTree(entityId, false);
      void loadNodeDetail(entityId);
    },
    [loadTree, loadNodeDetail],
  );

  useEffect(() => {
    clearError();
    void fetchHealth().then(() => {
      loadMetadata();
    }).catch(() => {
      setError("Backend indisponível. Rode a API com npm run backend.");
    });
  }, [loadMetadata]);

  useEffect(() => {
    if (!query) {
      setSearchResult([]);
      return;
    }

    const timeout = setTimeout(() => {
      void performSearch(query);
    }, 300);

    return () => clearTimeout(timeout);
  }, [query, performSearch]);

  useEffect(() => {
    void handleSelectEntity(selectedEntityId);
  }, [selectedEntityId, maxDepth, includeIndirect, maxPerNode]);

  useEffect(() => {
    if (!selectedEntityId) {
      return;
    }
    void loadNodeDetail(selectedEntityId);
  }, [selectedEntityId, loadNodeDetail]);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("[data-no-drag]") !== null) {
      return;
    }
    setDragging(true);
    setDragPoint({ x: event.clientX, y: event.clientY });
    (event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    const dx = event.clientX - dragPoint.x;
    const dy = event.clientY - dragPoint.y;
    setDragPoint({ x: event.clientX, y: event.clientY });
    setViewport((current) => ({
      ...current,
      x: current.x + dx,
      y: current.y + dy,
    }));
  };

  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    setDragging(false);
    (event.currentTarget as HTMLDivElement).releasePointerCapture(event.pointerId);
  };

  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const delta = event.deltaY < 0 ? 0.08 : -0.08;
    setViewport((current) => {
      const next = Math.min(2, Math.max(0.35, current.scale + delta));
      return { ...current, scale: next };
    });
  };

  const visibleRelations = useMemo(() => {
    const rows: Array<{
      from: EntityNode & { x: number; y: number };
      to: EntityNode & { x: number; y: number };
      relation: RelationItem;
    }> = [];

    for (const relation of tree.relations.values()) {
      const from = nodeLookup.get(relation.source);
      const to = nodeLookup.get(relation.target);
      if (!from || !to) continue;
      rows.push({ from, to, relation });
    }
    return rows;
  }, [nodeLookup, tree.relations]);

  const root = tree.nodes.get(tree.rootId);

  const topStats = meta
    ? `${meta.total_entidades.toLocaleString("pt-BR")} entidades | ${meta.total_grupos.toLocaleString("pt-BR")} grupos | ${meta.total_vinculos.toLocaleString("pt-BR")} vínculos`
    : "Carregando estatísticas...";

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-950">
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">Rede econômica para pessoas e empresas</h1>
              <p className="text-sm text-zinc-600">Pesquise por uma pessoa/empresa e navegue por relacionamentos de forma simples.</p>
            </div>
            <div className="text-xs text-zinc-500">{topStats}</div>
          </div>
          <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-2">
            <label className="mb-2 block text-sm font-medium text-zinc-700">
              Buscar por nome ou CPF/CNPJ
              <input
                className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ex.: Carlos, 123.456.789-00, 12345678000190"
              />
            </label>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              {searchBusy ? (
                <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-900">Buscando...</span>
              ) : null}
              {searchResult.slice(0, 8).map((item) => {
                const label = `${item.nome} (${item.tipo_entidade})`;
                return (
                  <button
                    key={item.entidade_id}
                    data-no-drag
                    type="button"
                    className="rounded-md border border-emerald-200 bg-white px-2.5 py-1.5 text-sm text-zinc-700 shadow-sm"
                    onClick={() => void handleSelectEntity(item.entidade_id)}
                    title="Abrir no mapa"
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
              <label className="text-xs text-zinc-600">Nível de profundidade</label>
              <input
                type="range"
                min={1}
                max={6}
                value={maxDepth}
                onChange={(event) => setMaxDepth(Number(event.target.value))}
              />
              <div className="text-xs text-zinc-700">{maxDepth}</div>
            </div>
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
              <label className="text-xs text-zinc-600">Máximo de conexões por nó</label>
              <input
                type="range"
                min={5}
                max={20}
                value={maxPerNode}
                onChange={(event) => setMaxPerNode(Number(event.target.value))}
              />
              <div className="text-xs text-zinc-700">{maxPerNode}</div>
            </div>
            <label className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={includeIndirect}
                onChange={(event) => setIncludeIndirect(event.target.checked)}
              />
              Mostrar sinais fracos
            </label>
            <button
              type="button"
              className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm"
              onClick={() => void loadTree(selectedEntityId, false)}
            >
              <MagnifyingGlass size={16} />
              Atualizar árvore
            </button>
          </div>
        </header>

        {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="relative overflow-hidden rounded-xl border border-zinc-200 bg-white p-2">
            <div className="mb-2 flex items-center justify-between rounded-md bg-zinc-50 p-2 text-xs text-zinc-700">
              <strong className="inline-flex items-center gap-2">
                <Network size={16} />
                Árvore de vínculos de {root ? root.nome : "..."}
              </strong>
              <div className="inline-flex gap-2">
                <button
                  type="button"
                  data-no-drag
                  onClick={() =>
                    setViewport((current) => ({
                      ...current,
                      scale: Math.min(2, current.scale + 0.1),
                    }))
                  }
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1"
                  title="Aumentar"
                >
                  <ArrowsOut size={14} />
                  <span className="sr-only">Aumentar</span>
                </button>
                <button
                  type="button"
                  data-no-drag
                  onClick={() =>
                    setViewport((current) => ({
                      ...current,
                      scale: Math.max(0.35, current.scale - 0.1),
                    }))
                  }
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1"
                  title="Diminuir"
                >
                  <ArrowsIn size={14} />
                  <span className="sr-only">Diminuir</span>
                </button>
                <button
                  type="button"
                  data-no-drag
                  onClick={() => setViewport({ x: 20, y: 20, scale: 1 })}
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1"
                  title="Centralizar"
                >
                  <House size={14} />
                  <span className="sr-only">Centralizar</span>
                </button>
              </div>
            </div>

            <p className="mb-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
              Arraste com o mouse para movimentar. Clique no botão de uma pessoa para abrir a perna de relação desse nó.
            </p>

            <div
              ref={canvasRef}
              className="relative h-[62vh] overflow-hidden rounded-md border border-zinc-200 bg-white"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onWheel={onWheel}
            >
              <div
                className="absolute inset-0 origin-top-left"
                style={{
                  transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})`,
                  transformOrigin: "0 0",
                  width: layout.width,
                  height: layout.height,
                }}
              >
                {loadingTree ? <p className="p-2 text-sm text-zinc-600">Carregando vínculos...</p> : null}

                <svg
                  className="absolute inset-0"
                  width={layout.width}
                  height={layout.height}
                  style={{ overflow: "visible", pointerEvents: "none" }}
                >
                  {visibleRelations.map((item) => {
                    const midX = (item.from.x + item.to.x) / 2;
                    const midY = (item.from.y + item.to.y) / 2;
                    return (
                      <g key={`${item.relation.id}-${item.from.id}-${item.to.id}`}>
                        <line
                          x1={item.from.x}
                          y1={item.from.y}
                          x2={item.to.x}
                          y2={item.to.y}
                          stroke="#94a3b8"
                          strokeWidth={1.2}
                        />
                        <text
                          x={midX}
                          y={midY - 8}
                          fill="#475569"
                          fontSize={11}
                          textAnchor="middle"
                        >
                          {relationLabel(item.relation.tipo_vinculo)}
                        </text>
                      </g>
                    );
                  })}
                </svg>

                {layout.nodes.map((node) => (
                  <article
                    key={node.id}
                    style={{ left: node.x, top: node.y, position: "absolute" }}
                    className={`max-w-[220px] cursor-pointer rounded-lg border border-zinc-200 p-2 ring-2 ring-offset-1 ${
                      statusToTone(node.status_entidade)
                    } ${node.id === selectedEntityId ? "ring-emerald-500" : "ring-transparent"}`}
                    onClick={() => {
                      setSelectedEntityId(node.id);
                      void loadNodeDetail(node.id);
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <h2 className="text-sm font-semibold">{node.nome}</h2>
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-600">
                        {normalizeLabel(normalizeRelationDirection(node))}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-zinc-700">{entityTypeLabel(node.tipo_entidade)}</p>
                    <p className="text-xs text-zinc-500">{getStatusLabel(node.status_entidade)} · documento: {node.documento_valido}</p>
                    <p className="text-xs text-zinc-500">{node.cpf_cnpj}</p>
                    <p className="text-xs text-zinc-500">Conexões: {node.total_vizinhos} {node.hidden_vizinhos > 0 ? `(${node.hidden_vizinhos} ocultas)` : ""}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        data-no-drag
                        type="button"
                        className="inline-flex items-center gap-2 rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs"
                        onClick={(event) => {
                          event.stopPropagation();
                          void openBranch(node.id);
                        }}
                      >
                        <Eye size={12} />
                        Abrir ligações
                      </button>
                      {node.id === selectedEntityId ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2 py-1 text-[11px] text-emerald-700">
                          <Eye size={12} /> foco
                        </span>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </section>

          <aside className="rounded-xl border border-zinc-200 bg-white p-3">
            <h2 className="text-base font-semibold">Detalhes da entidade selecionada</h2>

            {!selectedDetail ? (
              <p className="mt-2 text-sm text-zinc-500">Escolha uma pessoa/empresa na busca ou no mapa.</p>
            ) : (
              <div className="mt-3 space-y-3 text-sm">
                <p><strong>Nome:</strong> {selectedDetail.nome_canonico}</p>
                <p><strong>Documento:</strong> {selectedDetail.cpf_cnpj}</p>
                <p><strong>Tipo:</strong> {entityTypeLabel(selectedDetail.tipo_entidade)}</p>
                <p><strong>Status:</strong> {getStatusLabel(selectedDetail.status_entidade)}</p>
                <p><strong>Documento válido:</strong> {selectedDetail.documento_valido === "true" ? "sim" : "não"}</p>
                <p><strong>Nascimento/obito:</strong> {selectedDetail.data_nascimento || "-"} / {selectedDetail.data_obito || "-"}</p>
                <p><strong>Alertas:</strong> {selectedDetail.alertas || "sem alertas"}</p>
                <p><strong>Última atualização:</strong> {selectedDetail.data_atualizacao}</p>
                <p><strong>Grupos:</strong> {selectedDetail.total_grupos} · vínculos: {selectedDetail.total_vinculos}</p>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                  <p className="mb-1 font-medium">Principais tipos de vínculo</p>
                  <ul className="list-disc space-y-1 pl-4">
                    {Object.entries(selectedDetail.conexoes_por_tipo)
                      .slice(0, 10)
                      .map(([tipo, quantidade]) => (
                        <li key={tipo}>
                          {relationLabel(tipo)}: {quantidade}
                        </li>
                      ))}
                    {Object.keys(selectedDetail.conexoes_por_tipo).length === 0 ? <li>Nenhum vínculo.</li> : null}
                  </ul>
                </div>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                  <p className="mb-1 font-medium">Grupos em que participa</p>
                  <ul className="list-disc space-y-1 pl-4">
                    {selectedDetail.grupos.slice(0, 8).map((group) => (
                      <li key={group.grupo_id}>
                        {group.nome_grupo}
                        <div className="text-xs text-zinc-500">
                          Tipo: {group.tipo_grupo} · {group.status_grupo} · Regulatório: {group.grupo_regulatorio}
                        </div>
                      </li>
                    ))}
                    {selectedDetail.grupos.length === 0 ? <li>Nenhum grupo gerado.</li> : null}
                  </ul>
                </div>

                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                  onClick={() => {
                    if (!selectedDetail) return;
                    const nextDepth = maxDepth + 1;
                    setMaxDepth(Math.min(6, nextDepth));
                    void handleSelectEntity(selectedDetail.entidade_id);
                  }}
                >
                  Aumentar nível da rede
                </button>
              </div>
            )}
          </aside>
        </div>
      </div>
    </main>
  );
}
