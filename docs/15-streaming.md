# 15 — Streaming phản hồi và thông báo tiến trình

> Mục tiêu: người dùng **không bao giờ nhìn vào màn hình trống**. Mỗi giai đoạn xử lý đều báo rõ đang làm gì, và phần diễn giải chảy ra dần thay vì hiện một cục sau 8 giây.

## 15.1 Vấn đề cần giải, và cái bẫy nằm ở đâu

Một câu hỏi phân tích mất 4–8 giây: truy vấn, kiểm định thống kê, gọi LLM viết, rồi kiểm chứng. Không có phản hồi trung gian thì người dùng tưởng hệ thống treo.

Nhưng streaming va thẳng vào thiết kế chống hallucination ở [08](08-anti-hallucination.md):

* Narrator phát ra **thẻ** `{{F1.r1.romi}}` chứ không phát ra số. Stream token thô sẽ khiến người dùng nhìn thấy `{{F1.r` nhấp nháy trên màn hình.
* Lớp L2 numeric grounding chạy **sau khi có toàn bộ câu trả lời**. Nếu đã stream hết rồi mới phát hiện một con số bịa thì đã muộn — người dùng đọc xong rồi.

Giải pháp không phải là bỏ streaming, cũng không phải là bỏ kiểm chứng. Giải pháp là **kiểm chứng theo khối (block-level verification)**: đơn vị stream không phải token mà là **khối markdown hoàn chỉnh** (một đoạn văn, một tiêu đề, một gạch đầu dòng). Mỗi khối được thay thế thẻ và kiểm chứng ngay khi nó hoàn chỉnh, rồi mới đẩy ra client.

Điều may mắn: việc thay thế thẻ **vốn đã** đòi hỏi buffer tới ranh giới khối (một thẻ có thể bị cắt giữa hai token). Nên ta có kiểm chứng gần như miễn phí tại cùng ranh giới đó.

```
LLM token  ->  [ Buffer theo khoi ]  ->  thay the the  ->  L2 + L3 tren khoi
                       |                                          |
                 giu lai the chua du                       dat  -> emit block
                                                           fail -> emit block bi chan
```

Độ trễ thêm vào: một đoạn văn thay vì một token. Thực tế khoảng 200–600 ms mỗi khối — vẫn cho cảm giác chảy mượt, mà **không một con số chưa kiểm chứng nào lọt lên màn hình**.

## 15.2 Giai đoạn và thông báo

Thông báo tiến trình nằm trong `config/stages.yaml`, không hardcode — đúng nguyên tắc P4 ([01](01-overview.md) §1.5).

```yaml
# config/stages.yaml
version: "1.0.0"

stages:
  intake:     { label_vi: "Đang đọc câu hỏi",                    weight: 1 }
  routing:    { label_vi: "Đang xác định loại phân tích",        weight: 1 }
  planning:   { label_vi: "Đang chọn chỉ số cần tính",           weight: 1 }
  computing:  { label_vi: "Đang truy vấn dữ liệu",               weight: 4,
                template_vi: "Đang truy vấn {n_metrics} chỉ số trên {n_rows} dòng" }
  analyzing:  { label_vi: "Đang kiểm định thống kê",             weight: 2 }
  narrating:  { label_vi: "Đang viết phân tích",                 weight: 6 }
  verifying:  { label_vi: "Đang đối chiếu số liệu với nguồn",    weight: 2 }
  rendering:  { label_vi: "Đang hoàn thiện",                     weight: 1 }
  judging:    { label_vi: "Đang kiểm tra lại bằng mô hình",      weight: 0 }   # bat dong bo

# Ghi de theo tung playbook -- day la cho tra loi yeu cau
# "neu dang tao dashboard thi bao dang tao dashboard"
playbook_overrides:
  campaign_overview:
    computing: "Đang tạo dashboard hiệu quả chiến dịch"
    narrating: "Đang tóm tắt kết quả từng chiến dịch"
  campaign_diagnosis:
    computing: "Đang phân rã chi phí và phễu của chiến dịch"
    narrating: "Đang viết chẩn đoán"
  funnel_analysis:
    computing: "Đang dựng phễu lead → hồ sơ → giải ngân"
  customer_persona:
    computing: "Đang dựng chân dung các tập khách hàng"
    analyzing: "Đang tính CLV và khoảng tin cậy cho từng phân khúc"
    narrating: "Đang mô tả chân dung"
  segment_deep_dive:
    computing: "Đang bóc tách phân khúc"
  clv_actions:
    computing: "Đang tìm cơ hội tăng giá trị vòng đời"
    analyzing: "Đang ước lượng tác động của từng hành động"
    narrating: "Đang soạn khuyến nghị"
  risk_fraud:
    computing: "Đang phân tích hồ sơ bị từ chối"
  data_question:
    computing: "Đang đếm dữ liệu"
  freeform:
    planning:  "Đang dựng truy vấn cho câu hỏi này"
    computing: "Đang chạy truy vấn có kiểm soát"
  export:
    computing: "Đang lọc danh sách khách hàng"
    rendering: "Đang xuất file CSV"

# Thong bao dac biet, khong thuoc chuoi giai doan
special:
  rate_limited:   "Đang chờ lượt gọi mô hình, khoảng {wait_s} giây"
  repairing:      "Truy vấn chưa đúng, đang sửa lại (lần {attempt}/3)"
  regenerating:   "Kết quả chưa đạt kiểm chứng, đang viết lại"
  cache_hit:      "Dùng lại kết quả đã tính"
  degraded_llm:   "Mô hình tạm không phản hồi — hiển thị số liệu dạng rút gọn"
```

