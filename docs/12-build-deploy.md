# 12 — Build, chạy local và deploy lên GreenNode AgentBase

> Tài liệu này bám theo `HD_cua_BTC/3. MSB x GreenNode AI Hackathon Training 2026.md`, và bổ sung những chi tiết mà sổ tay không nêu nhưng tài liệu nền tảng có quy định.

## 12.1 Bước 1 — Import AgentBase Skills (bắt buộc)

Sổ tay BTC nêu ba cách. Bộ skill được phát hành dưới dạng **plugin marketplace**, không phải thư viện Python:

```bash
claude plugin marketplace add vngcloud/greennode-agentbase-skills
```

Hoặc tải/clone repo rồi đặt cây `skills/` vào `.claude/skills/` của project. Trước khi dùng bất kỳ thao tác nền tảng nào, đặt hai biến:

```bash
export GREENNODE_CLIENT_ID="<service-account-client-id>"
export GREENNODE_CLIENT_SECRET="<service-account-secret>"
```

Bộ skill gồm 10 nhóm, ta dùng chủ yếu bốn nhóm đầu:

| Skill | Dùng để |
|---|---|
| `agentbase-llm` | Tạo API key MaaS, **liệt kê và bật model** — bắt buộc chạy trước khi code ([10](10-config-secrets.md) §10.4) |
| `agentbase-deploy` | Build/push image lên Container Registry, tạo và cập nhật Runtime |
| `agentbase-monitor` | Xem log và metric của runtime sau khi deploy |
| `agentbase-identity` | Quản lý agent identity, xoay credential — dùng khi rời khỏi giai đoạn PoC |
| `agentbase-wizard` | Scaffold dự án 9 bước, `agentbase-gateway`, `agentbase-policy`, `agentbase-memory`, `agentbase-teardown` | |

Script hữu ích nằm ở `.claude/skills/agentbase/scripts/`: `get_token.sh`, `aip.sh`, `cr.sh`, `runtime.sh`, `docker_login.sh`, `vserver.sh`.

> **Đừng tự viết đoạn lấy token IAM.** Tài liệu chính thức có hai phiên bản khác nhau (khác host, khác cấu trúc response). Dùng `get_token.sh` của bộ skill.

## 12.2 Cấu trúc file mà AgentBase mong đợi

Scaffold chuẩn đặt các file **ngay tại thư mục gốc project**, không đặt trong thư mục con:

| File | Bắt buộc | Nội dung |
|---|---|---|
| `main.py` | ✅ | Entrypoint, đúng tên này ([11](11-module-spec.md) §11.2) |
| `Dockerfile` | ✅ | `python:3.13-slim`, `EXPOSE 8080`, `CMD ["python","main.py"]` |
| `requirements.txt` | ✅ | Phải có `greennode-agentbase` |
| `.greennode.json` | ✅ | `{"client_id":"","client_secret":"","agent_identity":""}` |
| `.env.example` | | `GREENNODE_*`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` |
| `.dockerignore` | | Loại `data/`, `docs/`, `.venv/`, `tests/` |

**Không có file `agent.yaml` hay `agentbase.yaml` hay manifest nào.** Cấu hình chỉ gồm `.greennode.json` và biến môi trường. Nếu ai đó tìm một file manifest thì sẽ không thấy, vì nó không tồn tại.

## 12.3 Hợp đồng runtime — hai yêu cầu cứng

1. **Lắng nghe cổng 8080.** Nền tảng định tuyến toàn bộ traffic vào đây.
2. **`GET /health` trả HTTP 200.** Dùng để đánh dấu runtime `ACTIVE`.

Container thoả hai điều này sẽ deploy được và đạt trạng thái ACTIVE. Cách nó phục vụ nghiệp vụ — route nào, payload ra sao — là hoàn toàn tự do. Đó là lý do ta phục vụ được dashboard, SSE chat và trang admin trong cùng một image.

Một quy tắc mềm nhưng quan trọng: **stateless**. Không giữ state phiên trong bộ nhớ process, vì có thể chạy nhiều replica và filesystem là ephemeral ([04](04-architecture.md) §4.6).

## 12.4 Dockerfile

```dockerfile
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py       ./
COPY app/          ./app/
COPY prompts/      ./prompts/
COPY config/       ./config/
COPY etl/          ./etl/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["python", "main.py"]
```

Không COPY `data/`, `docs/`, `tests/`, `evals/` — dữ liệu nằm trong PostgreSQL, ETL chạy riêng. Image mục tiêu dưới 400 MB.

> **Bắt buộc build `linux/amd64`.** Node của runtime là amd64. Build trên máy ARM (Mac M-series) mà không chỉ định platform thì image push lên sẽ không pull được, và thông báo lỗi lúc đó khá tối nghĩa.

```bash
docker build --platform linux/amd64 -t mkt-insight-agent:v1.0.0 .
```

## 12.5 Bước 4 — Chạy local trước khi deploy

```powershell
# 1. Chuan bi
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config\secrets.example.yaml config\secrets.yaml
# -> dien DATABASE_URL (vDB RDS) va LLM_API_KEY vao config\secrets.yaml

