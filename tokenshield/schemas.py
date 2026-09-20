from pydantic import BaseModel, ConfigDict, Field


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str
    created_at: str
    model: str | None = None
    provider: str
    pricing_status: str = "missing"
    session_hash: str | None = None
    original_tokens: int = Field(ge=0)
    optimized_tokens: int = Field(ge=0)
    output_tokens: int = Field(default=0, ge=0)
    original_cost: float = Field(default=0, ge=0)
    optimized_cost: float = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    cache_hit: int = Field(default=0, ge=0, le=1)
    fallback: int = Field(default=0, ge=0, le=1)
    compressed_items: int = Field(default=0, ge=0)
    task_success: int | None = Field(default=None, ge=0, le=1)


def validate_chat_request(body: object) -> dict:
    if not isinstance(body, dict):
        raise TypeError("request body must be a JSON object")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise TypeError(f"messages[{index}] must be an object")
        if not isinstance(message.get("role"), str):
            raise TypeError(f"messages[{index}].role must be a string")
        if "content" not in message and "tool_calls" not in message:
            raise ValueError(f"messages[{index}] must contain content or tool_calls")
    if "model" in body and not isinstance(body["model"], str):
        raise ValueError("model must be a string")
    if "stream" in body and not isinstance(body["stream"], bool):
        raise ValueError("stream must be a boolean")
    return body
