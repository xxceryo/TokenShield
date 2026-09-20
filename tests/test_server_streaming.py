from typing import ClassVar

import pytest
from httpx import ASGITransport, AsyncClient

from tokenshield import server
from tokenshield.storage import Store


class FakeUpstreamResponse:
    status_code = 200
    headers: ClassVar = {"content-type": "text/event-stream"}

    async def aiter_bytes(self):
        yield b"data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\n"
        yield b"data: [DONE]\n\n"

    async def aclose(self):
        return None


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    def build_request(self, *args, **kwargs):
        return object()

    async def send(self, *args, **kwargs):
        return FakeUpstreamResponse()

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_streaming_proxy_preserves_chunks_and_records_event(monkeypatch, tmp_path):
    monkeypatch.setattr(server.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(server, "store", Store(f"sqlite:///{tmp_path}/events.db"))
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json={
            "model": "test-model",
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
        })
    assert response.status_code == 200
    assert "data: [DONE]" in response.text
    assert int(response.headers["x-tokenshield-original-tokens"]) > 0
    assert server.store.summary()["n"] == 1
