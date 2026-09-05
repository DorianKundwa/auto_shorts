import sqlite3
import json
import os
from typing import Optional, Dict, Any, List

DB_PATH = "auto_shorts.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            filename TEXT,
            status TEXT,
            progress INTEGER,
            message TEXT,
            clips_json TEXT,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    # Migrations for existing databases
    try:
        c.execute("ALTER TABLE jobs ADD COLUMN created_at TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE jobs ADD COLUMN metadata_json TEXT DEFAULT '{}'")
    except Exception:
        pass

    conn.commit()
    conn.close()


def _normalize_clips(raw: list) -> list:
    """Normalise the clips list to always be [{path, title}, ...]"""
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"path": item, "title": None})
        elif isinstance(item, dict):
            out.append(item)
    return out


def create_job(job_id: str, filename: str, status: str, progress: int, message: str, metadata: Optional[Dict[str, Any]] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    meta_str = json.dumps(metadata or {})
    c.execute('''
        INSERT INTO jobs (job_id, filename, status, progress, message, clips_json, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (job_id, filename, status, progress, message, "[]", meta_str))
    conn.commit()
    conn.close()


def update_job(
    job_id: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    clips: Optional[List[Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if status is not None:
        c.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))
    if progress is not None:
        c.execute("UPDATE jobs SET progress=? WHERE job_id=?", (progress, job_id))
    if message is not None:
        c.execute("UPDATE jobs SET message=? WHERE job_id=?", (message, job_id))
    if clips is not None:
        c.execute("UPDATE jobs SET clips_json=? WHERE job_id=?", (json.dumps(clips), job_id))
    if metadata is not None:
        # Merge or overwrite metadata
        c.execute("SELECT metadata_json FROM jobs WHERE job_id=?", (job_id,))
        row = c.fetchone()
        existing_meta = {}
        if row and row[0]:
            try:
                existing_meta = json.loads(row[0])
            except Exception:
                existing_meta = {}
        existing_meta.update(metadata)
        c.execute("UPDATE jobs SET metadata_json=? WHERE job_id=?", (json.dumps(existing_meta), job_id))

    conn.commit()
    conn.close()


def get_job(job_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
    row = c.fetchone()
    conn.close()

    if row:
        job_dict = dict(row)
        job_dict['clips'] = _normalize_clips(json.loads(job_dict['clips_json'] or "[]"))
        del job_dict['clips_json']
        try:
            job_dict['metadata'] = json.loads(job_dict.get('metadata_json') or "{}")
        except Exception:
            job_dict['metadata'] = {}
        if 'metadata_json' in job_dict:
            del job_dict['metadata_json']
        return job_dict
    return None


def get_all_jobs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()

    jobs = []
    for row in rows:
        job_dict = dict(row)
        job_dict['clips'] = _normalize_clips(json.loads(job_dict['clips_json'] or "[]"))
        del job_dict['clips_json']
        try:
            job_dict['metadata'] = json.loads(job_dict.get('metadata_json') or "{}")
        except Exception:
            job_dict['metadata'] = {}
        if 'metadata_json' in job_dict:
            del job_dict['metadata_json']
        jobs.append(job_dict)
    return jobs