# 2. Dung schema + nap du lieu (chay MOT LAN, hoac khi du lieu doi)
python -m etl.load_excel  --source excel
python -m etl.build_marts
python -m etl.dq_checks          # exit code khac 0 -> co loi BLOCK, phai sua truoc

# 3. Chay app
$env:APP_PROFILE = "local"
python main.py
```

Kiểm tra theo thứ tự này, mỗi bước phải xanh trước khi sang bước sau:

```powershell
curl http://127.0.0.1:8080/health     # {"status":"ok"}
curl http://127.0.0.1:8080/readyz     # {"db":"ok","dq":"ok","catalog":"ok"}
curl http://127.0.0.1:8080/api/dashboard/campaigns   # 6 chien dich, ROMI khop bang 02.4
start http://127.0.0.1:8080/          # UI: dashboard + chat
curl -X POST http://127.0.0.1:8080/invocations `
     -H "Content-Type: application/json" `
     -d '{\"message\":\"Chien dich nao dang lo?\"}'
```

Điểm kiểm tra quan trọng nhất: `/api/dashboard/campaigns` phải trả **đúng** sáu giá trị ROMI trong [02](02-data-model.md) §2.4. Lệch một chữ số nghĩa là ETL hoặc định nghĩa chỉ số sai — sửa ngay tại đây, đừng đi tiếp.

## 12.6 Bước 6–7 — IAM credentials, API key và model

```bash
# 1. Lay token (dung script cua bo skill, dung tu viet)
source .claude/skills/agentbase/scripts/get_token.sh

# 2. Tao API key MaaS  (ten: 5-50 ky tu, chi [a-z0-9-])
./.claude/skills/agentbase/scripts/aip.sh api-keys create --name mkt-insight-poc
# -> key tao ra o trang thai CREATING; POLL cho toi khi ACTIVE roi moi dung

# 3. Xem model nao dang bat cho tai khoan
./.claude/skills/agentbase/scripts/aip.sh models list --status ENABLED
# -> lay dung truong code/name lam gia tri LLM_MODEL
```

Ba điều dễ vấp:

* **Key mới chưa dùng được ngay** — phải chờ sang `ACTIVE`.
* **Model phải được enable riêng** cho tài khoản (`aip.sh models enable <uuid>`).
* **"Qwen 3.5 27B" trong sổ tay không có trong catalog.** Xem [10](10-config-secrets.md) §10.4.

## 12.7 Bước 5 & 8 — Deploy

### 7.1 Push image lên Container Registry

```bash
./.claude/skills/agentbase/scripts/docker_login.sh        # dang nhap vcr.vngcloud.vn
docker tag  mkt-insight-agent:v1.0.0 \
            vcr.vngcloud.vn/<backendName>/mkt-insight-agent:v1.0.0
docker push vcr.vngcloud.vn/<backendName>/mkt-insight-agent:v1.0.0
```

`<backendName>` là **tên backend của repository**, không phải tên hiển thị trên console. Lấy bằng `cr.sh repositories list`. Dùng nhầm tên hiển thị là lỗi phổ biến nhất ở bước này.

Nên dùng vCR thay vì Docker Hub: image trên vCR nằm cùng mạng riêng với node runtime nên pull nhanh và không tốn phí egress. Registry ngoài vẫn dùng được qua `imageAuth`.

### 7.2 Tạo Agent Runtime

