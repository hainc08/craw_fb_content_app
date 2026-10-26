from pathlib import Path
from tkinter import Tk

import pytest

import app
import page_data
from pages import DEFAULT_SLUG, PageProfile


@pytest.fixture
def gui(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, 'MEDIA', tmp_path / 'media')
    monkeypatch.setattr(app, 'DB', tmp_path / 'c.sqlite3')
    monkeypatch.setattr(app, 'CONFIG_FILE', tmp_path / 'api_config.json')
    app.init_db()
    app.import_json(str(Path(app.__file__).with_name('sample_posts.json')))
    with app.db() as c:
        page_data.migrate(c, DEFAULT_SLUG)
        page_data.save_draft(c, 'demo_001', DEFAULT_SLUG, 'nháp A')
    root = Tk()
    root.withdraw()
    yield app.App(root), root
    root.destroy()


def select(a, pid):
    a.table.selection_set(pid)
    a.select_post()


def test_app_switches_page_and_shows_per_page_draft(gui):
    a, root = gui
    a.store.save(PageProfile(slug='b', name='Page B'))
    a.reload_pages()
    select(a, 'demo_001')
    assert a.draft.get('1.0', 'end-1c') == 'nháp A'
    a.page_combo.set('Page B')
    a.on_page_change()
    select(a, 'demo_001')
    assert a.draft.get('1.0', 'end-1c') == ''
    assert 'Page B' in root.title()


def test_status_column_and_url_box(gui):
    a, _ = gui
    assert a.table.set('demo_001', 'status') == 'review'
    assert a.table.set('demo_002', 'status') == '—'
    a.url_text.insert('1.0', 'https://facebook.com/a\nhttps://facebook.com/b')
    assert a.url_text.get('1.0', 'end-1c').count('\n') == 1


def test_approve_blocks_copy(gui, monkeypatch):
    a, _ = gui
    errors = []
    monkeypatch.setattr(app.messagebox, 'showerror', lambda *x, **k: errors.append(x))
    select(a, 'demo_002')
    a.draft.insert('1.0', 'Một lời xin lỗi đúng lúc có thể cứu một mối quan hệ. Hãy thử nhé.')
    a.approve()
    assert errors
    with app.db() as c:
        assert page_data.get_draft(c, 'demo_002', DEFAULT_SLUG)['status'] == 'review'


def test_scrape_error_is_shown_to_user(gui, monkeypatch):
    a, root = gui

    class SyncThread:  # chạy luôn trên luồng chính để test được callback Tk
        def __init__(self, target, daemon=None):
            self.target = target

        def start(self):
            self.target()

    def boom(*args, **kwargs):
        raise RuntimeError('Facebook chặn truy cập')
    errors = []
    monkeypatch.setattr(app.threading, 'Thread', SyncThread)
    monkeypatch.setattr(app, 'scrape_facebook_posts', boom)
    monkeypatch.setattr(app.messagebox, 'showerror', lambda *x, **k: errors.append(x))
    a.url_text.insert('1.0', 'https://facebook.com/x')
    a.start_auto_scrape()
    root.update()
    assert errors and 'Facebook chặn truy cập' in errors[0][1]


def test_save_draft_keeps_published_status(gui, monkeypatch):
    a, _ = gui
    warnings = []
    monkeypatch.setattr(app.messagebox, 'showwarning', lambda *x, **k: warnings.append(x))
    with app.db() as c:
        page_data.save_draft(c, 'demo_001', DEFAULT_SLUG, 'bài đã đăng', 'approved')
        page_data.mark_published(c, 'demo_001', DEFAULT_SLUG, '1_1', 'text')
    select(a, 'demo_001')
    a.draft.insert('end', ' sửa thêm')
    a.save_draft()
    with app.db() as c:
        d = page_data.get_draft(c, 'demo_001', DEFAULT_SLUG)
    assert (d['status'], d['body']) == ('published', 'bài đã đăng') and warnings


def test_create_post_asks_before_overwriting_approved(gui, monkeypatch):
    a, _ = gui
    asked, called = [], []
    monkeypatch.setattr(app.messagebox, 'askyesno', lambda *x, **k: asked.append(x) or False)
    monkeypatch.setattr(app, 'create_new', lambda *x, **k: called.append(x) or 'mới')
    with app.db() as c:
        page_data.save_draft(c, 'demo_001', DEFAULT_SLUG, 'bản đã duyệt', 'approved')
    select(a, 'demo_001')
    a.create_post()
    assert asked and not called
