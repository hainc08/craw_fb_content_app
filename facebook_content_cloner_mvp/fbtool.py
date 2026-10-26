"""CLI cho Facebook Content Cloner — dùng chung DB, scraper, AI và hồ sơ Page với GUI.

Cờ --page <slug> đặt TRƯỚC lệnh con; bỏ trống = Page đang chọn trong GUI.
  py -3 fbtool.py pages
  py -3 fbtool.py --page meo-van-phong page-show
  py -3 fbtool.py scrape "https://www.facebook.com/somepage" --limit 5
  py -3 fbtool.py list [--status none|review|approved|published|scheduled]
  py -3 fbtool.py show <post_id>
  py -3 fbtool.py analyze <post_id>
  py -3 fbtool.py save-draft <post_id> --file draft.txt
  py -3 fbtool.py check <post_id>
  py -3 fbtool.py approve <post_id>
  py -3 fbtool.py page-info
  py -3 fbtool.py publish <post_id> [--image anh.jpg | --video clip.mp4] [--schedule 2026-10-27T20:00] [--yes]
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app  # noqa: E402  (tạo thư mục dữ liệu, không mở cửa sổ)
import page_data  # noqa: E402
import publisher  # noqa: E402
from pages import DEFAULT_SLUG, PageStore  # noqa: E402
from research import analyze, create_new, render_prompt  # noqa: E402
from scraper import scrape_facebook_posts  # noqa: E402


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def fail(msg, code=1):
    print(f'LỖI: {msg}', file=sys.stderr)
    sys.exit(code)


class Ctx:
    def __init__(self, page_slug):
        self.store = PageStore(app.ROOT / 'pages.json', legacy=app.load_api_config())
        try:
            self.page = self.store.get(page_slug) if page_slug else self.store.active()
        except KeyError:
            fail(f'Không có Page "{page_slug}". Chạy "pages" để xem danh sách.')
        app.init_db()
        self.conn = app.db()
        page_data.migrate(self.conn, DEFAULT_SLUG)

    @property
    def slug(self):
        return self.page.slug

    def prompts(self):
        p = self.page
        return (render_prompt(p.analysis_prompt, p.name, p.hashtags),
                render_prompt(p.creation_prompt, p.name, p.hashtags))

    def provider(self):
        cfg = app.load_api_config()
        return self.page.provider or cfg.get('provider', 'gemini'), cfg

    def post(self, pid):
        p = self.conn.execute('SELECT * FROM posts WHERE id=?', (pid,)).fetchone()
        if not p:
            fail(f'Không có bài {pid}. Chạy "list" để xem ID.')
        return p

    def draft(self, pid):
        d = page_data.get_draft(self.conn, pid, self.slug)
        if not d:
            fail(f'Bài {pid} chưa có nháp cho Page "{self.page.name}".')
        return d


# ---------- lệnh ----------

def cmd_pages(c, a):
    out([{**p.public_dict(), 'active': p.slug == c.store.active().slug} for p in c.store.list()])


def cmd_page_show(c, a):
    analysis, creation = c.prompts()
    out({**c.page.public_dict(), 'analysis_prompt': analysis, 'creation_prompt': creation})


def cmd_scrape(c, a):
    posts = scrape_facebook_posts('\n'.join(a.urls), max_count=a.limit,
                                  progress_callback=lambda t: print(t, file=sys.stderr))
    saved = []
    for post in posts:
        if not app.insert_post(post):
            continue
        media_ok = 0
        if not a.no_media:
            rows = c.conn.execute('SELECT * FROM media WHERE post_id=? AND local_path=""', (post['id'],)).fetchall()
            for row in rows:
                try:
                    app.save_media(row)
                    media_ok += 1
                except Exception as e:
                    print(f'  media lỗi ({post["id"]}): {e}', file=sys.stderr)
        saved.append({'id': post['id'], 'chars': len(post.get('message') or ''),
                      'preview': (post.get('message') or '').replace('\n', ' ')[:120],
                      'url': post.get('permalink_url'), 'media_downloaded': media_ok})
    out({'scraped': len(posts), 'saved': len(saved), 'posts': saved})


def cmd_list(c, a):
    rows = page_data.list_posts(c.conn, c.slug, a.status, a.limit)
    out([{'id': r['id'], 'status': r['status'] or 'chưa có nháp', 'analyzed': bool(r['analyzed']),
          'published': r['fb_post_id'], 'media': r['media_count'], 'chars': len(r['message']),
          'preview': r['message'].replace('\n', ' ')[:100]} for r in rows])


def cmd_show(c, a):
    p = c.post(a.id)
    m = c.conn.execute('SELECT kind, local_path FROM media WHERE post_id=?', (a.id,)).fetchall()
    d = page_data.get_draft(c.conn, a.id, c.slug)
    out({'id': p['id'], 'page': c.page.name, 'url': p['permalink_url'], 'created_time': p['created_time'],
         'source': p['message'], 'media': [{'kind': x['kind'], 'local_path': x['local_path']} for x in m],
         'analysis': page_data.get_analysis(c.conn, a.id, c.slug),
         'draft': d['body'] if d else None, 'draft_status': d['status'] if d else None})


def cmd_analyze(c, a):
    p = c.post(a.id)
    provider, keys = c.provider()
    text = analyze(p['message'], a.provider or provider, keys, instruction=c.prompts()[0])
    page_data.save_analysis(c.conn, a.id, c.slug, text)
    print(text)


def cmd_create(c, a):
    p = c.post(a.id)
    provider, keys = c.provider()
    analysis = page_data.get_analysis(c.conn, a.id, c.slug) or ''
    print(create_new(p['message'], analysis, a.provider or provider, keys, instruction=c.prompts()[1]))


def cmd_save_draft(c, a):
    p = c.post(a.id)
    body = Path(a.file).read_text(encoding='utf-8-sig').strip()
    if not body:
        fail('File nháp rỗng.')
    page_data.save_draft(c.conn, a.id, c.slug, body, 'review')
    out({'saved': a.id, 'page': c.page.name, 'status': 'review',
         'check': publisher.check_originality(p['message'], body, c.page.max_similarity)})


def cmd_check(c, a):
    p = c.post(a.id)
    r = publisher.check_originality(p['message'], c.draft(a.id)['body'], c.page.max_similarity)
    out(r)
    sys.exit(0 if r['passed'] else 2)


def cmd_approve(c, a):
    p = c.post(a.id)
    d = c.draft(a.id)
    r = publisher.check_originality(p['message'], d['body'], c.page.max_similarity)
    if not r['passed']:
        out(r)
        fail('Nháp còn quá giống bài nguồn — viết lại rồi mới duyệt.', 2)
    page_data.save_draft(c.conn, a.id, c.slug, d['body'], 'approved')
    out({'approved': a.id, 'page': c.page.name, 'check': r})


def creds(c):
    if not c.page.fb_page_id or not c.page.fb_page_token:
        fail(f'Page "{c.page.name}" chưa có Facebook Page ID / token. Cấu hình trong GUI → '
             f'"Quản lý Page" hoặc file {app.ROOT / "pages.json"}.')
    return c.page.fb_page_id, c.page.fb_page_token


def cmd_page_info(c, a):
    pid, tok = creds(c)
    out(app.graph_get(f'https://graph.facebook.com/{app.GRAPH_VERSION}/{pid}', tok,
                      {'fields': 'id,name,fan_count,link'}))


def cmd_publish(c, a):
    p = c.post(a.id)
    d = c.draft(a.id)
    if d['status'] != 'approved':
        fail('Chỉ đăng nháp đã duyệt (chạy "approve" trước).')
    done = page_data.get_published(c.conn, a.id, c.slug)
    if done:
        fail(f'Bài này đã đăng lên "{c.page.name}": {done["fb_post_id"]}')
    text = Path(a.text_file).read_text(encoding='utf-8-sig') if a.text_file else d['body']
    try:
        plan = publisher.prepare(p['message'], text, c.page.max_similarity, a.image or a.video,
                                 app.MEDIA, a.schedule, i_own_media=a.i_own_media)
    except publisher.PublishError as e:
        fail(str(e), 2)
    summary = {'page': c.page.name, 'post_id': a.id, 'kind': plan.kind,
               'media': str(plan.media_path) if plan.media_path else None, 'schedule': a.schedule,
               'chars': len(plan.text), 'text': plan.text}
    if not a.yes:
        out({'dry_run': True, **summary, 'note': 'Thêm --yes để đăng thật.'})
        return
    pid, tok = creds(c)
    fb_id = publisher.send(plan, pid, tok, app.SESSION, app.GRAPH_VERSION)
    page_data.mark_published(c.conn, a.id, c.slug, fb_id, plan.kind, a.schedule or '')
    out({'published': True, **summary, 'fb_post_id': fb_id, 'url': f'https://www.facebook.com/{fb_id}'})


def build_parser():
    ap = argparse.ArgumentParser(description='Facebook Content Cloner CLI')
    ap.add_argument('--page', help='slug của Page (xem lệnh "pages"); mặc định Page đang chọn')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('pages', help='Danh sách Page (không in token)').set_defaults(fn=cmd_pages)
    sub.add_parser('page-show', help='Cấu hình + prompt của Page').set_defaults(fn=cmd_page_show)
    sub.add_parser('page-info', help='Kiểm tra token Page qua Graph API').set_defaults(fn=cmd_page_info)

    s = sub.add_parser('scrape', help='Cào bài công khai từ URL Page/Reel/Post vào DB')
    s.add_argument('urls', nargs='+')
    s.add_argument('--limit', type=int, default=5)
    s.add_argument('--no-media', action='store_true', help='Không tải ảnh/video về máy')
    s.set_defaults(fn=cmd_scrape)

    s = sub.add_parser('list', help='Liệt kê bài và trạng thái theo Page')
    s.add_argument('--limit', type=int, default=30)
    s.add_argument('--status', choices=['none', 'review', 'approved', 'published', 'scheduled'])
    s.set_defaults(fn=cmd_list)

    for name, fn, h in [('show', cmd_show, 'Xem nguồn, phân tích, nháp'),
                        ('check', cmd_check, 'Kiểm tra trùng lặp nháp với nguồn'),
                        ('approve', cmd_approve, 'Duyệt nháp (phải qua kiểm tra trùng)')]:
        s = sub.add_parser(name, help=h)
        s.add_argument('id')
        s.set_defaults(fn=fn)

    for name, fn, h in [('analyze', cmd_analyze, 'Phân tích bài nguồn bằng prompt của Page'),
                        ('create', cmd_create, 'Viết bài mới bằng prompt của Page (in ra, không lưu)')]:
        s = sub.add_parser(name, help=h)
        s.add_argument('id')
        s.add_argument('--provider', choices=['gemini', 'cloudflare', 'openai'])
        s.set_defaults(fn=fn)

    s = sub.add_parser('save-draft', help='Lưu nháp từ file (trạng thái review)')
    s.add_argument('id')
    s.add_argument('--file', required=True)
    s.set_defaults(fn=cmd_save_draft)

    s = sub.add_parser('publish', help='Đăng nháp đã duyệt lên Page (mặc định chạy thử)')
    s.add_argument('id')
    g = s.add_mutually_exclusive_group()
    g.add_argument('--image')
    g.add_argument('--video')
    s.add_argument('--text-file', help='Đăng nội dung trong file thay vì nháp')
    s.add_argument('--schedule', help='Giờ hẹn ISO, mặc định giờ VN, vd 2026-10-27T20:00')
    s.add_argument('--i-own-media', action='store_true')
    s.add_argument('--yes', action='store_true', help='Đăng thật')
    s.set_defaults(fn=cmd_publish)
    return ap


def main():
    a = build_parser().parse_args()
    c = Ctx(a.page)
    try:
        a.fn(c, a)
    except SystemExit:
        raise
    except Exception as e:
        fail(str(e))


if __name__ == '__main__':
    main()
