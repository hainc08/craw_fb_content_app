"""Facebook Content Cloner: permission-based Windows desktop MVP.
Run: python app.py. Never stores Meta/OpenAI tokens in SQLite.
"""
import csv
import datetime
import json
import os
import re
import sqlite3
import threading
import urllib.parse
from pathlib import Path
from tkinter import Tk, Toplevel, StringVar, BooleanVar, Text, filedialog, messagebox, ttk, END

import requests
import page_data
import publisher
from media_view import MediaStrip, media_items
from page_dialog import PageManagerDialog
from pages import DEFAULT_SLUG, PageStore
from publish_dialog import PublishDialog
from research import analyze, create_new, render_prompt, test_gemini, test_cloudflare
from scraper import scrape_facebook_posts

ROOT = Path(os.environ.get('FBCLONER_HOME', Path.home() / 'Documents' / 'FacebookContentCloner'))
ROOT.mkdir(parents=True, exist_ok=True)
MEDIA = ROOT / 'media'
MEDIA.mkdir(exist_ok=True)
DB = ROOT / 'content.sqlite3'
CONFIG_FILE = ROOT / 'api_config.json'


def load_api_config():
    defaults = {
        'provider': 'gemini',
        'gemini_key': os.environ.get('GEMINI_API_KEY', ''),
        'cloudflare_account_id': os.environ.get('CLOUDFLARE_ACCOUNT_ID', ''),
        'cloudflare_token': os.environ.get('CLOUDFLARE_API_TOKEN', ''),
        'openai_key': os.environ.get('OPENAI_API_KEY', '')
    }
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            defaults.update(data)
        except Exception:
            pass
    return defaults


def save_api_config(data):
    try:
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Error saving config: {e}")

GRAPH_VERSION = 'v26.0'  # Update if your Meta app targets another supported version.
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'AuthorizedPageArchive/1.0'})


