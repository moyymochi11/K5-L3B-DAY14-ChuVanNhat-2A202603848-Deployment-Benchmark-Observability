# Deployment Information

## Public URL
https://day14-production-agent-gh9o.onrender.com

## Platform
Render (deploy từ thư mục `06-lab-complete/` dùng `Dockerfile` + managed Redis `Key Value` gói Free)

## Test Commands

Đặt biến môi trường trước khi chạy (không ghi secret trong repo):
```bash
export BASE="https://day14-production-agent-gh9o.onrender.com"
export AGENT_API_KEY="<your-api-key>"
```

### 1. Health Check (Liveness — expected: `200`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Output: 200
```

### 2. Readiness Check (Redis connected — expected: `200`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Output: 200
```

### 3. Authentication Required (No API key — expected: `401`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Output: 401
```

### 4. API Test (With valid API key — expected: `200`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Output: 200
```

## Environment Variables Set (trên Render Dashboard)
- `PORT` (Render tự động inject)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (Internal Connection String tới Render Key Value Redis)
- `AGENT_API_KEY` (secret đặt trực tiếp trên Render Dashboard, không lưu trong code/Git)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running (logs)](screenshots/running.png)
- [Test results](screenshots/test.png)
