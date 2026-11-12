# GraphRAG frontend — kiểm tra local

Giao diện được kiểm tra ngày **10/11/2026**. Frontend chạy độc lập bằng Vite trên
`http://127.0.0.1:5173/`. Không triển khai hoặc công khai website.

## Kiểm tra tự động

Quy trình pnpm được kiểm tra ngày **12/11/2026** trên Windows với Node.js
`24.22.0` và pnpm `11.25.0`. Các lệnh frontend chạy trong `frontend/`.

- `pnpm install --frozen-lockfile` cài thành công vào `node_modules` trống.
  `pnpm import` giữ nguyên phiên bản và mã kiểm tra toàn vẹn của cả 143 gói trong
  lockfile. `pnpm-workspace.yaml` cho phép `postinstall` của `esbuild@0.28.2`.
- `pnpm test` cho kết quả **13/13 đạt** bằng test runner có sẵn của Node.
  Bao gồm tính toàn vẹn graph/source, URL HTTP(S), requestedUrl tách khỏi nguồn,
  mở rộng trực tiếp có giới hạn, chống trùng node/cạnh, loại cạnh thiếu endpoint,
  reset đồ thị, chat theo ngữ cảnh/ngoài phạm vi, schema và tính riêng tư của
  export, khôi phục ghi chú, localStorage lỗi/hỏng và provenance của adapter.
- `pnpm build` hoàn tất kiểm tra TypeScript strict và build production bằng Vite.
  Font tiếng Việt được đóng gói local cùng ứng dụng.
- `pnpm dev` khởi động Vite. Trang `/` và module `/src/main.tsx` đều trả HTTP 200
  từ `127.0.0.1:5173`. Server đã dừng sau kiểm tra.

Kết quả Python và xuất JSON dưới đây thuộc lượt kiểm tra ngày **10/11/2026**.

- `python -m pytest -q -p no:cacheprovider --basetemp=<thư mục mới>` với Python
  trong `.venv`: **113 đạt, 1 bỏ qua** ở lần kiểm tra. Test Neo4j live được bỏ
  qua theo cấu hình hiện tại. Đã dùng thư mục tạm mới trong
  `frontend/qa-temp/` vì thư mục tạm mặc định của sandbox không khả dụng.
- Tệp JSON tải xuống từ trình duyệt được đọc và parse lại: `schemaVersion=1.0`,
  `isMock=true`, `requestedUrl=https://example.com/learning`, **15 node duy
  nhất, 18 cạnh duy nhất, 5 nguồn**. Chỉ có sáu trường được yêu cầu; không có
  ghi chú hoặc lịch sử chat.

## Kiểm tra trực tiếp bằng trình duyệt

Đã dùng trình duyệt trong ứng dụng để thao tác, quan sát DOM và chụp ảnh ở
desktop **1280×720**, **1440×900**, tablet **1024×768** và mobile **390×844**.

| Luồng | Kết quả quan sát |
| --- | --- |
| Mở ứng dụng | Hiện 12 node, 14 cạnh, chi tiết Prompt templates và chat demo. |
| URL không phải HTTP(S) | `javascript:alert(1)` bị từ chối; lỗi nằm sát input và được đánh dấu `alert`. |
| URL hợp lệ | Có loading, nút gửi bị khóa; nạp sample và thông báo rõ crawler chưa kết nối. |
| Chọn node | Click Retrieval đổi chi tiết và ngữ cảnh chat; chọn node bằng Enter cũng hoạt động. |
| Mở rộng | Retrieval thêm Vector stores, Text splitters và Document loaders. Bấm lại giữ 15 node/18 cạnh, báo hết dữ liệu. |
| Pan / zoom / fit | Kéo nền thay đổi viewport; nút zoom đổi tỷ lệ; fit trả đồ thị vào khung. Chọn Embeddings sau zoom vẫn đúng. |
| Tìm kiếm | `aGeNtS` tìm được Agents; Enter đưa vào vùng nhìn. Truy vấn không tồn tại có thông báo; xóa tìm kiếm hoạt động. |
| Lọc | Chọn Khái niệm còn 5 node; xóa bộ lọc khôi phục tập node đã nạp. Cạnh được giới hạn theo endpoint đang render. |
| Focus mode | Mở được vùng đồ thị lớn và đóng bằng Escape; trạng thái lựa chọn được giữ. |
| Chat | “Hỏi về node này” gửi câu hỏi chứa tên Retrieval và nhận nội dung mẫu tương ứng. Click Embeddings trong phản hồi chọn đúng node. Câu hỏi thời tiết nhận giới hạn dữ liệu mẫu. |
| Soạn chat | Nội dung chỉ có khoảng trắng không gửi được; Shift+Enter xuống dòng; Enter gửi câu hỏi. Lịch sử cuộn riêng, composer vẫn truy cập được. |
| Nguồn tài liệu | Sidebar đổi nội dung thực sự; chọn nguồn hiện các node liên quan; chọn node quay lại graph. |
| Ghi chú | Thêm Agents chèn tên, tóm tắt và nguồn; lưu, tải lại và mở tab vẫn giữ nội dung. Nội dung QA đã được xóa sau khi kiểm tra. |
| Xuất JSON | Tải được tệp graph ban đầu và graph đã mở rộng; nội dung đã được parse và kiểm tra như trên. |
| Mobile / tablet | Truy cập được graph, tài liệu, ghi chú và drawer chat; chiều rộng document bằng viewport, không cuộn ngang toàn trang. |
| Drawer accessibility | Focus chuyển vào drawer, Shift+Tab được giữ trong dialog; Escape đóng và trả focus về nút mở. |
| Console | Không ghi nhận lỗi console trong lượt kiểm tra cuối sau reload. |

Ảnh desktop và mobile được lưu cùng artifact của chat. Viewport kiểm thử đã
được trả về kích thước mặc định sau khi hoàn thành.

## Phạm vi xác minh

Đã kiểm tra bàn phím và DOM accessibility trong trình duyệt; chưa chạy trình
đọc màn hình riêng hoặc thiết bị cảm ứng vật lý. Các nhánh localStorage bị chặn,
quota và dữ liệu hỏng được kiểm tra bằng unit test. Không kiểm tra crawl, LLM
hoặc kết nối Neo4j thật: các chức năng đó nằm ngoài demo này. Adapter đọc backend
được chuẩn bị nhưng không tự kích hoạt từ giao diện.
