# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode secrets trong mã nguồn (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Khi push lên Git/GitHub, secret bị lộ vĩnh viễn trong lịch sử commit.
2. **In secret ra log bằng `print()` (dòng 33–38):** Dùng `print()` thay vì structured logging và thậm chí in thẳng `OPENAI_API_KEY` ra stdout (`print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`).
3. **Không có quản lý cấu hình từ biến môi trường (dòng 21–22):** Hardcode `DEBUG = True`, `MAX_TOKENS = 500`, không phân tách cấu hình giữa dev/staging/production theo 12-Factor App.
4. **Không có Health Check / Readiness endpoint:** Thiếu `GET /health` và `GET /ready`, nên cloud platform / load balancer không biết container còn sống hay đã sẵn sàng nhận traffic để restart hoặc định tuyến.
5. **Bind cứng `host="localhost"`, `port=8000` và bật `reload=True` (dòng 49–54):**
   - `host="localhost"` khiến container không thể nhận kết nối từ bên ngoài.
   - `port=8000` cố định, không đọc biến `PORT` do nền tảng cloud (Railway/Render/Cloud Run) cấp.
   - `reload=True` gây tốn tài nguyên và mất ổn định trong production.
6. **Không có Graceful Shutdown:** Không xử lý tín hiệu `SIGTERM` hay vòng đời `lifespan`, khi tắt server sẽ cắt ngang các request đang xử lý (in-flight requests).

### Exercise 1.2: Kết quả chạy bản develop (`01-localhost-vs-production/develop/app.py`)
```text
POST /ask?question=Hello -> HTTP 200
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```
> Lưu ý: Bản develop nhận `question` qua query parameter (`?question=Hello`), không nhận JSON body.

