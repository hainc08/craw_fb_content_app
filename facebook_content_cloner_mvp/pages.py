"""Hồ sơ cấu hình cho từng Facebook Page, lưu ở ROOT/pages.json.

Token Page chỉ nằm trong file này (không bao giờ vào SQLite, không in ra màn hình).
"""
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from research import ANALYSIS_PROMPT

DEFAULT_SLUG = 'chuyen-doi-nhan-tam'
DEFAULT_NAME = 'Chuyện Đời & Nhân Tâm'
PROVIDERS = ('', 'gemini', 'cloudflare', 'openai')

GENERIC_ANALYSIS_PROMPT = 'Page đích: {page_name}.\n' + ANALYSIS_PROMPT

GENERIC_CREATION_PROMPT = """Bạn là biên tập viên nội dung của Facebook Page "{page_name}".
Nhiệm vụ: dựa trên CHỦ ĐỀ và cơ chế cảm xúc của bài nguồn, viết MỘT bài Facebook hoàn toàn mới cho page.
- Nhân vật, bối cảnh, diễn biến, lời thoại và câu chốt phải khác hẳn bài nguồn. Không sao chép, không paraphrase từng câu.
- Tiếng Việt tự nhiên, câu ngắn, xuống dòng nhiều để dễ đọc trên điện thoại.
- Mở đầu bằng 1–2 câu hook chạm cảm xúc; kết thúc bằng một câu hỏi mở mời bình luận.
- Dòng cuối là hashtag: {hashtags}
- Không bịa số liệu, không bịa trích dẫn gán cho người nổi tiếng, không nêu tên người thật.
- CHỈ trả về nội dung bài đăng, sẵn sàng đăng ngay: không tiêu đề mục, không nhãn như "HOOK:", "TIÊU ĐỀ:", không giải thích."""

NHAN_TAM_CREATION_PROMPT = """Bạn là biên tập viên của Facebook Page "{page_name}" — page kể chuyện đời thường có bài học đối nhân xử thế theo tinh thần Đắc Nhân Tâm, cho người đi làm 22–45 tuổi.
Nhiệm vụ: giữ BÀI HỌC/CẢM XÚC của bài nguồn, viết một câu chuyện HOÀN TOÀN MỚI (nhân vật, bối cảnh, tình tiết, lời thoại, câu chốt đều khác). Không paraphrase câu nào của bài gốc.

Khung bài (180–320 chữ):
1. Hook 1–2 câu chạm nỗi niềm ("Có bao giờ bạn…", "Người càng… lại càng…"). Không chào hỏi.
2. Câu chuyện 2–4 đoạn ngắn, ngôi thứ ba, một nhân vật chính tên Việt ngắn (Minh, Lan, Hùng, Thảo…), bối cảnh đời thường Việt Nam. Có một chi tiết nhỏ cụ thể và một câu thoại trong ngoặc kép ở khoảnh khắc thay đổi.
3. Bài học 1–2 câu, nói bằng lời của mình, không giảng đạo.
4. Một câu đúc kết ngắn, đối xứng, dễ chia sẻ.
5. Một câu hỏi mời người đọc kể trải nghiệm của họ, kèm 👇
6. Dòng cuối: {hashtags}

Văn phong: câu ngắn, chi tiết thay cho tính từ chung chung, kết tích cực nhưng không màu hồng, tối đa 2–3 emoji.
Không chép câu chữ sách Đắc Nhân Tâm, không bịa câu nói gán cho Dale Carnegie hay người nổi tiếng, không viết như trải nghiệm thật của admin.
CHỈ trả về bài đăng sẵn sàng đăng: không nhãn mục ("HOOK:", "TIÊU ĐỀ:"…), không giải thích."""


def slugify(name: str) -> str:
    s = unicodedata.normalize('NFD', name.replace('đ', 'd').replace('Đ', 'D'))
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn').lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


