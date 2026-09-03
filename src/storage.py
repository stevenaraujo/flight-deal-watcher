"""
Storage-Layer auf Basis von SQLite.

WICHTIG: GitHub-Actions-Runner sind nicht persistent. Die DB-Datei
(config.DB_PATH) muss daher am Ende jedes Workflow-Runs zurück ins
Repository committet werden (siehe .github/workflows/watcher.yml).
SQLite ist dafür bewusst gewählt: eine einzelne Datei, kein Server,
kostenlos, robust, einfach zu versionieren.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Iterator, List, Optional, Sequence

from . import config
from .deal_engine import DealAssessment
from .models import FlightOffer

logger = logging.getLogger("flight_watcher.storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    price_per_person REAL NOT NULL,
    price_total REAL NOT NULL,
    outbound_date TEXT NOT NULL,
    return_date TEXT NOT NULL,
    airline TEXT,
    flight_number TEXT,
    departure_time TEXT,
    arrival_time TEXT,
    duration_minutes INTEGER,
    stops INTEGER,
    layover_minutes INTEGER,
    travel_class TEXT,
    baggage_included INTEGER,
    baggage_verified INTEGER,
    data_source TEXT,
    booking_link TEXT,
    unique_key TEXT NOT NULL,
    deal_tier TEXT,
    is_all_time_low INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_obs_combo ON price_observations(outbound_date, return_date);
CREATE INDEX IF NOT EXISTS idx_obs_key ON price_observations(unique_key);
CREATE INDEX IF NOT EXISTS idx_obs_checked_at ON price_observations(checked_at);

CREATE TABLE IF NOT EXISTS notified_deals (
    unique_key TEXT PRIMARY KEY,
    first_notified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    combinations_checked INTEGER DEFAULT 0,
    offers_found INTEGER DEFAULT 0,
    api_calls_used INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS rotation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_combo_index INTEGER NOT NULL DEFAULT 0
);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    try:
        with get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO rotation_state (id, next_combo_index) VALUES (1, 0)"
            )
    except sqlite3.DatabaseError as exc:
        logger.error("Datenbank beschädigt oder nicht lesbar: %s", exc)
        raise


def save_observation(offer: FlightOffer, assessment: DealAssessment) -> None:
    leg = offer.outbound_legs[0] if offer.outbound_legs else None
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO price_observations (
                checked_at, price_per_person, price_total, outbound_date, return_date,
                airline, flight_number, departure_time, arrival_time, duration_minutes,
                stops, layover_minutes, travel_class, baggage_included, baggage_verified,
                data_source, booking_link, unique_key, deal_tier, is_all_time_low
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                offer.checked_at.isoformat(),
                offer.price_per_person,
                offer.price_total,
                offer.outbound_date.isoformat(),
                offer.return_date.isoformat(),
                offer.airline_primary,
                leg.flight_number if leg else "",
                leg.departure_time.isoformat() if leg else None,
                leg.arrival_time.isoformat() if leg else None,
                offer.outbound_duration_minutes + offer.return_duration_minutes,
                offer.outbound_stops + offer.return_stops,
                sum(offer.outbound_layovers_minutes),
                offer.travel_class,
                offer.baggage.checked_bags_included,
                int(offer.baggage.verified),
                offer.data_source,
                offer.booking_link,
                offer.unique_key(),
                assessment.tier_label,
                int(assessment.is_all_time_low),
            ),
        )


def get_historical_low() -> Optional[float]:
    with get_connection() as conn:
        row = conn.execute("SELECT MIN(price_per_person) AS lo FROM price_observations").fetchone()
        return row["lo"] if row and row["lo"] is not None else None


def get_all_time_low_details() -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """SELECT * FROM price_observations
               ORDER BY price_per_person ASC, checked_at ASC LIMIT 1"""
        ).fetchone()


def get_previous_price_for_combo(outbound_date: date, return_date: date) -> Optional[float]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT price_per_person FROM price_observations
               WHERE outbound_date = ? AND return_date = ?
               ORDER BY checked_at DESC, id DESC LIMIT 1 OFFSET 1""",
            (outbound_date.isoformat(), return_date.isoformat()),
        ).fetchone()
        return row["price_per_person"] if row else None


def get_notified_keys() -> set:
    with get_connection() as conn:
        rows = conn.execute("SELECT unique_key FROM notified_deals").fetchall()
        return {r["unique_key"] for r in rows}


def mark_notified(unique_key: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO notified_deals (unique_key, first_notified_at) VALUES (?, ?)",
            (unique_key, datetime.now(timezone.utc).isoformat()),
        )


def get_top_deals(limit: int = config.TOP_DEALS_COUNT) -> List[sqlite3.Row]:
    """Neuester Preis je Kombination, dann günstigste zuerst."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT po.* FROM price_observations po
            INNER JOIN (
                SELECT outbound_date, return_date, MAX(checked_at) AS max_checked
                FROM price_observations GROUP BY outbound_date, return_date
            ) latest
            ON po.outbound_date = latest.outbound_date
               AND po.return_date = latest.return_date
               AND po.checked_at = latest.max_checked
            ORDER BY po.price_per_person ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_price_history_series(limit: int = 500) -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT checked_at, price_per_person FROM price_observations ORDER BY checked_at ASC LIMIT ?",
            (limit,),
        ).fetchall()


def get_next_combo_indices(count: int) -> List[int]:
    total = len(config.ALL_COMBINATIONS)
    with get_connection() as conn:
        row = conn.execute("SELECT next_combo_index FROM rotation_state WHERE id = 1").fetchone()
        start = row["next_combo_index"] if row else 0
    return [(start + i) % total for i in range(count)]


def advance_rotation(count: int) -> None:
    total = len(config.ALL_COMBINATIONS)
    with get_connection() as conn:
        row = conn.execute("SELECT next_combo_index FROM rotation_state WHERE id = 1").fetchone()
        start = row["next_combo_index"] if row else 0
        new_index = (start + count) % total
        conn.execute("UPDATE rotation_state SET next_combo_index = ? WHERE id = 1", (new_index,))


def start_run() -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO run_log (started_at, status) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(), "running"),
        )
        return cur.lastrowid


def finish_run(run_id: int, status: str, combinations_checked: int, offers_found: int,
               api_calls_used: int, error_message: Optional[str] = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE run_log SET finished_at=?, status=?, combinations_checked=?,
               offers_found=?, api_calls_used=?, error_message=? WHERE id=?""",
            (
                datetime.now(timezone.utc).isoformat(), status, combinations_checked,
                offers_found, api_calls_used, error_message, run_id,
            ),
        )


def get_recent_runs(limit: int = 10) -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM run_log ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()


def get_consecutive_failed_runs() -> int:
    """Zählt fehlgeschlagene Runs am Stück (für Alarmierung bei wiederholtem Ausfall)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status FROM run_log ORDER BY started_at DESC LIMIT 10"
        ).fetchall()
    count = 0
    for r in rows:
        if r["status"] == "failed":
            count += 1
        else:
            break
    return count
