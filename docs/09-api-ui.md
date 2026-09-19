# 09 — API và giao diện

## 9.1 Bảng endpoint

| Method | Path | Mục đích | Ghi chú |
|---|---|---|---|
| `GET` | `/health` | **Bắt buộc bởi AgentBase** — trả 200 để runtime chuyển ACTIVE | Không chạm DB. Luôn 200 nếu process sống |
| `GET` | `/readyz` | Sẵn sàng phục vụ: DB nối được, DQ không có lỗi BLOCK, catalog nạp xong | 503 khi chưa sẵn sàng |
| `POST` | `/invocations` | Quy ước AgentBase — một câu hỏi, một câu trả lời JSON | Cổng cho Zalo/API ngoài |
| `GET` | `/` | Trang chính: dashboard + chat | HTML |
| `GET` | `/api/dashboard/summary` | Thẻ KPI tổng | JSON |
| `GET` | `/api/dashboard/campaigns` | Bảng 6 chiến dịch × các chỉ số | JSON |
| `GET` | `/api/dashboard/funnel` | Dữ liệu phễu | JSON |
| `GET` | `/api/dashboard/trend` | Chuỗi theo ngày | JSON |
| `GET` | `/api/segments` | Bảng phân khúc + CLV | JSON |
| `GET` | `/api/segments/{id}/customers.csv` | Xuất danh sách cho CRM | text/csv |
| `GET` | `/api/actions` | Khuyến nghị D3 | JSON |
| `POST` | `/api/chat` | Hỏi đáp, **SSE stream** | text/event-stream |
| `GET` | `/api/trace/{trace_id}` | Bằng chứng đầy đủ: SQL, dòng dữ liệu, kết quả từng lớp kiểm tra | Nguồn cho nút "Xem SQL & số liệu" |
| `GET`/`PUT` | `/api/admin/prompts[/{id}]` | Xem/sửa prompt | [07](07-prompt-fewshot.md) §7.5 |
| `GET`/`PUT` | `/api/admin/metrics` | Xem/sửa catalog chỉ số | |
| `GET` | `/api/admin/quality` | Bảng theo dõi chất lượng | [08](08-anti-hallucination.md) §8.8 |
| `POST` | `/api/admin/etl/run` | Chạy lại ETL | Có bảo vệ bằng token |

### `/health` và `/readyz` tách rời — và vì sao điều đó quan trọng

AgentBase dùng `GET /health` để quyết định runtime có ACTIVE hay không. Nếu ta cho `/health` fail khi mất kết nối DB, runtime sẽ bị đánh dấu lỗi và có thể bị khởi động lại liên tục — trong khi vấn đề nằm ở database chứ không ở container.

Vì vậy: `/health` chỉ khẳng định **process còn sống**. `/readyz` mới nói **có phục vụ được câu trả lời đúng hay không**. UI đọc `/readyz` để hiện banner cảnh báo.

## 9.2 Hợp đồng `/invocations`

```jsonc
// Request
{
  "message": "Chiến dịch nào đang lỗ?",
  "session_id": "optional",          // hoac header X-GreenNode-AgentBase-Session-Id
  "history": [ {"role":"user","content":"..."}, {"role":"assistant","content":"..."} ],
  "options": { "locale": "vi", "max_words": 400 }
}

// Response
{
  "trace_id": "8f14e45f-...",
  "answer_markdown": "### Kết luận\nHai chiến dịch đang lỗ: ...",
  "trust": {
    "score": 0.94, "band": "PASS",
    "checks": { "numeric_grounding": 1.0, "entity_grounding": 1.0,
                "stats_guard": 1.0, "judge": "pending" }
  },
  "evidence": [
    { "fact_id": "F1", "title": "ROMI theo chiến dịch",
      "sql": "SELECT ...", "columns": [...], "rows": [...] }
  ],
  "caveats": ["Tỷ lệ lead thành hồ sơ là tỷ lệ tổng hợp mức chiến dịch..."],
  "decision": "ANSWERED",
  "meta": { "llm_calls": 2, "latency_ms": 4120,
            "prompt_version": "2.1.0", "metrics_version": "1.3.0",
            "data_version": "etl_run_42" }
}
```

