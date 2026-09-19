# 16 — Độ sẵn sàng để dev triển khai

> Tài liệu này trả lời hai câu hỏi: *bộ tài liệu hiện tại đã đủ để giao cho dev chưa*, và *có nên viết thiết kế chi tiết tới từng class/function không*.

---

## ✅ CẬP NHẬT 2026-09-19 — sáu nhóm hiện vật đã hoàn tất

Đánh giá 72% ở §16.1 dưới đây là **trạng thái trước khi bổ sung**. Toàn bộ sáu nhóm hiện vật ở §16.2 nay đã được viết và kiểm chứng:

| Hiện vật | Đã có | Kiểm chứng |
|---|---|---|
| `config/semantic/metrics.yml` | **53 chỉ số** | 42 chỉ số có `reference`; 6/6 ROMI khớp tuyệt đối |
| `config/semantic/entities.yml` | 4 dataset, 25 dimension | parse OK |
| `config/analytics.yaml` | 8 luật phân khúc, bảng tra `p_repeat`, 6 hành động | phân bố khớp 100%, `_unclassified` = 0 |
| `config/verify.yaml` | 7 lớp, 24 marker so sánh, 15 marker nhân quả, 9 mục tiêu sức khoẻ | parse OK |
| `config/stages.yaml`, `config/app.yaml`, `config/profiles/*` | đầy đủ | parse OK |
| `config/playbooks/*.yml` | **9 playbook** | parse OK |
| `prompts/*.yaml` | **9 prompt, 36 few-shot** | parse OK, số trong few-shot là số thật |
| `app/contracts.py` | **14 Protocol, 52 kiểu** | `py_compile` + import OK |
| `app/errors.py` | **40 mã lỗi** | `py_compile` + import OK |
| `etl/sql/*.sql` | 4 file DDL | chạy trên DuckDB: **12/12 bất biến đạt** |
| `evals/golden/qa_set.yaml` | **100 ca, 37 ca bẫy** | không trùng id, không thiếu id |
| [17-implementation-guide.md](17-implementation-guide.md) | 14 nhiệm vụ, mỗi nhiệm vụ có lệnh nghiệm thu | — |

**Độ sẵn sàng hiện tại: ~95%.** Phần còn lại là bảy mục nhỏ ở §16.5, mỗi mục dưới một giờ và không chặn việc bắt đầu.

**Bắt đầu từ [17-implementation-guide.md](17-implementation-guide.md).**

### Hai lỗi thiết kế bị bắt trong quá trình kiểm chứng

Việc chạy thật các công thức trên dữ liệu không chỉ xác nhận — nó bắt được hai lỗi mà đọc tài liệu không thấy:

1. **Bộ luật phân khúc để lọt 36,7% khách** vào `_unclassified`, vì mọi luật đều yêu cầu `n_disbursed >= 1` nên nhóm chỉ-bị-từ-chối không khớp luật nào. Đã sửa: thêm `rejected_only` và `repeat_standard`, và chuyển `high_risk` lên đầu (trước đó nó đứng cuối nên chỉ bắt được 15/97 khách).
2. **Công thức CLV bị vòng lặp logic**: `p_repeat` lấy từ phân khúc giá trị, mà phân khúc đó lại được định nghĩa bằng trạng thái vay lại — nên `champion` luôn có `p_repeat = 1,0`. Đã sửa: lấy từ bảng tra theo hồ sơ hành vi `(income_band × has_app)`.

Cả hai đều được ghi lại trong [ADR-004](adr/ADR-004-segmentation.md) và [06 §6.5](06-agent-design.md).

---

## 16.1 Đánh giá thẳng (trạng thái trước khi bổ sung)

Bộ tài liệu hiện tại đủ để một **dev có kinh nghiệm** bắt đầu ngay và làm xong Giai đoạn 0–2 (ETL, semantic layer, dashboard, phân khúc, CLV) mà gần như không cần hỏi lại. Đó là khoảng **60% khối lượng công việc**.

