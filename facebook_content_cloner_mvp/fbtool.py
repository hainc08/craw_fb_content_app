"""CLI cho Facebook Content Cloner — dùng lại DB, scraper và AI của app.py, không mở GUI.

Ví dụ:
  py -3 fbtool.py scrape "https://www.facebook.com/somepage" --limit 5
  py -3 fbtool.py list
  py -3 fbtool.py show <post_id>
  py -3 fbtool.py analyze <post_id>
  py -3 fbtool.py save-draft <post_id> --file draft.txt
  py -3 fbtool.py check <post_id>
  py -3 fbtool.py approve <post_id>
  py -3 fbtool.py page-info
  py -3 fbtool.py publish <post_id> [--image anh.jpg | --video clip.mp4] [--schedule 2026-10-27T20:00] [--yes]
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app  # noqa: E402  (tạo thư mục dữ liệu, không mở cửa sổ)
from research import analyze, create_new, similarity  # noqa: E402
from scraper import scrape_facebook_posts  # noqa: E402

# Ngưỡng chống sao chép: bản mới phải khác bài nguồn rõ rệt.
MAX_SEQUENCE_RATIO = 0.35
MAX_SHARED_PHRASES = 0  # không được trùng cụm 7 từ nào
TEMPLATE_MARKERS = ('KỊCH BẢN REEL', 'TIÊU ĐỀ:', 'HOOK:', 'CAPTION FACEBOOK:')


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def fail(msg, code=1):
    print(f'LỖI: {msg}', file=sys.stderr)
    sys.exit(code)


def init_extra_tables():
    app.init_db()
    with app.db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS published (
            post_id TEXT PRIMARY KEY, fb_post_id TEXT NOT NULL, kind TEXT NOT NULL,
            scheduled_time TEXT DEFAULT '', published_at TEXT DEFAULT CURRENT_TIMESTAMP)''')


def get_post(pid):
    with app.db() as c:
        p = c.execute('SELECT * FROM posts WHERE id=?', (pid,)).fetchone()
    if not p:
        fail(f'Không có bài {pid}. Chạy "list" để xem ID.')
    return p


def get_draft(pid):
    with app.db() as c:
        return c.execute('SELECT body,status FROM drafts WHERE post_id=?', (pid,)).fetchone()


def ai_keys():
    cfg = app.load_api_config()
    return cfg.get('provider', 'gemini'), cfg


def check_result(source, body):
    r = similarity(source, body)
    r['passed'] = r['sequence_ratio'] <= MAX_SEQUENCE_RATIO and len(r['shared_phrases']) <= MAX_SHARED_PHRASES
    r['limits'] = {'max_sequence_ratio': MAX_SEQUENCE_RATIO, 'max_shared_7gram_phrases': MAX_SHARED_PHRASES}
    return r


# ---------- lệnh ----------

def cmd_scrape(a):
    urls = '\n'.join(a.urls)
    posts = scrape_facebook_posts(urls, max_count=a.limit, progress_callback=lambda t: print(t, file=sys.stderr))
    saved = []
    for post in posts:
        if not app.insert_post(post):
            continue
        media_ok = 0
        if not a.no_media:
            with app.db() as c:
                rows = c.execute('SELECT * FROM media WHERE post_id=? AND local_path=""', (post['id'],)).fetchall()
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


def cmd_list(a):
    q = '''SELECT p.id, p.created_time, p.message, COALESCE(d.status,'') status,
                  (SELECT COUNT(*) FROM research r WHERE r.post_id=p.id) analyzed,
                  (SELECT fb_post_id FROM published x WHERE x.post_id=p.id) fb_post_id
           FROM posts p LEFT JOIN drafts d ON d.post_id=p.id'''
    args = []
    if a.status:
        q += ' WHERE COALESCE(d.status,"") = ?'
        args.append('' if a.status == 'none' else a.status)
    q += ' ORDER BY p.imported_at DESC LIMIT ?'
    args.append(a.limit)
    with app.db() as c:
        rows = c.execute(q, args).fetchall()
    out([{'id': r['id'], 'status': r['status'] or 'chưa có nháp', 'analyzed': bool(r['analyzed']),
          'published': r['fb_post_id'], 'chars': len(r['message']),
          'preview': r['message'].replace('\n', ' ')[:100]} for r in rows])


def cmd_show(a):
    p = get_post(a.id)
    with app.db() as c:
        r = c.execute('SELECT analysis FROM research WHERE post_id=?', (a.id,)).fetchone()
        m = c.execute('SELECT kind,local_path,url FROM media WHERE post_id=?', (a.id,)).fetchall()
    d = get_draft(a.id)
    out({'id': p['id'], 'url': p['permalink_url'], 'created_time': p['created_time'],
         'source': p['message'], 'media': [{'kind': x['kind'], 'local_path': x['local_path']} for x in m],
         'analysis': r['analysis'] if r else None,
         'draft': d['body'] if d else None, 'draft_status': d['status'] if d else None})


def cmd_analyze(a):
    p = get_post(a.id)
    provider, keys = ai_keys()
    text = analyze(p['message'], a.provider or provider, keys)
    with app.db() as c:
        c.execute('''INSERT INTO research(post_id,analysis) VALUES(?,?) ON CONFLICT(post_id)
                     DO UPDATE SET analysis=excluded.analysis, updated_at=CURRENT_TIMESTAMP''', (a.id, text))
    print(text)


def cmd_create(a):
    p = get_post(a.id)
    with app.db() as c:
        r = c.execute('SELECT analysis FROM research WHERE post_id=?', (a.id,)).fetchone()
    provider, keys = ai_keys()
    text = create_new(p['message'], r['analysis'] if r else '', a.provider or provider, keys)
    print(text)


def save(pid, body, status):
    with app.db() as c:
        c.execute('''INSERT INTO drafts(post_id,body,status) VALUES(?,?,?) ON CONFLICT(post_id)
                     DO UPDATE SET body=excluded.body, status=excluded.status, updated_at=CURRENT_TIMESTAMP''',
                  (pid, body, status))


def cmd_save_draft(a):
    p = get_post(a.id)
    body = Path(a.file).read_text(encoding='utf-8-sig').strip()
    if not body:
        fail('File nháp rỗng.')
    save(a.id, body, 'review')
    out({'saved': a.id, 'status': 'review', 'check': check_result(p['message'], body)})


def cmd_check(a):
    p = get_post(a.id)
    d = get_draft(a.id)
    if not d:
        fail('Bài này chưa có nháp.')
    r = check_result(p['message'], d['body'])
    out(r)
    sys.exit(0 if r['passed'] else 2)


def cmd_approve(a):
    p = get_post(a.id)
    d = get_draft(a.id)
    if not d:
        fail('Bài này chưa có nháp.')
    r = check_result(p['message'], d['body'])
    if not r['passed']:
        out(r)
        fail('Nháp còn quá giống bài nguồn — viết lại rồi mới duyệt.', 2)
    save(a.id, d['body'], 'approved')
    out({'approved': a.id, 'check': r})


def page_creds():
    cfg = app.load_api_config()
    pid = os.environ.get('FB_PAGE_ID') or cfg.get('fb_page_id', '')
    tok = os.environ.get('FB_PAGE_TOKEN') or cfg.get('fb_page_token', '')
    if not pid or not tok:
        fail('Thiếu FB_PAGE_ID / FB_PAGE_TOKEN (biến môi trường hoặc khóa fb_page_id, fb_page_token '
             f'trong {app.CONFIG_FILE}).')
    return pid.strip(), tok.strip()


def graph_post(url, token, data, files=None):
    r = app.SESSION.post(url, headers={'Authorization': f'Bearer {token}'}, data=data, files=files,
                         timeout=(10, 600))
    if not r.ok:
        raise RuntimeError(app.friendly_error(r))
    return r.json()


def cmd_page_info(a):
    pid, tok = page_creds()
    info = app.graph_get(f'https://graph.facebook.com/{app.GRAPH_VERSION}/{pid}', tok,
                         {'fields': 'id,name,fan_count,link'})
    out(info)


def cmd_publish(a):
    p = get_post(a.id)
    d = get_draft(a.id)
    if not d or d['status'] not in ('approved',):
        fail('Chỉ đăng nháp đã duyệt (chạy "approve" trước).')
    with app.db() as c:
        done = c.execute('SELECT fb_post_id FROM published WHERE post_id=?', (a.id,)).fetchone()
    if done:
        fail(f'Bài này đã đăng rồi: {done["fb_post_id"]}')

    text = Path(a.text_file).read_text(encoding='utf-8-sig').strip() if a.text_file else d['body']
    if any(m in text for m in TEMPLATE_MARKERS):
        fail('Nội dung còn các mục khung (TIÊU ĐỀ:/HOOK:/KỊCH BẢN REEL...). Lưu bản sạch sẵn sàng đăng '
             'bằng save-draft hoặc truyền --text-file.')
    r = check_result(p['message'], text)
    if not r['passed']:
        out(r)
        fail('Nội dung đăng quá giống bài nguồn.', 2)

    media = a.image or a.video
    if media:
        mp = Path(media).resolve()
        if not mp.is_file():
            fail(f'Không thấy file {mp}')
        if app.MEDIA.resolve() in mp.parents and not a.i_own_media:
            fail('File này là media cào từ bài người khác — không đăng lại. Dùng ảnh/video tự tạo '
                 '(hoặc thêm --i-own-media nếu bạn có quyền).')

    sched_ts = None
    if a.schedule:
        dt = datetime.datetime.fromisoformat(a.schedule)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=7)))  # giờ Việt Nam
        sched_ts = int(dt.timestamp())
        delta = sched_ts - datetime.datetime.now(datetime.timezone.utc).timestamp()
        if not (600 <= delta <= 30 * 86400):
            fail('Giờ hẹn phải cách hiện tại từ 10 phút đến 30 ngày.')

    kind = 'video' if a.video else 'photo' if a.image else 'text'
    plan = {'post_id': a.id, 'kind': kind, 'media': media, 'schedule': a.schedule,
            'chars': len(text), 'text': text}
    if not a.yes:
        out({'dry_run': True, **plan, 'note': 'Thêm --yes để đăng thật.'})
        return

    pid, tok = page_creds()
    base = f'https://graph.facebook.com/{app.GRAPH_VERSION}/{pid}'
    data = {}
    if sched_ts:
        data.update({'published': 'false', 'scheduled_publish_time': str(sched_ts)})
    if kind == 'text':
        res = graph_post(f'{base}/feed', tok, {'message': text, **data})
    elif kind == 'photo':
        with open(media, 'rb') as f:
            res = graph_post(f'{base}/photos', tok, {'caption': text, **data}, files={'source': f})
    else:
        url = f'https://graph-video.facebook.com/{app.GRAPH_VERSION}/{pid}/videos'
        with open(media, 'rb') as f:
            res = graph_post(url, tok, {'description': text, **data}, files={'source': f})
    fb_id = res.get('post_id') or res.get('id')
    with app.db() as c:
        c.execute('INSERT INTO published(post_id,fb_post_id,kind,scheduled_time) VALUES(?,?,?,?)',
                  (a.id, fb_id, kind, a.schedule or ''))
        c.execute('UPDATE drafts SET status=?, updated_at=CURRENT_TIMESTAMP WHERE post_id=?',
                  ('scheduled' if sched_ts else 'published', a.id))
    out({'published': True, 'fb_post_id': fb_id, 'kind': kind, 'scheduled': a.schedule,
         'url': f'https://www.facebook.com/{fb_id}'})


def main():
    ap = argparse.ArgumentParser(description='Facebook Content Cloner CLI')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('scrape', help='Cào bài công khai từ URL Page/Reel/Post vào DB')
    s.add_argument('urls', nargs='+')
    s.add_argument('--limit', type=int, default=5)
    s.add_argument('--no-media', action='store_true', help='Không tải ảnh/video về máy')
    s.set_defaults(fn=cmd_scrape)

    s = sub.add_parser('list', help='Liệt kê bài trong DB')
    s.add_argument('--limit', type=int, default=30)
    s.add_argument('--status', choices=['none', 'review', 'approved', 'published', 'scheduled'])
    s.set_defaults(fn=cmd_list)

    for name, fn, h in [('show', cmd_show, 'Xem nguồn, phân tích, nháp'),
                        ('check', cmd_check, 'Kiểm tra trùng lặp nháp với nguồn'),
                        ('approve', cmd_approve, 'Duyệt nháp (phải qua kiểm tra trùng)')]:
        s = sub.add_parser(name, help=h)
        s.add_argument('id')
        s.set_defaults(fn=fn)

    for name, fn, h in [('analyze', cmd_analyze, 'Phân tích bài nguồn bằng AI của app'),
                        ('create', cmd_create, 'Sáng tạo bài mới bằng AI của app (in ra, không lưu)')]:
        s = sub.add_parser(name, help=h)
        s.add_argument('id')
        s.add_argument('--provider', choices=['gemini', 'cloudflare', 'openai'])
        s.set_defaults(fn=fn)

    s = sub.add_parser('save-draft', help='Lưu nháp từ file (trạng thái review)')
    s.add_argument('id')
    s.add_argument('--file', required=True)
    s.set_defaults(fn=cmd_save_draft)

    s = sub.add_parser('page-info', help='Kiểm tra token Page')
    s.set_defaults(fn=cmd_page_info)

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

    a = ap.parse_args()
    init_extra_tables()
    try:
        a.fn(a)
    except SystemExit:
        raise
    except Exception as e:
        fail(str(e))


if __name__ == '__main__':
    main()
