import pytest

from tokenshield.schemas import EventRecord, validate_chat_request
from tokenshield.storage import Store


def test_chat_request_validation_rejects_missing_messages():
    with pytest.raises(ValueError, match="messages"):
        validate_chat_request({"model": "x"})


def test_event_schema_and_database_version(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/events.db")
    assert store.schema_version() == 2
    store.save_event(EventRecord(
        request_id="req-1", created_at="now", provider="test",
        original_tokens=10, optimized_tokens=8,
    ))
    assert store.summary()["n"] == 1