```bash
curl -X POST https://agentbase.api.vngcloud.vn/runtime/agent-runtimes \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "mkt-insight-agent",
    "description": "Agent phan tich chien dich marketing va CLV",
    "imageUrl": "vcr.vngcloud.vn/<backendName>/mkt-insight-agent:v1.0.0",
    "imageAuth": {"enabled": true,
                  "username": "<robot-account>", "password": "<robot-secret>"},
    "environmentVariables": {
      "APP_PROFILE": "greennode",
      "LLM_BASE_URL": "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1",
      "LLM_MODEL": "<ma model da ENABLED>",
      "LLM_JUDGE_MODEL": "<ma model nho>",
      "LLM_API_KEY": "<api key ACTIVE>",
      "MKT_DATABASE__URL": "postgresql+psycopg://mkt_agent_ro:...@<rds-host>:5432/mkt_insight?sslmode=require",
      "MKT_ADMIN__TOKEN": "<random>",
      "LOG_LEVEL": "info"
    },
    "flavorId": "1x1-general",
    "autoscaling": {"minReplicas": 1, "maxReplicas": 2,
                    "cpuUtilization": 60, "memoryUtilization": 70},
    "poc": true
  }'
```

Ghi chú quan trọng:

* **`"poc": true`** tính vào ví POC (credit miễn phí). Nên bật cho hackathon.
* Bốn biến `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`, `GREENNODE_AGENT_IDENTITY`, `GREENNODE_ENDPOINT_URL` **được nền tảng tự tiêm** — không đặt tay, đặt tay sẽ ghi đè giá trị đúng.
* Network mode để mặc định **PUBLIC**. VPC mode cần VPC Peering phải mở ticket trước, không khả thi trong hackathon.
* Tạo runtime sẽ tự sinh một endpoint `DEFAULT` bám phiên bản mới nhất.

### 7.3 Lấy URL thật

```bash
./.claude/skills/agentbase/scripts/runtime.sh endpoints list --runtime-id <id>
```

Đọc trường **`url`** trong kết quả. Sổ tay BTC nêu mẫu `https://endpoint-<uuid>.agentbaseruntime.aiplatform.vngcloud.vn/`, nhưng tài liệu chính thức chỉ ghi `https://<default-url>` — nên **lấy giá trị thật từ API**, đừng tự ghép chuỗi.

### 7.4 Cập nhật phiên bản

```bash
docker build --platform linux/amd64 -t ...:v1.0.1 . && docker push ...:v1.0.1
./.claude/skills/agentbase/scripts/runtime.sh update --runtime-id <id> --image-url ...:v1.0.1
```

`PATCH` tạo một version mới bất biến; endpoint `DEFAULT` tự bám theo.

> **Bẫy khi update:** nếu đang dùng VPC mode, mỗi lần `PATCH` phải **truyền lại** `--network-mode VPC --vpc-id ... --subnet-id ...`. Bỏ sót thì version mới âm thầm quay về PUBLIC, endpoint bị tạo lại và kết nối nội bộ đứt. Với PoC chạy PUBLIC thì không gặp, nhưng cần biết.

### 7.5 Checklist nghiệm thu (Bước 8 của sổ tay)

| Kiểm tra | Kỳ vọng |
|---|---|
| Console Agent Runtime | Agent hiện trong danh sách, trạng thái `ACTIVE` |
| `GET <url>/health` | 200 `{"status":"ok"}` |
| `GET <url>/readyz` | 200, `db=ok`, `dq=ok` — nếu 503 thì xem §12.9 |
| `GET <url>/` | UI hiện, dashboard có số |
| `GET <url>/api/dashboard/campaigns` | Sáu giá trị ROMI khớp [02](02-data-model.md) §2.4 |
| `POST <url>/invocations` | Trả `answer_markdown` + `evidence` + `trust` |
| Vùng chat trên UI | Không vượt 60% chiều cao màn hình |
| `runtime.sh logs` | Không có ERROR lặp lại |

## 12.8 Zalo (Bước 3, tuỳ chọn)

Điều cần biết trước khi hứa với ban giám khảo: **tích hợp Zalo sẵn có chỉ dành cho OpenClaw** — một mẫu chatbot do nền tảng dựng, khai báo version + flavor + model + bot token từ Zalo OA Console, và **không nhận Docker image của bạn**.

