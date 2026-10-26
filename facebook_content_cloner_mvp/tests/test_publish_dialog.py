import time
from tkinter import Tk

import pytest

import publish_dialog as pdl
from pages import PageProfile

GOOD = 'Chị Hạnh bán bún riêu ở đầu ngõ mười hai năm. Bạn còn nhớ ai từng tử tế với mình?'
PROF = PageProfile(slug='a', name='A', fb_page_id='1', fb_page_token='t')


@pytest.fixture
def root():
    r = Tk()
    r.withdraw()
    yield r
    r.destroy()


def test_submit_blocked_without_token(root, tmp_path):
    d = pdl.PublishDialog(root, PageProfile(slug='a', name='A'), 'p1', 'nguồn', GOOD, tmp_path,
                          do_send=lambda p: 'x', on_done=lambda f: None)
    assert str(d.publish_btn['state']) == 'disabled'


def test_submit_rejects_bad_schedule(root, tmp_path, monkeypatch):
    errs = []
    monkeypatch.setattr(pdl.messagebox, 'showerror', lambda *a, **k: errs.append(a))
    d = pdl.PublishDialog(root, PROF, 'p1', 'nguồn', GOOD, tmp_path, do_send=lambda p: 'x', on_done=lambda f: None)
    d.schedule_var.set('ngày mai')
    d.submit()
    assert errs


def test_submit_success_calls_send_and_done(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdl.messagebox, 'askyesno', lambda *a, **k: True)
    sent, done = [], []
    d = pdl.PublishDialog(root, PROF, 'p1', 'nguồn', GOOD, tmp_path,
                          do_send=lambda plan: sent.append(plan) or '111_222', on_done=done.append)
    d.submit()
    deadline = time.time() + 3
    while not done and time.time() < deadline:
        root.update()
        time.sleep(0.02)
    assert done == ['111_222'] and sent[0].kind == 'text' and sent[0].text == GOOD


def test_submit_cancelled_does_not_send(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdl.messagebox, 'askyesno', lambda *a, **k: False)
    sent = []
    d = pdl.PublishDialog(root, PROF, 'p1', 'nguồn', GOOD, tmp_path,
                          do_send=lambda plan: sent.append(plan) or 'x', on_done=lambda f: None)
    d.submit()
    root.update()
    assert sent == []


def _wait(root, cond, secs=3):
    deadline = time.time() + secs
    while not cond() and time.time() < deadline:
        root.update()
        time.sleep(0.02)


def test_closing_dialog_mid_send_still_records(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdl.messagebox, 'askyesno', lambda *a, **k: True)
    done = []

    def slow_send(plan):
        time.sleep(0.3)
        return '9_9'
    d = pdl.PublishDialog(root, PROF, 'p1', 'nguồn', GOOD, tmp_path, do_send=slow_send, on_done=done.append)
    d.submit()
    d.destroy()
    _wait(root, lambda: done)
    assert done == ['9_9']


def test_cancel_disabled_while_sending(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdl.messagebox, 'askyesno', lambda *a, **k: True)
    d = pdl.PublishDialog(root, PROF, 'p1', 'nguồn', GOOD, tmp_path,
                          do_send=lambda p: time.sleep(0.3) or 'x', on_done=lambda f: None)
    d.submit()
    assert str(d.cancel_btn['state']) == 'disabled'
    _wait(root, lambda: not d.winfo_exists())


def test_on_done_failure_tells_user_post_may_be_live(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdl.messagebox, 'askyesno', lambda *a, **k: True)
    errs = []
    monkeypatch.setattr(pdl.messagebox, 'showerror', lambda *a, **k: errs.append(a))

    def bad_done(fb_id):
        raise RuntimeError('database is locked')
    d = pdl.PublishDialog(root, PROF, 'p1', 'nguồn', GOOD, tmp_path, do_send=lambda p: '5_5', on_done=bad_done)
    d.submit()
    _wait(root, lambda: errs)
    assert errs and '5_5' in errs[0][1]


def test_send_failure_warns_to_check_page(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdl.messagebox, 'askyesno', lambda *a, **k: True)
    errs = []
    monkeypatch.setattr(pdl.messagebox, 'showerror', lambda *a, **k: errs.append(a))

    def timeout(plan):
        raise TimeoutError('read timed out')
    d = pdl.PublishDialog(root, PROF, 'p1', 'nguồn', GOOD, tmp_path, do_send=timeout, on_done=lambda f: None)
    d.submit()
    _wait(root, lambda: errs)
    assert errs and 'kiểm tra Page' in errs[0][1]
