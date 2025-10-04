import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'link_cache.sqlite')

def _ensure_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            url TEXT PRIMARY KEY,
            final_url TEXT,
            title TEXT,
            fetched_at TEXT
        )
    ''')
    conn.commit()
    return conn


def get_cached(url, ttl_days: int = None):
    """Return (final_url, title) or None. If ttl_days is provided, return None when entry is older."""
    try:
        conn = _ensure_db()
        c = conn.cursor()
        c.execute('SELECT final_url, title, fetched_at FROM cache WHERE url = ?', (url,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        final_url, title, fetched_at = row
        if ttl_days is not None and fetched_at:
            try:
                from datetime import datetime, timedelta
                fetched = datetime.fromisoformat(fetched_at)
                if datetime.utcnow() - fetched > timedelta(days=ttl_days):
                    return None
            except Exception:
                # If parsing fails, treat as expired
                return None
        return final_url or '', title or ''
    except Exception:
        return None


def set_cached(url, final_url, title):
    try:
        conn = _ensure_db()
        c = conn.cursor()
        c.execute('REPLACE INTO cache(url, final_url, title, fetched_at) VALUES (?, ?, ?, ?)',
                  (url, final_url, title, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass
