import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowsClockwise,
  House,
  TreeStructure,
} from "@phosphor-icons/react";
import type { EntityDetailResponse, TreeNode, TreeRelation, SearchItem, TreeResponse } from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchMetadata,
  fetchSearch,
  fetchTreeSeed,
  fetchTreeNeighbors,
} from "./lib/api";
import "./styles.css";

type ApiMeta = {
  total_entidades: number;
  total_vinculos: number;
  total_grupos: number;
  total_revisao: number;
  total_pessoas: number;
  total_empresas: number;
  tipo_entidade: Record<string, number>;
};

type TreeState = {
  rootId: string;
  nodes: Map<string, TreeNode>;
  relations: Map<string, TreeRelation>;
};

type BranchCursor = {
  up_offset: number;
  down_offset: number;
  same_offset: number;
};

type BranchState = {
  hasMoreUp: boolean;
  hasMoreDown: boolean;
  hasMoreSame: boolean;
  nextUpOffset: number;
  nextDownOffset: number;
  nextSameOffset: number;
};

type EntityType = Record<string, string>;

const ENTITY_TYPE_LABEL: EntityType = {
  PF: "Pessoa física",
  PJ: "Empresa",
  PF_EXTERNA: "Pessoa sem cadastro completo",
  PJ_EXTERNA: "Empresa sem cadastro completo",
  ESPOLIO: "Espólio",
};

const RELATION_LABEL: EntityType = {
  "pai/mãe": "É Pai/Mãe",
  "filho(a)": "É Filho(a)",
  irmão: "Irmão(a)",
  "irmão(a)": "Irmão(a)",
  "cônjuge": "É Cônjuge",
  "cônjuge (candidato)": "Possível Cônjuge",
  "sócio(a)": "É Sócio(a)",
  "sócio(a) relevante": "É Sócio(a) relevante",
  "sócio(a) minoritário(a)": "É Sócio(a) minoritário(a)",
  "sócio(a) indireto(a)": "É Sócio(a) indireto(a)",
  "controlador(a)": "Controlador(a)",
  "controle conjunto": "Controle conjunto",
  "controle indireto": "Controle indireto",
  "fluxo financeiro": "Fluxo financeiro",
  "dependência financeira": "Dependência financeira",
  "tio(a)": "Tio(a)",
  "possível mesmo genitor": "Possível mesmo genitor",
  selecionado: "Nó selecionado",
  "pai / mãe": "É Pai/Mãe",
};

const HIDE_ON_DRAG_STYLE = "touch-action-none";

function clampLabel(value: string): string {
  return RELATION_LABEL[value?.trim().toLowerCase()] || value || "Relação";
}

function formatCount(value: number): string {
  return value.toLocaleString("pt-BR");
}

function depthLabel(level: number): string {
  if (level < 0) {
    return "Geração acima (ascendente)";
  }
  if (level > 0) {
    return "Geração abaixo (descendente)";
  }
  return "Nó central";
}

function toCpfReadable(value: string): string {
  if (!value) {
    return "-";
  }
  return value;
}

function normalizeTreeDepths(anchorDepth: number, nodes: TreeNode[]): TreeNode[] {
  return nodes.map((node) => ({
    ...node,
    nivel: anchorDepth + node.nivel,
  }));
}

function groupByLevel(nodes: Iterable<TreeNode>) {
  const grouped = new Map<number, TreeNode[]>();
  for (const node of nodes) {
    const current = grouped.get(node.nivel) ?? [];
    current.push(node);
    grouped.set(node.nivel, current);
  }

  return new Map(
    Array.from(grouped.entries())
      .sort(([a], [b]) => a - b)
      .map(([level, items]) => [level, [...items].sort((left, right) => left.nome.localeCompare(right.nome))] as const),
  );
}

function relationBadgeForNode(node: TreeNode, anchorId: string): string {
  if (node.id === anchorId) {
    return "Nó central";
  }
  return clampLabel(node.relacao_com_ancora);
}

