from tkinter import Tk

from PIL import Image

import media_view as mv


def test_media_items_missing_file(tmp_path):
    img = tmp_path / 'a.jpg'
    Image.new('RGB', (10, 10)).save(img)
    rows = [{'kind': 'video', 'local_path': '', 'url': 'https://v'},
            {'kind': 'image', 'local_path': str(tmp_path / 'gone.jpg'), 'url': 'https://g'},
            {'kind': 'image', 'local_path': str(img), 'url': 'https://i'}]
    items = mv.media_items(rows)
    assert [(i.kind, i.path) for i in items] == [('image', None), ('image', img), ('video', None)]


def test_make_thumbnail_size(tmp_path):
    p = tmp_path / 'big.png'
    Image.new('RGB', (800, 400)).save(p)
    assert mv.make_thumbnail(p, 160).size == (160, 80)


def test_make_thumbnail_corrupt_returns_none(tmp_path):
    p = tmp_path / 'bad.jpg'
    p.write_bytes(b'not an image')
    assert mv.make_thumbnail(p) is None


def test_media_strip_renders_without_error(tmp_path):
    img = tmp_path / 'a.png'
    Image.new('RGB', (300, 200)).save(img)
    vid = tmp_path / 'v.mp4'
    vid.write_bytes(b'x' * 2048)
    root = Tk()
    root.withdraw()
    try:
        s = mv.MediaStrip(root, on_download=lambda: None)
        s.show([mv.MediaItem('image', img, 'u'), mv.MediaItem('video', vid, 'v'),
                mv.MediaItem('image', None, 'u2')])
        assert len(s._images) == 1 and s.download_btn.winfo_manager()
        s.show([])
        assert not s.download_btn.winfo_manager()
    finally:
        root.destroy()
