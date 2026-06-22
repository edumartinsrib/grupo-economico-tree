import {
  ArrowsClockwise,
  ArrowsIn,
  ArrowsOut,
  House,
  MagnifyingGlass,
  TreeStructure,
  ArrowDown,
  ArrowUp,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { EntityDetailResponse, EntityNode, RelationItem, SearchItem, TreeResponse } from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchMetadata,
  fetchSearch,
  fetchTreeBranch,
  fetchFamilyTree,
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

const RELATION_TEXT: Record<string, string> = {
  "pai/mãe": "é pai/mãe de",
  "filho(a)": "é filho(a) de",
  "irmão(a)": "é irmão(a) de",
  cônjuge: "é cônjuge de",
  sócio: "é sócio(a) de",
  controlador: "é controlador(a) de",
  sociedade: "possui relação societária com",
  "filiação": "tem vínculo familiar com",
  "evidência compartilhada": "tem evidência em comum com",
  "vínculo de emprego": "tem vínculo de emprego com",
  vínculo: "está ligado a",
  selecionado: "selecionado",
};

function toEntityLabel(tipo: string): string {
  return ENTITY_LABEL[tipo] || tipo || "Pessoa";
}

function depthLabel(depth: number): string {
  if (depth < 0) {
    return "Acima (pais, cônjuges, parentes)";
  }
  if (depth === 0) {
    return "Selecionado(a)";
  }
  return "Abaixo (filhos, controladas)";
}

function nodeMainRelation(nodeId: string, tree: TreeState): string {
  const current = tree.nodes.get(nodeId);
  if (!current) {
    return "Vínculo encontrado";
  }

  const best = Array.from(tree.relations.values())
    .filter((item) => item.source === nodeId || item.target === nodeId)
    .map((item) => {
      const isSource = item.source === nodeId;
      const role = isSource ? item.role_from_source : item.role_from_target;
      const otherId = isSource ? item.target : item.source;
      const other = tree.nodes.get(otherId);
      return {
        rel: RELATION_TEXT[role] || role,
        name: other?.nome || "registro relacionado",
        relDepth: Math.abs(item.relation_depth_delta),
      };
    })
    .sort((a, b) => {
      const primary = a.relDepth - b.relDepth;
      if (primary !== 0) return primary;
      return a.name.localeCompare(b.name);
    })[0];

  if (!best) {
    return "Sem vínculos visíveis";
  }

  return `${best.rel} ${best.name}`;
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

function useWindowTreeNodes(nodes: Map<string, EntityNode>) {
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

  const [treeMode, setTreeMode] = useState<TreeMode>("family");
  const [includeWeak, setIncludeWeak] = useState(false);
  const [depthUp, setDepthUp] = useState(1);
  const [depthDown, setDepthDown] = useState(1);
  const [maxPerNode, setMaxPerNode] = useState(8);

  const [focusedId, setFocusedId] = useState("");
  const [detail, setDetail] = useState<EntityDetailResponse | null>(null);
  const [tree, setTree] = useState<TreeState>({ rootId: "", nodes: new Map(), relations: new Map() });
  const [loadingTree, setLoadingTree] = useState(false);
  const [apiError, setApiError] = useState("");

  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const debouncedQuery = useDebounced(query);

  const canLoadMoreSearch = searchRows.length < searchTotal && searchRows.length > 0;

  const groupsByDepth = useWindowTreeNodes(tree.nodes);

  const loadMetadata = useCallback(async () => {
    try {
      const payload = await fetchMetadata();
      setMetadata(payload);
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
    async (nextQuery: string, offset = 0) => {
      if (!nextQuery.trim() || nextQuery.trim().length < 2) {
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
          q: nextQuery,
          offset,
          limit: 12,
          include_external: true,
          only_active: false,
        });

        if (offset === 0) {
          setSearchRows(result.items);
        } else {
          const unique = new Map(searchRows.map((row) => [row.entidade_id, row]));
          for (const row of result.items) {
            unique.set(row.entidade_id, row);
          }
          setSearchRows(Array.from(unique.values()));
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
      relations: new Map(response.relations.map((relation) => [`${relation.id}:${relation.source}:${relation.target}`, relation])),
    });
    setFocusedId(response.root_id);
    setPanOffset({ x: 0, y: 0 });
  }, []);

  const mergeTreeFromNode = useCallback((anchorId: string, response: TreeResponse) => {
    setTree((current) => {
      const currentDepth = current.nodes.get(anchorId)?.depth ?? 0;
      const nodes = new Map(current.nodes);
      const relations = new Map(current.relations);

      for (const item of response.nodes) {
        const depth = item.id === anchorId ? currentDepth : currentDepth + item.depth;
        const existing = nodes.get(item.id);
        if (!existing || Math.abs(depth) < Math.abs(existing.depth)) {
          nodes.set(item.id, { ...item, depth });
        }
      }

      for (const item of response.relations) {
        relations.set(`${item.id}:${item.source}:${item.target}`, item);
      }

      return { ...current, nodes, relations };
    });
  }, []);

  const loadFamilyTree = useCallback(
    async (
      entityId: string,
      options: { mode: "replace" | "merge"; direction?: "all" | "up" | "down" },
    ) => {
      if (!entityId) {
        return;
      }

      setLoadingTree(true);
      setApiError("");
      try {
        if (options.mode === "replace") {
          const payload = await fetchFamilyTree({
            entidade_id: entityId,
            max_depth_up: depthUp,
            max_depth_down: depthDown,
            max_per_node: maxPerNode,
            include_weak: includeWeak,
          });
          replaceTree(payload);
        } else {
          const payload = await fetchTreeBranch({
            entidade_id: entityId,
            max_depth: 1,
            max_per_node: maxPerNode,
            include_weak: includeWeak,
            direction: options.direction ?? "all",
            relation_scope: treeMode === "family" ? "family" : "family,business",
          });
          mergeTreeFromNode(entityId, payload);
        }
        await loadEntityDetail(entityId);
      } catch {
        setApiError("Não foi possível carregar o grafo. Inicie o backend com `npm run backend`.");
      } finally {
        setLoadingTree(false);
      }
    },
    [depthDown, depthUp, includeWeak, loadEntityDetail, maxPerNode, mergeTreeFromNode, replaceTree, treeMode],
  );

  const chooseRoot = useCallback(
    (entityId: string) => {
      void loadFamilyTree(entityId, { mode: "replace" });
    },
    [loadFamilyTree],
  );

  const expandNode = useCallback(
    (entityId: string, direction: "up" | "down") => {
      void loadFamilyTree(entityId, { mode: "merge", direction });
    },
    [loadFamilyTree],
  );

  const resetTree = useCallback(() => {
    setTree({ rootId: "", nodes: new Map(), relations: new Map() });
    setFocusedId("");
    setDetail(null);
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
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">Árvore de vínculos familiares e empresariais</h1>
              <p className="text-sm text-zinc-600">
                Selecione uma pessoa/empresa. O sistema traz os pais acima e filhos abaixo, e você pode abrir novas pernas.
              </p>
            </div>
            {metadata ? (
              <div className="text-xs text-zinc-500">
                {formatCounter(metadata.total_entidades)} pessoas/empresas · {formatCounter(metadata.total_vinculos)} vínculos
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
            <label className="text-sm text-zinc-700">
              <span className="mb-1 inline-flex items-center gap-1">
                <MagnifyingGlass size={14} />
                Buscar nome, CPF/CNPJ
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
                  type="button"
                  key={row.entidade_id}
                  className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-left text-xs"
                  onClick={() => {
                    chooseRoot(row.entidade_id);
                  }}
                >
                  {row.nome} · {toEntityLabel(row.tipo_entidade)}
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
              Quantidade por pessoa
              <input
                type="range"
                min={4}
                max={20}
                value={maxPerNode}
                onChange={(event) => setMaxPerNode(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="mt-1 text-xs text-zinc-600">Máximo exibido: {maxPerNode}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Tipo de vínculo
              <select
                value={treeMode}
                onChange={(event) => setTreeMode(event.target.value as TreeMode)}
                className="mt-2 block w-full rounded-md border border-zinc-300 bg-white px-2 py-1"
              >
                <option value="family">Somente familiar</option>
                <option value="full">Familiar + societário</option>
              </select>
            </label>

            <label className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={includeWeak}
                onChange={(event) => setIncludeWeak(event.target.checked)}
              />
              Incluir vínculos de menor confiança
            </label>

            <div className="flex items-center justify-between gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2">
              <button
                type="button"
                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => setDepthUp((value) => Math.max(1, value - 1))}
              >
                <ArrowsIn size={14} /> Acima
              </button>
              <div className="text-sm">
                Profundidade: {depthUp}↑ / {depthDown}↓
              </div>
              <button
                type="button"
                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => setDepthDown((value) => Math.max(1, value + 1))}
              >
                <ArrowsOut size={14} /> Abaixo
              </button>
            </div>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={() => {
                if (!focusedId) {
                  return;
                }
                void loadFamilyTree(focusedId, { mode: "replace" });
              }}
            >
              <ArrowsClockwise size={14} />
              Recarregar visual
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
              <h2 className="text-sm text-zinc-700">Mapa: pais acima, filhos abaixo</h2>
              <span className="text-xs text-zinc-500">
                {loadingTree ? "Carregando..." : tree.nodes.size ? "Clique em um nó para abrir os detalhes" : "Escolha alguém para iniciar"}
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
              {tree.nodes.size === 0 ? (
                <p className="text-sm text-zinc-500">Selecione uma entidade para iniciar.</p>
              ) : null}

              <div className="space-y-4" style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }}>
                {Array.from(groupsByDepth.entries()).map(([depth, nodes]) => (
                  <section key={depth}>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                      {depthLabel(depth)}
                    </p>

                    <div className="flex flex-wrap gap-2">
                      {nodes.map((node) => {
                        const isRoot = node.id === tree.rootId;
                        const isSelected = node.id === focusedId;
                        const visible = node.id === tree.rootId || node.hidden_vizinhos < node.total_vizinhos;
                        return (
                          <article
                            key={node.id}
                            className={`w-full max-w-[360px] rounded-lg border p-3 ${
                              isSelected ? "bg-emerald-50 ring-2 ring-emerald-300" : "bg-white"
                            } ${isRoot ? "border-emerald-300" : "border-zinc-200"}`}
                          >
                            <button
                              type="button"
                              className="mb-2 w-full rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-left"
                              onClick={() => {
                                setFocusedId(node.id);
                                void loadEntityDetail(node.id);
                              }}
                            >
                              <div className="text-sm font-semibold">{node.nome}</div>
                              <div className="text-xs text-zinc-600">{toEntityLabel(node.tipo_entidade)}</div>
                              <div className="text-[11px] text-zinc-500">{node.cpf_cnpj || "sem documento"}</div>
                            </button>

                            <p className="text-xs text-zinc-700">{nodeMainRelation(node.id, tree)}</p>
                            <p className="mt-1 text-[11px] text-zinc-500">{node.status_entidade || "Sem status cadastral"}</p>

                            <div className="mt-2 flex flex-wrap gap-1">
                              {node.roles.slice(0, 3).map((role) => (
                                <span
                                  key={`${node.id}-${role}`}
                                  className="rounded-full border border-zinc-200 bg-zinc-100 px-2 py-1 text-[11px] text-zinc-700"
                                >
                                  {role}
                                </span>
                              ))}
                              {!visible ? <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">+{node.hidden_vizinhos} ocultos</span> : null}
                              {isRoot ? <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">Nó central</span> : null}
                            </div>

                            <div className="mt-2 flex flex-wrap gap-2">
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => expandNode(node.id, "up")}
                                title="Abrir também os pais e parentes acima"
                              >
                                <ArrowUp size={13} />
                                Ver acima
                              </button>
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => expandNode(node.id, "down")}
                                title="Abrir também os filhos e abaixo"
                              >
                                <ArrowDown size={13} />
                                Ver abaixo
                              </button>
                              {node.id === tree.rootId ? null : (
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => chooseRoot(node.id)}
                                >
                                  <TreeStructure size={13} />
                                  Definir este como centro
                                </button>
                              )}
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
              <p className="text-sm text-zinc-500">Selecione um nó para ver dados completos.</p>
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
                  <strong>Última atualização:</strong> {detail.data_atualizacao || "-"}
                </p>
                <p>
                  <strong>Conexões:</strong> {detail.total_vinculos} · Participa em {detail.total_grupos} grupos
                </p>
                <p className="text-xs text-zinc-500">Nível de confiança do documento: {detail.documento_valido}</p>

                {detail.alertas ? (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                    <p className="mb-1 font-medium">Alerta de revisão</p>
                    <p>{detail.alertas}</p>
                  </div>
                ) : null}

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                  <p className="mb-1 text-xs font-medium">Vínculos resumidos</p>
                  <ul className="space-y-1 text-[11px] text-zinc-700">
                    {Object.entries(detail.conexoes_por_tipo).map(([tipo, total]) => (
                      <li key={tipo} className="flex items-center justify-between gap-2">
                        <span>{toEntityLabel(tipo)}</span>
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