### Exercise 1.3: Bảng so sánh Develop vs Production (`01-localhost-vs-production/production/app.py`)

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| Config & Secrets | Hardcode trực tiếp trong code (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`) | Đọc từ biến môi trường qua `config.settings` (`PORT`, `ENVIRONMENT`, `DEBUG`, `ALLOWED_ORIGINS`) | Đảm bảo nguyên tắc 12-Factor App: không lộ secret trên Git, cùng 1 image chạy được ở dev/staging/prod |
| Network Binding | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port=settings.port`, `reload=settings.debug` | Container cần `0.0.0.0` để nhận traffic ngoài và đọc `PORT` động từ cloud platform |
| Health Check | Không có | Có `GET /health` (liveness), `GET /ready` (readiness, trả 503 khi chưa sẵn sàng), `GET /metrics` | Giúp orchestrator tự restart khi treo và load balancer chỉ route traffic khi sẵn sàng |
| Logging | `print()` plain text, log cả API key | `logging` định dạng JSON (`{"time":..., "level":..., "msg":...}`), tuyệt đối không log secret | Dễ thu thập, tìm kiếm, lọc trên Datadog/Loki/ELK và tránh rò rỉ thông tin nhạy cảm |
| Shutdown | Tắt đột ngột, không dọn dẹp | FastAPI `lifespan` + `signal.signal(signal.SIGTERM, handle_sigterm)` | Hoàn thành request đang xử lý và đóng kết nối an toàn trước khi tắt, tránh lỗi cho user |
| CORS & Input | Không cấu hình CORS, nhận `question` qua query | Cấu hình `CORSMiddleware` theo `settings.allowed_origins`, validate JSON body (trả 422 nếu thiếu) | Bảo mật cross-origin và chuẩn hóa contract API |

---

## Part 2: Docker

### Exercise 2.1: Trả lời câu hỏi về `02-docker/develop/Dockerfile`
1. **Base image là gì?** `python:3.11` (bản full Python distribution, dung lượng lớn ~1 GB vì chứa nhiều công cụ hệ thống và build tools).
2. **Working directory là gì?** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` phải đứng trước `COPY . .` (hoặc `COPY app.py`)?** Để tận dụng **Docker layer cache**. `requirements.txt` ít thay đổi hơn source code; khi chỉ sửa code, Docker tái sử dụng cache của layer `RUN pip install -r requirements.txt` nên rebuild rất nhanh thay vì phải tải và cài lại toàn bộ thư viện mỗi lần.
4. **CMD vs ENTRYPOINT khác nhau thế nào?**
   - `ENTRYPOINT` định nghĩa tiến trình chính cố định của container (khó bị ghi đè trừ khi dùng `--entrypoint`).
   - `CMD` cung cấp lệnh mặc định hoặc tham số mặc định cho `ENTRYPOINT`, và dễ dàng bị ghi đè khi truyền tham số lúc `docker run <image> <custom-cmd>`.

### Exercise 2.2 & 2.3: Build, test và so sánh dung lượng image
- **Multi-stage build (`02-docker/production/Dockerfile`):**
  - **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài công cụ biên dịch (`gcc`, `libpq-dev`) và chạy `pip install --user -r requirements.txt`.
  - **Stage 2 (`runtime`):** Dùng `python:3.11-slim` sạch, tạo user non-root `appuser`, chỉ `COPY --from=builder` thư mục gói đã cài (`/root/.local`) cùng source code, thêm `HEALTHCHECK` và chạy `uvicorn` bằng `appuser`.
  - **Tại sao nhỏ hơn?** Loại bỏ hoàn toàn `gcc`, `libpq-dev`, apt cache và các artifact build ở Stage 1 khỏi image cuối cùng, đồng thời tăng bảo mật (giảm attack surface, chạy non-root).
- **Kết quả chạy container `my-agent:develop` (Exercise 2.2):**
```text
POST http://localhost:8022/ask?question=What%20is%20Docker%3F -> HTTP 200
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```
- **Số liệu đo thực tế (`docker images my-agent`):**
  - Develop (`my-agent:develop`): **1.67 GB** (1670 MB)
  - Production (`my-agent:advanced`): **240 MB**
  - Chênh lệch: giảm **~85.6%** dung lượng (nhỏ hơn ~7 lần)

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)
- **Các service trong stack:** `nginx` (reverse proxy / load balancer, cổng 80/443), `agent` (FastAPI app, không expose port ra host), `redis` (`redis:7-alpine`, cache/session/rate-limit), `qdrant` (`qdrant/qdrant:v1.9.0`, vector DB).
- **Cách giao tiếp:** Tất cả cùng nằm trong bridge network riêng `internal`, gọi nhau bằng DNS tên service (`redis://redis:6379/0`, `http://qdrant:6333`, Nginx proxy tới `agent:8000`). Client chỉ truy cập qua Nginx cổng 80.
- **Sơ đồ kiến trúc:**
```text
Client ──(:80)──▶ Nginx (Reverse Proxy / LB)
                      │ (internal network)
                      ▼
                    Agent (:8000)
                    ├──▶ Redis (:6379)   [session & rate limit]
                    └──▶ Qdrant (:6333)  [vector DB]
```
- **Kết quả test qua Nginx (`docker compose -p k5-day14-docker up -d --build`):**
```text
GET http://localhost/health -> HTTP 200
{"status":"ok","uptime_seconds":8.7,"version":"2.0.0","timestamp":"2026-11-26T08:02:16.560201"}

POST http://localhost/ask ({"question": "Explain microservices"}) -> HTTP 200
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 (`06-lab-complete/`)
- **Platform:** Render (`Docker` runtime, Root Directory `06-lab-complete`, kết nối Render Key Value Redis)
- **Public URL:** `https://day14-production-agent-gh9o.onrender.com`
- **Kết quả 4 lệnh tự kiểm CP6:** `GET /health` → `200`, `GET /ready` → `200` (Redis connected), `POST /ask` không có key → `401`, `POST /ask` có `X-API-Key` → `200` (chi tiết trong `DEPLOYMENT.md`).
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
| --- | --- | --- |
| **Định dạng & Phạm vi** | File TOML cấu hình **một service** (build + deploy) trong thư mục hiện tại | File YAML dạng Infrastructure-as-Code (Blueprint), khai báo được **nhiều service** (web, worker, database, Redis) trong cùng 1 file |
| **Build & Healthcheck** | `[build] builder = "DOCKERFILE"`, `[deploy] healthcheckPath = "/health"`, `restartPolicyType` | `type: web`, `runtime: docker`, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /health` |
| **Quản lý biến môi trường & Secret** | Thường đặt qua Railway Dashboard hoặc CLI (`railway variables set`), không khai báo trong `railway.toml` | Khai báo trực tiếp trong `envVars`; hỗ trợ `generateValue: true` (tự sinh secret) và `sync: false` (nhập tay trên dashboard, không lưu vào Git) |
| **Managed Redis** | Tạo plugin/service Redis riêng trên project Railway và liên kết biến `REDIS_URL` | Có thể khai báo dịch vụ `type: redis` (Key Value) ngay trong `render.yaml` và dùng `fromService` để inject `REDIS_URL` |

### Exercise 3.3: Pipeline CI/CD trên GCP Cloud Run (`cloudbuild.yaml` & `service.yaml`)
Pipeline trong `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` tự động chạy 4 bước tuần tự (`waitFor`) khi push lên nhánh `main`:
1. **Test (`python:3.11-slim`):** Cài `requirements.txt` + `pytest` và chạy toàn bộ test suite (`pytest tests/`). Nếu test fail, pipeline dừng ngay.
2. **Build (`docker`):** Build Docker image gắn 2 tag `$COMMIT_SHA` và `latest`, tận dụng `--cache-from` từ image `latest` để tăng tốc build.
3. **Push (`docker`):** Đẩy toàn bộ tag lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`gcloud run deploy`):** Triển khai bản `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình `min-instances=1` (tránh cold start), `max-instances=10`, giới hạn CPU/RAM (`1 CPU / 512Mi`), nạp secret từ Google Secret Manager (`--set-secrets`). File `service.yaml` định nghĩa trạng thái dịch vụ dạng IaC (Knative) gồm `containerConcurrency: 80`, `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)
- **API key được check ở đâu?** Trong dependency `verify_api_key` sử dụng `APIKeyHeader(name="X-API-Key", auto_error=False)`, gắn vào endpoint `POST /ask` qua `Depends(verify_api_key)`.
- **Điều gì xảy ra nếu thiếu hoặc sai key?** Thiếu header `X-API-Key` trả về `HTTP 401`; sai key trả về `HTTP 403` (trong Part 6 chuẩn hóa cả thiếu và sai đều trả `401`).
- **Làm sao rotate key?** Cập nhật biến môi trường `AGENT_API_KEY` trên nền tảng (không cần sửa code); trong production thực tế nên hỗ trợ đồng thời 2 key (active + previous) trong khoảng thời gian chuyển giao để tránh downtime.

**Kết quả test thực tế:**
```text
# Không có key
POST /ask -> HTTP 401
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có key (X-API-Key: secret-key-123)
POST /ask -> HTTP 200
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)
- **Thuật toán Rate Limiting (`rate_limiter.py`):** **Sliding Window Counter** sử dụng `deque` lưu timestamp của các request trong cửa sổ `window_seconds = 60`. Trước mỗi request sẽ xóa các timestamp cũ hơn `now - 60s`, nếu số phần tử `>= max_requests` thì trả `HTTP 429` kèm `Retry-After`.
- **Giới hạn:** User thường (`student`): **10 requests/phút** (`rate_limiter_user`); Admin (`teacher`): **100 requests/phút** (`rate_limiter_admin`).
- **Bypass/nâng limit cho admin:** Đọc trường `role` từ JWT payload sau khi verify token; nếu `role == "admin"` thì áp dụng tier `rate_limiter_admin` (hoặc bỏ qua bước kiểm tra rate limit).

