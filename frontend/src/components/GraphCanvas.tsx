import { memo, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import {
  Bot,
  Braces,
  ChevronDown,
  CircleHelp,
  Code2,
  Database,
  Focus,
  GitBranch,
  Layers3,
  Maximize2,
  MessageSquare,
  Minimize2,
  Minus,
  Network,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import type { Graph, KnowledgeNode, NodeType } from "../types";
import { nodeTypeLabels } from "../types";

interface Props {
  graph: Graph;
  selectedId: string | null;
  onSelect: (id: string) => void;
  focused: boolean;
  onToggleFocus: () => void;
  revision: number;
  focusRequest: { id: string; key: number; fitIds?: string[] } | null;
}
type VisualNode = Node<
  {
    node: KnowledgeNode;
    related: boolean;
    dimmed: boolean;
    onSelect: (id: string) => void;
  },
  "knowledge"
>;
const icons: Record<string, typeof Network> = {
  langchain: Network,
  "chat-models": Bot,
  "prompt-templates": Code2,
  retrieval: Database,
  agents: GitBranch,
  memory: Layers3,
  messages: MessageSquare,
  tools: Braces,
  "output-parsers": Braces,
  embeddings: Sparkles,
};

const KnowledgeBubble = memo(function KnowledgeBubble({
  data,
  selected,
}: NodeProps<VisualNode>) {
  const Icon =
    icons[data.node.id] ?? (data.node.type === "Module" ? Layers3 : Code2);
  return (
    <div
      className={`knowledge-bubble ${data.node.type.toLowerCase()} ${selected ? "is-selected" : ""} ${data.related ? "is-related" : ""} ${data.dimmed ? "dimmed" : ""}`}
    >
      <Handle type="target" position={Position.Top} className="hidden-handle" />
      <button
        id={`graph-node-${data.node.id}`}
        className="node-button"
        onClick={() => data.onSelect(data.node.id)}
        aria-label={`Chọn node ${data.node.label}`}
        aria-pressed={selected}
      >
        <span className="node-orb">
          <Icon
            size={data.node.type === "Framework" ? 27 : 22}
            strokeWidth={1.6}
          />
        </span>
        <span className="node-label">{data.node.label}</span>
        {data.node.type === "Framework" && (
          <span className="node-subtitle">FRAMEWORK</span>
        )}
      </button>
      <Handle
        type="source"
        position={Position.Bottom}
        className="hidden-handle"
      />
    </div>
  );
});
const nodeTypes = { knowledge: KnowledgeBubble };
const viewPadding = {
  top: "52px",
  bottom: "40px",
  left: "22px",
  right: "22px",
} as const;

export default function GraphCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}

function Canvas({
  graph,
  selectedId,
  onSelect,
  focused,
  onToggleFocus,
  revision,
  focusRequest,
}: Props) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<NodeType | "all">("all");
  const [zoom, setZoom] = useState(1);
  const [searchOpen, setSearchOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const flow = useReactFlow<VisualNode>();
  const container = useRef<HTMLDivElement>(null);
  const initialView = useRef(true);
  const reducedMotion = () =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 280;
  const relatedIds = useMemo(
    () =>
      new Set(
        graph.edges
          .filter((e) => e.source === selectedId || e.target === selectedId)
          .flatMap((e) => [e.source, e.target]),
      ),
    [graph.edges, selectedId],
  );
  const visible = graph.nodes.filter(
    (n) => filter === "all" || n.type === filter,
  );
  const ids = new Set(visible.map((n) => n.id));
  const nodes: VisualNode[] = visible.map((node) => ({
    id: node.id,
    type: "knowledge",
    position: node.position,
    selected: node.id === selectedId,
    draggable: false,
    focusable: false,
    data: {
      node,
      onSelect,
      related: relatedIds.has(node.id),
      dimmed:
        !!selectedId && !relatedIds.has(node.id) && node.id !== selectedId,
    },
  }));
  const edges = graph.edges
    .filter((e) => ids.has(e.source) && ids.has(e.target))
    .map((edge) => {
      const active = edge.source === selectedId || edge.target === selectedId;
      return {
        ...edge,
        type: "straight",
        label: active ? edge.relation : undefined,
        style: {
          stroke: active ? "#4a8b70" : "#c0cfbf",
          strokeWidth: active ? 1.8 : 1.3,
          opacity: selectedId && !active ? 0.35 : 1,
          strokeDasharray: active ? undefined : "4 5",
        },
        labelStyle: { fill: "#496756", fontSize: 12 },
        labelBgStyle: { fill: "#fafcf8", fillOpacity: 0.96 },
        labelBgPadding: [5, 3] as [number, number],
      };
    });
  const matches = search.trim()
    ? graph.nodes.filter((n) =>
        n.label.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
      )
    : [];
  const fit = () => {
    void flow.fitView({
      padding: viewPadding,
      duration: reducedMotion(),
      minZoom: 0.2,
      maxZoom: 1.1,
    });
  };

  useEffect(() => {
    setSearch("");
    setFilter("all");
    setSearchOpen(false);
    initialView.current = true;
  }, [revision]);

  // ResizeObserver handles returning from tabs, focus mode, and responsive changes.
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver((entries) => {
      if (
        entries[0].contentRect.width &&
        entries[0].contentRect.height &&
        initialView.current
      ) {
        requestAnimationFrame(() => {
          void flow.fitView({ padding: viewPadding, maxZoom: 1.1 });
          initialView.current = false;
        });
      }
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, [flow, revision]);

  useEffect(() => {
    if (!focusRequest) return;
    setFilter("all");
    setSearch("");
    setSearchOpen(false);
    const frame = requestAnimationFrame(() => {
      const targets = focusRequest.fitIds ?? [focusRequest.id];
      void flow.fitView({
        nodes: targets.map((id) => ({ id })),
        padding: focusRequest.fitIds ? 0.4 : 1.2,
        maxZoom: 1.05,
        duration: reducedMotion(),
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusRequest, flow]);

  const chooseSearch = (id: string) => {
    onSelect(id);
    setFilter("all");
    setSearchOpen(false);
    requestAnimationFrame(() => {
      void flow.fitView({
        nodes: [{ id }],
        padding: 1.2,
        maxZoom: 1.05,
        duration: reducedMotion(),
      });
    });
  };

  return (
    <section
      className={`graph-canvas ${focused ? "focus-canvas" : ""}`}
      aria-label="Đồ thị tri thức tương tác"
      ref={container}
      style={
        {
          "--node-scale": Math.max(1, Math.min(1.4, 0.67 / zoom)),
        } as CSSProperties
      }
    >
      <div className="graph-toolbar">
        <div className="graph-search">
          <Search size={16} />
          <input
            aria-label="Tìm node theo tên"
            placeholder="Tìm khái niệm…"
            value={search}
            onFocus={() => setSearchOpen(true)}
            onChange={(e) => {
              setSearch(e.target.value);
              setSearchOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && matches[0]) {
                e.preventDefault();
                chooseSearch(matches[0].id);
              }
              if (e.key === "Escape") setSearchOpen(false);
            }}
          />
          {search && (
            <button
              className="icon-button"
              aria-label="Xóa tìm kiếm"
              onClick={() => {
                setSearch("");
                setSearchOpen(false);
              }}
            >
              <X size={14} />
            </button>
          )}
          {searchOpen && search.trim() && (
            <div className="search-results" aria-label="Kết quả tìm kiếm">
              {matches.length ? (
                matches.map((n) => (
                  <button key={n.id} onClick={() => chooseSearch(n.id)}>
                    <span className={`type-dot ${n.type.toLowerCase()}`} />
                    {n.label}
                    <small>{nodeTypeLabels[n.type]}</small>
                  </button>
                ))
              ) : (
                <p role="status">Không tìm thấy “{search}”.</p>
              )}
            </div>
          )}
        </div>
        <div className="toolbar-right">
          <label className="filter-select">
            <SlidersHorizontal size={15} />
            <select
              aria-label="Lọc theo loại node"
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value as NodeType | "all");
                requestAnimationFrame(fit);
              }}
            >
              <option value="all">Tất cả loại</option>
              <option value="Framework">Framework</option>
              <option value="Module">Module</option>
              <option value="Concept">Khái niệm</option>
            </select>
            <ChevronDown size={12} />
          </label>
          {filter !== "all" && (
            <button
              className="icon-button"
              title="Xóa bộ lọc"
              aria-label="Xóa bộ lọc"
              onClick={() => {
                setFilter("all");
                requestAnimationFrame(fit);
              }}
            >
              <X size={16} />
            </button>
          )}
          <button
            className={`icon-button focus-button ${focused ? "selected" : ""}`}
            aria-label={
              focused ? "Thoát chế độ tập trung" : "Mở rộng vùng đồ thị"
            }
            title={
              focused ? "Thoát chế độ tập trung (Escape)" : "Chế độ tập trung"
            }
            onClick={onToggleFocus}
          >
            {focused ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            {focused && <span>Thoát</span>}
          </button>
        </div>
      </div>
      <ReactFlow<VisualNode>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        minZoom={0.2}
        maxZoom={1.8}
        fitView
        fitViewOptions={{ padding: viewPadding, maxZoom: 1.1 }}
        onNodeClick={(_, node) => onSelect(node.id)}
        nodesConnectable={false}
        nodesDraggable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        deleteKeyCode={null}
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        zoomOnDoubleClick={false}
        onMove={(_, viewport) => setZoom(viewport.zoom)}
        proOptions={{ hideAttribution: false }}
        aria-label="Đồ thị LangChain; dùng Tab để đến node, Enter để chọn; kéo nền để di chuyển"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#d5dfd1"
        />
      </ReactFlow>
      <div className="graph-legend">
        <span>
          <i className="type-dot framework" />
          Framework
        </span>
        <span>
          <i className="type-dot module" />
          Module
        </span>
        <span>
          <i className="type-dot concept" />
          Khái niệm
        </span>
      </div>
      <div className="canvas-controls">
        <button
          className="icon-button"
          aria-label="Thu nhỏ đồ thị"
          onClick={() => {
            void flow.zoomOut({ duration: reducedMotion() });
          }}
          disabled={zoom <= 0.2}
        >
          <Minus size={17} />
        </button>
        <span aria-label="Mức zoom" className="zoom-level">
          {Math.round(zoom * 100)}%
        </span>
        <button
          className="icon-button"
          aria-label="Phóng to đồ thị"
          onClick={() => {
            void flow.zoomIn({ duration: reducedMotion() });
          }}
          disabled={zoom >= 1.8}
        >
          <Plus size={17} />
        </button>
        <span className="control-divider" />
        <button
          className="icon-button"
          aria-label="Vừa khung đồ thị"
          title="Vừa khung đồ thị"
          onClick={fit}
        >
          <Focus size={18} />
        </button>
      </div>
      <div className="canvas-hint">
        <span>
          {visible.length} node · {edges.length} liên kết
        </span>
        <button
          className="icon-button"
          aria-label="Hướng dẫn sử dụng đồ thị"
          aria-expanded={help}
          onClick={() => setHelp(!help)}
        >
          <CircleHelp size={15} />
        </button>
      </div>
      {help && (
        <div className="graph-help" role="status">
          <strong>Khám phá theo cách của bạn</strong>
          <p>
            Kéo nền để di chuyển. Cuộn hoặc chụm hai ngón để zoom. Dùng Tab đến
            node và Enter để chọn. Chọn “Vừa khung” để xem toàn bộ.
          </p>
          <button onClick={() => setHelp(false)}>Đã hiểu</button>
        </div>
      )}
    </section>
  );
}