`evidence` và `caveats` **luôn** có mặt, kể cả khi band là PASS. Đó là cách hiện thực hoá nguyên tắc P2 ở tầng API: người gọi qua Zalo hay qua API ngoài cũng phải nhận được bằng chứng, không chỉ người dùng web.

## 9.3 SSE cho chat

> Phần này nêu hình dạng cơ bản. Bảng sự kiện đầy đủ, thông báo tiến trình theo giai đoạn, cơ chế kiểm chứng theo khối khi streaming, và cách xử lý huỷ/mất mạng nằm ở [15 — Streaming](15-streaming.md).

```
POST /api/chat        Content-Type: application/json
Accept: text/event-stream
```

```
event: status
data: {"stage":"routing","message":"Đang xác định câu hỏi"}

event: status
data: {"stage":"computing","message":"Đang truy vấn 3 chỉ số"}

event: evidence
data: {"facts":[{"fact_id":"F1","title":"...","row_count":6}]}

event: token
data: {"text":"### Kết luận\n"}

event: token
data: {"text":"Hai chiến dịch đang lỗ"}

event: verified
data: {"trust":0.94,"band":"PASS","numeric":"12/12","entity":"ok","stats":"ok"}

event: judge
data: {"entailment_rate":0.92,"contradiction_rate":0.0,"trust":0.95}

event: done
data: {"trace_id":"8f14e45f-...","latency_ms":4120}
```

Điểm tinh tế: **token chỉ được stream sau khi thay thế thẻ**. Người dùng không bao giờ nhìn thấy `{{F1.r1.romi}}` nhấp nháy trên màn hình. Cách làm: narrator stream về buffer của server, server phân giải thẻ theo từng đoạn hoàn chỉnh rồi mới đẩy ra client. Một đoạn có thẻ không phân giải được thì cả đoạn bị giữ lại và thay bằng cảnh báo.

Sự kiện `judge` đến sau `done` — đó là lớp L5 bất đồng bộ ([08](08-anti-hallucination.md) §8.6). Client cập nhật huy hiệu tại chỗ.

## 9.4 Bố cục giao diện

Ràng buộc bắt buộc: **vùng hội thoại tối đa 60% chiều cao màn hình.**

```
+======================================================================+
| Marketing Insight Agent    [Du lieu: 01-31/08/2026]  [ETL: 2h truoc] |  56px
+======================================================================+
|                                                                      |
|  +----------------+ +----------------+ +----------------+            |
|  | Loi nhuan rong | | ROMI trung binh| | Ty le vay lai  |            |
|  |  +509,8 trieu  | |     1,32       | |     13,8%      |            |  KPI
|  +----------------+ +----------------+ +----------------+            |
|                                                                      |
|  +--------------------------------+ +-----------------------------+  |
|  | ROMI theo chien dich           | | Pheu: lead -> ho so -> giai |  |
|  | [bar chart, am/duong to mau]   | | [funnel chart]              |  |  DASHBOARD
|  +--------------------------------+ +-----------------------------+  |  (cuon)
|                                                                      |
|  +------------------------------------------------------------+     |
|  | Bang chi tiet 6 chien dich (sortable)                       |     |
|  +------------------------------------------------------------+     |
|                                                                      |
+======================================================================+
|  [Chien dich] [Chan dung KH] [Hanh dong CLV] [Hoi dap]   <- tab      |
+======================================================================+
|  VUNG HOI THOAI  -- max-height: 60vh, cuon rieng                     |
|                                                                      |
|   Ban: Vi sao Broker Network lo?                                     |
|                                                                      |
|   Agent: ### Ket luan                                                |
|          Chien dich dang lo 66.794.870 VND voi ROMI -1,85...         |  <= 60vh
|          [Da kiem chung  12/12 so]  [Xem SQL & du lieu]              |
|                                                                      |
+----------------------------------------------------------------------+
|  [ Nhap cau hoi...                                  ]  [Gui]         |  composer
+======================================================================+
```

### Thực thi ràng buộc 60%

```html
<!-- Vung cuon hoi thoai: dung 60vh, khong hon -->
<div id="chat-scroll"
     class="overflow-y-auto overscroll-contain"
     style="max-height: 60vh;">
  <template x-for="m in messages"> ... </template>
</div>

<!-- Composer nam NGOAI 60vh -->
<form class="border-t p-3 flex gap-2" @submit.prevent="send()">
  <input class="flex-1 rounded-lg border px-3 py-2" x-model="draft">
  <button class="rounded-lg px-4 py-2 bg-slate-900 text-white">Gửi</button>
</form>
```