**Kết quả test thực tế (đã che JWT token):**
```text
POST /auth/token (student/demo123) -> HTTP 200
{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.<REDACTED>","token_type":"bearer",...}

# Không có token
POST /ask -> HTTP 401
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# Vòng lặp với Bearer token (giới hạn 10 req/phút)
Req 01 -> HTTP 200 {"question":"Test 1","answer":"..."}
...
Req 10 -> HTTP 200 {"question":"Test 10","answer":"..."}
Req 11 -> HTTP 429 (Retry-After: 59) {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Req 12 -> HTTP 429 (Retry-After: 59) {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard
- **Tại sao cần cả Rate Limit và Cost Guard?** Rate limit chỉ bảo vệ **tốc độ gọi** (số request/phút), nhưng 1 request có prompt rất dài hoặc dùng model đắt vẫn có thể tiêu tốn rất nhiều tiền. Cost guard bảo vệ trực tiếp **ngân sách (USD)** dựa trên số token thực tế đã dùng.
- **Cách triển khai với Redis (áp dụng trong Part 6 `app/cost_guard.py`):**
  - Tạo key theo ngày/tháng trên Redis: `cost:daily:YYYY-MM-DD` (TTL 48h) và `cost:monthly:YYYY-MM` (TTL 32 ngày).
  - Trước khi gọi LLM (`check_budget()`): đọc tổng chi phí hiện tại từ Redis; nếu `>= DAILY_BUDGET_USD` hoặc `>= MONTHLY_BUDGET_USD` thì chặn ngay với `HTTP 402 Payment Required`.
  - Sau khi gọi LLM (`record_cost(input_tokens, output_tokens)`): tính chi phí theo đơn giá token và cộng nguyên tử bằng `INCRBYFLOAT` + `EXPIRE`.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Health Checks, Graceful Shutdown & Stateless Design
- **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
  - **Liveness (`/health`):** Kiểm tra tiến trình app còn sống không. Phải luôn trả `200` khi process hoạt động (kể cả khi Redis tạm mất kết nối), tránh để platform restart vòng lặp không cần thiết.
  - **Readiness (`/ready`):** Kiểm tra instance đã sẵn sàng nhận traffic chưa (đã load xong, kết nối được Redis). Khi Redis down, trả `503` để load balancer ngừng định tuyến traffic vào instance này mà không kill container.
- **Graceful Shutdown:** Khi orchestrator gửi `SIGTERM`, app ngừng nhận request mới, chờ các request in-flight hoàn thành, đóng kết nối Redis/DB rồi thoát với exit code `0`. Nếu tự đăng ký handler `SIGTERM`, phải gọi lại handler trước đó của `uvicorn` để quá trình tắt không bị treo.
- **Stateless Design:** Nếu lưu `conversation_history` hay state rate limit trong RAM (dict Python), khi scale ra 3 instance sau Nginx, request 1 vào `agent-1` nhưng request 2 vào `agent-2` sẽ không thấy lịch sử hoặc đếm sai rate limit. Chuyển toàn bộ state sang **Redis** giúp mọi instance chia sẻ chung dữ liệu và không mất state khi restart/scale.

### Exercise 5.4 & 5.5: Load Balancing (3 instances) & `test_stateless.py`
Chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` trong `05-scaling-reliability/production/` rồi chạy `python test_stateless.py`:

