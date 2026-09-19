# ADR-005 — FastAPI + Jinja2 + Tailwind + Alpine.js + ECharts, không có bước build

**Trạng thái:** Đã chốt · **Ngày:** 2026-09-19 · Liên quan: [09](../09-api-ui.md)

## Bối cảnh

Yêu cầu: dùng thư viện/framework có sẵn; vùng chat tối đa 60% chiều cao màn hình. Giao diện cần cả **dashboard** (KPI, biểu đồ, bảng) lẫn **chat streaming**.

Ràng buộc triển khai: AgentBase Runtime nhận đúng một Docker image, yêu cầu lắng nghe cổng 8080 và có `GET /health`. Mọi route khác tự do.

## Quyết định

Một process FastAPI phục vụ tất cả: `/health`, `/invocations`, UI HTML, và `/api/*`.

* **Jinja2** cho template (có sẵn cùng FastAPI)
* **Tailwind CSS** qua CDN cho style
* **Alpine.js** qua CDN cho tương tác và state
* **Apache ECharts** qua CDN cho biểu đồ
* **marked** qua CDN để render markdown
* **SSE** (`sse-starlette`) cho chat streaming

Không có Node, không có bundler, không có bước build frontend.

## Lý do

* **Một image, một process.** Thêm một frontend build riêng nghĩa là thêm multi-stage Dockerfile, thêm thời gian build, thêm một lớp có thể hỏng — để đổi lấy gì đó mà bài toán này không cần.
* **ECharts thay vì Chart.js** vì có sẵn biểu đồ **funnel** và **treemap** — đúng hai thứ ta cần cho phân tích phễu và cây lý do từ chối. Chart.js phải tự vẽ.
* **Alpine thay vì React/Vue** vì toàn bộ state của UI là: tab đang mở, danh sách tin nhắn, panel bằng chứng đóng/mở. Khoảng 15 KB là đủ; một SPA đầy đủ là thừa.
* **Ràng buộc 60% chỉ là một dòng CSS** — `max-height: 60vh` trên đúng vùng cuộn. Không cần framework nào để làm việc đó.
* Ba tab dashboard render server-side bằng Jinja nên hiện số ngay, không có màn hình trắng chờ JS.

## Phương án đã cân nhắc

| Phương án | Vì sao loại |
|---|---|
| **Streamlit** | Nhanh nhất để dựng, nhưng khó kiểm soát layout chính xác (ràng buộc 60% trở nên chật vật), khó làm SSE token-by-token, và khó gắn `/health` + `/invocations` theo đúng hợp đồng AgentBase trong cùng process |
| **Gradio** | `gr.Chatbot` có sẵn và tiện, nhưng dashboard nhiều biểu đồ + bảng + panel bằng chứng thì gượng ép; cũng vướng cùng vấn đề hợp đồng HTTP |
| **Next.js / React SPA** | Cần Node trong build, multi-stage Dockerfile, image lớn hơn nhiều. Không đổi lại giá trị nào cho một PoC |
| **assistant-ui / thư viện chat React** | Đẹp và đầy đủ, nhưng kéo theo toàn bộ toolchain React |

## Hệ quả

**Tích cực:** image nhỏ (< 400 MB); build nhanh; một process duy nhất cần quản lý; hợp đồng AgentBase thoả tự nhiên; ràng buộc 60% thực thi bằng một dòng CSS và kiểm thử được bằng Playwright.

**Tiêu cực:** thiếu type-safety ở frontend; component chat phải tự viết (khoảng 150 dòng JS); nếu sau này UI phức tạp lên đáng kể thì sẽ phải chuyển sang framework thật.

**Rủi ro CDN:** ba thư viện tải từ CDN. Nếu mạng nơi demo chặn CDN thì UI vỡ. Giảm thiểu: tải sẵn các file này vào `app/web/static/vendor/` trong Dockerfile và tham chiếu cục bộ. Nên làm trước buổi demo.

**Kiểm thử ràng buộc 60%:** có test Playwright chạy ở ba kích thước viewport (1920×1080, 1366×768, 390×844) để ràng buộc không bị phá về sau. Trên mobile dùng `dvh` thay `vh` vì iOS Safari không tính thanh địa chỉ co giãn vào `vh`.
