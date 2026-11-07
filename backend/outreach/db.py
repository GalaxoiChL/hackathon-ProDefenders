"""SQLite storage (stdlib only). Lives in output/outreach.db, which is git-ignored."""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY, market TEXT, city TEXT, category TEXT, clip TEXT, query TEXT,
    status TEXT, error TEXT, created REAL, finished REAL, log TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY, campaign_id INTEGER, market TEXT, city TEXT, name TEXT, category TEXT,
    website TEXT, email TEXT, email_source TEXT, phone TEXT, address TEXT, source TEXT, source_id TEXT,
    description TEXT, fit_score INTEGER, fit_reason TEXT, ai TEXT, created REAL,
    UNIQUE(campaign_id, source, source_id));
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY, campaign_id INTEGER, lead_id INTEGER, to_addr TEXT, subject TEXT,
    body TEXT, language TEXT, ai TEXT, status TEXT, error TEXT, created REAL, sent REAL, outbox_path TEXT);
CREATE TABLE IF NOT EXISTS suppression (email TEXT PRIMARY KEY, reason TEXT, created REAL);
CREATE TABLE IF NOT EXISTS bids (
    id INTEGER PRIMARY KEY, placement TEXT, clip TEXT, market TEXT, lead_id INTEGER, company TEXT,
    contact_email TEXT, amount_usd REAL, message TEXT, created REAL);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    # ---- low level ----
    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid

    def all(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, row: dict) -> int:
        """New row id, or 0 if a UNIQUE constraint made it a duplicate (lastrowid would be stale)."""
        cols = ",".join(row)
        marks = ",".join("?" for _ in row)
        with self._lock:
            cur = self._conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({marks})",
                                     tuple(row.values()))
            self._conn.commit()
            return cur.lastrowid if cur.rowcount == 1 else 0

    def update(self, table: str, row_id: int, **fields) -> None:
        sets = ",".join(f"{k}=?" for k in fields)
        self.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*fields.values(), row_id))

    # ---- helpers ----
    def secret(self, configured: str = "") -> str:
        if configured:
            return configured
        row = self.one("SELECT value FROM meta WHERE key='secret_key'")
        if row:
            return row["value"]
        key = secrets.token_hex(32)
        self.execute("INSERT INTO meta (key, value) VALUES ('secret_key', ?)", (key,))
        return key

    def log(self, campaign_id: int, line: str) -> None:
        row = self.one("SELECT log FROM campaigns WHERE id=?", (campaign_id,))
        lines = json.loads(row["log"]) if row else []
        lines = (lines + [f"{time.strftime('%H:%M:%S')} {line}"])[-200:]
        self.update("campaigns", campaign_id, log=json.dumps(lines, ensure_ascii=False))

    def suppressed(self, email: str) -> bool:
        return self.one("SELECT 1 FROM suppression WHERE email=?", (email.lower(),)) is not None

    def suppress(self, email: str, reason: str) -> None:
        self.execute("INSERT OR REPLACE INTO suppression (email, reason, created) VALUES (?,?,?)",
                     (email.lower(), reason, time.time()))

    def sent_today(self) -> int:
        start = time.time() - 24 * 3600
        return self.one("SELECT COUNT(*) n FROM emails WHERE status='sent' AND sent>=?", (start,))["n"]
