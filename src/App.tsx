import { ArrowBendUpLeft, ArrowsClockwise, ArrowDown, ArrowsIn, ArrowsOut, House } from "@phosphor-icons/react";
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
  PF_EXTERNA: "Pessoa (sem cadastro)",
  PJ_EXTERNA: "Empresa (sem cadastro)",
  ESPOLIO: "Espólio",
};

const RELATION_LABEL: Record<string, string> = {
  FILHO_DE: "pai/mãe",
  PAI_DE: "filho(a)",
  MAE_DE: "filho(a)",
  CONJUGE_DE: "cônjuge",
  CONJUGE_NOME_CANDIDATO: "cônjuge",
  IRMAO_DE: "irmão(a)",
  CONTROLADOR_DIRETO: "controlador",
  CONTROLADOR_CONJUNTO_CANDIDATO: "controle conjunto",
  INFLUENCIA_RELEVANTE: "participação relevante",
  SOCIO_DE: "sócio",
  SOCIO_MINORITARIO: "sócio",
  SOCIO_COTISTA: "sócio",
  PARTICIPACAO_INDIRETA: "participação indireta",
  ENDERECO_COMPARTILHADO: "endereço em comum",
  CONTATO_COMPARTILHADO: "contato compartilhado",
  EMPREGADO_DE: "vínculo de emprego",
  TIO_TIA_DE: "tio/tia",
  ESPOLIO_DE: "espólio",
  PARENTESCO_AMBIGUO: "parentesco ambíguo",
  POSSIVEL_MESMO_GENITOR: "parente relacionado",
  DEPENDENCIA_FINANCEIRA_CANDIDATA: "dependência sugerida",
  DEPENDENCIA_FINANCEIRA_CONFIRMADA: "dependência confirmada",
  TRANSFERIU_PARA: "fluxo de recursos",
};

const relationVerbFromPerspective = (relationType: string, sourceIsNode: boolean): string => {
  if (relationType === "FILHO_DE") {
    return sourceIsNode ? "é filho(a) de" : "é pai/mãe de";
  }

  if (relationType === "PAI_DE" || relationType === "MAE_DE") {
    return sourceIsNode ? "é pai/mãe de" : "é filho(a) de";
  }

  if (relationType === "IRMAO_DE") {
    return "é irmão(a) de";
  }

  if (relationType === "CONJUGE_DE" || relationType === "CONJUGE_NOME_CANDIDATO") {
    return "é cônjuge de";
  }

  if (relationType === "TIO_TIA_DE") {
    return "é tio/tia de";
  }

  if (relationType === "SOCIO_DE" || relationType === "SOCIO_COTISTA") {
    return "é sócio de";
  }

  if (relationType === "CONTROLADOR_DIRETO") {
    return "é controlador(a) de";
  }

  if (relationType === "PARTICIPACAO_INDIRETA") {
    return "tem participação indireta em";
  }

  if (relationType === "CONTROLADOR_CONJUNTO_CANDIDATO") {
    return "tem controle conjunto com";
  }

  if (relationType === "INFLUENCIA_RELEVANTE") {
    return "tem influência societária em";
  }

  if (relationType === "TRANSFERIU_PARA") {
    return "fez transferência para";
  }

  return `tem relação de ${RELATION_LABEL[relationType] ?? relationType.toLowerCase().replace(/_/g, " ")}`;
};

function toEntityLabel(tipo: string): string {
  return ENTITY_LABEL[tipo] || tipo || "Pessoa";
}

function depthTitle(depth: number): string {
  if (depth < 0) {
    return `Antepassados`;
  }

  if (depth > 0) {
    return `Descendentes`;
  }

  return "Pessoa selecionada";
}