@dataclass
class PageProfile:
    slug: str
    name: str
    fb_page_id: str = ''
    fb_page_token: str = ''
    provider: str = ''  # '' = dùng provider chung trong api_config.json
    hashtags: str = ''
    analysis_prompt: str = GENERIC_ANALYSIS_PROMPT
    creation_prompt: str = GENERIC_CREATION_PROMPT
    max_similarity: float = 0.35

    def public_dict(self) -> dict:
        d = asdict(self)
        d.pop('fb_page_token')
        d['has_token'] = bool(self.fb_page_token.strip())
        return d


_FIELDS = {f.name for f in fields(PageProfile)}


def default_profile(legacy: dict | None = None) -> PageProfile:
    legacy = legacy or {}
    return PageProfile(slug=DEFAULT_SLUG, name=DEFAULT_NAME,
                       fb_page_id=str(legacy.get('fb_page_id', '') or ''),
                       fb_page_token=str(legacy.get('fb_page_token', '') or ''),
                       hashtags='#chuyendoi #nhantam',
                       creation_prompt=NHAN_TAM_CREATION_PROMPT)


class PageStore:
    def __init__(self, path: Path, legacy: dict | None = None):
        self.path = Path(path)
        self.legacy = legacy
        self._pages: list[PageProfile] = []
        self._active = ''
        self._load()

    # ---- đọc / ghi ----
    def _load(self):
        data = None
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                data = None
        pages = []
        if isinstance(data, dict) and isinstance(data.get('pages'), list):
            for raw in data['pages']:
                if not isinstance(raw, dict) or not str(raw.get('name', '')).strip():
                    continue
                vals = {k: v for k, v in raw.items() if k in _FIELDS}
                try:
                    p = PageProfile(**{'slug': '', **vals})
                    p.max_similarity = float(p.max_similarity)
                except (TypeError, ValueError):
                    continue
                p.slug = p.slug or slugify(p.name)
                pages.append(p)
        if not pages:
            if self.path.exists():
                self.path.replace(self.path.with_name(self.path.name + '.bak'))
            self._pages = [default_profile(self.legacy)]
            self._active = DEFAULT_SLUG
            self._write()
            return
        self._pages = pages
        active = data.get('active', '')
        self._active = active if any(p.slug == active for p in pages) else pages[0].slug

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'active': self._active, 'pages': [asdict(p) for p in self._pages]}
        tmp = self.path.with_name(self.path.name + '.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    # ---- API ----
    def list(self) -> list[PageProfile]:
        return list(self._pages)

    def get(self, slug: str) -> PageProfile:
        for p in self._pages:
            if p.slug == slug:
                return p
        raise KeyError(slug)

    def save(self, profile: PageProfile) -> None:
        profile.name = profile.name.strip()
        profile.fb_page_id = profile.fb_page_id.strip()
        profile.fb_page_token = profile.fb_page_token.strip()
        if not profile.name:
            raise ValueError('Tên Page không được để trống.')
        if profile.fb_page_id and not profile.fb_page_id.isdigit():
            raise ValueError('Facebook Page ID phải là dãy số (không dán URL).')
        if not 0 < float(profile.max_similarity) < 1:
            raise ValueError('Ngưỡng trùng phải nằm trong khoảng 0–1 (vd 0.35).')
        if profile.provider not in PROVIDERS:
            raise ValueError(f'Nhà cung cấp AI không hợp lệ: {profile.provider}')
        profile.slug = profile.slug or slugify(profile.name)
        if not profile.slug:
            raise ValueError('Không tạo được mã Page từ tên này.')
        for i, p in enumerate(self._pages):
            if p.slug == profile.slug:
                self._pages[i] = profile
                break
        else:
            self._pages.append(profile)
        self._write()

    def delete(self, slug: str) -> None:
        self.get(slug)
        if len(self._pages) == 1:
            raise ValueError('Không thể xóa Page cuối cùng.')
        self._pages = [p for p in self._pages if p.slug != slug]
        if self._active == slug:
            self._active = self._pages[0].slug
        self._write()

    def active(self) -> PageProfile:
        return self.get(self._active)

    def set_active(self, slug: str) -> None:
        self.get(slug)
        self._active = slug
        self._write()
