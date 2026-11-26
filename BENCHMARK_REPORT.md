# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file JSON/CSV trong `reports/` và `benchmark-results/`.

**Họ tên:** Chu Văn Nhật (MSSV: 2A202603848)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11, Python 3.11.0, Docker Desktop (WSL2 backend)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Đảm bảo 95% người dùng nhận câu trả lời dưới nửa giây, tránh cảm giác giật lag dù vẫn chấp nhận một phần nhỏ tail latency |
| Error rate `/ask` | ≤ 2.0 % | Mock LLM có tỉ lệ lỗi upstream ~1%; ngưỡng 2% tạo error budget hợp lý mà không gây cảnh báo giả |
| Accuracy trên golden dataset | ≥ 85 % (mục tiêu 100% sau sửa KB) | Đảm bảo chất lượng trả lời của RAG không bị tụt (regression) trước khi merge/deploy |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.44 | 201.9 | 234.7 | 1685.5 | 1.33% | PASS |
| 10 | 33.55 | 196.3 | 484.6 | 1684.5 | 0.33% | PASS |
| 50 | 92.96 | 203.2 | 561.9 | 1728.0 | 0.67% | FAIL |
| 100 | 57.26 | 751.6 | 4150.7 | 4630.5 | 0.67% | FAIL |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ concurrency 1 → 10 → 50, RPS tăng từ 4.44 → 33.55 → 92.96 req/s vì hệ thống tận dụng async I/O để xử lý song song thời gian chờ LLM. Tuy nhiên đến concurrency = 100, RPS lại **giảm** xuống 57.26 req/s trong khi p50 tăng vọt lên 751.6 ms và p95 lên 4150.7 ms. Nguyên nhân là hiện tượng bão hòa (saturation) và xếp hàng (queuing) trên một tiến trình uvicorn đơn + giới hạn kết nối/event loop trên máy local: khi quá nhiều request đổ vào cùng lúc, thời gian chờ trong hàng đợi tăng mạnh làm giảm thông lượng hiệu dụng.

### 2.2 Tail latency (agent v2, 300 requests, concurrency = 20)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 204.5 | 456.3 | 486.7 |
| 0.03 (mặc định) | 236.1 | 451.6 | 1684.6 |
| 0.1 | 376.9 | 1692.4 | 1722.2 |

**Nhận xét:** **p99** (và khi tỉ lệ chậm vượt 5% là **p95**) là chỉ số nhạy nhất với request chậm. Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03`, `avg` chỉ tăng nhẹ từ `204.5 ms` lên `236.1 ms` (+15%), nhưng `p99` nhảy vọt từ `486.7 ms` lên `1684.6 ms` (gấp ~3.5 lần). Khi `MOCK_SLOW_RATE = 0.1`, `p95` vọt lên `1692.4 ms` (vi phạm SLO ≤ 500ms) dù `avg` mới là `376.9 ms`. Vì trung bình (average) bị kéo thấp bởi đa số request nhanh và che giấu trải nghiệm tệ của nhóm người dùng gặp tail latency, SLO bắt buộc phải đặt theo **p95 hoặc p99**.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.6 | 109.0 | 113.9 |
| Tổng cost (USD) | \$0.000411 | \$0.000760 | \$0.000793 |
| Cost / câu đúng (USD) | \$0.00041115 | \$0.00003619 | \$0.00003446 |
| Quality gate | FAIL | PASS | PASS (0 regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa (`utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `["jwt"]` vào `KNOWLEDGE_BASE` giải thích sự khác nhau giữa API key và JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn) |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA scale pod dựa trên CPU, memory hoặc custom metrics |

**Cách dùng exit code trong CI để chặn merge (Exercise 7.3):**
File `.github/workflows/eval.yml` chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85` trên mỗi Pull Request. Khi accuracy dưới ngưỡng hoặc phát hiện câu bị regression so với baseline, `run_eval.py` thoát với **exit code 1**, khiến job GitHub Actions fail và branch protection tự động chặn merge PR.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
Agent v2 thêm bước retrieval (RAG) nên prompt dài hơn (~109–113.9 tokens/câu so với 57.6 ở v1), kéo theo tổng chi phí cao hơn ~1.9 lần (\$0.000793 vs \$0.000411) và thêm ~20 ms latency retrieval. Tuy nhiên accuracy tăng vọt từ **4.3% lên 100.0%**, giúp **cost / câu đúng giảm ~12 lần** (từ \$0.00041115 xuống \$0.00003446). Đánh đổi này hoàn toàn xứng đáng trong production.

---

## 4. Observability stack (production)

### 4.1 Screenshot & Exercise 7.4

- [x] Dashboard Grafana khi đang có tải ([grafana-dashboard.png](screenshots/grafana-dashboard.png))
- [x] Một trace chậm trong Jaeger ([jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png))
- [x] Một trace lỗi trong Jaeger ([jaeger-error-trace.png](screenshots/jaeger-error-trace.png))
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** ([prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png))

**Trả lời Exercise 7.4:**
1. **p95 và avg trên Grafana:** Khi chạy tải ổn định với 3 instance, latency p95 dao động quanh **~297–299 ms** (trong Locust p95 `/ask` = **230 ms**, avg = **238.8 ms**, p99 = **1700 ms**). Khoảng cách rất lớn giữa avg/p95 và p99 (~1700 ms) phản ánh rõ hiện tượng **tail latency** (~3% request chậm bất thường).
2. **Panel "Requests/s theo instance":** Nginx phân phối traffic đều giữa các instance đang chạy (3 instance up, round-robin).
3. **Vì sao input tokens/s lớn hơn output tokens/s?** Vì ở agent v2 (RAG), mỗi request phải gửi `SYSTEM_PROMPT` + đoạn tài liệu truy xuất từ `KNOWLEDGE_BASE` + câu hỏi của người dùng làm input (ví dụ `95` input tokens), trong khi câu trả lời ngắn gọn hơn (`55` output tokens).
4. **`curl http://localhost:8080/metrics` trả về gì? Vì sao?** Trả về **HTTP 404** (`GET /metrics -> HTTP 404`). Nginx cố tình chặn `/metrics` từ bên ngoài để tránh lộ thông tin vận hành nội bộ; chỉ Prometheus trong mạng Docker nội bộ mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

Unit test alert rules (`promtool test rules /p/alert_rules_test.yml`): **`SUCCESS`**.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`critical`, value `0.203` = 20.3%) | **~83.5 giây** (gồm thời gian chờ `for: 1m` + chu kỳ scrape) | Golden Signals — Error rate (đỏ ~20%) & Requests/s theo status code (tăng mạnh 503) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (chuyển sang `PENDING`, sẽ `FIRING` sau `for: 2m`) | ~120–135 giây (theo ngưỡng `for: 2m`) | Latency /ask — p95 tăng vọt vượt ngưỡng 500 ms |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`warning`, value `$9.11/giờ`) | **~8.3 giây** (sau chu kỳ đánh giá ngay khi cost burn rate vượt ngưỡng) | LLM — Cost burn rate (USD/giờ) tăng vọt ~16 lần |
| D | `docker pause` 1 instance | `AgentInstanceDown` (nếu tạm dừng container thay vì `stop`) | ~30–45 giây (do container vẫn còn trong DNS nhưng `up == 0`) | Instances up giảm; Nginx trả 504 nhưng error rate nội bộ agent không tăng |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | N/A | Retrieval hit ratio giảm về 0, tokens/s giảm, bảng version đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing. Cách phát hiện loại sự cố này trong production:**
Observability hạ tầng (HTTP 200, latency, error rate) không biết nội dung câu trả lời đúng hay sai. Để phát hiện sự cố suy giảm chất lượng:
1. Chạy **Eval quality gate** trên golden dataset trong CI/CD trước khi deploy.
2. Thực hiện **online evaluation / LLM-as-a-judge** trên mẫu traffic thật (sampling 1–5%) và theo dõi **retrieval hit ratio** (alert khi tỉ lệ tìm thấy context tụt đột ngột).
3. Thu thập **user feedback** (thumbs up/down, retry rate) và gắn alert khi tỉ lệ phản hồi tiêu cực tăng.

