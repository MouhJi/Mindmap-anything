import type { ChatMessage, ChatRequest } from "../types.ts";

export function askMockGraph({
  question,
  graph,
  selectedNodeId,
}: ChatRequest): Omit<ChatMessage, "id" | "role"> {
  const query = question.toLocaleLowerCase("vi");
  const named = graph.nodes.filter((n) =>
    query.includes(n.label.toLocaleLowerCase("vi")),
  );
  const aliases: Record<string, string[]> = {
    retrieval: ["rag", "truy xuất", "tìm kiếm", "tài liệu"],
    "prompt-templates": ["prompt", "lời nhắc", "khuôn mẫu"],
    "chat-models": ["model", "mô hình"],
    agents: ["agent", "tác tử"],
    memory: ["bộ nhớ", "ngữ cảnh", "ghi nhớ"],
    embeddings: ["vector", "embedding"],
    tools: ["công cụ", "tool"],
    langchain: ["tổng quan", "bắt đầu", "đồ thị"],
  };
  const matched = named.length
    ? named
    : graph.nodes.filter((n) =>
        aliases[n.id]?.some((term) => query.includes(term)),
      );
  const contextual =
    /node này|khái niệm này|nó là gì|ví dụ|giải thích thêm|dùng thế nào/.test(
      query,
    );
  const node =
    matched[0] ??
    (contextual ? graph.nodes.find((n) => n.id === selectedNodeId) : undefined);
  if (!node)
    return {
      content:
        "Bộ dữ liệu mẫu chưa có thông tin phù hợp cho câu hỏi này. Tôi chỉ có thể minh họa các khái niệm LangChain đang có trong đồ thị. Bạn có thể chọn một node và hỏi về cách dùng hoặc ví dụ của node đó. Demo không gọi LLM và không tìm kiếm trên Internet.",
      nodeIds: ["langchain", "retrieval"].filter((id) =>
        graph.nodes.some((n) => n.id === id),
      ),
      isMock: true,
    };
  const related = graph.nodes
    .filter((n) => node.relatedNodeIds.includes(n.id))
    .slice(0, 3);
  const compare =
    matched.length > 1 ? `\n\n${matched[1].label}: ${matched[1].summary}` : "";
  return {
    content: `${node.label}: ${node.summary}\n\n${node.purpose}\n\n${node.explanation}${compare}\n\nBạn có thể mở các node liên quan bên dưới để tiếp tục khám phá. Nội dung này được soạn sẵn cho demo, chưa được lấy từ URL bạn nhập.`,
    nodeIds: [node.id, ...related.map((n) => n.id)],
    isMock: true,
  };
}
