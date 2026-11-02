"""SQLite-backed single-host processing queue. No Redis, Celery or extra server."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

STATES = {"QUEUED", "RUNNING", "READY", "FAILED_RETRYABLE",
          "FAILED_TERMINAL", "CANCEL_REQUESTED", "CANCELLED"}


class JobRepository:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "paper2xmind.sqlite3"
        self.initialize()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    source_key TEXT NOT NULL UNIQUE, source_name TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id),
                    source TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT, error_message TEXT,
                    not_before REAL NOT NULL DEFAULT 0,
                    lease_until REAL NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(state, not_before);
                CREATE INDEX IF NOT EXISTS idx_jobs_paper ON jobs(paper_id);
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    state TEXT NOT NULL, stage TEXT NOT NULL,
                    message TEXT, created_at REAL NOT NULL
                );
            """)

    @staticmethod
    def _row(row):
        return dict(row) if row is not None else None

    def create(self, *, source: str, source_key: str, source_name: str) -> dict:
        """Create a paper+job or reuse one with identical source identity."""
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM papers WHERE source_key = ?", (source_key,)
            ).fetchone()
            if existing:
                job = db.execute(
                    "SELECT * FROM jobs WHERE paper_id=? ORDER BY created_at DESC LIMIT 1",
                    (existing["id"],)
                ).fetchone()
                return self._row(job)
            paper_id, job_id = uuid.uuid4().hex, uuid.uuid4().hex
            db.execute("INSERT INTO papers VALUES (?,?,?,?,?)",
                       (paper_id, source_name, source_key, source_name, now))
            db.execute("""INSERT INTO jobs
                       (id,paper_id,source,state,stage,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?)""",
                       (job_id, paper_id, source, "QUEUED", "QUEUED", now, now))
            self._event(db, job_id, "QUEUED", "QUEUED", "Paper accepted")
            return self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    @staticmethod
    def _event(db, job_id, state, stage, message=None):
        db.execute(
            "INSERT INTO job_events(job_id,state,stage,message,created_at) VALUES(?,?,?,?,?)",
            (job_id, state, stage, message, time.time()),
        )

    def get(self, job_id: str):
        with self._connect() as db:
            return self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def get_paper(self, paper_id: str):
        with self._connect() as db:
            row = db.execute(
                """SELECT p.*, j.id AS job_id,j.state AS status,j.stage
                   FROM papers p JOIN jobs j ON j.paper_id=p.id
                   WHERE p.id=? ORDER BY j.created_at DESC LIMIT 1""",
                (paper_id,),
            ).fetchone()
            return self._row(row)

    def list_papers(self):
        with self._connect() as db:
            return [self._row(row) for row in db.execute(
                """SELECT p.id AS paper_id,p.title,p.created_at,
                          j.id AS job_id,j.state AS status,j.stage
                   FROM papers p JOIN jobs j ON j.paper_id=p.id
                   WHERE j.id=(SELECT id FROM jobs WHERE paper_id=p.id
                               ORDER BY created_at DESC LIMIT 1)
                   ORDER BY p.created_at DESC"""
            ).fetchall()]

    def claim(self, lease_seconds: int = 900):
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM jobs WHERE state='QUEUED' AND not_before<=?
                   ORDER BY created_at ASC LIMIT 1""", (now,),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                """UPDATE jobs SET state='RUNNING',stage='ACQUIRING',attempt=attempt+1,
                   lease_until=?,updated_at=? WHERE id=?""",
                (now + lease_seconds, now, row["id"]),
            )
            self._event(db, row["id"], "RUNNING", "ACQUIRING")
            return self._row(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def recover(self):
        """Reclaim leases after process crash; output publication is idempotent."""
        now = time.time()
        with self._connect() as db:
            jobs = db.execute(
                "SELECT id FROM jobs WHERE state='RUNNING' AND lease_until<?", (now,)
            ).fetchall()
            for job in jobs:
                db.execute(
                    "UPDATE jobs SET state='QUEUED',stage='QUEUED',updated_at=? WHERE id=?",
                    (now, job["id"]),
                )
                self._event(db, job["id"], "QUEUED", "QUEUED", "Recovered expired lease")

    def stage(self, job_id: str, stage: str):
        now = time.time()
        with self._connect() as db:
            current = db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if current is None or current["state"] == "CANCEL_REQUESTED":
                raise JobCancelled("Job was cancelled")
            if current["state"] != "RUNNING":
                raise RuntimeError("Job is no longer running")
            db.execute("UPDATE jobs SET stage=?,lease_until=?,updated_at=? WHERE id=?",
                       (stage, now + 900, now, job_id))
            self._event(db, job_id, "RUNNING", stage)

    def finish(self, job_id: str, *, state: str, error_code=None, error_message=None):
        if state not in {"READY", "FAILED_RETRYABLE", "FAILED_TERMINAL", "CANCELLED"}:
            raise ValueError("Invalid terminal state")
        now = time.time()
        with self._connect() as db:
            old = db.execute("SELECT state,attempt FROM jobs WHERE id=?", (job_id,)).fetchone()
            if old is None:
                raise KeyError(job_id)
            if old["state"] == "CANCEL_REQUESTED":
                state = "CANCELLED"
            if old["state"] not in {"RUNNING", "CANCEL_REQUESTED"}:
                raise RuntimeError("Cannot publish terminal state from " + old["state"])
            # Delayed automatic retry for transient errors; three attempts maximum.
            if state == "FAILED_RETRYABLE" and old["attempt"] < 3:
                new_state = "QUEUED"
                delay = min(60, 2 ** old["attempt"])
            else:
                new_state = state
                delay = 0
            db.execute(
                """UPDATE jobs SET state=?,stage=?,error_code=?,error_message=?,
                   not_before=?,lease_until=0,updated_at=? WHERE id=?""",
                (new_state, new_state, error_code, error_message, now + delay, now, job_id),
            )
            self._event(db, job_id, new_state, new_state, error_code)

    def retry(self, job_id: str):
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            if row["state"] != "FAILED_RETRYABLE":
                raise ValueError("Job is not retryable")
            db.execute(
                """UPDATE jobs SET state='QUEUED',stage='QUEUED',attempt=0,
                   error_code=NULL,error_message=NULL,not_before=0,updated_at=? WHERE id=?""",
                (now, job_id),
            )
            self._event(db, job_id, "QUEUED", "QUEUED", "Manual retry")
            return self.get(job_id)

    def cancel(self, job_id: str):
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            if row["state"] == "QUEUED":
                new_state = "CANCELLED"
            elif row["state"] == "RUNNING":
                new_state = "CANCEL_REQUESTED"
            else:
                raise ValueError("Cannot cancel job in current state")
            db.execute("UPDATE jobs SET state=?,updated_at=? WHERE id=?",
                       (new_state, now, job_id))
            self._event(db, job_id, new_state, row["stage"])
            return self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def events(self, job_id: str):
        with self._connect() as db:
            return [self._row(r) for r in db.execute(
                "SELECT state,stage,message,created_at FROM job_events WHERE job_id=? ORDER BY id",
                (job_id,),
            ).fetchall()]


class JobCancelled(RuntimeError):
    pass
