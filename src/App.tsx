import { ArrowDown, ArrowUp, ArrowsClockwise, ArrowsIn, ArrowsOut, House } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { EntityNode, EntityDetailResponse, RelationItem, SearchItem, TreeResponse } from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchSearch,
  fetchTree,
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

const RELATION_LABEL: Record<string, string> = {
  FILHO_DE: "pai/mãe",
  PAI_DE: "filho",
  MAE_DE: "filho",
  CONJUGE_DE: "cônjuge",
  CONJUGE_NOME_CANDIDATO: "cônjuge (em análise)",
  IRMAO_DE: "irmão(a)",
  CONTROLADOR_DIRETO: "controle societário",
  CONTROLADOR_CONJUNTO_CANDIDATO: "controle conjunto",
  INFLUENCIA_RELEVANTE: "participação relevante",
  SOCIO_DE: "sócio",
  SOCIO_MINORITARIO: "sócio",
  SOCIO_COTISTA: "sócio",
  PARTICIPACAO_INDIRETA: "participação indireta",
  ENDERECO_COMPARTILHADO: "endereço comum",
  CONTATO_COMPARTILHADO: "contato compartilhado",
  EMPREGADO_DE: "vínculo de trabalho",
  TIO_TIA_DE: "tio/tia",
  ESPOLIO_DE: "espólio",
  PARENTESCO_AMBIGUO: "parentesco ambíguo",
  POSSIVEL_MESMO_GENITOR: "parente com mesmo pai",
  TRANSFERIU_PARA: "fluxo financeiro",
  DEPENDENCIA_FINANCEIRA_CANDIDATA: "dependência sugerida",
  DEPENDENCIA_FINANCEIRA_CONFIRMADA: "dependência confirmada",
};

const ROLE_TEXT: Record<string, string> = {
  "pai/mãe": "é pai/mãe de",
  "filho(a)": "é filho(a) de",
  "irmão(a)": "é irmão(a) de",
  cônjuge: "é cônjuge de",
  "cônjuge(a)": "é cônjuge de",
  sócio: "é sócio(a) de",
  controlador: "é controlador(a) de",
  filiação: "tem vínculo familiar com",
  "fluxo financeiro": "tem fluxo financeiro com",
  "evidência compartilhada": "tem evidência compartilhada com",
  "vínculo de emprego": "tem vínculo de emprego com",
  "parente relacionado": "pode ser parente relacionado de",
  "endereço em comum": "tem endereço em comum com",
  "contato compartilhado": "tem contato compartilhado com",
  "selecionado": "selecionado",
  vínculo: "possui vínculo com",
};

function toEntityLabel(tipo: string): string {
  return ENTITY_LABEL[tipo] || tipo || "Pessoa";
}

function relationForRole(role: string): string {
  return ROLE_TEXT[role] || `é ${role} de`;
}

function depthLabel(depth: number): string {
  if (depth < 0) {
    return "Antepassados";
  }

  if (depth === 0) {
    return "Pessoa selecionada";
  }

  return "Descendentes";
}