Nó **chưa đủ** cho Giai đoạn 3–4 (agent, prompt, chống hallucination), không phải vì thiếu mô tả mà vì thiếu **hiện vật chạy được**: file cấu hình, file prompt, bộ golden set. Những thứ đó không thể để dev tự bịa — chúng là nội dung nghiệp vụ, và nếu dev đoán thì sẽ lệch khỏi các giá trị tham chiếu ở [02](02-data-model.md) §2.4.

| Phần | Mức sẵn sàng | Thiếu gì |
|---|---|---|
| Mô hình dữ liệu + DDL | 🟢 95% | Không đáng kể — DDL copy-paste chạy được |
| Chọn DB, role, kết nối | 🟢 95% | File `00_roles.sql` thật |
| Kiến trúc, ranh giới module | 🟢 90% | — |
| Semantic layer | 🟡 55% | **`metrics.yml` đầy đủ 35 chỉ số** (tài liệu mới có ~10) |
| Agent, playbook | 🟡 50% | **8 file playbook** (mới có 1 mẫu) |
| Prompt, few-shot | 🟡 45% | **9 file prompt** (mới có 2 mẫu) |
| Chống hallucination | 🟢 85% | Thuật toán đã đủ chi tiết; thiếu bộ từ khoá so sánh/nhân quả đầy đủ |
| Streaming | 🟢 90% | — |
| API + UI | 🟡 65% | Cấu hình ECharts cho 7 biểu đồ; bảng mã lỗi |
| Config, deploy | 🟢 90% | — |
| Test, eval | 🟡 40% | **Golden set 100 ca** (mới có 6) |

**Tổng thể: khoảng 72%.** Phần còn lại tập trung ở sáu nhóm hiện vật, không phải ở tài liệu.

## 16.2 Sáu thứ còn thiếu, xếp theo mức chặn

| # | Hiện vật | Vì sao dev không tự làm được | Công sức |
|---|---|---|---|
| **1** | `config/semantic/metrics.yml` — 35 chỉ số, SQL thật | Mỗi chỉ số phải cho ra **đúng** giá trị tham chiếu ở [02](02-data-model.md) §2.4. Sai mẫu số là sai âm thầm, không báo lỗi | 3–4 giờ |
| **2** | `evals/golden/qa_set.yaml` — 100 ca | Là **định nghĩa của "đúng"**. Không có nó thì không đo được gì, và không hiệu chỉnh được ngưỡng | 4–5 giờ |
| **3** | 9 file `prompts/*.yaml` | Few-shot là phần chịu tải. Ví dụ "biết im lặng khi chênh lệch là nhiễu" phải lấy từ chính dữ liệu này | 2–3 giờ |
| **4** | 8 file `config/playbooks/*.yml` | Quyết định câu trả lời gồm mục nào — là quyết định nghiệp vụ | 2 giờ |
| **5** | `app/` skeleton: signature + type hint + docstring, thân hàm `NotImplementedError` | Cho phép chia việc song song mà không va nhau | 2–3 giờ |
| **6** | `config/{verify,analytics,stages}.yaml` + `entities.yml` + `errors.py` | Ngưỡng và mã lỗi phải thống nhất từ đầu | 1 giờ |

Tổng khoảng **14–18 giờ**. Sau đó bộ tài liệu đạt mức mà một dev mới vào cũng chạy được.

## 16.3 Có nên viết thiết kế chi tiết tới từng class/function không?

**Khuyến nghị: không — trừ bốn loại dưới đây.**

Lý do không nên: ở mức class/function, **code chính là đặc tả**. Một tài liệu mô tả "hàm `_compile_filters` nhận danh sách filter và trả về mệnh đề WHERE cùng dict tham số" không nói thêm điều gì so với chính chữ ký hàm đó, nhưng nó sẽ lỗi thời ngay lần refactor đầu tiên. Tài liệu lỗi thời tệ hơn không có tài liệu, vì người đọc vẫn tin nó.

Cái thực sự cần thống nhất trước khi code là những chỗ **nhiều người phải khớp nhau** hoặc **dễ làm sai một cách âm thầm**:

