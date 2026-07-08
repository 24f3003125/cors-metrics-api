import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import List

import jwt
from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Q1 VALUES
# ---------------------------------------------------------------------------
EMAIL = "24f3003125@ds.study.iitm.ac.in"            # your exact logged-in email
ALLOWED_ORIGIN = "https://dash-dw26jb.example.com"  # your assigned origin (Q1)

# ---------------------------------------------------------------------------
# Q2 VALUES  --  COPY DIRECTLY FROM THE ASSIGNMENT PAGE
# ---------------------------------------------------------------------------
ISSUER = "https://idp.exam.local"
AUDIENCE = "tds-3hypqblt.apps.exam.local"

PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2okOHspNjgA+2rTLbeuY
cxiP/hG8C6Sb9iwg3yiLAA4HCnpITcbWCSelbvbYGuc3EbNy4xFyf5Cbj5DHJMID
EkryOgyd2giIIIBOUBj8S63uGcnRpOBh9NFatfNwheKuzsPuVNldu6A9cNteNpXc
WyJjG2axVfmq7i6SuKr1JoWYG7xTTAvKPujSl4OtsQfO3h5NepzdfXpr28oNnzfW
ed+zclR6BcmNNo/WVfJ4xyCLSf0BCOgdTgW6PdaChd1l9VDetJZVEgC5tkyvXsfI
SI6iyrYbKR0NEBSqq4XkadEjsCs4F1RncsS4LlgniT7GlkL9Mce3b0wGLs9/7ZIX
dQIDAQAB
-----END PUBLIC KEY-----"""

# ---------------------------------------------------------------------------
# Q3 CONFIG LAYERS (low -> high precedence)
# ---------------------------------------------------------------------------
DEFAULTS = {                       # layer 1: hardcoded defaults (already typed)
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}
YAML_LAYER = {"workers": 16}       # layer 2: config.development.yaml
ENV_FILE = {"NUM_WORKERS": "11"}   # layer 3: .env  (NUM_WORKERS is an alias)
OS_ENV = {                         # layer 4: OS env vars (APP_* prefix)
    "APP_PORT": "8904",
    "APP_LOG_LEVEL": "warning",
}
ALIAS = {"NUM_WORKERS": "workers"}  # .env alias mapping
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Q6 OBSERVABILITY STATE
# ---------------------------------------------------------------------------
START_TIME = time.time()          # for uptime_s
REQUEST_COUNT = 0                 # live Prometheus counter
LOGS = deque(maxlen=500)          # in-memory structured log buffer
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Q9 API-ENGINEERING STATE
# ---------------------------------------------------------------------------
T_ORDERS = 40                     # total orders in the fixed catalog (IDs 1..T)
RATE_LIMIT = 15                   # R requests
RATE_WINDOW = 10.0                # per 10 seconds
IDEMPOTENT = {}                   # Idempotency-Key -> order
RATE = {}                         # client_id -> deque[timestamps]
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Q10 MIDDLEWARE-STACK STATE
# ---------------------------------------------------------------------------
B_PING = 11                       # /ping bucket size per 10s
RATE_PING = {}                    # client_id -> deque[timestamps] for /ping
# ---------------------------------------------------------------------------

app = FastAPI()


def _acao_for(path: str, origin):
    """Which Access-Control-Allow-Origin to send for a given path."""
    if origin is None:
        return None
    if path.startswith("/stats"):
        # Q1: strict -- only the assigned origin, no wildcard
        return origin if origin == ALLOWED_ORIGIN else None
    # Q3 (/effective-config) and everything else: reflect any origin
    return origin


@app.middleware("http")
async def cors_and_headers(request: Request, call_next):
    global REQUEST_COUNT
    origin = request.headers.get("origin")
    path = request.url.path
    # Q10 request context: reuse inbound X-Request-ID, else fresh UUID4
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()

    # Q6: count every request to any endpoint (live counter)
    REQUEST_COUNT += 1
    # Q6: structured JSON log entry for every request
    LOGS.append({
        "level": "info",
        "ts": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "request_id": request_id,
    })

    if request.method == "OPTIONS":
        # CORS preflight -- answer here
        resp = Response(status_code=204)
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = (
            request.headers.get("access-control-request-headers") or "*"
        )
    else:
        # per-client rate limit (only when X-Client-Id present)
        #   /orders -> R=15 (Q9),  /ping -> B=11 (Q10)
        limited = None
        rule = None
        if path.startswith("/orders"):
            rule = (RATE_LIMIT, RATE)
        elif path.startswith("/ping"):
            rule = (B_PING, RATE_PING)
        if rule:
            cap, store = rule
            cid = request.headers.get("x-client-id")
            if cid:
                now = time.time()
                dq = store.setdefault(cid, deque())
                while dq and now - dq[0] >= RATE_WINDOW:
                    dq.popleft()
                if len(dq) >= cap:
                    retry = max(1, int(RATE_WINDOW - (now - dq[0])) + 1)
                    limited = JSONResponse(
                        status_code=429, content={"detail": "rate limit exceeded"}
                    )
                    limited.headers["Retry-After"] = str(retry)
                else:
                    dq.append(now)
        resp = limited if limited is not None else await call_next(request)

    acao = _acao_for(path, origin)
    if acao:
        resp.headers["Access-Control-Allow-Origin"] = acao
    resp.headers["Vary"] = "Origin"
    # let cross-origin JS actually read these response headers
    resp.headers["Access-Control-Expose-Headers"] = (
        "Retry-After, X-Request-ID, X-Process-Time"
    )

    elapsed = time.perf_counter() - start
    resp.headers["X-Request-ID"] = request_id
    resp.headers["X-Process-Time"] = f"{elapsed:.6f}"
    return resp


# --------------------------- Q1: /stats ------------------------------------
@app.get("/stats")
async def stats(values: str = Query(...)):
    nums = [int(v) for v in values.split(",") if v.strip() != ""]
    return {
        "email": EMAIL,
        "count": len(nums),
        "sum": sum(nums),
        "min": min(nums),
        "max": max(nums),
        "mean": sum(nums) / len(nums),
    }


# --------------------------- Q2: /verify -----------------------------------
class TokenIn(BaseModel):
    token: str


@app.post("/verify")
async def verify(body: TokenIn):
    try:
        claims = jwt.decode(
            body.token,
            PUBLIC_KEY,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
        )
        return {
            "valid": True,
            "email": claims.get("email"),
            "sub": claims.get("sub"),
            "aud": claims.get("aud"),
        }
    except jwt.PyJWTError:
        return JSONResponse(status_code=401, content={"valid": False})


# --------------------------- Q3: /effective-config -------------------------
def _coerce(key, value):
    if key in ("port", "workers"):
        return int(value)
    if key == "debug":
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


@app.get("/effective-config")
async def effective_config(overrides: List[str] = Query(default=[], alias="set")):
    merged = {}

    # layer 1: defaults
    merged.update(DEFAULTS)

    # layer 2: yaml
    for k, v in YAML_LAYER.items():
        merged[k] = v

    # layer 3: .env (apply alias)
    for k, v in ENV_FILE.items():
        merged[ALIAS.get(k, k)] = v

    # layer 4: OS env vars with APP_ prefix
    for k, v in OS_ENV.items():
        if k.startswith("APP_"):
            merged[k[4:].lower()] = v

    # highest precedence: CLI overrides ?set=key=value
    for item in overrides:
        if "=" in item:
            k, v = item.split("=", 1)
            merged[k.strip()] = v

    # coerce types
    result = {k: _coerce(k, v) for k, v in merged.items()}

    # secret masking -- api_key never exposed
    if "api_key" in result:
        result["api_key"] = "****"

    return result


# --------------------------- Q5: /analytics --------------------------------
API_KEY = "ak_jq620l7dz0acj29gan0uwbki"   # your assigned X-API-Key value


@app.post("/analytics")
async def analytics(request: Request):
    # Auth: X-API-Key header must match, else 401
    if request.headers.get("x-api-key") != API_KEY:
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    payload = await request.json()
    events = payload.get("events", [])

    total_events = len(events)
    unique_users = len({e.get("user") for e in events})

    revenue = 0.0
    totals = {}
    for e in events:
        amt = e.get("amount", 0)
        if amt > 0:
            revenue += amt
            user = e.get("user")
            totals[user] = totals.get(user, 0) + amt

    top_user = max(totals, key=totals.get) if totals else None

    return {
        "email": EMAIL,
        "total_events": total_events,
        "unique_users": unique_users,
        "revenue": revenue,
        "top_user": top_user,
    }


# --------------------------- Q6: observability -----------------------------
@app.get("/work")
async def work(n: int = Query(1)):
    total = 0
    for i in range(max(n, 0)):     # do K units of "work"
        total += i
    return {"email": EMAIL, "done": n}


@app.get("/metrics")
async def metrics():
    text = (
        "# HELP http_requests_total Total HTTP requests\n"
        "# TYPE http_requests_total counter\n"
        f"http_requests_total {REQUEST_COUNT}\n"
    )
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "uptime_s": time.time() - START_TIME}


@app.get("/logs/tail")
async def logs_tail(limit: int = Query(100)):
    items = list(LOGS)
    if limit > 0:
        items = items[-limit:]
    return items


# --------------------------- Q9: orders API --------------------------------
@app.post("/orders")
async def create_order(request: Request):
    key = request.headers.get("idempotency-key")
    if key and key in IDEMPOTENT:
        # repeat call with same key -> same order id, no duplicate
        return JSONResponse(status_code=200, content=IDEMPOTENT[key])
    order = {"id": str(uuid.uuid4()), "status": "created"}
    if key:
        IDEMPOTENT[key] = order
    return JSONResponse(status_code=201, content=order)


@app.get("/orders")
async def list_orders(limit: int = Query(10), cursor: str = Query("")):
    if limit < 1:
        limit = 1
    try:
        start = int(cursor) if cursor else 1
    except ValueError:
        start = 1
    if start < 1:
        start = 1

    end = min(start + limit - 1, T_ORDERS)
    items = [{"id": i} for i in range(start, end + 1)]
    next_cursor = str(end + 1) if end < T_ORDERS else None
    return {"items": items, "next_cursor": next_cursor}


# --------------------------- Q10: /ping ------------------------------------
@app.get("/ping")
async def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}