```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: cd4785b0-4b9c-49f2-b6b8-4b4b85edc43c

Request 1: [instance-9174c4] -> Q: What is Docker?
Request 2: [instance-98c11e] -> Q: Why do we need containers?
Request 3: [instance-52e95e] -> Q: What is Kubernetes?
Request 4: [instance-9174c4] -> Q: How does load balancing work?
Request 5: [instance-98c11e] -> Q: What is Redis used for?

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-98c11e', 'instance-9174c4', 'instance-52e95e'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

**Giải thích:** Nginx phân phối 5 request lần lượt theo thuật toán round-robin tới cả 3 container (`instance-9174c4`, `instance-98c11e`, `instance-52e95e`). Dù mỗi câu hỏi trong cùng 1 `session_id` được xử lý bởi các instance khác nhau, toàn bộ 10 tin nhắn (5 user + 5 assistant) vẫn được bảo toàn đầy đủ vì trạng thái hội thoại được lưu tập trung trên Redis chứ không nằm trong RAM cục bộ của từng instance.

---

## Part 6: Final Project (`06-lab-complete/`)

### Kết quả `python check_production_ready.py`
Chạy đầy đủ (có Docker, môi trường Linux POSIX) trong `06-lab-complete/` — image cuối **271 MB**, `docker stop` **exit code 0 trong 0.8s**, `SIGTERM` **exit code 0**:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log (theo `RULES.md`)

| Lần | Hỏi gì / Mục đích | Nhận được gì | Tự sửa và tự kiểm tra |
| --- | --- | --- | --- |
| 1 | Đọc toàn bộ tài liệu Day 14 (`README.md`, `RULES.md`, `CHECKPOINTS.md`, `SUBMISSION.md`, `RUBRIC.md`, `CODE_LAB.md`) và lên kế hoạch làm bài | Tóm tắt cấu trúc điểm, các lưu ý đặc thù lớp K5 và danh sách 12 tiêu chí chấm của `check_production_ready.py` | Đối chiếu từng mục với `check_production_ready.py` và `RUBRIC.md` |
| 2 | Triển khai toàn bộ `TODO` cho Part 6 trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) | Mã nguồn hoàn chỉnh theo 12-Factor, sliding window Redis, cost guard, JSON logging, graceful shutdown, multi-stage Dockerfile | Chạy `python check_production_ready.py --static-only` đạt 28/28 checks; kiểm tra kỹ xử lý `SIGTERM` trong `lifespan` |
| 3 | Chạy thực nghiệm Part 1, Part 4 và Part 7 Bước 1 (load test 4 mức concurrency, 3 mức `MOCK_SLOW_RATE`, eval v1/v2, sửa `KNOWLEDGE_BASE` cho `security-02` và `scaling-03`) | Script tự động chạy kiểm thử thật, lưu đủ JSON report trong `reports/` và thêm metric `agent_question_length_chars` | Kiểm tra lại toàn bộ số liệu từ file JSON thực tế, đối chiếu quality gate 23/23 không regression |
