"""Kiểm tra và đăng bài lên Facebook Page qua Graph API — dùng chung cho GUI và CLI."""
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from research import similarity

TEMPLATE_MARKERS = ('KỊCH BẢN REEL', 'TIÊU ĐỀ:', 'HOOK:', 'CAPTION FACEBOOK:')
PHOTO_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXT = {'.mp4', '.mov'}
VN_TZ = dt.timezone(dt.timedelta(hours=7))
MIN_AHEAD = 600
MAX_AHEAD = 30 * 86400


class PublishError(Exception):
    pass


@dataclass
class PublishPlan:
    text: str
    kind: str  # 'text' | 'photo' | 'video'
    media_path: Path | None
    scheduled_ts: int | None
    check: dict


def check_originality(source: str, text: str, max_ratio: float) -> dict:
    r = similarity(source, text)
    r['passed'] = r['sequence_ratio'] <= max_ratio and not r['shared_phrases']
    r['limits'] = {'max_sequence_ratio': max_ratio, 'max_shared_7gram_phrases': 0}
    return r


def parse_schedule(value: str, now: dt.datetime) -> int:
    try:
        when = dt.datetime.fromisoformat(value.strip())
    except ValueError:
        raise PublishError(f'Giờ hẹn không đúng định dạng (vd 2026-10-27T20:00): {value}') from None
    if when.tzinfo is None:
        when = when.replace(tzinfo=VN_TZ)
    ts = int(when.timestamp())
    ahead = ts - now.timestamp()
    if not MIN_AHEAD <= ahead <= MAX_AHEAD:
        raise PublishError('Giờ hẹn phải cách hiện tại từ 10 phút đến 30 ngày.')
    return ts


def prepare(source: str, text: str, max_ratio: float, media_path: str | None, scraped_media_root: Path,
            schedule: str | None = None, now: dt.datetime | None = None, i_own_media: bool = False) -> PublishPlan:
    text = (text or '').strip()
    if not text:
        raise PublishError('Nội dung đăng đang trống.')
    if any(m in text for m in TEMPLATE_MARKERS):
        raise PublishError('Nội dung còn các mục khung (TIÊU ĐỀ:/HOOK:/KỊCH BẢN REEL...). '
                           'Biên tập thành bài sạch sẵn sàng đăng trước.')
    check = check_originality(source, text, max_ratio)
    if not check['passed']:
        shared = '; '.join(check['shared_phrases'][:3])
        raise PublishError(f'Nội dung quá giống bài nguồn (tỉ lệ {check["sequence_ratio"]:.0%}). {shared}')

    kind, path = 'text', None
    if media_path:
        path = Path(media_path).resolve()
        if not path.is_file():
            raise PublishError(f'Không thấy file {path}')
        ext = path.suffix.lower()
        if ext in PHOTO_EXT:
            kind = 'photo'
        elif ext in VIDEO_EXT:
            kind = 'video'
        else:
            raise PublishError(f'Định dạng không hỗ trợ: {ext} (dùng jpg/png/webp hoặc mp4/mov).')
        if Path(scraped_media_root).resolve() in path.parents and not i_own_media:
            raise PublishError('File này là media cào từ bài người khác — không đăng lại. '
                               'Dùng ảnh/video tự tạo, hoặc xác nhận bạn có quyền dùng file.')

    ts = parse_schedule(schedule, now or dt.datetime.now(dt.timezone.utc)) if schedule and schedule.strip() else None
    return PublishPlan(text, kind, path, ts, check)


def _error_message(r) -> str:
    try:
        err = r.json().get('error', {})
        return f"Meta HTTP {r.status_code}: {err.get('message', '')} (code={err.get('code', '?')})"
    except Exception:
        return f'HTTP {r.status_code}: {getattr(r, "text", "")[:180]}'


def send(plan: PublishPlan, page_id: str, token: str, session, graph_version: str) -> str:
    headers = {'Authorization': f'Bearer {token}'}
    data = {}
    if plan.scheduled_ts:
        data = {'published': 'false', 'scheduled_publish_time': str(plan.scheduled_ts)}

    def post(url, payload, file_path=None):
        if file_path is None:
            return session.post(url, headers=headers, data=payload, files=None, timeout=(10, 120))
        with open(file_path, 'rb') as f:
            return session.post(url, headers=headers, data=payload, files={'source': f}, timeout=(10, 900))

    if plan.kind == 'text':
        r = post(f'https://graph.facebook.com/{graph_version}/{page_id}/feed', {'message': plan.text, **data})
    elif plan.kind == 'photo':
        r = post(f'https://graph.facebook.com/{graph_version}/{page_id}/photos',
                 {'caption': plan.text, **data}, plan.media_path)
    elif plan.kind == 'video':
        r = post(f'https://graph-video.facebook.com/{graph_version}/{page_id}/videos',
                 {'description': plan.text, **data}, plan.media_path)
    else:
        raise PublishError(f'Loại bài không hỗ trợ: {plan.kind}')
    if not r.ok:
        raise PublishError(_error_message(r))
    res = r.json()
    fb_id = res.get('post_id') or res.get('id')
    if not fb_id:
        raise PublishError(f'Meta không trả về ID bài viết: {res}')
    return str(fb_id)
