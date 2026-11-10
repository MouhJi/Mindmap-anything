import type { Graph, KnowledgeNode, NodeType, Source } from "../types.ts";
import { mergeGraph } from "./graph.ts";

// Contract from knowledge/models.py and knowledge/api.py. This adapter is opt-in;
// the demo never fetches the Python API or fills missing evidence with mock data.
export interface ApiNode {
  id: string;
  label: string;
  type: string;
}
export interface ApiExpansion {
  center_node: ApiNode;
  nodes: ApiNode[];
  edges: {
    id: string;
    source: string;
    target: string;
    relation_type: string;
  }[];
  pagination: {
    returned: number;
    has_more: boolean;
    next_cursor: string | null;
  };
}

function mapType(type: string): NodeType {
  if (type === "Framework") return "Framework";
  return ["Library", "API", "Service", "Tool"].includes(type)
    ? "Module"
    : "Concept";
}

export function mapExpansion(response: ApiExpansion, graph: Graph): Graph {
  if (graph.isMock)
    throw new Error(
      "Không trộn dữ liệu API vào đồ thị mẫu. Khởi tạo đồ thị thật riêng trước khi dùng adapter.",
    );
  const nodes: KnowledgeNode[] = [response.center_node, ...response.nodes].map(
    (n, index) => {
      const existing = graph.nodes.find((item) => item.id === n.id);
      return (
        existing ?? {
          id: n.id,
          label: n.label,
          type: mapType(n.type),
          summary: "API đọc hiện tại chưa cung cấp mô tả node.",
          purpose: "Chưa có dữ liệu từ backend.",
          explanation:
            "Nạp mô tả và bằng chứng từ backend trước khi hiển thị nội dung giải thích.",
          relatedNodeIds: response.edges
            .filter((e) => e.source === n.id || e.target === n.id)
            .map((e) => (e.source === n.id ? e.target : e.source)),
          sourceIds: [],
          position: { x: (index % 4) * 240, y: Math.floor(index / 4) * 170 },
        }
      );
    },
  );
  return mergeGraph(
    graph,
    nodes,
    response.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      relation: e.relation_type,
    })),
  );
}

export function createReadApiAdapter(baseUrl = "") {
  return {
    async expandNode(
      projectId: string,
      nodeId: string,
      cursor?: string,
    ): Promise<ApiExpansion> {
      const params = new URLSearchParams({ project_id: projectId, limit: "3" });
      if (cursor) params.set("cursor", cursor);
      const response = await fetch(
        `${baseUrl}/api/graph/nodes/${encodeURIComponent(nodeId)}/expand?${params}`,
      );
      if (!response.ok)
        throw new Error(`Graph API trả về HTTP ${response.status}`);
      return response.json() as Promise<ApiExpansion>;
    },
    async getEvidence(
      projectId: string,
      edgeId: string,
    ): Promise<{
      evidence: {
        evidence_id: string;
        document_id: string;
        url: string;
        text: string;
      }[];
    }> {
      const response = await fetch(
        `${baseUrl}/api/graph/edges/${encodeURIComponent(edgeId)}/evidence?${new URLSearchParams({ project_id: projectId })}`,
      );
      if (!response.ok)
        throw new Error(`Evidence API trả về HTTP ${response.status}`);
      return response.json();
    },
  };
}

export function mapEvidence(item: {
  evidence_id: string;
  document_id: string;
  url: string;
  text: string;
}): Source {
  const url = new URL(item.url);
  if (!["http:", "https:"].includes(url.protocol))
    throw new Error("URL bằng chứng không hợp lệ");
  return {
    id: item.evidence_id,
    title: item.document_id,
    url: url.href,
    excerpt: item.text,
    isMock: false,
  };
}
