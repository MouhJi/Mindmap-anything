import { ArrowUpRight, BookOpen, ExternalLink, FileText } from "lucide-react";
import { useState } from "react";
import type { Graph } from "../types";

export default function SourcesPanel({
  graph,
  onSelectNode,
}: {
  graph: Graph;
  onSelectNode: (id: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <section
      className="content-panel sources-panel"
      aria-label="Nguồn tài liệu mẫu"
    >
      <div className="panel-intro">
        <span className="panel-icon">
          <BookOpen size={23} />
        </span>
        <div>
          <h2>Thư viện tài liệu</h2>
          <p>Những điểm bắt đầu cho hành trình khám phá LangChain.</p>
        </div>
        <span className="count-badge">{graph.sources.length} nguồn</span>
      </div>
      <div className="info-banner">
        <FileText size={17} />
        <span>
          Đoạn trích và liên kết node được soạn sẵn cho demo. Các URL là nguồn
          đọc thêm, chưa được crawler truy xuất.
        </span>
      </div>
      {graph.requestedUrl && (
        <p className="requested-url">
          URL yêu cầu: <span>{graph.requestedUrl}</span>
          <small>Chưa crawl · Không dùng làm bằng chứng</small>
        </p>
      )}
      {!graph.sources.length && (
        <div className="empty-state">
          <BookOpen size={35} />
          <h3>Chưa có tài liệu</h3>
          <p>Nhập một URL để nạp bộ dữ liệu demo.</p>
        </div>
      )}
      <div className="source-cards">
        {graph.sources.map((source, index) => (
          <article
            className={`source-card ${selected === source.id ? "source-selected" : ""}`}
            key={source.id}
          >
            <div className="source-card-top">
              <span className="source-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="demo-tag">DỮ LIỆU MẪU</span>
              <a
                className="icon-button"
                aria-label={`Mở nguồn ${source.title}`}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink size={16} />
              </a>
            </div>
            <button
              className="source-title"
              aria-expanded={selected === source.id}
              onClick={() =>
                setSelected(selected === source.id ? null : source.id)
              }
            >
              {source.title}
              <ArrowUpRight size={17} />
            </button>
            <a
              className="source-url"
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {source.url}
            </a>
            <p>{source.excerpt}</p>
            <button
              className="source-nodes-toggle"
              onClick={() =>
                setSelected(selected === source.id ? null : source.id)
              }
            >
              {selected === source.id
                ? "Thu gọn node liên quan"
                : "Xem các node liên quan"}
              <ArrowUpRight size={14} />
            </button>
            {selected === source.id && (
              <div className="source-node-list">
                {graph.nodes
                  .filter((n) => n.sourceIds.includes(source.id))
                  .map((n) => (
                    <button
                      className="node-link"
                      key={n.id}
                      onClick={() => onSelectNode(n.id)}
                    >
                      {n.label}
                      <ArrowUpRight size={12} />
                    </button>
                  ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
