# 13 — Kiểm thử và đo chất lượng agent

## 13.1 Kim tự tháp kiểm thử

```
                  /\
                 /  \   E2E (Playwright)         ~5 ca
                /----\   - rang buoc chat 60%
               /      \  - hoi -> tra loi -> xem bang chung
              /--------\
             /          \ Golden set (100 ca)    <- trong tam
            /            \  chat luong cau tra loi
           /--------------\
          /                \ Integration          ~30 ca
         /                  \ ETL, compiler, repository tren Postgres that
        /--------------------\
       /                      \ Unit                ~150 ca
      /________________________\ stats, CLV, numeric parser, sqlguard
```

Khác với dự án phần mềm thông thường, **tầng golden set mới là tầng quyết định**. Unit test chứng minh code chạy đúng; golden set chứng minh *agent trả lời đúng* — và đó mới là thứ người dùng quan tâm.

## 13.2 Unit test — những chỗ dễ sai nhất

| File test | Bảo vệ điều gì | Số ca tối thiểu |
|---|---|---|
| `test_vi_number_parser.py` | `parse_vi_number` — tiếng Việt dùng `.` cho hàng nghìn, `,` cho thập phân, ngược với Python | **30** |
| `test_numeric_grounding.py` | Từng kiểu lỗi H1–H3, H12 ở [08](08-anti-hallucination.md) §8.10 | 25 |
| `test_stats.py` | Wilson CI, z-test hai tỷ lệ, bootstrap; đối chiếu với giá trị tính tay | 20 |
| `test_stats_guard.py` | H5, H6, H7 — đặc biệt ca "nghề nghiệp" phải trả `significant=false` | 15 |
| `test_sqlguard.py` | Chặn DML, bịa cột, thiếu LIMIT, comment che giấu, truy vấn lồng | 25 |
| `test_semantic_compiler.py` | Metric/dimension không tồn tại phải raise; filter phải bind param | 20 |
| `test_clv.py` | n<30 trả `INSUFFICIENT_SAMPLE`; khoảng phải chứa điểm | 10 |
| `test_segmentation.py` | Mọi khách rơi vào đúng một phân khúc, tổng = 100% | 10 |
| `test_formatting.py` | Backend và frontend định dạng số ra cùng chuỗi | 15 |

Ví dụ bộ ca của `parse_vi_number` — phải có cả ca ngược để tránh khớp quá rộng:

```python
@pytest.mark.parametrize("s,expected", [
    ("392.498.500",   392_498_500.0),
    ("392.498.500 VND", 392_498_500.0),
    ("6,20",          6.2),
    ("-1,85",         -1.85),
    ("48,8%",         0.488),
    ("92%",           0.92),
    ("1,2 tỷ",        1_200_000_000.0),
    ("392,5 tr",      392_500_000.0),
    ("2 687",         2687.0),
    ("2026",          2026.0),
    # ca nguoc: khong duoc nhan dang la so
    ("CMP-FB-001",    None),
    ("CUS-100701",    None),
    ("PRD-RL",        None),
    ("v2.1.0",        None),
])
def test_parse_vi_number(s, expected):
    assert parse_vi_number(s) == (pytest.approx(expected) if expected else None)
```

Bốn ca cuối quan trọng không kém bốn ca đầu: nếu parser nhận nhầm `CMP-FB-001` là số, lớp L2 sẽ báo động giả trên mọi câu trả lời có nhắc mã chiến dịch.

## 13.3 Integration test

Chạy trên PostgreSQL thật từ `docker-compose.dev.yml`, nạp bằng chính `etl/`.

```python
# tests/test_etl_invariants.py
def test_counts(db):
    assert db.scalar("SELECT COUNT(*) FROM raw.fact_loan")             == 2687
    assert db.scalar("SELECT COUNT(*) FROM raw.fact_lead")             == 14530
    assert db.scalar("SELECT COUNT(*) FROM raw.fact_reject")           == 1062
    assert db.scalar("SELECT COUNT(*) FROM raw.dim_customer")          == 2901

def test_inv2_rejected_and_disbursed_are_disjoint(db):
    assert db.scalar("""SELECT COUNT(*) FROM mart.mart_application
                        WHERE is_rejected AND is_disbursed""") == 0

def test_inv3_counts_add_up(db):
    r, d, t = db.row("""SELECT COUNT(*) FILTER (WHERE is_rejected),
                               COUNT(*) FILTER (WHERE is_disbursed),
                               COUNT(*) FROM mart.mart_application""")
    assert (r, d) == (1062, 1625) and r + d == t

def test_inv7_mart_does_not_multiply_rows(db):
    assert db.scalar("SELECT COUNT(*) FROM mart.mart_application") == 2687
```

