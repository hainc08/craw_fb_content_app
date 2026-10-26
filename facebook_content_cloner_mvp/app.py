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
import time
import urllib.parse
from pathlib import Path
from tkinter import Tk, Toplevel, StringVar, BooleanVar, Text, filedialog, messagebox, ttk, END

import requests
from research import analyze, create_new, similarity, test_gemini, test_cloudflare
from scraper import scrape_url, scrape_facebook_posts

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


def ai_rewrite(text, api_key):
    if not api_key.strip():
        raise ValueError('Điền OpenAI API key để tạo bản nháp AI. Bạn cũng có thể sửa tay.')
    if not text.strip():
        raise ValueError('Bài viết gốc không có caption để viết lại.')
    prompt = ("Viết một bài Facebook mới bằng tiếng Việt dựa trên CHỦ ĐỀ, không sao chép cách diễn đạt, "
              "nhân vật hay diễn biến độc đáo của nội dung nguồn. Dùng câu chuyện nguyên bản, tự nhiên, "
              "mở đầu hấp dẫn, bài học hữu ích, CTA một câu hỏi mở. Không tuyên bố trải nghiệm thật "
              "nếu đó là tình huống hư cấu. Đầu ra chỉ có bài viết. Nội dung tham khảo:\n" + text[:12000])
    r = SESSION.post('https://api.openai.com/v1/responses',
                     headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json'},
                     json={'model':'gpt-4.1-mini','input':prompt,'max_output_tokens':1300}, timeout=(10,100))
    if not r.ok:
        raise RuntimeError(f'OpenAI HTTP {r.status_code}: {r.text[:250]}')
    data = r.json()
    output = ''.join(p.get('text','') for item in data.get('output',[])
                     for p in item.get('content',[]) if p.get('type') == 'output_text')
    if not output.strip(): raise RuntimeError('OpenAI không trả nội dung.')
    return output.strip()


