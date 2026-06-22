import { MagnifyingGlass, House, ArrowsOut, ArrowsIn } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { EntityNode, EntityDetailResponse, RelationItem, SearchItem, TreeResponse } from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchSearch,
  fetchTree,
  fetchTreeBranch,
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

const HUMAN_RELATION_LABEL: Record<string, string> = {
  FILHO_DE: "pai/mãe",
  PAI_DE: "filho(a)",
  MAE_DE: "filho(a)",
  CONJUGE_DE: "cônjuge",
  CONJUGE_NOME_CANDIDATO: "cônjuge",
  IRMAO_DE: "irmão(a)",
  TIO_TIA_DE: "tio/tia",
  SOCIO_DE: "sócio",
  CONTROLADOR_DIRETO: "controle societário",
  CONTROLADOR_CONJUNTO_CANDIDATO: "controle conjunto",
  INFLUENCIA_RELEVANTE: "participação relevante",
  SOCIO_MINORITARIO: "participação minoritária",
  PARTICIPACAO_INDIRETA: "participação indireta",
  ENDERECO_COMPARTILHADO: "endereço em comum",
  CONTATO_COMPARTILHADO: "contato compartilhado",
  EMPREGADO_DE: "vínculo de emprego",
  ESPOLIO_DE: "espólio",
  DEPENDENCIA_FINANCEIRA_CANDIDATA: "dependência sugerida",
  TRANSFERIU_PARA: "fluxo financeiro",
};

const relationLabel = (type: string): string => HUMAN_RELATION_LABEL[type] ?? type.toLowerCase().split("_").join(" ");

const toFriendlyEntityType = (value: string): string => {
  switch (value) {
    case "PF":
      return "Pessoa física";
    case "PJ":
      return "Empresa";
    case "PF_EXTERNA":
      return "Pessoa (sem cadastro)";
    case "PJ_EXTERNA":
      return "Empresa (sem cadastro)";
    case "ESPOLIO":
      return "Espólio";
    default:
      return value;
  }
};

const formatCpfOrEmpty = (value: string): string => value || "-";

const depthLabel = (depth: number): string => {
  if (depth < 0) return `Antepassados (${Math.abs(depth)})`;
  if (depth > 0) return `Descendentes (${depth})`;
  return "Selecionado";
};

const relationFromNodePerspective = (relationType: string, sourceIsCurrentNode: boolean): string => {
  if (relationType === "FILHO_DE") {
    return sourceIsCurrentNode ? "pai/mãe" : "filho(a)";
  }

  if (relationType === "PAI_DE" || relationType === "MAE_DE") {
    return sourceIsCurrentNode ? "filho(a)" : "pai/mãe";
  }

  if (relationType === "IRMAO_DE") {
    return "irmão(a)";
  }

  if (relationType === "CONJUGE_DE" || relationType === "CONJUGE_NOME_CANDIDATO") {
    return "cônjuge";
  }

  if (relationType === "TIO_TIA_DE") {
    return "tio/tia";
  }

  if (relationType === "SOCIO_DE") {
    return "sócio";
  }

  if (relationType === "CONTROLADOR_DIRETO") {
    return "controlador de";
  }

  if (relationType === "CONTROLADOR_CONJUNTO_CANDIDATO") {
    return "controle conjunto com";
  }

  if (relationType === "INFLUENCIA_RELEVANTE") {
    return "participação relevante em";
  }

  if (relationType === "SOCIO_MINORITARIO") {
    return "participação societária em";
  }

  if (relationType === "PARTICIPACAO_INDIRETA") {
    return "participação indireta em";
  }

  if (relationType === "DEPENDENCIA_FINANCEIRA_CANDIDATA") {
    return "dependência financeira sugerida com";
  }

  if (relationType === "ENDERECO_COMPARTILHADO") {
    return "endereço em comum com";
  }

  if (relationType === "CONTATO_COMPARTILHADO") {
    return "contato compartilhado com";
  }

  if (relationType === "TRANSFERIU_PARA") {
    return "transferiu para";
  }

  return relationLabel(relationType);
};

function useDebounced<T>(value: T, delay = 350): T {
  const [valueDebounced, setValueDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setValueDebounced(value);
    }, delay);

    return () => clearTimeout(timer);
  }, [value, delay]);

  return valueDebounced;
}

