# 08 — Bộ đo và cơ chế chống hallucination

> Tài liệu tham khảo được yêu cầu: [AWS — Detect hallucinations for RAG-based systems](https://aws.amazon.com/blogs/machine-learning/detect-hallucinations-for-rag-based-systems/). Phần §9 nói rõ ta lấy gì từ đó, và chỗ nào ta cố tình làm khác — vì bài toán của ta là analytics trên dữ liệu có cấu trúc, không phải RAG trên văn bản.

## 8.1 Luận điểm trung tâm

Trong RAG văn bản, "bằng chứng" là những đoạn prose mờ nhoè, nên gần như mọi cách kiểm tra đều phải nhờ một model khác đọc và phán xét. Ở bài toán này, bằng chứng là **một bảng số chính xác, đọc được bằng máy**.

Đó là một lợi thế lớn, và nó đảo ngược thứ tự ưu tiên: **phần lớn việc kiểm tra làm được một cách tất định — không gọi LLM, không tốn quota, không thêm độ trễ đáng kể, độ chính xác gần như tuyệt đối.**

```
                 do phu  <-------------------------> do chac chan
  L5 LLM judge     cao                                   thap
  L4 stats guard   trung binh                            cao
  L3 entity        hep                                   tuyet doi
  L2 numeric       hep                                   tuyet doi   <- ROI cao nhat
  L1 EXPLAIN       hep                                   tuyet doi
  L0 AST/schema    hep                                   tuyet doi
```

Thứ tự triển khai: **chặn từ thiết kế → kiểm tra tất định → LLM-judge → con người review**. Ai đảo thứ tự này sẽ trả tiền cho LLM-judge để bắt những lỗi mà một regex bắt được miễn phí.

Ràng buộc thực tế củng cố lựa chọn: MaaS của GreenNode giới hạn **10 request/phút cho cả tài khoản**. Một kiến trúc dựa vào LLM-judge để đảm bảo chất lượng sẽ không chạy nổi ở quy mô demo.

## 8.2 Bảy lớp

| Lớp | Bắt lỗi gì | Gọi LLM | Độ trễ | Tất định |
|---|---|---|---|---|
| **L0** Kiểm tra SQL tĩnh (AST + schema binding) | Bịa bảng/cột, DML, thiếu LIMIT | 0 | ~5 ms | ✅ |
| **L1** `EXPLAIN` chạy thử dưới role chỉ đọc | Lỗi kiểu, truy vấn quá nặng | 0 | ~20 ms | ✅ |
| **L2** **Numeric grounding (PCN)** | **Số bịa hoặc trích sai** | 0 | ~1 ms | ✅ |
| **L3** Entity grounding | Bịa tên chiến dịch/phân khúc/kênh | 0 | ~1 ms | ✅ |
| **L4** Stats guard | So sánh trên nhiễu, mẫu quá nhỏ, suy nhân quả | 0 | ~10 ms | ✅ |
| **L5** LLM judge (kiểu AWS) | Suy diễn không có cơ sở, lạc đề | 1 (bất đồng bộ) | ngoài đường găng | ❌ |
| **L6** Cổng abstain + Trust Score + telemetry | Ra quyết định cuối | 0 | ~1 ms | ✅ |

L0 và L1 chỉ chạy trên đường free-form SQL. Đường chính đi qua semantic layer nên đã an toàn về schema từ trong thiết kế.

## 8.3 L2 — Numeric grounding: lớp quan trọng nhất

### Ý tưởng

Áp dụng giao thức **Proof-Carrying Numbers** ([arXiv:2509.06902](https://arxiv.org/abs/2509.06902)): số được phát ra dưới dạng **token gắn với claim**, một bộ verifier kiểm tra từng token theo một **chính sách đã khai báo** (bằng tuyệt đối, làm tròn, dung sai, bí danh đơn vị), và **việc xác minh nằm ở tầng render chứ không ở model**. Chỉ số nào qua được kiểm tra mới được đánh dấu đã xác minh; mọi thứ khác mặc định là chưa xác minh. Nguyên tắc: *niềm tin chỉ đến từ bằng chứng, còn sự vắng mặt của dấu xác minh chính là lời cảnh báo.*

Áp vào hệ thống này:

```
1. Narrator xuat:  "ROMI dat {{F1.r1.romi}}, gap {{D1.value}} lan Google."
2. Verifier phan giai tung the ve dung mot o trong EvidenceSet.
3. Renderer thay the -> "ROMI dat 6,20, gap 3,88 lan Google."
4. The khong phan giai duoc  -> CHAN.
5. Chu so tran khong nam trong the -> CHAN (tru allowlist).
```

Bước 5 là chốt chặn. Nếu model phớt lờ hướng dẫn và viết thẳng "6,20", con số đó không phải thẻ, nên bị quét regex bắt được và bị chặn.

### Thuật toán

```python
NUM_RE = re.compile(r"""
    (?<![\w.])                      # khong dinh vao chu
    -?\d{1,3}(?:[.\s]\d{3})*        # 1.234.567 hoac 1 234 567  (kieu vi-VN)
    (?:,\d+)?                       # phan thap phan dung dau phay
    \s*(?:%|tỷ|triệu|nghìn|VND|đ)?  # don vi tieng Viet
    | -?\d+(?:\.\d+)?%?             # dang so thuan
""", re.VERBOSE)

ALLOWLIST = {
    "years":     lambda v: 2000 <= v <= 2100 and float(v).is_integer(),
    "ordinals":  lambda v: v in range(1, 11),       # "top 5", "3 de xuat"
    "literals":  lambda v: v in (0, 1, 2, 100),     # "mot nua", "100%"
}

def check_numeric_grounding(text: str, ev: EvidenceSet, policy: NumericPolicy) -> CheckResult:
    unresolved_tags, resolved = [], []
    for tag in TAG_RE.finditer(text):               # {{F1.r1.romi}}
        cell = ev.resolve(tag.group(1))
        (resolved if cell is not None else unresolved_tags).append(tag.group(1))

    rendered = ev.substitute(text)                  # thay the -> so da dinh dang
    bare = []
    for m in NUM_RE.finditer(strip_substituted_spans(rendered)):
        val = parse_vi_number(m.group())
        if any(f(val) for f in ALLOWLIST.values()):
            continue
        if ev.matches_any_cell(val, policy) or ev.matches_derived(val, policy):
            continue                                # so dung nhung viet thang -> canh bao, khong chan
        bare.append(m.group())

    total = len(resolved) + len(unresolved_tags) + len(bare)
    rate  = len(resolved) / total if total else 1.0
    return CheckResult(
        name="numeric_grounding", passed=not unresolved_tags and not bare,
        score=rate,
        details={"resolved": len(resolved), "unresolved_tags": unresolved_tags,
                 "ungrounded_numbers": bare},
        severity=Severity.BLOCK,
    )
```

### Chính sách so khớp

Phải khai báo tường minh, vì đây chính là chỗ các bộ kiểm tra dùng LLM hay sai — làm tròn và lệch đơn vị.

```yaml
# config/verify.yaml
numeric_policy:
  default:          { mode: round, decimals: 2 }
  vnd:              { mode: rel_tol, tol: 0.005 }   # sai so 0,5% do lam tron khi hien thi
  ratio:            { mode: round, decimals: 4 }
  percent:          { mode: round, decimals: 1, alias: [ratio_x100] }
  count:            { mode: exact }
  aliases:
    "tỷ":     1_000_000_000
    "triệu":  1_000_000
    "nghìn":  1_000
```

`alias: [ratio_x100]` xử lý trường hợp EvidenceSet lưu `0.488` còn câu trả lời viết `48,8%`. Không có quy tắc này thì mọi tỷ lệ phần trăm đều báo động giả.

### Chỉ số

| Chỉ số | Định nghĩa | Ngưỡng |
|---|---|---|
| `numeric_grounding_rate` | thẻ phân giải được / tổng số thực thể số | **phải = 1,0** |
| `ungrounded_number_count` | số chữ số trần không khớp ô nào | **phải = 0** |
| `bare_number_count` | số viết thẳng nhưng vẫn khớp ô | ≤ 2 → cảnh báo, không chặn |

`numeric_grounding_rate < 1.0` là **hard fail**. Không có ngoại lệ, không có trung bình có trọng số. Một con số bịa trong báo cáo marketing là loại lỗi mà người dùng thực sự nhận ra và nhớ mãi.

## 8.4 L4 — Stats guard: lớp mà bộ dữ liệu này bắt buộc phải có

Bộ dữ liệu có sẵn một cái bẫy hoàn hảo ([02](02-data-model.md) §2.4): lợi nhuận trung bình theo nghề nghiệp dao động 180k–220k trên n≈360 mỗi nhóm, trong khi độ lệch chuẩn cá thể là 738k. Một LLM không bị rào sẽ tuyên bố **"Freelancer là nhóm sinh lời nhất"** — đúng về mặt sắp xếp bảng, nhưng vô nghĩa về mặt thống kê, và nếu ai đó phân bổ ngân sách theo đó thì đã ra quyết định dựa trên nhiễu.

Không lớp grounding nào bắt được lỗi này, vì con số 220 200 **thật sự có** trong kết quả truy vấn. Cần một lớp riêng.

### Cơ chế

Trước bước NARRATE, mọi cặp so sánh tiềm năng được tính sẵn và đóng dấu:

```python
def guard_comparisons(fact: Fact, cfg: StatsConfig) -> list[Comparison]:
    out = []
    for a, b in itertools.combinations(fact.rows, 2):
        for metric in fact.comparable_metrics:
            if metric.unit == "ratio":                     # so sanh hai ty le
                res = two_proportion_ztest(a[metric.num], a[metric.den],
                                           b[metric.num], b[metric.den])
            else:                                          # so sanh hai trung binh
                res = bootstrap_mean_diff(a.raw_values, b.raw_values, n=2000)

            out.append(Comparison(
                left=a["_ref"], right=b["_ref"], metric=metric.name,
                diff=a[metric.name] - b[metric.name],
                p_value=res.p_value, ci=res.ci,
                effect_size=res.effect_size,
                n_left=a["_n_rows"], n_right=b["_n_rows"],
                significant=(res.p_value < cfg.alpha                 # 0.05
                             and abs(res.effect_size) >= cfg.min_effect   # 0.2 (Cohen's d)
                             and min(a["_n_rows"], b["_n_rows"]) >= cfg.min_n),  # 30
                verdict_vi=_verdict(res, cfg),
            ))
    return out
```

Kết quả đi vào `EvidenceSet.comparisons`, và prompt của Narrator ràng buộc: **`significant = false` thì không được dùng từ so sánh hơn kém.**

Lớp kiểm tra hậu kỳ bắt vi phạm bằng cách tìm ngôn ngữ so sánh trong câu trả lời:

```yaml
comparative_markers_vi:
  - "cao hơn"  - "thấp hơn"  - "tốt hơn"  - "kém hơn"
  - "vượt trội" - "dẫn đầu"  - "tốt nhất" - "kém nhất"
  - "hiệu quả hơn" - "gấp" - "nhất"
causal_markers_vi:
  - "vì" - "do" - "dẫn đến" - "khiến" - "nhờ" - "gây ra" - "làm cho"
```

Với mỗi câu chứa marker so sánh, verifier tìm cặp `(left, right)` mà câu đó đang nói tới; nếu `significant = false` thì → **BLOCK**. Với marker nhân quả, nếu `EvidenceSet` không có mục `causal_evidence` (chỉ sinh ra từ dữ liệu A/B test, mà PoC này không có) thì → **WARN**, và câu bị viết lại theo ngôn ngữ tương quan.

### Cỡ mẫu

| Quy tắc | Ngưỡng | Hành vi |
|---|---|---|
| `min_sample_size` cho mọi chỉ số tỷ lệ | 30 | n < 30 → không trả số, trả `INSUFFICIENT_SAMPLE` |
| Cảnh báo cỡ mẫu | n < 100 | Trả số nhưng bắt buộc kèm CI và cảnh báo hiển thị |
| CI Wilson cho mọi tỷ lệ | luôn luôn | Hiện dạng `20,7% (CI95: 18,0%–23,7%, n=797)` |

Nhóm thu nhập ≥20M (n=29) rơi đúng dưới ngưỡng 30 — nó trở thành ca kiểm thử số một của bộ golden set.

## 8.5 L3 — Entity grounding

Đơn giản nhưng cần thiết: mọi tên riêng xuất hiện trong câu trả lời phải có thật.

```python
def check_entity_grounding(text: str, ev: EvidenceSet, catalog: Catalog) -> CheckResult:
    known = ev.all_string_values() | catalog.all_dimension_values()  # cache 5 phut
    mentioned = extract_proper_nouns_vi(text)   # Ten hoa, ma CMP-*, PRD-*, CUS-*
    unknown = [m for m in mentioned if not fuzzy_in(m, known, threshold=0.92)]
    return CheckResult("entity_grounding", passed=not unknown,
                       score=1 - len(unknown)/max(len(mentioned), 1),
                       details={"unknown_entities": unknown}, severity=Severity.BLOCK)
```

Bắt được những lỗi như: bịa ra "chiến dịch Instagram Stories" (không tồn tại), nhầm `CMP-FB-002` (chỉ có `-001`), hay chế ra tên phân khúc không nằm trong `SEGMENT_RULES`.

Cũng ở lớp này, kiểm tra **caveat bắt buộc**: nếu EvidenceSet có chỉ số mang `caveat_vi` (ví dụ `lead_to_application_rate`) mà câu trả lời không nhắc tới ý đó, → WARN và tự động chèn caveat vào cuối.

## 8.6 L5 — LLM judge

Đây là nơi tài liệu AWS được áp dụng gần như nguyên bản, với hai điều chỉnh.

**Áp dụng:** cấu trúc prompt *system → task → định dạng → quy tắc chấm → 3 few-shot → ràng buộc*, `temperature = 0`, `max_tokens` nhỏ, chi phí **cố định 1 lượt gọi** bất kể độ dài bằng chứng. Prompt cụ thể ở [07](07-prompt-fewshot.md) §7.3.

**Điều chỉnh 1 — ba nhãn thay vì một điểm.** Thay vì chỉ trả điểm 0–1, judge trả nhãn cho từng claim: `SUPPORTED` / `CONTRADICTED` / `NOT_ENOUGH_INFO` (theo cách RefChecker gom nhóm mềm). Ba nhãn ánh xạ sang ba hành vi UX khác nhau, còn một điểm duy nhất thì không:

| Tín hiệu | Nghĩa | Hành vi |
|---|---|---|
| `contradiction_rate > 0` | Dữ liệu nói ngược lại | **BLOCK** |
| `neutral_rate > 0.3` | Dữ liệu không nói được điều đó | **HEDGE** — thêm rào đón, hiện bảng số |
| `entailment_rate ≥ 0.9` | Mọi phát biểu có chống đỡ | PASS |

**Điều chỉnh 2 — chạy bất đồng bộ.** Vì trần 10 RPM, judge không nằm trên đường găng. Câu trả lời được trả ngay sau khi qua L0–L4 (đều tất định, dưới 50 ms), huy hiệu Trust hiện trạng thái `đang kiểm tra`, rồi cập nhật qua SSE khi judge xong. Nếu judge phát hiện mâu thuẫn, UI đổi huy hiệu sang đỏ và hiện cảnh báo ngay trên câu trả lời đã hiển thị.

Đánh đổi này chấp nhận được **chính xác vì** các lớp tất định đã là lớp chính. Nếu L2/L3/L4 là lớp phụ thì việc chạy judge bất đồng bộ sẽ là liều lĩnh.

Ghi chú về kỳ vọng hiệu năng: trong đo lường của AWS, bộ judge dùng LLM đạt độ chính xác 0,75 với precision 0,94 nhưng recall chỉ 0,53 — nghĩa là **nó bỏ sót gần một nửa**. Đó là lý do nó không thể là lớp phòng thủ chính. Ngược lại, bộ so khớp token đạt precision 0,96 ở recall 0,03 — hình mẫu của một bộ lọc rẻ và đáng tin khi nó lên tiếng. Lớp L2 của ta cùng hình mẫu đó nhưng recall cao hơn hẳn, vì bằng chứng của ta có cấu trúc.

## 8.7 L6 — Trust Score và quyết định

Không lấy trung bình cộng các điểm khác bản chất. Dùng **tích có trọng số kèm tập hard-fail**:

```python
def compute_trust(checks: dict, cfg: VerifyConfig) -> TrustScore:
    hard_fail = (
        checks["numeric_grounding"].score < 1.0
        or checks["entity_grounding"].details["unknown_entities"]
        or checks["stats_guard"].has_unsupported_comparison
        or checks.get("judge", Judge()).contradiction_rate > 0
        or not checks["sql_validation"].passed
    )
    if hard_fail:
        return TrustScore(value=0.0, band=Band.BLOCKED,
                          reasons=[c.name for c in checks.values() if not c.passed])

    v = (cfg.w_schema  * checks["sql_validation"].score
       + cfg.w_numeric * checks["numeric_grounding"].score
       + cfg.w_entity  * checks["entity_grounding"].score
       + cfg.w_stats   * checks["stats_guard"].score
       + cfg.w_judge   * checks.get("judge", Judge(entailment_rate=1.0)).entailment_rate
       + cfg.w_consist * checks.get("self_consistency", Consist(1.0)).top_cluster_share
    ) / cfg.total_weight
    band = Band.PASS if v >= cfg.t_high else Band.HEDGE if v >= cfg.t_low else Band.ABSTAIN
    return TrustScore(value=v, band=band, components=checks)
```

Trọng số khởi điểm trong `config/verify.yaml` (và phải được thay bằng hồi quy logistic trên golden set khi đã có đủ nhãn):

```yaml
weights:
  schema: 0.15      # tat dinh
  numeric: 0.25     # tat dinh, quan trong nhat
  entity: 0.10      # tat dinh
  stats: 0.20       # tat dinh
  judge: 0.20       # LLM
  consistency: 0.10 # chi duong free-form SQL
thresholds:
  t_high: 0.85      # HIEU CHINH tren golden set, khong phai con so tu tai lieu nao
  t_low:  0.60
alpha: 0.05
min_effect_size: 0.2
min_sample_size: 30
```

**Ngưỡng `t_high` và `t_low` không được sao chép từ bất kỳ tài liệu nào.** Chúng được chọn bằng cách vẽ đường cong coverage–risk trên golden set và lấy điểm vận hành sao cho tỷ lệ trả lời sai trong số câu đã trả lời ≤ 2%. Quy trình ở [13](13-testing-eval.md) §5.

### Bốn hành vi đầu ra

| Band | Người dùng thấy | Huy hiệu |
|---|---|---|
| `PASS` | Câu trả lời đầy đủ | 🟢 Đã kiểm chứng · 12/12 số khớp |
| `HEDGE` | Câu trả lời + rào đón + **bảng số mở sẵn** | 🟡 Cần đối chiếu · lý do cụ thể |
| `ABSTAIN` | Không diễn giải, chỉ bảng số thô + câu hỏi làm rõ | ⚪ Không đủ cơ sở |
| `BLOCKED` | Sinh lại 1 lần; vẫn fail thì chỉ hiện bảng số | 🔴 Đã chặn phần diễn giải |

Hàm mục tiêu được chọn có chủ ý, theo tinh thần của TrustSQL: **một câu trả lời sai bị phạt nặng hơn một lần từ chối.** Với một agent phân tích kinh doanh, đó là cách tính điểm đúng.

## 8.8 Telemetry

Mỗi lượt trả lời ghi một dòng `ops.agent_trace` (DDL ở [03](03-database-choice.md) §3.4). Cột `checks` là JSONB:

```json
{
  "sql_validation":  {"passed": true, "score": 1.0, "unbound_identifiers": []},
  "numeric_grounding": {"passed": true, "score": 1.0,
                        "resolved": 12, "unresolved_tags": [], "ungrounded_numbers": []},
  "entity_grounding": {"passed": true, "score": 1.0, "unknown_entities": []},
  "stats_guard": {"passed": true, "score": 1.0,
                  "comparisons": 15, "significant": 4, "blocked_claims": []},
  "judge": {"entailment_rate": 0.92, "neutral_rate": 0.08, "contradiction_rate": 0.0,
            "model": "...", "prompt_version": "1.0.0", "latency_ms": 1840},
  "self_consistency": null
}
```

Ba cột **bắt buộc** không được bỏ: `prompt_version`, `model_name`, `profile`. Thiếu chúng thì khi chất lượng tụt, không ai phân biệt được là do sửa prompt, đổi model hay dữ liệu thay đổi.

### Bảng theo dõi sức khoẻ

`GET /admin/quality` hiển thị theo ngày:

| Chỉ số | Mục tiêu | Ý nghĩa nếu lệch |
|---|---|---|
| `numeric_grounding_rate` (trung bình) | **1,000** | Tụt dưới 1 là sự cố nghiêm trọng, điều tra ngay |
| `block_rate` | < 5% | Cao → prompt đang trôi hoặc model yếu |
| `abstain_rate` | 5–15% | Quá thấp → rào lỏng. Quá cao → rào chặt hoặc thiếu chỉ số |
| `hedge_rate` | < 25% | |
| `avg_trust_score` | > 0,88 | |
| `judge_contradiction_rate` | < 1% | |
| `p95_latency_ms` | < 8 000 | |
| `llm_calls_per_answer` | ≤ 2 | Vượt → sẽ đụng trần 10 RPM |

## 8.9 Đối chiếu với tài liệu AWS

| Nội dung trong tài liệu AWS | Ta làm gì |
|---|---|
| 4 cách phát hiện: LLM-judge, tương đồng ngữ nghĩa, BERT stochastic, tương đồng token | Lấy **LLM-judge** (L5). Bỏ tương đồng ngữ nghĩa và BERT stochastic — tốn K và N+1 lượt gọi, không chịu nổi trần 10 RPM, và với dữ liệu có cấu trúc thì L2 đã mạnh hơn |
| Điểm hallucination là số thực 0–1, 0 = bám context | Giữ thang đó cho L5, nhưng bổ sung ba nhãn để ánh xạ sang ba hành vi UX |
| Cấu trúc prompt judge + `temperature=0`, `max_tokens=100` | Áp dụng nguyên bản ([07](07-prompt-fewshot.md) §7.3) |
| "Tự hiệu chỉnh ngưỡng theo domain" | Làm đúng vậy: coverage–risk trên golden set. Không sao chép con số ngưỡng của ai |
| Khuyến nghị **cascade**: lọc rẻ trước, judge sau | Chính là kiến trúc L0→L6, nhưng bộ lọc rẻ của ta mạnh hơn nhiều vì bằng chứng có cấu trúc |
| Chi phí: token-sim 0 lượt, judge 1 lượt cố định | Là lý do ta đặt mọi thứ tất định lên trước và chỉ giữ đúng 1 lượt judge, chạy bất đồng bộ |
| Kết quả: judge acc 0,75 / P 0,94 / **R 0,53** | Bằng chứng cho thấy judge **không đủ** làm lớp phòng thủ chính — nó bỏ sót gần một nửa |

**Điểm khác biệt lớn nhất:** tài liệu AWS viết cho ngữ cảnh mà bằng chứng là văn bản. Ta có bằng chứng là bảng số, nên ta thêm được ba lớp mà bài viết đó không có, và chính ba lớp này mới là phòng tuyến chính: **numeric grounding (PCN), stats guard, và semantic layer chặn ngay từ khâu thiết kế.**

## 8.10 Danh mục lỗi và lớp bắt được

Dùng để viết test — mỗi dòng là một ca kiểm thử trong golden set.

| # | Kiểu lỗi | Ví dụ trên bộ dữ liệu này | Lớp bắt |
|---|---|---|---|
| H1 | Bịa số | "ROMI của Facebook là 2,4" (thật: 1,31) | L2 |
| H2 | Trích sai số | Lấy `net_profit` của dòng khác | L2 |
| H3 | Lẫn đơn vị | Viết "6,2%" cho ROMI 6,20 lần | L2 (policy) |
| H4 | Bịa tên | "chiến dịch Instagram Stories" | L3 |
| H5 | So sánh trên nhiễu | "Freelancer sinh lời nhất" | L4 |
| H6 | Mẫu quá nhỏ | Kết luận từ nhóm ≥20M (n=29) | L4 |
| H7 | Suy nhân quả | "Cài app làm tăng lợi nhuận 80k" | L4 + L5 |
| H8 | Bỏ caveat | Nêu tỷ lệ lead→app mà không nói là tỷ lệ tổng hợp | L3 |
| H9 | Bịa cột SQL | `fact_loan.campaign_id` | L0 |
| H10 | Sai mẫu số | `SUM(loan_amount)/COUNT(*)` gồm cả hồ sơ bị từ chối | Semantic layer (chặn từ thiết kế) |
| H11 | Ngoại suy thời gian | "Xu hướng tháng 8 so với tháng 7" | Semantic layer (DQ-03) + L4 |
| H12 | Diễn giải bảng rỗng | "Doanh thu tăng 12%" khi không có dòng nào | L2 + L6 |
| H13 | Lạc đề | Trả lời chuyện không được hỏi | L5 |
| H14 | Đọc ngược dấu | Gọi ROMI −1,85 là "hiệu quả" | L5 + `higher_is_better` |
| H15 | **Trung bình che cơ cấu** | "Lợi nhuận TB mỗi khách 199 629 VND" mà không nói trung vị là −86 175 và 53,8% khách lỗ | L4 skew guard + `must_report_with` |
| H16 | Ngoại suy tuyến tính từ trung bình | "1 000 khách mới ≈ 200 triệu lợi nhuận" | L4 skew guard |
| H17 | Chỉ số hư danh | "Broker có lead→hồ sơ cao nhất nên là chiến dịch tốt nhất" | L4 + playbook bắt buộc kèm ROMI |

### Skew guard — lớp con của L4

Kích hoạt khi `|mean − median| / |mean| > 0,3` **hoặc** tỷ lệ giá trị âm > 30%. Khi kích hoạt, chỉ số trung bình **không được** trả về một mình: `EvidenceSet` bắt buộc kèm `median` và `negative_share`, và prompt của Narrator yêu cầu nêu cả hai.

Với bộ dữ liệu này, điều kiện kích hoạt luôn đúng ở mức toàn tập: mean 199 629 · median −86 175 · negative_share 53,8%. Tham số ở `config/analytics.yaml → stats.skew_guard`.

## 8.11 Thứ tự triển khai

Xây theo đúng thứ tự này, vì giá trị mang lại giảm dần còn chi phí tăng dần:

1. **Semantic layer + role chỉ đọc** — chặn H9, H10 ngay từ thiết kế. Đây là phần nền.
2. **L2 numeric grounding + thẻ PCN** — chặn H1, H2, H3, H12. Không gọi LLM, vài chục dòng code, bắt đúng loại lỗi mà người dùng nhận ra.
3. **L4 stats guard** — chặn H5, H6, H7, H11. Bộ dữ liệu này bắt buộc phải có lớp này.
4. **L3 entity grounding + kiểm tra caveat** — chặn H4, H8.
5. **Golden set 100 ca + CI** — không có nó thì bốn bước trên không đo được.
6. **L5 LLM judge, chỉ ghi log, chưa chặn** — thu thập dữ liệu để hiệu chỉnh.
7. **Hiệu chỉnh ngưỡng, rồi mới bật cổng chặn.**
8. **L0/L1/self-consistency** — chỉ cần khi mở đường free-form SQL.

Bước 1–4 không tốn lượt gọi LLM nào và đã phủ 11 trên 14 kiểu lỗi.
