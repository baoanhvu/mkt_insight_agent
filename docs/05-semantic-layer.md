# 05 — Semantic Layer: catalog chỉ số

> Đây là lớp quan trọng nhất của hệ thống. Nó là nơi duy nhất định nghĩa "ROMI nghĩa là gì", và là lý do agent không thể bịa ra một chỉ số không tồn tại.

## 5.1 Vấn đề mà lớp này giải

Cách làm ngây thơ là đưa schema database vào prompt rồi bảo LLM viết SQL (text-to-SQL thuần). Cách đó hỏng ở ba chỗ, và cả ba đều đã hiện diện trong chính bộ dữ liệu này:

1. **Bịa tên cột.** LLM sẽ viết `JOIN fact_loan ON fact_lead.campaign_id = fact_loan.campaign_id` — cột đó **không tồn tại** trong `fact_loan` (xem [02](02-data-model.md) §2.1). Query fail, hoặc tệ hơn là chạy được nhưng sai.
2. **Sai mẫu số.** `AVG(loan_amount)` trên toàn bảng lặng lẽ bỏ 1 062 hồ sơ bị từ chối. Đôi khi đó là đúng, đôi khi là sai — phụ thuộc vào câu hỏi, và LLM không có cách nào biết chọn cái nào.
3. **Định nghĩa trôi.** Hỏi hai lần "ROMI của Facebook" có thể ra hai SQL khác nhau, vì lần này nó chia cho `marketing_cost`, lần sau chia cho `marketing_cost + lead_cost`. Dashboard và chat bất đồng, và không ai biết bên nào đúng.

Semantic layer giải cả ba bằng cách đảo ngược quan hệ: **LLM không viết SQL, LLM chọn chỉ số.** SQL đã được người viết sẵn, đã review, đã test.

```
Cach ngay tho:   cau hoi -> LLM -> SQL tu do -> ket qua   (LLM co the bia bat cu gi)
Cach nay:        cau hoi -> LLM -> MetricRequest  -> compiler -> SQL da kiem chung -> ket qua
                                   ^ chi duoc chon tu catalog
```

`MetricRequest` là một cấu trúc nhỏ, có kiểu chặt:

```python
MetricRequest(
    metric="campaign_romi",                    # phai ton tai trong catalog
    dimensions=["campaign_id", "campaign_name"],# phai nam trong dimension cho phep cua metric
    filters=[Filter("product_id", "eq", "PRD-FL")],
    date_range=DateRange("2026-08-01", "2026-08-31"),
    order_by="campaign_romi", limit=20,
)
```

Bất kỳ trường nào không khớp catalog thì **bị từ chối trước khi chạm tới database**. Đây là lớp L0 của hàng rào chống hallucination.

## 5.2 Cấu trúc file catalog

File: `config/semantic/metrics.yml`. Cùng `entities.yml` (khai báo bảng và chiều), đây là hai file mà một business analyst có thể đọc hiểu và sửa được.

```yaml
version: "1.3.0"          # tang moi khi doi dinh nghia -> ghi vao agent_trace

datasets:
  campaign:
    table: mart.mart_application
    grain: application
    description: "Mot dong = mot ho so vay, da noi campaign + P&L + khach hang"
    default_date_column: create_at

dimensions:
  campaign_id:
    dataset: campaign
    column: campaign_id
    label_vi: "Chiến dịch"
    label_column: campaign_name        # hien thi ten thay vi ma
    allowed_values_query: "SELECT DISTINCT campaign_id FROM mart.dim_campaign"
  channel:      { dataset: campaign, column: channel,      label_vi: "Kênh" }
  income_band:  { dataset: campaign, column: income_band,  label_vi: "Nhóm thu nhập",
                  ordered: ["<8M", "8-12M", "12-20M", ">=20M"] }
  age_band:     { dataset: campaign, column: age_band,     label_vi: "Nhóm tuổi",
                  ordered: ["20-25","26-30","31-35","36-45","46-55"] }
  occupation:   { dataset: campaign, column: occupation,   label_vi: "Nghề nghiệp" }
  has_app:      { dataset: campaign, column: has_app,      label_vi: "Có app" }
  device_os:    { dataset: campaign, column: device_os,    label_vi: "Hệ điều hành" }
  reason_level_1: { dataset: campaign, column: reason_level_1, label_vi: "Lý do từ chối" }
```

