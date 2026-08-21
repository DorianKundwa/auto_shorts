import sqlite3
import json
import os

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
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    # Migration: add created_at to databases that pre-date this column
    try:
        c.execute("ALTER TABLE jobs ADD COLUMN created_at TEXT DEFAULT (datetime('now'))")
    except Exception:
        pass  # Column already exists
    conn.commit()
    conn.close()


def _normalize_clips(raw: list) -> list:
    """
    Normalise the clips list to always be [{path, title}, ...] regardless of
    which version of the pipeline wrote the record.
    Old format: ["output/foo/bar.mp4", ...]
    New format: [{"path": "output/foo/bar.mp4", "title": "Hook 1"}, ...]
    """
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"path": item, "title": None})
        elif isinstance(item, dict):
            out.append(item)
    return out

def create_job(job_id, filename, status, progress, message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO jobs (job_id, filename, status, progress, message, clips_json)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (job_id, filename, status, progress, message, "[]"))
    conn.commit()
    conn.close()

def update_job(job_id, status=None, progress=None, message=None, clips=None):
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
        
    conn.commit()
    conn.close()

def get_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        job_dict = dict(row)
        job_dict['clips'] = _normalize_clips(json.loads(job_dict['clips_json']))
        del job_dict['clips_json']
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
        job_dict['clips'] = _normalize_clips(json.loads(job_dict['clips_json']))
        del job_dict['clips_json']
        jobs.append(job_dict)
    return jobs