| Loại | Vì sao cần đặc tả trước | Trạng thái |
|---|---|---|
| **A. Hợp đồng dữ liệu** — `EvidenceSet`, `MetricRequest`, `CheckResult`, `TrustScore`, `AgentState` | Nhiều module dùng chung; đổi một trường là vỡ bốn chỗ | 🟢 Đã có ở [11](11-module-spec.md) §11.3 |
| **B. Interface giữa module** (Protocol / ABC) | Cho phép hai người làm hai module song song, ráp lại vẫn khớp | 🟡 Có chữ ký, **nên nâng thành Protocol thật trong code** |
| **C. Thuật toán dễ sai** — `parse_vi_number`, `_find_safe_cut`, `wilson_ci`, `SQLGuard.validate` | Dev tự nghĩ sẽ ra bản sai tinh vi | 🟢 Đã có pseudocode + bộ test ở [11](11-module-spec.md), [13](13-testing-eval.md), [15](15-streaming.md) |
| **D. Schema cấu hình** | Business user cũng đụng vào, nên phải cố định | 🟡 Có ví dụ, **thiếu file đầy đủ** |

Còn lại — logic bên trong một hàm, tên biến cục bộ, thứ tự các bước, CRUD thường — **để dev tự quyết**. Đặc tả tới mức đó vừa tốn thời gian vừa tước mất phán đoán của người viết code.

### Mức đặc tả đúng: viết Protocol thành code, không thành văn

Thay vì viết thêm một tài liệu, đưa các interface vào **file Python thật**. Nó là tài liệu, nhưng là tài liệu mà `mypy` kiểm tra được và không bao giờ nói dối:

```python
# app/contracts.py  -- hop dong giua cac module, mypy kiem tra duoc
from typing import Protocol, Iterator

class MetricRunner(Protocol):
    """Chay mot MetricRequest va tra ve Fact co dia chi o.
    Raise UnknownMetricError neu chi so khong co trong catalog."""
    def run(self, req: MetricRequest) -> Fact: ...

class Narrator(Protocol):
    """Sinh van ban co THE, khong co chu so. Xem prompts/narrate_*.yaml."""
    async def narrate(self, playbook: Playbook, ev: EvidenceSet,
                      question: str) -> AsyncIterator[str]: ...

class Checker(Protocol):
    """Mot lop kiem chung. Phai thuan: khong I/O, khong goi LLM.
    Ngoai le duy nhat la Judge (L5), duoc danh dau bang thuoc tinh is_async."""
    name: str
    severity: Severity
    def check(self, answer: str, ev: EvidenceSet) -> CheckResult: ...

class SegmentBuilder(Protocol):
    """Gan moi khach vao dung mot phan khuc. Tong phai bang 100% so khach."""
    def build(self, rows: list[CustomerRow]) -> SegmentTable: ...
```

Một dev đọc `Checker` là biết đủ để viết `numeric.py`, `entity.py`, `stats_guard.py` mà không cần hỏi ai — và dòng docstring "phải thuần, không I/O" chính là thứ `import-linter` đang ép ở [11](11-module-spec.md) §11.6.

## 16.4 Điều kiện đủ để bắt đầu từng giai đoạn

Dùng như checklist trước khi giao việc.

| Giai đoạn | Cần có sẵn | Đã có? |
|---|---|---|
| **0 — Nền dữ liệu** | DDL, invariant, `00_roles.sql`, bảng giá trị tham chiếu | 🟢 Đủ, chỉ cần tách DDL ra file `.sql` |
| **1 — Dashboard** | `metrics.yml` đầy đủ, `entities.yml`, hợp đồng `EvidenceSet`, cấu hình ECharts | 🔴 **Chặn ở `metrics.yml`** |
| **2 — Phân khúc & CLV** | Luật phân khúc, công thức CLV, `analytics.yaml`, thư viện hành động | 🟡 Có công thức, thiếu file `clv_actions.yml` đầy đủ |
| **3 — Agent & chat** | 9 prompt, 8 playbook, `stages.yaml`, bảng sự kiện SSE | 🔴 **Chặn ở prompt và playbook** |
| **4 — Chống hallucination** | Thuật toán L0–L6, `verify.yaml`, **golden set** | 🔴 **Chặn ở golden set** |
| **5 — Deploy** | Dockerfile, các bước, biến môi trường | 🟢 Đủ |

