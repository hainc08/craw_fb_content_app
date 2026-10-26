"""Dải ảnh/video thu nhỏ của bài đã cào: bấm để mở file bằng ứng dụng mặc định."""
import os
from dataclasses import dataclass
from pathlib import Path
from tkinter import Canvas, ttk
from typing import Callable

from PIL import Image, ImageOps, ImageTk

TILE = 160


@dataclass
class MediaItem:
    kind: str  # 'image' | 'video'
    path: Path | None
    url: str


def media_items(rows) -> list[MediaItem]:
    items = []
    for r in rows:
        lp = r['local_path'] or ''
        path = Path(lp) if lp and Path(lp).is_file() else None
        items.append(MediaItem(r['kind'], path, r['url']))
    return [i for i in items if i.kind != 'video'] + [i for i in items if i.kind == 'video']


def make_thumbnail(path: Path, max_px: int = TILE) -> Image.Image | None:
    try:
        with Image.open(path) as im:
            im.load()
            return ImageOps.contain(im.convert('RGB'), (max_px, max_px))
    except Exception:
        return None


def _open(path: Path):
    try:
        os.startfile(str(path))
    except Exception:
        pass


class MediaStrip(ttk.Frame):
    def __init__(self, parent, on_download: Callable[[], None]):
        super().__init__(parent)
        self._images: list[ImageTk.PhotoImage] = []
        self.canvas = Canvas(self, height=TILE + 30, highlightthickness=0, background='#f3f3f3')
        bar = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=bar.set)
        self.inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.pack(fill='x')
        bar.pack(fill='x')
        self.download_btn = ttk.Button(self, text='⬇ Tải media còn thiếu', command=on_download)

    def show(self, items: list[MediaItem]) -> None:
        for w in self.inner.winfo_children():
            w.destroy()
        self._images = []
        if not items:
            ttk.Label(self.inner, text='(Bài này không có ảnh/video)', foreground='gray').pack(padx=8, pady=8)
        for item in items:
            self._tile(item)
        if any(i.path is None for i in items):
            self.download_btn.pack(anchor='w', pady=(2, 0))
        else:
            self.download_btn.pack_forget()
        self.canvas.xview_moveto(0)

    def _tile(self, item: MediaItem):
        frame = ttk.Frame(self.inner, padding=3)
        frame.pack(side='left')
        thumb = make_thumbnail(item.path) if item.kind == 'image' and item.path else None
        if thumb is not None:
            photo = ImageTk.PhotoImage(thumb)
            self._images.append(photo)
            w = ttk.Label(frame, image=photo, cursor='hand2')
            caption = item.path.name
        elif item.kind == 'video' and item.path:
            mb = item.path.stat().st_size / 1024 / 1024
            w = ttk.Label(frame, text=f'▶ VIDEO\n\n{item.path.name}\n{mb:.1f} MB', anchor='center',
                          justify='center', width=20, background='#222', foreground='white',
                          cursor='hand2', padding=(6, 40))
            caption = 'Bấm để mở'
        else:
            label = 'ẢNH' if item.kind == 'image' else 'VIDEO'
            w = ttk.Label(frame, text=f'{label}\nChưa tải / file lỗi', anchor='center', justify='center',
                          width=20, background='#ccc', padding=(6, 50))
            caption = ''
        w.pack()
        if item.path:
            w.bind('<Button-1>', lambda e, p=item.path: _open(p))
        ttk.Label(frame, text=caption[:26], foreground='gray').pack()
