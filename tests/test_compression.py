from tokenshield.compression import estimate_tokens, optimize_messages
from tokenshield.storage import Store


def test_long_log_is_compressed_and_recoverable(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/test.db")
    text = "\n".join(["INFO running"] * 300 + ["ERROR assertion failed at line 42"])
    result, changed = optimize_messages([{"role": "tool", "content": text}], store, True, 100)
    assert changed == 1
    assert estimate_tokens(result) < estimate_tokens([{"role": "tool", "content": text}])
    source_id = result[0]["metadata"]["tokenshield_source_id"]
    assert store.get_source(source_id) == text
