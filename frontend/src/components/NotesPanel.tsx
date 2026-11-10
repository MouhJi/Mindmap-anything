import { Check, HardDrive, NotebookPen, Save } from "lucide-react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
  status: "saved" | "dirty" | "error";
  error: string | null;
}
export default function NotesPanel({
  value,
  onChange,
  onSave,
  status,
  error,
}: Props) {
  return (
    <section className="content-panel notes-panel" aria-label="Ghi chú của tôi">
      <div className="panel-intro">
        <span className="panel-icon">
          <NotebookPen size={23} />
        </span>
        <div>
          <h2>Ghi lại điều bạn khám phá</h2>
          <p>Kết nối ý tưởng theo cách của riêng bạn.</p>
        </div>
        <button className="button primary" onClick={onSave}>
          <Save size={16} />
          Lưu ghi chú
        </button>
      </div>
      <div className="notes-meta">
        <span>
          <HardDrive size={15} />
          Lưu trong trình duyệt hiện tại
        </span>
        <span className={status === "error" ? "error-text" : ""} role="status">
          {status === "saved" ? (
            <>
              <Check size={15} />
              Đã lưu
            </>
          ) : status === "dirty" ? (
            "Đang chờ lưu…"
          ) : (
            "Chưa lưu được"
          )}
        </span>
      </div>
      {error && (
        <p className="storage-error" role="alert">
          {error}
        </p>
      )}
      <label className="sr-only" htmlFor="notes-editor">
        Nội dung ghi chú
      </label>
      <textarea
        id="notes-editor"
        className="notes-editor"
        placeholder={
          "Một ý tưởng hay thường bắt đầu từ một kết nối nhỏ…\n\nViết ghi chú ở đây hoặc chọn “Thêm vào ghi chú” từ một node.\nNội dung được tự động lưu sau khi bạn ngừng nhập."
        }
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <div className="notes-bottom">
        <span>Văn bản thuần · Tự động lưu</span>
        <span>{value.length.toLocaleString("vi-VN")} ký tự</span>
      </div>
    </section>
  );
}