Thanh tiến trình tính từ `weight` cộng dồn, nên nó **không giật** khi một giai đoạn dài (`narrating`, weight 6) đang chạy.

## 15.3 Bảng sự kiện SSE

```
POST /api/chat
Accept: text/event-stream
```

| `event` | Khi nào | `data` |
|---|---|---|
| `stage` | Vào một giai đoạn mới | `{stage, label, progress, elapsed_ms}` |
| `plan` | Sau PLAN — cho người dùng thấy sẽ tính gì | `{metrics:[...], filters:[...], date_range:{...}}` |
| `evidence` | Sau COMPUTE — số liệu đã có, **trước cả khi LLM viết** | `{facts:[{fact_id,title,row_count}], data_version}` |
| `table` | Bảng số hiển thị được ngay | `{fact_id, columns, rows}` |
| `chart` | Cấu hình biểu đồ | `{fact_id, type, option}` |
| `block` | Một khối markdown **đã thay thế thẻ và đã kiểm chứng** | `{seq, md, verified, numbers:{ok,total}}` |
| `warning` | Khối không qua kiểm chứng, hoặc cảnh báo cỡ mẫu | `{level, code, message}` |
| `verified` | Sau VERIFY — kết quả tổng hợp L0–L4 | `{trust, band, checks:{...}}` |
| `judge` | **Sau `done`** — L5 chạy bất đồng bộ xong | `{entailment_rate, contradiction_rate, trust, band}` |
| `artifact` | File xuất ra | `{kind:"csv", url, filename, rows}` |
| `done` | Kết thúc | `{trace_id, decision, latency_ms, llm_calls}` |
| `error` | Lỗi không phục hồi được | `{code, message, retryable}` |
| `:` (comment) | Keep-alive mỗi 15 giây | — |

### Một phiên đầy đủ

