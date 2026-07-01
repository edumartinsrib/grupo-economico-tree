import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowsClockwise,
  Buildings,
  Crosshair,
  Database,
  GitBranch,
  House,
  MagnifyingGlass,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
  SlidersHorizontal,
  TreeStructure,
  UsersThree,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import type { ApiMeta, EntityDetailResponse, SearchItem, TreeNode, TreeRelation, TreeResponse } from "./lib/api";
import {
  fetchEntityDetail,
  fetchHealth,
  fetchMetadata,
  fetchSearch,
  fetchTreeNeighbors,
  fetchTreeSeed,
} from "./lib/api";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { Skeleton } from "./components/ui/skeleton";
import { Switch } from "./components/ui/switch";
import { cn } from "./lib/cn";
import "./styles.css";

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

type WorkflowNode = TreeNode & {
  x: number;
  y: number;
  width: number;
  height: number;
};

type WorkflowLayout = {
  nodes: WorkflowNode[];
  nodeMap: Map<string, WorkflowNode>;
  width: number;
  height: number;
};

const WORKFLOW_NODE_WIDTH = 286;
const WORKFLOW_NODE_HEIGHT = 156;
const WORKFLOW_NODE_GAP = 28;
const WORKFLOW_LEVEL_GAP = 190;
const WORKFLOW_PADDING = 76;

const ENTITY_TYPE_LABEL: EntityType = {
  PF: "Pessoa física",
  PJ: "Empresa",
  PF_EXTERNA: "Pessoa parcial",
  PJ_EXTERNA: "Empresa parcial",
  ESPOLIO: "Espólio",
  GRUPO_ECONOMICO: "Grupo econômico",
};

const RELATION_LABEL: EntityType = {
  "pai/mãe": "Pai ou mãe",
  pai: "Pai",
  mãe: "Mãe",
  "filho(a)": "Filho(a)",
  irmão: "Irmão(a)",
  "irmão(a)": "Irmão(a)",
  "cônjuge": "Cônjuge",
  "cônjuge (candidato)": "Possível cônjuge",
  "sócio(a)": "Sócio(a)",
  "sócio(a) relevante": "Sócio(a) relevante",
  "sócio(a) minoritário(a)": "Sócio(a) minoritário(a)",
  "sócio(a) indireto(a)": "Sócio(a) indireto(a)",
  "controlador(a)": "Controlador(a)",
  "controle conjunto": "Controle conjunto",
  "grupo econômico existente": "Grupo econômico",
  "grupo vinculado": "Grupo vinculado",
  selecionado: "Selecionado",
};

const RELATION_TYPE_LABEL: EntityType = {
  FILHO_DE: "Filho(a)",
  PAI_DE: "Pai",
  MAE_DE: "Mãe",
  IRMAO_DE: "Irmão(a)",
  CONJUGE_DE: "Cônjuge",
  CONJUGE_NOME_CANDIDATO: "Possível cônjuge",
  PARENTESCO_AMBIGUO: "Parentesco a revisar",
  POSSIVEL_MESMO_GENITOR: "Possível familiar em comum",
  SOCIO_DE: "Sociedade",
  SOCIO_COTISTA: "Sociedade",
  CONTROLADOR_DIRETO: "Controle de empresa",
  CONTROLADOR_CONJUNTO_CANDIDATO: "Controle conjunto",
  INFLUENCIA_RELEVANTE: "Participação relevante",
  SOCIO_MINORITARIO: "Participação minoritária",
  PARTICIPACAO_INDIRETA: "Participação indireta",
  PERTENCE_A_GRUPO_EXISTENTE: "Grupo econômico",
  GRUPO_VINCULADO_POR_PESSOA: "Grupo vinculado por pessoa",
  GRUPO_AGREGADO_POR_FAMILIA: "Grupo agregado por família",
  EMPREGADO_DE: "Relação de emprego",
  TIO_TIA_DE: "Tio(a)",
  ESPOLIO_DE: "Espólio",
  ENDERECO_COMPARTILHADO: "Endereço compartilhado",
  CONTATO_COMPARTILHADO: "Contato compartilhado",
  TRANSFERIU_PARA: "Movimentação financeira",
  DEPENDENCIA_FINANCEIRA_CANDIDATA: "Possível dependência financeira",
  DEPENDENCIA_FINANCEIRA_CONFIRMADA: "Dependência financeira",
  EMPRESA_DE_GRUPO_OFICIAL: "Empresa do grupo",
};

const GROUP_RELATION_LABEL: EntityType = {
  FAMILIA_POSSUI_EMPRESA: "Família possui empresa",
  CONTROLADOR_COMUM: "Controlador comum",
  DEPENDENCIA_ECONOMICA: "Dependência econômica",
  GRUPOS_VINCULADOS_POR_ENTIDADE: "Pessoa em mais de um grupo",
  AGREGACAO_FAMILIAR_GRUPO_OFICIAL: "Agregação familiar",
};