### 4.3 Debug bằng trace

Chọn trace chậm nhất tìm được trong Jaeger (`observable-agent`):

- `trace_id`: `3a8a3c8ec51e78cdf35ac9efe9faa41e`
- Tổng thời gian: **~1720 ms** (`1.7s` trên Jaeger; `agent.retrieve_context` = `20.5 ms`, `chat mock-llm-small` = `1698.3 ms`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1698.3 ms**, chiếm **~98.7%** tổng thời gian request)
- Dòng log tương ứng (grep từ `docker compose -p k5-day14-observability logs agent` theo `trace_id`):

```json
{"ts": "2026-11-26T08:16:49.687800+00:00", "level": "INFO", "service": "observable-agent", "instance": "0fa444a03a06", "event": "llm_call", "trace_id": "3a8a3c8ec51e78cdf35ac9efe9faa41e", "span_id": "671567f4500a9ece", "request_id": "744b83f18d61", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.3}
```

Trace lỗi đối chiếu trong Jaeger: `trace_id = 2880bbf883d5fe29303082cc3eab698c` (`event: llm_error`, `Upstream LLM error: 503 Service Unavailable (mock)`).

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu lấy trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `POST /ask` và `Aggregated`):

| Số instance | Endpoint | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|---|
| 1 | `POST /ask` | 59.64 | 190 | 270 | 1700 | 75 (1.05%) |
| 1 | `Aggregated` | 65.31 | 190 | 260 | 1700 | 75 (0.96%) |
| 3 | `POST /ask` | 60.22 | 190 | 230 | 1700 | 88 (1.22%) |
| 3 | `Aggregated` | 66.02 | 190 | 220 | 1700 | 88 (1.12%) |

**Giải thích kết quả:** Khi scale từ 1 lên 3 instance, **p95 giảm nhẹ** (từ `270 ms` → `230 ms` cho `/ask`, giảm ~15% nhờ giảm hàng đợi xử lý đồng thời trên mỗi container), trong khi **p50 (190 ms), p99 (1700 ms) và tổng RPS (~65–66 req/s) gần như không đổi**. Nguyên nhân là nút thắt không nằm ở CPU của agent container mà nằm ở **I/O latency của upstream LLM** (`~120–180 ms` bình thường và `+1500 ms` tail latency) kết hợp với số lượng virtual users cố định (100 users có `wait_time` giữa các request). Để giảm p99 hoặc tăng tốc độ phản hồi từng request, cần tối ưu ở tầng LLM (streaming, caching, model nhanh hơn hoặc hedging/timeout) chứ không chỉ tăng số replica.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Tail latency quan trọng hơn average:** Chỉ 3% request chậm đã khiến p99 tăng gấp 3.5 lần dù trung bình gần như không đổi; SLO phải đặt trên p95/p99.
  2. **Chất lượng phải được đo tự động bằng Eval + Quality Gate:** Metric hạ tầng xanh không đồng nghĩa agent trả lời đúng; cần golden dataset + baseline để chặn regression trong CI.
  3. **3 trụ cột Metrics – Traces – Logs bổ trợ lẫn nhau:** Metrics phát hiện *có vấn đề*, Traces chỉ ra *chậm/lỗi ở span nào*, và JSON Logs gắn `trace_id` cung cấp *ngữ cảnh chi tiết*.
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  - **Metric:** `agent_retrieval_hit_ratio` (cảnh báo khi RAG mất kết nối hoặc rỗng), `agent_rate_limit_rejected_total` (phát hiện bot/abuse), `llm_time_to_first_token_seconds` (TTFT cho streaming), và `redis_operation_duration_seconds`.
  - **Alert:** Alert ở tầng Load Balancer/synthetic check từ bên ngoài (bắt lỗi 502/504 khi agent treo mà metric nội bộ không thấy), và alert `RetrievalHitRatioLow` khi tỉ lệ retrieval hit giảm mạnh.