Ba điểm cần làm đúng, nếu không ràng buộc sẽ bị phá trên thiết bị thật:

1. **`max-height` chứ không phải `height`.** Hội thoại ngắn thì khung co lại, dashboard được thêm chỗ. Chỉ khi dài mới chạm trần 60%.
2. **`60vh` áp cho đúng vùng cuộn**, không tính thanh tab và composer. Ràng buộc nói "đoạn chat" nên hiểu là phần nội dung hội thoại.
3. **Mobile dùng `dvh` chứ không phải `vh`.** Trên iOS Safari, `vh` không tính thanh địa chỉ co giãn nên khung bị cao quá và composer trôi khỏi màn hình.

```css
#chat-scroll { max-height: 60vh; }
@supports (height: 100dvh) { #chat-scroll { max-height: 60dvh; } }

/* Man hinh hep: chat va dashboard xep chong, chat van giu tran 60% */
@media (max-width: 768px) {
  #chat-scroll { max-height: 55dvh; }
}
```

Một kiểm thử tự động giữ ràng buộc này khỏi bị phá về sau:

```python
def test_chat_area_never_exceeds_60_percent(page):
    page.goto(BASE_URL)
    for _ in range(40):
        page.fill("#chat-input", "test"); page.click("#chat-send")
    h_chat = page.eval_on_selector("#chat-scroll", "el => el.clientHeight")
    h_view = page.evaluate("window.innerHeight")
    assert h_chat <= h_view * 0.60 + 1     # +1 cho sai so lam tron
```

## 9.5 Bốn tab

| Tab | Nội dung | Gọi LLM |
|---|---|---|
| **Chiến dịch** (D1) | KPI, ROMI bar chart (âm tô đỏ), phễu, xu hướng theo ngày, bảng chi tiết | **0** |
| **Chân dung KH** (D2) | Thẻ phân khúc: size, CLV kèm khoảng, repeat rate kèm CI, phân bố tuổi/thu nhập/thiết bị | **0** |
| **Hành động CLV** (D3) | Danh sách khuyến nghị: phân khúc, tác động ước tính, giả định, công sức, nút xuất CSV | **0** |
| **Hỏi đáp** | Chat tự do | ≤ 2 |

Ba tab đầu **không gọi LLM** — dữ liệu từ SQL, phần chữ từ template điền số. Đây vừa là biện pháp chống hallucination triệt để, vừa là cách sống dưới trần 10 RPM ([04](04-architecture.md) §4.5).

## 9.6 Hiển thị lòng tin

Mỗi câu trả lời của agent mang một huy hiệu:

```
+------------------------------------------------------------+
| ### Ket luan                                               |
| Chien dich Broker Network dang lo 66.794.870 VND ...       |
|                                                            |
| [🟢 Da kiem chung]  12/12 so khop  |  [Xem SQL & du lieu]  |
+------------------------------------------------------------+
```

Bấm "Xem SQL & dữ liệu" mở panel:

```
+------------------------------------------------------------+
| Bang chung  (trace 8f14e45f)                               |
+------------------------------------------------------------+
| F1 - ROMI theo chien dich                       6 dong     |
|   SELECT campaign_id, campaign_name,                       |
|          SUM(net_profit) / NULLIF(SUM(...),0) AS romi ...  |
|   +--------------------------+--------+-------------+      |
|   | campaign_name            | romi   | net_profit  |      |
|   | Vay Lai - Zalo Remarket. | 6,20   | 392.498.500 |      |
|   | ...                      |        |             |      |
|                                                            |
| Kiem chung                                                 |
|   Numeric grounding  12/12 the phan giai duoc      PASS    |
|   Entity grounding   3/3 ten hop le                PASS    |
|   Stats guard        4/15 so sanh co y nghia       PASS    |
|   LLM judge          entail 0,92 | contra 0,00     PASS    |
|                                                            |
| Luu y                                                      |
|   - Ty le lead thanh ho so la ty le tong hop muc chien dich|
+------------------------------------------------------------+
```

Panel này là hiện thực hoá nguyên tắc P2 ở tầng giao diện. Nó cũng chính là thứ làm agent thuyết phục được người chất vấn: chị Head of Lending hỏi "số này ở đâu ra?" và câu trả lời có sẵn trên màn hình, không cần ai đi dò lại.

