from tkinter import Tk

import pytest

import page_dialog as pdlg
from pages import DEFAULT_SLUG, PageStore


@pytest.fixture
def root():
    r = Tk()
    r.withdraw()
    yield r
    r.destroy()


def make(root, store, saved=None):
    return pdlg.PageManagerDialog(root, store, test_token=lambda i, t: 'X',
                                  on_saved=(saved.append if saved is not None else lambda s: None))


def test_new_page_saved(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdlg.messagebox, 'showerror', lambda *a, **k: None)
    store = PageStore(tmp_path / 'pages.json')
    saved = []
    d = make(root, store, saved)
    d.new_page()
    d.vars['name'].set('Mẹo Văn Phòng')
    d.vars['hashtags'].set('#meo')
    d.vars['max_similarity'].set('0.3')
    d.creation_text.delete('1.0', 'end')
    d.creation_text.insert('1.0', 'Prompt cho {page_name}')
    assert d.save() is True
    p = store.get('meo-van-phong')
    assert (p.hashtags, p.max_similarity, p.creation_prompt) == ('#meo', 0.3, 'Prompt cho {page_name}')
    assert saved == ['meo-van-phong']


def test_invalid_similarity_not_saved(root, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(pdlg.messagebox, 'showerror', lambda *a, **k: errors.append(a))
    d = make(root, PageStore(tmp_path / 'pages.json'))
    d.vars['max_similarity'].set('abc')
    assert d.save() is False and errors


def test_rename_existing_keeps_slug(root, tmp_path):
    store = PageStore(tmp_path / 'pages.json')
    d = make(root, store)
    d.vars['name'].set('Chuyện Đời Mới')
    assert d.save() is True
    assert [p.slug for p in store.list()] == [DEFAULT_SLUG]
    assert store.get(DEFAULT_SLUG).name == 'Chuyện Đời Mới'


def test_provider_label_maps_to_empty(root, tmp_path):
    store = PageStore(tmp_path / 'pages.json')
    d = make(root, store)
    assert d.vars['provider'].get() == pdlg.DEFAULT_PROVIDER_LABEL
    assert d.save() is True and store.get(DEFAULT_SLUG).provider == ''
