# Deployment Information

## Public URL
<!-- Điền Public URL sau khi deploy lên Railway hoặc Render -->
https://<your-agent-url>

## Platform
Railway / Render (deploy từ thư mục `06-lab-complete/` sử dụng `railway.toml` hoặc `render.yaml`)

## Test Commands

Đặt biến môi trường trước khi chạy:
```bash
export BASE="https://<your-agent-url>"
export AGENT_API_KEY="<your-api-key>"
```

### 1. Health Check (Liveness — expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
```

### 2. Readiness Check (Redis connected — expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
```

### 3. Authentication Required (No API key — expected: 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
```

### 4. API Test (With valid API key — expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Environment Variables Set
- `PORT` (do nền tảng tự cấp, mặc định `8000`)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (kết nối tới managed Redis trên Railway/Render)
- `AGENT_API_KEY` (secret đặt trên dashboard nền tảng, không ghi trong code)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `MONTHLY_BUDGET_USD` (`10.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
