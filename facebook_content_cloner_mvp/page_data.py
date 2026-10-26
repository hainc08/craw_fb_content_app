"""Nháp, phân tích và lịch sử đăng theo cặp (bài nguồn, Page)."""
import sqlite3

STATUSES = ('review', 'approved', 'published', 'scheduled')


def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def migrate(conn, default_slug: str) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS page_drafts (
        post_id TEXT NOT NULL, page_slug TEXT NOT NULL, body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'review', updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(post_id, page_slug))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS page_research (
        post_id TEXT NOT NULL, page_slug TEXT NOT NULL, analysis TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(post_id, page_slug))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS page_published (
        post_id TEXT NOT NULL, page_slug TEXT NOT NULL, fb_post_id TEXT NOT NULL, kind TEXT NOT NULL,
        scheduled_time TEXT DEFAULT '', published_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(post_id, page_slug))''')
    if _has_table(conn, 'drafts'):
        conn.execute('''INSERT OR IGNORE INTO page_drafts(post_id, page_slug, body, status, updated_at)
                        SELECT post_id, ?, body, status, updated_at FROM drafts''', (default_slug,))
    if _has_table(conn, 'research'):
        conn.execute('''INSERT OR IGNORE INTO page_research(post_id, page_slug, analysis, updated_at)
                        SELECT post_id, ?, analysis, updated_at FROM research''', (default_slug,))
    if _has_table(conn, 'published'):
        conn.execute('''INSERT OR IGNORE INTO page_published(post_id, page_slug, fb_post_id, kind,
                        scheduled_time, published_at)
                        SELECT post_id, ?, fb_post_id, kind, scheduled_time, published_at FROM published''',
                     (default_slug,))
    conn.commit()


def get_draft(conn, post_id, page_slug) -> sqlite3.Row | None:
    return conn.execute('SELECT body, status FROM page_drafts WHERE post_id=? AND page_slug=?',
                        (post_id, page_slug)).fetchone()


def save_draft(conn, post_id, page_slug, body: str, status: str = 'review') -> None:
    if status not in STATUSES:
        raise ValueError(f'Trạng thái không hợp lệ: {status}')
    conn.execute('''INSERT INTO page_drafts(post_id, page_slug, body, status) VALUES(?,?,?,?)
                    ON CONFLICT(post_id, page_slug) DO UPDATE SET body=excluded.body,
                    status=excluded.status, updated_at=CURRENT_TIMESTAMP''',
                 (post_id, page_slug, body, status))
    conn.commit()


def get_analysis(conn, post_id, page_slug) -> str | None:
    row = conn.execute('SELECT analysis FROM page_research WHERE post_id=? AND page_slug=?',
                       (post_id, page_slug)).fetchone()
    return row['analysis'] if row else None


def save_analysis(conn, post_id, page_slug, text: str) -> None:
    conn.execute('''INSERT INTO page_research(post_id, page_slug, analysis) VALUES(?,?,?)
                    ON CONFLICT(post_id, page_slug) DO UPDATE SET analysis=excluded.analysis,
                    updated_at=CURRENT_TIMESTAMP''', (post_id, page_slug, text))
    conn.commit()


def get_published(conn, post_id, page_slug) -> sqlite3.Row | None:
    return conn.execute('SELECT * FROM page_published WHERE post_id=? AND page_slug=?',
                        (post_id, page_slug)).fetchone()


def mark_published(conn, post_id, page_slug, fb_post_id: str, kind: str, scheduled_time: str = '') -> None:
    conn.execute('''INSERT INTO page_published(post_id, page_slug, fb_post_id, kind, scheduled_time)
                    VALUES(?,?,?,?,?)''', (post_id, page_slug, fb_post_id, kind, scheduled_time))
    conn.execute('UPDATE page_drafts SET status=?, updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND page_slug=?',
                 ('scheduled' if scheduled_time else 'published', post_id, page_slug))
    conn.commit()


def list_posts(conn, page_slug, status: str | None = None, limit: int = 200) -> list[sqlite3.Row]:
    q = '''SELECT p.id, p.created_time, p.message, COALESCE(d.status, '') AS status,
                  EXISTS(SELECT 1 FROM page_research r WHERE r.post_id=p.id AND r.page_slug=?) AS analyzed,
                  (SELECT COUNT(*) FROM media m WHERE m.post_id=p.id) AS media_count,
                  (SELECT fb_post_id FROM page_published x WHERE x.post_id=p.id AND x.page_slug=?) AS fb_post_id
           FROM posts p LEFT JOIN page_drafts d ON d.post_id=p.id AND d.page_slug=?'''
    args = [page_slug, page_slug, page_slug]
    if status:
        q += " WHERE COALESCE(d.status, '') = ?"
        args.append('' if status == 'none' else status)
    q += ' ORDER BY p.imported_at DESC, p.rowid DESC LIMIT ?'
    args.append(limit)
    return conn.execute(q, args).fetchall()
