import json
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from .config import DB_PATH, REPORT_DIR


SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_items (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  published_at TEXT,
  title TEXT,
  url TEXT,
  content_text TEXT,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecasts (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  evidence_hours INTEGER NOT NULL,
  model TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  forecast_json TEXT NOT NULL,
  report_markdown TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_configs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  interval_seconds INTEGER NOT NULL,
  params_json TEXT NOT NULL,
  last_run_at TEXT,
  last_status TEXT,
  last_message TEXT,
  last_item_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runtime_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def insert_raw_items(items: Iterable[Dict[str, Any]]) -> int:
    rows = list(items)
    if not rows:
        return 0
    with connect() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO raw_items (
              id, source, fetched_at, published_at, title, url, content_text, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["source"],
                    row["fetched_at"],
                    row.get("published_at"),
                    row.get("title"),
                    row.get("url"),
                    row.get("content_text", ""),
                    json.dumps(row, ensure_ascii=False),
                )
                for row in rows
            ],
        )
        conn.commit()
    return len(rows)


def fetch_recent_items(hours: int, limit: int = 200) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT payload_json
            FROM raw_items
            WHERE COALESCE(published_at, fetched_at) >= datetime('now', ?)
            ORDER BY COALESCE(published_at, fetched_at) DESC
            LIMIT ?
            """,
            (f"-{hours} hours", limit),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def insert_forecast(
    forecast_id: str,
    created_at: str,
    evidence_hours: int,
    model: str,
    summary: Dict[str, Any],
    forecast: Dict[str, Any],
    report_markdown: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO forecasts (
              id, created_at, evidence_hours, model, summary_json, forecast_json, report_markdown
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                forecast_id,
                created_at,
                evidence_hours,
                model,
                json.dumps(summary, ensure_ascii=False, indent=2),
                json.dumps(forecast, ensure_ascii=False, indent=2),
                report_markdown,
            ),
        )
        conn.commit()


def list_forecasts(limit: int = 20) -> List[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, created_at, evidence_hours, model
            FROM forecasts
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_forecast(forecast_id: Optional[str] = None):
    with connect() as conn:
        if forecast_id:
            row = conn.execute(
                "SELECT * FROM forecasts WHERE id = ?",
                (forecast_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM forecasts ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
    return row


def upsert_source_configs(configs: Iterable[Dict[str, Any]]) -> None:
    rows = list(configs)
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO source_configs (
              id, name, kind, enabled, interval_seconds, params_json,
              last_run_at, last_status, last_message, last_item_count
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0)
            ON CONFLICT(id) DO UPDATE SET
              name = excluded.name,
              kind = excluded.kind,
              params_json = excluded.params_json
            """,
            [
                (
                    row["id"],
                    row["name"],
                    row["kind"],
                    int(bool(row.get("enabled", True))),
                    int(row["interval_seconds"]),
                    json.dumps(row.get("params", {}), ensure_ascii=False),
                )
                for row in rows
            ],
        )
        conn.commit()


def prune_source_configs(valid_ids: Iterable[str]) -> None:
    ids = sorted(set(valid_ids))
    with connect() as conn:
        if not ids:
            conn.execute("DELETE FROM source_configs")
        else:
            placeholders = ", ".join("?" for _ in ids)
            conn.execute(
                f"DELETE FROM source_configs WHERE id NOT IN ({placeholders})",
                ids,
            )
        conn.commit()


def list_source_configs() -> List[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM source_configs
            ORDER BY kind, name
            """
        ).fetchall()


def get_source_config(source_id: str):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM source_configs WHERE id = ?",
            (source_id,),
        ).fetchone()


def update_source_config(source_id: str, enabled: bool, interval_seconds: int) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE source_configs
            SET enabled = ?, interval_seconds = ?
            WHERE id = ?
            """,
            (int(enabled), int(interval_seconds), source_id),
        )
        conn.commit()


def update_source_runtime(
    source_id: str,
    last_run_at: str,
    last_status: str,
    last_message: str,
    last_item_count: int,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE source_configs
            SET last_run_at = ?, last_status = ?, last_message = ?, last_item_count = ?
            WHERE id = ?
            """,
            (last_run_at, last_status, last_message, int(last_item_count), source_id),
        )
        conn.commit()


def set_runtime_setting(key: str, value: Any) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO runtime_settings (key, value_json)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
            """,
            (key, json.dumps(value, ensure_ascii=False)),
        )
        conn.commit()


def get_runtime_setting(key: str, default: Any = None) -> Any:
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM runtime_settings WHERE key = ?",
            (key,),
        ).fetchone()
    if not row:
        return default
    return json.loads(row["value_json"])


def list_runtime_settings() -> Dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value_json FROM runtime_settings ORDER BY key"
        ).fetchall()
    return {row["key"]: json.loads(row["value_json"]) for row in rows}
