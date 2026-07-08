import time
import uuid

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# CHANGE THESE TWO VALUES
# ---------------------------------------------------------------------------
EMAIL = "24f3003125@ds.study.iitm.ac.in"   # <-- your exact logged-in email
ALLOWED_ORIGIN = "https://dash-dw26jb.example.com"    # <-- your assigned origin
# ---------------------------------------------------------------------------

app = FastAPI()

# INNER middleware (added first -> sits closest to the app).
# Starlette's CORSMiddleware handles the OPTIONS preflight itself and only
# echoes the Access-Control-Allow-Origin header when the Origin exactly
# matches ALLOWED_ORIGIN. No wildcard is ever emitted.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


# OUTER middleware (added second -> wraps CORS). Because it is outermost it
# runs on EVERY response, including the CORS preflight response, so both
# headers are always present.
@app.middleware("http")
async def add_required_headers(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Process-Time"] = f"{elapsed:.6f}"
    return response


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