function useDebounced<T>(value: T, delay = 350): T {
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

function App() {
  const [searchTerm, setSearchTerm] = useState("");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchRows, setSearchRows] = useState<SearchItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchOffset, setSearchOffset] = useState(0);

  const [metadata, setMetadata] = useState<ApiMeta | null>(null);
  const [apiError, setApiError] = useState("");

  const [treeMode, setTreeMode] = useState<TreeMode>("family");
  const [includeWeak, setIncludeWeak] = useState(false);
  const [depth, setDepth] = useState(2);
  const [maxPerNode, setMaxPerNode] = useState(10);

  const [selectedEntityId, setSelectedEntityId] = useState("");
  const [selectedDetail, setSelectedDetail] = useState<EntityDetailResponse | null>(null);

  const [tree, setTree] = useState<TreeState>({
    rootId: "",
    nodes: new Map(),
    relations: new Map(),
  });

  const [loadingTree, setLoadingTree] = useState(false);
  const treeContainerRef = useRef<HTMLDivElement | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const debouncedSearch = useDebounced(searchTerm);

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
      options: {
        mode: "replace" | "merge";
        direction?: "all" | "up" | "down";
      },
    ) => {
      if (!entidadeId) {
        return;
      }

      setApiError("");
      setLoadingTree(true);

      const isFull = treeMode === "full";
      const relationScope = isFull ? "family,business" : "family";

      try {
        let response: TreeResponse;
        if (options.mode === "replace") {
          response = isFull
            ? await fetchTree({
                entidade_id: entidadeId,
                max_depth: payloadDepth,
                max_per_node: maxPerNode,
                include_weak: includeWeak,
                relation_scope: relationScope,
              })
            : await fetchFamilyTree({
                entidade_id: entidadeId,
                max_depth: payloadDepth,
                max_per_node: maxPerNode,
                include_weak: includeWeak,
              });

          setTree({
            rootId: response.root_id,
            nodes: new Map(response.nodes.map((node) => [node.id, node])),
            relations: new Map(response.relations.map((rel) => [`${rel.id}:${rel.source}:${rel.target}`, rel])),
          });
          setSelectedEntityId(response.root_id);
          setPanOffset({ x: 0, y: 0 });
        } else {
          const responseBranch = await fetchTreeBranch({
            entidade_id: entidadeId,
            max_depth: payloadDepth,
            max_per_node: maxPerNode,
            direction: options.direction ?? "all",
            include_weak: includeWeak,
            relation_scope: relationScope,
          });

          setTree((current) => {
            const anchorDepth = current.nodes.get(entidadeId)?.depth ?? 0;
            const nextNodes = new Map(current.nodes);
            const nextRelations = new Map(current.relations);

            for (const node of responseBranch.nodes) {
              const adjustedDepth = node.id === entidadeId ? anchorDepth : anchorDepth + node.depth;
              const existing = nextNodes.get(node.id);
              if (!existing || Math.abs(adjustedDepth) < Math.abs(existing.depth)) {
                nextNodes.set(node.id, { ...node, depth: adjustedDepth });
              }
            }

            for (const rel of responseBranch.relations) {
              nextRelations.set(`${rel.id}:${rel.source}:${rel.target}`, rel);
            }

            return {
              rootId: current.rootId,
              nodes: nextNodes,
              relations: nextRelations,
            };
          });
        }
      } catch (error) {
        setApiError("Não foi possível carregar a árvore. Confirme se a API está online.");
        if (error instanceof Error) {
          console.error(error);
        }
      } finally {
        setLoadingTree(false);
      }
    },
    [includeWeak, maxPerNode, treeMode],
  );

  const loadEntityDetail = useCallback(async (entityId: string) => {
    try {
      const payload = await fetchEntityDetail(entityId);
      setSelectedDetail(payload);
    } catch {
      setSelectedDetail(null);
    }
  }, []);

  const selectEntity = useCallback(
    async (entityId: string) => {
      setSelectedEntityId(entityId);
      await loadTreePayload(entityId, depth, { mode: "replace" });
      await loadEntityDetail(entityId);
    },
    [depth, loadEntityDetail, loadTreePayload],
  );

  const expand = useCallback(
    async (entityId: string, direction: "up" | "down" | "all") => {
      await loadTreePayload(entityId, 1, { mode: "merge", direction });
    },
    [loadTreePayload],
  );

  const relationForNode = useCallback(
    (node: EntityNode): string => {
      if (node.id === tree.rootId) {
        return "Selecionado como foco";
      }

      let best = {
        text: "ligação em contexto comum",
        score: Number.POSITIVE_INFINITY,
      };

      const targetDepth = node.depth < 0 ? node.depth + 1 : node.depth > 0 ? node.depth - 1 : null;
      for (const rel of tree.relations.values()) {
        if (rel.source !== node.id && rel.target !== node.id) {
          continue;
        }

        const neighborId = rel.source === node.id ? rel.target : rel.source;
        const neighbor = tree.nodes.get(neighborId);
        if (!neighbor) {
          continue;
        }

        const depthDiff = Math.abs(neighbor.depth - node.depth);
        const sourceIsNode = rel.source === node.id;
        const relationName = relationVerbFromPerspective(rel.tipo_vinculo, sourceIsNode);
        const candidateText = `${relationName} ${neighbor.nome}`;

        let score = depthDiff;

        if (targetDepth !== null && neighbor.depth === targetDepth) {
          score -= 0.7;
        }

        if (targetDepth === 0 && neighbor.depth === 0) {
          score -= 0.4;
        }

        if (rel.requer_revisao) {
          score += 0.4;
        }

        if (score < best.score) {
          best = { text: candidateText, score };
        }
      }

      return best.text;
    },
    [tree.nodes, tree.rootId, tree.relations],
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
    if (selectedEntityId && tree.rootId) {
      void loadEntityDetail(selectedEntityId);
    }
  }, [selectedEntityId, loadEntityDetail, tree.rootId]);

  const nodesByDepth = useMemo(() => {
    const buckets = new Map<number, EntityNode[]>();
    for (const node of tree.nodes.values()) {
      const list = buckets.get(node.depth) ?? [];
      list.push(node);
      buckets.set(node.depth, list);
    }

    return Array.from(buckets.entries())
      .sort(([a], [b]) => a - b)
      .map(([depthLevel, nodes]) => ({
        depthLevel,
        title: depthTitle(depthLevel),
        nodes: nodes.sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
      }));
  }, [tree.nodes]);

  const hiddenRelations = useMemo(
    () => Array.from(tree.nodes.values()).reduce((acc, node) => acc + Math.max(node.hidden_vizinhos, 0), 0),
    [tree.nodes],
  );

  const canLoadMoreSearch = searchRows.length < searchTotal;

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-950">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-2xl font-semibold">Rede econômica (visão por árvore)</h1>
              <p className="text-sm text-zinc-600">Use a busca para localizar uma pessoa/empresa e explorar parentesco, sócios e fluxos em expansão sob demanda.</p>
            </div>
            {metadata ? <div className="text-xs text-zinc-500">{metadata.total_entidades.toLocaleString("pt-BR")} registros · {metadata.total_grupos.toLocaleString("pt-BR")} grupos</div> : null}
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
              {searchBusy ? <span className="text-xs text-amber-700">Buscando...</span> : null}

              {searchRows.slice(0, 12).map((item) => (
                <button
                  key={item.entidade_id}
                  type="button"
                  className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-xs text-zinc-700"
                  onClick={() => void selectEntity(item.entidade_id)}
                >
                  {item.nome} · {toEntityLabel(item.tipo_entidade)}
                </button>
              ))}

              {!searchBusy && searchTotal > 0 ? <span className="text-xs text-zinc-500">{searchRows.length} / {searchTotal} encontrados</span> : null}
            </div>

            {canLoadMoreSearch ? (
              <button
                type="button"
                className="mt-2 rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => void runSearch(debouncedSearch, searchOffset + 12)}
              >
                Ver mais
              </button>
            ) : null}
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-5">
            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Níveis da árvore
              <input
                type="range"
                min={1}
                max={6}
                value={depth}
                onChange={(event) => setDepth(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="text-xs text-zinc-600">{depth}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Ligações por pessoa
              <input
                type="range"
                min={5}
                max={20}
                value={maxPerNode}
                onChange={(event) => setMaxPerNode(Number(event.target.value))}
                className="mt-2 w-full"
              />
              <div className="text-xs text-zinc-600">{maxPerNode}</div>
            </label>

            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Modo da árvore
              <select
                value={treeMode}
                onChange={(event) => setTreeMode(event.target.value as TreeMode)}
                className="mt-2 block w-full rounded-md border border-zinc-300 bg-white px-2 py-1"
              >
                <option value="family">Só família</option>
                <option value="full">Família + societário</option>
              </select>
            </label>

            <label className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={includeWeak}
                onChange={(event) => setIncludeWeak(event.target.checked)}
              />
              Mostrar evidências fracas
            </label>

            <button
              type="button"
              className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
              onClick={() => {
                if (!tree.rootId) {
                  return;
                }

                void loadTreePayload(tree.rootId, depth, { mode: "replace" });
              }}
            >
              <ArrowsClockwise size={14} />
              Atualizar árvore
            </button>
          </div>
        </header>

        {apiError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{apiError}</div> : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
          <article className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm text-zinc-700">Árvore de vínculos</h2>
              <div className="text-xs text-zinc-500">
                Arraste para acompanhar o avanço da árvore.
              </div>
            </div>

            {loadingTree ? <p className="mb-2 text-sm text-zinc-600">Carregando...</p> : null}

            {nodesByDepth.length === 0 ? (
              <p className="text-sm text-zinc-500">Selecione um nome para montar a visualização.</p>
            ) : null}

            <div className="overflow-hidden rounded-md border border-zinc-100 p-2">
              <div
                ref={treeContainerRef}
                className={`min-h-[56vh] rounded-md ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
                style={{ touchAction: "none" }}
                onPointerDown={onPanStart}
                onPointerMove={onPanMove}
                onPointerUp={onPanStop}
                onPointerCancel={onPanStop}
                onPointerLeave={onPanStop}
              >
                <div className="relative p-2" style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }}>
                  {nodesByDepth.map((layer) => (
                    <div key={layer.depthLevel} className="mb-3">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                        {layer.title}
                        <span className="ml-2 text-zinc-400">(profundidade {layer.depthLevel})</span>
                      </div>

                      <div className="flex flex-wrap gap-3">
                        {layer.nodes.map((node) => {
                          const isSelected = node.id === selectedEntityId;
                          const relationHint = relationForNode(node);

                          return (
                            <div
                              key={node.id}
                              className={`w-full max-w-[320px] rounded-lg border border-zinc-200 p-3 ${
                                isSelected ? "bg-emerald-50 ring-2 ring-emerald-300" : "bg-white"
                              }`}
                            >
                              <button
                                type="button"
                                className="w-full text-left"
                                onClick={() => {
                                  if (node.id !== selectedEntityId) {
                                    void selectEntity(node.id);
                                  }
                                }}
                              >
                                <p className="text-sm font-semibold">{node.nome}</p>
                                <p className="text-xs text-zinc-600">{toEntityLabel(node.tipo_entidade)}</p>
                                <p className="text-xs text-zinc-500">{node.cpf_cnpj || "sem documento"}</p>
                              </button>

                              <p className="mt-2 text-xs text-zinc-600">{relationHint}</p>

                              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                                <span className="rounded-full border border-zinc-200 bg-zinc-50 px-2 py-1 text-zinc-600">
                                  {node.status_entidade || "sem status"}
                                </span>
                                {node.hidden_vizinhos > 0 ? (
                                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-amber-700">
                                    +{node.hidden_vizinhos} vínculos ocultos
                                  </span>
                                ) : null}
                              </div>

                              <div className="mt-2 flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => void expand(node.id, "up")}
                                >
                                  <ArrowBendUpLeft size={14} />
                                  Ver acima
                                </button>
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => void expand(node.id, "down")}
                                >
                                  <ArrowDown size={14} />
                                  Ver abaixo
                                </button>
                                <button
                                  type="button"
                                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                  onClick={() => void expand(node.id, "all")}
                                >
                                  <ArrowsClockwise size={14} />
                                  Abrir tudo
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}

                  <p className="px-2 text-xs text-zinc-500">Possíveis vínculos não exibidos por limite atual: {hiddenRelations}</p>
                </div>
              </div>
            </div>
          </article>

          <aside className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-base font-semibold">Detalhes da seleção</h2>
              <button
                type="button"
                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => {
                  if (!selectedEntityId) {
                    return;
                  }

                  const nextDepth = Math.max(1, depth - 1);
                  setDepth(nextDepth);
                  void selectEntity(selectedEntityId);
                }}
              >
                <ArrowsIn size={14} />
                Menos nível
              </button>
            </div>

            {!selectedDetail ? (
              <p className="text-sm text-zinc-500">Clique em uma entidade da árvore para ver os dados.</p>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="font-semibold">{selectedDetail.nome_canonico || selectedDetail.nome_original}</p>
                <p><strong>Documento:</strong> {selectedDetail.cpf_cnpj || "-"}</p>
                <p><strong>Tipo:</strong> {toEntityLabel(selectedDetail.tipo_entidade)}</p>
                <p><strong>Status:</strong> {selectedDetail.status_entidade || "-"}</p>
                <p><strong>Nascimento:</strong> {selectedDetail.data_nascimento || "-"}</p>
                <p><strong>Última atualização:</strong> {selectedDetail.data_atualizacao || "-"}</p>
                <p><strong>Conexões:</strong> {selectedDetail.total_vinculos} · Grupos: {selectedDetail.total_grupos}</p>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                  <p className="mb-1 font-medium">Principais tipos de vínculo</p>
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
                    <p className="mb-1 font-medium">Observação</p>
                    <p className="text-xs">{selectedDetail.alertas}</p>
                  </div>
                ) : null}
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              <button
                type="button"
                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1"
                onClick={() => {
                  if (!selectedEntityId) {
                    return;
                  }

                  const nextDepth = Math.min(7, depth + 1);
                  setDepth(nextDepth);
                  void selectEntity(selectedEntityId);
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
                }}
              >
                <House size={14} />
                Limpar
              </button>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

export default App;
