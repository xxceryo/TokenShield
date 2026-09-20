import hashlib
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .compression import optimize_messages
from .config import settings
from .metering import TokenMeter
from .schemas import validate_chat_request
from .storage import Store

store = Store(settings.database_url)
meter = TokenMeter(settings.pricing_json)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="TokenShield", version="0.1.0", lifespan=lifespan)


def _event(request: Request, request_id: str, started: float, model: str | None,
           original_tokens: int, optimized_tokens: int, output_tokens: int,
           compressed_items: int):
    return {
        "request_id": request_id, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": model, "provider": settings.upstream_base_url,
        "session_hash": hashlib.sha256(request.headers.get("x-session-id", "").encode()).hexdigest()[:16],
        "original_tokens": original_tokens, "optimized_tokens": optimized_tokens,
        "output_tokens": output_tokens, "original_cost": meter.cost(model, original_tokens, output_tokens),
        "optimized_cost": meter.cost(model, optimized_tokens, output_tokens),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "cache_hit": 0, "fallback": 0, "compressed_items": compressed_items, "task_success": None,
    }


def _response_headers(request_id: str, original_tokens: int, optimized_tokens: int):
    return {
        "x-tokenshield-request-id": request_id,
        "x-tokenshield-original-tokens": str(original_tokens),
        "x-tokenshield-optimized-tokens": str(optimized_tokens),
    }


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
    try:
        body = validate_chat_request(await request.json())
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    request_id = "req_" + uuid.uuid4().hex
    original_messages = body.get("messages", [])
    original_tokens = meter.count(original_messages, body.get("model"))
    optimized_messages, compressed_items = optimize_messages(
        original_messages, store, settings.compression_enabled, settings.compression_min_chars
    )
    outgoing = dict(body)
    outgoing["messages"] = optimized_messages
    optimized_tokens = meter.count(optimized_messages, body.get("model"))
    headers = {"content-type": "application/json"}
    if settings.upstream_api_key:
        headers["authorization"] = f"Bearer {settings.upstream_api_key}"
    upstream_url = settings.upstream_base_url.rstrip("/") + "/v1/chat/completions"
    if body.get("stream"):
        client = httpx.AsyncClient(timeout=120)
        try:
            upstream_request = client.build_request("POST", upstream_url, json=outgoing, headers=headers)
            upstream = await client.send(upstream_request, stream=True)
            if upstream.status_code >= 400:
                detail = (await upstream.aread())[:2000].decode(errors="replace")
                await upstream.aclose()
                await client.aclose()
                raise HTTPException(502, f"upstream returned HTTP {upstream.status_code}: {detail}")
        except httpx.RequestError as exc:
            await client.aclose()
            raise HTTPException(502, f"upstream connection failed: {exc}") from exc

        async def body_iterator():
            chunks: list[bytes] = []
            try:
                async for chunk in upstream.aiter_bytes():
                    chunks.append(chunk)
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()
                output_tokens = meter.count(b"".join(chunks).decode(errors="replace"), body.get("model"))
                store.save_event(_event(request, request_id, started, body.get("model"),
                                        original_tokens, optimized_tokens, output_tokens, compressed_items))

        return StreamingResponse(body_iterator(), status_code=upstream.status_code,
                                 media_type=upstream.headers.get("content-type", "text/event-stream"),
                                 headers=_response_headers(request_id, original_tokens, optimized_tokens))

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(upstream_url, json=outgoing, headers=headers)
        if response.status_code >= 400:
            detail = response.text[:2000]
            raise HTTPException(502, f"upstream returned HTTP {response.status_code}: {detail}")
        payload = response.json()
    except httpx.RequestError as exc:
        raise HTTPException(502, f"upstream connection failed: {exc}") from exc
    usage = payload.get("usage", {})
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
    model = body.get("model")
    store.save_event(_event(request, request_id, started, model, original_tokens,
                            optimized_tokens, output_tokens, compressed_items))
    return JSONResponse(payload, headers={
        "x-tokenshield-request-id": request_id,
        "x-tokenshield-original-tokens": str(original_tokens),
        "x-tokenshield-optimized-tokens": str(optimized_tokens),
    })
