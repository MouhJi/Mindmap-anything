import { allEdges, allNodes, makeInitialGraph } from "../data/langchain.ts";
import type {
  Graph,
  GraphService,
  KnowledgeEdge,
  KnowledgeNode,
} from "../types.ts";
import { askMockGraph } from "./chat.ts";

export function validateUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname)
      return "Chỉ chấp nhận URL bắt đầu bằng http:// hoặc https://.";
    if (url.username || url.password)
      return "Vui lòng dùng URL không chứa thông tin đăng nhập.";
    return null;
  } catch {
    return "Nhập URL hợp lệ, ví dụ https://docs.langchain.com.";
  }
}

// Shared by demo expansion and the future API integration. Drops dangling edges.
export function mergeGraph(
  graph: Graph,
  nodes: KnowledgeNode[],
  edges: KnowledgeEdge[],
): Graph {
  const mergedNodes = [
    ...new Map([...graph.nodes, ...nodes].map((n) => [n.id, n])).values(),
  ];
  const ids = new Set(mergedNodes.map((n) => n.id));
  const mergedEdges = [
    ...new Map([...graph.edges, ...edges].map((e) => [e.id, e])).values(),
  ].filter((e) => ids.has(e.source) && ids.has(e.target));
  return { ...graph, nodes: mergedNodes, edges: mergedEdges };
}

export function expandMockGraph(graph: Graph, nodeId: string): Graph {
  if (!graph.nodes.some((n) => n.id === nodeId))
    throw new Error("Node không có trong đồ thị hiện tại.");
  const existing = new Set(graph.nodes.map((n) => n.id));
  const related = allEdges.filter(
    (e) => e.source === nodeId || e.target === nodeId,
  );
  const ids = related
    .map((e) => (e.source === nodeId ? e.target : e.source))
    .filter((id) => !existing.has(id))
    .slice(0, 3);
  const nodes = allNodes.filter((n) => ids.includes(n.id));
  const visible = new Set([...existing, ...ids]);
  return mergeGraph(
    graph,
    structuredClone(nodes),
    allEdges.filter(
      (e) =>
        visible.has(e.source) &&
        visible.has(e.target) &&
        (e.source === nodeId ||
          e.target === nodeId ||
          ids.includes(e.source) ||
          ids.includes(e.target)),
    ),
  );
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const graphService: GraphService = {
  getGraph: () => makeInitialGraph(),
  async createGraphFromUrl(url) {
    const error = validateUrl(url);
    if (error) throw new Error(error);
    await delay(850);
    return makeInitialGraph(new URL(url.trim()).href);
  },
  async expandNode(graph, nodeId) {
    await delay(550);
    return expandMockGraph(graph, nodeId);
  },
  async askGraph(request) {
    await delay(750);
    return askMockGraph(request);
  },
};

export function exportGraph(graph: Graph): string {
  const { schemaVersion, isMock, requestedUrl, nodes, edges, sources } = graph;
  return JSON.stringify(
    { schemaVersion, isMock, requestedUrl, nodes, edges, sources },
    null,
    2,
  );
}
