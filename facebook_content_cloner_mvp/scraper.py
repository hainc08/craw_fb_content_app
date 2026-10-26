"""Facebook content scraper module for Reels, Videos, and Posts via public URLs.
Supports Playwright for full page timeline scraping and yt-dlp for video/reels stream extraction.
"""
import datetime
import json
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


def parse_ytdlp_info(info: dict, fallback_url: str = '') -> dict:
    """Convert a yt-dlp extracted dict into standard post format."""
    post_id = str(info.get('id') or extract_post_id_from_url(fallback_url or info.get('webpage_url', '')))
    
    title = (info.get('title') or '').strip()
    description = (info.get('description') or '').strip()
    
    if description and title and title != description and not description.startswith(title):
        message = f"{title}\n\n{description}"
    else:
        message = description or title or ''

    upload_date = info.get('upload_date')
    if upload_date and len(upload_date) == 8:
        created_time = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00"
    elif info.get('timestamp'):
        created_time = datetime.datetime.fromtimestamp(info['timestamp']).isoformat()
    else:
        created_time = datetime.datetime.now().isoformat()

    attachments_data = []
    video_url = info.get('url')
    if not video_url and info.get('formats'):
        for f in reversed(info['formats']):
            if f.get('url', '').startswith('https://') and f.get('vcodec') != 'none':
                video_url = f['url']
                break

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


def scrape_facebook_page_playwright(page_url: str, max_count: int = 5, progress_callback=None) -> list[dict]:
    """Scrape posts/reels from a Facebook Fanpage or Profile using Playwright headless."""
    from playwright.sync_api import sync_playwright

    if progress_callback:
        progress_callback("Đang mở trình duyệt nền (Playwright) để tải bài viết của Page...")

    posts = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="vi-VN"
        )
        page = context.new_page()
        page.goto(page_url, wait_until="domcontentloaded", timeout=35000)
        time.sleep(3)

        # Scroll down to load posts
        scroll_attempts = 0
        found_articles = []
        while len(found_articles) < max_count and scroll_attempts < 8:
            scroll_attempts += 1
            page.evaluate("window.scrollBy(0, 1600)")
            time.sleep(2)
            found_articles = page.locator("div[role='article']").all()
            if progress_callback:
                progress_callback(f"Đang cuộn tìm bài viết ({len(found_articles)}/{max_count})...")

        for idx, art in enumerate(found_articles):
            if len(posts) >= max_count:
                break
            raw_text = art.inner_text().strip()
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            ignore_keywords = {"Thích", "Bình luận", "Chia sẻ", "Viết bình luận...", "Gửi", "Theo dõi", "Đã theo dõi", "Tin nhắn"}
            clean_lines = [l for l in lines if l not in ignore_keywords]
            message = "\n".join(clean_lines) if clean_lines else raw_text

            # Find media images
            imgs = []
            for img in art.locator("img").all():
                src = img.get_attribute("src") or ""
                if src.startswith("https://") and ("fbcdn" in src or "scontent" in src):
                    imgs.append(src)

            # Find post or reel link
            post_permalink = page_url
            reel_or_video_url = None
            for a in art.locator("a").all():
                href = a.get_attribute("href") or ""
                if any(k in href for k in ["/posts/", "/videos/", "/reel/", "story_fbid", "/photos/"]):
                    clean_link = href.split("?")[0] if "?" in href else href
                    post_permalink = clean_link
                    if "/reel/" in clean_link or "/videos/" in clean_link:
                        reel_or_video_url = clean_link
                    break

            attachments_data = []
            if reel_or_video_url:
                try:
                    if progress_callback:
                        progress_callback(f"Đang lấy video MP4 cho bài {len(posts)+1}...")
                    reel_data = scrape_via_ytdlp(reel_or_video_url, max_count=1)
                    if reel_data and reel_data[0].get('attachments', {}).get('data'):
                        attachments_data = reel_data[0]['attachments']['data']
                        if reel_data[0].get('message') and len(reel_data[0]['message']) > len(message):
                            message = reel_data[0]['message']
                except Exception:
                    pass

            if not attachments_data and imgs:
                attachments_data.append({'media': {'image': {'src': imgs[0]}}})

            if not message and not attachments_data:
                continue

            post_id = extract_post_id_from_url(post_permalink)
            posts.append({
                'id': post_id,
                'message': message,
                'created_time': datetime.datetime.now().isoformat(),
                'permalink_url': post_permalink,
                'attachments': {'data': attachments_data},
                'source_type': 'facebook_page'
            })
            if progress_callback:
                progress_callback(f"Đã lấy thành công bài {len(posts)}/{max_count}...")

        browser.close()

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
