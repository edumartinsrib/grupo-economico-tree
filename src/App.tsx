import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { ArrowDown, ArrowUp, ArrowsClockwise, House, MagnifyingGlass, TreeStructure } from "@phosphor-icons/react";
import type { EntityDetailResponse, EntityNode, RelationItem, SearchItem, TreeResponse } from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchMetadata,
  fetchSearch,
  fetchTreeContext,
  fetchTreeExpand,
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
  nodes: Map<string, EntityNode>;
  relations: Map<string, RelationItem>;
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

const ENTITY_TYPE_LABEL: Record<string, string> = {
  PF: "Pessoa física",
  PJ: "Empresa",
  PF_EXTERNA: "Pessoa sem cadastro completo",
  PJ_EXTERNA: "Empresa sem cadastro completo",
  ESPOLIO: "Espólio",
};

const ROLE_TEXT: Record<string, string> = {
  "pai/mãe": "Pai / Mãe",
  "filho(a)": "Filho(a)",
  "irmão(a)": "Irmão(a)",
  "cônjuge": "Cônjuge",
  "cônjuge (candidato)": "Cônjuge (candidato)",
  "sócio(a)": "Sócio(a)",
  "sócio(a) com participação relevante": "Sócio(a) relevante",
  "sócio(a) minoritário(a)": "Sócio(a) minoritário(a)",
  "sócio(a) indireto(a)": "Sócio(a) indireto(a)",
  "controlador(a)": "Controlador(a)",
  "controle conjunto": "Controle conjunto",
  "controle indireto": "Relação societária indireta",
  "fluxo financeiro": "Fluxo financeiro",
  "evidência compartilhada": "Contato ou endereço em comum",
  "tio(a)": "Tio(a)",
  "parente (possível)": "Parente (possível)",
  "possível mesmo genitor": "Possível mesmo genitor",
  "dependência financeira": "Dependência econômica",
  "parente": "Parente",
  "vínculo": "Vínculo",
  "selecionado": "Selecionado",
};

function roleLabel(role: string): string {
  return ROLE_TEXT[role] || role;
}

function formatCount(value: number): string {
  return value.toLocaleString("pt-BR");
}

function depthLabel(depth: number): string {
  if (depth < 0) {
    return "Pais e gerações acima";
  }
  if (depth > 0) {
    return "Filhos e ligações abaixo";
  }
  return "Pessoa/empresa selecionada";
}

function normalizeRelationText(nodeId: string, relation: RelationItem, nodeMap: Map<string, EntityNode>): string {
  if (relation.source === nodeId) {
    const targetName = nodeMap.get(relation.target)?.nome || "registro";
    const role = relation.role_from_source || "vínculo";
    return `${roleLabel(role)} de ${targetName}`;
  }

  const sourceName = nodeMap.get(relation.source)?.nome || "registro";
  const role = relation.role_from_target || "vínculo";
  return `${roleLabel(role)} de ${sourceName}`;
}

function nearestDirectRelationToRoot(nodeId: string, rootId: string, relations: Map<string, RelationItem>) {
  for (const rel of relations.values()) {
    if (rel.source === nodeId && rel.target === rootId) return rel;
    if (rel.source === rootId && rel.target === nodeId) return rel;
  }
  return null;
}

function buildDepthMap(nodes: Map<string, EntityNode>) {
  return useMemo(() => {
    const grouped = new Map<number, EntityNode[]>();
    for (const node of nodes.values()) {
      const list = grouped.get(node.depth) ?? [];
      list.push(node);
      grouped.set(node.depth, list);
    }

    const ordered = new Map<number, EntityNode[]>();
    for (const [depth, entries] of Array.from(grouped.entries()).sort(([a], [b]) => a - b)) {
      ordered.set(depth, entries.sort((a, b) => a.nome.localeCompare(b.nome)));
    }
    return ordered;
  }, [nodes]);
}

