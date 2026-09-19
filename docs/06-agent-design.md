# 06 — Thiết kế Agent

## 6.1 Máy trạng thái

Agent không phải vòng lặp ReAct tự do. Nó là một pipeline có số bước cố định, vì ba lý do: trần rate limit 10 RPM, yêu cầu truy vết được từng bước, và vì bài toán này thực sự chỉ có vài hình thái câu hỏi.

```
        +---------+
        |  INTAKE |  chuan hoa cau hoi, doc lich su, kiem tra cache
        +----+----+
             |
        +----v----+
        |  ROUTE  |  -> intent + entity   (1 goi LLM, co the bo qua neu khop luat)
        +----+----+
             |
     +-------v--------+
     | SELECT PLAYBOOK|  bang tra cuu, KHONG goi LLM
     +-------+--------+
             |
        +----v----+
        |  PLAN   |  playbook sinh danh sach MetricRequest (0 goi LLM)
        +----+----+
             |
        +----v----+
        | COMPUTE |  semantic compiler -> engine_ro -> EvidenceSet
        +----+----+
             |
        +----v----+
        | ANALYZE |  thong ke, CLV, phan khuc  (Python thuan, 0 goi LLM)
        +----+----+
             |
        +----v----+
        | NARRATE |  LLM viet CHU, so la the {{F1.r1.romi}}   (1 goi LLM)
        +----+----+
             |
        +----v----+
        | VERIFY  |  L0..L6  (tat dinh truoc, LLM judge bat dong bo)
        +----+----+
             |
       +-----v------+
       |   DECIDE   |  ANSWER | HEDGE | REGENERATE(1 lan) | ABSTAIN
       +-----+------+
             |
        +----v----+
        | RENDER  |  thay the -> so that, dinh dang vi-VN, gan huy hieu
        +----+----+
             |
        +----v----+
        |  TRACE  |  ghi ops.agent_trace
        +---------+
```

Chỉ hai bước gọi LLM: `ROUTE` và `NARRATE`. `VERIFY` có thể gọi thêm một lượt nhưng chạy bất đồng bộ ngoài đường găng.

Khi chạy ở chế độ streaming, mỗi bước phát một sự kiện `stage` kèm thông báo tiếng Việt lấy từ `config/stages.yaml`, và bước `NARRATE`/`VERIFY`/`RENDER` hợp nhất thành một vòng kiểm chứng theo khối. Chi tiết ở [15 — Streaming](15-streaming.md).

## 6.2 AgentState

```python
@dataclass
class AgentState:
    # Dau vao
    trace_id: UUID
    session_id: str | None
    question: str
    history: list[Turn] = field(default_factory=list)
    locale: str = "vi"

    # Dinh tuyen
    intent: Intent | None = None            # enum, xem 6.3
    entities: dict[str, list[str]] = field(default_factory=dict)
    playbook: str | None = None
    route_confidence: float = 0.0

    # Tinh toan
    metric_requests: list[MetricRequest] = field(default_factory=list)
    evidence: EvidenceSet | None = None
    analyses: dict[str, Any] = field(default_factory=dict)   # ket qua thong ke/CLV

    # Sinh van ban
    narrative_template: str | None = None   # van con the {{F1.r1.romi}}
    narrative_final: str | None = None      # da thay the

    # Kiem chung
    checks: list[CheckResult] = field(default_factory=list)
    trust: TrustScore | None = None
    decision: Decision = Decision.PENDING
    block_reason: str | None = None

    # Do luong
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    started_at: datetime = field(default_factory=now)
    prompt_version: str = ""
    metrics_version: str = ""
```

State là một dataclass thuần, không có phương thức gọi I/O. Mỗi bước là một hàm `step(state) -> state`, nên có thể test từng bước riêng và có thể tái hiện lại một phiên từ `agent_trace`.

## 6.3 Intent và playbook