### Khai báo một chỉ số

```yaml
metrics:

  applications:
    label_vi: "Số hồ sơ"
    description_vi: "Đếm hồ sơ vay được tạo trong kỳ, gồm cả hồ sơ sau đó bị từ chối."
    dataset: campaign
    sql: "COUNT(*)"
    unit: count
    format: "#,##0"
    allowed_dimensions: [campaign_id, channel, income_band, age_band, occupation,
                         has_app, device_os, reason_level_1]

  disbursed_loans:
    label_vi: "Số khoản giải ngân"
    description_vi: "Hồ sơ có disbursement_date khác NULL. Không giao với hồ sơ bị từ chối."
    dataset: campaign
    sql: "COUNT(*) FILTER (WHERE is_disbursed)"
    unit: count
    format: "#,##0"

  approval_rate:
    label_vi: "Tỷ lệ duyệt"
    description_vi: "Số khoản giải ngân chia cho tổng số hồ sơ trong cùng kỳ và cùng lát cắt."
    dataset: campaign
    sql: |
      CASE WHEN COUNT(*) = 0 THEN NULL
           ELSE COUNT(*) FILTER (WHERE is_disbursed)::numeric / COUNT(*) END
    unit: ratio
    format: "0.0%"
    min_sample_size: 30          # duoi nguong nay -> gan canh bao, xem 08 muc 4
    higher_is_better: true

  net_profit:
    label_vi: "Lợi nhuận ròng"
    description_vi: >
      Tổng doanh thu trừ tổng chi phí ở mức hồ sơ.
      Doanh thu = interest_income + overdue_interest + early_paid_off_fee + processing_fee.
      Chi phí = loan_processing_cost + funding_cost + lead_cost + credit_loss
              + operation_cost + marketing_cost + partner_fee + collection_cost.
      Hồ sơ bị từ chối vẫn phát sinh chi phí (lead, marketing, xử lý) nên đóng góp ÂM.
    dataset: campaign
    sql: "SUM(net_profit)"
    unit: vnd
    format: "#,##0"
    higher_is_better: true

  acquisition_spend:
    label_vi: "Chi phí thu hút"
    description_vi: "marketing_cost + lead_cost, cộng trên TẤT CẢ hồ sơ kể cả bị từ chối."
    dataset: campaign
    sql: "SUM(acquisition_spend)"
    unit: vnd
    format: "#,##0"

  romi:
    label_vi: "ROMI"
    description_vi: >
      Lợi nhuận ròng chia cho chi phí thu hút.
      ROMI = 1,0 nghĩa là mỗi đồng chi thu hút mang về một đồng lợi nhuận.
      ROMI âm nghĩa là chiến dịch đang lỗ sau khi trừ mọi chi phí.
    dataset: campaign
    sql: |
      CASE WHEN SUM(acquisition_spend) = 0 THEN NULL
           ELSE SUM(net_profit) / SUM(acquisition_spend) END
    unit: ratio
    format: "0.00"
    higher_is_better: true
    thresholds:                  # dung cho to mau va cho canh bao tu dong
      critical: { lt: 0 }
      warning:  { lt: 1.0 }
      good:     { gte: 2.0 }

  cost_per_disbursed:
    label_vi: "Chi phí thu hút / khoản giải ngân"
    description_vi: "acquisition_spend chia cho số khoản giải ngân. NULL nếu không có khoản nào."
    dataset: campaign
    sql: |
      CASE WHEN COUNT(*) FILTER (WHERE is_disbursed) = 0 THEN NULL
           ELSE SUM(acquisition_spend) / COUNT(*) FILTER (WHERE is_disbursed) END
    unit: vnd
    format: "#,##0"
    higher_is_better: false
```

### Chỉ số trên grain khác — phễu lead

Vì `fact_lead` khác grain và không nối được ở mức cá thể ([02](02-data-model.md) §2.1), chỉ số phễu phải được khai báo riêng, có **ghi chú giả định bắt buộc**:

