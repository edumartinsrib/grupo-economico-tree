import {
  ArrowsClockwise,
  ArrowDown,
  ArrowUp,
  House,
  MagnifyingGlass,
  TreeStructure,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
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

type BranchState = {
  upHasMore: boolean;
  downHasMore: boolean;
  sameHasMore: boolean;
  nextUpOffset: number;
  nextDownOffset: number;
  nextSameOffset: number;
};

type BranchCursor = {
  up_offset: number;
  down_offset: number;
  same_offset: number;
};

const ENTITY_LABEL: Record<string, string> = {
  PF: "Pessoa física",
  PJ: "Empresa",
  PF_EXTERNA: "Pessoa sem cadastro completo",
  PJ_EXTERNA: "Empresa sem cadastro completo",
  ESPOLIO: "Espólio",
};

const RELATION_TEXT: Record<string, string> = {
  "pai/mãe": "pai/mãe",
  "filho(a)": "filho(a)",
  "irmão(a)": "irmão(a)",
  cônjuge: "cônjuge",
  sócio: "sócio",
  "sócio principal": "sócio principal",
  controlador: "controlador",
  sociedade: "sócio",
  "evidência compartilhada": "evidência compartilhada",
  "vínculo de emprego": "vínculo de emprego",
  selecionado: "selecionado(a)",
  "fluxo financeiro": "fluxo financeiro",
  "dependência financeira sugerida": "dependência financeira sugerida",
  "dependência financeira confirmada": "dependência financeira confirmada",
  "cônjuge (candidato)": "cônjuge candidato",
  filiação: "filiação",
  "controle conjunto": "controle conjunto",
  "vínculo": "vínculo",
};

function toEntityLabel(tipo: string): string {
  return ENTITY_LABEL[tipo] || tipo || "Pessoa";
}

function normalizeRelationLabel(value: string): string {
  return RELATION_TEXT[value] || value;
}

function formatCounter(value: number): string {
  return value.toLocaleString("pt-BR");
}

function useDebounced<T>(value: T, delay = 240): T {
  const [result, setResult] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setResult(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return result;
}

function depthLabel(depth: number): string {
  if (depth < 0) {
    return "Pais / vínculos anteriores";
  }
  if (depth === 0) {
    return "Selecionado";
  }
  return "Filhos / entidades ligadas";
}

function relationRoleForPerspective(relation: RelationItem, perspectiveNodeId: string): string {
  if (relation.source === perspectiveNodeId) {
    return relation.role_from_source;
  }

  if (relation.target === perspectiveNodeId) {
    return relation.role_from_target;
  }

  return "vínculo";
}

function groupNodesByDepth(nodes: Map<string, EntityNode>) {
  return useMemo(() => {
    const grouped = new Map<number, EntityNode[]>();
    for (const node of nodes.values()) {
      const list = grouped.get(node.depth) ?? [];
      list.push(node);
      grouped.set(node.depth, list);
    }

    const ordered = new Map<number, EntityNode[]>();
    for (const [depth, entries] of Array.from(grouped.entries()).sort(([a], [b]) => a - b)) {
      ordered.set(
        depth,
        entries.sort((a, b) => a.nome.localeCompare(b.nome)),
      );
    }

    return ordered;
  }, [nodes]);
}

function App() {
  const [query, setQuery] = useState("");
  const [metadata, setMetadata] = useState<ApiMeta | null>(null);
  const [apiError, setApiError] = useState("");

  const [searchBusy, setSearchBusy] = useState(false);
  const [searchRows, setSearchRows] = useState<SearchItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchOffset, setSearchOffset] = useState(0);

  const [includeWeak, setIncludeWeak] = useState(false);
  const [includeBusiness, setIncludeBusiness] = useState(false);
  const [maxPerNode, setMaxPerNode] = useState(8);

  const [focusedId, setFocusedId] = useState("");
  const [detail, setDetail] = useState<EntityDetailResponse | null>(null);
  const [tree, setTree] = useState<TreeState>({ rootId: "", nodes: new Map(), relations: new Map() });
  const [branchState, setBranchState] = useState<Map<string, BranchState>>(new Map());
  const [branchCursor, setBranchCursor] = useState<Map<string, BranchCursor>>(new Map());
  const [loadingTree, setLoadingTree] = useState(false);

  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const debouncedQuery = useDebounced(query);
  const groupedByDepth = groupNodesByDepth(tree.nodes);

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
    async (searchText: string, offset = 0) => {
      if (!searchText.trim() || searchText.trim().length < 2) {
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
          q: searchText,
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
      } catch {
        setSearchRows([]);
        setSearchTotal(0);
      } finally {
        setSearchBusy(false);
      }
    },
    [searchRows],
  );

  const relationText = useCallback((nodeId: string, relation: RelationItem | null) => {
    if (!relation) {
      return "Ligação disponível";
    }

    const sourceName = tree.nodes.get(relation.source)?.nome || "registro";
    const targetName = tree.nodes.get(relation.target)?.nome || "registro";
    const role = relationRoleForPerspective(relation, nodeId);
    if (relation.source === nodeId) {
      return `${normalizeRelationLabel(role)} em relação a ${targetName}`;
    }
    return `${normalizeRelationLabel(role)} em relação a ${sourceName}`;
  }, [tree.nodes]);

  const directRelationToRoot = useCallback(
    (nodeId: string) => {
      const rootId = tree.rootId;
      if (!rootId || nodeId === rootId) {
        return null;
      }

      for (const relation of tree.relations.values()) {
        if (
          (relation.source === nodeId && relation.target === rootId)
          || (relation.source === rootId && relation.target === nodeId)
        ) {
          return relation;
        }
      }

      return null;
    },
    [tree.relations, tree.rootId],
  );

  const renderRelationHint = useCallback(
    (nodeId: string) => {
      const root = tree.nodes.get(tree.rootId);
      if (!root || nodeId === tree.rootId) {
        return "Nó central da visualização";
      }

      const rootRelation = directRelationToRoot(nodeId);
      if (rootRelation) {
        const role = normalizeRelationLabel(
          relationRoleForPerspective(rootRelation, nodeId),
        );

        if (role === "vínculo") {
          return `Ligado(a) ao centro por vínculo ${rootRelation.tipo_nome}`;
        }

        return `${role} do registro central`;
      }

      return "Conexão exibida no mesmo componente";
    },
    [directRelationToRoot, tree.nodes, tree.rootId],
  );

  const pickNodeSummary = useCallback(
    (nodeId: string) => {
      const rels = Array.from(tree.relations.values()).filter(
        (item) => item.source === nodeId || item.target === nodeId,
      );

      if (!rels.length) {
        return "Sem vínculos visíveis";
      }

      if (nodeId === tree.rootId) {
        return "Registro central. Use os botões para expandir por nível.";
      }

      return relationText(nodeId, rels[0]!);
    },
    [relationText, tree.relations, tree.rootId],
  );

  const normalizeTreeResponse = useCallback((response: TreeResponse, anchorId: string): TreeState => {
    return {
      rootId: tree.rootId || response.root_id,
      nodes: new Map(response.nodes.map((node) => [node.id, node])),
      relations: new Map(response.relations.map((item) => [`${item.id}:${item.source}:${item.target}`, item])),
    };
  }, [tree.rootId]);

  const replaceTree = useCallback((response: TreeResponse) => {
    setTree(normalizeTreeResponse(response, response.root_id));
    setPanOffset({ x: 0, y: 0 });
    setBranchState((prev) => {
      const next = new Map(prev);
      next.set(response.root_id, {
        upHasMore: response.has_more_up,
        downHasMore: response.has_more_down,
        sameHasMore: response.has_more_same,
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
    setDetail(null);
    setFocusedId(response.root_id);
  }, [normalizeTreeResponse]);

  const mergeTree = useCallback((anchorId: string, response: TreeResponse, mode: "up" | "down" | "same") => {
    const anchor = tree.nodes.get(anchorId);
    if (!anchor) {
      replaceTree(response);
      return;
    }

    setTree((current) => {
      const nodes = new Map(current.nodes);
      const relations = new Map(current.relations);

      for (const item of response.nodes) {
        if (item.id === anchorId) {
          continue;
        }

        const depthShift = anchor.depth;
        const itemDepth = item.depth + depthShift;

        const existing = nodes.get(item.id);
        if (!existing) {
          nodes.set(item.id, { ...item, depth: itemDepth });
        } else if (Math.abs(itemDepth) < Math.abs(existing.depth)) {
          nodes.set(item.id, { ...existing, depth: itemDepth });
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
        upHasMore: response.has_more_up,
        downHasMore: response.has_more_down,
        sameHasMore: response.has_more_same,
        nextUpOffset: response.next_up_offset,
        nextDownOffset: response.next_down_offset,
        nextSameOffset: response.next_same_offset,
      });
      return next;
    });

    setBranchCursor((prev) => {
      const cursor = prev.get(anchorId) ?? {
        up_offset: 0,
        down_offset: 0,
        same_offset: 0,
      };

      const next = new Map(prev);
      if (mode === "up") {
        next.set(anchorId, {
          ...cursor,
          up_offset: response.next_up_offset,
        });
      }
      if (mode === "down") {
        next.set(anchorId, {
          ...cursor,
          down_offset: response.next_down_offset,
        });
      }
      if (mode === "same") {
        next.set(anchorId, {
          ...cursor,
          same_offset: response.next_same_offset,
        });
      }

      return next;
    });
  }, [replaceTree, tree.nodes]);

  const loadRootTree = useCallback(
    async (entityId: string) => {
      setLoadingTree(true);
      setApiError("");
      try {
        const response = await fetchTreeContext({
          entidade_id: entityId,
          include_up: true,
          include_down: true,
          include_same: false,
          relation_scope: relationScope,
          include_weak: includeWeak,
          max_per_node: maxPerNode,
        });

        replaceTree(response);
        setTree((current) => {
          if (!current.nodes.has(entityId)) {
            const updated = new Map(current.nodes);
            const selected = searchRows.find((row) => row.entidade_id === entityId);
            if (selected) {
              updated.set(entityId, {
                id: entityId,
                nome: selected.nome,
                cpf_cnpj: selected.cpf_cnpj,
                tipo_entidade: selected.tipo_entidade,
                status_entidade: "",
                data_nascimento: selected.data_nascimento,
                data_obito: "",
                documento_valido: selected.documento_valido,
                alerta: "",
                depth: 0,
                total_vizinhos: 0,
                hidden_vizinhos: 0,
                roles: ["selecionado"],
              });
            }
            return { ...current, nodes: updated };
          }
          return current;
        });

        void loadEntityDetail(entityId);
      } catch {
        setApiError("Não foi possível carregar a árvore. Inicie o backend com `npm run backend`.");
      } finally {
        setLoadingTree(false);
      }
    },
    [branchState, includeBusiness, includeWeak, relationScope, maxPerNode, replaceTree, loadEntityDetail, searchRows],
  );

  const expandNode = useCallback(
    async (entityId: string, direction: "up" | "down") => {
      const nodeState = branchCursor.get(entityId) ?? {
        up_offset: 0,
        down_offset: 0,
        same_offset: 0,
      };
      const cursor = {
        up_offset: nodeState.up_offset,
        down_offset: nodeState.down_offset,
        same_offset: nodeState.same_offset,
      };

      setLoadingTree(true);
      setApiError("");
      try {
        const response = await fetchTreeExpand({
          entidade_id: entityId,
          direction,
          relation_scope: relationScope,
          max_per_node: maxPerNode,
          include_weak: includeWeak,
          up_offset: cursor.up_offset,
          down_offset: cursor.down_offset,
          same_offset: cursor.same_offset,
        });

        mergeTree(entityId, response, direction);
        const target = branchState.get(entityId);
        if (!target) {
          void loadEntityDetail(entityId);
          return;
        }
        if ((direction === "up" && target.upHasMore) || (direction === "down" && target.downHasMore)) {
          await loadEntityDetail(entityId);
        }
      } catch {
        setApiError("Falha ao carregar nova perna da árvore.");
      } finally {
        setLoadingTree(false);
      }
    },
    [branchCursor, branchState, includeWeak, loadEntityDetail, maxPerNode, mergeTree, relationScope],
  );

  const resetTree = useCallback(() => {
    setTree({ rootId: "", nodes: new Map(), relations: new Map() });
    setFocusedId("");
    setDetail(null);
    setApiError("");
    setBranchState(new Map());
    setBranchCursor(new Map());
  }, []);

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

  const canLoadMoreSearch = searchRows.length < searchTotal && searchRows.length > 0;

  useEffect(() => {
    void loadMetadata();
    void fetchHealth().catch(() => {
      setApiError("API indisponível no momento. Abra o backend com `npm run backend`.");
    });
  }, [loadMetadata]);

  useEffect(() => {
    if (focusedId) {
      void loadEntityDetail(focusedId);
    }
  }, [focusedId, loadEntityDetail]);

  useEffect(() => {
    void runSearch(debouncedQuery, 0);
  }, [debouncedQuery, runSearch]);

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">Mapa de vínculos familiares e empresariais</h1>
              <p className="text-sm text-zinc-600">
                Escolha uma pessoa/empresa para abrir a árvore por cima (pais e cônjuges) e por baixo (filhos e empresas relacionadas).
              </p>
            </div>
            {metadata ? (
              <div className="text-xs text-zinc-500">
                {formatCounter(metadata.total_entidades)} cadastros · {formatCounter(metadata.total_vinculos)} vínculos
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
            <label className="text-sm text-zinc-700">
              <span className="mb-1 inline-flex items-center gap-1">
                <MagnifyingGlass size={14} />
                Buscar nome, CPF ou CNPJ
              </span>
              <input
                className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Digite ao menos 2 caracteres"
              />
            </label>

            <div className="mt-2 flex flex-wrap gap-2">
              {searchBusy ? <span className="text-xs text-amber-700">Buscando…</span> : null}
              {searchRows.map((row) => (
                <button
                  type="button"
                  key={row.entidade_id}
                  className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-left text-xs"
                  onClick={() => void loadRootTree(row.entidade_id)}
                >
                  <span className="font-medium">{row.nome}</span>
                  <span className="ml-2 text-zinc-500">{toEntityLabel(row.tipo_entidade)} · {row.cpf_cnpj || "sem documento"}</span>
                </button>
              ))}
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-zinc-600">
              <span>
                {searchRows.length} de {searchTotal}
              </span>
              {canLoadMoreSearch ? (
                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                  onClick={() => void runSearch(debouncedQuery, searchOffset + 12)}
                >
                  Ver mais resultados
                </button>
              ) : null}
            </div>
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-6">
            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Quantidade de relações por pessoa
              <input
                type="range"
                min={4}
                max={20}
                value={maxPerNode}
                onChange={(event) => setMaxPerNode(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="mt-1 text-xs text-zinc-600">Mostrando até: {maxPerNode}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={includeWeak}
                onChange={(event) => setIncludeWeak(event.target.checked)}
              />
              <span className="ml-2">Incluir vínculos de revisão</span>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={includeBusiness}
                onChange={(event) => setIncludeBusiness(event.target.checked)}
              />
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
              <ArrowsClockwise size={14} />
              Recarregar visual atual
            </button>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={resetTree}
            >
              <House size={14} />
              Limpar
            </button>
          </div>
        </header>

        {apiError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{apiError}</div> : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
          <article className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm text-zinc-700">Árvore: acima (pais/cônjuges) e abaixo (filhos/controle)</h2>
              <span className="text-xs text-zinc-500">
                {loadingTree
                  ? "Carregando..."
                  : tree.nodes.size
                    ? `Nó central: ${tree.nodes.get(tree.rootId)?.nome || "carregando..."}`
                    : "Escolha uma pessoa para iniciar"}
              </span>
            </div>

            <div
              ref={canvasRef}
              className={`min-h-[58vh] rounded-md border border-zinc-100 p-2 ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
              style={{ touchAction: "none" }}
              onPointerDown={onPanStart}
              onPointerMove={onPanMove}
              onPointerUp={onPanStop}
              onPointerCancel={onPanStop}
              onPointerLeave={onPanStop}
            >
              {tree.nodes.size === 0 ? <p className="text-sm text-zinc-500">Selecione uma pessoa/empresa para iniciar a visualização.</p> : null}

              <div className="space-y-4" style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }}>
                {Array.from(groupedByDepth.entries()).map(([depth, nodes]) => (
                  <section key={depth}>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                      {depthLabel(depth)}
                    </p>

                    <div className="flex flex-wrap gap-2">
                      {nodes.map((node) => {
                        const isRoot = node.id === tree.rootId;
                        const state = branchState.get(node.id);
                        const canExpandUp = state?.upHasMore ?? false;
                        const canExpandDown = state?.downHasMore ?? false;
                        const isFocused = node.id === focusedId;
                        const nodeRoles = node.roles.length ? node.roles : ["vínculo"];
                          const summary = pickNodeSummary(node.id);
                          const relationHint = renderRelationHint(node.id);

                          return (
                            <article
                              key={node.id}
                              className={`w-full max-w-[360px] rounded-lg border p-3 ${isFocused ? "bg-emerald-50 ring-2 ring-emerald-300" : "bg-white"} ${isRoot ? "border-emerald-300" : "border-zinc-200"}`}
                            >
                            <button
                              type="button"
                              className="mb-2 w-full rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-left"
                              onClick={() => {
                                loadEntityDetail(node.id).catch(() => {
                                  setDetail(null);
                                });
                              }}
                            >
                              <div className="text-sm font-semibold">{node.nome}</div>
                              <div className="text-xs text-zinc-600">{toEntityLabel(node.tipo_entidade)} · {node.cpf_cnpj || "sem documento"}</div>
                              </button>

                            <p className="text-xs text-zinc-700">{relationHint}</p>
                            <p className="text-xs text-zinc-500">{summary}</p>
                            <p className="mt-1 text-[11px] text-zinc-500">
                              {node.status_entidade || "Sem status cadastral"} · {node.hidden_vizinhos > 0 ? `${node.hidden_vizinhos} vínculos ocultos` : "Todos os vínculos exibidos"}
                            </p>

                            <div className="mt-2 flex flex-wrap gap-1">
                              {nodeRoles.slice(0, 3).map((role) => (
                                <span key={`${node.id}-${role}`} className="rounded-full border border-zinc-200 bg-zinc-100 px-2 py-1 text-[11px] text-zinc-700">
                                  {role}
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
                                  title="Trazer mais vínculos para cima (pai, mãe e vínculos do mesmo ramo)"
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
                                  title="Trazer mais vínculos abaixo (filhos e empresas vinculadas)"
                                >
                                  <ArrowDown size={13} />
                                  Ver mais abaixo
                                </button>
                              ) : null}

                              {!isRoot ? (
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => void loadRootTree(node.id)}
                                >
                                  <TreeStructure size={13} />
                                  Centralizar aqui
                                </button>
                              ) : null}
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
            <h2 className="mb-2 text-base font-semibold">Detalhes</h2>
            {!detail ? (
              <p className="text-sm text-zinc-500">Selecione um nó para ver as informações.</p>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="font-semibold">{detail.nome_canonico || detail.nome_original || "Sem nome"}</p>
                <p><strong>Documento:</strong> {detail.cpf_cnpj || "-"}</p>
                <p><strong>Tipo:</strong> {toEntityLabel(detail.tipo_entidade)}</p>
                <p><strong>Status:</strong> {detail.status_entidade || "-"}</p>
                <p><strong>Vínculos totais:</strong> {detail.total_vinculos}</p>
                <p><strong>Grupos relacionados:</strong> {detail.total_grupos}</p>
                <p><strong>Documento válido:</strong> {detail.documento_valido}</p>

                {!!detail.alertas ? (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                    <p className="mb-1 font-medium">Observação importante</p>
                    <p>{detail.alertas}</p>
                  </div>
                ) : null}

                {!!Object.keys(detail.conexoes_por_tipo).length ? (
                  <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                    <p className="mb-1 text-xs font-medium">Principais tipos de vínculo</p>
                    <ul className="space-y-1 text-[11px] text-zinc-700">
                      {Object.entries(detail.conexoes_por_tipo).map(([tipo, total]) => (
                        <li key={tipo} className="flex items-center justify-between gap-2">
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