`test_metrics_contract.py` là file quan trọng nhất ở tầng này: nó khoá sáu giá trị ROMI tham chiếu ([02](02-data-model.md) §2.4) và toàn bộ bảng phân khúc. Bất kỳ ai sửa định nghĩa chỉ số mà quên cập nhật giá trị tham chiếu sẽ thấy CI đỏ — đó chính là mục đích.

## 13.4 Golden set

### Lược đồ một ca

Mở rộng từ lược đồ bốn trường mà Ragas dùng cho eval text-to-SQL (`Query`, `SQL`, `Levels`, `split`), thêm những trường mà bài toán này cần:

```yaml
# evals/golden/qa_set.yaml
- id: G001
  question: "Chiến dịch nào đang lỗ?"
  category: ranking
  difficulty: easy
  split: dev
  expected_behavior: answer          # answer | clarify | refuse
  gold_sql: |
    SELECT campaign_id,
           SUM(net_profit) / NULLIF(SUM(acquisition_spend), 0) AS romi
    FROM mart.mart_application GROUP BY campaign_id HAVING SUM(net_profit) < 0
  must_mention_numbers: ["-66794870", "-17529770", "-1,85", "-0,41"]
  must_mention_entities: ["Broker Network", "Momo"]
  must_not_mention: ["Zalo", "Google"]      # chien dich co lai, khong duoc goi la lo
  notes: "Kiem tra doc dung dau am"

- id: G014
  question: "Nhóm nghề nghiệp nào sinh lời nhất?"
  category: adversarial
  difficulty: hard
  split: dev
  expected_behavior: answer
  must_mention_phrases: ["sai số thống kê"]     # hoac tuong duong
  must_not_mention_phrases: ["sinh lời nhất", "tốt nhất", "vượt trội"]
  expected_stats_flag: { significant: false }
  notes: "BAY: chenh lech 180k-220k tren n~360 la nhieu. Xem 02.4 bay 2"

- id: G027
  question: "Nhóm thu nhập trên 20 triệu có đáng đầu tư không?"
  category: small_sample
  difficulty: hard
  split: dev
  expected_behavior: answer
  must_mention_numbers: ["29"]
  must_mention_phrases: ["mẫu", "chưa đủ"]
  must_not_mention_phrases: ["nên dồn ngân sách", "chắc chắn"]
  notes: "n=29 duoi nguong 30. Phai canh bao co mau"

- id: G041
  question: "So sánh doanh thu tháng 8 với tháng 7"
  category: unanswerable
  difficulty: medium
  split: dev
  expected_behavior: refuse
  must_mention_phrases: ["tháng 8/2026", "không"]
  notes: "DQ-03: chi co 31 ngay du lieu"

- id: G058
  question: "Tỷ lệ chuyển đổi của chiến dịch Instagram là bao nhiêu?"
  category: out_of_schema
  difficulty: easy
  split: test
  expected_behavior: refuse
  must_not_mention_numbers: ["*"]     # khong duoc tra bat ky so nao
  notes: "Chien dich khong ton tai"

- id: G072
  question: "Cài app có làm khách vay lại nhiều hơn không?"
  category: causal_trap
  difficulty: hard
  split: test
  expected_behavior: answer
  must_mention_phrases: ["tương quan"]
  must_not_mention_phrases: ["vì", "do", "làm tăng", "dẫn đến"]
  notes: "BAY 3 o 02.4: tuong quan khong phai nhan qua"
```

### Thành phần 100 ca

| Nhóm | Tỷ lệ | Số ca | Mục đích |
|---|---:|---:|---|
| Trả lời được — dễ | 20% | 20 | Chỉ số đơn, một chiều |
| Trả lời được — trung bình | 20% | 20 | Nhiều chỉ số, có lọc, có sắp xếp |
| Trả lời được — khó | 20% | 20 | Chẩn đoán, phân rã, so sánh nhiều chiều |
| **Bẫy đối kháng** | 12% | 12 | Nhiễu thống kê, mẫu nhỏ, bẫy nhân quả |
| Không trả lời được | 12% | 12 | Ngoài schema, ngoài khoảng thời gian, ngoài phạm vi |
| Mơ hồ | 8% | 8 | Kỳ vọng hỏi lại làm rõ |
| Kết quả rỗng | 5% | 5 | Bẫy diễn giải bảng rỗng |
| Xuất dữ liệu | 3% | 3 | CSV phân khúc |

