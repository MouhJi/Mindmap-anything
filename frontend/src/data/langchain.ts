import type { Graph, KnowledgeEdge, KnowledgeNode, Source } from "../types.ts";

// Authored teaching material. URLs are reading references, never crawl evidence.
const base = "https://docs.langchain.com/oss/python/langchain";
export const sources: Source[] = [
  {
    id: "overview",
    title: "LangChain · Tổng quan",
    url: `${base}/overview`,
    excerpt:
      "Minh họa: LangChain kết nối mô hình, prompt và công cụ để xây dựng ứng dụng ngôn ngữ. Bản demo tổ chức các thành phần này thành một bản đồ khái niệm.",
    isMock: true,
  },
  {
    id: "models",
    title: "Models & messages",
    url: `${base}/models`,
    excerpt:
      "Minh họa: Chat model nhận các message và tạo phản hồi. Một số mô hình hỗ trợ gọi công cụ và đầu ra có cấu trúc.",
    isMock: true,
  },
  {
    id: "prompts",
    title: "Prompt templates · API reference",
    url: "https://reference.langchain.com/python/langchain-core/prompts/",
    excerpt:
      "Minh họa: Prompt template dùng biến đầu vào để tạo lời nhắc nhất quán. Có thể ghép template với model và parser trong một luồng xử lý.",
    isMock: true,
  },
  {
    id: "retrieval",
    title: "Retrieval · Tìm ngữ cảnh liên quan",
    url: "https://docs.langchain.com/oss/python/deepagents/retrieval",
    excerpt:
      "Minh họa: Retrieval tìm thông tin liên quan cho câu hỏi. Trong ví dụ RAG, tài liệu có thể được chia nhỏ, chuyển thành vector và tìm kiếm trong vector store.",
    isMock: true,
  },
  {
    id: "agents",
    title: "Agents · Models, tools & state",
    url: `${base}/agents`,
    excerpt:
      "Minh họa: Agent phối hợp model và tool theo từng bước. Trạng thái lưu thông tin cần thiết để tiếp tục cuộc hội thoại hoặc tác vụ.",
    isMock: true,
  },
];