Agent tuỳ chỉnh (image riêng, như dự án này) **không có tích hợp Zalo dựng sẵn**. Có hai đường:

| Đường | Cách làm | Công sức |
|---|---|---|
| **A. Tự nối Zalo OA API** | Dựng webhook `POST /webhook/zalo` trong chính app này, xác thực chữ ký, gọi `Orchestrator.answer()`, trả lời qua Zalo OA send API | Trung bình — nằm trong tầm, nhưng là việc thêm |
| **B. OpenClaw riêng** | Deploy thêm một OpenClaw làm mặt tiền Zalo, cho nó gọi endpoint `/invocations` của agent này | Thấp — nhưng thành hai thành phần |

Khuyến nghị: **để Zalo ngoài đường găng.** Ba deliverable D1/D2/D3 và bộ chống hallucination mới là phần cốt lõi. Nếu còn thời gian thì làm đường A, vì `/invocations` đã sẵn sàng nhận đúng hợp đồng đó.

## 12.9 Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| Runtime kẹt `CREATING` rồi `ERROR` | Image không pull được (sai `backendName`, sai robot account) hoặc sai kiến trúc CPU | `cr.sh repositories list`; build lại `--platform linux/amd64` |
| `ACTIVE` nhưng gọi gì cũng timeout | App không nghe `0.0.0.0:8080` (nghe `127.0.0.1` thì nền tảng không tới được) | Kiểm tra tham số `host` trong `uvicorn.run` |
| `/health` fail, replica restart liên tục | `/health` có chạm DB | `/health` chỉ kiểm tra process. Dùng `/readyz` cho DB ([09](09-api-ui.md) §9.1) |
| `/readyz` 503, `db=fail` | Security Group của vDB chặn IP egress của runtime | Xem [03](03-database-choice.md) §3.3, đường 2 |
| LLM trả 401 | Key chưa `ACTIVE`, hoặc model chưa enable | `aip.sh api-keys list`, `aip.sh models list --status ENABLED` |
| LLM trả 429 liên tục | Đụng trần 10 RPM | Hạ `llm.rate_limit.requests_per_minute`, bật cache, tắt self-consistency |
| Dashboard trống | ETL chưa chạy trên DB dùng chung | Chạy `etl.*` từ máy local — DB là chung nên prod thấy ngay |
| Số trên prod khác local | Không thể xảy ra nếu đúng thiết kế (chung DB) | Kiểm tra `MKT_DATABASE__URL` hai bên có thật sự trỏ cùng instance |
| Câu trả lời bị chặn liên tục | Narrator viết số trực tiếp thay vì dùng thẻ | Xem [10](10-config-secrets.md) §10.4, phần cuối — đừng tắt L2 |

## 12.10 Script một lệnh

```powershell
# scripts/deploy_greennode.ps1
param(
  [Parameter(Mandatory)][string]$Version,
  [string]$Registry   = "vcr.vngcloud.vn",
  [string]$BackendName,
  [string]$RuntimeId
)
$ErrorActionPreference = "Stop"
$image = "$Registry/$BackendName/mkt-insight-agent:$Version"

Write-Host "==> Kiem tra truoc khi build"
pytest tests/ -q                      ; if (-not $?) { throw "Unit test that bai" }
python -m evals.run_eval --quick      ; if (-not $?) { throw "Golden set that bai" }

Write-Host "==> Build $image"
docker build --platform linux/amd64 -t $image .

Write-Host "==> Push"
bash .claude/skills/agentbase/scripts/docker_login.sh
docker push $image

Write-Host "==> Cap nhat runtime"
bash .claude/skills/agentbase/scripts/runtime.sh update --runtime-id $RuntimeId --image-url $image

Write-Host "==> Cho ACTIVE va kiem tra"
bash .claude/skills/agentbase/scripts/runtime.sh wait --runtime-id $RuntimeId --state ACTIVE
$url = bash .claude/skills/agentbase/scripts/runtime.sh endpoints url --runtime-id $RuntimeId
curl -fsS "$url/health" ; curl -fsS "$url/readyz"
Write-Host "==> Xong: $url"
```

Điểm đáng giữ: **golden set chạy trước khi build**. Đây là chỗ duy nhất trong quy trình ngăn được việc deploy một phiên bản mà chất lượng câu trả lời đã tụt — và nó tốn đúng vài chục giây.
