# 07 — Prompt, few-shot và cách sửa nội dung phân tích

> Yêu cầu gốc: *"Nội dung phân tích, tôi muốn có thể chỉnh sửa sau."* Tài liệu này mô tả cơ chế để một người không biết code vẫn đổi được giọng văn, cấu trúc báo cáo, tiêu chí đánh giá và ví dụ mẫu — mà không cần build lại, không cần deploy lại.

## 7.1 Bốn tầng có thể sửa

Cần phân biệt rõ, vì người dùng hay nhầm "sửa prompt" với "sửa mọi thứ":

| Tầng | File | Sửa được gì | Ai sửa |
|---|---|---|---|
| **T1 — Định nghĩa chỉ số** | `config/semantic/metrics.yml` | ROMI tính thế nào, ngưỡng cảnh báo, chú thích bắt buộc | Data analyst |
| **T2 — Cấu trúc báo cáo** | `config/playbooks/*.yml` | Câu trả lời gồm mục nào, mỗi mục lấy chỉ số nào, theo thứ tự nào | Business analyst |
| **T3 — Giọng văn & hướng dẫn** | `prompts/*.yaml` | System prompt, hướng dẫn viết, few-shot, độ dài | Marketing lead |
| **T4 — Ngưỡng kiểm chứng** | `config/verify.yaml` | Khi nào chặn, khi nào cảnh báo, cỡ mẫu tối thiểu | AI engineer |

Sửa T3 đổi **cách nói**. Sửa T2 đổi **nói về cái gì**. Sửa T1 đổi **con số**. Ba việc khác nhau, ba file khác nhau — cố tình như vậy, để một người sửa văn phong không vô tình làm sai số liệu.

## 7.2 Định dạng file prompt

Mỗi prompt là một file YAML độc lập trong `prompts/`. Một file, một nhiệm vụ.

```yaml
# prompts/narrate_campaign_diagnosis.yaml
id: narrate_campaign_diagnosis
version: "2.1.0"
description_vi: "Viết phần diễn giải cho chẩn đoán một chiến dịch"
model_role: narrator
engine: jinja2

params:
  temperature: 0.2
  max_tokens: 1200
  top_p: 0.9

system: |
  Bạn là chuyên gia phân tích marketing của một công ty cho vay tiêu dùng số.
  Bạn viết cho Trưởng phòng Digital Marketing — người bận, đọc nhanh, và sẽ
  chất vấn bất kỳ con số nào trông lạ.

  QUY TẮC TUYỆT ĐỐI:
  1. Bạn KHÔNG được viết bất kỳ chữ số nào. Mọi con số phải viết dưới dạng thẻ
     {{fact_id}} lấy từ EVIDENCE. Ví dụ đúng: "ROMI đạt {{F1.r1.romi}}".
     Ví dụ SAI: "ROMI đạt 6,20".
  2. Bạn chỉ được dùng các fact_id có trong EVIDENCE. Bịa fact_id sẽ bị chặn.
  3. Nếu EVIDENCE không chứa thông tin để trả lời một ý, hãy viết thẳng
     "dữ liệu hiện có chưa trả lời được điều này" thay vì suy đoán.
  4. Không dùng từ chỉ nhân quả ("vì", "do", "dẫn đến", "khiến cho") giữa hai
     chỉ số trừ khi EVIDENCE có mục causal_evidence. Dùng từ chỉ tương quan
     ("đi cùng với", "tương quan với", "song hành").
  5. Nếu một so sánh có cờ significant = false, phải viết rõ rằng chênh lệch
     nằm trong sai số thống kê. Không được gọi đó là "cao hơn" hay "tốt hơn".
  6. Mọi chú thích trong EVIDENCE.caveats phải được nhắc lại ít nhất một lần.

instructions: |
  Viết bằng tiếng Việt, {{ tone }}, tối đa {{ max_words }} từ.
  Cấu trúc theo đúng thứ tự các mục sau, mỗi mục một tiêu đề `###`:
  {% for s in sections %}
  - {{ s.label_vi }}
  {% endfor %}

  Mục "Kết luận" phải nằm đầu tiên và dài tối đa 3 câu: chiến dịch này lãi hay
  lỗ, mức độ, và nguyên nhân lớn nhất.

  Kết thúc bằng một mục "### Đề xuất" gồm tối đa 3 gạch đầu dòng, mỗi gạch nêu
  một hành động cụ thể kèm chỉ số kỳ vọng thay đổi.