type NodeInput = Omit<KnowledgeNode, "relatedNodeIds">;
const entries: NodeInput[] = [
  {
    id: "langchain",
    label: "LangChain",
    type: "Framework",
    position: { x: 480, y: 120 },
    summary:
      "Bộ công cụ kết nối các thành phần để xây dựng ứng dụng với mô hình ngôn ngữ.",
    purpose:
      "Tổ chức model, prompt, dữ liệu và công cụ thành một luồng làm việc.",
    explanation:
      "Hãy hình dung LangChain như bộ ghép nối. Bạn chọn model để xử lý ngôn ngữ, chuẩn bị prompt, rồi bổ sung retrieval hoặc tools khi tác vụ cần thêm thông tin. Bản đồ này là ví dụ khái niệm, không phải sơ đồ mọi API của một phiên bản.",
    sourceIds: ["overview"],
    example:
      '# Ví dụ minh họa, không thực thi trong demo\nfrom langchain_core.prompts import ChatPromptTemplate\n\nprompt = ChatPromptTemplate.from_template(\n    "Giải thích {topic} bằng tiếng Việt."\n)\nmessages = prompt.invoke({"topic": "RAG"})',
  },
  {
    id: "chat-models",
    label: "Chat models",
    type: "Module",
    position: { x: 240, y: 0 },
    summary: "Giao diện làm việc với mô hình hội thoại thông qua các message.",
    purpose: "Nhận hướng dẫn và câu hỏi, tạo phản hồi cho ứng dụng.",
    explanation:
      "Chuẩn bị các message, cấu hình model từ nhà cung cấp và gọi model. Các khả năng như tool calling hay structured output phụ thuộc model. Bản demo không khởi tạo model hoặc gửi yêu cầu đến nhà cung cấp.",
    sourceIds: ["models"],
    example:
      '# Minh họa; cần model thật khi tích hợp backend\nmessages = [\n    ("system", "Bạn là trợ lý học tập."),\n    ("human", "Retrieval là gì?"),\n]\n# response = model.invoke(messages)',
  },
  {
    id: "prompt-templates",
    label: "Prompt templates",
    type: "Module",
    position: { x: 240, y: 150 },
    summary: "Khuôn mẫu lời nhắc có thể tái sử dụng với các biến đầu vào.",
    purpose: "Giữ hướng dẫn nhất quán khi câu hỏi hoặc dữ liệu thay đổi.",
    explanation:
      "Định nghĩa phần hướng dẫn cố định, đánh dấu biến như {topic}, rồi truyền giá trị khi sử dụng. Template tạo message cho chat model. Bạn có thể bổ sung few-shot examples để minh họa định dạng mong muốn.",
    sourceIds: ["prompts"],
    example:
      '# Nội dung minh họa\nfrom langchain_core.prompts import ChatPromptTemplate\n\nprompt = ChatPromptTemplate.from_template(\n    "Giải thích {topic} cho {audience}."\n)\nmessages = prompt.invoke({\n    "topic": "embeddings",\n    "audience": "người mới",\n})',
  },
  {
    id: "output-parsers",
    label: "Output parsers",
    type: "Module",
    position: { x: 480, y: 290 },
    summary: "Chuyển đầu ra của model thành dạng thuận tiện cho ứng dụng.",
    purpose: "Đọc và xử lý kết quả dưới dạng chuỗi hoặc cấu trúc mong muốn.",
    explanation:
      "Parser nhận đầu ra rồi chuyển đổi theo quy tắc. Khi cần schema chặt chẽ, cân nhắc structured output và kiểm tra dữ liệu. Parser không tự bảo đảm nội dung model là đúng.",
    sourceIds: ["prompts", "models"],
    example:
      '# Nội dung minh họa\nfrom langchain_core.output_parsers import StrOutputParser\n\nparser = StrOutputParser()\ntext = parser.invoke("Một phản hồi mẫu")',
  },
  {
    id: "retrieval",
    label: "Retrieval",
    type: "Module",
    position: { x: 720, y: 150 },
    summary: "Tìm và đưa những đoạn thông tin liên quan vào ngữ cảnh trả lời.",
    purpose:
      "Giúp ứng dụng sử dụng tài liệu bên ngoài thay vì chỉ dựa vào kiến thức của model.",
    explanation:
      "Một luồng RAG minh họa: nạp tài liệu, chia đoạn, tạo embedding, lưu vào vector store và tìm đoạn liên quan đến câu hỏi. Kết quả retrieval được đưa vào prompt. Mở rộng node này để xem ba thành phần chuẩn bị dữ liệu.",
    sourceIds: ["retrieval"],
    example:
      '# Mã giả minh họa, không gọi dịch vụ thật\nquestion = "Prompt template dùng để làm gì?"\n# documents = retriever.invoke(question)\n# context = "\\n".join(d.page_content for d in documents)\n# answer = chain.invoke({"context": context, "question": question})',
  },
  {
    id: "agents",
    label: "Agents",
    type: "Module",
    position: { x: 720, y: 0 },
    summary: "Phối hợp model và công cụ qua nhiều bước để thực hiện tác vụ.",
    purpose:
      "Chọn công cụ phù hợp khi câu hỏi đòi hỏi thao tác hoặc thông tin bổ sung.",
    explanation:
      "Agent nhận yêu cầu, dùng model để quyết định gọi tool, đọc kết quả rồi tiếp tục cho đến khi hoàn thành. Trạng thái giúp lưu tiến trình. Demo chỉ mô tả luồng này, không chạy một agent.",
    sourceIds: ["agents"],
    example:
      '# Mã giả minh họa\n# agent = create_agent(model=model, tools=[lookup_docs])\n# result = agent.invoke({\n#     "messages": [{"role": "user", "content": "Tìm hiểu RAG"}]\n# })',
  },
  {
    id: "memory",
    label: "Memory",
    type: "Module",
    position: { x: 480, y: -40 },
    summary: "Giữ lại ngữ cảnh cần thiết giữa các lượt hoặc các bước xử lý.",
    purpose: "Giúp ứng dụng tiếp tục hội thoại với thông tin đã có.",
    explanation:
      "Ngữ cảnh ngắn hạn có thể là lịch sử message trong trạng thái. Bộ nhớ dài hạn cần cơ chế lưu và truy xuất riêng. Đây là mô hình khái niệm; không ngụ ý một lớp Memory cụ thể của LangChain.",
    sourceIds: ["agents"],
    example:
      '# Mã giả minh họa trạng thái hội thoại\nstate = {"messages": []}\nstate["messages"].append({\n    "role": "user", "content": "Tôi đang học RAG"\n})',
  },
  {
    id: "messages",
    label: "Messages",
    type: "Concept",
    position: { x: 0, y: 0 },
    summary: "Đơn vị biểu diễn nội dung và vai trò trong cuộc hội thoại.",
    purpose: "Truyền ngữ cảnh có cấu trúc giữa ứng dụng và chat model.",
    explanation:
      "Message thường phân biệt vai trò system, human, AI hoặc tool. Mỗi message chứa nội dung và có thể có metadata. Chat model dùng chuỗi message làm đầu vào.",
    sourceIds: ["models"],
    example:
      '# Nội dung minh họa\nfrom langchain_core.messages import HumanMessage\n\nmessage = HumanMessage(content="Xin chào!")',
  },
  {
    id: "input-variables",
    label: "Input variables",
    type: "Concept",
    position: { x: 0, y: 150 },
    summary: "Các giá trị được truyền vào vị trí trống trong prompt template.",
    purpose: "Thay đổi nội dung đầu vào mà không cần viết lại template.",
    explanation:
      "Ví dụ template có {topic} cần một giá trị topic khi gọi. Đặt tên biến rõ ràng và bảo đảm đã cung cấp mọi biến cần thiết. Dữ liệu từ người dùng vẫn cần xử lý an toàn ở ứng dụng thật.",
    sourceIds: ["prompts"],
    example:
      '# Nội dung minh họa\nvariables = {"topic": "đồ thị tri thức"}\ntext = "Giải thích {topic}".format(**variables)',
  },
  {
    id: "structured-output",
    label: "Structured output",
    type: "Concept",
    position: { x: 240, y: 310 },
    summary: "Đầu ra theo schema để ứng dụng có thể đọc và kiểm tra.",
    purpose: "Nhận dữ liệu như danh sách khái niệm thay vì văn bản tự do.",
    explanation:
      "Bạn định nghĩa schema với các trường cần thiết. Model hoặc lớp xử lý cố gắng tạo kết quả theo schema đó. Ứng dụng vẫn phải kiểm tra dữ liệu và xử lý lỗi.",
    sourceIds: ["models"],
    example:
      "# Schema minh họa\nfrom pydantic import BaseModel\n\nclass Concept(BaseModel):\n    name: str\n    summary: str",
  },
  {
    id: "embeddings",
    label: "Embeddings",
    type: "Concept",
    position: { x: 960, y: 150 },
    summary: "Biểu diễn nội dung thành vector số phục vụ so sánh ngữ nghĩa.",
    purpose: "Tìm những đoạn văn gần nghĩa với câu hỏi trong ví dụ retrieval.",
    explanation:
      "Embedding model chuyển câu hỏi và tài liệu thành các vector. Vector store dùng chúng để tìm nội dung gần nhau. Chất lượng tìm kiếm còn phụ thuộc dữ liệu và cách chia đoạn; demo không đo chất lượng.",
    sourceIds: ["retrieval"],
    example:
      '# Mã giả minh họa\ntexts = ["Prompt là lời nhắc", "RAG sử dụng tài liệu"]\n# vectors = embedding_model.embed_documents(texts)',
  },
  {
    id: "tools",
    label: "Tools",
    type: "Concept",
    position: { x: 960, y: 0 },
    summary: "Các thao tác có mô tả để agent có thể gọi khi cần.",
    purpose: "Mở rộng khả năng ứng dụng bằng hàm tra cứu hoặc xử lý dữ liệu.",
    explanation:
      "Tool có tên, mô tả và đầu vào rõ ràng. Agent có thể yêu cầu gọi tool rồi dùng kết quả làm ngữ cảnh. Trong sản phẩm thật, mọi tool cần giới hạn quyền và kiểm tra đầu vào.",
    sourceIds: ["agents"],
    example:
      '# Hàm minh họa; chưa gắn vào agent\ndef lookup_docs(topic: str) -> str:\n    return f"Nội dung mẫu cho: {topic}"',
  },
  {
    id: "vector-stores",
    label: "Vector stores",
    type: "Module",
    position: { x: 720, y: 350 },
    summary: "Lưu vector và tìm nội dung có biểu diễn ngữ nghĩa gần nhau.",
    purpose: "Cung cấp lớp tìm kiếm cho luồng retrieval minh họa.",
    explanation:
      "Tài liệu được gắn embedding rồi đưa vào kho. Câu hỏi được chuyển thành vector để tìm các tài liệu gần nhất. Demo không tạo index hoặc kết nối cơ sở dữ liệu.",
    sourceIds: ["retrieval"],
    example:
      '# Mã giả minh họa\n# store.add_documents(documents)\n# results = store.similarity_search("RAG là gì?", k=3)',
  },
  {
    id: "text-splitters",
    label: "Text splitters",
    type: "Module",
    position: { x: 960, y: 350 },
    summary: "Chia tài liệu dài thành những đoạn nhỏ hơn để xử lý.",
    purpose: "Chuẩn bị các đoạn phù hợp cho embedding và retrieval.",
    explanation:
      "Có thể chia theo đoạn hoặc ký tự, giữ một phần chồng lấp để bảo toàn ngữ cảnh. Kích thước phù hợp tùy nội dung. Demo không thực hiện chia tài liệu từ URL nhập vào.",
    sourceIds: ["retrieval"],
    example:
      "# Mã giả minh họa\n# chunks = splitter.split_documents(documents)",
  },
  {
    id: "document-loaders",
    label: "Document loaders",
    type: "Module",
    position: { x: 1200, y: 150 },
    summary: "Đưa nội dung từ một nguồn vào định dạng tài liệu của ứng dụng.",
    purpose: "Là bước đầu chuẩn bị tài liệu cho luồng retrieval.",
    explanation:
      "Loader có thể đọc tệp hoặc nguồn bên ngoài và trả về nội dung cùng metadata. Trong ứng dụng này, URL chỉ được ghi nhận để xem trước; crawler chưa kết nối.",
    sourceIds: ["retrieval"],
    example:
      "# Mã giả minh họa\n# documents = loader.load()\n# print(documents[0].page_content)",
  },
  {
    id: "few-shot",
    label: "Few-shot examples",
    type: "Concept",
    position: { x: 0, y: 310 },
    summary: "Một vài cặp ví dụ đầu vào và đầu ra được đưa vào prompt.",
    purpose: "Minh họa cách trả lời hoặc định dạng mong muốn.",
    explanation:
      "Chọn ví dụ ngắn và liên quan, đưa chúng vào template trước câu hỏi mới. Các ví dụ hướng dẫn hành vi nhưng không bảo đảm mọi phản hồi đều chính xác.",
    sourceIds: ["prompts"],
    example:
      '# Dữ liệu ví dụ minh họa\nexamples = [{\n    "input": "Embedding",\n    "output": "Biểu diễn nội dung bằng vector số."\n}]',
  },
  {
    id: "agent-state",
    label: "Agent state",
    type: "Concept",
    position: { x: 720, y: -160 },
    summary: "Thông tin tiến trình được giữ giữa các bước của agent.",
    purpose: "Theo dõi message và dữ liệu cần thiết cho bước tiếp theo.",
    explanation:
      "State có thể chứa lịch sử message và các trường do ứng dụng định nghĩa. Cơ chế lưu bền vững phải được cấu hình riêng khi tích hợp thực tế.",
    sourceIds: ["agents"],
    example:
      '# Trạng thái minh họa\nstate = {\n    "messages": [],\n    "current_topic": "LangChain",\n}',
  },
];