def db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY, message TEXT NOT NULL DEFAULT '', created_time TEXT DEFAULT '',
            permalink_url TEXT DEFAULT '', raw_json TEXT NOT NULL DEFAULT '{}', imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT NOT NULL, url TEXT NOT NULL,
            kind TEXT NOT NULL, local_path TEXT DEFAULT '', UNIQUE(post_id,url))''')
        c.execute('''CREATE TABLE IF NOT EXISTS research (post_id TEXT PRIMARY KEY, analysis TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS drafts (
            post_id TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'review',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')


def friendly_error(r):
    try:
        payload = r.json()
        err = payload.get('error', {})
        return f"Meta HTTP {r.status_code}: {err.get('message', r.text[:180])} (code={err.get('code','?')})"
    except ValueError:
        return f'HTTP {r.status_code}: {r.text[:180]}'


def graph_get(url, token, params=None):
    """Single bounded request. No browser login or bypassing access checks."""
    headers = {'Authorization': f'Bearer {token}'}
    r = SESSION.get(url, headers=headers, params=params, timeout=(10, 40))
    if not r.ok:
        raise RuntimeError(friendly_error(r))
    return r.json()


def collect_attachments(obj):
    """Extract only URLs Graph returned; some URLs are previews, not original MP4."""
    found = []
    def walk(x):
        if isinstance(x, dict):
            media = x.get('media') or {}
            if isinstance(media, dict):
                img = media.get('image') or {}
                if isinstance(img, dict) and img.get('src'):
                    found.append(('image', img['src']))
                if media.get('source'):
                    found.append(('video', media['source']))
            if x.get('source') and isinstance(x['source'], str):
                found.append(('video', x['source']))
            for k in ('data','attachments','subattachments'):
                if k in x:
                    walk(x[k])
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(obj)
    unique = {}
    for kind, url in found:
        if url.startswith('https://'):
            unique[url] = kind
    return [(kind, url) for url, kind in unique.items()]


def insert_post(post):
    pid = str(post.get('id', '')).strip()
    if not pid:
        return False
    message = str(post.get('message') or post.get('story') or '')
    raw = json.dumps(post, ensure_ascii=False)
    with db() as c:
        c.execute('''INSERT INTO posts(id,message,created_time,permalink_url,raw_json)
                     VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                     message=excluded.message,created_time=excluded.created_time,
                     permalink_url=excluded.permalink_url,raw_json=excluded.raw_json''',
                  (pid, message, post.get('created_time',''), post.get('permalink_url',''), raw))
        for kind, url in collect_attachments(post):
            c.execute('INSERT OR IGNORE INTO media(post_id,url,kind) VALUES (?,?,?)', (pid,url,kind))
    return True


def import_json(path):
    payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    posts = payload if isinstance(payload, list) else payload.get('data', payload.get('posts', []))
    if not isinstance(posts, list):
        raise ValueError('JSON phải là danh sách bài viết hoặc đối tượng có data/posts là danh sách.')
    return sum(insert_post(p) for p in posts if isinstance(p, dict))


def fetch_page(page_id, token, max_posts=100):
    if not re.fullmatch(r'\d+', page_id.strip()):
        raise ValueError('Nhập Page ID dạng số (không nhập URL /share/).')
    url = f'https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/posts'
    params = {'fields':'id,message,story,created_time,permalink_url,attachments{media,type,subattachments}', 'limit': min(50,max_posts)}
    count = 0
    while url and count < max_posts:
        result = graph_get(url, token, params)
        for post in result.get('data', []):
            if insert_post(post): count += 1
            if count >= max_posts: break
        next_url = result.get('paging',{}).get('next')
        # Graph next may contain token in query; do not print/log it, and send auth via header.
        if next_url:
            parts = urllib.parse.urlsplit(next_url)
            if parts.scheme != 'https' or parts.hostname != 'graph.facebook.com':
                raise RuntimeError('Paging URL không thuộc graph.facebook.com')
            q = urllib.parse.parse_qs(parts.query)
            q.pop('access_token', None)
            url = urllib.parse.urlunsplit((parts.scheme,parts.netloc,parts.path,'',''))
            params = {key: vals[-1] for key, vals in q.items()}
        else:
            url = None
    return count


def save_media(row, max_bytes=150*1024*1024):
    url = row['url']
    if not url.startswith('https://'):
        raise ValueError('Chỉ hỗ trợ link HTTPS trực tiếp')
    # We do not scrape playback URLs or bypass permissions. These must be authorized media URLs.
    output = MEDIA / re.sub(r'[^a-zA-Z0-9_-]', '_', row['post_id'])
    output.mkdir(exist_ok=True)
    with SESSION.get(url, stream=True, timeout=(10,60), allow_redirects=True) as r:
        r.raise_for_status()
        if not r.url.startswith('https://'):
            raise ValueError('Media redirect không phải HTTPS')
        mime = r.headers.get('content-type','').split(';')[0].lower()
        extensions = {'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','video/mp4':'.mp4'}
        if mime not in extensions:
            raise ValueError(f'Media không hỗ trợ hoặc URL chỉ là trang xem: {mime}')
        length = int(r.headers.get('content-length') or 0)
        if length > max_bytes: raise ValueError('Media quá giới hạn 150 MB')
        dest = output / f"media_{row['id']}{extensions[mime]}"
        tmp = dest.with_suffix(dest.suffix+'.part')
        total = 0
        try:
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1024*1024):
                    total += len(chunk)
                    if total > max_bytes: raise ValueError('Media vượt 150 MB')
                    f.write(chunk)
            tmp.replace(dest)
        finally:
            tmp.unlink(missing_ok=True)
    with db() as c:
        c.execute('UPDATE media SET local_path=? WHERE id=?', (str(dest),row['id']))
    return dest


class App:
    def __init__(self, root):
        self.root = root
        root.geometry('1380x900')
        self.store = PageStore(ROOT / 'pages.json', legacy=load_api_config())
        self.scrape_limit = StringVar(value='5')
        self.auto_download_media = BooleanVar(value=True)
        self.api_config = load_api_config()
        self.ai_provider = StringVar(value=self.api_config.get('provider', 'gemini'))
        self.status = StringVar(value=f'Sẵn sàng | Dữ liệu lưu tại: {ROOT}')
        self.current = None

        # --- CHỌN PAGE ĐANG LÀM ---
        page_bar = ttk.Frame(root, padding=(12, 8, 12, 0))
        page_bar.pack(fill='x')
        ttk.Label(page_bar, text='Page đang làm:', font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.page_var = StringVar()
        self.page_combo = ttk.Combobox(page_bar, textvariable=self.page_var, state='readonly', width=40,
                                       font=('Segoe UI', 10))
        self.page_combo.pack(side='left', padx=6)
        self.page_combo.bind('<<ComboboxSelected>>', self.on_page_change)
        ttk.Button(page_bar, text='⚙️ Quản lý Page', command=self.open_page_manager).pack(side='left', padx=4)
        self.page_info_lbl = ttk.Label(page_bar, text='', foreground='gray')
        self.page_info_lbl.pack(side='left', padx=8)

        # --- KHUNG CÀO FACEBOOK ---
        top_frame = ttk.LabelFrame(root, text=' 🚀 Cào bài viết & Reels từ Facebook URL ', padding=10)
        top_frame.pack(fill='x', padx=12, pady=(6, 4))
        r1 = ttk.Frame(top_frame)
        r1.pack(fill='x', pady=2)
        ttk.Label(r1, text='Link Facebook\n(mỗi dòng 1 link):', font=('Segoe UI', 9, 'bold'),
                  justify='left').pack(side='left', padx=(0, 6), anchor='n')
        self.url_text = Text(r1, height=3, wrap='none', font=('Segoe UI', 10))
        self.url_text.pack(side='left', fill='x', expand=True, padx=4)
        side = ttk.Frame(r1)
        side.pack(side='left', anchor='n', padx=(8, 0))
        lim = ttk.Frame(side)
        lim.pack(anchor='w')
        ttk.Label(lim, text='Số bài:').pack(side='left', padx=(0, 4))
        ttk.Entry(lim, textvariable=self.scrape_limit, width=6, justify='center').pack(side='left')
        ttk.Button(side, text='⚡ CÀO BÀI & TẢI MEDIA', command=self.start_auto_scrape).pack(fill='x', pady=(4, 0))

        r2 = ttk.Frame(top_frame)
        r2.pack(fill='x', pady=(6, 0))
        ttk.Checkbutton(r2, text='Tự động tải Video MP4 & Hình ảnh về máy',
                        variable=self.auto_download_media).pack(side='left', padx=(0, 15))
        ttk.Button(r2, text='📂 Mở thư mục Media', command=self.open_media_folder).pack(side='left', padx=3)
        ttk.Button(r2, text='📝 Dán nhanh thủ công', command=self.open_manual_add_dialog).pack(side='left', padx=3)
        ttk.Button(r2, text='📥 Nhập file JSON', command=self.load_json).pack(side='left', padx=3)
        ttk.Button(r2, text='📊 Xuất CSV', command=self.export).pack(side='left', padx=3)
        ttk.Button(r2, text='🔄 Làm mới danh sách', command=self.refresh).pack(side='left', padx=3)
        ttk.Label(r2, text='Hỗ trợ: Reels, Video, Post cá nhân/Fanpage', foreground='gray').pack(side='right')

        # --- DANH SÁCH BÊN TRÁI & BIÊN TẬP BÊN PHẢI ---
        mid = ttk.Panedwindow(root, orient='horizontal')
        mid.pack(fill='both', expand=True, padx=12, pady=6)
        listf = ttk.Frame(mid)
        mid.add(listf, weight=2)
        self.table = ttk.Treeview(listf, columns=('date', 'caption', 'media', 'status'), show='headings')
        for key, label, width in [('date', 'Ngày', 120), ('caption', 'Nội dung', 330), ('media', 'Media', 55),
                                  ('status', 'Trạng thái', 90)]:
            self.table.heading(key, text=label)
            self.table.column(key, width=width)
        y = ttk.Scrollbar(listf, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=y.set)
        self.table.pack(side='left', fill='both', expand=True)
        y.pack(side='right', fill='y')
        self.table.bind('<<TreeviewSelect>>', self.select_post)

        editor = ttk.Frame(mid, padding=(8, 0))
        mid.add(editor, weight=3)
        ttk.Label(editor, text='Nguồn (chỉ đọc):', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.source = Text(editor, height=5, wrap='word')
        self.source.pack(fill='both', expand=True)
        self.source.configure(state='disabled')
        ttk.Label(editor, text='Ảnh & Video đã cào (bấm để mở):', font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 0))
        self.media_strip = MediaStrip(editor, on_download=self.download)
        self.media_strip.pack(fill='x')

        ttk.Label(editor, text='Phân tích nội dung nguồn (theo prompt của Page):',
                  font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 0))
        self.research = Text(editor, height=4, wrap='word')
        self.research.pack(fill='both', expand=True)
        ttk.Label(editor, text='Bài mới cho Page (sửa trực tiếp được):',
                  font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 0))
        self.draft = Text(editor, height=8, wrap='word')
        self.draft.pack(fill='both', expand=True)

        key_box = ttk.Frame(editor)
        key_box.pack(fill='x', pady=(6, 2))
        self.ai_status_lbl = ttk.Label(key_box, text='', font=('Segoe UI', 9, 'bold'), foreground='#0066cc')
        self.ai_status_lbl.pack(side='left', padx=2)
        ttk.Button(key_box, text='⚙️ Khóa AI (dùng chung)', command=self.open_api_settings_dialog).pack(side='right', padx=2)

        actions = ttk.Frame(editor)
        actions.pack(fill='x', pady=7)
        for title, fn in [('Phân tích AI', self.analyze_post), ('Sáng tạo mới', self.create_post),
                          ('Kiểm tra trùng', self.check_similarity), ('Lưu nháp', self.save_draft),
                          ('Duyệt', self.approve), ('🚀 Đăng lên Page', self.open_publish),
                          ('Xuất TXT', self.export_txt)]:
            ttk.Button(actions, text=title, command=fn).pack(side='left', padx=2)

        ttk.Label(root, textvariable=self.status, padding=8, relief='sunken').pack(fill='x')
        self.reload_pages()

    # ---------- Page ----------
    @property
    def page(self):
        return self.store.active()

    def reload_pages(self):
        pages = self.store.list()
        self.page_combo['values'] = [p.name for p in pages]
        self.page_var.set(self.page.name)
        self._page_changed()

    def on_page_change(self, event=None):
        name = self.page_var.get()
        for p in self.store.list():
            if p.name == name:
                self.store.set_active(p.slug)
                break
        self._page_changed()

    def _page_changed(self):
        p = self.page
        self.root.title(f'Facebook Content Cloner — Page: {p.name}')
        token = '✓ có token' if p.fb_page_id and p.fb_page_token else '⚠️ chưa có ID/token để đăng'
        self.page_info_lbl.configure(text=f'{token} | hashtag: {p.hashtags or "—"} | ngưỡng trùng {p.max_similarity:.0%}')
        self.ai_status_lbl.configure(text=self.get_ai_status_text())
        self.refresh()
        self.select_post()

    def open_page_manager(self):
        def test_token(pid, tok):
            info = graph_get(f'https://graph.facebook.com/{GRAPH_VERSION}/{pid}', tok, {'fields': 'id,name'})
            return info.get('name', pid)
        PageManagerDialog(self.root, self.store, test_token=test_token, on_saved=lambda slug: self.reload_pages())

    def effective_provider(self):
        return self.page.provider or self.api_config.get('provider', 'gemini')

    def ai_ready(self, provider):
        if provider == 'gemini' and not self.api_config.get('gemini_key', '').strip():
            missing = 'Gemini API Key'
        elif provider == 'cloudflare' and not (self.api_config.get('cloudflare_token', '').strip()
                                               and self.api_config.get('cloudflare_account_id', '').strip()):
            missing = 'Cloudflare Account ID / API Token'
        elif provider == 'openai' and not self.api_config.get('openai_key', '').strip():
            missing = 'OpenAI API Key'
        else:
            return True
        messagebox.showwarning('Thiếu khóa AI', f'Bạn chưa nhập {missing}. Hãy bấm [⚙️ Khóa AI] để điền.')
        self.open_api_settings_dialog()
        return False

    def get_ai_status_text(self):
        p = self.effective_provider()
        key = {'gemini': 'gemini_key', 'cloudflare': 'cloudflare_token', 'openai': 'openai_key'}.get(p, '')
        has_k = bool(self.api_config.get(key, '').strip())
        name = {'gemini': 'Google Gemini', 'cloudflare': 'Cloudflare Workers AI', 'openai': 'OpenAI'}.get(p, p)
        return f"🤖 AI: {name} {'[✓ Đã có Key]' if has_k else '[⚠️ Chưa nhập Key]'}"

    def open_media_folder(self):
        try:
            os.startfile(str(MEDIA))
        except Exception:
            messagebox.showinfo('Thư mục Media', f'Đường dẫn thư mục media:\n{MEDIA}')

    def start_auto_scrape(self):
        url_input = self.url_text.get('1.0', 'end-1c').strip()
        if not url_input:
            messagebox.showwarning('Chưa có link', 'Vui lòng dán link Facebook (Reels, Video, Post hoặc Page) vào ô trên, mỗi dòng một link.')
            self.url_text.focus()
            return
        try:
            max_posts = max(1, min(100, int(self.scrape_limit.get().strip())))
        except ValueError:
            messagebox.showwarning('Số bài không hợp lệ', 'Số bài phải là số nguyên dương (ví dụ: 1, 5, 10).')
            return

        auto_dl = self.auto_download_media.get()

        def work():
            self.status.set(f'Đang cào dữ liệu tối đa {max_posts} bài từ URL...')
            try:
                posts = scrape_facebook_posts(url_input, max_count=max_posts,
                                             progress_callback=lambda txt: self.root.after(0, lambda: self.status.set(txt)))
            except Exception as exc:
                msg = str(exc)  # exc bị xóa khi ra khỏi khối except, nên giữ chuỗi lỗi lại
                self.root.after(0, lambda: messagebox.showerror('Lỗi cào dữ liệu', msg))
                self.root.after(0, lambda: self.status.set(f'Lỗi cào dữ liệu: {msg}'))
                return

            if not posts:
                self.root.after(0, lambda: messagebox.showwarning('Không có kết quả', 'Không tìm thấy bài viết nào từ link đã cung cấp.'))
                return

            success_count = 0
            first_id = None
            total_media_downloaded = 0

            for idx, post in enumerate(posts, 1):
                self.root.after(0, lambda i=idx, tot=len(posts): self.status.set(f'Đang lưu bài {i}/{tot} vào database...'))
                if insert_post(post):
                    success_count += 1
                    if not first_id:
                        first_id = post['id']
                    
                    if auto_dl:
                        with db() as c:
                            rows = c.execute('SELECT * FROM media WHERE post_id=? AND local_path=""', (post['id'],)).fetchall()
                        for row in rows:
                            try:
                                self.root.after(0, lambda p=post['id']: self.status.set(f"Đang tải media bài {p}..."))
                                save_media(row)
                                total_media_downloaded += 1
                            except Exception as dl_err:
                                print(f"Media download error: {dl_err}")

            def finish():
                self.refresh()
                if first_id and self.table.exists(first_id):
                    self.table.selection_set(first_id)
                    self.select_post()
                res_msg = f"Đã cào thành công {success_count} bài viết!"
                if auto_dl:
                    res_msg += f"\nĐã tải {total_media_downloaded} file hình ảnh/video vào thư mục Media."
                self.status.set(f"Hoàn thành: Đã cào {success_count} bài | {total_media_downloaded} media đã tải.")
                messagebox.showinfo('Thành công', res_msg)

            self.root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def run_async(self, label, work):
        self.status.set(label)
        def job():
            try:
                result = work()
                self.root.after(0, lambda: (self.status.set(str(result)), self.refresh()))
            except Exception as exc:
                msg = str(exc)
                self.root.after(0, lambda: (self.status.set(msg), messagebox.showerror('Lỗi', msg)))
        threading.Thread(target=job, daemon=True).start()

    def load_json(self):
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if path:
            self.run_async('Đang nhập JSON...', lambda: f'Đã nhập {import_json(path)} bài từ JSON.')

    def open_manual_add_dialog(self):
        win = Toplevel(self.root)
        win.title('Thêm bài viết thủ công / Dán nhanh')
        win.geometry('600x420')
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text='URL bài viết (nếu có):').pack(anchor='w', padx=12, pady=(10, 2))
        url_var = StringVar()
        ttk.Entry(win, textvariable=url_var).pack(fill='x', padx=12, pady=2)

        ttk.Label(win, text='Nội dung / Caption / Lời thoại (bắt buộc):').pack(anchor='w', padx=12, pady=(8, 2))
        msg_text = Text(win, height=10, wrap='word')
        msg_text.pack(fill='both', expand=True, padx=12, pady=2)

        def do_save():
            caption = msg_text.get('1.0', 'end-1c').strip()
            if not caption:
                messagebox.showwarning('Thiếu nội dung', 'Vui lòng nhập nội dung bài viết.', parent=win)
                return
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            post_id = f"manual_{ts}"
            url = url_var.get().strip() or f"https://facebook.com/manual_post_{ts}"
            post = {
                'id': post_id,
                'message': caption,
                'created_time': datetime.datetime.now().isoformat(),
                'permalink_url': url,
                'attachments': {'data': []}
            }
            if insert_post(post):
                self.refresh()
                if self.table.exists(post_id):
                    self.table.selection_set(post_id)
                    self.select_post()
                messagebox.showinfo('Thành công', 'Đã thêm bài viết mới!', parent=win)
                win.destroy()

        btn_box = ttk.Frame(win, padding=10)
        btn_box.pack(fill='x')
        ttk.Button(btn_box, text='Lưu bài viết', command=do_save).pack(side='left', padx=4)
        ttk.Button(btn_box, text='Hủy', command=win.destroy).pack(side='right', padx=4)

    def refresh(self):
        selected = self.current
        for item in self.table.get_children():
            self.table.delete(item)
        with db() as c:
            rows = page_data.list_posts(c, self.page.slug, limit=1000)
        for row in rows:
            self.table.insert('', END, iid=row['id'], values=(
                row['created_time'][:19], row['message'].replace('\n', ' ')[:65], row['media_count'],
                row['status'] or '—'))
        if selected and self.table.exists(selected):
            self.table.selection_set(selected)

    def _set_text(self, widget, value, readonly=False):
        widget.configure(state='normal')
        widget.delete('1.0', END)
        if value:
            widget.insert('1.0', value)
        if readonly:
            widget.configure(state='disabled')

    def select_post(self, event=None):
        selection = self.table.selection()
        if not selection:
            self.current = None
            self._set_text(self.source, '', readonly=True)
            self._set_text(self.research, '')
            self._set_text(self.draft, '')
            self.media_strip.show([])
            return
        self.current = selection[0]
        slug = self.page.slug
        with db() as c:
            p = c.execute('SELECT * FROM posts WHERE id=?', (self.current,)).fetchone()
            d = page_data.get_draft(c, self.current, slug)
            analysis = page_data.get_analysis(c, self.current, slug)
            pub = page_data.get_published(c, self.current, slug)
            medias = c.execute('SELECT kind, local_path, url FROM media WHERE post_id=?', (self.current,)).fetchall()
        self._set_text(self.source, f"🔗 LINK: {p['permalink_url']}\n\n📝 CAPTION GỐC:\n{p['message']}", readonly=True)
        self.media_strip.show(media_items(medias))
        self._set_text(self.research, analysis)
        self._set_text(self.draft, d['body'] if d else '')
        state = d['status'] if d else 'chưa có nháp'
        extra = f" | đã đăng: {pub['fb_post_id']}" if pub else ''
        self.status.set(f"Page {self.page.name} | Bài {self.current} | Trạng thái: {state}{extra}")

    def save_draft(self, status='review'):
        if not self.current:
            return False
        body = self.draft.get('1.0', 'end-1c').strip()
        if not body:
            messagebox.showwarning('Bản nháp', 'Nhập nội dung mới trước.')
            return False
        if self._locked_by_publish(self.current):
            return False
        with db() as c:
            page_data.save_draft(c, self.current, self.page.slug, body, status)
        self.status.set(f'Đã lưu bản nháp cho {self.page.name}: {status}')
        self.refresh()
        return True

    def _locked_by_publish(self, pid):
        """Bài đã đăng/hẹn giờ trên Page này thì giữ nguyên nội dung đã đăng."""
        with db() as c:
            pub = page_data.get_published(c, pid, self.page.slug)
        if pub:
            messagebox.showwarning('Bài đã đăng',
                                   f'Bài này đã đăng/hẹn giờ trên "{self.page.name}" (ID {pub["fb_post_id"]}).\n'
                                   'Nội dung đã đăng được giữ nguyên, không lưu đè.')
            return True
        return False

    def approve(self):
        if not self.current:
            return
        if not self.save_draft('review'):
            return
        with db() as c:
            src = c.execute('SELECT message FROM posts WHERE id=?', (self.current,)).fetchone()['message']
        r = publisher.check_originality(src, self.draft.get('1.0', 'end-1c').strip(), self.page.max_similarity)
        if not r['passed']:
            shared = '\n'.join(r['shared_phrases'][:8]) or '(không có cụm 7 từ chung)'
            messagebox.showerror('Chưa duyệt được',
                                 f'Bài mới còn quá giống bài nguồn.\nTỉ lệ khớp: {r["sequence_ratio"]:.0%} '
                                 f'(tối đa {self.page.max_similarity:.0%})\nCụm trùng:\n{shared}')
            return
        self.save_draft('approved')


    def open_api_settings_dialog(self):
        win = Toplevel(self.root)
        win.title('Cấu hình API AI (Google Gemini & Cloudflare)')
        win.geometry('660x540')
        win.transient(self.root)
        win.grab_set()

        # Chọn Nhà cung cấp
        prov_frame = ttk.LabelFrame(win, text=' 1. Chọn Nhà cung cấp AI để Phân tích & Sáng tạo ', padding=10)
        prov_frame.pack(fill='x', padx=14, pady=(10, 6))

        selected_prov = StringVar(value=self.api_config.get('provider', 'gemini'))
        ttk.Radiobutton(prov_frame, text='Google Gemini (Khuyên dùng - Nhanh, Tiếng Việt tự nhiên, Có gói Free)',
                        variable=selected_prov, value='gemini').pack(anchor='w', pady=2)
        ttk.Radiobutton(prov_frame, text='Cloudflare Workers AI (Mô hình Llama 3.1 8B Instruct)',
                        variable=selected_prov, value='cloudflare').pack(anchor='w', pady=2)
        ttk.Radiobutton(prov_frame, text='OpenAI (GPT-4.1 mini)',
                        variable=selected_prov, value='openai').pack(anchor='w', pady=2)

        # Cấu hình Google Gemini
        gem_frame = ttk.LabelFrame(win, text=' 2. Cấu hình Google Gemini API ', padding=10)
        gem_frame.pack(fill='x', padx=14, pady=6)

        ttk.Label(gem_frame, text='Gemini API Key:').pack(anchor='w')
        gem_var = StringVar(value=self.api_config.get('gemini_key', ''))
        gem_entry = ttk.Entry(gem_frame, textvariable=gem_var, show='●')
        gem_entry.pack(fill='x', pady=(2, 6))

        gem_btn_row = ttk.Frame(gem_frame)
        gem_btn_row.pack(fill='x')
        def test_gem():
            k = gem_var.get().strip()
            ok, msg = test_gemini(k)
            if ok:
                messagebox.showinfo('Kiểm tra Gemini', msg, parent=win)
            else:
                messagebox.showerror('Kiểm tra Gemini thất bại', msg, parent=win)
        ttk.Button(gem_btn_row, text='🔍 Kiểm tra kết nối Gemini', command=test_gem).pack(side='left')
        ttk.Label(gem_btn_row, text='(Lấy key tại aistudio.google.com)', foreground='gray').pack(side='left', padx=10)

        # Cấu hình Cloudflare
        cf_frame = ttk.LabelFrame(win, text=' 3. Cấu hình Cloudflare Workers AI ', padding=10)
        cf_frame.pack(fill='x', padx=14, pady=6)

        ttk.Label(cf_frame, text='Cloudflare Account ID:').pack(anchor='w')
        cf_acc_var = StringVar(value=self.api_config.get('cloudflare_account_id', ''))
        ttk.Entry(cf_frame, textvariable=cf_acc_var).pack(fill='x', pady=(2, 4))

        ttk.Label(cf_frame, text='Cloudflare API Token:').pack(anchor='w')
        cf_tok_var = StringVar(value=self.api_config.get('cloudflare_token', ''))
        ttk.Entry(cf_frame, textvariable=cf_tok_var, show='●').pack(fill='x', pady=(2, 6))

        def test_cf():
            acc = cf_acc_var.get().strip()
            tok = cf_tok_var.get().strip()
            ok, msg = test_cloudflare(acc, tok)
            if ok:
                messagebox.showinfo('Kiểm tra Cloudflare', msg, parent=win)
            else:
                messagebox.showerror('Kiểm tra Cloudflare thất bại', msg, parent=win)
        ttk.Button(cf_frame, text='🔍 Kiểm tra kết nối Cloudflare', command=test_cf).pack(anchor='w')

        # Nút Lưu
        bottom_box = ttk.Frame(win, padding=12)
        bottom_box.pack(fill='x')

        def save_and_close():
            self.api_config['provider'] = selected_prov.get()
            self.api_config['gemini_key'] = gem_var.get().strip()
            self.api_config['cloudflare_account_id'] = cf_acc_var.get().strip()
            self.api_config['cloudflare_token'] = cf_tok_var.get().strip()
            save_api_config(self.api_config)
            self.ai_provider.set(self.api_config['provider'])
            self.ai_status_lbl.configure(text=self.get_ai_status_text())
            messagebox.showinfo('Đã lưu', 'Đã lưu cấu hình API thành công!', parent=win)
            win.destroy()

        ttk.Button(bottom_box, text='💾 Lưu Cấu Hình & Sử Dụng', command=save_and_close).pack(side='left')
        ttk.Button(bottom_box, text='Đóng', command=win.destroy).pack(side='right')

    def _source_text(self, pid):
        with db() as c:
            p = c.execute('SELECT message FROM posts WHERE id=?', (pid,)).fetchone()
        return p['message'] if p else ''

    def analyze_post(self):
        if not self.current:
            messagebox.showwarning('Chưa chọn bài', 'Vui lòng chọn một bài viết trong danh sách bên trái.')
            return
        pid, page = self.current, self.page
        source = self._source_text(pid)
        if not source.strip():
            messagebox.showwarning('Nội dung trống', 'Bài viết này không có nội dung text để phân tích.')
            return
        provider = self.effective_provider()
        if not self.ai_ready(provider):
            return
        instruction = render_prompt(page.analysis_prompt, page.name, page.hashtags)

        def work():
            result = analyze(source, provider, self.api_config, instruction=instruction)
            with db() as c:
                page_data.save_analysis(c, pid, page.slug, result)

            def update():
                if self.current == pid and self.page.slug == page.slug:
                    self._set_text(self.research, result)
            self.root.after(0, update)
            return f'Đã phân tích bằng {provider.upper()} theo prompt của "{page.name}". Bấm "Sáng tạo mới".'

        self.run_async(f'AI ({provider.upper()}) đang phân tích nội dung...', work)

    def create_post(self):
        if not self.current:
            messagebox.showwarning('Chưa chọn bài', 'Vui lòng chọn một bài viết trong danh sách bên trái.')
            return
        pid, page = self.current, self.page
        source = self._source_text(pid)
        if not source.strip():
            messagebox.showwarning('Nội dung trống', 'Bài viết này không có nội dung để sáng tạo.')
            return
        if self._locked_by_publish(pid):
            return
        with db() as c:
            existing = page_data.get_draft(c, pid, page.slug)
        if existing and existing['status'] == 'approved' and not messagebox.askyesno(
                'Ghi đè bài đã duyệt?', 'Bài này đã được duyệt. Viết bản mới bằng AI sẽ thay bản đã duyệt '
                '(và phải duyệt lại). Tiếp tục?'):
            return
        provider = self.effective_provider()
        if not self.ai_ready(provider):
            return
        analysis = self.research.get('1.0', 'end-1c').strip()
        instruction = render_prompt(page.creation_prompt, page.name, page.hashtags)

        def work():
            result = create_new(source, analysis, provider, self.api_config, instruction=instruction)
            check = publisher.check_originality(source, result, page.max_similarity)
            with db() as c:
                page_data.save_draft(c, pid, page.slug, result, 'review')

            def update():
                if self.current == pid and self.page.slug == page.slug:
                    self._set_text(self.draft, result)
            self.root.after(0, update)
            verdict = 'đạt' if check['passed'] else 'QUÁ GIỐNG nguồn — nên viết lại'
            return (f'Đã viết bài mới cho "{page.name}" ({provider.upper()}), đã lưu nháp; '
                    f'tỉ lệ trùng {check["sequence_ratio"]:.0%} → {verdict}.')

        self.run_async(f'AI ({provider.upper()}) đang viết bài mới cho "{page.name}"...', work)

    def check_similarity(self):
        if not self.current:
            return
        r = publisher.check_originality(self._source_text(self.current), self.draft.get('1.0', 'end-1c'),
                                        self.page.max_similarity)
        detail = '\n'.join(r['shared_phrases']) or '(không phát hiện cụm 7 từ giống nhau)'
        verdict = 'ĐẠT' if r['passed'] else 'CHƯA ĐẠT'
        messagebox.showinfo('Kiểm tra trùng lặp sơ bộ',
                            f'{verdict} — tỉ lệ khớp chuỗi: {r["sequence_ratio"]:.1%} '
                            f'(tối đa {self.page.max_similarity:.0%})\nCác cụm 7 từ chung:\n{detail}\n\n'
                            'Chỉ là phép đo sơ bộ, vẫn cần kiểm tra ý tưởng/cốt truyện bằng mắt.')

    def open_publish(self):
        if not self.current:
            messagebox.showwarning('Chưa chọn bài', 'Chọn bài cần đăng.')
            return
        pid, page = self.current, self.page
        with db() as c:
            d = page_data.get_draft(c, pid, page.slug)
            pub = page_data.get_published(c, pid, page.slug)
        if pub:
            messagebox.showwarning('Đã đăng', f'Bài này đã đăng lên "{page.name}": {pub["fb_post_id"]}')
            return
        if not d or d['status'] != 'approved':
            messagebox.showwarning('Chưa duyệt', 'Chỉ đăng bài đã duyệt. Bấm "Duyệt" trước.')
            return

        sent = {}

        def do_send(plan):  # chạy ở luồng phụ: chỉ gọi mạng, không chạm Tk/SQLite
            fb_id = publisher.send(plan, page.fb_page_id, page.fb_page_token, SESSION, GRAPH_VERSION)
            sent['plan'] = plan
            return fb_id

        def on_done(fb_id):
            plan = sent.get('plan')
            kind = plan.kind if plan else 'text'
            when = (datetime.datetime.fromtimestamp(plan.scheduled_ts).isoformat(timespec='minutes')
                    if plan and plan.scheduled_ts else '')
            with db() as c:
                page_data.mark_published(c, pid, page.slug, fb_id, kind, when)
            self.refresh()
            self.select_post()
            msg = f'Đã hẹn đăng lúc {when}' if when else 'Đã đăng'
            messagebox.showinfo('Thành công', f'{msg} lên "{page.name}".\nID: {fb_id}')

        PublishDialog(self.root, page, pid, self._source_text(pid), d['body'], MEDIA,
                      do_send=do_send, on_done=on_done)

    def download(self):
        if not self.current:
            messagebox.showwarning('Chọn bài', 'Chọn bài cần tải media.')
            return
        pid = self.current

        def work():
            with db() as c:
                rows = [r for r in c.execute('SELECT * FROM media WHERE post_id=?', (pid,)).fetchall()
                        if not r['local_path'] or not os.path.exists(r['local_path'])]
            ok, fails = 0, []
            for row in rows:
                try:
                    save_media(row)
                    ok += 1
                except Exception as e:
                    fails.append(f"media {row['id']}: {e}")
            self.root.after(0, self.select_post)
            return f'Tải thành công {ok}/{len(rows)} media. ' + (' | '.join(fails[:3]) if fails else '')
        self.run_async('Đang tải media...', work)

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        if not path:
            return
        with db() as c:
            rows = c.execute('''SELECT p.id, p.created_time, p.permalink_url, p.message,
                    COALESCE(d.body,'') draft, COALESCE(d.status,'') status
                    FROM posts p LEFT JOIN page_drafts d ON d.post_id=p.id AND d.page_slug=?
                    ORDER BY p.created_time DESC''', (self.page.slug,)).fetchall()
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(['id', 'created_time', 'permalink_url', 'source', 'draft', 'status'])
            for row in rows:
                w.writerow(list(row))
        self.status.set('Đã xuất ' + str(path))

    def export_txt(self):
        if not self.current:
            return
        with db() as c:
            row = page_data.get_draft(c, self.current, self.page.slug)
        if not row or row['status'] not in ('approved', 'published', 'scheduled'):
            messagebox.showwarning('Chưa duyệt', 'Chỉ xuất bản thảo đã được duyệt.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text', '*.txt')])
        if path:
            Path(path).write_text(row['body'], encoding='utf-8-sig')
            self.status.set('Đã xuất bài viết được duyệt: ' + path)


if __name__ == '__main__':
    init_db()
    with db() as _c:
        page_data.migrate(_c, DEFAULT_SLUG)
    root = Tk()
    ttk.Style().theme_use('clam')
    App(root)
    try:
        root.state('zoomed')  # mở toàn màn hình trên Windows để thấy đủ nút
    except Exception:
        pass
    root.mainloop()
