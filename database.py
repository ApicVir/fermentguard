"""FermentGuard SQLite database layer for batch and measurement tracking."""

import sqlite3
from datetime import datetime, date
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import pandas as pd

DB_PATH = "fermentguard.db"


@contextmanager
def get_connection():
    """Context manager for SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database tables if they do not exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                measured_at TEXT NOT NULL,
                pH REAL,
                dissolved_oxygen REAL,
                temperature_C REAL,
                aeration_rate REAL,
                notes TEXT,
                FOREIGN KEY (batch_id) REFERENCES batches(batch_id) ON DELETE CASCADE
            )
        """)
        # Helpful indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meas_batch_time ON measurements(batch_id, measured_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status)")


def create_batch(batch_id: str, start_date: str, description: str = "") -> bool:
    """Create a new batch. Returns True on success."""
    if not batch_id or not start_date:
        return False
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO batches (batch_id, start_date, description) VALUES (?, ?, ?)",
                (batch_id.strip(), start_date, description.strip())
            )
            return True
        except sqlite3.IntegrityError:
            return False


def add_measurement(
    batch_id: str,
    measured_at: str,
    pH: Optional[float] = None,
    dissolved_oxygen: Optional[float] = None,
    temperature_C: Optional[float] = None,
    aeration_rate: Optional[float] = None,
    notes: str = ""
) -> int:
    """Insert a measurement row. Returns the new measurement id."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO measurements 
            (batch_id, measured_at, pH, dissolved_oxygen, temperature_C, aeration_rate, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, measured_at, pH, dissolved_oxygen, temperature_C, aeration_rate, notes.strip())
        )
        return cur.lastrowid


def get_all_batches(include_archived: bool = False) -> List[Dict[str, Any]]:
    """Return all batches with latest measurement stats attached."""
    status_filter = "" if include_archived else "WHERE b.status = 'active'"
    query = f"""
        SELECT 
            b.batch_id,
            b.start_date,
            b.description,
            b.status,
            b.created_at,
            (SELECT COUNT(*) FROM measurements m WHERE m.batch_id = b.batch_id) as log_count,
            (SELECT measured_at FROM measurements m WHERE m.batch_id = b.batch_id ORDER BY measured_at DESC LIMIT 1) as last_log,
            (SELECT pH FROM measurements m WHERE m.batch_id = b.batch_id ORDER BY measured_at DESC LIMIT 1) as latest_pH,
            (SELECT temperature_C FROM measurements m WHERE m.batch_id = b.batch_id ORDER BY measured_at DESC LIMIT 1) as latest_temp
        FROM batches b
        {status_filter}
        ORDER BY b.start_date DESC, b.created_at DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]


def get_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    """Fetch single batch metadata."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        return dict(row) if row else None


def update_batch_status(batch_id: str, status: str) -> None:
    """Update batch status (active/complete/archived)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE batches SET status = ? WHERE batch_id = ?",
            (status, batch_id)
        )


def get_measurements(batch_id: Optional[str] = None, limit: Optional[int] = None) -> pd.DataFrame:
    """Return measurements as DataFrame. Filter by batch if provided."""
    query = "SELECT * FROM measurements"
    params: List[Any] = []
    if batch_id:
        query += " WHERE batch_id = ?"
        params.append(batch_id)
    query += " ORDER BY measured_at ASC"
    if limit:
        query += f" LIMIT {int(limit)}"

    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df["measured_at"] = pd.to_datetime(df["measured_at"])
    return df


def get_measurements_for_batch(batch_id: str) -> pd.DataFrame:
    """Convenience wrapper."""
    return get_measurements(batch_id=batch_id)


def delete_measurement(measurement_id: int) -> None:
    """Delete a single measurement (for corrections)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM measurements WHERE id = ?", (measurement_id,))


def get_latest_measurement(batch_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent measurement dict for a batch."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM measurements 
            WHERE batch_id = ? 
            ORDER BY measured_at DESC 
            LIMIT 1
            """,
            (batch_id,)
        ).fetchone()
        return dict(row) if row else None


def batch_exists(batch_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
        return row is not None


def seed_demo_data() -> None:
    """Create a demo batch with realistic honey vinegar log entries if DB is empty."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        if count > 0:
            return

    demo_batch = "HV-2025-03-HoneyClover"
    start = "2025-03-12"

    if not create_batch(
        demo_batch,
        start,
        "Submerged generator - 12L raw clover honey + spring water (1:4). Active acetobacter mother added day 3."
    ):
        return

    # Realistic progression for submerged honey vinegar (pH falling, temp controlled, aeration on)
    demo_logs = [
        ("2025-03-12 09:15", 4.85, 38.0, 26.2, 0.8, "Day 0 - post inoculation. Honey fully dissolved. Initial aeration started."),
        ("2025-03-13 18:40", 4.62, 52.0, 27.1, 1.1, "pH dropping nicely. Good foam formation on surface."),
        ("2025-03-15 08:05", 4.35, 61.0, 27.8, 1.3, "Smell developing - nice sharp note. DO rising with consistent bubbles."),
        ("2025-03-17 14:20", 4.08, 55.0, 26.9, 1.0, "Slight temp dip last night. Increased aeration slightly."),
        ("2025-03-19 10:55", 3.87, 48.0, 28.3, 0.9, "Strong vinegar aroma. Mother starting to form. Reduced aeration a touch."),
        ("2025-03-21 21:10", 3.71, 42.0, 27.4, 0.7, "pH under 3.8 - progressing well. Sample tasted sharp but clean."),
        ("2025-03-24 11:30", 3.58, 35.0, 25.8, 0.6, "Target range approaching. Monitoring closely for finish."),
        ("2025-03-26 16:45", 3.49, 29.0, 26.5, 0.5, "Beautiful clarity developing. Ready for harvest decision soon."),
    ]

    for measured_at, ph, do, temp, aer, notes in demo_logs:
        add_measurement(demo_batch, measured_at, ph, do, temp, aer, notes)

    # Second small demo batch for multi-batch view
    batch2 = "HV-2025-04-TestJar"
    if create_batch(batch2, "2025-04-01", "Small 2L test jar - wildflower honey. Submerged stone aerator."):
        logs2 = [
            ("2025-04-01 14:00", 4.92, 25.0, 24.8, 0.4, "Initial fill and startup."),
            ("2025-04-03 09:30", 4.55, 47.0, 26.4, 0.6, "pH moving. Good activity."),
            ("2025-04-05 20:15", 4.21, 58.0, 27.9, 0.55, "Smell is promising."),
            ("2025-04-08 12:00", 3.95, 44.0, 28.1, 0.5, "Steady progress."),
        ]
        for ts, ph, do, temp, aer, notes in logs2:
            add_measurement(batch2, ts, ph, do, temp, aer, notes)
