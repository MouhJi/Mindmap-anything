import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronRight,
  Download,
  GitFork,
  Menu,
  MessageSquare,
  Network,
  NotebookPen,
  PanelLeftOpen,
  X,
} from "lucide-react";
import Sidebar from "./components/Sidebar";
import UrlInput from "./components/UrlInput";
import GraphCanvas from "./components/GraphCanvas";
import NodeDetails from "./components/NodeDetails";
import ChatPanel from "./components/ChatPanel";
import SourcesPanel from "./components/SourcesPanel";
import NotesPanel from "./components/NotesPanel";
import { graphService, exportGraph } from "./services/graph";
import { loadNotes, saveNotes } from "./utils/storage";
import type { ChatMessage, WorkspaceTab } from "./types";
import { useMediaQuery } from "./hooks/useMediaQuery";
import { useDialogFocus } from "./hooks/useDialogFocus";

const welcome = (): ChatMessage[] => [
  {
    id: "welcome",
    role: "assistant",
    content:
      "Chào bạn! Cùng khám phá những kết nối trong tài liệu LangChain nhé.\n\nChọn một node trên đồ thị, hoặc đặt câu hỏi để bắt đầu.",
    nodeIds: [],
    isMock: true,
  },
];

export default function App() {
  const [graph, setGraph] = useState(() => graphService.getGraph());
  const [tab, setTab] = useState<WorkspaceTab>("graph");
  const [selectedId, setSelectedId] = useState<string | null>(
    "prompt-templates",
  );
  const [revision, setRevision] = useState(0);
  const epoch = useRef(0);
  const [focusRequest, setFocusRequest] = useState<{
    id: string;
    key: number;
    fitIds?: string[];
  } | null>(null);
  const [focused, setFocused] = useState(false);
  const [creating, setCreating] = useState(false);
  const createLock = useRef(false);
  const [expanding, setExpanding] = useState(false);
  const expansionLock = useRef(false);
  const [urlStatus, setUrlStatus] = useState("");
  const [messages, setMessages] = useState(welcome);
  const [chatBusy, setChatBusy] = useState(false);
  const chatLock = useRef(false);
  const [chatOpen, setChatOpen] = useState(false);
  const chatTriggerRef = useRef<HTMLButtonElement>(null);
  const chatReturnFocus = useRef<HTMLElement | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const drawer = useMediaQuery("(max-width: 1199px)");
  const mobile = useMediaQuery("(max-width: 699px)");
  const [initialNotes] = useState(() => loadNotes());
  const [notes, setNotes] = useState(initialNotes.text);
  const [storageError, setStorageError] = useState(initialNotes.error);
  const [notesStatus, setNotesStatus] = useState<"saved" | "dirty" | "error">(
    initialNotes.error ? "error" : "saved",
  );
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  const selectedNode = graph.nodes.find((n) => n.id === selectedId);
  const navRef = useRef<HTMLDivElement>(null);
  const focusRef = useRef<HTMLDivElement>(null);
  const closeNav = useCallback(() => setNavOpen(false), []);
  const closeChat = useCallback(() => {
    setChatOpen(false);
    requestAnimationFrame(() => {
      const target = chatReturnFocus.current?.isConnected
        ? chatReturnFocus.current
        : chatTriggerRef.current;
      target?.focus();
    });
  }, []);
  const closeFocus = useCallback(() => setFocused(false), []);
  useDialogFocus(mobile && navOpen, navRef, closeNav);
  useDialogFocus(focused, focusRef, closeFocus);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!mobile) setNavOpen(false);
  }, [mobile]);
  useEffect(() => {
    if (notesStatus !== "dirty") return;
    const timer = setTimeout(() => {
      const error = saveNotes(notes);
      setStorageError(error);
      setNotesStatus(error ? "error" : "saved");
    }, 650);
    return () => clearTimeout(timer);
  }, [notes, notesStatus]);
  // Flush the latest edit on reload, including edits made during the debounce.
  useEffect(() => {
    const flush = () => {
      if (notesStatus === "dirty") saveNotes(notes);
    };
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, [notes, notesStatus]);

  const notify = (text: string, error = false) => setToast({ text, error });
  const openChat = () => {
    chatReturnFocus.current = document.activeElement as HTMLElement | null;
    setChatOpen(true);
  };
  const navigate = (next: WorkspaceTab) => {
    setTab(next);
    setNavOpen(false);
  };
  const selectAndReveal = (id: string) => {
    if (!graph.nodes.some((n) => n.id === id)) {
      notify("Node này chưa có trong đồ thị hiện tại.");
      return;
    }
    setSelectedId(id);
    setTab("graph");
    setFocusRequest({ id, key: Date.now() });
    setChatOpen(false);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document
          .getElementById(`graph-node-${id}`)
          ?.focus({ preventScroll: true });
      });
    });
  };

  async function createGraph(url: string) {
    if (createLock.current) return;
    createLock.current = true;
    setCreating(true);
    setUrlStatus("");
    const currentEpoch = ++epoch.current;
    chatLock.current = false;
    setChatBusy(false);
    try {
      const next = await graphService.createGraphFromUrl(url);
      if (epoch.current !== currentEpoch) return;
      setGraph(next);
      setSelectedId("langchain");
      setRevision((r) => r + 1);
      setFocusRequest(null);
      setTab("graph");
      setMessages(welcome());
      chatLock.current = false;
      setChatBusy(false);
      setUrlStatus(
        "Đã nạp đồ thị mẫu để xem trước. Chức năng crawl chưa được kết nối.",
      );
      notify("Đã nạp đồ thị mẫu. Chức năng crawl chưa được kết nối.");
    } catch (error) {
      notify(
        error instanceof Error
          ? error.message
          : "Không thể nạp dữ liệu mẫu. Vui lòng thử lại.",
        true,
      );
    } finally {
      createLock.current = false;
      setCreating(false);
    }
  }

  async function expandNode() {
    if (!selectedId || expansionLock.current || creating) return;
    expansionLock.current = true;
    setExpanding(true);
    const currentEpoch = epoch.current;
    try {
      const next = await graphService.expandNode(graph, selectedId);
      if (epoch.current !== currentEpoch) return;
      const count = next.nodes.length - graph.nodes.length;
      setGraph(next);
      if (count)
        setFocusRequest({
          id: selectedId,
          key: Date.now(),
          fitIds: [
            selectedId,
            ...next.nodes
              .filter((n) => !graph.nodes.some((old) => old.id === n.id))
              .map((n) => n.id),
          ],
        });
      notify(
        count
          ? `Đã thêm ${count} node liên quan từ dữ liệu mẫu.`
          : "Đã hiển thị hết dữ liệu mở rộng cho node này.",
      );
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "Không thể mở rộng node.",
        true,
      );
    } finally {
      expansionLock.current = false;
      setExpanding(false);
    }
  }

  async function sendChat(question: string) {
    if (!question.trim() || chatLock.current || creating) return;
    chatLock.current = true;
    setChatBusy(true);
    const currentEpoch = epoch.current;
    setMessages((items) => [
      ...items,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: question.trim(),
        nodeIds: [],
        isMock: true,
      },
    ]);
    try {
      const reply = await graphService.askGraph({
        question,
        graph,
        selectedNodeId: selectedId,
      });
      if (epoch.current === currentEpoch)
        setMessages((items) => [
          ...items,
          { ...reply, id: crypto.randomUUID(), role: "assistant" },
        ]);
    } catch {
      if (epoch.current === currentEpoch)
        notify("Chưa thể tạo phản hồi mẫu. Bạn có thể gửi lại câu hỏi.", true);
    } finally {
      if (epoch.current === currentEpoch) {
        chatLock.current = false;
        setChatBusy(false);
      }
    }
  }

  function addNote() {
    if (!selectedNode) return;
    const references = graph.sources
      .filter((s) => selectedNode.sourceIds.includes(s.id))
      .map((s) => `- ${s.title}: ${s.url}`)
      .join("\n");
    const addition = `## ${selectedNode.label}\n${selectedNode.summary}\n\nNguồn đọc thêm (nội dung minh họa, chưa truy xuất):\n${references}`;
    const next = `${notes}${notes.trim() ? "\n\n" : ""}${addition}\n`;
    setNotes(next);
    const error = saveNotes(next);
    setStorageError(error);
    setNotesStatus(error ? "error" : "saved");
    notify(
      error ?? `Đã thêm ${selectedNode.label} và lưu vào ghi chú.`,
      !!error,
    );
  }

  function download() {
    try {
      const blob = new Blob([exportGraph(graph)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "graphrag-demo.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify("Đã xuất đồ thị hiện tại dưới dạng JSON.");
    } catch {
      notify("Trình duyệt chưa thể tải tệp. Vui lòng thử lại.", true);
    }
  }

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <a className="skip-link" href="#main-workspace">
        Đến nội dung chính
      </a>
      {mobile && navOpen && (
        <div
          className="drawer-backdrop nav-backdrop"
          onClick={closeNav}
          aria-hidden="true"
        />
      )}
      <div
        className={`sidebar-container ${navOpen ? "nav-open" : ""}`}
        ref={navRef}
        role={mobile && navOpen ? "dialog" : undefined}
        aria-modal={mobile && navOpen ? true : undefined}
        aria-label={mobile && navOpen ? "Menu điều hướng" : undefined}
        tabIndex={-1}
      >
        {mobile && (
          <button
            className="icon-button mobile-nav-close"
            aria-label="Đóng menu"
            onClick={closeNav}
          >
            <X size={20} />
          </button>
        )}
        <Sidebar
          tab={tab}
          onNavigate={navigate}
          onCollapse={() => setSidebarCollapsed(true)}
        />
      </div>
      <div className="workspace-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            {(mobile || sidebarCollapsed) && (
              <button
                className="icon-button"
                aria-label={mobile ? "Mở menu điều hướng" : "Mở rộng sidebar"}
                onClick={() =>
                  mobile ? setNavOpen(true) : setSidebarCollapsed(false)
                }
              >
                {mobile ? <Menu size={20} /> : <PanelLeftOpen size={18} />}
              </button>
            )}
            <span className="breadcrumb-icon">
              <GitFork size={16} />
            </span>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {tab === "sources"
                ? "Nguồn tài liệu"
                : tab === "notes"
                  ? "Ghi chú của tôi"
                  : "Khám phá"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="local-label">
              <span className="status-dot" />
              Chỉ chạy local
            </span>
            <span className="version-badge">DEMO WORKSPACE</span>
          </div>
        </header>
        <div className="workspace-body">
          <main className="main-workspace" id="main-workspace">
            <div className="page-heading">
              <div>
                <div className="eyebrow">TỪ TÀI LIỆU ĐẾN HIỂU BIẾT</div>
                <h1>
                  Khám phá tri thức<span>.</span>
                </h1>
                <p>Nhìn thấy kết nối. Hiểu sâu từng khái niệm.</p>
              </div>
              <button
                className="button export-button"
                aria-label="Xuất đồ thị"
                onClick={download}
                disabled={creating}
              >
                <Download size={16} />
                <span>Xuất đồ thị</span>
              </button>
            </div>
            <UrlInput
              loading={creating}
              status={urlStatus}
              onCreate={createGraph}
            />
            <div className="workspace-card" aria-busy={creating}>
              <div
                className="workspace-tabs"
                role="tablist"
                aria-label="Nội dung workspace"
                onKeyDown={(e) => {
                  const tabs: WorkspaceTab[] = ["graph", "sources", "notes"];
                  if (
                    ["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)
                  ) {
                    e.preventDefault();
                    const index =
                      e.key === "Home"
                        ? 0
                        : e.key === "End"
                          ? 2
                          : (tabs.indexOf(tab) +
                              (e.key === "ArrowRight" ? 1 : 2)) %
                            3;
                    setTab(tabs[index]);
                    document.getElementById(`tab-${tabs[index]}`)?.focus();
                  }
                }}
              >
                {[
                  {
                    id: "graph" as const,
                    label: "Đồ thị tri thức",
                    icon: Network,
                  },
                  { id: "sources" as const, label: "Tài liệu", icon: BookOpen },
                  { id: "notes" as const, label: "Ghi chú", icon: NotebookPen },
                ].map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    id={`tab-${id}`}
                    role="tab"
                    aria-selected={tab === id}
                    aria-controls={`panel-${id}`}
                    tabIndex={tab === id ? 0 : -1}
                    onClick={() => setTab(id)}
                  >
                    <Icon size={16} />
                    <span>{label}</span>
                    {id === "sources" && (
                      <span className="tab-count">{graph.sources.length}</span>
                    )}
                  </button>
                ))}
                <span className="graph-live-label">
                  <span className="status-dot" />
                  Dữ liệu mẫu
                </span>
              </div>
              <div
                id="panel-graph"
                role="tabpanel"
                aria-labelledby="tab-graph"
                hidden={tab !== "graph"}
                className={`graph-panel ${focused ? "is-focused" : ""}`}
              >
                <div
                  className="graph-focus-container"
                  ref={focusRef}
                  role={focused ? "dialog" : undefined}
                  aria-modal={focused ? true : undefined}
                  aria-label={focused ? "Đồ thị ở chế độ tập trung" : undefined}
                  tabIndex={-1}
                >
                  <GraphCanvas
                    graph={graph}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    focused={focused}
                    onToggleFocus={() => setFocused((value) => !value)}
                    revision={revision}
                    focusRequest={focusRequest}
                  />
                </div>
                <NodeDetails
                  node={selectedNode}
                  sources={graph.sources}
                  nodes={graph.nodes}
                  expanding={expanding || creating}
                  onExpand={() => {
                    void expandNode();
                  }}
                  onAsk={() => {
                    if (selectedNode) {
                      openChat();
                      void sendChat(
                        `Giải thích ${selectedNode.label} và cách sử dụng cơ bản.`,
                      );
                    }
                  }}
                  onAddNote={addNote}
                  onSelect={selectAndReveal}
                />
              </div>
              <div
                id="panel-sources"
                role="tabpanel"
                aria-labelledby="tab-sources"
                hidden={tab !== "sources"}
                className="other-tab-panel"
              >
                <SourcesPanel graph={graph} onSelectNode={selectAndReveal} />
              </div>
              <div
                id="panel-notes"
                role="tabpanel"
                aria-labelledby="tab-notes"
                hidden={tab !== "notes"}
                className="other-tab-panel"
              >
                <NotesPanel
                  value={notes}
                  onChange={(text) => {
                    setNotes(text);
                    setNotesStatus("dirty");
                  }}
                  onSave={() => {
                    const error = saveNotes(notes);
                    setStorageError(error);
                    setNotesStatus(error ? "error" : "saved");
                    notify(
                      error ?? "Đã lưu ghi chú trong trình duyệt hiện tại.",
                      !!error,
                    );
                  }}
                  status={notesStatus}
                  error={storageError}
                />
              </div>
            </div>
            <footer className="workspace-caption">
              <span>
                <GitFork size={13} />
                Học từ những kết nối.
              </span>
              <span>LangChain · Bộ sưu tập minh họa</span>
            </footer>
          </main>
          <ChatPanel
            messages={messages}
            selectedNode={selectedNode}
            nodes={graph.nodes}
            busy={chatBusy}
            onSend={(text) => {
              void sendChat(text);
            }}
            onSelectNode={selectAndReveal}
            drawer={drawer}
            open={chatOpen}
            onClose={closeChat}
            disabled={creating}
          />
        </div>
      </div>
      {drawer && !chatOpen && !focused && !navOpen && (
        <button
          ref={chatTriggerRef}
          className="chat-launcher"
          aria-label="Mở trò chuyện với tri thức"
          onClick={openChat}
        >
          <MessageSquare size={20} />
          <span>Trò chuyện</span>
        </button>
      )}
      <div className="sr-only" role="status">
        {creating ? "Đang nạp bộ dữ liệu mẫu." : urlStatus}
      </div>
      {toast && (
        <div
          className={`toast ${toast.error ? "toast-error" : ""}`}
          role={toast.error ? "alert" : "status"}
        >
          {toast.error ? <X size={17} /> : <Check size={17} />}
          <span>{toast.text}</span>
          <button
            className="icon-button"
            aria-label="Đóng thông báo"
            onClick={() => setToast(null)}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
