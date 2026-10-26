"""Facebook content scraper module for Reels, Videos, and Posts via public URLs.
Supports Playwright for full page timeline scraping and yt-dlp for video/reels stream extraction.
"""
import datetime
import hashlib
import logging
import re
import time
import urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
}


def clean_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ''
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url
    return url


def is_facebook_page_url(url: str) -> bool:
    """Check if URL points to a Fanpage or Profile timeline instead of a single post/reel."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip('/')
    if not path:
        return False
    non_page_indicators = ['reel', 'videos', 'posts', 'watch', 'share', 'permalink.php', 'story.php', 'photo']
    parts = path.split('/')
    if any(p in non_page_indicators for p in parts):
        return False
    if 'profile.php' in path and ('story_fbid' in parsed.query or 'v=' in parsed.query):
        return False
    return True


def extract_post_id_from_url(url: str) -> str:
    """Generate a clean identifier from Facebook URL or timestamp."""
    patterns = [
        r'/reel/(\d+)',
        r'/videos/(\d+)',
        r'v=(\d+)',
        r'/posts/(\d+)',
        r'story_fbid=([^&]+)',
        r'/share/[rp]/([^/?]+)',
        r'/share/([^/?]+)',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1).replace('/', '_')
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', url.replace('https://', '').replace('http://', ''))
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"fb_{sanitized[:30]}_{ts}"


def _is_truncated(text: str) -> bool:
    return text.rstrip().endswith(('...', '…'))


def _caption_from_title(title: str) -> str:
    """'2K views · 33 reactions | <caption> | <tên page>' → '<caption>'."""
    parts = title.split(' | ')
    if len(parts) >= 3 and re.search(r'(views|lượt xem|reactions|cảm xúc)', parts[0], re.IGNORECASE):
        return ' | '.join(parts[1:-1]).strip()
    return ''


def pick_video_with_audio(formats: list[dict]) -> str | None:
    """Chọn file MP4 có cả hình lẫn tiếng.

    Facebook trả luồng hình và tiếng tách riêng (DASH, acodec='none' hoặc vcodec='none') cùng bản ghép sẵn
    'hd'/'sd'. Ưu tiên hd → sd → định dạng ghép sẵn khác; chỉ dùng luồng chỉ-có-hình khi không còn gì khác.
    """
    ok = [f for f in formats if str(f.get('url', '')).startswith('https://')]
    by_id = {f.get('format_id'): f for f in ok}
    for fid in ('hd', 'sd'):
        if fid in by_id:
            return by_id[fid]['url']
    muxed = [f for f in ok if f.get('vcodec') not in (None, 'none') and f.get('acodec') not in (None, 'none')]
    if muxed:
        return muxed[-1]['url']
    video_only = [f for f in ok if f.get('vcodec') not in (None, 'none')]
    return video_only[-1]['url'] if video_only else None


def parse_ytdlp_info(info: dict, fallback_url: str = '') -> dict:
    """Convert a yt-dlp extracted dict into standard post format."""
    post_id = str(info.get('id') or extract_post_id_from_url(fallback_url or info.get('webpage_url', '')))
    
    title = (info.get('title') or '').strip()
    description = (info.get('description') or '').strip()
    
    # Với Facebook, title thường là "8.2K views · 71 reactions | <caption> | <tên page>": cùng caption.
    # Facebook đôi khi cắt description ("…đều in..."); khi đó lấy caption trong title nếu đầy đủ hơn.
    message = description or title or ''
    if description and _is_truncated(description):
        from_title = _caption_from_title(title)
        if len(from_title) > len(description.rstrip('.… ')) and not _is_truncated(from_title):
            message = from_title

    upload_date = info.get('upload_date')
    if upload_date and len(upload_date) == 8:
        created_time = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00"
    elif info.get('timestamp'):
        created_time = datetime.datetime.fromtimestamp(info['timestamp']).isoformat()
    else:
        created_time = datetime.datetime.now().isoformat()

    attachments_data = []
    video_url = info.get('url') or pick_video_with_audio(info.get('formats') or [])

    thumbnail = info.get('thumbnail')
    media_item = {}
    if thumbnail and thumbnail.startswith('https://'):
        media_item['image'] = {'src': thumbnail}
    if video_url and video_url.startswith('https://'):
        media_item['source'] = video_url

    if media_item:
        attachments_data.append({'media': media_item})

    return {
        'id': post_id,
        'message': message,
        'created_time': created_time,
        'permalink_url': info.get('webpage_url') or fallback_url,
        'attachments': {'data': attachments_data},
        'source_type': 'yt-dlp',
    }


def scrape_via_ytdlp(url: str, max_count: int = 1) -> list[dict]:
    """Extract metadata using yt-dlp for Reels and Videos."""
    import yt_dlp

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'playlistend': max_count,
        'socket_timeout': 20,
    }

    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError('yt-dlp không trích xuất được thông tin.')

        if 'entries' in info and info['entries'] is not None:
            entries = list(info['entries'])[:max_count]
            for entry in entries:
                if not entry:
                    continue
                entry_url = entry.get('url') or entry.get('webpage_url')
                results.append(parse_ytdlp_info(entry, entry_url or url))
        else:
            results.append(parse_ytdlp_info(info, url))

    return results


PERMALINK_KEYS = ('/reel/', '/videos/', '/posts/', '/photos/', '/photo/', 'story_fbid', '/permalink/', 'fbid=')
KEEP_QUERY_KEYS = ('story_fbid', 'fbid', 'id', 'v', 'set')
HEADER_NOISE = {'·', 'Đủ điều kiện nhận tiền hoa hồng', 'Eligible for commission', 'Theo dõi', 'Follow',
                'Đã chỉnh sửa', 'Edited', 'Vừa xong', 'Just now', 'Được tài trợ', 'Sponsored'}
UI_NOISE = {'Thích', 'Like', 'Bình luận', 'Comment', 'Chia sẻ', 'Share', 'Gửi', 'Send', 'Ẩn bớt', 'See less',
            'Xem thêm', 'See more', 'Viết bình luận...', 'Viết bình luận công khai...', 'Phù hợp nhất',
            'Most relevant', 'Theo dõi', 'Đã theo dõi', 'Tin nhắn'}
FOOTER_START = ('Tất cả cảm xúc', 'All reactions')
TIME_RE = re.compile(r'^(\d+\s*(giây|phút|giờ|ngày|tuần|tháng|năm|s|m|h|d|w|y)(\s*trước)?|Hôm qua.*|Yesterday.*|'
                     r'\d{1,2}\s+tháng\s+\d{1,2}.*|Tháng\s+\d{1,2}.*)$', re.IGNORECASE)
MIN_IMAGE_PX = 100
PLAYER_TIME_RE = re.compile(r'^\d{1,2}:\d{2}(:\d{2})?\s*/\s*\d{1,2}:\d{2}(:\d{2})?$')
INLINE_TOGGLE_RE = re.compile(r'\s+(Ẩn bớt|Xem thêm|See less|See more)$')


def pick_permalink(hrefs: list[str]) -> str | None:
    """Link riêng của bài: bỏ tham số theo dõi (__cft__, __tn__...), giữ story_fbid/id cho permalink.php."""
    for href in hrefs:
        if not href or not any(k in href for k in PERMALINK_KEYS):
            continue
        parts = urllib.parse.urlsplit(urllib.parse.urljoin('https://www.facebook.com/', href))
        if 'facebook.com' not in (parts.hostname or ''):
            continue
        query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k in KEEP_QUERY_KEYS]
        return urllib.parse.urlunsplit(('https', parts.netloc, parts.path, urllib.parse.urlencode(query), ''))
    return None


def clean_post_text(raw: str, page_name: str = '') -> str:
    """Bỏ phần đầu (tên page, thời gian, nhãn) và phần cuối (cảm xúc, nút bấm) của khối bài đăng."""
    lines = [l.strip() for l in raw.splitlines()]
    body, started = [], False
    for line in lines:
        if line.startswith(FOOTER_START):
            break
        line = INLINE_TOGGLE_RE.sub('', line).strip()  # "… Ẩn bớt" dính cuối dòng
        if not line or line in UI_NOISE or line.isdigit() or PLAYER_TIME_RE.match(line):
            continue
        if not started and (line == page_name or line in HEADER_NOISE or TIME_RE.match(line)):
            continue
        started = True
        body.append(line)
    return '\n'.join(body).strip()


def content_images(imgs: list[tuple[str, int, int]]) -> list[str]:
    """Ảnh nội dung: chỉ ảnh fbcdn/scontent, bỏ avatar/emoji nhỏ và ảnh trùng. Kích thước 0 = chưa biết, vẫn giữ."""
    out = []
    for src, w, h in imgs:
        if not src.startswith('https://') or 'scontent' not in src:
            continue
        if (w and w < MIN_IMAGE_PX) or (h and h < MIN_IMAGE_PX):
            continue
        if src not in out:
            out.append(src)
    return out


def choose_caption(page_text: str, ytdlp_text: str, is_video: bool) -> str:
    """Reel/video: caption từ yt-dlp là nguyên văn tác giả (chữ trên trang lẫn phụ đề video). Bài khác: lấy bản dài hơn."""
    if is_video and ytdlp_text.strip():
        if _is_truncated(ytdlp_text) and len(page_text) > len(ytdlp_text) and not _is_truncated(page_text):
            return page_text
        return ytdlp_text.strip()
    return page_text if len(page_text) >= len(ytdlp_text) else ytdlp_text


def _dismiss_login_dialog(page) -> bool:
    """Đóng hộp "Xem thêm từ …" (có nút X do Facebook cung cấp) để trang cuộn được. Không đăng nhập."""
    btn = page.locator("div[role='dialog'] div[aria-label='Đóng'], div[role='dialog'] div[aria-label='Close']")
    if btn.count():
        try:
            btn.first.click(timeout=3000)
            time.sleep(0.8)
            return True
        except Exception:
            return False
    return False


def _expand_see_more(post):
    for label in ('Xem thêm', 'See more'):
        try:
            more = post.locator(f"div[role='button']:text-is('{label}')")
            if more.count():
                more.first.click(timeout=2000)
                time.sleep(0.4)
        except Exception:
            pass


def _stable_id(text: str) -> str:
    return 'fb_' + hashlib.md5(text.encode('utf-8')).hexdigest()[:12]


def scrape_facebook_page_playwright(page_url: str, max_count: int = 5, progress_callback=None) -> list[dict]:
    """Cào bài công khai từ Fanpage/Profile bằng Playwright headless (không đăng nhập).

    Facebook chỉ cho khách chưa đăng nhập xem một số bài đầu (thường ~8–10); khi trang không tải thêm,
    hàm trả về số bài lấy được và báo lý do qua progress_callback.
    """
    from playwright.sync_api import sync_playwright

    def say(msg):
        if progress_callback:
            progress_callback(msg)

    say("Đang mở trình duyệt nền (Playwright) để tải bài viết của Page...")
    posts, seen = [], set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS['User-Agent'], viewport={"width": 1280, "height": 900},
                                      locale="vi-VN")
        page = context.new_page()
        page.goto(page_url, wait_until="domcontentloaded", timeout=35000)
        time.sleep(3)
        page_name = (page.title() or '').split(' | ')[0].strip()

        units, stale = [], 0
        for _ in range(20):
            _dismiss_login_dialog(page)
            units = page.locator("div[aria-posinset]").all()
            say(f"Đang cuộn tìm bài viết ({min(len(units), max_count)}/{max_count})...")
            if len(units) >= max_count:
                break
            before = len(units)
            page.mouse.wheel(0, 2500)
            time.sleep(2.5)
            stale = stale + 1 if len(page.locator("div[aria-posinset]").all()) == before else 0
            if stale >= 3:
                break
        if not units:  # giao diện cũ: không có aria-posinset
            units = page.locator("div[role='article']").all()

        raw_posts = []
        for unit in units:
            if len(raw_posts) >= max_count:
                break
            try:
                _expand_see_more(unit)
                text = clean_post_text(unit.inner_text(), page_name)
                hrefs = [a.get_attribute('href') or '' for a in unit.locator('a').all()]
                imgs = []
                for img in unit.locator('img').all():
                    size = img.evaluate('e => [e.naturalWidth || e.width || 0, e.naturalHeight || e.height || 0]')
                    imgs.append((img.get_attribute('src') or '', size[0], size[1]))
            except Exception as exc:
                logger.info(f"Bỏ qua một khối bài: {exc}")
                continue
            permalink = pick_permalink(hrefs)
            if not text and not permalink:
                continue
            raw_posts.append((text, permalink, content_images(imgs)))
        browser.close()

    for idx, (text, permalink, images) in enumerate(raw_posts, 1):
        attachments, message = [], text
        if permalink and ('/reel/' in permalink or '/videos/' in permalink):
            say(f"Đang lấy caption đầy đủ & video cho bài {idx}/{len(raw_posts)}...")
            try:
                data = scrape_via_ytdlp(permalink, max_count=1)
                if data:
                    attachments = data[0].get('attachments', {}).get('data', [])
                    message = choose_caption(text, data[0].get('message') or '', is_video=True)
            except Exception as exc:
                logger.info(f"yt-dlp lỗi {permalink}: {exc}")
        if not attachments:
            attachments = [{'media': {'image': {'src': src}}} for src in images]
        post_id = extract_post_id_from_url(permalink) if permalink else _stable_id(message)
        if post_id.startswith('fb_') and permalink:
            post_id = _stable_id(permalink)
        if post_id in seen or not (message or attachments):
            continue
        seen.add(post_id)
        posts.append({'id': post_id, 'message': message, 'created_time': datetime.datetime.now().isoformat(),
                      'permalink_url': permalink or page_url, 'attachments': {'data': attachments},
                      'source_type': 'facebook_page'})
        say(f"Đã lấy thành công bài {len(posts)}/{max_count}...")

    if len(posts) < max_count:
        say(f"Chỉ lấy được {len(posts)}/{max_count} bài: Facebook không cho khách chưa đăng nhập xem thêm. "
            "Muốn lấy thêm, hãy dán link từng bài/Reel (mỗi dòng một link).")
    return posts


def scrape_url(url: str) -> dict:
    """Scrape a single Facebook URL (Reel, Video, or Post)."""
    cleaned = clean_url(url)
    if not cleaned:
        raise ValueError('URL không được để trống.')

    if is_facebook_page_url(cleaned):
        posts = scrape_facebook_page_playwright(cleaned, max_count=1)
        if posts:
            return posts[0]

    # Try yt-dlp first (for Reels/Videos)
    try:
        posts = scrape_via_ytdlp(cleaned, max_count=1)
        if posts and (posts[0].get('message') or posts[0].get('attachments', {}).get('data')):
            return posts[0]
    except Exception as exc:
        logger.info(f"yt-dlp error: {exc}")

    # Fallback to Playwright single post
    posts = scrape_facebook_page_playwright(cleaned, max_count=1)
    if posts:
        return posts[0]

    raise RuntimeError(f"Không thể cào dữ liệu từ URL: {url}")


def scrape_facebook_posts(input_text: str, max_count: int = 5, progress_callback=None) -> list[dict]:
    """Parse input URL(s) and scrape up to max_count posts."""
    raw_lines = [line.strip() for line in input_text.splitlines() if line.strip() and not line.strip().startswith('#')]

    urls = []
    for line in raw_lines:
        found = re.findall(r'https?://[^\s]+|facebook\.com/[^\s]+', line)
        if found:
            for u in found:
                urls.append(clean_url(u))
        else:
            urls.append(clean_url(line))

    if not urls:
        raise ValueError('Vui lòng nhập link Facebook (URL Page, Reels, hoặc bài viết).')

    # Case 1: Multiple URLs provided
    if len(urls) > 1:
        target_urls = urls[:max_count]
        posts = []
        for idx, u in enumerate(target_urls, 1):
            if progress_callback:
                progress_callback(f"Đang cào bài {idx}/{len(target_urls)}: {u[:40]}...")
            try:
                p = scrape_url(u)
                posts.append(p)
            except Exception as exc:
                logger.warning(f"Lỗi cào {u}: {exc}")
        return posts

    # Case 2: Single URL provided
    single_url = urls[0]
    
    # If it's a Page URL (e.g. facebook.com/thinhancac.studio)
    if is_facebook_page_url(single_url):
        return scrape_facebook_page_playwright(single_url, max_count=max_count, progress_callback=progress_callback)

    # If it's a specific Reel/Video/Post URL
    try:
        scraped = scrape_via_ytdlp(single_url, max_count=max_count)
        if scraped:
            return scraped[:max_count]
    except Exception as exc:
        logger.info(f"yt-dlp single failed: {exc}")

    p = scrape_url(single_url)
    return [p]