function App() {
  const [searchTerm, setSearchTerm] = useState("");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchOffset, setSearchOffset] = useState(0);
  const [searchRows, setSearchRows] = useState<SearchItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [metadata, setMetadata] = useState<ApiMeta | null>(null);

  const [selectedEntityId, setSelectedEntityId] = useState<string>("");
  const [selectedDetail, setSelectedDetail] = useState<EntityDetailResponse | null>(null);
  const [tree, setTree] = useState<TreeState>({
    rootId: "",
    nodes: new Map<string, EntityNode>(),
    relations: new Map<string, RelationItem>(),
  });

  const [loadingTree, setLoadingTree] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const [depth, setDepth] = useState(2);
  const [maxPerNode, setMaxPerNode] = useState(10);
  const [showWeak, setShowWeak] = useState(false);
  const [relationScope, setRelationScope] = useState("family");
  const treeContainerRef = useRef<HTMLDivElement | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const panStartRef = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const debouncedSearch = useDebounced(searchTerm);

  const loadMetadata = useCallback(async () => {
    try {
      const data = await fetch("/api/metadata").then((res) => res.json());
      setMetadata(data as ApiMeta);
    } catch {
      setMetadata(null);
    }
  }, []);

  const executeSearch = useCallback(
    async (query: string, offset = 0) => {
      if (!query || query.trim().length < 2) {
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
          const seen = new Map<string, SearchItem>(
            [...searchRows, ...result.items].map((item) => [item.entidade_id, item]),
          );
          setSearchRows(Array.from(seen.values()));
        }
        setSearchTotal(result.total);
        setSearchOffset(offset);
      } catch {
        if (offset === 0) {
          setSearchRows([]);
          setSearchTotal(0);
        }
      } finally {
        setSearchBusy(false);
      }
    },
    [searchRows],
  );

  const loadTreePayload = useCallback(
    async (
      entidadeId: string,
      upDownDepth: number,
      opts?: {
        direction?: "all" | "up" | "down";
        maxPerNode?: number;
        includeIndirect?: boolean;
        relationScope?: string;
        mode?: "replace" | "merge";
      },
    ) => {
      if (!entidadeId) {
        return;
      }

      setErrorMessage("");
      setLoadingTree(true);

      const options = {
        max_depth: upDownDepth,
        max_per_node: opts?.maxPerNode ?? maxPerNode,
        include_indirect: opts?.includeIndirect ?? showWeak,
        relation_scope: opts?.relationScope ?? relationScope,
      } as const;

      try {
        const payload: TreeResponse =
          opts?.mode === "replace"
            ? await fetchTree({
                entidade_id: entidadeId,
                max_depth: options.max_depth,
                max_per_node: options.max_per_node,
                include_indirect: options.include_indirect,
                relation_scope: options.relation_scope,
              })
            : await fetchTreeBranch({
                entidade_id: entidadeId,
                max_depth: options.max_depth,
                max_per_node: options.max_per_node,
                direction: opts?.direction ?? "all",
                include_indirect: options.include_indirect,
                relation_scope: options.relation_scope,
              });

        if (opts?.mode === "replace" || tree.nodes.size === 0 || tree.rootId !== entidadeId) {
          setTree({
            rootId: payload.root_id,
            nodes: new Map(payload.nodes.map((node) => [node.id, node])),
            relations: new Map(payload.relations.map((rel) => [`${rel.id}:${rel.source}:${rel.target}`, rel])),
          });
          setSelectedEntityId(payload.root_id);
          setPanOffset({ x: 0, y: 0 });
        } else {
          setTree((current) => {
            const anchorDepth = current.nodes.get(entidadeId)?.depth ?? 0;
            const nextNodes = new Map(current.nodes);
            const nextRelations = new Map(current.relations);

            for (const node of payload.nodes) {
              const depth = node.id === entidadeId ? anchorDepth : anchorDepth + node.depth;
              const currentNode = nextNodes.get(node.id);
              if (!currentNode || Math.abs(depth) < Math.abs(currentNode.depth)) {
                nextNodes.set(node.id, { ...node, depth });
              }
            }

            for (const rel of payload.relations) {
              nextRelations.set(`${rel.id}:${rel.source}:${rel.target}`, rel);
            }

            return {
              rootId: current.rootId,
              nodes: nextNodes,
              relations: nextRelations,
            };
          });
        }
      } catch {
        setErrorMessage("Não foi possível carregar a árvore. Confirme se a API está ativa.");
      } finally {
        setLoadingTree(false);
      }
    },
    [maxPerNode, showWeak, relationScope, tree.nodes.size, tree.rootId],
  );

  const loadEntityDetail = useCallback(async (entityId: string) => {
    try {
      const detail = await fetchEntityDetail(entityId);
      setSelectedDetail(detail);
    } catch {
      setSelectedDetail(null);
    }
  }, []);

  const chooseEntity = useCallback(
    async (entityId: string) => {
      setSelectedEntityId(entityId);
      await loadTreePayload(entityId, depth, { mode: "replace" });
      await loadEntityDetail(entityId);
    },
    [depth, loadEntityDetail, loadTreePayload],
  );

  const expandNode = useCallback(
    async (entityId: string, direction: "all" | "up" | "down") => {
      await loadTreePayload(entityId, 1, {
        direction,
        maxPerNode,
        includeIndirect: showWeak,
        relationScope,
        mode: "merge",
      });
    },
    [loadTreePayload, maxPerNode, relationScope, showWeak],
  );

  const relationByNode = useCallback(
    (node: EntityNode): string => {
      if (node.id === tree.rootId) {
        return "Referência (seleção atual)";
      }

      let bestRelation = "";
      let bestScore = Number.POSITIVE_INFINITY;

      for (const rel of tree.relations.values()) {
        if (!rel.source || !rel.target) {
          continue;
        }

        const sourceIsCurrentNode = rel.source === node.id;
        const isInvolved = sourceIsCurrentNode || rel.target === node.id;

        if (!isInvolved) {
          continue;
        }

        const neighborId = sourceIsCurrentNode ? rel.target : rel.source;
        const neighbor = tree.nodes.get(neighborId);
        if (!neighbor) {
          continue;
        }

        const directionDeltaFromNode = sourceIsCurrentNode
          ? rel.relation_depth_delta
          : -rel.relation_depth_delta;
        const verticalDistance = Math.abs(neighbor.depth - node.depth);
        const score = Math.abs(directionDeltaFromNode === 0 ? 2 : directionDeltaFromNode)
          + verticalDistance * 0.08
          + (rel.requer_revisao ? 0.25 : 0);

        if (score >= bestScore) {
          continue;
        }

        const relationVerb = relationFromNodePerspective(rel.tipo_vinculo, sourceIsCurrentNode);
        bestScore = score;
        bestRelation = `${relationVerb} ${neighbor.nome || "entidade"}`;
      }

      return bestRelation || "vínculo indireto";
    },
    [tree],
  );

  const onPanStart = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (tree.nodes.size === 0 || event.button !== 0) {
        return;
      }

      setIsPanning(true);
      panStartRef.current = {
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

      const deltaX = event.clientX - panStartRef.current.x;
      const deltaY = event.clientY - panStartRef.current.y;
      setPanOffset({
        x: panStartRef.current.baseX + deltaX,
        y: panStartRef.current.baseY + deltaY,
      });
    },
    [isPanning],
  );

  const onPanEnd = useCallback((event: PointerEvent<HTMLDivElement>) => {
    setIsPanning(false);
    treeContainerRef.current?.releasePointerCapture(event.pointerId);
  }, []);

  useEffect(() => {
    void loadMetadata();
    void fetchHealth().catch(() => {
      setErrorMessage("API offline. Rode backend: npm run backend");
    });
  }, [loadMetadata]);

  useEffect(() => {
    void executeSearch(debouncedSearch, 0);
  }, [debouncedSearch, executeSearch]);

  const nodesByDepth = useMemo(() => {
    const buckets = new Map<number, EntityNode[]>();
    for (const node of tree.nodes.values()) {
      const bucket = buckets.get(node.depth) ?? [];
      bucket.push(node);
      buckets.set(node.depth, bucket);
    }

    const keys = Array.from(buckets.keys()).sort((a, b) => a - b);
    return keys.map((depthKey) => ({
      depth: depthKey,
      label: depthLabel(depthKey),
      nodes: buckets.get(depthKey)!.slice().sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    }));
  }, [tree.nodes]);

  const totalHiddenLinks = useMemo(
    () => Array.from(tree.nodes.values()).reduce((acc, node) => acc + Math.max(node.hidden_vizinhos, 0), 0),
    [tree.nodes],
  );

  useEffect(() => {
    if (selectedEntityId && tree.rootId) {
      void loadEntityDetail(selectedEntityId);
    }
  }, [selectedEntityId, loadEntityDetail]);

  const canLoadMoreSearch = searchRows.length < searchTotal;

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-950">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-4 p-4">
        <header className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">Rede econômica para pessoas e empresas</h1>
              <p className="text-sm text-zinc-600">Visualização em árvore, otimizada para operação com muitos cadastros.</p>
            </div>
            {metadata ? (
              <div className="text-xs text-zinc-500">
                {metadata.total_entidades.toLocaleString("pt-BR")} pessoas/empresas · {metadata.total_grupos.toLocaleString("pt-BR")} grupos
              </div>
            ) : null}
          </div>

          <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3">
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
                  type="button"
                  key={item.entidade_id}
                  className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-xs text-zinc-700"
                  onClick={() => void chooseEntity(item.entidade_id)}
                >
                  {item.nome} · {toFriendlyEntityType(item.tipo_entidade)}
                </button>
              ))}
              {!searchBusy && searchTotal > 0 ? (
                <span className="text-xs text-zinc-500">{searchRows.length} / {searchTotal} resultados</span>
              ) : null}
            </div>
            {canLoadMoreSearch ? (
              <button
                type="button"
                className="mt-2 rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => void executeSearch(debouncedSearch, searchOffset + 12)}
              >
                Ver mais resultados
              </button>
            ) : null}
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <label className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              Profundidade (pais/filhos)
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
              Ligações por entidade
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
              Escopo
              <select
                value={relationScope}
                onChange={(event) => setRelationScope(event.target.value)}
                className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-2 py-1"
              >
                <option value="family">Somente família</option>
                <option value="family,business">Família + Societário</option>
                <option value="all">Tudo</option>
              </select>
            </label>

            <label className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={showWeak}
                onChange={(event) => setShowWeak(event.target.checked)}
              />
              Incluir relações fracas
            </label>
          </div>
        </header>

        {errorMessage ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{errorMessage}</div> : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
          <article className="rounded-xl border border-zinc-200 bg-white p-3">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm text-zinc-700">
                Árvore do selecionado
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                  onClick={() => {
                    if (!tree.rootId) return;
                    void loadTreePayload(tree.rootId, depth, { mode: "replace", includeIndirect: showWeak, relationScope, maxPerNode });
                  }}
                >
                  <MagnifyingGlass size={14} />
                  atualizar
                </button>
                <button
                  type="button"
                  className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                  onClick={() => {
                    setSelectedEntityId("");
                    setSelectedDetail(null);
                    setTree({ rootId: "", nodes: new Map(), relations: new Map() });
                    setPanOffset({ x: 0, y: 0 });
                  }}
                >
                  <House size={14} />
                  limpar
                </button>
              </div>
            </div>

            {loadingTree ? <p className="text-sm text-zinc-600">Carregando árvore...</p> : null}

            {nodesByDepth.length === 0 ? <p className="text-sm text-zinc-500">Selecione uma pessoa/empresa para visualizar a árvore.</p> : null}

            <div className="overflow-hidden rounded-md border border-zinc-100 p-2">
              <div
                ref={treeContainerRef}
                className={`min-h-[58vh] rounded-md ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
                style={{ touchAction: "none" }}
                onPointerDown={onPanStart}
                onPointerMove={onPanMove}
                onPointerUp={onPanEnd}
                onPointerCancel={onPanEnd}
                onPointerLeave={onPanEnd}
              >
                <p className="px-2 pb-2 text-xs text-zinc-500">
                  Passe o mouse e arraste para navegar na árvore. Clique em um nó para abrir a nova raiz.
                </p>
                <div
                  className="flex min-h-[54vh] flex-col gap-3 p-1"
                  style={{ transform: `translate(${panOffset.x}px, ${panOffset.y}px)` }}
                >
                {nodesByDepth.map((layer) => (
                  <div key={layer.depth}>
                    <div className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">
                      {layer.label}
                    </div>
                    <div className="flex flex-wrap gap-3">
                      {layer.nodes.map((node) => {
                        const isSelected = node.id === selectedEntityId;
                        const relationText = relationByNode(node);

                        return (
                          <div
                            key={node.id}
                            className={`w-full max-w-[320px] rounded-lg border border-zinc-200 p-3 ${
                              isSelected ? "bg-emerald-50 ring-2 ring-emerald-300" : "bg-white"
                            }`}
                          >
                            <div className="text-xs uppercase tracking-[0.12em] text-zinc-500">profundidade {node.depth}</div>
                            <button
                              type="button"
                              className="mt-1 w-full text-left"
                              onClick={() => {
                                if (node.id !== selectedEntityId) {
                                  void chooseEntity(node.id);
                                }
                              }}
                            >
                              <div className="text-sm font-semibold">{node.nome}</div>
                              <div className="text-xs text-zinc-600">{toFriendlyEntityType(node.tipo_entidade)}</div>
                              <div className="text-[11px] text-zinc-500">{formatCpfOrEmpty(node.cpf_cnpj)}</div>
                              <div className="mt-2 text-[11px] text-zinc-600">Relação: {relationText}</div>
                            </button>
                            <div className="mt-2 flex flex-wrap gap-2 text-xs">
                              <span className="rounded-full border border-zinc-200 bg-zinc-50 px-2 py-1 text-zinc-600">
                                {node.status_entidade || "sem status"}
                              </span>
                              {node.hidden_vizinhos > 0 ? (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-amber-700">
                                  +{node.hidden_vizinhos} relações ocultas
                                </span>
                              ) : null}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => void expandNode(node.id, "up")}
                              >
                                Ver pai/mãe
                              </button>
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => void expandNode(node.id, "down")}
                              >
                                Ver filhos
                              </button>
                              <button
                                type="button"
                                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                                onClick={() => void expandNode(node.id, "all")}
                              >
                                Expandir tudo
                              </button>
                            </div>
                            <p className="mt-1 text-[11px] text-zinc-500">
                              Clique em +pai/mãe, +filhos ou + tudo para abrir a perna a partir desse item.
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}

                <div className="px-2 text-xs text-zinc-500">
                  Total de relações ocultas no contexto atual: {totalHiddenLinks}
                </div>
              </div>
            </div>
            </div>
          </article>

          <aside className="rounded-xl border border-zinc-200 bg-white p-3">
            <h2 className="text-base font-semibold">Detalhe da entidade</h2>

            {!selectedDetail ? (
              <p className="mt-2 text-sm text-zinc-500">Clique em uma entidade para ver os dados.</p>
            ) : (
              <div className="mt-3 space-y-3 text-sm">
                <p className="font-medium">{selectedDetail.nome_canonico || selectedDetail.nome_original}</p>
                <p><strong>Documento:</strong> {formatCpfOrEmpty(selectedDetail.cpf_cnpj)}</p>
                <p><strong>Tipo:</strong> {toFriendlyEntityType(selectedDetail.tipo_entidade)}</p>
                <p><strong>Status:</strong> {selectedDetail.status_entidade || "-"}</p>
                <p><strong>Nascimento:</strong> {selectedDetail.data_nascimento || "-"}</p>
                <p><strong>Última atualização:</strong> {selectedDetail.data_atualizacao || "-"}</p>
                <p><strong>Grupos:</strong> {selectedDetail.total_grupos} · vínculos: {selectedDetail.total_vinculos}</p>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
                  <p className="mb-1 font-medium">Conexões por tipo</p>
                  <ul className="list-disc space-y-1 pl-5 text-xs">
                    {Object.entries(selectedDetail.conexoes_por_tipo)
                      .slice(0, 12)
                      .map(([tipo, quantidade]) => (
                        <li key={tipo}>
                          {relationLabel(tipo)}: {quantidade}
                        </li>
                      ))}
                    {Object.keys(selectedDetail.conexoes_por_tipo).length === 0 ? <li>Nenhuma conexão encontrada.</li> : null}
                  </ul>
                </div>

                {selectedDetail.alertas ? (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-amber-900">
                    <p className="mb-1 font-medium">Alertas</p>
                    <p className="text-xs">{selectedDetail.alertas}</p>
                  </div>
                ) : null}
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => {
                  if (!selectedEntityId) return;
                  setDepth((current) => Math.max(1, current - 1));
                  void chooseEntity(selectedEntityId);
                }}
              >
                <ArrowsIn size={14} /> menos nível
              </button>
              <button
                type="button"
                className="rounded-md border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs"
                onClick={() => {
                  if (!selectedEntityId) return;
                  setDepth((current) => Math.min(7, current + 1));
                  void chooseEntity(selectedEntityId);
                }}
              >
                <ArrowsOut size={14} /> mais nível
              </button>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

export default App;