const GROUP_ROLE_LABEL: EntityType = {
  MEMBRO_GRUPO_EXISTENTE: "Membro do grupo",
  EMPRESA_ANCORA: "Empresa principal",
  CONTROLADOR: "Controlador",
  EMPRESA_CONTROLADA: "Empresa controlada",
  MEMBRO_FAMILIA: "Membro da família",
  EMPRESA_DA_FAMILIA: "Empresa da família",
  CONJUGE: "Cônjuge",
  FILHO: "Filho(a)",
  PAI: "Pai",
  MAE: "Mãe",
};

function clampLabel(value: string): string {
  return RELATION_LABEL[value?.trim().toLowerCase()] || value || "Relação";
}

function displayEntityType(value: string): string {
  return ENTITY_TYPE_LABEL[value] || "Cadastro";
}

function displayRelationType(value: string): string {
  return RELATION_TYPE_LABEL[value] || clampLabel(value);
}

function displayGroupRelationType(value: string): string {
  return GROUP_RELATION_LABEL[value] || value.replace(/_/g, " ").toLowerCase();
}

function displayGroupRole(value: string): string {
  return GROUP_ROLE_LABEL[value] || value.replace(/_/g, " ").toLowerCase();
}

function displayDocumentStatus(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (["true", "1", "sim", "valido", "válido"].includes(normalized)) {
    return "Validado";
  }
  if (!normalized) {
    return "Sem validação";
  }
  return "Não validado";
}

function formatCount(value?: number): string {
  return Number(value || 0).toLocaleString("pt-BR");
}

function formatDocument(value: string): string {
  return value || "-";
}

function statusVariant(value: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const normalized = value.toLowerCase();
  if (normalized.includes("ativo") || normalized.includes("validado")) return "success";
  if (normalized.includes("revis") || normalized.includes("candidato")) return "warning";
  if (normalized.includes("inativo") || normalized.includes("não")) return "danger";
  if (normalized.includes("grupo")) return "info";
  return "neutral";
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

function buildWorkflowLayout(nodes: Iterable<TreeNode>): WorkflowLayout {
  const grouped = groupByLevel(nodes);
  const levels = Array.from(grouped.keys());
  const maxNodesInLevel = Math.max(1, ...Array.from(grouped.values()).map((items) => items.length));
  const width = Math.max(
    900,
    WORKFLOW_PADDING * 2 + maxNodesInLevel * WORKFLOW_NODE_WIDTH + (maxNodesInLevel - 1) * WORKFLOW_NODE_GAP,
  );
  const height = Math.max(
    540,
    WORKFLOW_PADDING * 2 + levels.length * WORKFLOW_NODE_HEIGHT + Math.max(0, levels.length - 1) * WORKFLOW_LEVEL_GAP,
  );
  const minLevel = levels[0] ?? 0;
  const positioned: WorkflowNode[] = [];
  const nodeMap = new Map<string, WorkflowNode>();

  for (const [level, levelNodes] of grouped.entries()) {
    const rowWidth = levelNodes.length * WORKFLOW_NODE_WIDTH + Math.max(0, levelNodes.length - 1) * WORKFLOW_NODE_GAP;
    const xStart = (width - rowWidth) / 2;
    const y = WORKFLOW_PADDING + (level - minLevel) * (WORKFLOW_NODE_HEIGHT + WORKFLOW_LEVEL_GAP);

    levelNodes.forEach((node, index) => {
      const positionedNode = {
        ...node,
        x: xStart + index * (WORKFLOW_NODE_WIDTH + WORKFLOW_NODE_GAP),
        y,
        width: WORKFLOW_NODE_WIDTH,
        height: WORKFLOW_NODE_HEIGHT,
      };
      positioned.push(positionedNode);
      nodeMap.set(node.id, positionedNode);
    });
  }

  return { nodes: positioned, nodeMap, width, height };
}

function workflowEdgePath(source: WorkflowNode, target: WorkflowNode): string {
  const sourceX = source.x + source.width / 2;
  const sourceY = source.y + source.height / 2;
  const targetX = target.x + target.width / 2;
  const targetY = target.y + target.height / 2;
  const vertical = targetY >= sourceY ? 1 : -1;
  const controlDistance = Math.max(70, Math.abs(targetY - sourceY) / 2);

  if (Math.abs(targetY - sourceY) < 20) {
    const horizontalDistance = Math.max(80, Math.abs(targetX - sourceX) / 2);
    const horizontal = targetX >= sourceX ? 1 : -1;
    return `M ${sourceX} ${sourceY} C ${sourceX + horizontal * horizontalDistance} ${sourceY - 72}, ${targetX - horizontal * horizontalDistance} ${targetY - 72}, ${targetX} ${targetY}`;
  }

  return `M ${sourceX} ${sourceY} C ${sourceX} ${sourceY + vertical * controlDistance}, ${targetX} ${targetY - vertical * controlDistance}, ${targetX} ${targetY}`;
}

function relationStrokeClass(type: string): string {
  if (type === "GRUPO_AGREGADO_POR_FAMILIA") return "stroke-emerald-600";
  if (type === "PERTENCE_A_GRUPO_EXISTENTE") return "stroke-sky-600";
  if (type.includes("CONJUGE") || type.includes("IRMAO") || type.includes("FILHO") || type.includes("PAI") || type.includes("MAE")) return "stroke-zinc-500";
  return "stroke-zinc-400";
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("button, input, a, textarea, select"));
}

