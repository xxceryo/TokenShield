import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            c.executescript("""
            CREATE TABLE IF NOT EXISTS events (
              request_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
              model TEXT, provider TEXT, session_hash TEXT,
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

    def save_event(self, event: dict):
        fields = ["request_id", "created_at", "model", "provider", "session_hash",
                  "original_tokens", "optimized_tokens", "output_tokens", "original_cost",
                  "optimized_cost", "latency_ms", "cache_hit", "fallback", "compressed_items", "task_success"]
        values = [event.get(k) for k in fields]
        with self.lock, self._connect() as c:
            c.execute(f"INSERT OR REPLACE INTO events ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", values)

    def summary(self) -> dict:
        with self._connect() as c:
            row = c.execute("""SELECT COUNT(*) n, COALESCE(SUM(original_tokens),0) original_tokens,
                COALESCE(SUM(optimized_tokens),0) optimized_tokens,
                COALESCE(SUM(original_cost),0) original_cost,
                COALESCE(SUM(optimized_cost),0) optimized_cost,
                COALESCE(SUM(cache_hit),0) cache_hits, COALESCE(SUM(fallback),0) fallbacks
                FROM events""").fetchone()
        d = dict(row)
        d["token_reduction_rate"] = round(1 - d["optimized_tokens"] / d["original_tokens"], 4) if d["original_tokens"] else 0
        d["cost_reduction_rate"] = round(1 - d["optimized_cost"] / d["original_cost"], 4) if d["original_cost"] else 0
        return d
