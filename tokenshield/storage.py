import hashlib
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from .schemas import EventRecord


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, database_url: str):
        path = database_url.removeprefix("sqlite:///")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            c.executescript("""
            CREATE TABLE IF NOT EXISTS events (
              request_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
              model TEXT, provider TEXT, session_hash TEXT,
              pricing_status TEXT NOT NULL DEFAULT 'missing',
              original_tokens INTEGER NOT NULL, optimized_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL DEFAULT 0, original_cost REAL NOT NULL DEFAULT 0,
              optimized_cost REAL NOT NULL DEFAULT 0, latency_ms REAL,
              cache_hit INTEGER NOT NULL DEFAULT 0, fallback INTEGER NOT NULL DEFAULT 0,
              compressed_items INTEGER NOT NULL DEFAULT 0, task_success INTEGER
            );
            CREATE TABLE IF NOT EXISTS sources (
              source_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
              content_hash TEXT NOT NULL, content TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
            """)
            version = c.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
            current_version = int(version[0]) if version else 0
            if current_version < 2:
                columns = {row[1] for row in c.execute("PRAGMA table_info(events)")}
                if "pricing_status" not in columns:
                    c.execute("ALTER TABLE events ADD COLUMN pricing_status TEXT NOT NULL DEFAULT 'missing'")
                c.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '2')")

    def save_source(self, content: str) -> str:
        source_id = "src_" + hashlib.sha256((content + _now()).encode()).hexdigest()[:20]
        with self.lock, self._connect() as c:
            c.execute("INSERT INTO sources VALUES (?, ?, ?, ?)",
                      (source_id, _now(), hashlib.sha256(content.encode()).hexdigest(), content))
        return source_id

    def get_source(self, source_id: str) -> str | None:
        with self._connect() as c:
            row = c.execute("SELECT content FROM sources WHERE source_id=?", (source_id,)).fetchone()
        return row[0] if row else None

    def save_event(self, event: dict | EventRecord):
        event = (event.model_dump() if isinstance(event, EventRecord)
                 else EventRecord.model_validate(event).model_dump())
        fields = ["request_id", "created_at", "model", "provider", "session_hash", "pricing_status",
                  "original_tokens", "optimized_tokens", "output_tokens", "original_cost",
                  "optimized_cost", "latency_ms", "cache_hit", "fallback", "compressed_items", "task_success"]
        values = [event.get(k) for k in fields]
        with self.lock, self._connect() as c:
            c.execute(f"INSERT OR REPLACE INTO events ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", values)

    def schema_version(self) -> int:
        with self._connect() as c:
            row = c.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        return int(row[0]) if row else 0

    def summary(self) -> dict:
        with self._connect() as c:
            row = c.execute("""SELECT COUNT(*) n, COALESCE(SUM(original_tokens),0) original_tokens,
                COALESCE(SUM(optimized_tokens),0) optimized_tokens,
                COALESCE(SUM(original_cost),0) original_cost,
                COALESCE(SUM(optimized_cost),0) optimized_cost,
                COALESCE(SUM(cache_hit),0) cache_hits, COALESCE(SUM(fallback),0) fallbacks,
                COALESCE(SUM(CASE WHEN pricing_status='missing' THEN 1 ELSE 0 END),0) pricing_missing
                FROM events""").fetchone()
        d = dict(row)
        d["token_reduction_rate"] = round(1 - d["optimized_tokens"] / d["original_tokens"], 4) if d["original_tokens"] else 0
        d["cost_reduction_rate"] = round(1 - d["optimized_cost"] / d["original_cost"], 4) if d["original_cost"] else 0
        return d
