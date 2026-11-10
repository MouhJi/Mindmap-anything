export type NodeType = "Framework" | "Module" | "Concept";
export type WorkspaceTab = "graph" | "sources" | "notes";

export interface KnowledgeNode {
  id: string;
  label: string;
  type: NodeType;
  summary: string;
  purpose: string;
  explanation: string;
  sourceIds: string[];
  relatedNodeIds: string[];
  example?: string;
  position: { x: number; y: number };
}

export interface KnowledgeEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
}

export interface Source {
  id: string;
  title: string;
  url: string;
  excerpt: string;
  isMock: boolean;
}

export interface Graph {
  schemaVersion: "1.0";
  isMock: boolean;
  requestedUrl: string | null;
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  sources: Source[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  nodeIds: string[];
  isMock: boolean;
}

export interface ChatRequest {
  question: string;
  selectedNodeId: string | null;
  graph: Graph;
}

export interface GraphService {
  getGraph(): Graph;
  createGraphFromUrl(url: string): Promise<Graph>;
  expandNode(graph: Graph, nodeId: string): Promise<Graph>;
  askGraph(request: ChatRequest): Promise<Omit<ChatMessage, "id" | "role">>;
}

export const nodeTypeLabels: Record<NodeType, string> = {
  Framework: "Framework",
  Module: "Module",
  Concept: "Khái niệm",
};