function App() {
  const [query, setQuery] = useState("");
  const [metadata, setMetadata] = useState<ApiMeta | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchRows, setSearchRows] = useState<SearchItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchOffset, setSearchOffset] = useState(0);

  const [includeBusiness, setIncludeBusiness] = useState(false);
  const [includeWeak, setIncludeWeak] = useState(false);
  const [maxPerNode, setMaxPerNode] = useState(8);

  const [tree, setTree] = useState<TreeState>({ rootId: "", nodes: new Map(), relations: new Map() });
  const [branchState, setBranchState] = useState<Map<string, BranchState>>(new Map());
  const [branchCursor, setBranchCursor] = useState<Map<string, BranchCursor>>(new Map());

  const [detail, setDetail] = useState<EntityDetailResponse | null>(null);
  const [focusedId, setFocusedId] = useState("");
  const [treeBusy, setTreeBusy] = useState(false);
  const [apiError, setApiError] = useState("");

  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const groupedNodes = buildDepthMap(tree.nodes);
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
      setFocusedId(entidadeId);
    } catch {
      setDetail(null);
    }
  }, []);

  const runSearch = useCallback(
    async (text: string, offset = 0) => {
      if (!text.trim() || text.trim().length < 2) {
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
          q: text,
          offset,
          limit: 12,
          include_external: true,
          only_active: false,
        });

        if (offset === 0) {
          setSearchRows(response.items);
        } else {
          const merged = new Map(searchRows.map((row) => [row.entidade_id, row]));
          for (const row of response.items) {
            merged.set(row.entidade_id, row);
          }
          setSearchRows(Array.from(merged.values()));
        }

        setSearchTotal(response.total);
        setSearchOffset(offset);
      } finally {
        setSearchBusy(false);
      }
    },
    [searchRows],
  );

  const normalizeTreeResponse = useCallback((response: TreeResponse) => {
    return {
      rootId: response.root_id,
      nodes: new Map(response.nodes.map((node) => [node.id, node])),
      relations: new Map(response.relations.map((item) => [`${item.id}:${item.source}:${item.target}`, item])),
    };
  }, []);

  const resetTree = useCallback(() => {
    setTree({ rootId: "", nodes: new Map(), relations: new Map() });
    setBranchState(new Map());
    setBranchCursor(new Map());
    setFocusedId("");
    setDetail(null);
    setApiError("");
    setPanOffset({ x: 0, y: 0 });
  }, []);

  const applyTreeFromRoot = useCallback(
    (response: TreeResponse) => {
      setTree(normalizeTreeResponse(response));
      setBranchState((prev) => {
        const next = new Map(prev);
        next.set(response.root_id, {
          hasMoreUp: response.has_more_up,
          hasMoreDown: response.has_more_down,
          hasMoreSame: response.has_more_same,
          nextUpOffset: response.next_up_offset,
          nextDownOffset: response.next_down_offset,
          nextSameOffset: response.next_same_offset,
        });
        return next;
      });
      setBranchCursor((prev) => {
        const next = new Map(prev);
        next.set(response.root_id, {
          up_offset: response.next_up_offset,
          down_offset: response.next_down_offset,
          same_offset: response.next_same_offset,
        });
        return next;
      });
      if (response.root_id) {
        void loadEntityDetail(response.root_id);
      }
      setTreeBusy(false);
    },
    [loadEntityDetail, normalizeTreeResponse],
  );

  const loadRootTree = useCallback(
    async (entidadeId: string) => {
      setTreeBusy(true);
      setApiError("");
      try {
        const response = await fetchTreeContext({
          entidade_id: entidadeId,
          include_up: true,
          include_down: true,
          include_same: false,
          include_weak: includeWeak,
          relation_scope: relationScope,
          max_per_node: maxPerNode,
        });
        applyTreeFromRoot(response);
      } catch {
        setApiError("Não foi possível carregar a árvore. Inicie o backend com npm run backend.");
        setTreeBusy(false);
      }
    },
    [includeBusiness, includeWeak, relationScope, maxPerNode, applyTreeFromRoot],
  );

  const mergeTree = useCallback((anchorId: string, response: TreeResponse, direction: "up" | "down") => {
    const anchor = tree.nodes.get(anchorId);
    if (!anchor) {
      applyTreeFromRoot(response);
      return;
    }

    setTree((current) => {
      const nodes = new Map(current.nodes);
      const relations = new Map(current.relations);

      for (const item of response.nodes) {
        const newDepth = anchor.depth + item.depth;
        if (item.id === anchorId) {
          continue;
        }
        const existing = nodes.get(item.id);
        if (!existing || Math.abs(newDepth) < Math.abs(existing.depth)) {
          nodes.set(item.id, { ...item, depth: newDepth });
        }
      }

      for (const item of response.relations) {
        relations.set(`${item.id}:${item.source}:${item.target}`, item);
      }

      return { ...current, nodes, relations };
    });

    setBranchState((prev) => {
      const next = new Map(prev);
      next.set(response.root_id, {
        hasMoreUp: response.has_more_up,
        hasMoreDown: response.has_more_down,
        hasMoreSame: response.has_more_same,
        nextUpOffset: response.next_up_offset,
        nextDownOffset: response.next_down_offset,
        nextSameOffset: response.next_same_offset,
      });
      return next;
    });

    setBranchCursor((prev) => {
      const cursor = prev.get(anchorId) ?? { up_offset: 0, down_offset: 0, same_offset: 0 };
      const next = new Map(prev);
      if (direction === "up") {
        next.set(anchorId, { ...cursor, up_offset: response.next_up_offset });
      } else {
        next.set(anchorId, { ...cursor, down_offset: response.next_down_offset });
      }
      return next;
    });
  }, [applyTreeFromRoot, tree.nodes]);

  const expandNode = useCallback(
    async (nodeId: string, direction: "up" | "down") => {
      const nodeState = branchState.get(nodeId) ?? {
        hasMoreUp: false,
        hasMoreDown: false,
        hasMoreSame: false,
        nextUpOffset: 0,
        nextDownOffset: 0,
        nextSameOffset: 0,
      };

      const cursor = branchCursor.get(nodeId) ?? { up_offset: 0, down_offset: 0, same_offset: 0 };
      if (direction === "up" && !nodeState.hasMoreUp) {
        return;
      }
      if (direction === "down" && !nodeState.hasMoreDown) {
        return;
      }

      setTreeBusy(true);
      setApiError("");
      try {
        const response = await fetchTreeExpand({
          entidade_id: nodeId,
          direction,
          max_per_node: maxPerNode,
          include_weak: includeWeak,
          relation_scope: relationScope,
          up_offset: cursor.up_offset,
          down_offset: cursor.down_offset,
          same_offset: cursor.same_offset,
        });
        mergeTree(nodeId, response, direction);
        await loadEntityDetail(nodeId);
      } catch {
        setApiError("Não foi possível expandir a perna selecionada.");
      } finally {
        setTreeBusy(false);
      }
    },
    [branchCursor, branchState, includeWeak, loadEntityDetail, maxPerNode, mergeTree, relationScope],
  );

  const openAndExpand = useCallback(
    async (nodeId: string) => {
      await loadEntityDetail(nodeId);
      const state = branchState.get(nodeId);
      if (!state || (!state.hasMoreUp && !state.hasMoreDown)) {
        return;
      }
      if (state.hasMoreUp) {
        await expandNode(nodeId, "up");
      }
      if (state.hasMoreDown) {
        await expandNode(nodeId, "down");
      }
    },
    [branchState, expandNode, loadEntityDetail],
  );

  const relationForNode = useCallback(
    (nodeId: string) => {
      const rel = nearestDirectRelationToRoot(nodeId, tree.rootId, tree.relations);
      if (!rel) {
        return null;
      }
      return normalizeRelationText(nodeId, rel, tree.nodes);
    },
    [tree.nodes, tree.relations, tree.rootId],
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
      const dx = event.clientX - panStart.current.x;
      const dy = event.clientY - panStart.current.y;
      setPanOffset({ x: panStart.current.baseX + dx, y: panStart.current.baseY + dy });
    },
    [isPanning],
  );

  const onPanStop = useCallback((event: PointerEvent<HTMLDivElement>) => {
    setIsPanning(false);
    canvasRef.current?.releasePointerCapture(event.pointerId);
  }, []);

  const canSearchMore = searchRows.length < searchTotal && searchRows.length > 0;

  useEffect(() => {
    void loadMetadata();
    void fetchHealth().catch(() => {
      setApiError("API indisponível no momento. Abra o backend com npm run backend.");
    });
  }, [loadMetadata]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void runSearch(query, 0);
    }, 220);
    return () => clearTimeout(timer);
  }, [query, runSearch]);

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-2xl font-semibold">Mapa de vínculos familiares e empresariais</h1>
              <p className="text-sm text-zinc-600">
                Selecione uma pessoa/empresa e acompanhe a árvore de relações por geração (acima e abaixo).
              </p>
            </div>
            {metadata ? <span className="text-xs text-zinc-500">{formatCount(metadata.total_entidades)} cadastros · {formatCount(metadata.total_vinculos)} vínculos</span> : null}
          </div>

          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
            <label className="text-sm text-zinc-700">
              <span className="mb-1 inline-flex items-center gap-1">
                <MagnifyingGlass size={14} />
                Buscar por nome, CPF ou CNPJ
              </span>
              <input
                className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Digite pelo menos 2 caracteres"
              />
            </label>

            <div className="mt-2 flex flex-wrap gap-2">
              {searchBusy ? <span className="text-xs text-amber-700">Buscando…</span> : null}
              {searchRows.map((row) => (
                <button
                  key={row.entidade_id}
                  type="button"
                  className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-left text-xs"
                  onClick={() => void loadRootTree(row.entidade_id)}
                >
                  <div className="font-semibold">{row.nome}</div>
                  <div className="text-zinc-500">{ENTITY_TYPE_LABEL[row.tipo_entidade] || row.tipo_entidade} · {row.cpf_cnpj || "sem documento"}</div>
                </button>
              ))}
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-zinc-600">
              <span>
                {searchRows.length} de {searchTotal}
              </span>
              {canSearchMore ? (
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
              Vínculos por passo
              <input
                type="range"
                min={4}
                max={20}
                value={maxPerNode}
                onChange={(event) => setMaxPerNode(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="mt-1 text-xs text-zinc-600">{maxPerNode}</div>
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
              <ArrowsClockwise size={14} /> Recarregar árvore
            </button>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={resetTree}
            >
              <House size={14} /> Limpar
            </button>
          </div>
        </header>

        {apiError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{apiError}</div> : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
          <article className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm text-zinc-700">Árvore de vínculos (exibição de cima para baixo)</h2>
              <span className="text-xs text-zinc-500">
                {treeBusy ? "Carregando..." : tree.nodes.size ? `Nó central: ${tree.nodes.get(tree.rootId)?.nome || "carregando..."}` : "Escolha uma pessoa para iniciar"}
              </span>
            </div>

            <p className="mb-2 text-xs text-zinc-500">Arraste a área para ver toda a árvore. Clique no cartão de uma pessoa para abrir a nova perna.</p>

            <div
              ref={canvasRef}
              className={`min-h-[58vh] overflow-hidden rounded-md border border-zinc-100 bg-zinc-50 p-2 ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
              style={{ touchAction: "none" }}
              onPointerDown={onPanStart}
              onPointerMove={onPanMove}
              onPointerUp={onPanStop}
              onPointerCancel={onPanStop}
              onPointerLeave={onPanStop}
            >
              <div className="space-y-4" style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }}>
                {groupedNodes.size === 0 ? (
                  <p className="p-4 text-sm text-zinc-500">Selecione uma pessoa ou empresa para iniciar a visualização.</p>
                ) : null}

                {Array.from(groupedNodes.entries()).map(([level, items]) => (
                  <section key={level}>
                    <div className="mb-2 text-xs font-semibold tracking-[0.12em] text-zinc-500">{depthLabel(level)}</div>
                    <div className="flex flex-wrap gap-2">
                      {items.map((node) => {
                        const state = branchState.get(node.id);
                        const canExpandUp = state?.hasMoreUp ?? false;
                        const canExpandDown = state?.hasMoreDown ?? false;
                        const isRoot = node.id === tree.rootId;
                        const relationHint = relationForNode(node.id) || "Nó de origem";

                        return (
                          <article
                            key={node.id}
                            className={`w-full max-w-[380px] rounded-lg border p-3 ${isRoot ? "border-emerald-300 bg-emerald-50" : "border-zinc-200 bg-white"}`}
                          >
                            <button
                              type="button"
                              className="mb-2 w-full rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-left"
                              onClick={() => void openAndExpand(node.id)}
                            >
                              <div className="text-sm font-semibold">{node.nome}</div>
                              <div className="text-xs text-zinc-600">{ENTITY_TYPE_LABEL[node.tipo_entidade] || node.tipo_entidade} · {node.cpf_cnpj || "sem documento"}</div>
                            </button>

                            <p className="text-xs text-zinc-700">{relationHint}</p>
                            <p className="text-xs text-zinc-500">
                              {node.status_entidade || "Sem status"}
                              {node.total_vizinhos > 0 ? ` · ${formatCount(node.total_vizinhos)} vínculos totais` : ""}
                            </p>
                            <p className="mt-1 text-[11px] text-zinc-500">
                              {node.hidden_vizinhos > 0 ? `${node.hidden_vizinhos} vínculos ocultos na fonte` : "Todos os vínculos visíveis nesta seleção"}
                            </p>

                            <div className="mt-2 flex flex-wrap gap-2">
                              {node.roles.slice(0, 3).map((role) => (
                                <span key={`${node.id}-${role}`} className="rounded-full border border-zinc-200 bg-zinc-100 px-2 py-1 text-[11px] text-zinc-700">
                                  {roleLabel(role)}
                                </span>
                              ))}
                              {isRoot ? <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">Nó central</span> : null}
                            </div>

                            <div className="mt-2 flex flex-wrap gap-2">
                              {canExpandUp ? (
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => void expandNode(node.id, "up")}
                                >
                                  <ArrowUp size={13} />
                                  Ver mais acima
                                </button>
                              ) : null}

                              {canExpandDown ? (
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => void expandNode(node.id, "down")}
                                >
                                  <ArrowDown size={13} />
                                  Ver mais abaixo
                                </button>
                              ) : null}

                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => void loadEntityDetail(node.id)}
                              >
                                <TreeStructure size={13} />
                                Ver detalhe
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
            </div>
          </article>

          <aside className="rounded-xl border border-zinc-200 bg-white p-3">
            <h2 className="mb-2 text-base font-semibold">Detalhes da seleção</h2>
            {!detail ? (
              <p className="text-sm text-zinc-500">Selecione um nó para mostrar os detalhes.</p>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="font-semibold">{detail.nome_canonico || detail.nome_original || "Sem nome"}</p>
                <p><strong>Documento:</strong> {detail.cpf_cnpj || "-"}</p>
                <p><strong>Tipo:</strong> {ENTITY_TYPE_LABEL[detail.tipo_entidade] || detail.tipo_entidade}</p>
                <p><strong>Status:</strong> {detail.status_entidade || "-"}</p>
                <p><strong>Conexões:</strong> {formatCount(detail.total_vinculos)}</p>
                <p><strong>Grupos:</strong> {formatCount(detail.total_grupos)}</p>
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