Màu huy hiệu: 🟢 PASS · 🟡 HEDGE (kèm lý do) · ⚪ ABSTAIN · 🔴 BLOCKED.

## 9.7 Biểu đồ

Dùng ECharts, và mọi biểu đồ tuân theo bốn quy tắc:

1. **Giá trị âm luôn tô khác màu.** ROMI của Broker (−1,85) và Momo (−0,41) phải bật ra khỏi màn hình. Đây là thông tin quan trọng nhất trong dashboard.
2. **Cỡ mẫu luôn hiện.** Mọi tỷ lệ kèm `n` trong tooltip. Cột có `n < 30` vẽ gạch chéo và tooltip ghi "mẫu nhỏ".
3. **Khoảng tin cậy vẽ thành thanh sai số** ở các biểu đồ tỷ lệ vay lại và CLV. Không có chuyện vẽ một cột đặc cho `p = 86,2%, n = 29`.
4. **Trục tiền tệ rút gọn** (`392,5 tr`) nhưng tooltip hiện số đầy đủ (`392.498.500 VND`) — và cả hai dạng đều phải khớp với chính sách numeric ở [08](08-anti-hallucination.md) §8.3.

| Biểu đồ | Loại | Dữ liệu |
|---|---|---|
| ROMI theo chiến dịch | bar ngang, âm/dương khác màu | `/api/dashboard/campaigns` |
| Phễu | funnel | lead → hồ sơ → giải ngân |
| Phân rã lợi nhuận | waterfall | doanh thu → từng khoản chi phí → lợi nhuận ròng |
| Xu hướng theo ngày | line, 31 điểm | `/api/dashboard/trend` |
| Kích thước × giá trị phân khúc | scatter, bán kính = size | `/api/segments` |
| Tỷ lệ vay lại theo nhóm | bar + thanh sai số | `/api/segments` |
| Lý do từ chối | treemap 2 cấp | `reason_level_1` → `reason_level_2` |

## 9.8 Định dạng số vi-VN

Một nguồn duy nhất, dùng chung cho backend và frontend — vì bộ kiểm tra numeric grounding so khớp chính chuỗi mà người dùng nhìn thấy.

```python
# app/web/formatting.py
def fmt_vnd(v: float | None) -> str:
    if v is None: return "—"
    return f"{v:,.0f}".replace(",", ".") + " VND"      # 392.498.500 VND

def fmt_vnd_short(v: float | None) -> str:
    if v is None: return "—"
    a = abs(v)
    if a >= 1e9: return f"{v/1e9:,.1f}".replace(",", ".").replace(".", ",", 1) + " tỷ"
    if a >= 1e6: return f"{v/1e6:,.1f}".replace(".", ",") + " tr"
    return fmt_vnd(v)

def fmt_pct(v: float | None, d: int = 1) -> str:
    return "—" if v is None else f"{v*100:.{d}f}".replace(".", ",") + "%"

def fmt_ratio(v: float | None, d: int = 2) -> str:
    return "—" if v is None else f"{v:.{d}f}".replace(".", ",")
```

`None` luôn hiển thị `—`, không bao giờ `0`. Nhầm hai thứ này sẽ khiến "không có dữ liệu" trông như "không có doanh thu" — một lỗi nghiêm trọng trong báo cáo tài chính.

Frontend dùng cùng logic qua `Intl.NumberFormat('vi-VN')`, và có một test đối chiếu hai bên trên cùng bộ giá trị để tránh trôi lệch.

## 9.9 Truy cập và bảo mật

PoC không làm RBAC ([01](01-overview.md) §1.3). Nhưng hai chỗ vẫn phải rào:

* `/api/admin/*` yêu cầu header `X-Admin-Token` khớp `config/secrets.yaml`. Không có token thì 404 (chứ không phải 401 — không thông báo sự tồn tại của trang admin).
* Endpoint AgentBase nên đặt **Inbound Auth = IAM Permissions** thay vì "No authorization", trừ khi cần Zalo gọi vào thì mới mở. Runtime cũng hỗ trợ IP Access Control nếu muốn siết thêm.

Ràng buộc "tạm lưu model và API key trong repo" được xử lý ở [10](10-config-secrets.md).
