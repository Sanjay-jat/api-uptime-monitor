<div align="center">
# Uptime
 
**Your API dies at 3 AM. You hear about it from a signed message at 3:03, not from a customer at 9.**
 
A multi-tenant uptime and incident monitor. Add a URL, pick an interval, and a background scheduler checks it, confirms real downtime, opens an incident, fires a signed webhook, and updates your dashboard live.
 
[![Live Demo](https://img.shields.io/badge/Live_Demo-Open_the_app-111111?style=for-the-badge)](https://api-uptime-monitor-frontend-mu.vercel.app/#/)
 
![CI](https://github.com/Sanjay-jat/api-uptime-monitor/actions/workflows/ci.yml/badge.svg)
![Tests](https://img.shields.io/badge/tests-414_passing-2F4F3F?style=flat-square)
![Coverage](https://img.shields.io/badge/coverage-99%25-2F4F3F?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
 
</div>
---
 
> **Heads up:** the demo runs on free tiers. Render puts the backend to sleep after 15 minutes without traffic, so the very first request can take about a minute. A keep-awake pinger is set up, but it is best effort.
 
## See it
 
| Everything is running | One endpoint, up close | Alerts |
|:---:|:---:|:---:|
| ![Home](./screenshots/home.png) | ![Endpoint detail](./screenshots/detail.png) | ![Alerts](./screenshots/alerts.png) |
 
The plain English is on purpose: "Everything is running." and "How fast it answered" read better at 3 AM than a wall of charts.
 
## One outage, start to finish
 
One failed check proves nothing. Networks blink. So the monitor waits for **3 failures in a row** before it believes you.
 
```mermaid
sequenceDiagram
    participant S as Scheduler
    participant T as Your API
    participant D as Dashboard
    participant W as Your webhook
    S->>T: check
    T--xS: timeout (fail 1, nothing happens)
    S->>T: check
    T--xS: 500 (fail 2, still nothing)
    S->>T: check
    T--xS: timeout (fail 3)
    S->>D: status DOWN (live over WebSocket)
    S->>W: signed alert, incident opened
    S->>T: check
    T-->>S: 200
    S->>D: status UP
    S->>W: signed recovery, incident closed
```
 
At the shortest interval (1 minute) a confirmed outage reaches you in roughly 3 minutes.
 
## Try to break it
 
The server makes outbound requests to URLs that strangers type in. That is the classic recipe for SSRF, so the app fights back. Open the demo, create an account and try adding:
 
- `http://169.254.169.254` (cloud metadata address)
- `http://localhost:8000`
- `http://user:pass@example.com`
- `ftp://example.com`
All refused. The check runs when you register a URL **and again before every single ping and webhook**, because a hostname can point somewhere harmless today and somewhere private tomorrow. Redirects are never followed.
 
## What it does
 
- **Auth that holds up:** bcrypt passwords, short-lived JWT access tokens, rotating refresh tokens stored as hashes. Reusing an already-rotated refresh token revokes every token of that user.
- **Your data stays yours:** another user's endpoint returns `404`, never `403`, so nobody can even learn it exists.
- **Real downtime, not noise:** 3 consecutive failures flip an endpoint to DOWN. The logic is one pure function, `next_state`, tested without I/O or clocks.
- **Incidents:** opened once per outage, closed on recovery. A partial unique index makes the database itself refuse a second open incident for the same endpoint.
- **Signed webhooks:** HMAC-SHA256 over the raw body in `X-Signature: sha256=<hex>`. The secret is shown once when you save the address.
- **Live dashboard:** WebSocket with a snapshot on connect and an update after every ping, for every open tab of the same user.
- **History and uptime %:** 24h, 7d and 30d windows from one SQL aggregate. No data returns `null`, not a fake 100%.
- **Per-endpoint intervals:** 60 seconds to 24 hours, each endpoint on its own clock, with a little upward jitter.
- **Housekeeping:** a daily job deletes ping rows older than 30 days and expired refresh tokens.
## How it is built
 
```mermaid
flowchart LR
    Browser["Frontend<br/>HTML, CSS, JS"] -->|REST + JWT| API[FastAPI]
    Browser <-->|WebSocket| API
    API --> DB[(PostgreSQL)]
    subgraph One["One uvicorn worker"]
        API
        Sched["Scheduler<br/>asyncio loop"]
        Cache["Status cache<br/>in memory"]
        WS["WebSocket manager"]
    end
    Sched -->|"due endpoints"| DB
    Sched -->|"httpx, no redirects"| Targets["Monitored URLs"]
    Sched -->|"signed webhook"| Hook["Your webhook"]
    Sched --> Cache
    Sched --> WS
    WS --> Browser
```
 
**One ping, one journey**
 
| Step | What happens |
|---|---|
| **Pick** | Each tick selects active endpoints whose `next_check_at` is due. The time lives in the database, so a restart does not fire a burst of missed checks |
| **Guard** | The URL is re-validated (fresh DNS lookup, every resolved IP must be public) |
| **Ping** | `httpx`, no redirects, hard total timeout, the response body is never read |
| **Decide** | `next_state(...)` returns the new status plus an event: nothing, went down, or recovered |
| **Save** | Ping result, endpoint state, and incident open or close go into **one commit** |
| **Tell** | Cache update, WebSocket broadcast, then the webhook. The DB connection is released before the webhook is sent, so a slow receiver cannot starve the pool |
 
A few decisions worth a sentence each:
 
- **Scheduler = one asyncio loop, not a library.** Fewer dependencies, and the state is in Postgres anyway.
- **Endpoint cap is enforced inside a transaction** (`SELECT ... FOR UPDATE` on the user row). A test fires 6 parallel creates against a cap of 2 and expects exactly 2 to succeed.
- **PyJWT and `bcrypt` directly**, no `passlib`.
- **WebSocket auth is the first message**, not a query string, so tokens stay out of URLs and logs.
- **Offset pagination** on history. Simple today, keyset is the upgrade.
- **httpx's own INFO log is silenced**: it prints full URLs, and URLs can carry secrets in the query string.
## The tests
 
**414 tests, 99% coverage** (815 statements, 6 missed), and CI fails below 90%.
 
- **Unit:** the state machine, uptime math, and the SSRF validator (60 tests, including Hypothesis property tests over blocked IP ranges).
- **Integration:** a real Postgres test database. Auth flow, ownership, endpoint limits, scheduler with mocked HTTP (timeouts, 500s, redirect to a private address), webhooks, WebSockets, rate limits, errors, CORS.
- **Regression:** one test per fixed bug, indexed in `tests/regression/test_regressions.py`.
- **Mutation checks, by hand:** passing tests are not proof. For the critical logic I broke the code on purpose (threshold off by one, SSRF check removed, newest-first order flipped) and confirmed a test failed. Where a mutation survived, I wrote the missing test.
CI runs two jobs. **check:** lint, migrations on an empty database, tests, coverage gate. **docker:** builds the image and imports the app inside it with no test database configured.
 
## Bugs that taught me something
 
- **The green suite that lied.** The dashboard router was never included in `main.py`, and every test still passed, because no test hit the route. Now there is one.
- **The purge that never ran.** A leftover `___` placeholder raised inside a `try/except`, so the daily cleanup silently never executed. Caught on review, then covered by a test.
- **Same signature for every alert.** `sign()` still had a hardcoded key from a tutorial snippet, so every webhook got an identical signature. Fixed and pinned with a test.
- **"Works on my machine."** `httpx` and `email-validator` were missing from the runtime dependencies. My local environment hid it, the Docker CI job caught it. That job exists because of this bug.
## Run it yourself
 
<details>
<summary><b>Backend (Docker)</b></summary>
```bash
git clone https://github.com/Sanjay-jat/api-uptime-monitor.git
cd api-uptime-monitor
cp .env.example .env
```
 
Set `JWT_SECRET` in `.env` to a random string of at least 32 characters, then:
 
```bash
docker compose up --build -d api
curl localhost:8000/health
```
 
API docs: http://localhost:8000/docs. The container runs `alembic upgrade head`, then uvicorn with one worker.
 
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres URL (asyncpg) |
| `JWT_SECRET` | Signing key, at least 32 characters, no default |
| `CORS_ORIGINS` | JSON list of allowed browser origins, exact match, no trailing slash |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | Token lifetimes (15 min / 7 days) |
| `TEST_DATABASE_URL` | Tests only, optional for the app |
 
</details>
<details>
<summary><b>Frontend</b></summary>
Plain HTML, CSS and JS in `frontend/`. No framework, no build step. The backend address is one constant, `API_URL`, at the top of `app.js`.
 
```bash
cd frontend
python -m http.server 3000
```
 
Make sure `http://localhost:3000` is in `CORS_ORIGINS`.
 
</details>
<details>
<summary><b>Tests</b></summary>
```bash
docker compose up -d db_test
pip install -e ".[dev]"
pytest -q --cov=app --cov-report=term-missing
```
 
</details>
<details>
<summary><b>API at a glance</b></summary>
| Area | Routes |
|---|---|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me` |
| Webhook | `PUT /auth/me/webhook` (returns the secret once), `DELETE /auth/me/webhook` |
| Endpoints | `POST /endpoints`, `GET /endpoints`, `GET/PATCH/DELETE /endpoints/{id}` |
| History | `GET /endpoints/{id}/pings`, `/uptime?window=24h\|7d\|30d`, `/incidents` |
| Live | `WS /ws/dashboard`, first message `{"token": "<access token>"}` |
 
Webhook body fields: `event`, `endpoint_id`, `url`, `at`. Verify `X-Signature` with the secret. Replay protection is up to the receiver, use `at`.
 
Rate limits (in memory): register and login 5 per minute per IP, refresh 20 per minute per IP, create endpoint, update endpoint and set webhook 10 per minute per user. A `429` carries `Retry-After`.
 
</details>
## Deployment
 
| Piece | Where |
|---|---|
| Backend | Render (Docker, free) |
| Database | Neon Postgres (free) |
| Frontend | Vercel (free), served from `frontend/` |
| Keep-awake | A Better Stack monitor pings the backend `/health` |
 
## Honest limits
 
1. **One worker only.** The scheduler, status cache, WebSocket manager and rate limiter all live in memory. Two workers would ping everything twice. The upgrade path is Redis plus a leader lock.
2. **Free-tier demo.** Render sleeps after 15 minutes of silence, and checks pause while it sleeps.
3. **Alerts are one attempt.** No retry, no cooldown, and the webhook secret sits in the database as plain text.
4. **DNS rebinding window.** The URL is re-checked before each request, but `httpx` resolves the name again when it connects. Pinning the resolved IP in the transport closes it.
5. **Stateless tokens.** An access token stays valid for up to 15 minutes after logout, and a WebSocket checks its token only when it connects.
6. **Frontend is untested by machines.** Manual testing only, and tokens live in `localStorage`.
---
 
<div align="center">
Built by [Sanjay Jat](https://github.com/Sanjay-jat) · [Source on GitHub](https://github.com/Sanjay-jat/api-uptime-monitor)
 
</div>