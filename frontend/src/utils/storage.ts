const STORAGE_KEY = "graphrag.demo.notes.v1";
export interface NotesStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}
export interface StorageResult {
  text: string;
  error: string | null;
}

function browserStorage(): NotesStorage {
  return window.localStorage;
}

export function loadNotes(storage?: NotesStorage): StorageResult {
  try {
    const value = (storage ?? browserStorage()).getItem(STORAGE_KEY);
    if (value === null) return { text: "", error: null };
    const parsed: unknown = JSON.parse(value);
    if (
      typeof parsed !== "object" ||
      !parsed ||
      !("text" in parsed) ||
      typeof parsed.text !== "string"
    )
      throw new Error("Invalid notes");
    return { text: parsed.text, error: null };
  } catch {
    return {
      text: "",
      error:
        "Không thể khôi phục ghi chú. Nội dung mới sẽ được giữ trong phiên này; bạn có thể sao chép để lưu riêng.",
    };
  }
}

export function saveNotes(text: string, storage?: NotesStorage): string | null {
  try {
    (storage ?? browserStorage()).setItem(
      STORAGE_KEY,
      JSON.stringify({ version: 1, text }),
    );
    return null;
  } catch {
    return "Trình duyệt không cho phép lưu ghi chú. Nội dung vẫn còn trong phiên này; hãy sao chép để lưu riêng.";
  }
}
