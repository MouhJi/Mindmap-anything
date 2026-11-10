import {
  ArrowUpRight,
  BookmarkPlus,
  ChevronRight,
  ExternalLink,
  LoaderCircle,
  MessageCircle,
  Network,
  Plus,
} from "lucide-react";
import { useEffect, useRef } from "react";
import type { KnowledgeNode, Source } from "../types";
import { nodeTypeLabels } from "../types";

interface Props {
  node: KnowledgeNode | undefined;
  sources: Source[];
  expanding: boolean;
  onExpand: () => void;
  onAsk: () => void;
  onAddNote: () => void;
  onSelect: (id: string) => void;
  nodes: KnowledgeNode[];
}

export default function NodeDetails({
  node,
  sources,
  expanding,
  onExpand,
  onAsk,
  onAddNote,
  onSelect,
  nodes,
}: Props) {
  const detailsRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (detailsRef.current) detailsRef.current.scrollTop = 0;
  }, [node?.id]);
  if (!node)
    return (
      <section className="node-details empty-details">
        <Network size={28} />
        <h2>Một khái niệm mở ra nhiều kết nối</h2>
        <p>Chọn một node để xem giải thích, ví dụ và nguồn tham khảo.</p>
      </section>
    );
  return (
    <section
      ref={detailsRef}
      className="node-details"
      aria-label={`Chi tiết ${node.label}`}
    >
      <div className="details-heading">
        <div>
          <div className="eyebrow">
            KHÁI NIỆM ĐANG CHỌN <ChevronRight size={12} />
          </div>
          <h2>
            {node.label}
            <span className={`type-badge ${node.type.toLowerCase()}`}>
              {nodeTypeLabels[node.type]}
            </span>
          </h2>
        </div>
        <button
          className="button subtle expand-node"
          disabled={expanding}
          onClick={onExpand}
        >
          {expanding ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <Plus size={16} />
          )}
          {expanding ? "Đang mở rộng…" : "Mở rộng node"}
        </button>
      </div>
      <p className="node-summary">{node.summary}</p>
      <div className="details-grid">
        <div>
          <h3>DÙNG ĐỂ LÀM GÌ?</h3>
          <p>{node.purpose}</p>
        </div>
        <div>
          <h3>CÁCH HOẠT ĐỘNG</h3>
          <p>{node.explanation}</p>
        </div>
      </div>
      {node.example && (
        <details className="code-example" key={node.id}>
          <summary>
            <span>
              <span className="code-symbol">&lt;/&gt;</span> Ví dụ code minh họa
            </span>
            <ChevronRight size={16} />
          </summary>
          <pre>
            <code>{node.example}</code>
          </pre>
        </details>
      )}
      <div className="related-list">
        <span>Liên quan</span>
        {node.relatedNodeIds
          .map((id) => nodes.find((n) => n.id === id))
          .filter((n): n is KnowledgeNode => !!n)
          .map((n) => (
            <button key={n.id} onClick={() => onSelect(n.id)}>
              {n.label}
              <ArrowUpRight size={12} />
            </button>
          ))}
      </div>
      <div className="source-links">
        <span>Nguồn đọc thêm</span>
        {sources
          .filter((s) => node.sourceIds.includes(s.id))
          .map((s) => (
            <a
              key={s.id}
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {s.title}
              <ExternalLink size={12} />
            </a>
          ))}
      </div>
      <div className="details-footer">
        <span className="mock-caption">
          Nội dung minh họa · Chưa truy xuất từ URL
        </span>
        <div>
          <button className="button text-button" onClick={onAddNote}>
            <BookmarkPlus size={16} />
            Thêm vào ghi chú
          </button>
          <button className="button subtle" onClick={onAsk}>
            <MessageCircle size={16} />
            Hỏi về node này
          </button>
        </div>
      </div>
    </section>
  );
}