```yaml
  leads:
    label_vi: "Số lead"
    dataset: lead                # mart.mart_campaign_daily hoac raw.fact_lead
    sql: "SUM(leads)"
    unit: count
    format: "#,##0"

  lead_to_application_rate:
    label_vi: "Tỷ lệ lead thành hồ sơ"
    dataset: campaign_daily
    sql: |
      CASE WHEN SUM(leads) = 0 THEN NULL
           ELSE SUM(applications)::numeric / SUM(leads) END
    unit: ratio
    format: "0.0%"
    # Chuoi nay BAT BUOC xuat hien cung moi ket qua cua chi so nay
    caveat_vi: >
      Tỷ lệ tổng hợp ở mức chiến dịch, không phải attribution từng lead:
      bảng hồ sơ vay không có khoá nối về bảng lead (xem tài liệu 02, mục 2.1).
      Lead và hồ sơ được đếm độc lập rồi chia cho nhau trong cùng kỳ.
    allowed_dimensions: [campaign_id, channel, activity_date]
```

Trường `caveat_vi` không phải trang trí. Compiler gắn nó vào `EvidenceSet`, prompt của Narrator bắt buộc phải nhắc lại, và lớp kiểm tra L3 sẽ **từ chối** câu trả lời dùng chỉ số này mà không kèm chú thích.

## 5.3 Compiler: từ MetricRequest ra SQL

`app/semantic/compiler.py` sinh SQL theo khuôn cố định. Không có nối chuỗi từ dữ liệu người dùng.

```python
def compile(req: MetricRequest, catalog: Catalog) -> CompiledQuery:
    ds  = catalog.dataset_of(req.metric)                   # loi neu metric khong ton tai
    dims = [catalog.dimension(d, ds) for d in req.dimensions]  # loi neu dimension khong hop le
    mets = [catalog.metric(m) for m in req.metrics]

    select  = [f"{d.column} AS {d.name}" for d in dims]
    select += [f"({m.sql}) AS {m.name}" for m in mets]
    select += [f"COUNT(*) AS _n_rows"]                     # LUON kem co mau -> can cho 08 muc 4

    where, params = _compile_filters(req.filters, catalog) # chi bind param, khong noi chuoi
    if req.date_range:
        where.append(f"{ds.default_date_column} >= :d_from AND "
                     f"{ds.default_date_column} < :d_to")
        params |= {"d_from": req.date_range.start, "d_to": req.date_range.end_exclusive}

    sql = (f"SELECT {', '.join(select)} FROM {ds.table}"
           + (f" WHERE {' AND '.join(where)}" if where else "")
           + (f" GROUP BY {', '.join(d.name for d in dims)}" if dims else "")
           + (f" ORDER BY {_safe_order(req, mets, dims)}" if req.order_by else "")
           + f" LIMIT {min(req.limit or 100, catalog.max_rows)}")   # LUON co LIMIT

    return CompiledQuery(sql=sql, params=params, query_id=_hash(sql, params),
                         metrics=mets, dimensions=dims,
                         caveats=[m.caveat_vi for m in mets if m.caveat_vi])
```

Năm bất biến của compiler — mỗi cái chặn một lối bịa:

| Bất biến | Chặn được gì |
|---|---|
| Tên bảng và tên cột **chỉ** lấy từ catalog, không bao giờ từ input | Bịa tên cột/bảng |
| Giá trị filter luôn đi qua bind parameter | SQL injection và lỗi kiểu |
| Luôn có `LIMIT` | Truy vấn nổ bộ nhớ |
| Luôn thêm `COUNT(*) AS _n_rows` | Phát biểu so sánh trên mẫu quá nhỏ |
| `ORDER BY` chỉ nhận tên đã có trong SELECT | Bịa cột sắp xếp |

## 5.4 EvidenceSet — cầu nối giữa số liệu và ngôn ngữ

Kết quả truy vấn không được đưa cho LLM dưới dạng CSV thô. Nó được gói thành `EvidenceSet`, trong đó **mỗi ô có một địa chỉ**:

```json
{
  "evidence_id": "ev_7f3a",
  "generated_at": "2026-09-19T14:03:11+07:00",
  "data_version": "etl_run_42",
  "facts": [
    {
      "fact_id": "F1",
      "title": "Hiệu quả theo chiến dịch, 01/08–31/08/2026",
      "query_id": "q_9c21",
      "sql": "SELECT campaign_id, campaign_name, ...",
      "row_count": 6,
      "caveats": [],
      "columns": [
        {"name": "campaign_name", "label": "Chiến dịch", "unit": "text"},
        {"name": "romi",          "label": "ROMI",       "unit": "ratio", "format": "0.00"},
        {"name": "net_profit",    "label": "Lợi nhuận ròng", "unit": "vnd"},
        {"name": "_n_rows",       "label": "Cỡ mẫu",     "unit": "count"}
      ],
      "rows": [
        {"_ref": "F1.r1", "campaign_name": "Vay Lai - Zalo Remarketing",
         "romi": 6.20, "net_profit": 392498500, "_n_rows": 486},
        {"_ref": "F1.r2", "campaign_name": "Vay Tin Chap - Google Search",
         "romi": 1.60, "net_profit": 88164340,  "_n_rows": 478}
      ]
    }
  ],
  "derived": [
    {"fact_id": "D1", "expr": "F1.r1.romi / F1.r2.romi", "value": 3.875,
     "label": "Zalo gấp Google bao nhiêu lần về ROMI"}
  ]
}
```

Narrator tham chiếu số bằng `{{F1.r1.romi}}`. Bộ kiểm chứng phân giải thẻ đó về đúng một ô. Không phân giải được thì chặn. Xem [08](08-anti-hallucination.md) §3.

Khối `derived` cũng do **code** tính, không phải LLM — khi câu trả lời cần một phép so sánh mà SQL không trả thẳng ra (tỷ số, chênh lệch, phần trăm thay đổi), Planner khai báo biểu thức và `app/analytics/derive.py` tính, rồi nó trở thành một fact có địa chỉ như mọi fact khác.

## 5.5 Catalog chỉ số đầy đủ cho ba deliverable

### D1 — Dashboard hiệu quả chiến dịch

| Metric | Công thức rút gọn | Đơn vị |
|---|---|---|
| `leads` | `SUM(leads)` trên `mart_campaign_daily` | count |
| `applications` | `COUNT(*)` | count |
| `disbursed_loans` | `COUNT(*) FILTER (WHERE is_disbursed)` | count |
| `rejected_loans` | `COUNT(*) FILTER (WHERE is_rejected)` | count |
| `lead_to_application_rate` | `applications / leads` | % |
| `approval_rate` | `disbursed / applications` | % |
| `lead_to_disbursed_rate` | `disbursed / leads` | % |
| `total_loan_amount` | `SUM(loan_amount)` | VND |
| `avg_loan_amount` | `AVG(loan_amount)` — mẫu số chỉ gồm hồ sơ giải ngân | VND |
| `total_revenue` | `SUM(total_revenue)` | VND |
| `total_cost` | `SUM(total_cost)` | VND |
| `net_profit` | `SUM(net_profit)` | VND |
| `acquisition_spend` | `SUM(marketing_cost + lead_cost)` | VND |
| `cost_per_disbursed` | `acquisition_spend / disbursed` | VND |
| `romi` | `net_profit / acquisition_spend` | ratio |
| `profit_per_disbursed` | `net_profit / disbursed` | VND |
| `partner_fee_share` | `SUM(partner_fee) / SUM(total_cost)` | % |
| `credit_loss_rate` | `SUM(credit_loss) / SUM(loan_amount)` | % |
| `avg_days_late` | `AVG(max_dayslate)` trên hồ sơ đã giải ngân | ngày |

### D2 — Chân dung khách hàng tiềm năng

| Metric | Ghi chú |
|---|---|
| `customers` | `COUNT(DISTINCT customer_id)` |
| `repeat_customer_rate` | `max_loan_rank > 1` chia tổng khách — **bắt buộc kèm CI Wilson** |
| `avg_profit_per_customer` | trên `mart_customer_value` |
| `median_profit_per_customer` | trung vị chống lệch bởi đuôi dài (σ = 738k) |
| `clv_to_date` | `SUM(profit_to_date)` |
| `clv_predicted` | công thức ở [06](06-agent-design.md) §5 — luôn kèm khoảng |
| `app_adoption_rate` | `has_app` chia tổng |
| `avg_income`, `avg_age` | mô tả chân dung |
| `segment_size_share` | tỷ trọng phân khúc |
| `rejection_rate_by_reason` | cắt theo `reason_level_1` |
| `fraud_signal_rate` | `geo_location_match = false` |