Ba ô đỏ chính là sáu hiện vật ở §16.2. Không có gì khác đang chặn.

## 16.5 Những chỗ tài liệu nói "sẽ làm" mà chưa nói "làm thế nào"

Liệt kê để không ai tưởng đã xong:

| Chỗ | Tình trạng | Cần bổ sung |
|---|---|---|
| Bộ từ khoá so sánh/nhân quả tiếng Việt ([08](08-anti-hallucination.md) §8.4) | Mới liệt kê ~20 từ | Bộ đầy đủ + cách ghép câu với cặp `(left, right)` |
| `extract_proper_nouns_vi` ([08](08-anti-hallucination.md) §8.5) | Chỉ có tên hàm | Thuật toán: tiếng Việt không viết hoa danh từ chung như tiếng Anh nên heuristic khác hẳn |
| Cấu hình ECharts 7 biểu đồ ([09](09-api-ui.md) §9.7) | Mới có bảng mô tả | `option` JSON thật cho từng loại |
| Bảng mã lỗi | Rải rác | `app/errors.py` + ánh xạ sang HTTP + thông báo tiếng Việt |
| `ops.stream_buffer` cho reconnect ([15](15-streaming.md) §15.8) | Mới nhắc tên | DDL + chính sách dọn dẹp |
| Chế độ template khi LLM chết ([04](04-architecture.md) §4.7) | Mới nêu nguyên tắc | File `config/templates/*.yaml` |
| `answer_cache` ([04](04-architecture.md) §4.6) | Mới nêu ý | DDL + khoá cache + cách vô hiệu khi ETL chạy |

Bảy mục này đều nhỏ (mỗi mục dưới 1 giờ), nhưng nếu để dev tự quyết thì mỗi người một kiểu.

## 16.6 Khuyến nghị

**Đừng viết thêm tài liệu thiết kế. Hãy sinh ra hiện vật.**

Thứ tự đề xuất, mỗi bước xong là mở khoá được một giai đoạn:

1. **`metrics.yml` + `entities.yml` đầy đủ, kèm `tests/test_metrics_contract.py`** khoá 6 giá trị ROMI và bảng phân khúc.
   → Mở khoá Giai đoạn 1. Đây là việc đáng làm đầu tiên, vì nó vừa là cấu hình vừa là bài kiểm tra đúng/sai.
2. **Skeleton `app/` + `app/contracts.py`** — đầy đủ signature, type hint, docstring, thân `NotImplementedError`, `pytest` chạy được (tất cả skip).
   → Cho phép chia việc song song ngay.
3. **9 prompt + 8 playbook + `stages.yaml` + `verify.yaml` + `analytics.yaml`**.
   → Mở khoá Giai đoạn 3.
4. **Golden set 100 ca** theo thành phần ở [13](13-testing-eval.md) §13.4, gồm 32 ca bẫy.
   → Mở khoá Giai đoạn 4 và việc hiệu chỉnh ngưỡng.
5. **Bảy mục nhỏ ở §16.5.**

Sau bước 2, dev có thể bắt đầu viết code thật ngay trong khi bước 3–4 vẫn đang được soạn — vì chúng là file cấu hình, không chặn việc viết code.

### Cách chia việc nếu có nhiều người

Ranh giới module ở [04](04-architecture.md) §4.9 được thiết kế để chia được. Với 3 người:

| Người | Module | Phụ thuộc |
|---|---|---|
| A | `etl/`, `data/`, `semantic/` | Cần `metrics.yml` |
| B | `analytics/`, `verify/` | Chỉ cần `app/contracts.py` — **không cần DB, không cần LLM**, vì hai module này thuần hàm |
| C | `api/`, `web/`, `agent/streaming.py` | Cần bảng sự kiện SSE ([15](15-streaming.md) §15.3) — đã có |

Người B bắt đầu được **ngay lập tức** và test được toàn bộ phần việc của mình mà không cần chờ ai. Đó không phải may mắn — đó là lý do `analytics` và `verify` bị cấm import `data` và `llm` ngay từ đầu.
