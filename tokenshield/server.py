import hashlib
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from .compression import estimate_tokens, optimize_messages
from .config import settings
from .storage import Store

store = Store(settings.database_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="TokenShield", version="0.1.0", lifespan=lifespan)


def _cost(model: str | None, input_tokens: int, output_tokens: int = 0) -> float:
    # Conservative configurable placeholder; provider-specific pricing is a follow-up module.
    return (input_tokens + output_tokens) * 0.00001


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/metrics/summary")
async def metrics_summary():
    return store.summary()


@app.get("/sources/{source_id}")
async def source(source_id: str):
    content = store.get_source(source_id)
    if content is None:
        raise HTTPException(404, "source not found")
    return {"source_id": source_id, "content": content}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    started = time.perf_counter()
    body = await request.json()
    request_id = "req_" + uuid.uuid4().hex
    original_messages = body.get("messages", [])
    original_tokens = estimate_tokens(original_messages)
    optimized_messages, compressed_items = optimize_messages(
        original_messages, store, settings.compression_enabled, settings.compression_min_chars
    )
    outgoing = dict(body)
    outgoing["messages"] = optimized_messages
    optimized_tokens = estimate_tokens(optimized_messages)
    headers = {"content-type": "application/json"}
    if settings.upstream_api_key:
        headers["authorization"] = f"Bearer {settings.upstream_api_key}"
    upstream_url = settings.upstream_base_url.rstrip("/") + "/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(upstream_url, json=outgoing, headers=headers)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        # In production this becomes a bounded retry/fallback policy.
        raise HTTPException(502, f"upstream request failed: {exc}") from exc
    usage = payload.get("usage", {})
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
    model = body.get("model")
    event = {
        "request_id": request_id, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": model, "provider": settings.upstream_base_url,
        "session_hash": hashlib.sha256(request.headers.get("x-session-id", "").encode()).hexdigest()[:16],
        "original_tokens": original_tokens, "optimized_tokens": optimized_tokens,
        "output_tokens": output_tokens, "original_cost": _cost(model, original_tokens, output_tokens),
        "optimized_cost": _cost(model, optimized_tokens, output_tokens),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "cache_hit": 0, "fallback": 0, "compressed_items": compressed_items, "task_success": None,
    }
    store.save_event(event)
    return JSONResponse(payload, headers={
        "x-tokenshield-request-id": request_id,
        "x-tokenshield-original-tokens": str(original_tokens),
        "x-tokenshield-optimized-tokens": str(optimized_tokens),
    })
