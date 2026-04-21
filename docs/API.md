# insta-batch HTTP API Reference

Complete reference for the REST API exposed by `insta_batch.api.app`.

**Base URL**
- Direct (dev): `http://localhost:8000`
- Behind Caddy (prod): `https://<your-host>/` (self-signed unless you configure a domain)

**OpenAPI/Swagger**: `GET /docs` serves a live Swagger UI; `GET /openapi.json` serves the raw spec.

**Interactive Redoc**: `GET /redoc`.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Conventions](#conventions)
3. [Data Models](#data-models)
4. [Endpoints — Health](#endpoints--health)
    - [GET /](#get-)
    - [GET /v1/health](#get-v1health)
5. [Endpoints — Accounts](#endpoints--accounts)
    - [GET /v1/accounts](#get-v1accounts)
    - [GET /v1/accounts/{username}](#get-v1accountsusername)
    - [POST /v1/accounts/reload](#post-v1accountsreload)
6. [Endpoints — Tasks](#endpoints--tasks)
    - [POST /v1/tasks/follow](#post-v1tasksfollow)
    - [POST /v1/tasks/unfollow](#post-v1tasksunfollow)
    - [POST /v1/tasks/like](#post-v1taskslike)
    - [POST /v1/tasks/comment](#post-v1taskscomment)
    - [POST /v1/tasks/publish/photo](#post-v1taskspublishphoto)
    - [POST /v1/tasks/publish/reel](#post-v1taskspublishreel)
    - [POST /v1/tasks/monitor](#post-v1tasksmonitor)
7. [Endpoints — Jobs](#endpoints--jobs)
    - [GET /v1/jobs](#get-v1jobs)
    - [GET /v1/jobs/{job_id}](#get-v1jobsjob_id)
    - [DELETE /v1/jobs/{job_id}](#delete-v1jobsjob_id)
8. [Error Codes](#error-codes)
9. [Job Lifecycle](#job-lifecycle)
10. [End-to-End Examples](#end-to-end-examples)
11. [FAQ](#faq)

---

## Authentication

Every endpoint except `GET /` requires an API key passed in the `X-API-Key`
request header.

```
X-API-Key: your-long-random-key-here
```

Keys are configured on the server via the `API_KEYS` environment variable
(comma-separated list in `.env`). The server issues **one key per caller**
so you can revoke them independently.

### Auth error responses

| Condition | Status | Body |
|---|---|---|
| Header missing | `422` | `{"detail": [{"type": "missing", "loc": ["header", "X-API-Key"], ...}]}` |
| Header value not in `API_KEYS` | `401` | `{"detail": "Invalid API key"}` |
| Server has no `API_KEYS` configured | `500` | `{"detail": "Server has no API_KEYS configured"}` |

---

## Conventions

### Async task pattern

**Every task endpoint is asynchronous.** A successful submission returns
**`202 Accepted`** with a `job_id` _immediately_; the real work runs in the
background. The client then polls `GET /v1/jobs/{job_id}` until
`status` is `completed`, `failed`, or `canceled`.

```
Client                  Server
  │ POST /v1/tasks/follow   │
  │ ───────────────────────▶│
  │ 202 {"job_id": "abc"}   │
  │ ◀───────────────────────│
  │                         │  … runs across accounts …
  │ GET /v1/jobs/abc        │
  │ ───────────────────────▶│
  │ 200 {"status":"running"}│
  │ ◀───────────────────────│
  │  (wait 2–5s, repeat)    │
  │ GET /v1/jobs/abc        │
  │ ───────────────────────▶│
  │ 200 {"status":"completed",│
  │      "results":[…]}     │
  │ ◀───────────────────────│
```

Poll interval: **2–5 seconds** is reasonable. Shorter wastes requests.

### Content type

All request and response bodies are `application/json; charset=utf-8`.
The server responds with an explicit `Content-Type`; callers should send
`Content-Type: application/json` on every `POST` / `DELETE`.

### Timestamps

ISO-8601 strings in UTC, e.g. `"2026-04-21T10:53:53.419056+00:00"`.
They round-trip through Python `datetime.fromisoformat()` and JS `new Date(...)`.

### Request IDs

The service does not currently emit a correlation ID header. Use the
`job_id` as your end-to-end trace key — it's unique and appears in all logs.

### Pagination

Only `GET /v1/jobs?limit=N` is paginated (no cursor yet; newest first).
All other list endpoints return the complete set.

---

## Data Models

Types below are the canonical schemas referenced by the endpoint docs.
They map 1:1 onto the Pydantic models in
[`insta_batch/api/schemas.py`](../insta_batch/api/schemas.py).

### `AccountSelector`

Embedded in every task request to choose which accounts run the task.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `usernames` | `string[] \| null` | no | `null` | Explicit list of account usernames. **Takes precedence over `tags`**. Non-matching / disabled usernames are silently dropped. |
| `tags` | `string[] \| null` | no | `null` | Select accounts whose `tags` list intersects any of these. Ignored when `usernames` is set. |

**Selection semantics** (matches `routers/tasks.py:_select_accounts`):

1. If `usernames` is non-empty → intersect with enabled accounts.
2. Else → `pool.active(tags=sel.tags)`; empty `tags` ⇒ every enabled account.
3. If the final set is empty → the endpoint responds `400 "No enabled accounts matched the selector"`.

**Examples**:

```json
{"accounts": {"usernames": ["alice", "bob"]}}          // explicit two accounts
{"accounts": {"tags": ["group_a"]}}                    // by tag
{"accounts": {"tags": ["group_a", "vip"]}}             // intersect with ANY of these tags
{"accounts": {}}                                        // every enabled account
```

### `JobProgress`

| Field | Type | Description |
|---|---|---|
| `total` | `int` | Total number of accounts participating in the job. |
| `ok` | `int` | Accounts whose run returned success. |
| `failed` | `int` | Accounts whose run raised (see `results[i].detail` for the exception). |
| `skipped` | `int` | Accounts intentionally skipped (e.g. no matching per-account payload). |

Conservation: `ok + failed + skipped ≤ total` during `running`;
equality holds when `status == "completed"` or `"failed"`.

### `JobResultEntry`

One record per account.

| Field | Type | Description |
|---|---|---|
| `account` | `string` | Account username this record corresponds to. |
| `ok` | `boolean` | Whether the per-account action succeeded. |
| `detail` | `string` | Human-readable summary; on failure contains `<ExceptionType>: <message>`. |

### `JobView` — the core response shape of every job query

| Field | Type | Description |
|---|---|---|
| `job_id` | `string` (hex) | 32-char hex ID returned at submission time. |
| `task_type` | `string` | One of `follow` / `unfollow` / `like` / `comment` / `publish_photo` / `publish_reel` / `monitor`. |
| `status` | `"pending" \| "running" \| "completed" \| "failed" \| "canceled"` | See [Job Lifecycle](#job-lifecycle). |
| `created_at` | ISO-8601 datetime | When the submission reached the queue. |
| `started_at` | ISO-8601 datetime \| `null` | When the runner actually picked it up (usually ms after `created_at`). |
| `finished_at` | ISO-8601 datetime \| `null` | Terminal timestamp. `null` until the job leaves `running`. |
| `progress` | [`JobProgress`](#jobprogress) | Live counters. |
| `results` | [`JobResultEntry[]`](#jobresultentry) | Per-account results; populated when the job terminates. |
| `error` | `string \| null` | Populated only on top-level runner crash (rare); per-account errors live in `results`, not here. |

### `JobIdResponse`

Returned by every task submission.

| Field | Type |
|---|---|
| `job_id` | `string` |

### `AccountView`

Returned by `GET /v1/accounts[/{username}]`.

| Field | Type | Description |
|---|---|---|
| `username` | `string` | As configured in `accounts.yaml`. |
| `enabled` | `boolean` | If false, the account is skipped by every task. |
| `tags` | `string[]` | Used by `AccountSelector.tags`. |
| `has_session` | `boolean` | `true` once `login_and_save` (or a first task) has written `sessions/<username>.json`. |
| `device_preset` | `string \| null` | Per-account override (one of `SAMSUNG_A16`, `SAMSUNG_S23`, `SAMSUNG_A54`, `PIXEL_8`, `REDMI_NOTE_13_PRO`, or `null` meaning "use global default"). |
| `proxy_set` | `boolean` | Whether this account has a sticky proxy in `accounts.yaml`. The proxy string itself is **not returned** (never leak credentials). |

### `HealthResponse`

| Field | Type |
|---|---|
| `status` | `"ok"` |
| `version` | `string` |
| `accounts_total` | `int` |
| `accounts_enabled` | `int` |
| `jobs_active` | `int` (count of jobs in `pending`+`running`) |

### `StandardOK`

| Field | Type |
|---|---|
| `ok` | `boolean` (always `true`) |
| `message` | `string` |

### `ErrorResponse`

All 4xx/5xx responses have this shape **except** 422 (FastAPI's validation
errors, which come back as `{"detail": [<error array>]}`).

| Field | Type |
|---|---|
| `detail` | `string` |

---

## Endpoints — Health

### `GET /`

Service banner. **No auth required** — use this for uptime checks.

**Request**

```http
GET / HTTP/1.1
Host: localhost:8000
```

**Response — 200 OK**

```json
{
  "service": "insta-batch",
  "version": "0.1.0",
  "docs": "/docs"
}
```

---

### `GET /v1/health`

Liveness + configuration summary. Safe to call frequently.

**Headers**

| Header | Required | Value |
|---|---|---|
| `X-API-Key` | ✅ | Any configured key |

**Response — 200 OK** ([`HealthResponse`](#healthresponse))

```json
{
  "status": "ok",
  "version": "0.1.0",
  "accounts_total": 12,
  "accounts_enabled": 10,
  "jobs_active": 3
}
```

**curl**

```bash
curl https://api.example.com/v1/health -H "X-API-Key: $KEY"
```

---

## Endpoints — Accounts

The accounts API is read-only. Mutations (adding / editing accounts) go
through `config/accounts.yaml` + `POST /v1/accounts/reload`.

### `GET /v1/accounts`

List every account configured on the server, enabled or not.

**Response — 200 OK** — `AccountView[]`

```json
[
  {
    "username": "alice_demo",
    "enabled": true,
    "tags": ["group_a"],
    "has_session": true,
    "device_preset": "PIXEL_8",
    "proxy_set": true
  },
  {
    "username": "bob_demo",
    "enabled": false,
    "tags": ["group_b"],
    "has_session": false,
    "device_preset": null,
    "proxy_set": false
  }
]
```

**curl**

```bash
curl https://api.example.com/v1/accounts -H "X-API-Key: $KEY"
```

---

### `GET /v1/accounts/{username}`

Inspect a single account.

**Path parameters**

| Name | Type | Description |
|---|---|---|
| `username` | string | Must exist in `accounts.yaml`; lookup is case-sensitive. |

**Response — 200 OK** — [`AccountView`](#accountview)

**Response — 404 Not Found**

```json
{"detail": "account 'ghost_user' not found"}
```

**curl**

```bash
curl https://api.example.com/v1/accounts/alice_demo -H "X-API-Key: $KEY"
```

---

### `POST /v1/accounts/reload`

Hot-reload `config/accounts.yaml` and `config/settings.yaml` without
restarting the server. Clears the cached `Config` / `AccountPool` /
`ClientFactory` singletons and re-parses from disk — any YAML error
surfaces immediately in the response.

In a multi-worker deployment, **each worker caches independently**, so
hitting this endpoint once may only reload one of N workers. Call it N
times (FastAPI's round-robin will eventually hit all of them) or restart
the container for guaranteed propagation.

**Request**: empty body.

**Response — 200 OK** — [`StandardOK`](#standardok)

```json
{"ok": true, "message": "config reloaded"}
```

**Response — 500** (only when accounts.yaml has a YAML or field error)

```json
{"detail": "Internal Server Error"}
```
Check server logs for the real exception.

**curl**

```bash
curl -X POST https://api.example.com/v1/accounts/reload -H "X-API-Key: $KEY"
```

---

## Endpoints — Tasks

All task endpoints share the same contract:

- **Request body**: a JSON document with an embedded [`AccountSelector`](#accountselector) + task-specific fields.
- **Response on success**: `202 Accepted` + [`JobIdResponse`](#jobidresponse).
- **Response when no account matches**: `400 Bad Request` (same `ErrorResponse` shape below).
- **Response on auth failure**: `401` / `422` (see [Authentication](#authentication)).

Task failures _at the per-account level_ do **not** fail the HTTP request —
the task endpoint returns `202` regardless, and you learn about failures
by polling `GET /v1/jobs/{job_id}` and inspecting `results[i].ok`.

### Selector error — applies to every task endpoint

**Response — 400 Bad Request**

```json
{"detail": "No enabled accounts matched the selector"}
```

---

### `POST /v1/tasks/follow`

Make each selected account follow a list of target users.

**Request body**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `accounts` | [`AccountSelector`](#accountselector) | no | `{}` | Which accounts will do the following. |
| `usernames` | `string[] \| null` | no | `null` | Target Instagram usernames. Resolved to `pk` IDs on the server. |
| `user_ids` | `string[] \| null` | no | `null` | Target Instagram numeric user IDs (pk). Faster — skips the username→id lookup. |

At least one of `usernames` or `user_ids` should be set, otherwise the
task runs but follows nothing (each account returns `"followed 0 users"`).

**Example request**

```json
{
  "accounts": {"tags": ["group_a"]},
  "usernames": ["instagram", "natgeo"],
  "user_ids": ["12345678"]
}
```

**Response — 202 Accepted**

```json
{"job_id": "ba2073f29fbd45b8afdfc27cc30fde6c"}
```

**curl**

```bash
curl -X POST https://api.example.com/v1/tasks/follow \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"accounts":{"tags":["group_a"]},"usernames":["instagram"]}'
```

**Python httpx**

```python
import httpx

r = httpx.post(
    "https://api.example.com/v1/tasks/follow",
    headers={"X-API-Key": KEY, "Content-Type": "application/json"},
    json={
        "accounts": {"tags": ["group_a"]},
        "usernames": ["instagram", "natgeo"],
    },
    timeout=30,
).raise_for_status()
job_id = r.json()["job_id"]
```

---

### `POST /v1/tasks/unfollow`

Symmetric counterpart of `/follow`. Same request/response shape.

**Request body** — same as [`POST /v1/tasks/follow`](#post-v1tasksfollow).

**Example request**

```json
{
  "accounts": {"usernames": ["alice_demo"]},
  "usernames": ["instagram"]
}
```

---

### `POST /v1/tasks/like`

Like (or unlike) one or more media items from each selected account.

**Request body**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `accounts` | [`AccountSelector`](#accountselector) | no | `{}` | Which accounts do the liking. |
| `media_ids` | `string[]` | **yes** | — | Media IDs in Instagram's `"<shortcode_pk>_<owner_pk>"` format, e.g. `"3400123456789012345_17841400000000000"`. |
| `unlike` | `boolean` | no | `false` | When `true`, unlike instead of like. |

**Example request — like**

```json
{
  "accounts": {"tags": ["group_a"]},
  "media_ids": [
    "3400123456789012345_17841400000000000",
    "3400987654321098765_17841400000000000"
  ]
}
```

**Example request — unlike**

```json
{
  "accounts": {"tags": ["group_a"]},
  "media_ids": ["3400123456789012345_17841400000000000"],
  "unlike": true
}
```

**curl**

```bash
curl -X POST https://api.example.com/v1/tasks/like \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"accounts":{"tags":["group_a"]},"media_ids":["3400123456789012345_17841400000000000"]}'
```

---

### `POST /v1/tasks/comment`

Post one or more comments across accounts. `items` is an array of
`[media_id, comment_text]` tuples — each account runs **every item**
in the list.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `accounts` | [`AccountSelector`](#accountselector) | no | Which accounts comment. |
| `items` | `[string, string][]` | **yes** | `[[media_id, text], ...]`. First element = media_id, second = comment text. |

**Example request**

```json
{
  "accounts": {"tags": ["group_a"]},
  "items": [
    ["3400123456789012345_17841400000000000", "🔥"],
    ["3400987654321098765_17841400000000000", "great shot!"]
  ]
}
```

---

### `POST /v1/tasks/publish/photo`

Each selected account posts the **same photo**. The image file must
exist on the server's filesystem (usually under the `data/` volume).

**Request body**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `accounts` | [`AccountSelector`](#accountselector) | no | `{}` | Publishers. |
| `image_path` | `string` | **yes** | — | Server-side path. Absolute or relative to the project root. Inside Docker this typically means the `/app/data` directory — copy the file onto the `data_data` volume first (e.g. `docker cp my.jpg insta-batch-api-1:/app/data/`). |
| `caption` | `string` | no | `""` | Caption applied to every account's post. |

**Example request**

```json
{
  "accounts": {"tags": ["group_a"]},
  "image_path": "data/campaign_q2.jpg",
  "caption": "Happy Friday! 🎉"
}
```

**Notes**
- The image is uploaded **once per account** — if you have 10 accounts,
  Instagram sees 10 independent posts of the same bytes.
- For per-account images or captions, use one `POST /v1/tasks/publish/photo`
  request per (account, image) pair.

---

### `POST /v1/tasks/publish/reel`

Like `/publish/photo` but for Reels (short videos).

**Request body**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `accounts` | [`AccountSelector`](#accountselector) | no | `{}` | Publishers. |
| `video_path` | `string` | **yes** | — | Server-side video file path. |
| `caption` | `string` | no | `""` | |
| `thumbnail_path` | `string \| null` | no | `null` | Optional still-frame override. If not given, insta-wizard auto-generates a cover frame from the video. |
| `share_to_feed` | `boolean` | no | `true` | If `true`, the Reel also appears in the main feed. If `false`, it lives only in the Reels tab. |

**Example request**

```json
{
  "accounts": {"tags": ["group_a"]},
  "video_path": "data/reel_2026_04.mp4",
  "caption": "New drop ✨",
  "thumbnail_path": "data/reel_2026_04_cover.jpg",
  "share_to_feed": true
}
```

---

### `POST /v1/tasks/monitor`

Scrape profile metadata for a list of target users, using each selected
account as a "viewer". Results append to a JSONL file under `data/`.

**Request body**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `accounts` | [`AccountSelector`](#accountselector) | no | `{}` | Each account performs the scrape independently — useful for redundancy or cross-verification. |
| `usernames` | `string[] \| null` | no | `null` | Target usernames to snapshot. **`null` means "snapshot the running account itself"** (useful for checking your own accounts' follower counts over time). |
| `output_file` | `string` | no | `"monitor.jsonl"` | Relative to `data/` (or absolute). Multiple runs **append**; delete the file to reset. |

**Snapshot fields written to JSONL** (one JSON object per line):

```json
{
  "checked_at": "2026-04-21T10:53:53+00:00",
  "checked_by": "alice_demo",
  "username": "instagram",
  "pk": "25025320",
  "full_name": "Instagram",
  "follower_count": 675000000,
  "following_count": 75,
  "media_count": 8120,
  "is_private": false,
  "is_verified": true
}
```

**Example request**

```json
{
  "accounts": {"tags": ["group_a"]},
  "usernames": ["instagram", "natgeo", "nasa"],
  "output_file": "monitor_2026_04.jsonl"
}
```

---

## Endpoints — Jobs

### `GET /v1/jobs`

List the most recent jobs, newest first. Ephemeral — historic entries
expire after 7 days (set by the `RedisJobStore` TTL).

**Query parameters**

| Name | Type | Default | Range |
|---|---|---|---|
| `limit` | int | 50 | 1 – 500 |

**Response — 200 OK** — [`JobView[]`](#jobview--the-core-response-shape-of-every-job-query)

```json
[
  {
    "job_id": "ba2073f29fbd45b8afdfc27cc30fde6c",
    "task_type": "follow",
    "status": "running",
    "created_at": "2026-04-21T10:17:31.379492+00:00",
    "started_at": "2026-04-21T10:17:31.382485+00:00",
    "finished_at": null,
    "progress": {"total": 2, "ok": 0, "failed": 0, "skipped": 0},
    "results": [],
    "error": null
  }
]
```

**curl**

```bash
curl "https://api.example.com/v1/jobs?limit=20" -H "X-API-Key: $KEY"
```

---

### `GET /v1/jobs/{job_id}`

Fetch one job's current state. **Primary endpoint for polling.**

**Path parameters**

| Name | Type | Description |
|---|---|---|
| `job_id` | string | 32-char hex from the submission response. |

**Response — 200 OK** — [`JobView`](#jobview--the-core-response-shape-of-every-job-query)

See the sample in [GET /v1/jobs](#get-v1jobs); a completed `JobView`
includes populated `results[]` and a non-null `finished_at`.

**Response — 404 Not Found**

```json
{"detail": "job not found"}
```

Reasons a job can "disappear":
1. Wrong `job_id`.
2. Job was created > 7 days ago and TTL-expired out of Redis.
3. Single-worker mode restarted (memory backend only).

**curl**

```bash
curl https://api.example.com/v1/jobs/ba2073f29fbd45b8afdfc27cc30fde6c \
  -H "X-API-Key: $KEY"
```

---

### `DELETE /v1/jobs/{job_id}`

Request cancellation. Only cancels if **this uvicorn worker** submitted
the job (cross-worker cancel is a known limitation — see
[README § Limits of the MVP](../README.md#limits-of-the-mvp)).

**Path parameters**

| Name | Type | Description |
|---|---|---|
| `job_id` | string | Job to cancel. |

**Response — 200 OK** — [`StandardOK`](#standardok)

```json
{"ok": true, "message": "cancel signal sent"}
```

Cancellation propagates via `asyncio.Task.cancel()`; the job transitions
to `"canceled"` on its next await boundary (usually within a second).

**Response — 409 Conflict**

```json
{
  "detail": "Job not cancellable on this worker. Either it is already finished, or it was submitted to a different worker (cross-worker cancel is not supported in this version)."
}
```

**Workaround for cross-worker cancel**: retry `DELETE` a few times — load
balancer's round-robin will eventually hit the owning worker. Or plan for
the job to complete normally (most batch tasks finish in minutes).

**curl**

```bash
curl -X DELETE https://api.example.com/v1/jobs/ba2073f29fbd45b8afdfc27cc30fde6c \
  -H "X-API-Key: $KEY"
```

---

## Error Codes

Service-wide summary of what each status code means in this API.

| Status | When it fires | Body shape |
|---|---|---|
| `200 OK` | Normal read (`GET /v1/health`, `GET /v1/accounts`, `GET /v1/jobs/...`, etc.) or a successful non-task action (`POST /v1/accounts/reload`, `DELETE /v1/jobs/...`). | Endpoint-specific JSON. |
| `202 Accepted` | Task successfully enqueued; the actual work runs in the background. | `{"job_id": "…"}` |
| `400 Bad Request` | `AccountSelector` matched zero enabled accounts. | `{"detail": "No enabled accounts matched the selector"}` |
| `401 Unauthorized` | `X-API-Key` header present but not in `API_KEYS`. | `{"detail": "Invalid API key"}` |
| `404 Not Found` | Account / job ID doesn't exist. | `{"detail": "…not found"}` |
| `409 Conflict` | `DELETE /v1/jobs/{id}` against a finished or non-local job. | `{"detail": "Job not cancellable…"}` |
| `422 Unprocessable Entity` | Request body or headers failed Pydantic validation (missing required field, wrong type, missing `X-API-Key`, etc.). | `{"detail": [{"loc": […], "msg": "…", "type": "…"}, …]}` |
| `500 Internal Server Error` | Either `API_KEYS` env var is empty on the server, or an unhandled exception in the route. | `{"detail": "…"}` — check `logs/insta_batch.log`. |

---

## Job Lifecycle

```
     submit               picked up             runner returned
        │                     │                       │
        ▼                     ▼                       ▼
   ┌─────────┐            ┌─────────┐            ┌───────────┐
   │ pending │ ─────────▶ │ running │ ─────────▶ │ completed │
   └─────────┘            └─────────┘            └───────────┘
                              │                  │
                              │ runner raised    │ terminal →
                              ▼                  ▼  results[] populated
                          ┌─────────┐         ┌───────────┐
                          │ failed  │         │           │
                          └─────────┘         │           │
                              │               │           │
                              │ DELETE /jobs/ │           │
                              ▼ cancelled     │           │
                          ┌──────────┐        │           │
                          │ canceled │ ◀──────┘           │
                          └──────────┘                    │
                                                          │
                          (finished_at set in all cases ─ ┘)
```

`pending → running` typically takes < 10 ms on a warm server. The
majority of wall-clock time is spent in `running` while the batch
iterates over accounts.

### State transitions — observable guarantees

| Transition | Fires when | `progress` | `results` | `finished_at` |
|---|---|---|---|---|
| `pending → running` | Runner started. | `total` set; counters at 0. | `[]` | `null` |
| `running → completed` | Every account has a result. | counters filled. | filled | ISO timestamp |
| `running → failed` | Top-level runner exception (rare — usually a bug in the server, not per-account). | counters may be partial. | partial | ISO timestamp |
| `running → canceled` | Client called `DELETE /v1/jobs/{id}` and this worker owned it. | partial. | partial | ISO timestamp |

`results` is populated **in-place as accounts complete**, so you can see
partial results by polling mid-`running`. However, `progress.ok/failed/
skipped` are updated **only when the job terminates** (a lightweight
trade-off to avoid one Redis round-trip per account).

---

## End-to-End Examples

### Bash + curl — full lifecycle

```bash
#!/usr/bin/env bash
set -euo pipefail
KEY="${INSTA_BATCH_KEY:?set INSTA_BATCH_KEY}"
BASE="${INSTA_BATCH_URL:-https://api.example.com}"

# 1. Sanity check
curl -fs "$BASE/v1/health" -H "X-API-Key: $KEY" | jq

# 2. Submit a monitor job
JOB=$(curl -fs -X POST "$BASE/v1/tasks/monitor" \
    -H "X-API-Key: $KEY" \
    -H "Content-Type: application/json" \
    -d '{"accounts":{"tags":["group_a"]},"usernames":["instagram","natgeo"]}' \
  | jq -r .job_id)
echo "submitted job: $JOB"

# 3. Poll until terminal
while true; do
    STATUS=$(curl -fs "$BASE/v1/jobs/$JOB" -H "X-API-Key: $KEY" | jq -r .status)
    echo "  status: $STATUS"
    case "$STATUS" in
        completed|failed|canceled) break ;;
    esac
    sleep 3
done

# 4. Show results
curl -fs "$BASE/v1/jobs/$JOB" -H "X-API-Key: $KEY" | jq
```

### Python `httpx` — async client

```python
import asyncio
import httpx

KEY = "your-api-key"
BASE = "https://api.example.com"
HEADERS = {"X-API-Key": KEY, "Content-Type": "application/json"}


async def submit_and_wait(client: httpx.AsyncClient, path: str, payload: dict) -> dict:
    r = await client.post(path, json=payload, headers=HEADERS)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    print(f"submitted {path} → {job_id}")

    while True:
        r = await client.get(f"/v1/jobs/{job_id}", headers=HEADERS)
        r.raise_for_status()
        job = r.json()
        if job["status"] in ("completed", "failed", "canceled"):
            return job
        await asyncio.sleep(3)


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30, verify=False) as c:
        # verify=False because Caddy's internal TLS is self-signed;
        # remove when you move to a real domain.

        result = await submit_and_wait(
            c,
            "/v1/tasks/follow",
            {"accounts": {"tags": ["group_a"]}, "usernames": ["instagram"]},
        )
        print(f"job done — ok={result['progress']['ok']}  failed={result['progress']['failed']}")
        for r in result["results"]:
            tag = "OK " if r["ok"] else "ERR"
            print(f"  {tag} {r['account']}: {r['detail']}")


asyncio.run(main())
```

### Python `httpx` — sync client

```python
import httpx, time

KEY, BASE = "your-api-key", "https://api.example.com"

with httpx.Client(base_url=BASE, headers={"X-API-Key": KEY}, verify=False, timeout=30) as c:
    job_id = c.post(
        "/v1/tasks/like",
        json={
            "accounts": {"tags": ["group_a"]},
            "media_ids": ["3400123456789012345_17841400000000000"],
        },
    ).raise_for_status().json()["job_id"]

    while True:
        job = c.get(f"/v1/jobs/{job_id}").raise_for_status().json()
        if job["status"] in ("completed", "failed", "canceled"):
            break
        time.sleep(3)

    print(job)
```

### Node.js / TypeScript — `fetch`

```typescript
const KEY = process.env.INSTA_BATCH_KEY!;
const BASE = process.env.INSTA_BATCH_URL ?? "https://api.example.com";
const H = { "X-API-Key": KEY, "Content-Type": "application/json" };

async function submitAndWait(path: string, body: unknown): Promise<any> {
  const sub = await fetch(`${BASE}${path}`, {
    method: "POST", headers: H, body: JSON.stringify(body),
  });
  if (!sub.ok) throw new Error(`submit failed: ${sub.status} ${await sub.text()}`);
  const { job_id } = await sub.json();

  while (true) {
    const j = await fetch(`${BASE}/v1/jobs/${job_id}`, { headers: H });
    const job = await j.json();
    if (["completed", "failed", "canceled"].includes(job.status)) return job;
    await new Promise(r => setTimeout(r, 3000));
  }
}

const job = await submitAndWait("/v1/tasks/follow", {
  accounts: { tags: ["group_a"] },
  usernames: ["instagram"],
});
console.log(`done — ok=${job.progress.ok} failed=${job.progress.failed}`);
```

---

## FAQ

**Q: Can I submit two jobs in parallel for the same account?**
Technically yes — nothing in the API rejects it. In practice Instagram
will likely rate-limit or flag the account for unusual behavior. Prefer
one active job per account.

**Q: How long do I have to poll? Will jobs disappear?**
Job records live in Redis with a **7-day TTL**. Results written to
`data/` (e.g. the monitor JSONL) are kept until you delete them manually
or `docker compose down -v` wipes the volume.

**Q: The job shows `status=completed` but `progress.ok=0`. Why?**
`completed` means "the job finished running all its accounts". Per-account
failures show up in `results[].ok=false` and `progress.failed`. `status=failed`
is reserved for top-level runner crashes, which are server bugs — not the
common case.

**Q: How do I pass an image/video?**
Currently by **filesystem path** on the server. Pre-stage files into the
`data_data` docker volume (e.g. `docker cp my.jpg insta-batch-api-1:/app/data/`).
A proper multipart upload endpoint is on the roadmap — PRs welcome.

**Q: Can two callers with different API keys see each other's jobs?**
Yes — there's no per-key isolation in the current version. All keys share
the global job list. If you need isolation, prefix your own `task_type`
or filter by `job_id`s you've stored locally.

**Q: The API is returning `500 "Server has no API_KEYS configured"`.**
The server was started without `API_KEYS` in its environment. Edit `.env`
on the server, then `docker compose restart api`.

**Q: What Instagram API backend does this use?**
All Instagram traffic is handled by
[`insta-wizard`](https://github.com/5ou1e/insta-wizard) (mobile private API,
mimicking the Android app). Rate limits, checkpoints, and challenges are
Instagram's — this service just surfaces them in `results[].detail`.

**Q: Is there a rate limit on the API itself?**
Not yet on the application layer. The `Caddyfile` has a commented-out
rate-limit block you can enable after building a custom Caddy image with
the `caddy-ratelimit` plugin.

**Q: Why 422 instead of 400 when I forget the `X-API-Key` header?**
Because FastAPI's Pydantic validation runs before your route code — a
missing required header fails validation (`422`), whereas a present-but-
wrong key falls through to the handler's explicit `401` check. Think of
it as "422 = your request was malformed" vs "401 = your request was
well-formed but I don't know who you are".