### D3 — Hành động nâng CLV

| Metric | Vai trò |
|---|---|
| `dormant_customers` | Khách đã giải ngân, chưa vay lại, đủ điều kiện |
| `never_applied_customers` | 347 khách chưa có hồ sơ nào (DQ-07) |
| `uplift_potential_vnd` | Cỡ cơ hội, công thức ở [06](06-agent-design.md) §6 |
| `reloan_eligible_pool` | Khách thoả điều kiện tái vay |
| `expected_incremental_profit` | Ước lượng tác động, **luôn kèm khoảng và giả định** |

## 5.6 Đường thoát: free-form SQL có rào

Catalog không bao giờ phủ hết mọi câu hỏi. Khi Router không khớp được chỉ số nào, agent được phép dùng `sql_tool` — nhưng đường này đi qua năm cửa:

1. `sqlglot.parse_one()` — không parse được thì chặn.
2. Đúng **một** câu lệnh và phải là `SELECT`. Chặn CREATE/DROP/INSERT/UPDATE/DELETE/MERGE/ALTER/TRUNCATE/GRANT/COPY.
3. Duyệt AST: mọi `exp.Column` phải phân giải được về `(bảng, cột)` **có thật** trong snapshot catalog. Đây là lớp diệt hallucination schema, và nó bắt trên **cây cú pháp** chứ không phải trên chuỗi — so khớp chuỗi bị đánh bại bởi comment, hoa thường và lồng nhau.
4. Chỉ được chạm schema `mart`. Chặn `raw` và `ops`.
5. Bắt buộc có `LIMIT`; không có thì tự chèn `LIMIT 500`.
6. `EXPLAIN` chạy trước dưới chính role `mkt_agent_ro` — bắt lỗi kiểu và chi phí trước khi quét thật.
7. Nếu bật, chạy **self-consistency k=3**: sinh 3 SQL ở nhiệt độ cao hơn, chạy cả ba, gom cụm theo fingerprint kết quả. Cụm lớn nhất dưới 60% thì abstain.

Vòng sửa lỗi tối đa **3 lần**. Một vòng lặp không chặn trên là cách nhanh nhất để đốt hết quota 14 400 request/ngày cho đúng một câu hỏi.

## 5.7 Sửa catalog mà không cần dev

`config/semantic/metrics.yml` nằm ngoài code. Sửa một định nghĩa:

1. Sửa file (hoặc qua trang `/admin/metrics`).
2. Hệ thống validate: SQL có parse được không, dimension có tồn tại không, `format` có hợp lệ không.
3. Chạy `pytest tests/test_metrics_contract.py` — file này khẳng định các giá trị tham chiếu ở [02](02-data-model.md) §2.4 vẫn đúng.
4. Tăng `version`. Mọi `agent_trace` từ đó ghi phiên bản mới.

Test hợp đồng là thứ giữ cho việc sửa chỉ số không âm thầm phá dashboard:

```python
@pytest.mark.parametrize("campaign_id,expected_romi", [
    ("CMP-ZL-RL1",    6.20), ("CMP-GG-001",    1.60), ("CMP-FB-001",    1.31),
    ("CMP-TT-001",    0.67), ("CMP-PTN-MOMO", -0.41), ("CMP-PTN-BRK01", -1.85),
])
def test_romi_matches_reference(catalog, engine_ro, campaign_id, expected_romi):
    res = run_metric(catalog, engine_ro, "romi",
                     filters=[("campaign_id", "eq", campaign_id)],
                     date_range=("2026-08-01", "2026-09-01"))
    assert res.scalar() == pytest.approx(expected_romi, abs=0.01)
```

Đổi định nghĩa ROMI mà quên cập nhật giá trị tham chiếu thì CI đỏ. Đó chính là mục đích.
