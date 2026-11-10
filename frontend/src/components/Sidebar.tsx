import {
  BookOpen,
  FolderOpen,
  GitFork,
  Network,
  NotebookPen,
  PanelLeftClose,
  Sprout,
} from "lucide-react";
import type { WorkspaceTab } from "../types";

interface Props {
  tab: WorkspaceTab;
  onNavigate: (tab: WorkspaceTab) => void;
  onCollapse: () => void;
}

export default function Sidebar({ tab, onNavigate, onCollapse }: Props) {
  return (
    <aside className="sidebar" aria-label="Điều hướng workspace">
      <a
        className="brand"
        aria-label="GraphRAG · Về đồ thị"
        href="#graph"
        onClick={(e) => {
          e.preventDefault();
          onNavigate("graph");
        }}
      >
        <span className="brand-mark">
          <GitFork size={24} />
        </span>
        <span>
          Graph<span className="brand-light">RAG</span>
          <small>CONNECT THE DOTS</small>
        </span>
      </a>
      <div className="workspace-switch">
        <span className="workspace-avatar">K</span>
        <span>
          Knowledge workspace<small>Không gian cá nhân</small>
        </span>
      </div>
      <div className="nav-label">WORKSPACE</div>
      <nav>
        {[
          { id: "graph" as const, label: "Khám phá đồ thị", icon: Network },
          { id: "sources" as const, label: "Nguồn tài liệu", icon: BookOpen },
          { id: "notes" as const, label: "Ghi chú của tôi", icon: NotebookPen },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`nav-item ${tab === id ? "active" : ""}`}
            title={label}
            aria-label={label}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => onNavigate(id)}
          >
            <Icon size={18} />
            <span>{label}</span>
            {tab === id && <span className="active-dot" />}
          </button>
        ))}
      </nav>
      <div className="nav-label collection-label">
        BỘ SƯU TẬP <span>01</span>
      </div>
      <button
        className="collection"
        title="LangChain docs"
        aria-label="Bộ sưu tập LangChain docs"
        onClick={() => onNavigate("sources")}
      >
        <FolderOpen size={18} />
        <span>
          LangChain docs<small>Bộ dữ liệu mẫu</small>
        </span>
      </button>
      <div className="sidebar-bottom">
        <div className="workspace-tip">
          <Sprout size={22} />
          <strong>Mỗi kết nối, một góc nhìn.</strong>
          <p>Chọn một khái niệm và khám phá những điều liên quan.</p>
        </div>
        <div className="workspace-footer">
          <span className="status-dot" />
          <span>
            Workspace local<small>Dữ liệu mẫu · Phiên bản 0.1</small>
          </span>
          <button
            className="icon-button collapse-sidebar"
            aria-label="Thu gọn sidebar"
            onClick={onCollapse}
          >
            <PanelLeftClose size={17} />
          </button>
        </div>
      </div>
    </aside>
  );
}
