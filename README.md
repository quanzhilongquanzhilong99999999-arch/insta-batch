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

### Start the server

```bash
# .env must contain at least API_KEYS
API_KEYS=random-key-1,random-key-2

python scripts\run_api.py        # default 0.0.0.0:8000
# or:
uvicorn insta_batch.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000/docs** for the live Swagger UI.

### Endpoints

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

### Account selection

Every task body accepts an `accounts` object to pick which accounts run it:

```json
{"accounts": {"usernames": ["alice", "bob"]}}   // explicit
{"accounts": {"tags": ["group_a"]}}             // by tag
{"accounts": {}}                                 // all enabled accounts
```

### curl example

```bash
# Submit
curl -X POST http://localhost:8000/v1/tasks/follow \
  -H "X-API-Key: random-key-1" \
  -H "Content-Type: application/json" \
  -d '{"accounts":{"tags":["group_a"]},"usernames":["instagram","natgeo"]}'
# → {"job_id": "ba2073f29fbd45b8..."}

# Poll
curl http://localhost:8000/v1/jobs/ba2073f29fbd45b8... \
  -H "X-API-Key: random-key-1"
```

### Python client example

```python
import httpx, time

KEY = "random-key-1"
BASE = "http://localhost:8000"
H = {"X-API-Key": KEY}

with httpx.Client(base_url=BASE, headers=H, timeout=30) as c:
    r = c.post("/v1/tasks/follow", json={
        "accounts": {"tags": ["group_a"]},
        "usernames": ["instagram"],
    }).raise_for_status()
    job_id = r.json()["job_id"]

    while True:
        job = c.get(f"/v1/jobs/{job_id}").raise_for_status().json()
        if job["status"] in ("completed", "failed", "canceled"):
            print(job)
            break
        time.sleep(2)
```

### Limits of the MVP

- **Single process** — if you run multiple uvicorn workers, each has its
  own `JobManager` and jobs are not shared. Stay on one worker, or upgrade
  the JobManager to SQLite / Redis first.
- **State lost on restart** — jobs in memory disappear when the process
  dies. Results already written to `data/` are preserved.
- **No rate limiting** — add a reverse proxy (Caddy / Nginx) or a
  middleware if you expose the service publicly.

---

## License

MIT
