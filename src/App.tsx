import {
  ArrowDown,
  ArrowUp,
  ArrowsClockwise,
  ArrowsIn,
  ArrowsOut,
  MagnifyingGlass,
  House,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { EntityDetailResponse, EntityNode, RelationItem, SearchItem, TreeResponse } from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchSearch,
  fetchTree,
  fetchTreeBranch,
  fetchFamilyTree,
  fetchMetadata,
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

type TreeMode = "family" | "full";

type TreeState = {
  rootId: string;
  nodes: Map<string, EntityNode>;
  relations: Map<string, RelationItem>;
};

const ENTITY_LABEL: Record<string, string> = {
  PF: "Pessoa física",
  PJ: "Empresa",
  PF_EXTERNA: "Pessoa sem cadastro completo",
  PJ_EXTERNA: "Empresa sem cadastro completo",
  ESPOLIO: "Espólio",
};

const ROLE_TEXT: Record<string, string> = {
  "pai/mãe": "é pai/mãe de",
  "filho(a)": "é filho(a) de",
  "irmão(a)": "é irmão(a) de",
  cônjuge: "é cônjuge de",
  sócio: "é sócio(a) de",
  controlador: "é controlador(a) de",
  filiação: "tem vínculo familiar com",
  "evidência compartilhada": "tem evidência em comum com",
  "vínculo de emprego": "tem vínculo de emprego com",
  vínculo: "possui vínculo com",
  selecionado: "selecionado",
};

function toEntityLabel(tipo: string): string {
  return ENTITY_LABEL[tipo] || tipo || "Pessoa";
}

function depthLabel(depth: number): string {
  if (depth < 0) {
    return "Parentes acima";
  }
  if (depth === 0) {
    return "Pessoa selecionada";
  }
  return "Descendentes";
}

function relationSummary(nodeId: string, tree: TreeState): string {
  const rel = Array.from(tree.relations.values())
    .filter((item) => item.source === nodeId || item.target === nodeId)
    .map((item) => {
      const isSource = item.source === nodeId;
      const role = isSource ? item.role_from_source : item.role_from_target;
      const otherId = isSource ? item.target : item.source;
      const other = tree.nodes.get(otherId);
      const textRole = ROLE_TEXT[role] || role;
      return other ? `${textRole} ${other.nome}` : textRole;
    })[0];

  return rel || "vínculo disponível";
}

function useDebounced<T>(value: T, delay = 260): T {
  const [out, setOut] = useState(value);

  useEffect(() => {
    const t = setTimeout(() => setOut(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);

  return out;
}

function App() {
  const [searchTerm, setSearchTerm] = useState("");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchRows, setSearchRows] = useState<SearchItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchOffset, setSearchOffset] = useState(0);

  const [tree, setTree] = useState<TreeState>({
    rootId: "",
    nodes: new Map(),
    relations: new Map(),
  });
  const [focusId, setFocusId] = useState("");
  const [detail, setDetail] = useState<EntityDetailResponse | null>(null);

  const [metadata, setMetadata] = useState<ApiMeta | null>(null);
  const [apiError, setApiError] = useState("");
  const [treeMode, setTreeMode] = useState<TreeMode>("family");
  const [includeWeak, setIncludeWeak] = useState(false);
  const [depthUp, setDepthUp] = useState(1);
  const [depthDown, setDepthDown] = useState(1);
  const [maxPerNode, setMaxPerNode] = useState(12);
  const [loadingTree, setLoadingTree] = useState(false);

  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const debouncedSearch = useDebounced(searchTerm);

  const loadMetadata = useCallback(async () => {
    try {
      const data = await fetchMetadata();
      setMetadata(data);
    } catch {
      setMetadata(null);
    }
  }, []);

  const loadEntityDetail = useCallback(async (entityId: string) => {
    try {
      const payload = await fetchEntityDetail(entityId);
      setDetail(payload);
    } catch {
      setDetail(null);
    }
  }, []);

  const runSearch = useCallback(
    async (query: string, offset = 0) => {
      if (!query.trim() || query.trim().length < 2) {
        if (offset === 0) {
          setSearchRows([]);
          setSearchTotal(0);
          setSearchOffset(0);
        }
        return;
      }

      setSearchBusy(true);
      try {
        const result = await fetchSearch({
          q: query,
          limit: 12,
          offset,
          include_external: true,
          only_active: false,
        });

        if (offset === 0) {
          setSearchRows(result.items);
        } else {
          const merged = new Map(searchRows.map((item) => [item.entidade_id, item]));
          for (const item of result.items) {
            merged.set(item.entidade_id, item);
          }
          setSearchRows(Array.from(merged.values()));
        }
        setSearchTotal(result.total);
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

  const replaceTree = useCallback((response: TreeResponse) => {
    setTree({
      rootId: response.root_id,
      nodes: new Map(response.nodes.map((node) => [node.id, node])),
      relations: new Map(response.relations.map((rel) => [`${rel.id}:${rel.source}:${rel.target}`, rel])),
    });
    setFocusId(response.root_id);
    setPanOffset({ x: 0, y: 0 });
  }, []);

  const mergeTreeFromNode = useCallback((anchorId: string, response: TreeResponse) => {
    setTree((prev) => {
      const anchorDepth = prev.nodes.get(anchorId)?.depth ?? 0;
      const nodes = new Map(prev.nodes);
      const rels = new Map(prev.relations);

      for (const node of response.nodes) {
        const normalizedDepth = node.id === anchorId ? anchorDepth : anchorDepth + node.depth;
        const existing = nodes.get(node.id);
        if (!existing || Math.abs(normalizedDepth) < Math.abs(existing.depth)) {
          nodes.set(node.id, { ...node, depth: normalizedDepth });
        }
      }

      for (const rel of response.relations) {
        rels.set(`${rel.id}:${rel.source}:${rel.target}`, rel);
      }

      return { ...prev, nodes, relations: rels };
    });
  }, []);

  const loadTree = useCallback(
    async (
      entityId: string,
      options: { mode: "replace" | "merge"; direction?: "all" | "up" | "down" },
    ) => {
      if (!entityId) {
        return;
      }

      setApiError("");
      setLoadingTree(true);
      try {
        if (options.mode === "replace") {
          const response =
            treeMode === "family"
              ? await fetchFamilyTree({
                  entidade_id: entityId,
                  max_depth_up: depthUp,
                  max_depth_down: depthDown,
                  max_per_node: maxPerNode,
                  include_weak: includeWeak,
                })
              : await fetchTree({
                  entidade_id: entityId,
                  max_depth_up: depthUp,
                  max_depth_down: depthDown,
                  max_per_node: maxPerNode,
                  include_weak: includeWeak,
                  relation_scope: "family,business",
                });

          replaceTree(response);
          await loadEntityDetail(entityId);
          return;
        }

        const response = await fetchTreeBranch({
          entidade_id: entityId,
          max_depth: 1,
          max_per_node: maxPerNode,
          include_weak: includeWeak,
          direction: options.direction ?? "all",
          relation_scope: treeMode === "family" ? "family" : "family,business",
        });
        mergeTreeFromNode(entityId, response);
      } catch {
        setApiError("Não foi possível carregar a árvore agora. Abra o backend com `npm run backend`.");
      } finally {
        setLoadingTree(false);
      }
    },
    [depthDown, depthUp, includeWeak, loadEntityDetail, mergeTreeFromNode, maxPerNode, replaceTree, treeMode],
  );

  const chooseRoot = useCallback(
    async (entityId: string) => {
      setFocusId(entityId);
      await loadTree(entityId, { mode: "replace" });
    },
    [loadTree],
  );

  const expandFromNode = useCallback(
    async (entityId: string, direction: "up" | "down") => {
      await loadTree(entityId, { mode: "merge", direction });
    },
    [loadTree],
  );

  const reloadTree = useCallback(() => {
    if (!focusId) {
      return;
    }
    void loadTree(focusId, { mode: "replace" });
  }, [focusId, loadTree]);

  const groupedByDepth = useMemo(() => {
    const grouped = new Map<number, EntityNode[]>();
    for (const node of tree.nodes.values()) {
      const list = grouped.get(node.depth) ?? [];
      list.push(node);
      list.sort((a, b) => a.nome.localeCompare(b.nome));
      grouped.set(node.depth, list);
    }

    const ordered = new Map<number, EntityNode[]>();
    for (const [depth, list] of Array.from(grouped.entries()).sort(([a], [b]) => a - b)) {
      ordered.set(depth, list);
    }
    return ordered;
  }, [tree.nodes]);

  const canLoadMoreSearch = searchRows.length < searchTotal;

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
      containerRef.current?.setPointerCapture(event.pointerId);
    },
    [panOffset.x, panOffset.y, tree.nodes.size],
  );

  const onPanMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!isPanning) return;
      const deltaX = event.clientX - panStart.current.x;
      const deltaY = event.clientY - panStart.current.y;
      setPanOffset({
        x: panStart.current.baseX + deltaX,
        y: panStart.current.baseY + deltaY,
      });
    },
    [isPanning],
  );

  const onPanStop = useCallback((event: PointerEvent<HTMLDivElement>) => {
    setIsPanning(false);
    containerRef.current?.releasePointerCapture(event.pointerId);
  }, []);

  useEffect(() => {
    void loadMetadata();
    void fetchHealth().catch(() => {
      setApiError("API indisponível no momento. Abra o backend com `npm run backend`.");
    });
  }, [loadMetadata]);

  useEffect(() => {
    void runSearch(debouncedSearch, 0);
  }, [debouncedSearch, runSearch]);

  useEffect(() => {
    if (focusId) {
      void loadEntityDetail(focusId);
    }
  }, [focusId, loadEntityDetail]);

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-2xl font-semibold">Árvore familiar e societária</h1>
              <p className="text-sm text-zinc-600">Escolha uma pessoa/empresa e navegue por pais abaixo e filhos acima sem ruído técnico.</p>
            </div>
            {metadata ? (
              <div className="text-xs text-zinc-500">
                {metadata.total_entidades.toLocaleString("pt-BR")} entidades · {metadata.total_vinculos.toLocaleString("pt-BR")} vínculos
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
            <label className="text-sm text-zinc-700">
              <span className="mb-1 inline-flex items-center gap-1"><MagnifyingGlass size={14} /> Buscar por nome, CPF ou CNPJ</span>
              <input
                className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Digite ao menos 2 caracteres"
              />
            </label>

            <div className="mt-3 flex flex-wrap gap-2">
              {searchBusy ? <span className="text-xs text-amber-700">Buscando…</span> : null}
              {searchRows.map((item) => (
                <button
                  type="button"
                  key={item.entidade_id}
                  className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-left text-xs"
                  onClick={() => {
                    void chooseRoot(item.entidade_id);
                    void loadEntityDetail(item.entidade_id);
                  }}
                >
                  {item.nome} · {toEntityLabel(item.tipo_entidade)}
                </button>
              ))}

              {!searchBusy && searchRows.length > 0 ? (
                <span className="text-xs text-zinc-500">
                  {searchRows.length} / {searchTotal}
                </span>
              ) : null}
            </div>

            {canLoadMoreSearch ? (
              <button
                type="button"
                className="mt-2 rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => void runSearch(debouncedSearch, searchOffset + 12)}
              >
                Ver mais resultados
              </button>
            ) : null}
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-6">
            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Níveis acima (pais)
              <input
                type="range"
                min={0}
                max={6}
                value={depthUp}
                onChange={(event) => setDepthUp(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="text-xs text-zinc-600">{depthUp}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Níveis abaixo (filhos)
              <input
                type="range"
                min={0}
                max={6}
                value={depthDown}
                onChange={(event) => setDepthDown(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="text-xs text-zinc-600">{depthDown}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Ligações por pessoa
              <input
                type="range"
                min={5}
                max={25}
                value={maxPerNode}
                onChange={(event) => setMaxPerNode(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="text-xs text-zinc-600">{maxPerNode}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Tipo de vínculo
              <select
                value={treeMode}
                onChange={(event) => setTreeMode(event.target.value as TreeMode)}
                className="mt-2 block w-full rounded-md border border-zinc-300 bg-white px-2 py-1"
              >
                <option value="family">Somente familiares</option>
                <option value="full">Familiares + societário</option>
              </select>
            </label>

            <label className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={includeWeak}
                onChange={(event) => setIncludeWeak(event.target.checked)}
              />
              Incluir indicações com menor confiança
            </label>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={reloadTree}
            >
              <ArrowsClockwise size={14} />
              Recarregar
            </button>
          </div>
        </header>

        {apiError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{apiError}</div> : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
          <article className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm text-zinc-700">Árvore de vínculos (começa com pai e filho no centro)</h2>
              <div className="text-xs text-zinc-500">{loadingTree ? "Carregando…" : "Clique em um nó para abrir a perna"}</div>
            </div>

            {tree.nodes.size === 0 ? (
              <p className="text-sm text-zinc-500">Selecione uma entidade para iniciar a análise.</p>
            ) : null}

            <div
              ref={containerRef}
              className={`min-h-[58vh] rounded-md border border-zinc-100 p-2 ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
              style={{ touchAction: "none" }}
              onPointerDown={onPanStart}
              onPointerMove={onPanMove}
              onPointerUp={onPanStop}
              onPointerCancel={onPanStop}
              onPointerLeave={onPanStop}
            >
              <div style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }} className="space-y-4">
                {Array.from(groupedByDepth.entries()).map(([depth, nodes]) => (
                  <div key={depth}>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                      {depthLabel(depth)} (nível {depth})
                    </div>

                    <div className="flex flex-wrap gap-3">
                      {nodes.map((node) => {
                        const isRoot = node.id === tree.rootId;
                        const isSelected = node.id === focusId;
                        return (
                          <div
                            key={node.id}
                            className={`w-full max-w-[360px] rounded-lg border border-zinc-200 p-3 ${
                              isSelected ? "bg-emerald-50 ring-2 ring-emerald-300" : "bg-white"
                            }`}
                          >
                            <button
                              type="button"
                              className="mb-2 w-full rounded-md border border-zinc-100 bg-zinc-50 px-2 py-1 text-left"
                              onClick={() => {
                                setFocusId(node.id);
                                void loadEntityDetail(node.id);
                              }}
                            >
                              <p className="text-sm font-semibold">{node.nome}</p>
                              <p className="text-xs text-zinc-600">{toEntityLabel(node.tipo_entidade)}</p>
                              <p className="text-[11px] text-zinc-500">{node.cpf_cnpj || "sem documento"}</p>
                            </button>

                            <p className="text-xs text-zinc-600">{relationSummary(node.id, tree)}</p>
                            <p className="mt-1 text-[11px] text-zinc-500">{node.status_entidade || "sem status"}</p>

                            <div className="mt-2 flex flex-wrap gap-1">
                              {node.roles
                                .filter((role) => role !== "selecionado")
                                .slice(0, 3)
                                .map((role) => (
                                  <span
                                    key={`${node.id}-${role}`}
                                    className="rounded-full border border-zinc-200 bg-zinc-100 px-2 py-1 text-[11px] text-zinc-700"
                                  >
                                    {role}
                                  </span>
                                ))}
                              {isRoot ? <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">Raiz</span> : null}
                            </div>

                            <div className="mt-2 flex flex-wrap gap-2 text-xs">
                              {node.hidden_vizinhos > 0 ? (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-amber-700">
                                  +{node.hidden_vizinhos} vínculos não exibidos
                                </span>
                              ) : null}
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                                onClick={() => void expandFromNode(node.id, "up")}
                              >
                                <ArrowUp size={14} />
                                Ver pais
                              </button>
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                                onClick={() => void expandFromNode(node.id, "down")}
                              >
                                <ArrowDown size={14} />
                                Ver filhos
                              </button>
                            </div>

                            <div className="mt-2 flex gap-2 text-xs">
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                                onClick={() => chooseRoot(node.id)}
                              >
                                Abrir por esta pessoa
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </article>

          <aside className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-base font-semibold">Detalhes</h2>
              <div className="flex gap-1">
                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                  onClick={() => {
                    setDepthUp(Math.max(0, depthUp - 1));
                  }}
                >
                  <ArrowsIn size={14} />
                  Menos nível
                </button>
                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                  onClick={() => {
                    setDepthDown(Math.max(depthDown, 0));
                    if (focusId) {
                      void loadTree(focusId, { mode: "replace" });
                    }
                  }}
                >
                  <ArrowsOut size={14} />
                  Recarregar com nível atual
                </button>
                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                  onClick={() => {
                    setTree({ rootId: "", nodes: new Map(), relations: new Map() });
                    setFocusId("");
                    setDetail(null);
                  }}
                >
                  <House size={14} />
                  Limpar
                </button>
              </div>
            </div>

            {!detail ? (
              <p className="text-sm text-zinc-500">Selecione um nó para ver os detalhes.</p>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="font-semibold">{detail.nome_canonico || detail.nome_original}</p>
                <p>
                  <strong>Documento:</strong> {detail.cpf_cnpj || "-"}
                </p>
                <p>
                  <strong>Tipo:</strong> {toEntityLabel(detail.tipo_entidade)}
                </p>
                <p>
                  <strong>Status:</strong> {detail.status_entidade || "-"}
                </p>
                <p>
                  <strong>Atualizado em:</strong> {detail.data_atualizacao || "-"}
                </p>
                <p>
                  <strong>Conexões:</strong> {detail.total_vinculos} · Grupos: {detail.total_grupos}
                </p>

                {detail.alertas ? (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                    <p className="mb-1 font-medium">Observações</p>
                    <p>{detail.alertas}</p>
                  </div>
                ) : null}

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                  <p className="mb-1 text-xs font-medium">Conexões resumidas</p>
                  <ul className="space-y-1 text-[11px] text-zinc-700">
                    {Object.entries(detail.conexoes_por_tipo)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([tipo, total]) => (
                        <li key={tipo} className="flex items-center justify-between gap-2">
                          <span>{ROLE_TEXT[tipo] || tipo}</span>
                          <span className="font-semibold">{total}</span>
                        </li>
                      ))}
                  </ul>
                </div>
              </div>
            )}
          </aside>
        </section>
      </div>
    </main>
  );
}

export default App;