class App:
    def __init__(self, root):
        self.root = root
        root.title('Facebook Content Cloner & Research — Cào tự động & Sáng tạo nội dung')
        root.geometry('1380x880')
        self.target_url = StringVar()
        self.scrape_limit = StringVar(value='5')
        self.auto_download_media = BooleanVar(value=True)
        self.api_config = load_api_config()
        self.ai_provider = StringVar(value=self.api_config.get('provider', 'gemini'))
        self.status = StringVar(value=f'Sẵn sàng | Dữ liệu lưu tại: {ROOT}')
        self.current = None

        # --- KHUNG ĐIỀU KHIỂN CÀO FACEBOOK TRÊN CÙNG ---
        top_frame = ttk.LabelFrame(root, text=' 🚀 Cào bài viết & Reels từ Facebook URL ', padding=10)
        top_frame.pack(fill='x', padx=12, pady=(10, 4))

        # Dòng 1: Nhập link & Số lượng & Nút cào
        r1 = ttk.Frame(top_frame)
        r1.pack(fill='x', pady=2)

        ttk.Label(r1, text='Dán Link Facebook:', font=('Segoe UI', 9, 'bold')).pack(side='left', padx=(0, 6))
        self.url_entry = ttk.Entry(r1, textvariable=self.target_url, font=('Segoe UI', 10))
        self.url_entry.pack(side='left', fill='x', expand=True, padx=4)

        ttk.Label(r1, text='Số bài:').pack(side='left', padx=(8, 4))
        ttk.Entry(r1, textvariable=self.scrape_limit, width=6, justify='center').pack(side='left', padx=4)

        scrape_btn = ttk.Button(r1, text='⚡ CÀO BÀI & TẢI MEDIA', command=self.start_auto_scrape)
        scrape_btn.pack(side='left', padx=(8, 0))

        # Dòng 2: Tùy chọn & Thao tác phụ
        r2 = ttk.Frame(top_frame)
        r2.pack(fill='x', pady=(6, 0))

        ttk.Checkbutton(r2, text='Tự động tải Video MP4 & Hình ảnh về máy', variable=self.auto_download_media).pack(side='left', padx=(0, 15))
        ttk.Button(r2, text='📂 Mở thư mục Media', command=self.open_media_folder).pack(side='left', padx=3)
        ttk.Button(r2, text='📝 Dán nhanh thủ công', command=self.open_manual_add_dialog).pack(side='left', padx=3)
        ttk.Button(r2, text='📥 Nhập file JSON', command=self.load_json).pack(side='left', padx=3)
        ttk.Button(r2, text='📊 Xuất CSV', command=self.export).pack(side='left', padx=3)
        ttk.Button(r2, text='🔄 Làm mới danh sách', command=self.refresh).pack(side='left', padx=3)

        ttk.Label(r2, text='Hỗ trợ: Reels, Video, Post cá nhân/Fanpage, hoặc danh sách URL', foreground='gray').pack(side='right')

        # --- KHUNG CHÍNH (DANH SÁCH BÊN TRÁI & BIÊN TẬP BÊN PHẢI) ---
        mid = ttk.Panedwindow(root, orient='horizontal')
        mid.pack(fill='both', expand=True, padx=12, pady=6)

        listf = ttk.Frame(mid)
        mid.add(listf, weight=2)
        self.table = ttk.Treeview(listf, columns=('date', 'caption', 'media'), show='headings')
        for key, label, width in [('date', 'Ngày', 130), ('caption', 'Nội dung', 360), ('media', 'Media', 65)]:
            self.table.heading(key, text=label)
            self.table.column(key, width=width)
        y = ttk.Scrollbar(listf, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=y.set)
        self.table.pack(side='left', fill='both', expand=True)
        y.pack(side='right', fill='y')
        self.table.bind('<<TreeviewSelect>>', self.select_post)

        editor = ttk.Frame(mid, padding=(8, 0))
        mid.add(editor, weight=2)

        ttk.Label(editor, text='Nguồn & Media (Chỉ đọc):', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.source = Text(editor, height=8, wrap='word')
        self.source.pack(fill='both', expand=True)
        self.source.configure(state='disabled')

        ttk.Label(editor, text='Phân tích nội dung nguồn (Research & Hook & Insight):', font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 0))
        self.research = Text(editor, height=8, wrap='word')
        self.research.pack(fill='both', expand=True)

        ttk.Label(editor, text='Bản thảo mới (Kịch bản Reel / Bài viết / Caption):', font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 0))
        self.draft = Text(editor, height=12, wrap='word')
        self.draft.pack(fill='both', expand=True)

        key_box = ttk.Frame(editor)
        key_box.pack(fill='x', pady=(6, 2))
        self.ai_status_lbl = ttk.Label(key_box, text=self.get_ai_status_text(), font=('Segoe UI', 9, 'bold'), foreground='#0066cc')
        self.ai_status_lbl.pack(side='left', padx=2)
        ttk.Button(key_box, text='⚙️ Cài đặt API AI (Gemini / Cloudflare)', command=self.open_api_settings_dialog).pack(side='right', padx=2)

        actions = ttk.Frame(editor)
        actions.pack(fill='x', pady=7)
        for title, fn in [('Phân tích AI', self.analyze_post), ('Sáng tạo mới', self.create_post),
                          ('Kiểm tra trùng', self.check_similarity), ('Lưu nháp', self.save_draft),
                          ('Duyệt', self.approve), ('Xuất TXT', self.export_txt)]:
            ttk.Button(actions, text=title, command=fn).pack(side='left', padx=2)

        ttk.Label(root, textvariable=self.status, padding=8, relief='sunken').pack(fill='x')
        self.refresh()

    def get_ai_status_text(self):
        p = self.ai_provider.get()
        if p == 'gemini':
            has_k = bool(self.api_config.get('gemini_key', '').strip())
            return f"🤖 AI: Google Gemini {'[✓ Đã có Key]' if has_k else '[⚠️ Chưa nhập Key]'}"
        elif p == 'cloudflare':
            has_k = bool(self.api_config.get('cloudflare_token', '').strip())
            return f"🤖 AI: Cloudflare Workers AI {'[✓ Đã có Key]' if has_k else '[⚠️ Chưa nhập Key]'}"
        else:
            has_k = bool(self.api_config.get('openai_key', '').strip())
            return f"🤖 AI: OpenAI {'[✓ Đã có Key]' if has_k else '[⚠️ Chưa nhập Key]'}"

    def open_media_folder(self):
        try:
            os.startfile(str(MEDIA))
        except Exception:
            messagebox.showinfo('Thư mục Media', f'Đường dẫn thư mục media:\n{MEDIA}')

    def start_auto_scrape(self):
        url_input = self.target_url.get().strip()
        if not url_input:
            messagebox.showwarning('Chưa có link', 'Vui lòng dán link Facebook (Reels, Video, Post hoặc Page) vào ô trên.')
            self.url_entry.focus()
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
                self.root.after(0, lambda: messagebox.showerror('Lỗi cào dữ liệu', str(exc)))
                self.root.after(0, lambda: self.status.set(f'Lỗi cào dữ liệu: {exc}'))
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
        selected=self.current
        for item in self.table.get_children():self.table.delete(item)
        with db() as c:
            rows=c.execute('''SELECT p.id,p.message,p.created_time,COUNT(m.id) media_count
                     FROM posts p LEFT JOIN media m ON p.id=m.post_id
                     GROUP BY p.id ORDER BY p.created_time DESC''').fetchall()
        for row in rows:
            self.table.insert('',END,iid=row['id'],values=(row['created_time'][:19],row['message'].replace('\n',' ')[:65],row['media_count']))
        if selected and self.table.exists(selected):
            self.table.selection_set(selected)

    def select_post(self,event=None):
        selection=self.table.selection()
        if not selection:return
        self.current=selection[0]
        with db() as c:
            p=c.execute('SELECT * FROM posts WHERE id=?',(self.current,)).fetchone()
            d=c.execute('SELECT body,status FROM drafts WHERE post_id=?',(self.current,)).fetchone()
            a=c.execute('SELECT analysis FROM research WHERE post_id=?',(self.current,)).fetchone()
            medias=c.execute('SELECT kind, local_path, url FROM media WHERE post_id=?',(self.current,)).fetchall()

        media_lines = []
        for m in medias:
            lp = m['local_path']
            if lp and os.path.exists(lp):
                size_kb = os.path.getsize(lp) // 1024
                media_lines.append(f"  ✓ {m['kind'].upper()}: {Path(lp).name} ({size_kb} KB) -> Đã lưu tại thư mục Media")
            else:
                media_lines.append(f"  ● {m['kind'].upper()}: {m['url'][:65]}...")
        media_txt = "\n".join(media_lines) if media_lines else "  (Không có file đính kèm)"

        self.source.configure(state='normal')
        self.source.delete('1.0',END)
        self.source.insert('1.0',f"🔗 LINK: {p['permalink_url']}\n\n📁 MEDIA:\n{media_txt}\n\n📝 CAPTION GỐC:\n{p['message']}")
        self.source.configure(state='disabled')
        self.research.delete('1.0',END)
        if a:self.research.insert('1.0',a['analysis'])
        self.draft.delete('1.0',END)
        if d:self.draft.insert('1.0',d['body'])
        self.status.set(f"Bài {self.current} | Trạng thái: {d['status'] if d else 'chưa có nháp'}")

    def save_draft(self,status='review'):
        if not self.current:return
        body=self.draft.get('1.0','end-1c').strip()
        if not body:
            messagebox.showwarning('Bản nháp','Nhập nội dung mới trước.');return
        with db() as c:
            c.execute('''INSERT INTO drafts(post_id,body,status) VALUES(?,?,?)
            ON CONFLICT(post_id) DO UPDATE SET body=excluded.body,status=excluded.status,
            updated_at=CURRENT_TIMESTAMP''',(self.current,body,status))
        self.status.set('Đã lưu bản nháp: '+status)

    def approve(self):
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

    def analyze_post(self):
        if not self.current:
            messagebox.showwarning('Chưa chọn bài', 'Vui lòng chọn một bài viết trong danh sách bên trái.')
            return
        with db() as c:
            p = c.execute('SELECT message FROM posts WHERE id=?', (self.current,)).fetchone()
        if not p or not p['message'].strip():
            messagebox.showwarning('Nội dung trống', 'Bài viết này không có nội dung text để phân tích.')
            return

        pid = self.current
        provider = self.api_config.get('provider', 'gemini')

        if provider == 'gemini' and not self.api_config.get('gemini_key', '').strip():
            messagebox.showwarning('Thiếu Gemini Key', 'Bạn chưa nhập Gemini API Key. Hãy bấm nút [⚙️ Cài đặt API] để điền key.')
            self.open_api_settings_dialog()
            return
        elif provider == 'cloudflare' and (not self.api_config.get('cloudflare_token', '').strip() or not self.api_config.get('cloudflare_account_id', '').strip()):
            messagebox.showwarning('Thiếu Cloudflare Key', 'Bạn chưa nhập Cloudflare Account ID hoặc API Token. Hãy bấm nút [⚙️ Cài đặt API].')
            self.open_api_settings_dialog()
            return

        def work():
            result = analyze(p['message'], provider, self.api_config)
            with db() as c:
                c.execute('INSERT INTO research(post_id,analysis) VALUES(?,?) ON CONFLICT(post_id) DO UPDATE SET analysis=excluded.analysis,updated_at=CURRENT_TIMESTAMP', (pid, result))
            def update():
                if self.current == pid:
                    self.research.delete('1.0', END)
                    self.research.insert('1.0', result)
            self.root.after(0, update)
            return f'Đã nghiên cứu nội dung bằng {provider.upper()}. Bấm "Sáng tạo mới" để tạo bài viết / kịch bản Reel.'

        self.run_async(f'AI ({provider.upper()}) đang phân tích nội dung...', work)

    def create_post(self):
        if not self.current:
            messagebox.showwarning('Chưa chọn bài', 'Vui lòng chọn một bài viết trong danh sách bên trái.')
            return
        with db() as c:
            p = c.execute('SELECT message FROM posts WHERE id=?', (self.current,)).fetchone()
        if not p or not p['message'].strip():
            messagebox.showwarning('Nội dung trống', 'Bài viết này không có nội dung để sáng tạo.')
            return

        pid = self.current
        analysis = self.research.get('1.0', 'end-1c').strip()
        provider = self.api_config.get('provider', 'gemini')

        if provider == 'gemini' and not self.api_config.get('gemini_key', '').strip():
            messagebox.showwarning('Thiếu Gemini Key', 'Bạn chưa nhập Gemini API Key. Hãy bấm nút [⚙️ Cài đặt API] để điền key.')
            self.open_api_settings_dialog()
            return
        elif provider == 'cloudflare' and (not self.api_config.get('cloudflare_token', '').strip() or not self.api_config.get('cloudflare_account_id', '').strip()):
            messagebox.showwarning('Thiếu Cloudflare Key', 'Bạn chưa nhập Cloudflare Account ID hoặc API Token. Hãy bấm nút [⚙️ Cài đặt API].')
            self.open_api_settings_dialog()
            return

        def work():
            result = create_new(p['message'], analysis, provider, self.api_config)
            check = similarity(p['message'], result)
            def update():
                if self.current == pid:
                    self.draft.delete('1.0', END)
                    self.draft.insert('1.0', result)
            self.root.after(0, update)
            return f'Đã sáng tạo nội dung mới ({provider.upper()}); tỷ lệ tương đồng chuỗi: {check["sequence_ratio"]:.1%}.'

        self.run_async(f'AI ({provider.upper()}) đang sáng tạo nội dung mới...', work)

    def check_similarity(self):
        if not self.current:return
        with db() as c:p=c.execute('SELECT message FROM posts WHERE id=?',(self.current,)).fetchone()
        result=similarity(p['message'],self.draft.get('1.0','end-1c'))
        detail='\n'.join(result['shared_phrases']) or '(không phát hiện cụm 7 từ giống nhau)'
        messagebox.showinfo('Kiểm tra trùng lặp sơ bộ',f'Tỉ lệ khớp chuỗi: {result["sequence_ratio"]:.1%}\nCác cụm 7 từ chung:\n{detail}\n\nChỉ là phép đo sơ bộ, vẫn cần kiểm tra ý tưởng/cốt truyện bằng mắt.')

    def rewrite(self):
        if not self.current:return
        with db() as c:p=c.execute('SELECT message FROM posts WHERE id=?',(self.current,)).fetchone()
        pid=self.current;key=self.openai.get().strip()
        def work():
            body=ai_rewrite(p['message'],key)
            def update():
                if self.current==pid:
                    self.draft.delete('1.0',END);self.draft.insert('1.0',body)
                self.status.set('AI đã tạo bản nháp. Hãy kiểm tra và lưu/duyệt.')
            self.root.after(0,update)
            return 'Đã tạo bản thảo'
        self.run_async('AI đang soạn...',work)

    def download(self):
        if not self.current:
            messagebox.showwarning('Chọn bài','Chọn bài cần tải media.');return
        pid=self.current
        def work():
            with db() as c:
                rows=c.execute('SELECT * FROM media WHERE post_id=? AND local_path=""',(pid,)).fetchall()
            ok=0;fails=[]
            for row in rows:
                try: save_media(row);ok+=1
                except Exception as e: fails.append(f"media {row['id']}: {e}")
            return f'Tải thành công {ok}/{len(rows)} media. '+(' | '.join(fails[:3]) if fails else '')
        self.run_async('Đang tải media được phép...',work)

    def export(self):
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        with db() as c:
            rows=c.execute('''SELECT p.id,p.created_time,p.permalink_url,p.message,
                    COALESCE(d.body,'') draft, COALESCE(d.status,'') status
                    FROM posts p LEFT JOIN drafts d ON d.post_id=p.id ORDER BY p.created_time DESC''').fetchall()
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['id','created_time','permalink_url','source','draft','status'])
            for row in rows:w.writerow(list(row))
        self.status.set('Đã xuất '+str(path))

    def export_txt(self):
        if not self.current:return
        with db() as c:
            row=c.execute('SELECT body,status FROM drafts WHERE post_id=?',(self.current,)).fetchone()
        if not row or row['status']!='approved':
            messagebox.showwarning('Chưa duyệt','Chỉ xuất bản thảo đã được duyệt.');return
        path=filedialog.asksaveasfilename(defaultextension='.txt',filetypes=[('Text','*.txt')])
        if path:
            Path(path).write_text(row['body'],encoding='utf-8-sig')
            self.status.set('Đã xuất bài viết được duyệt: '+path)


if __name__=='__main__':
    init_db()
    root=Tk()
    ttk.Style().theme_use('clam')
    App(root)
    root.mainloop()