```python
class Intent(StrEnum):
    CAMPAIGN_OVERVIEW   = "campaign_overview"    # "chien dich nao hieu qua nhat"
    CAMPAIGN_DIAGNOSIS  = "campaign_diagnosis"   # "vi sao Broker lo"
    FUNNEL_ANALYSIS     = "funnel_analysis"      # "phieu roi o dau"
    CUSTOMER_PERSONA    = "customer_persona"     # "tap khach nao tiem nang"
    SEGMENT_DEEP_DIVE   = "segment_deep_dive"    # "ke ve nhom thu nhap 12-20M"
    CLV_ACTIONS         = "clv_actions"          # "lam gi de tang CLV"
    RISK_FRAUD          = "risk_fraud"           # "ho so bi tu choi vi sao"
    DATA_QUESTION       = "data_question"        # "co bao nhieu khach hang"
    FREEFORM            = "freeform"             # khong khop -> sql_tool co rao
    OUT_OF_SCOPE        = "out_of_scope"         # -> tu choi lich su
```

Ánh xạ intent sang playbook nằm trong `config/playbooks/*.yml`, không nằm trong code:

```yaml
# config/playbooks/campaign_diagnosis.yml
id: campaign_diagnosis
label_vi: "Chẩn đoán một chiến dịch"
requires_entities: [campaign_id]
sections:                        # thu tu section = thu tu trong cau tra loi
  - id: verdict
    label_vi: "Kết luận"
    metrics: [romi, net_profit, acquisition_spend]
    group_by: [campaign_id]
  - id: funnel
    label_vi: "Phễu"
    metrics: [leads, applications, disbursed_loans,
              lead_to_application_rate, approval_rate]
    group_by: [campaign_id]
  - id: cost_breakdown
    label_vi: "Phân rã chi phí"
    metrics: [marketing_cost, lead_cost, partner_fee, funding_cost,
              credit_loss, operation_cost, loan_processing_cost, collection_cost]
    group_by: [campaign_id]
  - id: benchmark
    label_vi: "So với các chiến dịch cùng sản phẩm"
    metrics: [romi, approval_rate, cost_per_disbursed]
    group_by: [campaign_id, campaign_name]
    filters: [{dim: product_id, op: eq, value_from_entity: product_id}]
    order_by: romi
  - id: reject_reasons
    label_vi: "Lý do bị từ chối"
    metrics: [rejected_loans]
    group_by: [reason_level_1]
prompt: prompts/narrate_campaign_diagnosis.yaml
comparison_policy: significance_required   # xem 08 muc 4
```

Thêm một loại phân tích mới nghĩa là thêm một file YAML, không phải sửa code.

## 6.4 Bộ công cụ

| Tool | Chữ ký | Gọi LLM | Ghi chú |
|---|---|---|---|
| `metric_tool` | `run(MetricRequest) -> Fact` | 0 | Đường chính. Đã kiểm chứng. |
| `schema_tool` | `describe(dataset?) -> CatalogView` | 0 | Trả mô tả chỉ số bằng tiếng Việt cho LLM đọc, **không** trả schema DB thô |
| `sql_tool` | `run_guarded(sql) -> Fact` | 0 | Đường thoát, 7 cửa kiểm tra ở [05](05-semantic-layer.md) §5.6 |
| `stats_tool` | `compare_proportions(...)`, `wilson_ci(...)`, `bootstrap_mean_diff(...)` | 0 | Bắt buộc gọi trước mọi phát biểu so sánh |
| `clv_tool` | `estimate(segment) -> CLVEstimate` | 0 | Công thức minh bạch, §6.5 |
| `segment_tool` | `build(spec) -> SegmentTable` | 0 | Rule-based, §6.6 |
| `export_tool` | `to_csv(segment) -> bytes` | 0 | Danh sách `customer_id` cho CRM |

Không có tool nào gọi LLM. LLM đứng ngoài, chọn tool và diễn giải kết quả. Đây là hệ quả trực tiếp của nguyên tắc P1.

`schema_tool` trả mô tả tiếng Việt chứ không trả `CREATE TABLE`, vì đưa schema thô cho LLM chính là mời nó viết SQL tự do — thứ ta đang cố tránh.

## 6.5 Mô hình CLV

CLV phải **minh bạch và kiểm tra được bằng tay**, không phải một model học máy hộp đen. Ai cũng phải mở được bảng tính ra và dò lại.

### CLV đã thực hiện (lịch sử)

```
clv_to_date(customer) = SUM(net_profit cua moi ho so cua khach do)
```

