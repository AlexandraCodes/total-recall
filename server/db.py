"""SQLite helpers. A new connection per call (the app is multi-threaded)."""
import contextlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile(
  id INTEGER PRIMARY KEY CHECK(id=1), handle TEXT, platform TEXT, niche TEXT, followers INTEGER, engagement REAL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, brand TEXT, product TEXT, model TEXT, url TEXT, image_url TEXT, retailer TEXT,
  mode TEXT NOT NULL DEFAULT 'review' CHECK(mode IN ('review','sponsored')),
  posts_count INTEGER NOT NULL DEFAULT 0, phase TEXT NOT NULL DEFAULT 'queued',
  error TEXT, last_alerted_rank INTEGER NOT NULL DEFAULT 0, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS checks(
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE, verdict TEXT, result_json TEXT, checked_at TEXT);
CREATE TABLE IF NOT EXISTS link_posts(
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE, label TEXT, url TEXT, posted_on TEXT, link_removed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE, verdict TEXT, headline TEXT,
  follow_up_json TEXT, follow_up_status TEXT NOT NULL DEFAULT 'generating', created_at TEXT, handled_at TEXT);
CREATE TABLE IF NOT EXISTS drafts(
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE, kind TEXT, content_json TEXT,
  status TEXT NOT NULL DEFAULT 'done', created_at TEXT);
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, value_json TEXT, created_at TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextlib.contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    raw = sqlite3.connect(config.DB_PATH)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.close()
    with conn() as c:
        c.executescript(SCHEMA)


def all(sql, args=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    with conn() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def run(sql, args=()):
    with conn() as c:
        return c.execute(sql, args).lastrowid


def cache_get(key, max_age_hours):
    row = one("SELECT value_json, created_at FROM cache WHERE key=?", (key,))
    if not row:
        return None
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])
    except ValueError:
        return None
    if age > timedelta(hours=max_age_hours):
        return None
    return json.loads(row["value_json"])


def cache_set(key, value):
    run("INSERT OR REPLACE INTO cache(key, value_json, created_at) VALUES(?,?,?)", (key, json.dumps(value), now()))
