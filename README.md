# insta-batch

Async multi-account batch operation framework for Instagram, built on top of
[`insta-wizard`](https://github.com/5ou1e/insta-wizard). Provides an opinionated
structure for running follow / like / comment / publish / monitor / register
tasks across many accounts concurrently — with proxy rotation, device
fingerprint diversity, and session persistence baked in.

> **Authorized use only.** This code is intended for operating accounts you
> own or have explicit permission to automate. Mass account creation and
> automation at scale may violate Instagram's Terms of Service; you are
> responsible for how you use it.

---

## Features

- **Async + concurrent** — `asyncio.Semaphore`-bounded parallelism across accounts
- **Session persistence** — each account's state is cached under `sessions/` and reused across runs
- **Proxy pool** — pull from a remote API (`ApiProxyProvider`) or a static file, with automatic rotation on network errors
- **Device fingerprint diversity** — per-account preset or random (Samsung A16/S23/A54, Pixel 8, Redmi Note 13 Pro)
- **Structured tasks** — follow / unfollow, like / comment, publish photo / reel, monitor, register (email/SMS)
- **Clean separation** — `core/` (infra) and `tasks/` (business logic) so adding new batch actions = writing one `BaseTask` subclass

---

## Quick start

```bash
# 1. Create venv and install
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. Copy config templates
copy .env.example .env
copy config\accounts.yaml.example config\accounts.yaml

# 3. Edit .env (proxy token) and config/accounts.yaml (real credentials)

# 4. First-time login — creates sessions/*.json for every account
python scripts\login_and_save.py

# 5. Run any task
python scripts\run_follow.py
python scripts\run_like.py
python scripts\run_monitor.py
```

---

## Project layout

```
insta-batch/
├── config/
│   ├── settings.yaml              # concurrency / retry / proxy / device
│   └── accounts.yaml              # credentials (gitignored; copy from .example)
├── insta_batch/
│   ├── core/
│   │   ├── config.py              # yaml + .env loader
│   │   ├── account_pool.py        # Account model + pool + session IO
│   │   ├── client_factory.py      # builds MobileClient(device + proxy + transport)
│   │   ├── proxy_provider.py      # ApiProxyProvider / FileProxyProvider
│   │   ├── logger.py              # rich console + file logging
│   │   └── utils.py               # jittered_sleep, chunked
│   ├── tasks/
│   │   ├── base.py                # BaseTask (concurrency + retry + session restore)
│   │   ├── follow.py              # FollowTask / UnfollowTask
│   │   ├── like_comment.py        # LikeTask / CommentTask
│   │   ├── publish.py             # PublishPhotoTask / PublishReelTask
│   │   ├── monitor.py             # MonitorTask (JSONL snapshot to data/)
│   │   └── register.py            # RegisterEmailTask / RegisterSmsTask
│   └── api/
│       ├── app.py                 # FastAPI application factory
│       ├── schemas.py             # Pydantic request/response models
│       ├── deps.py                # API key auth + cached singletons
│       ├── jobs.py                # in-memory JobManager
│       └── routers/               # /v1/accounts, /v1/tasks, /v1/jobs
├── scripts/
│   ├── _common.py                 # bootstrap (config + logging + factory)
│   ├── login_and_save.py          # warm the session cache
│   ├── run_api.py                 # start the HTTP API (uvicorn)
│   ├── run_follow.py
│   ├── run_like.py
│   ├── run_publish.py
│   ├── run_monitor.py
│   └── run_register.py
├── sessions/                      # runtime session JSONs (gitignored)
├── logs/                          # insta_batch.log (gitignored)
└── data/                          # scraper output (gitignored)
```

---

## Writing a new task

Subclass `BaseTask` and implement `run_for_account`. BaseTask handles
concurrency, session restore, and per-account error isolation:

```python
from insta_batch.tasks.base import BaseTask, TaskResult

class MyTask(BaseTask):
    name = "my_task"

    async def run_for_account(self, client, account, payload):
        user = await client.users.get_info_by_username(payload["target"])
        await client.friendships.follow(str(user.pk))
        return TaskResult(
            account=account.username, ok=True, detail=f"followed {user.username}"
        )
```

Drop a script in `scripts/` that calls `bootstrap()` + `MyTask(cfg, factory).execute(...)`.

---

## Proxy configuration

`config/settings.yaml` → `proxy` block:

| Mode | What to set |
|---|---|
| `source: api` | `api_url` + `api_token_env` (name of env var in `.env`) — the API returns a plaintext list or JSON array of `host:port` / `user:pass@host:port` |
| `source: file` | `file_path: config/proxies.txt`, one proxy per line |
| `source: none` | disable proxy entirely |

On transient network errors the transport layer automatically calls
`provide_new()` on the provider and retries — configurable via the `retry` block.

---

## Device fingerprints

Each account can have its own `device_preset` in `accounts.yaml` (stable
across runs), or you can leave it as `random` globally for maximum
diversity. Supported presets: `SAMSUNG_A16`, `SAMSUNG_S23`, `SAMSUNG_A54`,
`PIXEL_8`, `REDMI_NOTE_13_PRO`.

---

## Session lifecycle

1. `login_and_save.py` performs a real login for every enabled account and dumps
   `client.dump_state()` to `sessions/<username>.json`.
2. Every subsequent task run loads that state and verifies with
   `account.get_current_user()`. If the session is stale, the task drops the
   file and re-authenticates automatically.
3. Session files contain auth tokens — **never commit them**. `.gitignore`
   already excludes the entire `sessions/` directory.

---

## Registration

`run_register.py` is a **skeleton**. You must implement an `EmailCodeSignupProvider`
(or `PhoneSmsCodeProvider`) that pulls the verification code from your inbox
or SMS service. The script will refuse to run until you do.

---

## HTTP API

Everything above can also be driven over HTTP. Every task endpoint returns
**`202 Accepted` + `{"job_id": "..."}` immediately**; the caller polls
`/v1/jobs/{job_id}` for progress and results. Authenticate with an
`X-API-Key` header.

> 📖 **Full reference — every endpoint, request/response schema, status
> codes, and multi-language client examples — is in
> [`docs/API.md`](docs/API.md).** The sections below are a quick overview.

### Start the server

```bash
# .env must contain at least API_KEYS
API_KEYS=random-key-1,random-key-2

python scripts\run_api.py        # default 0.0.0.0:8000
# or:
uvicorn insta_batch.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000/docs** for the live Swagger UI.

### Endpoints (overview)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | service banner (no auth) |
| `GET` | `/v1/health` | counts of accounts + active jobs |
| `GET` | `/v1/accounts` | list all accounts + session state |
| `GET` | `/v1/accounts/{username}` | inspect one account |
| `POST` | `/v1/accounts/reload` | reload config/accounts.yaml without restart |
| `POST` | `/v1/tasks/follow` | batch follow (returns job_id) |
| `POST` | `/v1/tasks/unfollow` | batch unfollow |
| `POST` | `/v1/tasks/like` | batch like / unlike |
| `POST` | `/v1/tasks/comment` | batch comment |
| `POST` | `/v1/tasks/publish/photo` | each account posts the same photo |
| `POST` | `/v1/tasks/publish/reel` | each account posts the same reel |
| `POST` | `/v1/tasks/monitor` | snapshot target profiles to data/ |
| `GET` | `/v1/jobs` | list recent jobs |
| `GET` | `/v1/jobs/{job_id}` | job status + per-account results |
| `DELETE` | `/v1/jobs/{job_id}` | cancel a running job |

See [`docs/API.md`](docs/API.md) for the request/response body of each
endpoint, error codes, and the job lifecycle state diagram.

### Account selection

Every task body accepts an `accounts` object to pick which accounts run it:

```json
{"accounts": {"usernames": ["alice", "bob"]}}   // explicit
{"accounts": {"tags": ["group_a"]}}             // by tag
{"accounts": {}}                                 // all enabled accounts
```

### Quick taste

```bash
# Submit — returns 202 {"job_id": "..."}
curl -X POST https://localhost/v1/tasks/follow \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"accounts":{"tags":["group_a"]},"usernames":["instagram"]}'

# Poll — returns status, progress, per-account results
curl https://localhost/v1/jobs/<job_id> -H "X-API-Key: $KEY"
```

Full bash, Python (sync + async), and TypeScript examples in
[`docs/API.md#end-to-end-examples`](docs/API.md#end-to-end-examples).

### Limits of the MVP

- **Cross-worker cancel not supported** — `DELETE /v1/jobs/{id}` only works
  on the uvicorn worker that originally submitted the job. Cancel returns
  `409` if the job landed elsewhere. (Fix: add a `cancel_requested` flag
  in the Redis record and have runners poll it.)
- **No built-in rate limiting** — stock Caddy doesn't ship rate-limit.
  See the `Caddyfile` for the custom-build snippet; uncomment the
  `rate_limit` block once you've swapped in a Caddy image built with
  `github.com/mholt/caddy-ratelimit`.

---

## Docker deployment

Everything above runs in a 3-service compose stack: **redis** (job store) +
**api** (FastAPI × 4 uvicorn workers) + **caddy** (reverse proxy with TLS
and IP allow-list).

### One-command bring-up

```bash
# Clone onto your Linux server
git clone https://github.com/quanzhilongquanzhilong99999999-arch/insta-batch.git
cd insta-batch

# Fill in secrets & accounts
cp .env.example .env                             # edit API_KEYS, proxy token
cp config/accounts.yaml.example config/accounts.yaml   # edit credentials
vim Caddyfile                                    # put caller IPs into @allowed

docker compose up -d --build
docker compose logs -f api
```

### What's exposed

| Port | Service | Purpose |
|---|---|---|
| `80`  | caddy → 301 | redirect to HTTPS |
| `443` | caddy | TLS (self-signed internal CA, since no domain) |
| — | api   | only reachable from inside the compose network |
| — | redis | only reachable from inside the compose network |

### TLS without a domain

`Caddyfile` uses `tls internal` — Caddy generates a self-signed CA and
certificate on first boot. Callers have two options:

- **Trust Caddy's root CA**: copy `data/caddy/pki/authorities/local/root.crt`
  out of the `caddy_data` volume onto each caller machine's trust store.
- **Skip verification**: call with `curl -k` / `httpx.Client(verify=False)`.
  Fine when the IP allow-list is doing the real authentication work.

When you later acquire a real domain, change `:443` in the Caddyfile to
your hostname (e.g. `api.example.com`) and drop `tls internal` — Caddy
will auto-issue Let's Encrypt.

### Multi-worker + Redis

The compose stack sets `REDIS_URL=redis://redis:6379/0` on the `api`
service, so all 4 uvicorn workers share the same `JobStore`. Without
`REDIS_URL` set, the API silently falls back to the in-memory store —
single-worker only.

### IP allow-list (required)

The default `Caddyfile` allows only example IPs (`203.0.113.10`,
`198.51.100.0/24`). **The service returns `403` for everything else**
until you edit the `@allowed` block with your callers' real public IPs.
Apply changes without downtime:

```bash
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

### Persisted state

| Volume | Contents |
|---|---|
| `redis_data`    | append-only Redis log (jobs, index, cancellation flags) |
| `sessions_data` | per-account session JSONs (from `login_and_save`) |
| `logs_data`     | `insta_batch.log` rotation |
| `data_data`     | task output (monitor snapshots etc.) |
| `caddy_data`    | self-signed CA, access logs |

All survive `docker compose down`; use `docker compose down -v` to wipe.

### Operational cheatsheet

```bash
# Tail api logs across all 4 workers
docker compose logs -f api

# Peek at active jobs
docker compose exec redis redis-cli ZRANGE insta_batch:jobs:index 0 -1 WITHSCORES

# Reload accounts.yaml without downtime (all workers refresh)
curl -k https://your-host/v1/accounts/reload -X POST -H "X-API-Key: <key>"

# Scale uvicorn workers (re-build image with a different --workers flag)
# or use compose deploy.replicas if you split uvicorn into separate containers
```

---

## License

MIT