Đã có sẵn trong `mart_customer_value.profit_to_date`. Không có giả định nào.

### CLV dự báo

```
clv_predicted = clv_to_date
              + p_repeat(segment) * avg_profit_next_loan(segment) * horizon_factor
```

| Tham số | Nguồn | Giá trị đo được |
|---|---|---|
| `p_repeat(hồ sơ hành vi)` | bảng tra theo `(income_band × has_app)`, tính trên khách **đã giải ngân ≥1 khoản** | 12–20M+app: 36,3% · 12–20M không app: 23,1% · 8–12M+app: 19,5% · <8M không app: 8,2% · toàn tập 21,8% |
| `avg_profit_per_repeat_loan` | lợi nhuận TB mỗi **khoản vay lại** | **807 610 VND** (n = 486) |
| `horizon_factor` | số chu kỳ tái vay kỳ vọng trong 12 tháng | **giả định cấu hình**, mặc định 1,0 |

> ### ⚠️ Vì sao `p_repeat` KHÔNG lấy từ phân khúc giá trị
>
> Đây là một lỗi thiết kế đã được phát hiện khi kiểm chứng công thức trên dữ liệu thật, và nó tinh vi đến mức đáng ghi lại.
>
> Phân khúc `champion` được **định nghĩa bằng** `is_repeat_customer = true`. Nên nếu lấy tỷ lệ vay lại *trong* phân khúc đó làm `p_repeat`, ta luôn nhận được đúng 1,0 — và `dormant` luôn nhận 0,0. Đó là **vòng lặp logic**: con số đo quá khứ chứ không dự báo tương lai, và mô hình CLV trở thành phép nhân vô nghĩa.
>
> Cách sửa: `p_repeat` lấy từ **hồ sơ hành vi** — tổ hợp `(income_band × has_app)` — là những chiều **dự báo được và không nằm trong định nghĩa phân khúc**. Bảng tra nằm ở `config/analytics.yaml → clv.p_repeat_lookup`.
>
> Chuỗi dự phòng khi ô chi tiết có n < 30: `(income_band, has_app)` → `income_band` → toàn tập. Nhóm `>=20M` kích hoạt đúng chuỗi này: ô chi tiết chỉ có n=17 và n=7, gộp theo thu nhập vẫn chỉ n=24, nên rơi xuống giá trị toàn tập.

Ba quy tắc bắt buộc đi kèm mọi con số CLV dự báo:

1. **Luôn trả về khoảng, không bao giờ trả điểm.** Cận dưới và cận trên lấy từ khoảng tin cậy Wilson 95% của `p_repeat`. Với nhóm 12–20M (n=797, p=20,7%): CI Wilson xấp xỉ [18,0%; 23,7%] → CLV dự báo là một dải, và dải đó phải hiện trên UI.
2. **`horizon_factor` là giả định, không phải dữ liệu.** Dữ liệu chỉ có 31 ngày giao dịch (DQ-03). Không thể suy ra chu kỳ tái vay trong 12 tháng từ một tháng. Giá trị nằm ở `config/analytics.yaml`, mặc định 1,0, và **phải được in ra kèm kết quả**: *"giả định mỗi khách tái vay tối đa 1 lần trong 12 tháng"*.
3. **n < 30 thì không trả số**, chỉ trả `INSUFFICIENT_SAMPLE`. Nhóm thu nhập ≥20M (n=29) rơi đúng vào đây — một sự trùng hợp may mắn khiến nó thành test case hoàn hảo.

```python
def estimate_clv(seg: SegmentStats, cfg: AnalyticsConfig) -> CLVEstimate:
    if seg.n_customers < cfg.min_sample_size:                 # mac dinh 30
        return CLVEstimate.insufficient(seg, reason="n < %d" % cfg.min_sample_size)

    lo, hi = wilson_ci(seg.n_repeat, seg.n_customers, conf=0.95)
    base   = seg.profit_to_date_mean
    nxt    = seg.avg_profit_per_repeat_loan
    h      = cfg.horizon_factor

    return CLVEstimate(
        point = base + seg.repeat_rate * nxt * h,
        lower = base + lo * nxt * h,
        upper = base + hi * nxt * h,
        assumptions = [
            f"horizon_factor = {h} (gia dinh cau hinh, khong suy ra tu du lieu)",
            f"p_repeat = {seg.repeat_rate:.1%}, CI95 = [{lo:.1%}, {hi:.1%}], n = {seg.n_customers}",
            f"loi nhuan moi khoan tai vay = {nxt:,.0f} VND (trung binh cua {seg.n_repeat} khach)",
            "du lieu giao dich chi co 31 ngay (DQ-03): khong ngoai suy theo mua vu",
        ],
    )
```