function useDebounced<T>(value: T, delay = 300): T {
  const [output, setOutput] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setOutput(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return output;
}

function useMemoizedSortedNodes(nodes: Map<string, EntityNode>): Map<number, EntityNode[]> {
  return useMemo(() => {
    const grouped = new Map<number, EntityNode[]>();

    for (const node of nodes.values()) {
      const list = grouped.get(node.depth) ?? [];
      list.push(node);
      grouped.set(node.depth, list);
    }

    const sorted = new Map<number, EntityNode[]>();
    for (const [depthLevel, entries] of Array.from(grouped.entries()).sort(([a], [b]) => a - b)) {
      sorted.set(
        depthLevel,
        entries.sort((left, right) => (left.nome || "").localeCompare(right.nome || "")),
      );
    }

    return sorted;
  }, [nodes]);
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
  const [selectedEntityId, setSelectedEntityId] = useState("");
  const [selectedDetail, setSelectedDetail] = useState<EntityDetailResponse | null>(null);

  const [metadata, setMetadata] = useState<ApiMeta | null>(null);
  const [apiError, setApiError] = useState("");
  const [treeMode, setTreeMode] = useState<TreeMode>("family");
  const [includeWeak, setIncludeWeak] = useState(false);
  const [treeDepth, setTreeDepth] = useState(1);
  const [maxPerNode, setMaxPerNode] = useState(10);
  const [loadingTree, setLoadingTree] = useState(false);
  const [viewHint, setViewHint] = useState("Carregue uma entidade para iniciar.");

  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const treeContainerRef = useRef<HTMLDivElement | null>(null);
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const debouncedSearch = useDebounced(searchTerm, 280);

  const loadMetadata = useCallback(async () => {
    try {
      const response = await fetch("/api/metadata");
      const payload = (await response.json()) as ApiMeta;
      setMetadata(payload);
    } catch {
      setMetadata(null);
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
          const merged = new Map<string, SearchItem>(searchRows.map((item) => [item.entidade_id, item]));
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

  const loadTreePayload = useCallback(
    async (
      entidadeId: string,
      payloadDepth: number,
      opts: { mode: "replace" | "merge"; direction?: "all" | "up" | "down" },
    ) => {
      if (!entidadeId) {
        return;
      }

      const relationScope = treeMode === "full" ? "family,business" : "family";
      setApiError("");
      setLoadingTree(true);

      try {
        let response: TreeResponse;

        if (opts.mode === "replace") {
          response =
            treeMode === "family"
              ? await fetchFamilyTree({
                  entidade_id: entidadeId,
                  max_depth: payloadDepth,
                  max_per_node: maxPerNode,
                  include_weak: includeWeak,
                })
              : await fetchTree({
                  entidade_id: entidadeId,
                  max_depth: payloadDepth,
                  max_per_node: maxPerNode,
                  include_weak: includeWeak,
                  relation_scope: relationScope,
                });

          setTree({
            rootId: response.root_id,
            nodes: new Map(response.nodes.map((node) => [node.id, node])),
            relations: new Map(response.relations.map((rel) => [
              `${rel.id}:${rel.source}:${rel.target}:${rel.relation_depth_delta}`,
              rel,
            ])),
          });
          setSelectedEntityId(response.root_id);
          setPanOffset({ x: 0, y: 0 });
          setViewHint("Expandindo por demanda para manter a consulta leve em grandes volumes.");
        } else {
          response = await fetchTreeBranch({
            entidade_id: entidadeId,
            max_depth: payloadDepth,
            max_per_node: maxPerNode,
            direction: opts.direction ?? "all",
            include_weak: includeWeak,
            relation_scope: relationScope,
          });

          const anchorDepth = tree.nodes.get(entidadeId)?.depth ?? 0;
          setTree((current) => {
            const next = new Map(current.nodes);
            const rels = new Map(current.relations);

            for (const node of response.nodes) {
              const adjustedDepth = node.id === entidadeId ? anchorDepth : anchorDepth + node.depth;
              const existing = next.get(node.id);
              if (!existing || Math.abs(adjustedDepth) < Math.abs(existing.depth)) {
                next.set(node.id, { ...node, depth: adjustedDepth });
              }
            }

            for (const relation of response.relations) {
              rels.set(`${relation.id}:${relation.source}:${relation.target}:${relation.relation_depth_delta}`, relation);
            }

            return {
              rootId: current.rootId,
              nodes: next,
              relations: rels,
            };
          });
        }
      } catch (error) {
        setApiError("Não foi possível carregar a árvore agora. Confirme que a API está disponível.");
        if (error instanceof Error) {
          console.error(error);
        }
      } finally {
        setLoadingTree(false);
      }
    },
    [maxPerNode, tree.nodes, treeMode, includeWeak],
  );

  const loadEntityDetail = useCallback(async (entityId: string) => {
    try {
      const detail = await fetchEntityDetail(entityId);
      setSelectedDetail(detail);
    } catch {
      setSelectedDetail(null);
    }
  }, []);

  const selectEntity = useCallback(
    async (entityId: string) => {
      setSelectedEntityId(entityId);
      await loadTreePayload(entityId, treeDepth, { mode: "replace" });
      await loadEntityDetail(entityId);
    },
    [treeDepth, loadEntityDetail, loadTreePayload],
  );

  const expandNode = useCallback(
    async (entityId: string, direction: "up" | "down" | "all") => {
      await loadTreePayload(entityId, 1, { mode: "merge", direction });
    },
    [loadTreePayload],
  );

  const reloadWithMode = useCallback(() => {
    if (!selectedEntityId) {
      return;
    }

    void loadTreePayload(selectedEntityId, treeDepth, { mode: "replace" });
  }, [selectedEntityId, treeDepth, loadTreePayload]);

  const relationHint = useCallback(
    (node: EntityNode): string => {
      if (node.id === tree.rootId) {
        return "Selecionado para análise";
      }

      const best = Array.from(tree.relations.values())
        .filter((relation) => relation.source === node.id || relation.target === node.id)
        .map((relation) => {
          const isSource = relation.source === node.id;
          const role = isSource ? relation.role_from_source : relation.role_from_target;
          const neighborId = isSource ? relation.target : relation.source;
          const neighbor = tree.nodes.get(neighborId);
          const connector = relationForRole(role);
          return {
            text: neighbor ? `${connector} ${neighbor.nome}` : connector,
            depthWeight: Math.abs(neighborId === tree.rootId ? 0 : (tree.nodes.get(neighborId)?.depth ?? 999)),
            preferSibling: node.depth === 0 ? 0 : 1,
          };
        })
        .sort((left, right) => left.depthWeight - right.depthWeight || left.preferSibling - right.preferSibling);

      return best[0]?.text ?? "vínculo em análise";
    },
    [tree.nodes, tree.relations, tree.rootId],
  );

  const nodesByDepth = useMemoizedSortedNodes(tree.nodes);
  const hiddenCount = useMemo(() => {
    return Array.from(tree.nodes.values()).reduce((acc, node) => acc + Math.max(node.hidden_vizinhos, 0), 0);
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
      treeContainerRef.current?.setPointerCapture(event.pointerId);
    },
    [panOffset.x, panOffset.y, tree.nodes.size],
  );

  const onPanMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!isPanning) {
        return;
      }

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
    treeContainerRef.current?.releasePointerCapture(event.pointerId);
  }, []);

  useEffect(() => {
    void loadMetadata();
    void fetchHealth().catch(() => {
      setApiError("API não respondeu. Rode o backend com `npm run backend`.");
    });
  }, [loadMetadata]);

  useEffect(() => {
    void runSearch(debouncedSearch, 0);
  }, [debouncedSearch, runSearch]);

  useEffect(() => {
    if (selectedEntityId) {
      void loadEntityDetail(selectedEntityId);
    }
  }, [selectedEntityId, loadEntityDetail]);

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-2xl font-semibold">Visualização de grupos econômicos</h1>
              <p className="text-sm text-zinc-600">Selecione uma pessoa ou empresa e navegue por vínculos familiares e societários de forma progressiva.</p>
            </div>
            {metadata ? (
              <div className="text-xs text-zinc-500">
                {metadata.total_entidades.toLocaleString("pt-BR")} entidades · {metadata.total_vinculos.toLocaleString("pt-BR")} vínculos
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
            <label className="text-sm text-zinc-700">
              Buscar por nome, CPF ou CNPJ
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
                  className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-xs text-zinc-700"
                  onClick={() => {
                    void selectEntity(item.entidade_id);
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

          <div className="mt-3 grid gap-2 md:grid-cols-5">
            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Níveis iniciais da visualização
              <input
                type="range"
                min={1}
                max={6}
                value={treeDepth}
                onChange={(event) => setTreeDepth(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="text-xs text-zinc-600">{treeDepth}</div>
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
              Modo de consulta
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
              Mostrar indicações fracas
            </label>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={reloadWithMode}
            >
              <ArrowsClockwise size={14} />
              Recarregar
            </button>
          </div>
        </header>

        {apiError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{apiError}</div> : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
          <article className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm text-zinc-700">Árvore de vínculos (cresce para baixo)</h2>
              <div className="text-xs text-zinc-500">{viewHint}</div>
            </div>

            {loadingTree ? <p className="mb-2 text-sm text-zinc-600">Carregando nós e relações…</p> : null}

            {tree.nodes.size === 0 ? <p className="text-sm text-zinc-500">Escolha uma entidade na busca para iniciar.</p> : null}

            <div
              ref={treeContainerRef}
              className={`min-h-[56vh] rounded-md border border-zinc-100 p-2 ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
              style={{ touchAction: "none" }}
              onPointerDown={onPanStart}
              onPointerMove={onPanMove}
              onPointerUp={onPanStop}
              onPointerCancel={onPanStop}
              onPointerLeave={onPanStop}
            >
              <div className="relative space-y-4" style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }}>
                {Array.from(nodesByDepth.entries()).map(([layerDepth, nodes]) => (
                  <div key={layerDepth}>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                      {depthLabel(layerDepth)} (camada {layerDepth})
                    </div>

                    <div className="flex flex-wrap gap-3">
                      {nodes.map((node) => {
                        const isSelected = node.id === selectedEntityId;
                        return (
                          <div
                            key={node.id}
                            className={`w-full max-w-[320px] rounded-lg border border-zinc-200 p-3 ${
                              isSelected ? "bg-emerald-50 ring-2 ring-emerald-300" : "bg-white"
                            }`}
                          >
                            <button
                              type="button"
                              className="w-full rounded-md border border-zinc-100 bg-zinc-50 px-2 py-1 text-left"
                              onClick={() => {
                                if (node.id !== selectedEntityId) {
                                  void selectEntity(node.id);
                                }
                              }}
                            >
                              <p className="text-sm font-semibold">{node.nome}</p>
                              <p className="text-xs text-zinc-600">{toEntityLabel(node.tipo_entidade)}</p>
                              <p className="text-[11px] text-zinc-500">{node.cpf_cnpj || "sem documento"}</p>
                            </button>

                            <p className="mt-2 text-xs text-zinc-600">{relationHint(node)}</p>

                            <div className="mt-2 flex flex-wrap gap-1">
                              {node.roles.map((role) => (
                                <span
                                  key={`${node.id}-${role}`}
                                  className="rounded-full border border-zinc-200 bg-zinc-100 px-2 py-1 text-[11px] text-zinc-700"
                                >
                                  {role}
                                </span>
                              ))}
                            </div>

                            <div className="mt-2 flex flex-wrap gap-2 text-xs">
                              {node.hidden_vizinhos > 0 ? (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-amber-700">
                                  +{node.hidden_vizinhos} vínculos ocultos
                                </span>
                              ) : null}
                              <span className="rounded-full border border-zinc-200 bg-zinc-50 px-2 py-1 text-zinc-600">
                                {node.status_entidade || "sem status"}
                              </span>
                            </div>

                            <div className="mt-2 flex flex-wrap gap-2">
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => void expandNode(node.id, "up")}
                              >
                                <ArrowUp size={14} />
                                Ver acima
                              </button>
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => void expandNode(node.id, "down")}
                              >
                                <ArrowDown size={14} />
                                Ver abaixo
                              </button>
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => void expandNode(node.id, "all")}
                              >
                                <ArrowsClockwise size={14} />
                                Abrir perna
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}

                <p className="text-xs text-zinc-500">Possíveis vínculos não exibidos por limite atual: {hiddenCount}</p>
              </div>
            </div>
          </article>

          <aside className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-base font-semibold">Detalhes</h2>
              <button
                type="button"
                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => {
                  if (!selectedEntityId) {
                    return;
                  }

                  const nextDepth = Math.max(1, treeDepth - 1);
                  setTreeDepth(nextDepth);
                  void selectEntity(selectedEntityId);
                }}
              >
                <ArrowsIn size={14} />
                Menos nível
              </button>
            </div>

            {!selectedDetail ? (
              <p className="text-sm text-zinc-500">Selecione uma entidade da árvore para ver dados completos.</p>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="font-semibold">{selectedDetail.nome_canonico || selectedDetail.nome_original}</p>
                <p><strong>Documento:</strong> {selectedDetail.cpf_cnpj || "-"}</p>
                <p><strong>Tipo:</strong> {toEntityLabel(selectedDetail.tipo_entidade)}</p>
                <p><strong>Status:</strong> {selectedDetail.status_entidade || "-"}</p>
                <p><strong>Atualização:</strong> {selectedDetail.data_atualizacao || "-"}</p>
                <p><strong>Conexões:</strong> {selectedDetail.total_vinculos} · Grupos: {selectedDetail.total_grupos}</p>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                  <p className="mb-1 font-medium">Tipos de vínculo em resumo</p>
                  <ul className="list-disc space-y-1 pl-5 text-xs">
                    {Object.entries(selectedDetail.conexoes_por_tipo).map(([tipo, total]) => (
                      <li key={tipo}>
                        {RELATION_LABEL[tipo] || tipo}: {total}
                      </li>
                    ))}
                  </ul>
                </div>

                {selectedDetail.alertas ? (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-amber-900">
                    <p className="mb-1 font-medium">Observações</p>
                    <p className="text-xs">{selectedDetail.alertas}</p>
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-2 text-xs">
                  <button
                    type="button"
                    className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                    onClick={() => {
                      const next = Math.min(8, treeDepth + 1);
                      setTreeDepth(next);
                      if (selectedEntityId) {
                        void loadTreePayload(selectedEntityId, next, { mode: "replace" });
                      }
                    }}
                  >
                    <ArrowsOut size={14} />
                    Mais nível
                  </button>

                  <button
                    type="button"
                    className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                    onClick={() => {
                      setSelectedEntityId("");
                      setSelectedDetail(null);
                      setTree({ rootId: "", nodes: new Map(), relations: new Map() });
                      setPanOffset({ x: 0, y: 0 });
                      setViewHint("Selecione outra entidade para iniciar uma nova consulta.");
                    }}
                  >
                    <House size={14} />
                    Limpar
                  </button>
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