**32 ca thuộc nhóm bẫy / không trả lời được / mơ hồ.** Tỷ lệ cao có chủ ý: đó là những ca mà một agent kém sẽ trượt, còn các ca dễ thì agent nào cũng qua và không phân biệt được chất lượng.

Bắt đầu từ 100 ca (tương đương quy mô mà hướng dẫn eval text-to-SQL của Ragas dùng), rồi tăng dần bằng cách **biến mọi lần người dùng bấm ngón cái xuống thành một ca mới**. Đây là thói quen có giá trị nhất trong toàn bộ quy trình.

## 13.5 Chỉ số đo

| Chỉ số | Định nghĩa | Cổng CI |
|---|---|---|
| **`numeric_grounding_rate`** | Trung bình trên các ca đã trả lời | **= 1,000 — cổng cứng, không bao giờ cho phép tụt** |
| `execution_accuracy` | So kết quả SQL của agent với `gold_sql`, đối chiếu DataFrame (dung sai tuyệt đối 1e-10) | ≥ 0,90 |
| `entity_grounding_rate` | | = 1,000 |
| `refusal_accuracy` | Trong nhóm `expected_behavior = refuse`, tỷ lệ từ chối đúng | ≥ 0,85 |
| `false_refusal_rate` | Trong nhóm `answer`, tỷ lệ từ chối sai | ≤ 0,10 |
| `must_mention_recall` | Tỷ lệ số/thực thể bắt buộc thật sự xuất hiện | ≥ 0,95 |
| `must_not_mention_violations` | Số lần vi phạm | **= 0 — cổng cứng** |
| `selective_risk @ coverage` | Tỷ lệ trả lời sai trong số câu đã trả lời | ≤ 0,02 |
| `avg_trust_score` | | ≥ 0,88 |
| `p95_latency_ms` | | ≤ 8 000 |
| `llm_calls_per_answer` | | ≤ 2 |

Dùng **execution accuracy** làm chỉ số chính chứ không dùng exact-match trên chuỗi SQL. Exact-match phạt agent khi nó viết SQL đúng nhưng khác cú pháp với câu gold — một dạng âm tính giả vô nghĩa. Ngược lại, execution accuracy có thể cho dương tính giả khi hai câu SQL khác nhau tình cờ trả cùng kết quả trên bộ dữ liệu nhỏ; giảm thiểu bằng cách so cả tên và thứ tự cột ở những ca nhạy cảm.

## 13.6 Hiệu chỉnh ngưỡng

`t_high` và `t_low` trong `config/verify.yaml` khởi tạo là 0,85 và 0,60. **Đây là chỗ đặt tạm, không phải giá trị đã kiểm chứng.** Không có tài liệu nào công bố một ngưỡng đúng cho mọi domain; bản thân tài liệu AWS cũng chỉ nói "hãy tự hiệu chỉnh theo domain của bạn".

Quy trình hiệu chỉnh:

```python
# evals/calibrate.py
def calibrate(results: list[EvalResult], target_risk: float = 0.02) -> Thresholds:
    """1. Nguoi cham nhan dung/sai cho tung ca (mot lan, ~1 gio cho 100 ca)
       2. Sap xep theo trust_score giam dan
       3. Voi moi nguong t: coverage = ty le tra loi, risk = ty le sai trong so do
       4. Chon t_high nho nhat sao cho risk <= target_risk
       5. Chon t_low sao cho coverage tong >= 0.85 (gom ca HEDGE)
       6. Ve duong cong coverage-risk de nguoi doc tu chon diem van hanh"""
```

Chỉ bật cổng chặn **sau khi** đã hiệu chỉnh. Trước đó, lớp L5 chạy ở chế độ **chỉ ghi log** — thu điểm nhưng không chặn gì. Bật cổng trên một ngưỡng chưa hiệu chỉnh sẽ hoặc chặn nhầm hàng loạt câu đúng, hoặc không chặn gì cả.

Khi đã có đủ ca có nhãn, thay bộ trọng số thủ công bằng **hồi quy logistic** trên các đặc trưng kiểm tra để dự đoán đúng/sai. Đây là cách mà các nghiên cứu về ước lượng độ tin cậy cho text-to-SQL khuyến nghị, và nó luôn tốt hơn trọng số đoán bằng tay.

Một lưu ý khi đọc số: các đặc trưng hộp đen như self-consistency chỉ đạt AUROC khoảng 0,67 trong các nghiên cứu đối chứng, trong khi bộ verifier dùng LLM đạt khoảng 0,77 và hợp nhất hai nhà cung cấp đạt khoảng 0,82. Nghĩa là **đừng dựa vào self-consistency làm cổng chính** — nó đo xem model có tự nhất quán không, chứ không đo xem câu trả lời có đúng không.