```
event: stage
data: {"stage":"intake","label":"Đang đọc câu hỏi","progress":0.05,"elapsed_ms":12}

event: stage
data: {"stage":"routing","label":"Đang xác định loại phân tích","progress":0.12,"elapsed_ms":40}

event: stage
data: {"stage":"computing","label":"Đang phân rã chi phí và phễu của chiến dịch","progress":0.28,"elapsed_ms":900}

event: plan
data: {"metrics":["romi","net_profit","acquisition_spend","approval_rate"],
       "filters":[{"dimension":"campaign_id","op":"eq","value":"CMP-PTN-BRK01"}],
       "date_range":{"from":"2026-08-01","to":"2026-08-31"}}

event: evidence
data: {"facts":[{"fact_id":"F1","title":"Hiệu quả chiến dịch","row_count":1},
                {"fact_id":"F2","title":"Phễu","row_count":1},
                {"fact_id":"F3","title":"Phân rã chi phí","row_count":8}],
       "data_version":"etl_run_42"}

event: table
data: {"fact_id":"F3","columns":[...],"rows":[...]}

event: stage
data: {"stage":"analyzing","label":"Đang kiểm định thống kê","progress":0.45,"elapsed_ms":1400}

event: stage
data: {"stage":"narrating","label":"Đang viết chẩn đoán","progress":0.55,"elapsed_ms":1600}

event: block
data: {"seq":1,"md":"### Kết luận","verified":true,"numbers":{"ok":0,"total":0}}

event: block
data: {"seq":2,"md":"Chiến dịch đang lỗ **66.794.870 VND** với ROMI **-1,85**, thấp hơn hẳn mức trung vị 1,31 của các chiến dịch cùng sản phẩm.","verified":true,"numbers":{"ok":3,"total":3}}

event: block
data: {"seq":3,"md":"### Phễu","verified":true,"numbers":{"ok":0,"total":0}}

event: block
data: {"seq":4,"md":"Tỷ lệ lead thành hồ sơ đạt **29,9%** — cao so với mặt bằng...","verified":true,"numbers":{"ok":2,"total":2}}

event: stage
data: {"stage":"verifying","label":"Đang đối chiếu số liệu với nguồn","progress":0.90,"elapsed_ms":5200}

event: verified
data: {"trust":0.94,"band":"PASS",
       "checks":{"numeric_grounding":1.0,"entity_grounding":1.0,"stats_guard":1.0,"judge":"pending"}}

event: done
data: {"trace_id":"8f14e45f-...","decision":"ANSWERED","latency_ms":5400,"llm_calls":2}

event: judge
data: {"entailment_rate":0.92,"contradiction_rate":0.0,"trust":0.95,"band":"PASS"}
```

Chú ý thứ tự: **`evidence` và `table` đến trước `block`**. Người dùng thấy bảng số **trước khi** LLM viết xong câu nào. Đó là hệ quả trực tiếp của nguyên tắc "code tính toán, LLM diễn giải" — số liệu có sẵn từ giây thứ nhất, phần chữ chỉ là lớp phủ lên trên. Nếu LLM chết giữa chừng, người dùng vẫn có số.

## 15.4 Bộ đệm streaming có kiểm chứng

```python
# app/agent/streaming.py

FLUSH_ON = ("\n\n", "\n### ", "\n## ", "\n- ", "\n* ", "\n1. ")

class StreamingVerifier:
    """Gom token thanh khoi markdown hoan chinh, thay the the, kiem chung,
    roi moi phat ra. Khong bao gio de lot mot the chua phan giai len man hinh."""

    def __init__(self, evidence: EvidenceSet, catalog: Catalog,
                 policy: NumericPolicy, max_block_chars: int = 600):
        self._buf: str = ""
        self._seq: int = 0
        self._blocks: list[VerifiedBlock] = []

    def feed(self, token: str) -> Iterator[BlockEvent]:
        """Nap mot token. Sinh ra 0..n BlockEvent."""
        self._buf += token
        while (cut := self._find_safe_cut()) is not None:
            yield self._emit(self._buf[:cut])
            self._buf = self._buf[cut:]

    def finish(self) -> Iterator[BlockEvent]:
        """Goi khi LLM stream xong. Day not phan con lai."""
        if self._buf.strip():
            yield self._emit(self._buf)
        self._buf = ""

    # ---- noi bo ----
    def _find_safe_cut(self) -> int | None:
        """Tra ve vi tri cat AN TOAN, hoac None neu chua the cat.
        KHONG an toan khi dang o giua mot the: co '{{' chua dong '}}'."""
        if self._has_open_tag():
            # Van cat duoc neu diem cat nam TRUOC the dang mo
            open_at = self._buf.rfind("{{")
            region = self._buf[:open_at]
        else:
            region = self._buf
        best = max((region.rfind(m) for m in FLUSH_ON), default=-1)
        if best >= 0:
            return best + 1
        # Khoi qua dai ma khong co ranh gioi -> cat o khoang trang gan nhat
        if len(region) > self.max_block_chars:
            return region.rfind(" ", 0, self.max_block_chars) or None
        return None

    def _has_open_tag(self) -> bool:
        o, c = self._buf.rfind("{{"), self._buf.rfind("}}")
        return o > c

    def _emit(self, raw: str) -> BlockEvent:
        md, unresolved = self.evidence.substitute(raw)          # thay the -> so that
        num = check_numeric_grounding(md, self.evidence, self.policy)
        ent = check_entity_grounding(md, self.evidence, self.catalog)
        ok  = not unresolved and num.passed and ent.passed
        self._seq += 1
        blk = VerifiedBlock(seq=self._seq, md=md if ok else None, raw=raw,
                            verified=ok, numeric=num, entity=ent,
                            unresolved_tags=unresolved)
        self._blocks.append(blk)
        return BlockEvent.from_block(blk)
```

