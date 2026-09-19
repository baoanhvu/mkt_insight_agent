# Nguồn kiểm chứng

Các khẳng định về nền tảng GreenNode và về kỹ thuật chống hallucination trong bộ tài liệu này được tra từ nguồn chính thức, không suy đoán. Dưới đây là đường dẫn để bạn tự đối chiếu.

## GreenNode / VNG Cloud

| Chủ đề | Nguồn |
|---|---|
| Bộ skill AgentBase | https://github.com/vngcloud/greennode-agentbase-skills |
| Hợp đồng runtime (cổng 8080, `GET /health`) | `skills/agentbase/references/runtime-contract.md` trong repo trên |
| Scaffold dự án (`main.py`, `.greennode.json`) | `skills/agentbase-wizard/references/init.md` |
| Thao tác deploy, Container Registry | `skills/agentbase-deploy/references/{runtime-ops,cr-ops}.md` |
| Tài liệu nền tảng | https://docs.greennode.ai/ai-stack/agent-base/agent-runtime/runtime-reference.md |
| Filesystem ephemeral, không có storage service riêng | https://docs.greennode.ai/ai-stack/agent-base/faq.md |
| Network mode PUBLIC / VPC, yêu cầu VPC Peering | https://docs.greennode.ai/ai-stack/agent-base/private-networking.md |
| MaaS OpenAI-compatible, base URL, giới hạn 10 RPM / 14 400 req/ngày | https://docs.greennode.ai/ai-stack/model-as-a-service/maas-api.md |
| Catalog model (đối chiếu tên model trong sổ tay BTC) | https://docs.greennode.ai/ai-stack/model-as-a-service/available-models.md |
| vDB RDS — PostgreSQL, Public/Private Endpoint, Security Group | https://docs.greennode.ai/vdb.md |
| vStorage S3-compatible (`https://hcm04.vstorage.vngcloud.vn`) | https://docs.greennode.ai/ai-stack/agent-base/faq.md |

### Ba điểm cần lưu ý khi đối chiếu với sổ tay BTC

1. **"Qwen 3.5 27B" không xuất hiện trong catalog MaaS chính thức.** Các bản Qwen được liệt kê là Qwen 3.7 Plus, Qwen 3.6 Plus, Qwen 3.6 Flash. MiniMax M2.5 và Gemma 4 31B-IT thì có. → Phải chạy `aip.sh models list --status ENABLED` lấy mã thật.
2. **Mẫu URL endpoint `https://endpoint-<uuid>.agentbaseruntime.aiplatform.vngcloud.vn/` trong sổ tay không có trong tài liệu chính thức** — tài liệu chỉ ghi `https://<default-url>`. Đọc trường `url` từ API sau khi deploy thay vì tự ghép chuỗi.
3. **Tài liệu chính thức có hai phiên bản khác nhau cho việc lấy token IAM** (khác host, khác cấu trúc response). Dùng `get_token.sh` của bộ skill thay vì tự viết.

## Chống hallucination

| Chủ đề | Nguồn |
|---|---|
| **Tài liệu người đặt bài yêu cầu tham khảo** | https://aws.amazon.com/blogs/machine-learning/detect-hallucinations-for-rag-based-systems/ |
| Proof-Carrying Numbers — giao thức xác minh số ở tầng render, fail-closed | https://arxiv.org/abs/2509.06902 |
| RAGAS — faithfulness, answer relevancy, context precision/recall | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ |
| RAGAS — chỉ số cho SQL, công thức execution accuracy | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/sql/ |
| RAGAS — quy trình eval text-to-SQL, lược đồ golden set 4 trường | https://docs.ragas.io/en/stable/howtos/applications/text2sql/ |
| Bedrock Guardrails — contextual grounding check, ngữ nghĩa ngưỡng | https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html |
| RefChecker — gom nhóm mềm entailment/neutral/contradiction | https://github.com/amazon-science/RefChecker · https://arxiv.org/pdf/2405.14486 |
| SelfCheckGPT — tự nhất quán qua nhiều mẫu | https://arxiv.org/abs/2303.08896 |
| FActScore — phân rã thành atomic facts | https://arxiv.org/abs/2305.14251 |
| SQLHD — phân loại hallucination text-to-SQL (schema-linking vs logical-synthesis) | https://arxiv.org/abs/2512.22250 |
| CSC-SQL — self-consistency theo kết quả thực thi | https://arxiv.org/abs/2505.13271 |
| Nghiên cứu selective prediction — AUROC của self-consistency vs LLM verifier | https://arxiv.org/html/2607.06799v1 |
| Ước lượng độ tin cậy để phát hiện lỗi text-to-SQL | https://arxiv.org/pdf/2501.09527 |
| TrustSQL — chấm điểm có phạt, khuyến khích abstain | https://arxiv.org/abs/2403.15879 |
| Spider — phân biệt Exact Match và Execution Accuracy | https://arxiv.org/pdf/1809.08887 |

### Những con số được trích dẫn trong tài liệu, và chúng đến từ đâu

| Con số dùng ở | Giá trị | Nguồn |
|---|---|---|
| [08](08-anti-hallucination.md) §8.6, §8.9 | Judge dùng LLM: accuracy 0,75 · precision 0,94 · **recall 0,53** | Bài viết AWS, bảng kết quả |
| [08](08-anti-hallucination.md) §8.6 | Token similarity: precision 0,96 · recall 0,03 | Bài viết AWS |
| [08](08-anti-hallucination.md) §8.9 | Chi phí: token-sim 0 lượt · judge 1 lượt cố định · BERT stochastic N+1 lượt | Bài viết AWS |
| [13](13-testing-eval.md) §13.6 | Self-consistency AUROC ≈ 0,67 · LLM verifier ≈ 0,77 · hợp nhất 2 nhà cung cấp ≈ 0,82 | Nghiên cứu selective prediction |
| [13](13-testing-eval.md) §13.4 | Golden set quy mô khởi điểm ~100 ca, chia đều theo độ khó | Hướng dẫn eval text-to-SQL của RAGAS |

**Không có nguồn nào công bố một ngưỡng chặn đúng cho mọi domain.** Bản thân bài viết AWS nói rõ phải tự hiệu chỉnh theo domain. Mọi con số ngưỡng trong `config/verify.yaml` là chỗ đặt tạm, phải hiệu chỉnh trên golden set của chính dự án này trước khi bật cổng chặn — quy trình ở [13](13-testing-eval.md) §13.6.

## Dữ liệu

Mọi số liệu nghiệp vụ trong [02 §2.4](02-data-model.md) được đo trực tiếp từ `data/full_schema_mock_v2.xlsx` bằng pandas ngày 2026-09-19, không phải ước lượng. Chúng đồng thời là bộ đối chứng cho `tests/test_metrics_contract.py`.
