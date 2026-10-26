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
