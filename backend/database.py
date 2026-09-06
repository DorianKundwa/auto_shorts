import sqlite3
import json
import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS youtube_tokens (
            channel_id TEXT PRIMARY KEY,
            channel_title TEXT,
            channel_avatar TEXT,
            token_json TEXT,
            is_default INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS published_videos (
            id TEXT PRIMARY KEY,
            job_id TEXT,
            clip_path TEXT,
            youtube_video_id TEXT,
            youtube_url TEXT,
            title TEXT,
            description TEXT,
            privacy_status TEXT,
            published_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS youtube_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # ─── TikTok tables ───────────────────────────────────────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS tiktok_tokens (
            open_id       TEXT PRIMARY KEY,
            display_name  TEXT,
            username      TEXT,
            avatar_url    TEXT,
            token_json    TEXT,
            is_default    INTEGER DEFAULT 1,
            updated_at    TEXT DEFAULT (datetime('now'))
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS tiktok_config (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # ─── Instagram tables ────────────────────────────────────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS instagram_tokens (
            ig_user_id TEXT PRIMARY KEY,
            username   TEXT,
            name       TEXT,
            avatar     TEXT,
            page_token TEXT,
            token_json TEXT,
            is_default INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS instagram_config (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # ─── Social posts table (multi-platform publish history) ─────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS social_posts (
            id          TEXT PRIMARY KEY,
            job_id      TEXT,
            clip_path   TEXT,
            platform    TEXT,
            post_id     TEXT,
            post_url    TEXT,
            title       TEXT,
            caption     TEXT,
            privacy     TEXT,
            published_at TEXT DEFAULT (datetime('now'))
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
        INSERT OR REPLACE INTO jobs (job_id, filename, status, progress, message, clips_json, metadata_json)
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


# ─── YouTube Channel & Publishing Helpers ─────────────────────────────────────

def save_youtube_config(client_id: str, client_secret: str, redirect_uri: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO youtube_config (key, value) VALUES ('client_id', ?)", (client_id,))
    c.execute("INSERT OR REPLACE INTO youtube_config (key, value) VALUES ('client_secret', ?)", (client_secret,))
    if redirect_uri:
        c.execute("INSERT OR REPLACE INTO youtube_config (key, value) VALUES ('redirect_uri', ?)", (redirect_uri,))
    conn.commit()
    conn.close()


def get_youtube_config() -> Dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key, value FROM youtube_config")
    rows = c.fetchall()
    conn.close()
    cfg = {row[0]: row[1] for row in rows}
    # Fallback to environment variables if not stored in DB
    if not cfg.get('client_id'):
        cfg['client_id'] = os.getenv('YOUTUBE_CLIENT_ID', '')
    if not cfg.get('client_secret'):
        cfg['client_secret'] = os.getenv('YOUTUBE_CLIENT_SECRET', '')
    if not cfg.get('redirect_uri'):
        cfg['redirect_uri'] = os.getenv('YOUTUBE_REDIRECT_URI', 'http://localhost:8000/api/youtube/callback')
    return cfg


def save_youtube_token(channel_id: str, channel_title: str, channel_avatar: str, token_data: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Reset other channels as non-default
    c.execute("UPDATE youtube_tokens SET is_default=0")
    token_str = json.dumps(token_data)
    c.execute('''
        INSERT OR REPLACE INTO youtube_tokens (channel_id, channel_title, channel_avatar, token_json, is_default, updated_at)
        VALUES (?, ?, ?, ?, 1, datetime('now'))
    ''', (channel_id, channel_title, channel_avatar, token_str))
    conn.commit()
    conn.close()


def get_youtube_token(channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if channel_id:
        c.execute("SELECT * FROM youtube_tokens WHERE channel_id=?", (channel_id,))
    else:
        c.execute("SELECT * FROM youtube_tokens WHERE is_default=1 LIMIT 1")
    row = c.fetchone()
    conn.close()

    if row:
        token_info = dict(row)
        try:
            token_info['token'] = json.loads(token_info['token_json'])
        except Exception:
            token_info['token'] = {}
        return token_info
    return None


def delete_youtube_token(channel_id: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if channel_id:
        c.execute("DELETE FROM youtube_tokens WHERE channel_id=?", (channel_id,))
    else:
        c.execute("DELETE FROM youtube_tokens")
    conn.commit()
    conn.close()


def record_published_video(
    job_id: str,
    clip_path: str,
    youtube_video_id: str,
    youtube_url: str,
    title: str,
    description: str,
    privacy_status: str,
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    import uuid
    record_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO published_videos (id, job_id, clip_path, youtube_video_id, youtube_url, title, description, privacy_status, published_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ''', (record_id, job_id, clip_path, youtube_video_id, youtube_url, title, description, privacy_status))
    conn.commit()
    conn.close()
    return record_id


def get_published_videos(job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if job_id:
        c.execute("SELECT * FROM published_videos WHERE job_id=? ORDER BY published_at DESC", (job_id,))
    else:
        c.execute("SELECT * FROM published_videos ORDER BY published_at DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── TikTok Config & Token Helpers ────────────────────────────────────────────

def save_tiktok_config(app_key: str, app_secret: str, redirect_uri: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO tiktok_config (key, value) VALUES ('app_key', ?)", (app_key,))
    c.execute("INSERT OR REPLACE INTO tiktok_config (key, value) VALUES ('app_secret', ?)", (app_secret,))
    if redirect_uri:
        c.execute("INSERT OR REPLACE INTO tiktok_config (key, value) VALUES ('redirect_uri', ?)", (redirect_uri,))
    conn.commit()
    conn.close()


def get_tiktok_config() -> Dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key, value FROM tiktok_config")
    rows = c.fetchall()
    conn.close()
    cfg = {row[0]: row[1] for row in rows}
    if not cfg.get('app_key'):
        cfg['app_key'] = os.getenv('TIKTOK_APP_KEY', '')
    if not cfg.get('app_secret'):
        cfg['app_secret'] = os.getenv('TIKTOK_APP_SECRET', '')
    if not cfg.get('redirect_uri'):
        cfg['redirect_uri'] = os.getenv('TIKTOK_REDIRECT_URI', 'http://localhost:8000/api/tiktok/callback')
    return cfg


def save_tiktok_token(
    open_id:      str,
    display_name: str,
    username:     str,
    avatar_url:   str,
    token_data:   Dict[str, Any],
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tiktok_tokens SET is_default=0")
    c.execute('''
        INSERT OR REPLACE INTO tiktok_tokens
            (open_id, display_name, username, avatar_url, token_json, is_default, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, datetime('now'))
    ''', (open_id, display_name, username, avatar_url, json.dumps(token_data)))
    conn.commit()
    conn.close()


def get_tiktok_token(open_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if open_id:
        c.execute("SELECT * FROM tiktok_tokens WHERE open_id=?", (open_id,))
    else:
        c.execute("SELECT * FROM tiktok_tokens WHERE is_default=1 LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        info = dict(row)
        try:
            info['token'] = json.loads(info['token_json'])
        except Exception:
            info['token'] = {}
        return info
    return None


def delete_tiktok_token(open_id: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if open_id:
        c.execute("DELETE FROM tiktok_tokens WHERE open_id=?", (open_id,))
    else:
        c.execute("DELETE FROM tiktok_tokens")
    conn.commit()
    conn.close()


# ─── Instagram Config & Token Helpers ─────────────────────────────────────────

def save_instagram_config(app_id: str, app_secret: str, redirect_uri: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO instagram_config (key, value) VALUES ('app_id', ?)", (app_id,))
    c.execute("INSERT OR REPLACE INTO instagram_config (key, value) VALUES ('app_secret', ?)", (app_secret,))
    if redirect_uri:
        c.execute("INSERT OR REPLACE INTO instagram_config (key, value) VALUES ('redirect_uri', ?)", (redirect_uri,))
    conn.commit()
    conn.close()


def get_instagram_config() -> Dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key, value FROM instagram_config")
    rows = c.fetchall()
    conn.close()
    cfg = {row[0]: row[1] for row in rows}
    if not cfg.get('app_id'):
        cfg['app_id'] = os.getenv('META_APP_ID', '')
    if not cfg.get('app_secret'):
        cfg['app_secret'] = os.getenv('META_APP_SECRET', '')
    if not cfg.get('redirect_uri'):
        cfg['redirect_uri'] = os.getenv('INSTAGRAM_REDIRECT_URI', 'http://localhost:8000/api/instagram/callback')
    return cfg


def save_instagram_token(
    ig_user_id: str,
    username:   str,
    name:       str,
    avatar:     str,
    page_token: str,
    token_data: Dict[str, Any],
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE instagram_tokens SET is_default=0")
    c.execute('''
        INSERT OR REPLACE INTO instagram_tokens
            (ig_user_id, username, name, avatar, page_token, token_json, is_default, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'))
    ''', (ig_user_id, username, name, avatar, page_token, json.dumps(token_data)))
    conn.commit()
    conn.close()


def get_instagram_token(ig_user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if ig_user_id:
        c.execute("SELECT * FROM instagram_tokens WHERE ig_user_id=?", (ig_user_id,))
    else:
        c.execute("SELECT * FROM instagram_tokens WHERE is_default=1 LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        info = dict(row)
        try:
            info['token'] = json.loads(info['token_json'])
        except Exception:
            info['token'] = {}
        return info
    return None


def delete_instagram_token(ig_user_id: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if ig_user_id:
        c.execute("DELETE FROM instagram_tokens WHERE ig_user_id=?", (ig_user_id,))
    else:
        c.execute("DELETE FROM instagram_tokens")
    conn.commit()
    conn.close()


# ─── Generic Social Post Record ────────────────────────────────────────────────

def record_social_post(
    job_id:    str,
    clip_path: str,
    platform:  str,
    post_id:   str,
    post_url:  str,
    title:     str,
    caption:   str,
    privacy:   str,
) -> str:
    import uuid
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    record_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO social_posts (id, job_id, clip_path, platform, post_id, post_url, title, caption, privacy, published_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ''', (record_id, job_id, clip_path, platform, post_id, post_url, title, caption, privacy))
    conn.commit()
    conn.close()
    return record_id


def get_social_posts(job_id: Optional[str] = None, platform: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query  = "SELECT * FROM social_posts WHERE 1=1"
    params: List[Any] = []
    if job_id:
        query  += " AND job_id=?"
        params.append(job_id)
    if platform:
        query  += " AND platform=?"
        params.append(platform)
    query += " ORDER BY published_at DESC LIMIT 100"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

