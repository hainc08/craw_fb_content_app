import pytest

from pages import (DEFAULT_NAME, DEFAULT_SLUG, NHAN_TAM_CREATION_PROMPT, PageProfile,
                   PageStore, slugify)


def test_slugify_vietnamese():
    assert slugify('Chuyện Đời & Nhân Tâm') == 'chuyen-doi-nhan-tam'
    assert slugify('  Mẹo   Văn Phòng 24h ') == 'meo-van-phong-24h'


def test_missing_file_creates_default(tmp_path):
    s = PageStore(tmp_path / 'pages.json')
    pages = s.list()
    assert [p.slug for p in pages] == [DEFAULT_SLUG]
    assert pages[0].name == DEFAULT_NAME
    assert pages[0].creation_prompt == NHAN_TAM_CREATION_PROMPT
    assert s.active().slug == DEFAULT_SLUG
    assert (tmp_path / 'pages.json').exists()


def test_legacy_fb_keys_migrated_into_default(tmp_path):
    s = PageStore(tmp_path / 'pages.json', legacy={'fb_page_id': '123', 'fb_page_token': 'tok'})
    p = s.get(DEFAULT_SLUG)
    assert (p.fb_page_id, p.fb_page_token) == ('123', 'tok')


def test_save_roundtrip_and_new_store_reads_it(tmp_path):
    path = tmp_path / 'pages.json'
    PageStore(path).save(PageProfile(slug='meo-vp', name='Mẹo VP', hashtags='#meo', max_similarity=0.3))
    p = PageStore(path).get('meo-vp')
    assert (p.name, p.hashtags, p.max_similarity) == ('Mẹo VP', '#meo', 0.3)


def test_save_rejects_bad_values(tmp_path):
    s = PageStore(tmp_path / 'pages.json')
    for bad in [PageProfile(slug='x', name='  '),
                PageProfile(slug='x', name='X', fb_page_id='facebook.com/abc'),
                PageProfile(slug='x', name='X', max_similarity=1.5)]:
        with pytest.raises(ValueError):
            s.save(bad)


def test_corrupt_file_backed_up_and_default_created(tmp_path):
    path = tmp_path / 'pages.json'
    path.write_text('{not json', encoding='utf-8')
    assert PageStore(path).active().slug == DEFAULT_SLUG
    assert (tmp_path / 'pages.json.bak').read_text(encoding='utf-8') == '{not json'


def test_delete_last_page_refused(tmp_path):
    with pytest.raises(ValueError):
        PageStore(tmp_path / 'pages.json').delete(DEFAULT_SLUG)


def test_delete_active_switches_active(tmp_path):
    s = PageStore(tmp_path / 'pages.json')
    s.save(PageProfile(slug='b', name='B'))
    s.set_active('b')
    s.delete('b')
    assert s.active().slug == DEFAULT_SLUG


def test_public_dict_hides_token():
    d = PageProfile(slug='a', name='A', fb_page_token='secret').public_dict()
    assert 'fb_page_token' not in d and d['has_token'] is True
    assert 'secret' not in str(d)