Khi một khối **không** qua kiểm chứng, client nhận `block` với `verified: false` và nội dung bị giữ lại; kèm theo là một `warning`:

```
event: block
data: {"seq":5,"md":null,"verified":false,
       "reason":"unresolved_tag","detail":["F9.r1.romi"]}

event: warning
data: {"level":"block","code":"NUMERIC_UNGROUNDED",
       "message":"Một đoạn phân tích tham chiếu số liệu không có trong kết quả truy vấn nên đã được giữ lại."}
```

UI hiển thị chỗ đó bằng một ô xám: *"Đoạn này bị giữ lại vì không đối chiếu được với dữ liệu nguồn."* kèm nút xem bảng số thô. **Không bao giờ hiện nội dung chưa kiểm chứng rồi mới rút lại** — rút lại sau khi người dùng đã đọc là quá muộn.

Một chi tiết trong `_find_safe_cut` đáng chú ý: khi buffer đang có thẻ mở dở, ta vẫn tìm điểm cắt trong **phần trước thẻ đó**. Nhờ vậy một thẻ đang viết dở không chặn cả luồng — đoạn văn phía trước vẫn chảy ra bình thường.

## 15.5 Streaming cho dashboard

Ba tab dashboard không gọi LLM, nhưng ETL nặng hoặc DB xa vẫn có thể mất 1–2 giây. Có hai đường, dùng cho hai tình huống khác nhau:

**Khi người dùng mở tab** → `GET /api/dashboard/*` trả JSON bình thường, UI hiện **skeleton loader** kèm dòng chữ lấy từ `config/stages.yaml`:

```
+--------------------------------+
|  Đang tạo dashboard...          |
|  [====----------]  Đang truy vấn 15 chỉ số |
|  ████░░░░  ████░░░░  ████░░░░  |   <- skeleton the KPI
+--------------------------------+
```

**Khi người dùng gõ trong chat "tạo dashboard cho tôi"** → đi qua `/api/chat` như mọi câu hỏi khác, với playbook `campaign_overview`. Chuỗi sự kiện:

```
event: stage
data: {"stage":"computing","label":"Đang tạo dashboard hiệu quả chiến dịch","progress":0.28}

event: chart
data: {"fact_id":"F1","type":"bar","option":{...}}     <- bieu do hien ngay trong khung chat

event: table
data: {"fact_id":"F1","columns":[...],"rows":[...]}

event: stage
data: {"stage":"narrating","label":"Đang tóm tắt kết quả từng chiến dịch","progress":0.55}

event: block
data: {"seq":1,"md":"Trong 6 chiến dịch, **2** đang lỗ...","verified":true}
```

Tức là dashboard sinh ra **ngay trong dòng hội thoại**, không phải chuyển tab. Đây là hành vi mà yêu cầu gốc mô tả: hỏi tạo dashboard thì trả lời "đang tạo dashboard" rồi dựng nó ra.

Vì tab dashboard không gọi LLM, `progress` ở đây chạy rất nhanh — thường xong trong dưới 1,5 giây.

## 15.6 Bốn tình huống đặc biệt

### Bị giới hạn tốc độ gọi model