const connections: [string, string, string][] = [
  ["langchain", "chat-models", "kết nối"],
  ["langchain", "prompt-templates", "sử dụng"],
  ["langchain", "output-parsers", "xử lý qua"],
  ["langchain", "retrieval", "tích hợp"],
  ["langchain", "agents", "xây dựng"],
  ["langchain", "memory", "duy trì ngữ cảnh"],
  ["chat-models", "messages", "nhận / trả về"],
  ["prompt-templates", "input-variables", "nhận"],
  ["prompt-templates", "chat-models", "tạo đầu vào"],
  ["output-parsers", "structured-output", "liên quan"],
  ["retrieval", "embeddings", "có thể dùng"],
  ["agents", "tools", "gọi"],
  ["memory", "messages", "lưu ngữ cảnh"],
  ["chat-models", "structured-output", "có thể tạo"],
  ["retrieval", "vector-stores", "tìm trong"],
  ["retrieval", "text-splitters", "chuẩn bị qua"],
  ["retrieval", "document-loaders", "nạp qua"],
  ["embeddings", "vector-stores", "lưu tại"],
  ["prompt-templates", "few-shot", "bổ sung"],
  ["agents", "agent-state", "duy trì"],
  ["memory", "agent-state", "liên quan"],
];

export const allEdges: KnowledgeEdge[] = connections.map(
  ([source, target, relation]) => ({
    id: `${source}--${target}`,
    source,
    target,
    relation,
  }),
);
export const allNodes: KnowledgeNode[] = entries.map((node) => ({
  ...node,
  relatedNodeIds: allEdges
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => (e.source === node.id ? e.target : e.source)),
}));

export function makeInitialGraph(requestedUrl: string | null = null): Graph {
  const nodes = structuredClone(allNodes.slice(0, 12));
  const ids = new Set(nodes.map((n) => n.id));
  return {
    schemaVersion: "1.0",
    isMock: true,
    requestedUrl,
    nodes,
    edges: structuredClone(
      allEdges.filter((e) => ids.has(e.source) && ids.has(e.target)),
    ),
    sources: structuredClone(sources),
  };
}
