import json
import re
from dataclasses import dataclass
from .storage import Store


@dataclass
class CompressionResult:
    content: str
    source_id: str | None
    changed: bool


def estimate_tokens(value) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return max(1, (len(text) + 3) // 4)


def compress_text(text: str, store: Store, min_chars: int) -> CompressionResult:
    if len(text) < min_chars:
        return CompressionResult(text, None, False)
    source_id = store.save_source(text)
    lines = text.splitlines()
    is_log = bool(re.search(r"(error|exception|traceback|failed|warning)", text, re.I))
    if is_log:
        selected = [line for line in lines if re.search(r"(error|exception|traceback|failed|warning|assert)", line, re.I)]
        selected = selected[:120] + (["... [middle output indexed as " + source_id + "] ..."] if len(lines) > 120 else [])
    else:
        selected = lines[:60] + (["... [output indexed as " + source_id + "] ..."] if len(lines) > 60 else [])
    compressed = "\n".join(selected)
    if len(compressed) >= len(text):
        return CompressionResult(text, None, False)
    return CompressionResult(compressed, source_id, True)


def optimize_messages(messages: list[dict], store: Store, enabled: bool, min_chars: int):
    if not enabled:
        return messages, 0
    changed = 0
    result = []
    for message in messages:
        item = dict(message)
        content = item.get("content")
        if isinstance(content, str):
            compressed = compress_text(content, store, min_chars)
            if compressed.changed:
                item["content"] = compressed.content
                item["metadata"] = {**item.get("metadata", {}), "tokenshield_source_id": compressed.source_id}
                changed += 1
        result.append(item)
    return result, changed