Danh sách `assumptions` đi thẳng vào `EvidenceSet` và bắt buộc xuất hiện trong câu trả lời. Một con số CLV không kèm giả định là một con số không dùng được.

## 6.6 Phân khúc khách hàng

Phân khúc được tính bằng **luật tường minh trong code**, không do LLM nghĩ ra và không do k-means. LLM chỉ **đặt tên** và **kể chuyện** về các phân khúc đã tính xong.

Lý do: một phân khúc là cơ sở để chi tiền marketing. Nó phải tái lập được, giải thích được cho kiểm toán, và ổn định giữa hai lần chạy. K-means không cho ba tính chất đó.

### Khung phân tầng — ba trục, lấy từ dữ liệu thật

Trục được chọn vì chúng thực sự phân hoá trong bộ dữ liệu này ([02](02-data-model.md) §2.4), chứ không phải vì sách giáo khoa nói vậy:

| Trục | Vì sao chọn | Bằng chứng |
|---|---|---|
| **Giá trị** (`profit_to_date`) | Phân hoá mạnh nhất | Khách vay lại sinh lời gấp 20,9 lần |
| **Xu hướng tái vay** (`income_band` + `has_app` + `age_band`) | Ba chiều có tín hiệu | 20,7% vs 7,5%; 16,6% vs 10,3%; 21,6% vs 8,8% |
| **Trạng thái vòng đời** | Quyết định loại hành động | 347 khách chưa từng vay, 353 khách đã vay lại |

**Không dùng `occupation` làm trục phân khúc.** Nó gần như không phân hoá (180k–220k trên n≈360, σ cá thể 738k). Đưa nó vào chỉ tạo ra các phân khúc trông có vẻ sâu sắc nhưng thực chất là nhiễu. Nó vẫn được giữ làm **thuộc tính mô tả** trong chân dung, kèm ghi chú rõ rằng nó không phân biệt được giá trị.

```python
# Thu tu QUAN TRONG. Moi khach roi vao phan khuc DAU TIEN khop.
# Dinh nghia goc: config/analytics.yaml -> segmentation.rules
# SQL tuong duong: etl/sql/02_ddl_mart.sql -> mart.v_customer_segment
SEGMENT_RULES = [
    Rule("high_risk",        # rui ro ghi de MOI thuoc tinh khac
         lambda c: (c.worst_dayslate or 0) > 30 or c.n_rejected >= 2,
         label_vi="Rủi ro cao"),
    Rule("champion",         # da chung minh gia tri
         lambda c: c.is_repeat_customer and c.profit_to_date >= P75_PROFIT,
         label_vi="Khách hàng trụ cột"),
    Rule("repeat_standard",  # da vay lai nhung gia tri chua cao
         lambda c: c.is_repeat_customer,
         label_vi="Khách vay lại thường"),
    Rule("high_potential",   # chua tai vay nhung moi dau hieu deu thuan
         lambda c: c.n_disbursed >= 1 and c.income_band in ("12-20M", ">=20M")
                   and c.has_app and (c.worst_dayslate or 0) == 0,
         label_vi="Tiềm năng cao"),
    Rule("app_gap",          # gia tri tot nhung chua cai app
         lambda c: c.n_disbursed >= 1 and not c.has_app
                   and c.income_band in ("12-20M", ">=20M"),
         label_vi="Chưa cài app"),
    Rule("dormant",          # da giai ngan, chua vay lai
         lambda c: c.n_disbursed >= 1,
         label_vi="Đang ngủ đông"),
    Rule("rejected_only",    # da nop ho so nhung chua bao gio duoc giai ngan
         lambda c: c.n_applications >= 1,
         label_vi="Chỉ bị từ chối"),
    Rule("never_activated",  # 347 khach o DQ-07
         lambda c: c.is_never_applied,
         label_vi="Chưa kích hoạt"),
]
```

