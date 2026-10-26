import pytest

import app
import page_data as pd


def seed(conn, pid='p1', msg='Nguồn'):
    app.insert_post({'id': pid, 'message': msg, 'attachments': {'data': []}})


def test_migrate_copies_old_draft_once(conn):
    seed(conn)
    conn.execute("INSERT INTO drafts(post_id, body, status) VALUES('p1','cũ','approved')")
    conn.commit()
    pd.migrate(conn, 'a')
    pd.migrate(conn, 'a')
    assert dict(pd.get_draft(conn, 'p1', 'a')) == {'body': 'cũ', 'status': 'approved'}
    assert conn.execute('SELECT COUNT(*) FROM page_drafts').fetchone()[0] == 1


def test_migrate_copies_old_research(conn):
    seed(conn)
    conn.execute("INSERT INTO research(post_id, analysis) VALUES('p1','phân tích cũ')")
    conn.commit()
    pd.migrate(conn, 'a')
    assert pd.get_analysis(conn, 'p1', 'a') == 'phân tích cũ'
    assert pd.get_analysis(conn, 'p1', 'b') is None


def test_drafts_independent_per_page(conn):
    seed(conn)
    pd.migrate(conn, 'a')
    pd.save_draft(conn, 'p1', 'a', 'bài A')
    pd.save_draft(conn, 'p1', 'b', 'bài B', 'approved')
    assert pd.get_draft(conn, 'p1', 'a')['body'] == 'bài A'
    assert pd.get_draft(conn, 'p1', 'b')['status'] == 'approved'


def test_save_draft_rejects_unknown_status(conn):
    pd.migrate(conn, 'a')
    with pytest.raises(ValueError):
        pd.save_draft(conn, 'p1', 'a', 'x', 'done')


def test_published_per_page(conn):
    seed(conn)
    pd.migrate(conn, 'a')
    pd.save_draft(conn, 'p1', 'a', 'x', 'approved')
    pd.mark_published(conn, 'p1', 'a', '111_222', 'text')
    assert pd.get_published(conn, 'p1', 'a')['fb_post_id'] == '111_222'
    assert pd.get_published(conn, 'p1', 'b') is None
    assert pd.get_draft(conn, 'p1', 'a')['status'] == 'published'


def test_mark_scheduled_sets_status(conn):
    seed(conn)
    pd.migrate(conn, 'a')
    pd.save_draft(conn, 'p1', 'a', 'x', 'approved')
    pd.mark_published(conn, 'p1', 'a', '9', 'photo', '2026-10-27T20:00')
    assert pd.get_draft(conn, 'p1', 'a')['status'] == 'scheduled'


def test_list_posts_status_filter(conn):
    seed(conn, 'p1')
    seed(conn, 'p2')
    pd.migrate(conn, 'a')
    pd.save_draft(conn, 'p1', 'a', 'x')
    assert [r['id'] for r in pd.list_posts(conn, 'a', 'none')] == ['p2']
    assert [r['id'] for r in pd.list_posts(conn, 'a', 'review')] == ['p1']
    assert sorted(r['id'] for r in pd.list_posts(conn, 'b', 'none')) == ['p1', 'p2']