function isExpansionNeeded(nodeId: string, branchState: Map<string, BranchState>): boolean {
  const state = branchState.get(nodeId);
  return !!state?.hasMoreUp || !!state?.hasMoreDown;
}

function canExpandDirection(
  nodeId: string,
  direction: "up" | "down",
  branchState: Map<string, BranchState>,
): boolean {
  const state = branchState.get(nodeId);
  if (!state) {
    return true;
  }
  return direction === "up" ? state.hasMoreUp : state.hasMoreDown;
}

function App() {
  const [query, setQuery] = useState("");
  const [metadata, setMetadata] = useState<ApiMeta | null>(null);
  const [searchRows, setSearchRows] = useState<SearchItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchOffset, setSearchOffset] = useState(0);
  const [searchBusy, setSearchBusy] = useState(false);

  const [includeBusiness, setIncludeBusiness] = useState(false);
  const [includeWeak, setIncludeWeak] = useState(false);
  const [maxPerNode, setMaxPerNode] = useState(8);

  const [tree, setTree] = useState<TreeState>({ rootId: "", nodes: new Map(), relations: new Map() });
  const [branchState, setBranchState] = useState<Map<string, BranchState>>(new Map());
  const [branchCursor, setBranchCursor] = useState<Map<string, BranchCursor>>(new Map());
  const [detail, setDetail] = useState<EntityDetailResponse | null>(null);
  const [treeBusy, setTreeBusy] = useState(false);
  const [apiError, setApiError] = useState("");

  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const groupedNodes = useMemo(() => groupByLevel(tree.nodes.values()), [tree.nodes]);
  const relationScope = includeBusiness ? "family,business" : "family";

  const loadMetadata = useCallback(async () => {
    try {
      const payload = await fetchMetadata();
      setMetadata(payload);
    } catch {
      setMetadata(null);
    }
  }, []);

  const loadEntityDetail = useCallback(async (entidadeId: string) => {
    try {
      const payload = await fetchEntityDetail(entidadeId);
      setDetail(payload);
    } catch {
      setDetail(null);
    }
  }, []);

  const runSearch = useCallback(
    async (text: string, offset = 0) => {
      const cleanQuery = text.trim();
      if (!cleanQuery || cleanQuery.length < 2) {
        if (offset === 0) {
          setSearchRows([]);
          setSearchTotal(0);
          setSearchOffset(0);
        }
        return;
      }

      setSearchBusy(true);
      try {
        const response = await fetchSearch({
          q: cleanQuery,
          offset,
          limit: 12,
          include_external: true,
          only_active: false,
        });
        setSearchRows((current) => (offset === 0 ? response.items : [...current, ...response.items]));
        setSearchTotal(response.total);
        setSearchOffset(offset);
      } finally {
        setSearchBusy(false);
      }
    },
    [],
  );

  const resetTree = useCallback(() => {
    setTree({ rootId: "", nodes: new Map(), relations: new Map() });
    setBranchState(new Map());
    setBranchCursor(new Map());
    setApiError("");
    setPanOffset({ x: 0, y: 0 });
  }, []);

  const applyTree = useCallback((response: TreeResponse, mergeFrom?: string, forceReplace = false) => {
    const referenceDepth = mergeFrom ? tree.nodes.get(mergeFrom)?.nivel ?? 0 : 0;
    setTree((current) => {
      const nextNodes = forceReplace ? new Map<string, TreeNode>() : new Map(current.nodes);
      const nextRelations = forceReplace ? new Map<string, TreeRelation>() : new Map(current.relations);

      const nodesToInsert = forceReplace ? response.nodes : normalizeTreeDepths(referenceDepth, response.nodes);
      for (const node of nodesToInsert) {
        const exists = nextNodes.get(node.id);
        if (!exists || Math.abs(node.nivel) < Math.abs(exists.nivel)) {
          nextNodes.set(node.id, { ...node });
        }
      }

      for (const item of response.relations) {
        nextRelations.set(`${item.id}:${item.source}:${item.target}`, item);
      }

      return {
        ...current,
        rootId: forceReplace ? response.anchor_id : current.rootId || response.anchor_id,
        nodes: nextNodes,
        relations: nextRelations,
      };
    });

    setBranchState((current) => {
      const next = new Map(current);
      next.set(response.anchor_id, {
        hasMoreUp: response.has_more_up,
        hasMoreDown: response.has_more_down,
        hasMoreSame: response.has_more_same,
        nextUpOffset: response.next_up_offset,
        nextDownOffset: response.next_down_offset,
        nextSameOffset: response.next_same_offset,
      });
      return next;
    });

    setBranchCursor((current) => {
      const next = new Map(current);
      next.set(response.anchor_id, {
        up_offset: response.next_up_offset,
        down_offset: response.next_down_offset,
        same_offset: response.next_same_offset,
      });
      return next;
    });
  }, [tree.nodes]);

  const loadRootTree = useCallback(
    async (entidadeId: string) => {
      setTreeBusy(true);
      setApiError("");
      setTree({ rootId: "", nodes: new Map(), relations: new Map() });
      try {
        const response = await fetchTreeSeed({
          entidade_id: entidadeId,
          include_business: includeBusiness,
          include_weak: includeWeak,
          relation_scope: relationScope,
          max_up_per_node: Math.min(2, maxPerNode),
          max_down_per_node: Math.max(1, Math.min(12, maxPerNode)),
        });
        applyTree(response, undefined, true);
        await loadEntityDetail(entidadeId);
      } catch {
        setApiError("Não foi possível carregar a árvore. Inicie o backend com `npm run backend`.");
      } finally {
        setTreeBusy(false);
      }
    },
    [applyTree, includeBusiness, includeWeak, relationScope, maxPerNode, loadEntityDetail],
  );

  const loadNeighbors = useCallback(
    async (entidadeId: string, direction: "up" | "down" | "same") => {
      const cursor = branchCursor.get(entidadeId) ?? { up_offset: 0, down_offset: 0, same_offset: 0 };
      if (direction === "up" && cursor.up_offset === 0 && isExpansionNeeded(entidadeId, branchState) && !branchState.get(entidadeId)?.hasMoreUp) {
        return;
      }

      if (direction === "down" && cursor.down_offset === 0 && isExpansionNeeded(entidadeId, branchState) && !branchState.get(entidadeId)?.hasMoreDown) {
        return;
      }

      if (direction === "up" && !canExpandDirection(entidadeId, "up", branchState)) {
        return;
      }

      if (direction === "down" && !canExpandDirection(entidadeId, "down", branchState)) {
        return;
      }

      setTreeBusy(true);
      setApiError("");
      try {
        const response = await fetchTreeNeighbors({
          entidade_id: entidadeId,
          direction,
          include_business: includeBusiness,
          include_weak: includeWeak,
          relation_scope: relationScope,
          max_por_lote: maxPerNode,
          up_offset: cursor.up_offset,
          down_offset: cursor.down_offset,
          same_offset: cursor.same_offset,
        });

        applyTree(response, entidadeId, false);
        setBranchCursor((prev) => {
          const next = new Map(prev);
          const previous = next.get(entidadeId) ?? { up_offset: 0, down_offset: 0, same_offset: 0 };
          const newCursor = { ...previous };
          if (direction === "up") {
            newCursor.up_offset = response.next_up_offset;
          } else if (direction === "down") {
            newCursor.down_offset = response.next_down_offset;
          } else {
            newCursor.same_offset = response.next_same_offset;
          }
          next.set(entidadeId, newCursor);
          return next;
        });

        setBranchState((prev) => {
          const next = new Map(prev);
          const previous = next.get(response.anchor_id) ?? {
            hasMoreUp: false,
            hasMoreDown: false,
            hasMoreSame: false,
            nextUpOffset: 0,
            nextDownOffset: 0,
            nextSameOffset: 0,
          };
          next.set(response.anchor_id, {
            ...previous,
            hasMoreUp: response.has_more_up,
            hasMoreDown: response.has_more_down,
            hasMoreSame: response.has_more_same,
            nextUpOffset: response.next_up_offset,
            nextDownOffset: response.next_down_offset,
            nextSameOffset: response.next_same_offset,
          });
          return next;
        });
      } catch {
        setApiError("Não foi possível abrir a perna da árvore.");
      } finally {
        setTreeBusy(false);
      }
    },
    [applyTree, branchCursor, branchState, includeBusiness, includeWeak, maxPerNode, relationScope],
  );

  const openNode = useCallback(
    async (nodeId: string) => {
      await loadEntityDetail(nodeId);
      const level = tree.nodes.get(nodeId)?.nivel ?? 0;
      if (level < 0) {
        if (canExpandDirection(nodeId, "up", branchState)) {
          await loadNeighbors(nodeId, "up");
          return;
        }
        if (canExpandDirection(nodeId, "down", branchState)) {
          await loadNeighbors(nodeId, "down");
        }
        return;
      }
      if (level > 0) {
        if (canExpandDirection(nodeId, "down", branchState)) {
          await loadNeighbors(nodeId, "down");
          return;
        }
        if (canExpandDirection(nodeId, "up", branchState)) {
          await loadNeighbors(nodeId, "up");
        }
        return;
      }

      if (canExpandDirection(nodeId, "down", branchState)) {
        await loadNeighbors(nodeId, "down");
      } else if (canExpandDirection(nodeId, "up", branchState)) {
        await loadNeighbors(nodeId, "up");
      }
    },
    [loadEntityDetail, tree.nodes, loadNeighbors, branchState],
  );

  const onPanStart = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (tree.nodes.size === 0 || event.button !== 0) {
        return;
      }
      setIsPanning(true);
      panStart.current = {
        x: event.clientX,
        y: event.clientY,
        baseX: panOffset.x,
        baseY: panOffset.y,
      };
      canvasRef.current?.setPointerCapture(event.pointerId);
    },
    [panOffset.x, panOffset.y, tree.nodes.size],
  );

  const onPanMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!isPanning) {
        return;
      }
      const x = panStart.current.baseX + (event.clientX - panStart.current.x);
      const y = panStart.current.baseY + (event.clientY - panStart.current.y);
      setPanOffset({ x, y });
    },
    [isPanning],
  );

  const onPanStop = useCallback((event: PointerEvent<HTMLDivElement>) => {
    setIsPanning(false);
    canvasRef.current?.releasePointerCapture(event.pointerId);
  }, []);

  const canLoadMore = searchRows.length > 0 && searchRows.length < searchTotal;
  const hasTree = tree.nodes.size > 0;

  useEffect(() => {
    void loadMetadata();
    void fetchHealth().catch(() => {
      setApiError("API indisponível. Rode `npm run backend` para subir a API.");
    });
  }, [loadMetadata]);

  useEffect(() => {
    const timer = setTimeout(() => void runSearch(query), 250);
    return () => clearTimeout(timer);
  }, [query, runSearch]);

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-2xl font-semibold text-zinc-900">Mapa de vínculos familiares e empresariais</h1>
              <p className="text-sm text-zinc-600">
                Busque a pessoa/empresa e expanda a árvore por perna: pai/acima e filhos/abaixo.
              </p>
            </div>
            <div className="text-xs text-zinc-500">
              {metadata ? (
                <>
                  {formatCount(metadata.total_entidades)} cadastros · {formatCount(metadata.total_vinculos)} vínculos · {formatCount(metadata.total_grupos)} grupos
                </>
              ) : (
                "Carregando metadados..."
              )}
            </div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
            <label className="text-sm font-medium text-zinc-700">
              Buscar por nome, CPF ou CNPJ
              <input
                className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Digite 2 caracteres para iniciar"
              />
            </label>

            <div className="mt-3 flex flex-wrap gap-2">
              {searchBusy ? <span className="text-xs text-amber-700">Buscando…</span> : null}
              {searchRows.map((row) => (
                <button
                  key={row.entidade_id}
                  type="button"
                  className="w-full rounded-md border border-emerald-200 bg-white px-2 py-2 text-left md:w-auto"
                  onClick={() => void loadRootTree(row.entidade_id)}
                  title="Abrir árvore para esta entidade"
                >
                  <div className="font-semibold">{row.nome}</div>
                  <div className="text-xs text-zinc-500">
                    {ENTITY_TYPE_LABEL[row.tipo_entidade] || row.tipo_entidade} · {toCpfReadable(row.cpf_cnpj)}
                  </div>
                </button>
              ))}
            </div>

            <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-600">
              <span>
                {searchRows.length} de {searchTotal}
              </span>
              {canLoadMore ? (
                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                  onClick={() => void runSearch(query, searchOffset + 12)}
                >
                  Ver mais resultados
                </button>
              ) : null}
            </div>
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-6">
            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Vínculos por expansão
              <input
                type="range"
                min={4}
                max={18}
                value={maxPerNode}
                onChange={(event) => setMaxPerNode(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="mt-1 text-xs text-zinc-500">{maxPerNode}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input type="checkbox" checked={includeWeak} onChange={(event) => setIncludeWeak(event.target.checked)} />
              <span className="ml-2">Incluir vínculos com revisão</span>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input type="checkbox" checked={includeBusiness} onChange={(event) => setIncludeBusiness(event.target.checked)} />
              <span className="ml-2">Incluir vínculos societários</span>
            </label>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={() => {
                if (!tree.rootId) {
                  return;
                }
                void loadRootTree(tree.rootId);
              }}
            >
              <ArrowsClockwise size={14} /> Recarregar
            </button>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={resetTree}
            >
              <House size={14} /> Nova busca
            </button>
          </div>
        </header>

        {apiError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{apiError}</div> : null}

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_360px]">
          <article className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-base font-semibold text-zinc-700">
                Árvore vertical (pais acima, descendentes abaixo)
              </h2>
              <span className="text-xs text-zinc-500">
                {treeBusy ? "Carregando..." : hasTree ? `Nó central: ${tree.nodes.get(tree.rootId)?.nome || "-"}` : "Escolha um registro para iniciar"}
              </span>
            </div>

            <p className="mb-2 text-xs text-zinc-500">
              A árvore cresce de cima para baixo. Use os botões dos nós para abrir a perna acima/abaixo gradualmente.
              Arraste o painel para acompanhar componentes com muitos nós.
            </p>

            <div
              ref={canvasRef}
              className={`min-h-[58vh] overflow-hidden rounded-md border border-zinc-100 bg-zinc-50 p-2 ${isPanning ? "cursor-grabbing" : "cursor-grab"} ${HIDE_ON_DRAG_STYLE}`}
              style={{ touchAction: "none" }}
              onPointerDown={onPanStart}
              onPointerMove={onPanMove}
              onPointerUp={onPanStop}
              onPointerCancel={onPanStop}
              onPointerLeave={onPanStop}
            >
              <div style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }} className="space-y-4">
                {groupedNodes.size === 0 ? <p className="p-4 text-sm text-zinc-500">Selecione uma pessoa ou empresa para iniciar a árvore.</p> : null}

                {Array.from(groupedNodes.entries()).map(([level, nodes]) => {
                  return (
                    <section key={level}>
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                        {depthLabel(level)}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {nodes.map((node) => {
                          const isRoot = node.id === tree.rootId;

                          return (
                            <article
                              key={node.id}
                              className={`w-full max-w-[360px] rounded-lg border p-3 ${isRoot ? "border-emerald-300 bg-emerald-50" : "border-zinc-200 bg-white"}`}
                            >
                              <button
                                type="button"
                                className="mb-2 w-full rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-left"
                                onClick={() => void openNode(node.id)}
                                title="Abrir detalhe e expandir a perna principal"
                              >
                                <div className="text-sm font-semibold">{node.nome}</div>
                                <div className="text-xs text-zinc-600">
                                  {ENTITY_TYPE_LABEL[node.tipo_entidade] || node.tipo_entidade} · {toCpfReadable(node.cpf_cnpj)}
                                </div>
                              </button>

                              <p className="text-xs text-zinc-700">
                                Relação: <strong>{relationBadgeForNode(node, tree.rootId) || "—"}</strong>
                              </p>
                              <p className="text-xs text-zinc-500">
                                {node.status_entidade || "Sem status"} {node.total_vizinhos ? `· ${formatCount(node.total_vizinhos)} vínculos` : ""}
                              </p>
                              <p className="mt-1 text-[11px] text-zinc-500">
                                {node.ocultos > 0 ? `${node.ocultos} vínculo(s) ocultos nesta perna` : "Sem vínculos ocultos nesta consulta"}
                              </p>

                              <div className="mt-2 flex flex-wrap gap-2">
                                {canExpandDirection(node.id, "up", branchState) ? (
                                  <button
                                    type="button"
                                    className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                    onClick={() => void loadNeighbors(node.id, "up")}
                                  >
                                    <ArrowUp size={13} /> Ver pais
                                  </button>
                                ) : null}
                                {canExpandDirection(node.id, "down", branchState) ? (
                                  <button
                                    type="button"
                                    className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                    onClick={() => void loadNeighbors(node.id, "down")}
                                  >
                                    <ArrowDown size={13} /> Ver filhos
                                  </button>
                                ) : null}
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => void loadEntityDetail(node.id)}
                                >
                                  <TreeStructure size={13} /> Detalhe
                                </button>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  );
                })}
              </div>
            </div>
          </article>

          <aside className="rounded-xl border border-zinc-200 bg-white p-3">
            <h2 className="mb-2 text-base font-semibold text-zinc-700">Detalhe da seleção</h2>
            {!detail ? (
              <p className="text-sm text-zinc-500">Clique em um nó para abrir os detalhes.</p>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="font-semibold">{detail.nome_canonico || detail.nome_original || "Sem nome cadastrado"}</p>
                <p><strong>Documento:</strong> {toCpfReadable(detail.cpf_cnpj)}</p>
                <p><strong>Tipo:</strong> {ENTITY_TYPE_LABEL[detail.tipo_entidade] || detail.tipo_entidade}</p>
                <p><strong>Status:</strong> {detail.status_entidade || "-"}</p>
                <p><strong>Conexões conhecidas:</strong> {formatCount(detail.total_vizinhos)}</p>
                <p><strong>Grupos associados:</strong> {formatCount(detail.total_grupos)}</p>
                <p><strong>Documento válido:</strong> {detail.documento_valido}</p>

                {!!detail.alertas ? (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                    <p className="font-medium">Observação</p>
                    <p>{detail.alertas}</p>
                  </div>
                ) : null}

                {!!Object.keys(detail.conexoes_por_tipo).length ? (
                  <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                    <p className="mb-1 text-xs font-medium">Tipos de vínculo</p>
                    <ul className="space-y-1 text-[11px] text-zinc-700">
                      {Object.entries(detail.conexoes_por_tipo).map(([tipo, total]) => (
                        <li key={tipo} className="flex justify-between gap-2">
                          <span>{tipo}</span>
                          <span className="font-semibold">{total}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            )}
          </aside>
        </section>
      </div>
    </main>
  );
}

export default App;
