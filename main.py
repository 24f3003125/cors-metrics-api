import time
import uuid
from typing import List

import jwt
from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
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
    origin = request.headers.get("origin")
    path = request.url.path
    start = time.perf_counter()

    if request.method == "OPTIONS":
        # CORS preflight -- answer here
        resp = Response(status_code=204)
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = (
            request.headers.get("access-control-request-headers") or "*"
        )
    else:
        resp = await call_next(request)

    acao = _acao_for(path, origin)
    if acao:
        resp.headers["Access-Control-Allow-Origin"] = acao
    resp.headers["Vary"] = "Origin"

    elapsed = time.perf_counter() - start
    resp.headers["X-Request-ID"] = str(uuid.uuid4())
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