few_shots:
  - name: "Chiến dịch lỗ vì phí đối tác"
    evidence: |
      F1.r1.campaign_name = "Vay Tieu Dung - Broker Network"
      F1.r1.romi = -1.85        F1.r1.net_profit = -66794870
      F2.r1.approval_rate = 0.488   F2.r1.lead_to_application_rate = 0.299
      F3.r1.partner_fee = 168974100 F3.r1.partner_fee_share = 0.34
      F4.r1.romi_benchmark_median = 1.31
      caveats = ["Tỷ lệ lead thành hồ sơ là tỷ lệ tổng hợp mức chiến dịch,
                  không phải attribution từng lead."]
    output: |
      ### Kết luận
      Chiến dịch đang lỗ {{F1.r1.net_profit}} VND với ROMI {{F1.r1.romi}}, thấp
      hơn hẳn mức trung vị {{F4.r1.romi_benchmark_median}} của các chiến dịch
      cùng sản phẩm. Nguyên nhân lớn nhất nằm ở phí đối tác, chiếm
      {{F3.r1.partner_fee_share}} tổng chi phí.

      ### Phễu
      Tỷ lệ lead thành hồ sơ đạt {{F2.r1.lead_to_application_rate}} — cao so với
      mặt bằng, nên vấn đề không nằm ở chất lượng lead đầu vào. Nút thắt ở bước
      duyệt: chỉ {{F2.r1.approval_rate}} hồ sơ được giải ngân. Lưu ý rằng tỷ lệ
      lead thành hồ sơ ở đây là tỷ lệ tổng hợp mức chiến dịch, không phải
      attribution từng lead.

      ### Đề xuất
      - Đàm phán lại phí đối tác hoặc chuyển sang mô hình trả theo khoản giải ngân
        thay vì theo lead — mục tiêu đưa ROMI về dương.
      - Chia sẻ tiêu chí thẩm định với đối tác để giảm hồ sơ trượt ngay từ đầu vào.

  - name: "Chênh lệch không có ý nghĩa thống kê"
    evidence: |
      F1.r1.occupation = "Freelancer"  F1.r1.avg_profit = 220200  F1.r1._n_rows = 375
      F1.r2.occupation = "Noi tro"     F1.r2.avg_profit = 184332  F1.r2._n_rows = 359
      stats.compare = { significant: false, p_value: 0.51, effect_size: 0.05 }
    output: |
      ### Kết luận
      Không có khác biệt đáng kể về lợi nhuận trung bình giữa các nhóm nghề
      nghiệp. Nhóm Freelancer đạt {{F1.r1.avg_profit}} VND và nhóm Nội trợ đạt
      {{F1.r2.avg_profit}} VND, nhưng chênh lệch này nằm trong sai số thống kê
      (p = {{stats.p_value}}) nên không dùng để phân bổ ngân sách được.
      Nên phân khúc theo thu nhập hoặc mức độ dùng app — hai chiều đó thực sự
      phân hoá.

  - name: "Không đủ dữ liệu"
    evidence: |
      F1.rows = []
      note = "Khong co ho so nao trong khoang thoi gian yeu cau"
    output: |
      ### Kết luận
      Không có hồ sơ nào trong khoảng thời gian được hỏi, nên chưa thể đánh giá.
      Dữ liệu giao dịch hiện có nằm trong tháng 8/2026. Bạn muốn xem kỳ đó không?

output_contract:
  format: markdown
  must_start_with: "### Kết luận"
  max_words: 400
  forbidden_patterns:
    - '\d'                      # khong duoc co chu so tran
    - '(?i)\b(chắc chắn|rõ ràng là|không thể chối cãi)\b'
```

### Vì sao ba few-shot, và vì sao đúng ba cái này

Nghiên cứu về LLM-as-a-judge của AWS chỉ ra rằng few-shot là phần **chịu tải** của prompt: chúng neo thang đo. Ba ví dụ ở đây được chọn để dạy ba hành vi khác nhau, và cả ba đều lấy từ chính dữ liệu thật:

1. **Ví dụ 1** dạy cách viết khi có tín hiệu mạnh và rõ — định dạng chuẩn, dùng thẻ, nhắc caveat.
2. **Ví dụ 2** dạy hành vi khó nhất: **kiềm chế khi chênh lệch là nhiễu**. Không có ví dụ này, model sẽ tuyên bố Freelancer là nhóm tốt nhất. Đây là bài học đắt nhất trong bộ dữ liệu.
3. **Ví dụ 3** dạy cách abstain một cách hữu ích, kèm gợi ý đường đi tiếp.

Khi thêm few-shot mới, giữ nguyên tắc: **mỗi ví dụ dạy một hành vi, và ưu tiên hành vi khó hơn hành vi dễ**. Mười ví dụ "trả lời đẹp" kém giá trị hơn một ví dụ "biết im lặng đúng lúc".

## 7.3 Danh mục file prompt

| File | Vai trò | Gọi khi nào |
|---|---|---|
| `route_intent.yaml` | Phân loại intent + trích entity | Mỗi câu hỏi chat (bỏ qua nếu khớp luật) |
| `narrate_campaign_overview.yaml` | Tổng quan nhiều chiến dịch | D1 |
| `narrate_campaign_diagnosis.yaml` | Chẩn đoán một chiến dịch | D1 |
| `narrate_funnel.yaml` | Phân tích phễu | D1 |
| `narrate_persona.yaml` | Chân dung phân khúc | D2 |
| `narrate_clv_actions.yaml` | Khuyến nghị hành động | D3 |
| `judge_grounding.yaml` | LLM-as-a-judge chấm mức bám bằng chứng | Lớp L5 |
| `clarify_question.yaml` | Hỏi lại khi mơ hồ | Khi abstain vì mơ hồ |
| `refuse_out_of_scope.yaml` | Từ chối lịch sự | Intent ngoài phạm vi |

### Prompt của bộ chấm điểm

Theo đúng cấu trúc mà AWS khuyến nghị: *system → task → định dạng đầu ra → quy tắc chấm → few-shot → ràng buộc đầu ra*, chạy ở `temperature = 0`, `max_tokens` nhỏ.

```yaml
# prompts/judge_grounding.yaml
id: judge_grounding
version: "1.0.0"
params: { temperature: 0.0, max_tokens: 200 }

system: |
  Bạn là chuyên gia kiểm tra xem các phát biểu có dựa trên bằng chứng hay không.

instructions: |
  Đọc EVIDENCE và STATEMENT. Với mỗi câu trong STATEMENT, xác định câu đó
  có được EVIDENCE chống đỡ trực tiếp hay không.

  Trả về DUY NHẤT một object JSON:
  {"claims": [{"text": "...", "label": "SUPPORTED|CONTRADICTED|NOT_ENOUGH_INFO",
               "evidence_ref": "F1.r1.romi hoặc null"}],
   "grounding_score": <float 0..1>}

  Quy tắc chấm grounding_score:
  - Đặt 1.0 nếu mọi câu đều dựa trực tiếp vào EVIDENCE.
  - Đặt 0.0 nếu có ít nhất một câu MÂU THUẪN với EVIDENCE.
  - Ở giữa: tỷ lệ số câu SUPPORTED trên tổng số câu.
  - Câu diễn đạt lại nguyên văn con số trong EVIDENCE luôn là SUPPORTED.
  - Câu suy luận nhân quả mà EVIDENCE chỉ có tương quan là NOT_ENOUGH_INFO.

  Không xuất bất kỳ thông tin nào khác ngoài JSON.

few_shots:
  - evidence: "F1.r1.romi = 6.20 ; F1.r2.romi = 1.60"
    statement: "Chiến dịch Zalo đạt ROMI 6,20, cao hơn Google ở mức 1,60."
    output: '{"claims":[{"text":"...","label":"SUPPORTED","evidence_ref":"F1.r1.romi"}],"grounding_score":1.0}'
  - evidence: "F1.r1.romi = 6.20"
    statement: "Zalo hiệu quả vì nhắm đúng khách hàng có nhu cầu thực."
    output: '{"claims":[{"text":"...","label":"NOT_ENOUGH_INFO","evidence_ref":null}],"grounding_score":0.0}'
  - evidence: "F1.r1.approval_rate = 0.488"
    statement: "Tỷ lệ duyệt đạt 72%."
    output: '{"claims":[{"text":"...","label":"CONTRADICTED","evidence_ref":"F1.r1.approval_rate"}],"grounding_score":0.0}'
```

Ba ví dụ phủ ba nhãn — quan trọng hơn số lượng. Ngưỡng chặn **không** được lấy từ tài liệu nào; nó phải được hiệu chỉnh trên golden set của chính dự án này (xem [13](13-testing-eval.md) §5). Bất kỳ ai đưa ra con số "dùng 0.7" là đang trích ví dụ trong tài liệu của người khác, không phải một khuyến nghị đã kiểm chứng.

## 7.4 Bộ nạp prompt

```python
class PromptLoader:
    def __init__(self, root: Path, watch: bool = True): ...

    def get(self, prompt_id: str) -> Prompt:
        """Tra ve prompt da parse. Kiem tra mtime, tu nap lai neu file doi."""

    def render(self, prompt_id: str, **ctx) -> RenderedPrompt:
        """Render Jinja2 -> messages OpenAI + params + version."""

    def validate(self, prompt_id: str) -> list[ValidationError]:
        """Kiem tra truoc khi luu: bien Jinja co ton tai, few-shot co du field,
        output_contract co parse duoc, forbidden_patterns co compile duoc."""
```

Hành vi hot-reload: mỗi lần render kiểm tra `mtime`. Đổi thì parse lại. Parse lỗi thì **giữ nguyên bản đang chạy** và ghi log lỗi — một file YAML hỏng không bao giờ được làm sập agent đang phục vụ.

`RenderedPrompt.version` đi thẳng vào `ops.agent_trace.prompt_version`. Không có nó thì khi chất lượng tụt sau một lần sửa prompt, không ai truy được.

## 7.5 Trang admin sửa prompt

`GET /admin/prompts` — danh sách prompt kèm version và lần sửa cuối.
`GET /admin/prompts/{id}` — trình soạn thảo:

```
+----------------------------------------------------------------+
| prompts/narrate_campaign_diagnosis.yaml        v2.1.0          |
+---------------------------+------------------------------------+
|                           |                                    |
|  [ YAML editor           ]|  Xem truoc                         |
|                           |  +------------------------------+  |
|  system: |                |  | Cau hoi thu:                 |  |
|    Ban la chuyen gia...   |  | [Vi sao Broker Network lo?]  |  |
|                           |  |                              |  |
|  few_shots:               |  | [ Chay thu ]                 |  |
|    - name: ...            |  |                              |  |
|                           |  | Ket qua:                     |  |
|                           |  | ### Ket luan                 |  |
|                           |  | Chien dich dang lo ...       |  |
|                           |  |                              |  |
|                           |  | Trust: 0.94  Numeric: 8/8    |  |
|                           |  +------------------------------+  |
+---------------------------+------------------------------------+
| [ Kiem tra ]  [ Chay golden set ]  [ Luu -> v2.2.0 ]  [ Khoi phuc ] |
+----------------------------------------------------------------+
```

Luồng lưu, có rào:

1. **Kiểm tra** — schema YAML, biến Jinja, hợp đồng đầu ra. Fail thì không cho lưu.
2. **Chạy thử** — một câu hỏi mẫu, hiện luôn Trust Score. Người sửa thấy ngay hậu quả.
3. **Chạy golden set** (tuỳ chọn nhưng nên) — 20 câu nhanh. Nếu `numeric_grounding_rate` tụt dưới 1,0 thì **cảnh báo đỏ**, phải xác nhận mới lưu được.
4. **Lưu** — tăng patch version, ghi bản cũ vào `ops.prompt_history`, các replica nạp lại trong 5 giây.
5. **Khôi phục** — quay về bất kỳ version nào trong lịch sử, một cú bấm.

Khác biệt giữa T1 và T3 thể hiện ở đây: sửa prompt có thể làm câu trả lời **xấu đi**, nhưng không thể làm **con số sai** — vì con số đến từ semantic layer và được kiểm chứng ở tầng render. Đó là lý do trao quyền sửa prompt cho business user là an toàn.

## 7.6 Lưu prompt ở đâu khi chạy nhiều replica

Filesystem container là ephemeral, nên sửa qua trang admin không thể chỉ ghi xuống đĩa.

```
Khoi dong:  doc prompts/*.yaml tu image  -> nap vao bo nho
            doc ops.prompt_override tu DB -> de chong len neu co
Sua qua UI: ghi vao ops.prompt_override (co version, co tac gia, co thoi diem)
Cac replica: poll ops.prompt_override moi 5 giay theo updated_at
Deploy moi:  file trong image la baseline; override trong DB van thang
             -> nut "Xoa override" tren UI de quay ve baseline cua image
```

```sql
CREATE TABLE ops.prompt_override (
    prompt_id   TEXT PRIMARY KEY,
    version     TEXT        NOT NULL,
    content     TEXT        NOT NULL,   -- YAML day du
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  TEXT
);
CREATE TABLE ops.prompt_history (
    id          BIGSERIAL PRIMARY KEY,
    prompt_id   TEXT NOT NULL,
    version     TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  TEXT
);
```

Với PoC chỉ chạy 1 replica, đọc thẳng từ đĩa cũng đủ. Nhưng bảng `prompt_history` nên có ngay từ đầu — giá trị lớn nhất của nó là nút "khôi phục" lúc 11 giờ đêm trước ngày demo.

## 7.7 Chỗ nào KHÔNG được biến thành prompt

Ranh giới cần giữ, nếu không toàn bộ thiết kế chống hallucination sẽ bị rò:

| Không bao giờ nằm trong prompt | Nằm ở đâu | Vì sao |
|---|---|---|
| Công thức tính chỉ số | `metrics.yml` → SQL | LLM không được tính số |
| Ngưỡng chặn/cảnh báo của bộ kiểm chứng | `config/verify.yaml` | Prompt không được tự nới rào của chính nó |
| Cỡ mẫu tối thiểu | `metrics.yml` + `verify.yaml` | Là quy tắc thống kê, không phải giọng văn |
| Chuỗi kết nối DB, API key | `config/secrets.yaml` | Bảo mật |
| Danh sách bảng/cột thật | `semantic/entities.yml` | Đưa schema thô vào prompt là mời viết SQL tự do |

Một quy tắc để nhớ: **prompt điều khiển ngôn ngữ, config điều khiển sự thật.**