function relationBadgeForNode(node: TreeNode, anchorId: string): string {
  if (node.id === anchorId) {
    return "Selecionado";
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

function MetricTile({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="h-stack min-w-0 items-center gap-3 border-r border-zinc-200 px-4 py-3 last:border-r-0">
      <div className="center h-9 w-9 shrink-0 rounded-md border border-zinc-200 bg-zinc-50 text-zinc-600">{icon}</div>
      <div className="min-w-0">
        <div className="text-xs font-medium text-zinc-500">{label}</div>
        <div className="truncate font-mono text-lg font-semibold text-zinc-950">{value}</div>
      </div>
    </div>
  );
}

function App() {
  const [query, setQuery] = useState("");
  const [metadata, setMetadata] = useState<ApiMeta | null>(null);
  const [searchRows, setSearchRows] = useState<SearchItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchOffset, setSearchOffset] = useState(0);
  const [searchBusy, setSearchBusy] = useState(false);

  const [includeBusiness, setIncludeBusiness] = useState(true);
  const [includeWeak, setIncludeWeak] = useState(false);
  const [maxPerNode, setMaxPerNode] = useState(8);

  const [tree, setTree] = useState<TreeState>({ rootId: "", nodes: new Map(), relations: new Map() });
  const [branchState, setBranchState] = useState<Map<string, BranchState>>(new Map());
  const [branchCursor, setBranchCursor] = useState<Map<string, BranchCursor>>(new Map());
  const [detail, setDetail] = useState<EntityDetailResponse | null>(null);
  const [treeBusy, setTreeBusy] = useState(false);
  const [apiError, setApiError] = useState("");

  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(0.92);
  const [isPanning, setIsPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panStart = useRef({ x: 0, y: 0, baseX: 0, baseY: 0 });

  const workflowLayout = useMemo(() => buildWorkflowLayout(tree.nodes.values()), [tree.nodes]);
  const workflowRelations = useMemo(
    () =>
      Array.from(tree.relations.values()).filter(
        (relation) => workflowLayout.nodeMap.has(relation.source) && workflowLayout.nodeMap.has(relation.target),
      ),
    [tree.relations, workflowLayout.nodeMap],
  );
  const relationScope = includeBusiness ? "family,business" : "family";
  const hasTree = tree.nodes.size > 0;
  const currentAnchor = tree.nodes.get(tree.rootId);
  const visibleGroups = detail?.grupos.slice(0, 10) ?? [];
  const visibleCompanies = detail?.empresas.slice(0, 12) ?? [];
  const visibleGroupLinks = useMemo(
    () =>
      [...(detail?.vinculos_grupos ?? [])]
        .sort((left, right) => {
          const priorityLeft = left.tipo_relacao === "AGREGACAO_FAMILIAR_GRUPO_OFICIAL" ? 0 : 1;
          const priorityRight = right.tipo_relacao === "AGREGACAO_FAMILIAR_GRUPO_OFICIAL" ? 0 : 1;
          if (priorityLeft !== priorityRight) return priorityLeft - priorityRight;
          return right.relevancia - left.relevancia;
        })
        .slice(0, 10),
    [detail],
  );
  const canLoadMore = searchRows.length > 0 && searchRows.length < searchTotal;

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

  const runSearch = useCallback(async (text: string, offset = 0) => {
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
  }, []);

  const resetTree = useCallback(() => {
    setTree({ rootId: "", nodes: new Map(), relations: new Map() });
    setBranchState(new Map());
    setBranchCursor(new Map());
    setDetail(null);
    setApiError("");
    setPanOffset({ x: 0, y: 0 });
    setZoom(0.92);
  }, []);

  const applyTree = useCallback(
    (response: TreeResponse, mergeFrom?: string, forceReplace = false) => {
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
    },
    [tree.nodes],
  );

  const loadRootTree = useCallback(
    async (entidadeId: string) => {
      setTreeBusy(true);
      setApiError("");
      setTree({ rootId: "", nodes: new Map(), relations: new Map() });
      setPanOffset({ x: 0, y: 0 });
      setZoom(0.92);
      try {
        const response = await fetchTreeSeed({
          entidade_id: entidadeId,
          include_business: includeBusiness,
          include_weak: includeWeak,
          relation_scope: relationScope,
          max_up_per_node: Math.min(4, maxPerNode),
          max_down_per_node: Math.max(1, Math.min(14, maxPerNode)),
        });
        applyTree(response, undefined, true);
        await loadEntityDetail(entidadeId);
      } catch {
        setApiError("API indisponível ou consulta não localizada.");
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
      } catch {
        setApiError("Não foi possível abrir esse ramo.");
      } finally {
        setTreeBusy(false);
      }
    },
    [applyTree, branchCursor, branchState, includeBusiness, includeWeak, maxPerNode, relationScope],
  );

  const openNode = useCallback(
    async (nodeId: string) => {
      await loadEntityDetail(nodeId);
      const node = tree.nodes.get(nodeId);
      const level = node?.nivel ?? 0;
      if (node?.tipo_entidade === "GRUPO_ECONOMICO") {
        if (canExpandDirection(nodeId, "down", branchState)) {
          await loadNeighbors(nodeId, "down");
          return;
        }
        if (canExpandDirection(nodeId, "up", branchState)) {
          await loadNeighbors(nodeId, "up");
        }
        return;
      }
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
      if (tree.nodes.size === 0 || event.button !== 0 || isInteractiveTarget(event.target)) {
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
    if (canvasRef.current?.hasPointerCapture(event.pointerId)) {
      canvasRef.current.releasePointerCapture(event.pointerId);
    }
  }, []);

  const onWheelZoom = useCallback(
    (event: WheelEvent<HTMLDivElement>) => {
      if (!hasTree || !event.ctrlKey) {
        return;
      }
      event.preventDefault();
      setZoom((current) => {
        const next = current + (event.deltaY > 0 ? -0.08 : 0.08);
        return Math.min(1.6, Math.max(0.55, Number(next.toFixed(2))));
      });
    },
    [hasTree],
  );

  const recenterWorkflow = useCallback(() => {
    setPanOffset({ x: 0, y: 0 });
    setZoom(0.92);
  }, []);

  useEffect(() => {
    void loadMetadata();
    void fetchHealth().catch(() => {
      setApiError("API indisponível.");
    });
  }, [loadMetadata]);

  useEffect(() => {
    const timer = setTimeout(() => void runSearch(query), 250);
    return () => clearTimeout(timer);
  }, [query, runSearch]);

  return (
    <main className="min-h-[100dvh] bg-zinc-100 text-zinc-950">
      <div className="v-stack min-h-[100dvh]">
        <header className="border-b border-zinc-200 bg-white">
          <div className="mx-auto grid w-full max-w-[1600px] gap-3 px-4 py-4 xl:grid-cols-[1fr_auto]">
            <div className="min-w-0">
              <div className="h-stack items-center gap-2">
                <div className="center h-9 w-9 rounded-md bg-zinc-950 text-white">
                  <GitBranch size={18} weight="bold" />
                </div>
                <div className="min-w-0">
                  <h1 className="truncate text-xl font-semibold tracking-tight text-zinc-950">Painel de grupos econômicos</h1>
                  <div className="h-stack flex-wrap items-center gap-2 text-xs text-zinc-500">
                  <span>Base explicável</span>
                    <span className="h-1 w-1 rounded-full bg-zinc-300" />
                    <span>{currentAnchor?.nome || "Sem cadastro selecionado"}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 sm:grid-cols-2 xl:grid-cols-4">
              <MetricTile label="Cadastros" value={formatCount(metadata?.total_entidades)} icon={<Database size={18} />} />
              <MetricTile label="Relações" value={formatCount(metadata?.total_vinculos)} icon={<TreeStructure size={18} />} />
              <MetricTile label="Grupos" value={formatCount(metadata?.total_grupos)} icon={<UsersThree size={18} />} />
              <MetricTile label="Revisões" value={formatCount(metadata?.total_revisao)} icon={<WarningCircle size={18} />} />
            </div>
          </div>
        </header>

        {apiError ? (
          <div className="mx-auto mt-3 w-full max-w-[1600px] px-4">
            <div className="h-stack items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              <WarningCircle size={18} />
              <span>{apiError}</span>
            </div>
          </div>
        ) : null}

        <section className="mx-auto grid w-full max-w-[1600px] grow gap-4 p-4 xl:grid-cols-[340px_minmax(0,1fr)_380px]">
          <aside className="v-stack min-h-0 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Consulta</CardTitle>
              </CardHeader>
              <CardContent className="v-stack gap-4">
                <div className="v-stack gap-2">
                  <Label htmlFor="search">Nome, CPF, CNPJ ou grupo</Label>
                  <div className="relative">
                    <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={16} />
                    <Input
                      id="search"
                      className="pl-9"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Carlos, Almeida, 900..."
                    />
                    {query ? (
                      <button
                        type="button"
                        className="center absolute right-2 top-1/2 h-6 w-6 -translate-y-1/2 rounded-md text-zinc-400 hover:bg-zinc-100 hover:text-zinc-800"
                        onClick={() => setQuery("")}
                        aria-label="Limpar busca"
                      >
                        <X size={14} />
                      </button>
                    ) : null}
                  </div>
                </div>

                <div className="v-stack max-h-[34vh] gap-2 overflow-y-auto pr-1">
                  {searchBusy ? (
                    <>
                      <Skeleton className="h-14" />
                      <Skeleton className="h-14" />
                      <Skeleton className="h-14" />
                    </>
                  ) : null}

                  {!searchBusy && query.trim().length >= 2 && searchRows.length === 0 ? (
                    <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-500">Nenhum cadastro encontrado.</div>
                  ) : null}

                  {searchRows.map((row) => (
                    <button
                      key={row.entidade_id}
                      type="button"
                      className="v-stack rounded-md border border-zinc-200 bg-white p-3 text-left transition hover:border-emerald-500 hover:bg-emerald-50 active:translate-y-px"
                      onClick={() => void loadRootTree(row.entidade_id)}
                    >
                      <span className="line-clamp-1 text-sm font-semibold text-zinc-950">{row.nome}</span>
                      <span className="h-stack flex-wrap items-center gap-2 text-xs text-zinc-500">
                        <span>{displayEntityType(row.tipo_entidade)}</span>
                        <span>{formatDocument(row.cpf_cnpj)}</span>
                      </span>
                    </button>
                  ))}
                </div>

                <div className="h-stack items-center justify-between gap-2 text-xs text-zinc-500">
                  <span>{searchRows.length} de {formatCount(searchTotal)}</span>
                  {canLoadMore ? (
                    <Button size="sm" onClick={() => void runSearch(query, searchOffset + 12)}>
                      Mais resultados
                    </Button>
                  ) : null}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="h-stack items-center justify-between gap-2">
                <CardTitle>Escopo</CardTitle>
                <SlidersHorizontal size={18} className="text-zinc-500" />
              </CardHeader>
              <CardContent className="v-stack gap-4">
                <label className="h-stack cursor-pointer items-center justify-between gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-3">
                  <span className="v-stack gap-0.5">
                    <span className="text-sm font-semibold text-zinc-800">Empresas e grupos</span>
                    <span className="text-xs text-zinc-500">{includeBusiness ? "Incluído" : "Oculto"}</span>
                  </span>
                  <Switch checked={includeBusiness} onChange={(event) => setIncludeBusiness(event.target.checked)} />
                </label>

                <label className="h-stack cursor-pointer items-center justify-between gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-3">
                  <span className="v-stack gap-0.5">
                    <span className="text-sm font-semibold text-zinc-800">Pendentes de revisão</span>
                    <span className="text-xs text-zinc-500">{includeWeak ? "Incluído" : "Oculto"}</span>
                  </span>
                  <Switch checked={includeWeak} onChange={(event) => setIncludeWeak(event.target.checked)} />
                </label>

                <div className="v-stack gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-3">
                  <div className="h-stack items-center justify-between">
                    <span className="text-sm font-semibold text-zinc-800">Relações por lote</span>
                    <span className="font-mono text-sm font-semibold text-zinc-950">{maxPerNode}</span>
                  </div>
                  <input
                    type="range"
                    min={4}
                    max={18}
                    value={maxPerNode}
                    onChange={(event) => setMaxPerNode(Number(event.target.value))}
                    className="w-full accent-emerald-700"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    onClick={() => {
                      if (tree.rootId) {
                        void loadRootTree(tree.rootId);
                      }
                    }}
                    disabled={!tree.rootId}
                  >
                    <ArrowsClockwise size={15} />
                    Recarregar
                  </Button>
                  <Button type="button" onClick={resetTree}>
                    <House size={15} />
                    Limpar
                  </Button>
                </div>
              </CardContent>
            </Card>
          </aside>

          <Card className="v-stack min-h-[70vh] min-w-0 overflow-hidden">
            <CardHeader className="h-stack flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>Árvore operacional</CardTitle>
                <div className="mt-1 h-stack flex-wrap items-center gap-2 text-xs text-zinc-500">
                  <Badge variant={includeBusiness ? "success" : "neutral"}>{includeBusiness ? "Escopo completo" : "Família"}</Badge>
                  <Badge variant={includeWeak ? "warning" : "neutral"}>{includeWeak ? "Com revisão" : "Confirmados"}</Badge>
                  {treeBusy ? <Badge variant="info">Carregando</Badge> : null}
                </div>
              </div>
              <div className="h-stack flex-wrap items-center gap-2">
                <div className="h-stack items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Afastar"
                    aria-label="Afastar"
                    disabled={!hasTree}
                    onClick={() => setZoom((current) => Math.max(0.55, Number((current - 0.1).toFixed(2))))}
                  >
                    <MagnifyingGlassMinus size={15} />
                  </Button>
                  <span className="min-w-12 text-center font-mono text-xs font-semibold text-zinc-600">{Math.round(zoom * 100)}%</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Aproximar"
                    aria-label="Aproximar"
                    disabled={!hasTree}
                    onClick={() => setZoom((current) => Math.min(1.6, Number((current + 0.1).toFixed(2))))}
                  >
                    <MagnifyingGlassPlus size={15} />
                  </Button>
                  <Button size="sm" variant="ghost" title="Centralizar" aria-label="Centralizar" disabled={!hasTree} onClick={recenterWorkflow}>
                    <Crosshair size={15} />
                  </Button>
                </div>
                <div className="h-stack items-center gap-2 text-xs text-zinc-500">
                  <span>{formatCount(tree.nodes.size)} nós</span>
                  <span>{formatCount(tree.relations.size)} vínculos</span>
                </div>
              </div>
            </CardHeader>

            <CardContent className="min-h-0 grow p-0">
              <div
                ref={canvasRef}
                className={cn(
                  "relative min-h-[70vh] overflow-hidden bg-[linear-gradient(#e4e4e7_1px,transparent_1px),linear-gradient(90deg,#e4e4e7_1px,transparent_1px)] bg-[size:28px_28px]",
                  isPanning ? "cursor-grabbing" : "cursor-grab",
                )}
                style={{ touchAction: "none" }}
                onPointerDown={onPanStart}
                onPointerMove={onPanMove}
                onPointerUp={onPanStop}
                onPointerCancel={onPanStop}
                onPointerLeave={onPanStop}
                onWheel={onWheelZoom}
              >
                {!hasTree ? (
                  <div className="center min-h-[70vh] p-4">
                    <div className="v-stack w-full max-w-md items-center gap-3 rounded-lg border border-dashed border-zinc-300 bg-white/90 p-8 text-center">
                      <TreeStructure size={34} className="text-zinc-400" />
                      <div>
                        <div className="font-semibold text-zinc-950">Nenhum cadastro selecionado</div>
                        <div className="mt-1 text-sm text-zinc-500">Aguardando seleção.</div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div
                    className="absolute left-0 top-0 transition-transform duration-150"
                    style={{
                      width: workflowLayout.width,
                      height: workflowLayout.height,
                      transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoom})`,
                      transformOrigin: "0 0",
                    }}
                  >
                    <svg
                      className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
                      width={workflowLayout.width}
                      height={workflowLayout.height}
                      viewBox={`0 0 ${workflowLayout.width} ${workflowLayout.height}`}
                    >
                      {workflowRelations.map((relation) => {
                        const source = workflowLayout.nodeMap.get(relation.source);
                        const target = workflowLayout.nodeMap.get(relation.target);
                        if (!source || !target) return null;
                        const labelX = (source.x + source.width / 2 + target.x + target.width / 2) / 2 - 78;
                        const labelY = (source.y + source.height / 2 + target.y + target.height / 2) / 2 - 13;

                        return (
                          <g key={`${relation.id}:${relation.source}:${relation.target}`}>
                            <path
                              d={workflowEdgePath(source, target)}
                              className={cn(
                                "fill-none stroke-[2.5] opacity-80",
                                relationStrokeClass(relation.tipo_vinculo),
                                relation.tipo_vinculo === "GRUPO_AGREGADO_POR_FAMILIA" ? "stroke-[3.5] opacity-95" : "",
                              )}
                            >
                              <title>{displayRelationType(relation.tipo_vinculo)}</title>
                            </path>
                            {relation.tipo_vinculo === "GRUPO_AGREGADO_POR_FAMILIA" ? (
                              <foreignObject x={labelX} y={labelY} width={156} height={26}>
                                <div className="center h-[26px] rounded-md border border-emerald-200 bg-emerald-50 px-2 text-[11px] font-semibold text-emerald-900 shadow-sm">
                                  Agregação familiar
                                </div>
                              </foreignObject>
                            ) : null}
                          </g>
                        );
                      })}
                    </svg>

                    {workflowLayout.nodes.map((node) => {
                      const isRoot = node.id === tree.rootId;
                      const isOfficialGroup = node.tipo_entidade === "GRUPO_ECONOMICO";
                      const canUp = canExpandDirection(node.id, "up", branchState);
                      const canDown = canExpandDirection(node.id, "down", branchState);

                      return (
                        <article
                          key={node.id}
                          className={cn(
                            "v-stack absolute min-w-0 gap-3 rounded-lg border bg-white p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md",
                            isRoot ? "border-emerald-600 ring-2 ring-emerald-100" : "border-zinc-200",
                            isOfficialGroup && !isRoot ? "border-sky-400 bg-sky-50/90" : "",
                          )}
                          style={{ left: node.x, top: node.y, width: node.width, minHeight: node.height }}
                        >
                          <button type="button" className="v-stack min-w-0 gap-1 text-left" onClick={() => void openNode(node.id)}>
                            <span className="line-clamp-2 text-sm font-semibold leading-5 text-zinc-950">{node.nome}</span>
                            <span className="h-stack flex-wrap items-center gap-2 text-xs text-zinc-500">
                              <span>{displayEntityType(node.tipo_entidade)}</span>
                              <span>{formatDocument(node.cpf_cnpj)}</span>
                            </span>
                          </button>

                          <div className="h-stack flex-wrap items-center gap-2">
                            <Badge variant={isRoot ? "success" : statusVariant(node.relacao_com_ancora)}>{relationBadgeForNode(node, tree.rootId)}</Badge>
                            {node.status_entidade ? <Badge variant={statusVariant(node.status_entidade)}>{node.status_entidade}</Badge> : null}
                          </div>

                          <div className="mt-auto h-stack flex-wrap gap-2">
                            {canUp ? (
                              <Button size="sm" variant="ghost" onClick={() => void loadNeighbors(node.id, "up")}>
                                <ArrowUp size={14} />
                                Acima
                              </Button>
                            ) : null}
                            {canDown ? (
                              <Button size="sm" variant="ghost" onClick={() => void loadNeighbors(node.id, "down")}>
                                <ArrowDown size={14} />
                                Abaixo
                              </Button>
                            ) : null}
                            <Button size="sm" variant="ghost" onClick={() => void loadEntityDetail(node.id)}>
                              <TreeStructure size={14} />
                              Detalhes
                            </Button>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <aside className="v-stack min-h-0 gap-4">
            <Card className="min-h-0">
              <CardHeader>
                <CardTitle>Resumo do cadastro</CardTitle>
              </CardHeader>
              <CardContent className="v-stack gap-4">
                {!detail ? (
                  <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-500">Nenhum cadastro selecionado.</div>
                ) : (
                  <>
                    <div className="v-stack gap-2">
                      <div className="text-base font-semibold leading-6 text-zinc-950">{detail.nome_canonico || detail.nome_original || "Sem nome cadastrado"}</div>
                      <div className="h-stack flex-wrap gap-2">
                        <Badge variant="info">{displayEntityType(detail.tipo_entidade)}</Badge>
                        <Badge variant={statusVariant(detail.status_entidade)}>{detail.status_entidade || "Sem status"}</Badge>
                        <Badge variant={statusVariant(displayDocumentStatus(detail.documento_valido))}>{displayDocumentStatus(detail.documento_valido)}</Badge>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
                        <div className="text-xs text-zinc-500">Documento</div>
                        <div className="mt-1 truncate font-mono text-sm font-semibold text-zinc-950">{formatDocument(detail.cpf_cnpj)}</div>
                      </div>
                      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
                        <div className="text-xs text-zinc-500">Conexões</div>
                        <div className="mt-1 font-mono text-sm font-semibold text-zinc-950">{formatCount(detail.total_vizinhos)}</div>
                      </div>
                      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
                        <div className="text-xs text-zinc-500">Grupos</div>
                        <div className="mt-1 font-mono text-sm font-semibold text-zinc-950">{formatCount(detail.total_grupos)}</div>
                      </div>
                      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
                        <div className="text-xs text-zinc-500">Atualização</div>
                        <div className="mt-1 truncate font-mono text-xs font-semibold text-zinc-950">{detail.data_atualizacao || "-"}</div>
                      </div>
                    </div>

                    {detail.alertas ? (
                      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                        <div className="font-semibold">Observação</div>
                        <div className="mt-1 text-xs">{detail.alertas}</div>
                      </div>
                    ) : null}
                  </>
                )}
              </CardContent>
            </Card>

            <Card className="min-h-0">
              <CardHeader className="h-stack items-center justify-between">
                <CardTitle>Grupos associados</CardTitle>
                {detail ? <Badge variant="neutral">{formatCount(detail.total_grupos)}</Badge> : null}
              </CardHeader>
              <CardContent className="v-stack max-h-[28vh] gap-2 overflow-y-auto">
                {visibleGroups.length === 0 ? (
                  <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-500">Sem grupos para o cadastro atual.</div>
                ) : null}
                {visibleGroups.map((grupo) => (
                  <div key={`${grupo.grupo_id}:${grupo.papel_no_grupo}`} className="v-stack gap-2 rounded-md border border-zinc-200 bg-white p-3">
                    <div className="font-semibold leading-5 text-zinc-950">{grupo.nome_grupo || "Grupo sem nome"}</div>
                    <div className="h-stack flex-wrap gap-2">
                      <Badge variant={grupo.grupo_id.startsWith("GE:") ? "info" : "neutral"}>{displayGroupRole(grupo.papel_no_grupo)}</Badge>
                      <Badge variant={statusVariant(grupo.status_grupo)}>{grupo.status_grupo || "Sem status"}</Badge>
                    </div>
                    {grupo.justificativa_textual ? <div className="text-xs leading-5 text-zinc-500">{grupo.justificativa_textual}</div> : null}
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="min-h-0">
              <CardHeader className="h-stack items-center justify-between">
                <CardTitle>Empresas</CardTitle>
                {detail ? <Badge variant="neutral">{formatCount(detail.empresas.length)}</Badge> : null}
              </CardHeader>
              <CardContent className="v-stack max-h-[26vh] gap-2 overflow-y-auto">
                {visibleCompanies.length === 0 ? (
                  <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-500">Sem empresas para o cadastro atual.</div>
                ) : null}
                {visibleCompanies.map((empresa) => (
                  <button
                    key={`${empresa.entidade_id}:${empresa.tipo_relacao}:${empresa.grupo_nome}`}
                    type="button"
                    className="v-stack gap-2 rounded-md border border-zinc-200 bg-white p-3 text-left transition hover:border-emerald-500 hover:bg-emerald-50 active:translate-y-px"
                    onClick={() => void loadRootTree(empresa.entidade_id)}
                  >
                    <div className="h-stack min-w-0 items-start gap-2">
                      <div className="center mt-0.5 h-7 w-7 shrink-0 rounded-md border border-zinc-200 bg-zinc-50 text-zinc-600">
                        <Buildings size={15} />
                      </div>
                      <div className="min-w-0">
                        <div className="line-clamp-2 text-sm font-semibold leading-5 text-zinc-950">{empresa.nome || "Empresa sem nome"}</div>
                        <div className="mt-0.5 truncate font-mono text-xs text-zinc-500">{formatDocument(empresa.cpf_cnpj)}</div>
                      </div>
                    </div>
                    <div className="h-stack flex-wrap gap-2">
                      <Badge variant="info">{displayRelationType(empresa.tipo_relacao)}</Badge>
                      {empresa.grupo_nome ? <Badge variant="neutral">{empresa.grupo_nome}</Badge> : null}
                    </div>
                  </button>
                ))}
              </CardContent>
            </Card>

            <Card className="min-h-0">
              <CardHeader className="h-stack items-center justify-between">
                <CardTitle>Vínculos entre grupos</CardTitle>
                {detail ? <Badge variant="neutral">{formatCount(detail.vinculos_grupos.length)}</Badge> : null}
              </CardHeader>
              <CardContent className="v-stack max-h-[28vh] gap-2 overflow-y-auto">
                {visibleGroupLinks.length === 0 ? (
                  <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-500">Sem vínculo de grupo para o cadastro atual.</div>
                ) : null}
                {visibleGroupLinks.map((vinculo) => (
                  <div
                    key={`${vinculo.grupo_origem}:${vinculo.grupo_destino}:${vinculo.entidade_ponte}:${vinculo.tipo_relacao}`}
                    className="v-stack gap-2 rounded-md border border-zinc-200 bg-white p-3"
                  >
                    <div className="h-stack items-center gap-2">
                      <Badge variant="info">{displayGroupRelationType(vinculo.tipo_relacao)}</Badge>
                      <span className="font-mono text-xs text-zinc-500">{formatCount(vinculo.relevancia)}</span>
                    </div>
                    <div className="text-sm font-semibold leading-5 text-zinc-950">
                      {vinculo.grupo_origem_nome} ↔ {vinculo.grupo_destino_nome}
                    </div>
                    {vinculo.entidade_ponte_nome ? <div className="text-xs text-zinc-500">Vínculo por {vinculo.entidade_ponte_nome}</div> : null}
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="min-h-0">
              <CardHeader>
                <CardTitle>Relações conhecidas</CardTitle>
              </CardHeader>
              <CardContent className="max-h-[24vh] overflow-y-auto p-0">
                {!detail || Object.keys(detail.conexoes_por_tipo).length === 0 ? (
                  <div className="p-4 text-sm text-zinc-500">Sem relações carregadas.</div>
                ) : (
                  <table className="w-full text-left text-sm">
                    <tbody className="divide-y divide-zinc-200">
                      {Object.entries(detail.conexoes_por_tipo).map(([tipo, total]) => (
                        <tr key={tipo}>
                          <td className="px-4 py-2 text-zinc-700">{displayRelationType(tipo)}</td>
                          <td className="px-4 py-2 text-right font-mono font-semibold text-zinc-950">{formatCount(total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </aside>
        </section>
      </div>
    </main>
  );
}

export default App;
