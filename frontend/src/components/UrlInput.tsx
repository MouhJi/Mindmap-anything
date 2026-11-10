import { ArrowRight, Globe2, Info, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { validateUrl } from "../services/graph";

interface Props {
  loading: boolean;
  status: string;
  onCreate: (url: string) => void;
}
export default function UrlInput({ loading, status, onCreate }: Props) {
  const [url, setUrl] = useState(
    "https://docs.langchain.com/oss/python/langchain/overview",
  );
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="url-card">
      <form
        className={`url-form ${error ? "invalid" : ""}`}
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (loading) return;
          const message = validateUrl(url);
          setError(message);
          if (!message) onCreate(url);
        }}
      >
        <span className="url-icon">
          <Globe2 size={21} />
        </span>
        <div className="url-field">
          <label htmlFor="document-url">Bắt đầu từ một tài liệu</label>
          <input
            id="document-url"
            type="url"
            value={url}
            disabled={loading}
            onChange={(event) => {
              setUrl(event.target.value);
              setError(null);
            }}
            placeholder="https://docs.example.com"
            aria-invalid={!!error}
            aria-describedby={error ? "url-error" : "demo-notice"}
          />
        </div>
        <button className="button primary" disabled={loading} type="submit">
          {loading ? (
            <LoaderCircle size={17} className="spin" />
          ) : (
            <NetworkIcon />
          )}
          <span>{loading ? "Đang nạp…" : "Tạo đồ thị"}</span>
          <ArrowRight size={16} />
        </button>
      </form>
      {error && (
        <p id="url-error" className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="url-notice" id="demo-notice">
        <span className="demo-tag">DEMO</span>
        <span>
          {loading
            ? "Đang chuẩn bị bộ dữ liệu mẫu…"
            : status ||
              "Khám phá với dữ liệu LangChain mẫu. Crawl và LLM chưa được kết nối."}
        </span>
        <Info size={14} />
      </div>
    </div>
  );
}

function NetworkIcon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path d="m5 5 10 4-7 7Z" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="5" cy="5" r="2.5" fill="currentColor" />
      <circle cx="15" cy="9" r="2.5" fill="currentColor" />
      <circle cx="8" cy="16" r="2.5" fill="currentColor" />
    </svg>
  );
}
