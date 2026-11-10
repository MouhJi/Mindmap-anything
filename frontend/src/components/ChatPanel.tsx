import {
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  GitFork,
  LoaderCircle,
  MessageSquare,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ChatMessage, KnowledgeNode } from "../types";
import { useDialogFocus } from "../hooks/useDialogFocus";

interface Props {
  messages: ChatMessage[];
  selectedNode: KnowledgeNode | undefined;
  nodes: KnowledgeNode[];
  busy: boolean;
  onSend: (text: string) => void;
  onSelectNode: (id: string) => void;
  drawer: boolean;
  open: boolean;
  onClose: () => void;
  disabled: boolean;
}

export default function ChatPanel({
  messages,
  selectedNode,
  nodes,
  busy,
  onSend,
  onSelectNode,
  drawer,
  open,
  onClose,
  disabled,
}: Props) {
  const [draft, setDraft] = useState("");
  const history = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  useDialogFocus(drawer && open, panel, onClose);
  useEffect(() => {
    if (history.current)
      history.current.scrollTop =
        messages.length === 1 && !busy ? 0 : history.current.scrollHeight;
  }, [messages, busy, open]);
  function submit() {
    if (!draft.trim() || busy || disabled) return;
    onSend(draft.trim());
    setDraft("");
  }
  return (
    <>
      {drawer && open && (
        <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      )}
      <aside
        ref={panel}
        tabIndex={-1}
        className={`chat-panel ${drawer ? "chat-drawer" : ""} ${open ? "open" : ""}`}
        role={drawer && open ? "dialog" : undefined}
        aria-modal={drawer && open ? true : undefined}
        aria-labelledby="chat-title"
        aria-hidden={drawer && !open ? true : undefined}
      >
        <div className="chat-heading">
          <span className="chat-icon">
            <Sparkles size={19} />
          </span>
          <div>
            <h2 id="chat-title">Trò chuyện với tri thức</h2>
            <p>Cùng kết nối những ý tưởng</p>
          </div>
          {drawer ? (
            <button
              className="icon-button"
              aria-label="Đóng trò chuyện"
              onClick={onClose}
            >
              <X size={20} />
            </button>
          ) : (
            <span className="status-dot" />
          )}
        </div>
        <div className="chat-source">
          <BookOpen size={15} />
          <span>LangChain docs</span>
          <span className="demo-tag">MẪU</span>
        </div>
        <div
          ref={history}
          className="chat-history"
          role="log"
          aria-label="Lịch sử trò chuyện"
          aria-relevant="additions"
          aria-live="polite"
        >
          <div className="chat-day">
            <span />
            PHIÊN KHÁM PHÁ
            <span />
          </div>
          {messages.map((message) => (
            <div className={`chat-message ${message.role}`} key={message.id}>
              {message.role === "assistant" && (
                <div className="message-author">
                  <span className="assistant-avatar">
                    <GitFork size={13} />
                  </span>
                  GraphRAG<span>DEMO</span>
                </div>
              )}
              <div className="message-content">{message.content}</div>
              {message.role === "assistant" && message.nodeIds.length > 0 && (
                <div className="message-links">
                  {message.nodeIds
                    .map((id) => nodes.find((n) => n.id === id))
                    .filter((n): n is KnowledgeNode => !!n)
                    .map((node) => (
                      <button
                        key={node.id}
                        className="node-link"
                        onClick={() => onSelectNode(node.id)}
                      >
                        {node.label}
                        <ArrowUpRight size={12} />
                      </button>
                    ))}
                </div>
              )}
              {message.role === "assistant" && (
                <small className="response-label">
                  {message.isMock
                    ? "Phản hồi mô phỏng · Không gọi LLM"
                    : "Phản hồi từ backend"}
                </small>
              )}
            </div>
          ))}
          {messages.length === 1 && (
            <div className="chat-starter">
              <span className="eyebrow">THỬ MỘT CÂU HỎI</span>
              {[
                "LangChain gồm những thành phần nào?",
                "Retrieval hoạt động thế nào?",
                "Cho tôi ví dụ về Prompt templates",
              ].map((text) => (
                <button
                  key={text}
                  disabled={busy || disabled}
                  onClick={() => onSend(text)}
                >
                  <MessageSquare size={14} />
                  <span>{text}</span>
                  <ArrowUpRight size={14} />
                </button>
              ))}
            </div>
          )}
          {busy && (
            <div className="chat-thinking" role="status">
              <LoaderCircle size={15} className="spin" />
              Đang chuẩn bị phản hồi mẫu…
            </div>
          )}
        </div>
        <div className="chat-compose">
          {selectedNode && (
            <button
              className="chat-context"
              onClick={() => onSelectNode(selectedNode.id)}
            >
              <span className="context-indicator" />
              <span>
                Đang khám phá <strong>{selectedNode.label}</strong>
              </span>
              <ChevronRight size={14} />
            </button>
          )}
          <form
            className="chat-form"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <label className="sr-only" htmlFor="chat-input">
              Câu hỏi về đồ thị
            </label>
            <textarea
              id="chat-input"
              value={draft}
              rows={2}
              maxLength={8000}
              placeholder={
                selectedNode
                  ? `Hỏi về ${selectedNode.label}…`
                  : "Đặt câu hỏi về đồ thị…"
              }
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <div className="compose-bottom">
              <span>Shift + Enter để xuống dòng</span>
              <button
                className="send-button"
                aria-label="Gửi câu hỏi"
                type="submit"
                disabled={!draft.trim() || busy || disabled}
              >
                {busy ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <ArrowUp size={18} />
                )}
              </button>
            </div>
          </form>
          <p className="chat-disclaimer">
            <span className="status-dot" />
            Dữ liệu mẫu · Câu trả lời chỉ để minh họa
          </p>
        </div>
      </aside>
    </>
  );
}
