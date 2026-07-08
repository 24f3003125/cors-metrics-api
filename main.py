import time
import uuid

import jwt
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Q1 VALUES
# ---------------------------------------------------------------------------
EMAIL = "24f3003125@ds.study.iitm.ac.in"          # <-- your exact logged-in email
ALLOWED_ORIGIN = "https://dash-dw26jb.example.com"  # <-- your assigned origin

# ---------------------------------------------------------------------------
# Q2 VALUES  --  COPY THESE DIRECTLY FROM THE ASSIGNMENT PAGE (avoid typos!)
# ---------------------------------------------------------------------------
ISSUER = "https://idp.exam.local"
AUDIENCE = "tds-3hypqblt.apps.exam.local"

# Paste the RS256 public key EXACTLY as shown on the page (copy from portal,
# do not retype). Even one wrong character breaks signature verification.
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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_required_headers(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Process-Time"] = f"{elapsed:.6f}"
    return response


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
            algorithms=["RS256"],   # only RS256; blocks "alg: none" tricks
            audience=AUDIENCE,      # rejects wrong-audience tokens
            issuer=ISSUER,          # rejects wrong-issuer tokens
            # exp is verified by default (rejects expired tokens)
        )
        return {
            "valid": True,
            "email": claims.get("email"),
            "sub": claims.get("sub"),
            "aud": claims.get("aud"),
        }
    except jwt.PyJWTError:
        # bad signature / tampered / expired / wrong aud / wrong iss -> 401
        return JSONResponse(status_code=401, content={"valid": False})