Trần MaaS là 10 request/phút cho cả tài khoản ([04](04-architecture.md) §4.5). Khi token bucket cạn, **không** im lặng chờ:

```
event: stage
data: {"stage":"narrating","label":"Đang chờ lượt gọi mô hình, khoảng 7 giây","progress":0.55,"waiting":true}
```

Client hiện đồng hồ đếm ngược. Quan trọng: **bảng số và biểu đồ đã gửi trước đó rồi**, nên người dùng có cái để đọc trong lúc chờ.

### Model không phản hồi

Chuyển sang chế độ template: số liệu vẫn đầy đủ, phần diễn giải dùng văn bản mẫu điền số.

```
event: warning
data: {"level":"session","code":"LLM_UNAVAILABLE",
       "message":"Mô hình tạm không phản hồi — hiển thị số liệu dạng rút gọn."}

event: block
data: {"seq":1,"md":"**2/6 chiến dịch đang lỗ:** Broker Network (-66.794.870 VND, ROMI -1,85) và Momo (-17.529.770 VND, ROMI -0,41).","verified":true,"source":"template"}
```

### Người dùng huỷ giữa chừng

Client đóng kết nối → `request.is_disconnected()` → huỷ task LLM, đóng cursor DB, ghi `agent_trace` với `decision = "CANCELLED"`. Không để một lượt gọi LLM mồ côi tiếp tục đốt quota.

```python
async def event_generator(request: Request, state: AgentState):
    try:
        async for ev in orchestrator.answer_stream(state):
            if await request.is_disconnected():
                raise asyncio.CancelledError
            yield ev.to_sse()
    except asyncio.CancelledError:
        await trace_store.save(state, decision=Decision.CANCELLED)
        raise
    finally:
        await state.release_resources()
```

### Phải viết lại vì không qua kiểm chứng

Nếu quá nhiều khối bị chặn, orchestrator sinh lại **một lần** với ràng buộc chặt hơn. Người dùng thấy rõ điều đó chứ không thấy màn hình đứng im:

```
event: warning
data: {"level":"answer","code":"REGENERATING",
       "message":"Kết quả chưa đạt kiểm chứng, đang viết lại."}

event: stage
data: {"stage":"narrating","label":"Đang viết phân tích (lần 2)","progress":0.55}
```

Các khối của lần một bị xoá khỏi UI. Lần hai vẫn fail → `decision = ABSTAIN`, chỉ hiện bảng số thô.

## 15.7 Phía client

```javascript
// app/web/static/chat.js  (rut gon)
async function ask(question, history) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json", "Accept": "text/event-stream"},
    body: JSON.stringify({message: question, history}),
    signal: state.abort.signal,
  });

  const msg = appendAssistantMessage();          // khung rong + thanh tien trinh

  for await (const ev of parseSSE(res.body)) {
    switch (ev.event) {
      case "stage":
        msg.setStage(ev.data.label, ev.data.progress, ev.data.waiting);
        break;
      case "plan":
        msg.setPlan(ev.data);                    // "Se tinh: ROMI, loi nhuan rong..."
        break;
      case "evidence":
        msg.setEvidenceSummary(ev.data.facts);   // "3 bang du lieu"
        break;
      case "table":  msg.appendTable(ev.data);  break;
      case "chart":  msg.appendChart(ev.data);  break;   // ECharts render ngay
      case "block":
        ev.data.verified ? msg.appendBlock(ev.data.md)
                         : msg.appendBlockedBlock(ev.data.reason);
        break;
      case "warning":  msg.addWarning(ev.data);        break;
      case "verified": msg.setTrustBadge(ev.data);     break;
      case "judge":    msg.updateTrustBadge(ev.data);  break;   // den SAU done
      case "artifact": msg.addDownload(ev.data);       break;
      case "done":     msg.finalize(ev.data);          break;
      case "error":    msg.showError(ev.data);         break;
    }
    scrollToBottomIfPinned();     // chi cuon neu nguoi dung dang o day
  }
}
```

Bốn chi tiết UX dễ bỏ sót nhưng ảnh hưởng lớn:

1. **Chỉ tự cuộn khi người dùng đang ở đáy.** Nếu họ đang cuộn lên đọc lại, kéo màn hình xuống là hành vi khó chịu nhất mà một chat UI có thể làm.
2. **Thanh tiến trình chạy theo `weight` cộng dồn**, không nhảy cóc từ 12% lên 90%.
3. **`judge` đến sau `done`** — huy hiệu Trust phải cập nhật tại chỗ mà không làm giật bố cục. Dành sẵn chỗ cho huy hiệu từ đầu.
4. **Nút Dừng** luôn hiện trong lúc stream, gọi `state.abort.abort()`. Liên quan trực tiếp tới việc tiết kiệm quota.

Ràng buộc chat 60% ở [09](09-api-ui.md) §9.4 vẫn giữ nguyên: vùng cuộn có `max-height: 60vh`, và nội dung stream vào đúng vùng đó.

## 15.8 Giữ kết nối sống

| Vấn đề | Xử lý |
|---|---|
| Proxy đóng kết nối idle | Gửi dòng comment `:keepalive` mỗi 15 giây |
| Proxy gom buffer làm mất tính real-time | Header `X-Accel-Buffering: no` và `Cache-Control: no-cache` |
| Mất mạng giữa chừng | Mỗi sự kiện có `id:` tăng dần; client gửi lại `Last-Event-ID` để nhận tiếp từ `ops.stream_buffer` |
| Nhiều replica trên AgentBase | Stream là kết nối bám một replica; không dùng bộ nhớ process cho state, chỉ dùng `ops.*` |

```python
return EventSourceResponse(
    event_generator(request, state),
    ping=15,
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
             "Connection": "keep-alive"},
)
```

## 15.9 Hợp đồng không streaming vẫn giữ nguyên

`POST /invocations` (cổng cho Zalo và API ngoài) **không** streaming — nó chạy cùng pipeline rồi trả một JSON đầy đủ, kèm thêm trường `stages` để client biết đã qua những bước nào:

```jsonc
{
  "trace_id": "...",
  "answer_markdown": "### Kết luận\n...",
  "trust": { "score": 0.94, "band": "PASS" },
  "evidence": [...],
  "stages": [
    {"stage":"computing","label":"Đang phân rã chi phí...","duration_ms":860},
    {"stage":"narrating","label":"Đang viết chẩn đoán","duration_ms":3100},
    {"stage":"verifying","label":"Đang đối chiếu số liệu","duration_ms":40}
  ],
  "meta": { "llm_calls": 2, "latency_ms": 5400 }
}
```

Cùng một `Orchestrator`, hai lối ra: `answer()` gom hết rồi trả, `answer_stream()` phát sự kiện. Không có hai đường code nghiệp vụ song song — đó là điều kiện để hành vi hai bên không trôi lệch theo thời gian.

## 15.10 Kiểm thử

| Test | Khẳng định điều gì |
|---|---|
| `test_streaming_never_leaks_tags` | Sinh 500 chuỗi token ngẫu nhiên cắt thẻ ở mọi vị trí; **không `block.md` nào chứa `{{` hoặc `}}`** |
| `test_streaming_blocks_ungrounded` | Narrator giả bịa một `fact_id` → khối đó có `verified=false`, `md=null` |
| `test_stage_labels_from_config` | Đổi `config/stages.yaml`, reload, nhãn đổi theo — không cần restart |
| `test_playbook_override_label` | Playbook `campaign_overview` phải phát nhãn "Đang tạo dashboard hiệu quả chiến dịch" |
| `test_progress_monotonic` | `progress` không bao giờ giảm, kết thúc ở 1,0 |
| `test_cancel_releases_resources` | Client ngắt → task LLM bị huỷ, trace ghi `CANCELLED` |
| `test_sse_keepalive` | Có comment keep-alive khi im lặng > 15s |
| `test_invocations_matches_stream` | Cùng câu hỏi, `answer()` và `answer_stream()` ghép lại cho **cùng một markdown** |

Test cuối cùng là cái quan trọng nhất: nó ngăn hai lối ra trôi lệch — một lỗi rất dễ xảy ra và rất khó phát hiện bằng mắt.