## 13.7 Chạy eval

```bash
python -m evals.run_eval --split dev  --profile test          # nhanh, mock LLM
python -m evals.run_eval --split test --profile local         # LLM that
python -m evals.run_eval --quick                              # 20 ca, dung truoc khi deploy
python -m evals.run_eval --split all --seeds 3 --report html  # bao cao day du
```

Vì bộ chấm điểm có tính ngẫu nhiên, chạy ở `temperature = 0` và báo cáo **trung bình ± độ lệch chuẩn của 3 seed**, không bao giờ báo cáo một con số đơn lẻ.

Báo cáo HTML gồm: bảng tổng hợp, phân rã theo `category` và `difficulty`, danh sách ca trượt kèm diff giữa mong đợi và thực tế, đường cong coverage–risk, so sánh với lần chạy trước.

## 13.8 CI

```yaml
# .github/workflows/ci.yml  (rut gon)
jobs:
  test:
    services:
      postgres: { image: postgres:16-alpine, env: { POSTGRES_PASSWORD: devonly } }
    steps:
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: ruff check . && mypy app/semantic app/verify app/analytics
      - run: lint-imports                       # ep rang buoc module 04.9
      - run: python -m etl.load_excel --source excel && python -m etl.build_marts
      - run: python -m etl.dq_checks            # exit != 0 neu co BLOCK
      - run: pytest tests/ -v --cov=app --cov-fail-under=75
      - run: python -m evals.run_eval --split dev --profile test --fail-on-regression
      - run: playwright test tests/e2e/
```

Cổng chặn merge:

* `numeric_grounding_rate < 1.0` → **chặn**, không có ngoại lệ.
* `must_not_mention_violations > 0` → **chặn**.
* Bất kỳ DQ mức `BLOCK` nào fail → **chặn**.
* `execution_accuracy` tụt quá 3 điểm phần trăm so với `main` → **chặn**.
* `false_refusal_rate` tăng quá 5 điểm phần trăm → **cảnh báo** (cần người xem).

## 13.9 E2E

```python
# tests/e2e/test_ui_chat_height.py
def test_chat_area_max_60_percent(page):
    page.goto(BASE_URL)
    for i in range(40):
        page.fill("#chat-input", f"Câu hỏi thử {i}")
        page.click("#chat-send"); page.wait_for_selector(".msg-assistant")
    h = page.eval_on_selector("#chat-scroll", "el => el.clientHeight")
    assert h <= page.evaluate("window.innerHeight") * 0.60 + 1

@pytest.mark.parametrize("w,h", [(1920,1080), (1366,768), (390,844)])
def test_chat_height_across_viewports(page, w, h):
    page.set_viewport_size({"width": w, "height": h})
    page.goto(BASE_URL)
    assert page.eval_on_selector("#chat-scroll", "el => el.clientHeight") <= h * 0.60 + 1

def test_evidence_panel_shows_sql(page):
    page.goto(BASE_URL)
    page.fill("#chat-input", "Chiến dịch nào đang lỗ?"); page.click("#chat-send")
    page.wait_for_selector(".trust-badge")
    page.click("text=Xem SQL & dữ liệu")
    assert "SELECT" in page.inner_text("#evidence-panel")
    assert "mart_application" in page.inner_text("#evidence-panel")
```

## 13.10 Theo dõi sau khi chạy thật

`GET /admin/quality` đọc từ `ops.agent_trace`, hiển thị theo ngày các chỉ số ở [08](08-anti-hallucination.md) §8.8.

Bốn tín hiệu cần chú ý, kèm ý nghĩa:

| Tín hiệu | Nghĩa là gì |
|---|---|
| `numeric_grounding_rate` tụt dưới 1,0 | **Sự cố nghiêm trọng.** Điều tra ngay từng trace liên quan |
| `abstain_rate` tăng đột ngột | Người dùng đang hỏi những thứ catalog chưa phủ — đây là danh sách chỉ số cần bổ sung |
| `judge_contradiction_rate` tăng sau khi sửa prompt | Lần sửa prompt vừa rồi có vấn đề; dùng nút khôi phục ([07](07-prompt-fewshot.md) §7.5) |
| `llm_calls_per_answer` vượt 2 | Sắp đụng trần 10 RPM — kiểm tra vòng lặp sửa lỗi có đang chạy quá nhiều không |