Phân bố thực tế, **đã kiểm chứng** trên dữ liệu:

| Phân khúc | n | Tỷ trọng | LN trung bình | LN trung vị | CLV dự báo (khoảng) |
|---|---:|---:|---:|---:|---|
| `rejected_only` | 1 023 | 35,3% | −140 451 | −140 551 | không áp dụng |
| `dormant` | 802 | 27,6% | 305 061 | 293 219 | 431 988 – 499 124 |
| `never_activated` | 347 | 12,0% | 0 | 0 | không áp dụng |
| `champion` | 282 | 9,7% | 1 423 972 | 1 276 482 | 1 673 474 – 1 763 233 |
| `app_gap` | 159 | 5,5% | 327 085 | 330 648 | 472 540 – 561 802 |
| `high_potential` | 145 | 5,0% | 303 559 | 271 814 | 553 060 – 642 819 |
| `high_risk` | 97 | 3,3% | −936 131 | −382 047 | −809 205 – −742 069 |
| `repeat_standard` | 46 | 1,6% | 45 579 | −90 022 | 295 081 – 384 840 |

Tổng **2 901 = 100%**, và `_unclassified` bằng **0**.

> ### ⚠️ Bộ luật ban đầu để lọt 36,7% khách
>
> Phiên bản đầu của thiết kế này có sáu luật và dùng `_unclassified` như "lưới an toàn". Khi chạy thật, **1 064 khách (36,7%) rơi vào lưới đó** — chủ yếu là nhóm đã nộp hồ sơ nhưng chưa bao giờ được giải ngân, vì mọi luật khác đều yêu cầu `n_disbursed >= 1`.
>
> Một phân khúc `_unclassified` chiếm hơn một phần ba tập khách không phải lưới an toàn; nó là **dấu hiệu bộ luật chưa hoàn chỉnh**. Bài học: `_unclassified` phải luôn bằng 0, và `tests/test_segmentation.py::test_no_unclassified` khẳng định điều đó.
>
> Sửa thêm: `high_risk` được chuyển lên **đầu** danh sách. Trước đó nó đứng cuối nên chỉ bắt được 15 khách; một khách vay lại nhiều lần nhưng nợ quá hạn 60 ngày vẫn bị xếp vào `champion`. Rủi ro phải ghi đè mọi thuộc tính khác.

Với mỗi phân khúc, `segment_tool` trả về một bảng có: `n`, tỷ trọng, `repeat_rate` kèm CI Wilson, `avg_profit`, `median_profit`, phân bố `income_band`/`age_band`/`occupation`/`device_os`, và `clv_predicted` kèm khoảng.

K-means được giữ ở `app/analytics/segmentation.py` như một **chế độ đối chứng tuỳ chọn** (`--mode kmeans`), dùng để kiểm tra xem luật thủ công có bỏ sót cấu trúc nào không. Nó không bao giờ là nguồn cho câu trả lời gửi người dùng.

## 6.7 Sinh khuyến nghị hành động (D3)

Đây là phần dễ bịa nhất — một LLM sẽ vui vẻ đề xuất "chạy chiến dịch email marketing" cho bất cứ vấn đề gì. Cấu trúc để chặn:

Khuyến nghị **không được LLM nghĩ ra**. Chúng đến từ một **thư viện hành động** trong `config/playbooks/clv_actions.yml`, mỗi hành động có: điều kiện kích hoạt (biểu thức trên số liệu phân khúc), chỉ số mục tiêu, và công thức ước lượng tác động. LLM chỉ chọn trong số các hành động **đã đủ điều kiện** và viết lời giải thích.

```yaml
actions:
  - id: push_app_adoption
    label_vi: "Đẩy cài app cho nhóm giá trị cao chưa có app"
    trigger: "segment == 'app_gap' and segment.n >= 100"
    target_segment: app_gap
    target_metric: repeat_customer_rate
    impact_formula: "segment.n * (repeat_rate_with_app - repeat_rate_without_app) * avg_profit_per_repeat_loan"
    impact_caveat_vi: >
      Ước lượng trần trên. Chênh lệch tỷ lệ vay lại giữa nhóm có app và không app là
      TƯƠNG QUAN, chưa chứng minh nhân quả. Phải chạy A/B test trước khi mở rộng.
    evidence_required: [repeat_customer_rate_by_has_app, segment_size]
    effort: medium

  - id: reloan_campaign_dormant
    label_vi: "Chiến dịch tái vay cho nhóm ngủ đông qua Zalo ZNS"
    trigger: "segment == 'dormant' and campaign.CMP-ZL-RL1.romi > 2.0"
    target_segment: dormant
    target_metric: net_profit
    impact_formula: "segment.n * reloan_conversion_observed * profit_per_reloan"
    impact_caveat_vi: >
      Dùng tỷ lệ chuyển đổi quan sát được của chính chiến dịch CMP-ZL-RL1 (34,4% lead
      thành hồ sơ, duyệt 92%), áp cho tập ngủ đông. Giả định tập này phản ứng tương tự
      tập đã được nhắm trước đó — cần kiểm chứng bằng một đợt thử quy mô nhỏ.
    evidence_required: [campaign_funnel_CMP-ZL-RL1, dormant_segment_size]
    effort: low

  - id: cut_broker_budget
    label_vi: "Cắt hoặc đàm phán lại phí kênh Broker"
    trigger: "campaign.romi < 0 and campaign.partner_fee_share > 0.15"
    target_metric: romi
    impact_formula: "abs(campaign.net_profit)"
    impact_caveat_vi: >
      Khoản lỗ tránh được nếu dừng hẳn. Chưa tính tác động tới tổng số lead
      và chưa tính chi phí chấm dứt hợp đồng đối tác.
    effort: low

  - id: tighten_tiktok_targeting
    label_vi: "Siết targeting TikTok theo tiêu chí của nhóm được duyệt"
    trigger: "campaign.lead_to_application_rate < 0.15 and campaign.approval_rate < 0.50"
    target_metric: cost_per_disbursed
    impact_formula: "campaign.acquisition_spend * (1 - target_ratio)"
    effort: medium
```

Mỗi khuyến nghị xuất ra đều mang đủ năm thứ: **phân khúc mục tiêu (kèm cỡ), chỉ số mục tiêu, ước lượng tác động (kèm công thức), giả định, và mức công sức**. Thiếu một trong năm thì không được hiển thị. Không có khuyến nghị chung chung kiểu "nên tăng cường chăm sóc khách hàng".

## 6.8 Chính sách từ chối trả lời

Agent abstain khi bất kỳ điều kiện nào dưới đây đúng. Đây là hiện thực hoá nguyên tắc P3, và nó phản ánh một lựa chọn hàm mục tiêu: **một câu trả lời sai đắt hơn nhiều một lần im lặng.**

| Điều kiện | Câu trả lời mẫu |
|---|---|
| Cỡ mẫu dưới ngưỡng chỉ số | "Nhóm này chỉ có 29 khách hàng — quá ít để kết luận. Số thô: ..." |
| Hỏi xu hướng liên tháng (DQ-03) | "Dữ liệu giao dịch chỉ có tháng 8/2026, không so sánh theo tháng được." |
| Chỉ số không có trong catalog | "Chưa có định nghĩa cho chỉ số này. Các chỉ số gần nhất: ..." |
| Free-form SQL fail sau 3 lần | "Không dựng được truy vấn. Thử hỏi theo cách khác?" |
| Self-consistency dưới 60% | "Có nhiều cách hiểu câu hỏi cho kết quả khác nhau. Ý bạn là A hay B?" |
| Numeric grounding fail sau khi sinh lại | Chặn hẳn phần diễn giải, chỉ hiện bảng số thô |
| Ngoài phạm vi (hỏi chuyện không liên quan) | Từ chối ngắn gọn, gợi ý ba câu hỏi làm được |

`false_refusal_rate` được đo song song với `abstention_rate` trong [13](13-testing-eval.md). Một agent từ chối quá tay cũng là một agent hỏng.
