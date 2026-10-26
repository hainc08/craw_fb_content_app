# Giao diện đa Page + Xem media + Prompt AI theo Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa GUI của Facebook Content Cloner để: nhập (nhiều) URL Facebook cần cào; xem nội dung bài cùng ảnh/video đã cào về; dùng AI viết lại theo prompt cấu hình riêng cho từng Page; quản lý nhiều Page (mỗi Page có ID, token, prompt, hashtag, ngưỡng trùng riêng) và đăng lên Page đang chọn.

**Architecture:** Tách logic khỏi `app.py` (731 dòng) thành các module nhỏ, test được: `pages.py` (hồ sơ Page lưu ở `pages.json`), `page_data.py` (nháp/phân tích/đã đăng theo cặp bài nguồn + Page trong SQLite), `publisher.py` (kiểm tra và gửi lên Graph API, dùng chung cho GUI và CLI), `media_view.py` (dải ảnh/video thu nhỏ), `page_dialog.py` + `publish_dialog.py` (hộp thoại Tk). `app.py` và `fbtool.py` chỉ lắp ghép các module này.

**Tech Stack:** Python 3.14 (`py -3`), Tkinter/ttk theme `clam`, SQLite, requests, Pillow (ảnh thu nhỏ), pytest (chỉ để dev).

**Spec:** Yêu cầu người dùng ngày 2026-10-26, không có tài liệu spec riêng:
> "sửa lại giao diện để có thể nhập url facebook cần cào bài, nội dung bài & ảnh video sau khi cào về, thực hiện dùng AI sửa lại nội dung mới theo prompt được thiết lập, ngoài ra phần cấu hình cần cấu hình cho từng page nhé. tôi dự định dùng nhiều page khác nhau chứ ko hẳn 1 page chuyện đời & nhân tâm"

Hiểu thành các yêu cầu:
- R1 Ô nhập URL nhiều dòng (mỗi dòng một link) + số bài + nút cào (giữ luồng cào hiện có).
- R2 Khi chọn bài: hiện caption gốc, ảnh thu nhỏ, ô video; bấm vào để mở file; tải media còn thiếu.
- R3 "Phân tích AI" và "Sáng tạo mới" dùng prompt của Page đang chọn; prompt sửa được trong GUI và có nút khôi phục mặc định.
- R4 Cấu hình theo Page: tên, Facebook Page ID, Page token, nhà cung cấp AI (hoặc dùng mặc định chung), hashtag, ngưỡng trùng, prompt phân tích, prompt sáng tạo. Thêm/sửa/xóa nhiều Page, chọn Page đang làm ở thanh trên.
- R5 Nháp, phân tích, trạng thái duyệt/đăng tách theo từng Page: một bài nguồn có thể có nháp khác nhau cho từng Page.
- R6 Đăng bài đã duyệt lên Page đang chọn (chữ / ảnh / video, có thể hẹn giờ) từ GUI và CLI.

## Global Constraints

- Chạy bằng `py -3` (Python 3.14) trên Windows; test chạy trong `facebook_content_cloner_mvp/`: `py -3 -m pytest tests -v`.
- Thư mục dữ liệu: `ROOT = FBCLONER_HOME` hoặc `%USERPROFILE%\Documents\FacebookContentCloner`. File hồ sơ: `ROOT/pages.json`.
- Token Page **không bao giờ** lưu vào SQLite, không in ra stdout/log, ô nhập token trong GUI dùng `show='●'`.
- Khóa AI (Gemini/Cloudflare/OpenAI) vẫn để chung trong `api_config.json`; Page chỉ chọn `provider`.
- Ngưỡng trùng mặc định: `sequence_ratio ≤ 0.35` và `0` cụm 7 từ chung (`research.similarity`).
- Placeholder trong prompt: `{page_name}`, `{hashtags}`, thay bằng `str.replace` (không dùng `str.format`).
- Slug Page mặc định: `chuyen-doi-nhan-tam`, tên `Chuyện Đời & Nhân Tâm`.
- `GRAPH_VERSION = 'v26.0'`; hẹn giờ phải cách hiện tại 600 giây – 30 ngày; giờ không có múi giờ hiểu là UTC+7.
- Không đăng lại file nằm trong `ROOT/media` (media cào về) trừ khi có cờ `i_own_media=True`.
- Chữ hiển thị trong GUI bằng tiếng Việt; giữ theme `clam`, font `Segoe UI`.
- Không thêm thư viện ngoài Pillow (runtime) và pytest (dev).

## Review Focus

1. `pages.json` thiếu, rỗng, hỏng JSON hoặc bị sửa tay sai → app vẫn mở với Page mặc định; file hỏng được đổi tên thành `pages.json.bak`. (Task 1: `test_corrupt_file_backed_up_and_default_created`)
2. Xóa Page đang chọn hoặc Page cuối cùng → không cho xóa Page cuối; xóa Page đang chọn thì Page đang chọn chuyển sang Page đầu còn lại. (Task 1: `test_delete_last_page_refused`, `test_delete_active_switches_active`)
3. Prompt chứa dấu ngoặc nhọn thật (ví dụ mẫu JSON `{"a": 1}`) → không lỗi, chỉ thay đúng `{page_name}`/`{hashtags}`. (Task 3: `test_render_prompt_keeps_other_braces`)
4. File media bị xóa khỏi ổ, ảnh hỏng, hoặc bài chỉ có video → dải media hiện ô giữ chỗ, không văng lỗi. (Task 6: `test_media_items_missing_file`, `test_make_thumbnail_corrupt_returns_none`)
5. Cùng một bài nguồn làm cho hai Page → nháp tách riêng; đăng lên Page A không chặn Page B; đăng lại lên A bị chặn. (Task 2: `test_drafts_independent_per_page`, `test_published_per_page`)

---

## File Structure

| File | Trách nhiệm |
|---|---|
| Create `facebook_content_cloner_mvp/pages.py` | `PageProfile`, `PageStore` (đọc/ghi `pages.json`, Page đang chọn), `slugify`, prompt mặc định |
| Create `facebook_content_cloner_mvp/page_data.py` | Bảng `page_drafts`, `page_research`, `page_published`; migrate từ `drafts`/`research`/`published`; CRUD |
| Modify `facebook_content_cloner_mvp/research.py` | `render_prompt`; `analyze`/`create_new` nhận `instruction` |
| Create `facebook_content_cloner_mvp/publisher.py` | `PublishPlan`, `prepare`, `parse_schedule`, `send` |
| Modify `facebook_content_cloner_mvp/fbtool.py` | Cờ `--page`, lệnh `pages`, `page-show`; dùng `page_data` + `publisher` |
| Create `facebook_content_cloner_mvp/media_view.py` | `MediaItem`, `media_items`, `make_thumbnail`, widget `MediaStrip` |
| Create `facebook_content_cloner_mvp/page_dialog.py` | `PageManagerDialog` |
| Create `facebook_content_cloner_mvp/publish_dialog.py` | `PublishDialog` |
| Modify `facebook_content_cloner_mvp/app.py` | Thanh chọn Page, ô URL nhiều dòng, dải media, nháp/AI/đăng theo Page |
| Create `facebook_content_cloner_mvp/tests/` | `conftest.py` + test cho từng module |
| Modify `requirements.txt`, create `requirements-dev.txt`, `.gitignore` | Pillow, pytest |
| Modify `CLAUDE.md`, `README.md`, `.claude/skills/*` | Tài liệu và skill theo đa Page |

---

### Task 1: Hồ sơ Page (`pages.py`) + khung test + git

**Files:**
- Create: `.gitignore` (ở gốc dự án: `__pycache__/`, `dist/`, `build/`, `*.spec`, `.pytest_cache/`)
- Create: `facebook_content_cloner_mvp/requirements-dev.txt` (`-r requirements.txt` + `pytest>=8,<9`)
- Modify: `facebook_content_cloner_mvp/requirements.txt` (thêm `Pillow>=10,<13`)
- Create: `facebook_content_cloner_mvp/tests/conftest.py`
- Create: `facebook_content_cloner_mvp/pages.py`
- Test: `facebook_content_cloner_mvp/tests/test_pages.py`

**Interfaces:**
- Produces:
  - `DEFAULT_SLUG = 'chuyen-doi-nhan-tam'`, `DEFAULT_NAME = 'Chuyện Đời & Nhân Tâm'`
  - `GENERIC_ANALYSIS_PROMPT: str`, `GENERIC_CREATION_PROMPT: str`, `NHAN_TAM_CREATION_PROMPT: str`
  - `slugify(name: str) -> str`
  - `@dataclass PageProfile(slug: str, name: str, fb_page_id: str = '', fb_page_token: str = '', provider: str = '', hashtags: str = '', analysis_prompt: str = GENERIC_ANALYSIS_PROMPT, creation_prompt: str = GENERIC_CREATION_PROMPT, max_similarity: float = 0.35)`; `provider == ''` nghĩa là dùng provider chung trong `api_config.json`. Có thêm `public_dict() -> dict`: như `asdict` nhưng bỏ `fb_page_token`, thêm `has_token: bool`.
  - `class PageStore(path: Path, legacy: dict | None = None)` với `list() -> list[PageProfile]`, `get(slug) -> PageProfile` (KeyError), `save(profile) -> None`, `delete(slug) -> None`, `active() -> PageProfile`, `set_active(slug) -> None`.

- [ ] **Step 1: Khung dự án**

Chạy ở gốc `D:\facebook_content_research_creator_windows`: `git init`, tạo `.gitignore`; sửa `requirements.txt`, tạo `requirements-dev.txt`; `py -3 -m pip install -r facebook_content_cloner_mvp/requirements-dev.txt`.
`tests/conftest.py` phải đặt `FBCLONER_HOME` **trước** khi import `app`:

```python
import os, sys, tempfile
from pathlib import Path
os.environ['FBCLONER_HOME'] = tempfile.mkdtemp(prefix='fbcloner_test_')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

@pytest.fixture
def conn(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, 'DB', tmp_path / 'test.sqlite3')
    app.init_db()
    c = app.db()
    yield c
    c.close()
```

- [ ] **Step 2: Viết test lỗi trước**

```python
from pages import PageStore, PageProfile, slugify, DEFAULT_SLUG, DEFAULT_NAME, NHAN_TAM_CREATION_PROMPT

def test_slugify_vietnamese():
    assert slugify('Chuyện Đời & Nhân Tâm') == 'chuyen-doi-nhan-tam'
    assert slugify('  Mẹo   Văn Phòng 24h ') == 'meo-van-phong-24h'

def test_missing_file_creates_default(tmp_path):
    s = PageStore(tmp_path / 'pages.json')
    pages = s.list()
    assert [p.slug for p in pages] == [DEFAULT_SLUG]
    assert pages[0].name == DEFAULT_NAME
    assert pages[0].creation_prompt == NHAN_TAM_CREATION_PROMPT
    assert s.active().slug == DEFAULT_SLUG
    assert (tmp_path / 'pages.json').exists()

def test_legacy_fb_keys_migrated_into_default(tmp_path):
    s = PageStore(tmp_path / 'pages.json', legacy={'fb_page_id': '123', 'fb_page_token': 'tok'})
    p = s.get(DEFAULT_SLUG)
    assert (p.fb_page_id, p.fb_page_token) == ('123', 'tok')

def test_save_roundtrip_and_new_store_reads_it(tmp_path):
    path = tmp_path / 'pages.json'
    PageStore(path).save(PageProfile(slug='meo-vp', name='Mẹo VP', hashtags='#meo', max_similarity=0.3))
    p = PageStore(path).get('meo-vp')
    assert (p.name, p.hashtags, p.max_similarity) == ('Mẹo VP', '#meo', 0.3)

def test_save_rejects_bad_values(tmp_path):
    s = PageStore(tmp_path / 'pages.json')
    for bad in [PageProfile(slug='x', name='  '),
                PageProfile(slug='x', name='X', fb_page_id='facebook.com/abc'),
                PageProfile(slug='x', name='X', max_similarity=1.5)]:
        with pytest.raises(ValueError):
            s.save(bad)

def test_corrupt_file_backed_up_and_default_created(tmp_path):
    path = tmp_path / 'pages.json'
    path.write_text('{not json', encoding='utf-8')
    assert PageStore(path).active().slug == DEFAULT_SLUG
    assert (tmp_path / 'pages.json.bak').read_text(encoding='utf-8') == '{not json'

def test_delete_last_page_refused(tmp_path):
    with pytest.raises(ValueError):
        PageStore(tmp_path / 'pages.json').delete(DEFAULT_SLUG)

def test_delete_active_switches_active(tmp_path):
    s = PageStore(tmp_path / 'pages.json')
    s.save(PageProfile(slug='b', name='B'))
    s.set_active('b')
    s.delete('b')
    assert s.active().slug == DEFAULT_SLUG

def test_public_dict_hides_token():
    d = PageProfile(slug='a', name='A', fb_page_token='secret').public_dict()
    assert 'fb_page_token' not in d and d['has_token'] is True
    assert 'secret' not in str(d)
```
(thêm `import pytest` ở đầu file.)

- [ ] **Step 3: Chạy để thấy lỗi**

Run: `py -3 -m pytest tests/test_pages.py -v` → FAIL `ModuleNotFoundError: No module named 'pages'`.

- [ ] **Step 4: Viết `pages.py`**

- `pages.json` có dạng `{"active": "<slug>", "pages": [ {...PageProfile...} ]}`, ghi UTF-8, `ensure_ascii=False`, `indent=2`, ghi ra file tạm `.tmp` rồi `replace` để khỏi hỏng file khi mất điện.
- `slugify`: `unicodedata.normalize('NFD')`, bỏ dấu kết hợp, đổi `đ/Đ` → `d`, viết thường, ký tự không phải `[a-z0-9]` thành `-`, gộp và cắt `-` hai đầu.
- Khi đọc: thiếu file, JSON hỏng, hoặc `pages` rỗng/không phải list → (nếu file có tồn tại thì đổi tên thành `.bak`) tạo Page mặc định (`NHAN_TAM_CREATION_PROMPT`, `hashtags='#chuyendoi #nhantam'`, cộng `legacy` nếu có) rồi ghi file. Bỏ qua khóa lạ trong từng mục, khóa thiếu thì lấy giá trị mặc định. `active` không trỏ tới Page nào → lấy Page đầu.
- Kiểm tra trong `save`: tên không rỗng sau `strip()`; `fb_page_id` rỗng hoặc toàn chữ số; `0 < max_similarity < 1`; `provider in ('', 'gemini', 'cloudflare', 'openai')`; slug rỗng thì tự lấy `slugify(name)`.
- `GENERIC_ANALYSIS_PROMPT` = nội dung `research.ANALYSIS_PROMPT`, thêm dòng mở đầu "Page đích: {page_name}." Tạo `GENERIC_CREATION_PROMPT` mới. Prompt này yêu cầu AI chỉ trả về **một bài Facebook sạch, đăng được ngay** cho `{page_name}`: không có nhãn mục (TIÊU ĐỀ:, HOOK:…), có nhân vật/bối cảnh/diễn biến mới hoàn toàn, và kết thúc bằng câu hỏi mở và hashtag `{hashtags}`. `NHAN_TAM_CREATION_PROMPT` làm theo cùng quy tắc, cộng thêm giọng văn từ `.claude/skills/sang-tao-nhan-tam/references/giong-van-page.md`: khung Hook → chuyện → bài học → đúc kết → câu hỏi → hashtag, 180–320 chữ, và cấm bịa trích dẫn Dale Carnegie.

- [ ] **Step 5: Chạy test đạt**

Run: `py -3 -m pytest tests/test_pages.py -v` → 9 passed.

- [ ] **Step 6: Commit**

```bash
git add .gitignore facebook_content_cloner_mvp CLAUDE.md .claude
git commit -m "feat: per-page profiles stored in pages.json"
```
(Commit đầu tiên gồm toàn bộ code hiện có + phần mới.)

---

### Task 2: Dữ liệu theo Page (`page_data.py`)

**Files:**
- Create: `facebook_content_cloner_mvp/page_data.py`
- Test: `facebook_content_cloner_mvp/tests/test_page_data.py`

**Interfaces:**
- Consumes: fixture `conn` (Task 1); bảng `posts`, `media`, `drafts`, `research` sẵn có từ `app.init_db()`.
- Produces:
  - `migrate(conn, default_slug: str) -> None`: tạo bảng nếu chưa có, chạy lại nhiều lần vẫn an toàn.
    - `page_drafts(post_id, page_slug, body, status DEFAULT 'review', updated_at)`, khóa chính `(post_id, page_slug)`.
    - `page_research(post_id, page_slug, analysis, updated_at)`, khóa chính `(post_id, page_slug)`.
    - `page_published(post_id, page_slug, fb_post_id, kind, scheduled_time, published_at)`, khóa chính `(post_id, page_slug)`.
    - Chép `INSERT OR IGNORE` từ `drafts`, `research` và (nếu bảng tồn tại) `published` sang các bảng trên với `default_slug`.
  - `get_draft(conn, post_id, page_slug) -> sqlite3.Row | None` (cột `body`, `status`)
  - `save_draft(conn, post_id, page_slug, body: str, status: str = 'review') -> None`
  - `get_analysis(conn, post_id, page_slug) -> str | None`; `save_analysis(conn, post_id, page_slug, text) -> None`
  - `get_published(conn, post_id, page_slug) -> sqlite3.Row | None`
  - `mark_published(conn, post_id, page_slug, fb_post_id: str, kind: str, scheduled_time: str = '') -> None`: thêm dòng vào `page_published`, đổi status nháp thành `'scheduled'` nếu có `scheduled_time`, ngược lại `'published'`.
  - `list_posts(conn, page_slug, status: str | None = None, limit: int = 200) -> list[sqlite3.Row]`: các cột `id, created_time, message, status ('' nếu chưa có nháp), analyzed (0/1), media_count, fb_post_id`, sắp theo `imported_at DESC`. `status='none'` lọc bài chưa có nháp.
- Status hợp lệ: `review`, `approved`, `published`, `scheduled`. `save_draft` báo `ValueError` nếu status khác.

- [ ] **Step 1: Viết test lỗi trước**

```python
import app, page_data as pd

def seed(conn, pid='p1', msg='Nguồn'):
    app.insert_post({'id': pid, 'message': msg, 'attachments': {'data': []}})

def test_migrate_copies_old_draft_once(conn):
    seed(conn)
    conn.execute("INSERT INTO drafts(post_id, body, status) VALUES('p1','cũ','approved')"); conn.commit()
    pd.migrate(conn, 'a'); pd.migrate(conn, 'a')
    assert dict(pd.get_draft(conn, 'p1', 'a')) == {'body': 'cũ', 'status': 'approved'}
    assert conn.execute('SELECT COUNT(*) FROM page_drafts').fetchone()[0] == 1

def test_drafts_independent_per_page(conn):
    seed(conn); pd.migrate(conn, 'a')
    pd.save_draft(conn, 'p1', 'a', 'bài A')
    pd.save_draft(conn, 'p1', 'b', 'bài B', 'approved')
    assert pd.get_draft(conn, 'p1', 'a')['body'] == 'bài A'
    assert pd.get_draft(conn, 'p1', 'b')['status'] == 'approved'

def test_save_draft_rejects_unknown_status(conn):
    pd.migrate(conn, 'a')
    with pytest.raises(ValueError):
        pd.save_draft(conn, 'p1', 'a', 'x', 'done')

def test_published_per_page(conn):
    seed(conn); pd.migrate(conn, 'a')
    pd.save_draft(conn, 'p1', 'a', 'x', 'approved')
    pd.mark_published(conn, 'p1', 'a', '111_222', 'text')
    assert pd.get_published(conn, 'p1', 'a')['fb_post_id'] == '111_222'
    assert pd.get_published(conn, 'p1', 'b') is None
    assert pd.get_draft(conn, 'p1', 'a')['status'] == 'published'

def test_mark_scheduled_sets_status(conn):
    seed(conn); pd.migrate(conn, 'a'); pd.save_draft(conn, 'p1', 'a', 'x', 'approved')
    pd.mark_published(conn, 'p1', 'a', '9', 'photo', '2026-10-27T20:00')
    assert pd.get_draft(conn, 'p1', 'a')['status'] == 'scheduled'

def test_list_posts_status_filter(conn):
    seed(conn, 'p1'); seed(conn, 'p2'); pd.migrate(conn, 'a')
    pd.save_draft(conn, 'p1', 'a', 'x')
    assert [r['id'] for r in pd.list_posts(conn, 'a', 'none')] == ['p2']
    assert [r['id'] for r in pd.list_posts(conn, 'a', 'review')] == ['p1']
    assert sorted(r['id'] for r in pd.list_posts(conn, 'b', 'none')) == ['p1', 'p2']
```
(thêm `import pytest`.)

- [ ] **Step 2: Chạy để thấy lỗi** — `py -3 -m pytest tests/test_page_data.py -v` → FAIL `No module named 'page_data'`.
- [ ] **Step 3: Viết `page_data.py`** theo Interfaces. Mọi hàm ghi đều tự `conn.commit()`. Kiểm tra bảng `published` có tồn tại hay không bằng `sqlite_master`.
- [ ] **Step 4: Chạy test đạt** — 6 passed.
- [ ] **Step 5: Commit** — `git commit -m "feat: per-page drafts, research and published tables"`

---

### Task 3: Prompt theo Page trong `research.py`

**Files:**
- Modify: `facebook_content_cloner_mvp/research.py:213-223`
- Test: `facebook_content_cloner_mvp/tests/test_research_prompt.py`

**Interfaces:**
- Consumes: `PageProfile` (Task 1).
- Produces:
  - `render_prompt(template: str, page_name: str, hashtags: str) -> str`
  - `analyze(source, provider, keys, instruction: str | None = None) -> str` (None → `ANALYSIS_PROMPT`)
  - `create_new(source, analysis, provider, keys, instruction: str | None = None) -> str` (None → `CREATION_PROMPT`)

- [ ] **Step 1: Viết test lỗi trước**

```python
import research

def test_render_prompt_replaces_placeholders():
    assert research.render_prompt('Viết cho {page_name}. Tag: {hashtags}', 'Page A', '#a #b') == 'Viết cho Page A. Tag: #a #b'

def test_render_prompt_keeps_other_braces():
    t = 'Trả JSON {"title": "..."} cho {page_name}'
    assert research.render_prompt(t, 'X', '') == 'Trả JSON {"title": "..."} cho X'

def test_create_new_uses_custom_instruction(monkeypatch):
    seen = {}
    monkeypatch.setattr(research, 'generate_ai', lambda p, k, instr, src, n: seen.setdefault('i', instr) or 'ok')
    research.create_new('nguồn', '', 'gemini', {}, instruction='PROMPT RIÊNG')
    assert seen['i'] == 'PROMPT RIÊNG'

def test_analyze_default_instruction(monkeypatch):
    seen = {}
    monkeypatch.setattr(research, 'generate_ai', lambda p, k, instr, src, n: seen.setdefault('i', instr) or 'ok')
    research.analyze('nguồn', 'gemini', {})
    assert seen['i'] == research.ANALYSIS_PROMPT
```

- [ ] **Step 2: Chạy để thấy lỗi** — FAIL `has no attribute 'render_prompt'`.
- [ ] **Step 3: Sửa code** — thêm `render_prompt` (hai lần `str.replace`) và tham số `instruction`; ngoài ra không đổi gì khác.
- [ ] **Step 4: Chạy test đạt** — `py -3 -m pytest tests -v`: tất cả đều đạt.
- [ ] **Step 5: Commit** — `git commit -m "feat: page-specific AI prompts"`

---

### Task 4: `publisher.py` (đăng bài dùng chung)

**Files:**
- Create: `facebook_content_cloner_mvp/publisher.py`
- Test: `facebook_content_cloner_mvp/tests/test_publisher.py`

**Interfaces:**
- Consumes: `research.similarity`.
- Produces:
  - `class PublishError(Exception)`
  - `TEMPLATE_MARKERS = ('KỊCH BẢN REEL', 'TIÊU ĐỀ:', 'HOOK:', 'CAPTION FACEBOOK:')`
  - `@dataclass PublishPlan(text: str, kind: str, media_path: Path | None, scheduled_ts: int | None, check: dict)`; `kind` ∈ `'text' | 'photo' | 'video'`
  - `check_originality(source: str, text: str, max_ratio: float) -> dict` (kết quả `similarity` + `passed` + `limits`)
  - `parse_schedule(value: str, now: datetime) -> int` (timestamp Unix; báo `PublishError` nếu sai định dạng ISO hoặc nằm ngoài khoảng 600 giây – 30 ngày)
  - `prepare(source: str, text: str, max_ratio: float, media_path: str | None, scraped_media_root: Path, schedule: str | None = None, now: datetime | None = None, i_own_media: bool = False) -> PublishPlan`
  - `send(plan: PublishPlan, page_id: str, token: str, session, graph_version: str) -> str` (trả `post_id` hoặc `id`)
- Đuôi file: `.jpg .jpeg .png .webp` → `photo`; `.mp4 .mov` → `video`; đuôi khác → `PublishError`.
- Endpoint: `text` → `POST https://graph.facebook.com/{v}/{page_id}/feed` với `message`. `photo` → `/{page_id}/photos` với `caption` và file `source`. `video` → `https://graph-video.facebook.com/{v}/{page_id}/videos` với `description` và file `source`. Hẹn giờ thì thêm `published='false'`, `scheduled_publish_time=str(ts)`. Token gửi qua header `Authorization: Bearer`, không đặt trong URL. Lỗi HTTP → `PublishError` có kèm `app.friendly_error`-style message (dùng chung logic: `error.message` + `code`).

- [ ] **Step 1: Viết test lỗi trước**

```python
import datetime as dt
from pathlib import Path
import pytest, publisher as pb

NOW = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
GOOD = 'Chị Hạnh bán bún riêu ở đầu ngõ mười hai năm. Bạn còn nhớ ai từng tử tế với mình? #chuyendoi'
SRC = 'Một người thợ già kiểm tra từng đường chỉ trước khi giao đôi giày.'

def test_prepare_text_ok():
    plan = pb.prepare(SRC, GOOD, 0.35, None, Path('C:/nowhere'), now=NOW)
    assert plan.kind == 'text' and plan.scheduled_ts is None and plan.check['passed']

def test_prepare_rejects_copy():
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, SRC, 0.35, None, Path('C:/nowhere'), now=NOW)

def test_prepare_rejects_template_markers():
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, 'TIÊU ĐỀ: abc\n' + GOOD, 0.35, None, Path('C:/nowhere'), now=NOW)

def test_prepare_blocks_scraped_media(tmp_path):
    f = tmp_path / 'media' / 'p1' / 'a.jpg'; f.parent.mkdir(parents=True); f.write_bytes(b'x')
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, GOOD, 0.35, str(f), tmp_path / 'media', now=NOW)
    assert pb.prepare(SRC, GOOD, 0.35, str(f), tmp_path / 'media', now=NOW, i_own_media=True).kind == 'photo'

def test_prepare_video_kind_and_bad_extension(tmp_path):
    v = tmp_path / 'v.mp4'; v.write_bytes(b'x'); t = tmp_path / 'a.gif'; t.write_bytes(b'x')
    assert pb.prepare(SRC, GOOD, 0.35, str(v), tmp_path / 'media', now=NOW).kind == 'video'
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, GOOD, 0.35, str(t), tmp_path / 'media', now=NOW)

def test_parse_schedule_vietnam_time_and_bounds():
    assert pb.parse_schedule('2026-10-26T20:00', NOW) == int(dt.datetime(2026, 10, 26, 13, 0, tzinfo=dt.timezone.utc).timestamp())
    for bad in ['2026-10-26T19:05', '2026-12-30T20:00', 'ngày mai']:   # 5 phút nữa / quá 30 ngày / sai định dạng
        with pytest.raises(pb.PublishError):
            pb.parse_schedule(bad, NOW)

def test_send_text_scheduled_uses_header_not_url():
    calls = []
    class S:
        def post(self, url, headers, data, files, timeout):
            calls.append((url, headers, data))
            class R: ok = True; status_code = 200
            R.json = staticmethod(lambda: {'id': '1_2'})
            return R()
    plan = pb.PublishPlan(GOOD, 'text', None, 1800000000, {})
    assert pb.send(plan, '123', 'tok', S(), 'v26.0') == '1_2'
    url, headers, data = calls[0]
    assert url == 'https://graph.facebook.com/v26.0/123/feed' and 'tok' not in url
    assert headers['Authorization'] == 'Bearer tok'
    assert data == {'message': GOOD, 'published': 'false', 'scheduled_publish_time': '1800000000'}
```

- [ ] **Step 2: Chạy để thấy lỗi** — FAIL `No module named 'publisher'`.
- [ ] **Step 3: Viết `publisher.py`** theo Interfaces. `media_path` được `resolve()`; "nằm trong media cào về" nghĩa là `scraped_media_root.resolve() in path.parents`.
- [ ] **Step 4: Chạy test đạt** — 7 passed.
- [ ] **Step 5: Commit** — `git commit -m "feat: shared publisher module"`

---

### Task 5: `fbtool.py` đa Page

**Files:**
- Modify: `facebook_content_cloner_mvp/fbtool.py` (toàn bộ phần lệnh)
- Test: `facebook_content_cloner_mvp/tests/test_fbtool.py`

**Interfaces:**
- Consumes: `PageStore`, `PageProfile.public_dict` (T1); toàn bộ `page_data` (T2); `render_prompt`, `analyze(..., instruction)`, `create_new(..., instruction)` (T3); `publisher.prepare/send/check_originality/PublishError` (T4).
- Produces (CLI):
  - Cờ toàn cục `--page SLUG` đặt **trước** lệnh con; mặc định lấy `PageStore.active()`.
  - Store tạo bằng `PageStore(app.ROOT / 'pages.json', legacy=app.load_api_config())`.
  - `pages`: in ra danh sách `public_dict()`, mỗi mục có thêm `active: bool`.
  - `page-show [slug]`: in `public_dict()` của Page đó, gồm cả hai prompt đã render.
  - `list`, `show`, `analyze`, `create`, `save-draft`, `check`, `approve`, `publish`, `page-info` giữ nguyên tham số cũ nhưng thao tác trên Page đã chọn. `analyze`/`create` dùng prompt và `provider` của Page (nếu `provider` rỗng thì dùng provider chung). Ngưỡng trùng lấy `profile.max_similarity`. `page-info` dùng `fb_page_id`/`fb_page_token` của Page, thiếu thì báo lỗi và nêu tên Page.
  - Bỏ bảng `published` cũ và hàm `init_extra_tables`; thay bằng `app.init_db()` + `page_data.migrate(conn, DEFAULT_SLUG)`.
  - `publish` gọi `publisher.prepare` rồi (khi có `--yes`) `publisher.send` + `page_data.mark_published`. Không có `--yes` thì in ra `dry_run` gồm tên Page, kind, text.

- [ ] **Step 1: Viết test lỗi trước** (gọi CLI bằng subprocess, `FBCLONER_HOME=tmp_path`)

```python
import json, os, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]

def run(tmp_path, *args):
    env = {**os.environ, 'FBCLONER_HOME': str(tmp_path), 'PYTHONIOENCODING': 'utf-8'}
    r = subprocess.run([sys.executable, str(HERE / 'fbtool.py'), *args], capture_output=True, text=True, encoding='utf-8', env=env)
    return r.returncode, r.stdout, r.stderr

def test_pages_hides_token(tmp_path):
    (tmp_path / 'api_config.json').write_text(json.dumps({'fb_page_id': '1', 'fb_page_token': 'SECRET'}), encoding='utf-8')
    code, out, _ = run(tmp_path, 'pages')
    assert code == 0 and 'SECRET' not in out
    assert json.loads(out)[0]['has_token'] is True

def test_drafts_are_per_page(tmp_path):
    run(tmp_path, 'pages')  # tạo pages.json mặc định
    store = json.loads((tmp_path / 'pages.json').read_text(encoding='utf-8'))
    store['pages'].append({'slug': 'b', 'name': 'B'})
    (tmp_path / 'pages.json').write_text(json.dumps(store, ensure_ascii=False), encoding='utf-8')
    subprocess.run([sys.executable, '-c', f"import sys; sys.path.insert(0, r'{HERE}'); import app; app.init_db(); app.import_json(r'{HERE / 'sample_posts.json'}')"],
                   env={**os.environ, 'FBCLONER_HOME': str(tmp_path)}, check=True)
    f = tmp_path / 'd.txt'; f.write_text('Chị Hạnh bán bún riêu ở đầu ngõ mười hai năm, nhớ khẩu vị từng khách quen.', encoding='utf-8')
    assert run(tmp_path, '--page', 'b', 'save-draft', 'demo_001', '--file', str(f))[0] == 0
    _, out_b, _ = run(tmp_path, '--page', 'b', 'show', 'demo_001')
    _, out_a, _ = run(tmp_path, 'show', 'demo_001')
    assert json.loads(out_b)['draft'].startswith('Chị Hạnh') and json.loads(out_a)['draft'] is None

def test_unknown_page_errors(tmp_path):
    code, _, err = run(tmp_path, '--page', 'khong-co', 'list')
    assert code == 1 and 'khong-co' in err
```

- [ ] **Step 2: Chạy để thấy lỗi** — FAIL (`unrecognized arguments: --page` / lệnh `pages` chưa có).
- [ ] **Step 3: Viết lại các hàm `cmd_*`** theo Interfaces. Giữ nguyên dạng output JSON.
- [ ] **Step 4: Chạy test đạt** — `py -3 -m pytest tests -v`: tất cả đều đạt.
- [ ] **Step 5: Commit** — `git commit -m "feat: fbtool supports multiple pages"`

---

### Task 6: Dải ảnh/video (`media_view.py`)

**Files:**
- Create: `facebook_content_cloner_mvp/media_view.py`
- Test: `facebook_content_cloner_mvp/tests/test_media_view.py`

**Interfaces:**
- Consumes: các dòng của bảng `media` (`kind`, `local_path`, `url`).
- Produces:
  - `@dataclass MediaItem(kind: str, path: Path | None, url: str)`, với `path=None` khi `local_path` rỗng hoặc file không còn.
  - `media_items(rows) -> list[MediaItem]`: ảnh xếp trước video, giữ thứ tự gốc trong từng nhóm.
  - `make_thumbnail(path: Path, max_px: int = 160) -> PIL.Image.Image | None` (`ImageOps.contain`; ảnh lỗi → None).
  - `class MediaStrip(ttk.Frame)`: `__init__(parent, on_download: Callable[[], None])`; `show(items: list[MediaItem]) -> None`.
    - Dùng một `Canvas` cuộn ngang, cao 190px. Ảnh có file → ô thu nhỏ, bấm vào thì `os.startfile(path)`.
    - Video có file → ô tối màu ghi "▶ VIDEO", tên file và dung lượng MB; bấm vào thì `os.startfile`.
    - Mục không có file → ô xám "Chưa tải" và chỉ hiện nút "⬇ Tải media còn thiếu" (gọi `on_download`) khi có ít nhất một mục như vậy.
    - Danh sách rỗng → nhãn "(Bài này không có ảnh/video)".
    - Giữ tham chiếu `ImageTk.PhotoImage` trong `self._images` để ảnh không bị thu gom mất.

- [ ] **Step 1: Viết test lỗi trước**

```python
from pathlib import Path
from PIL import Image
import media_view as mv

def test_media_items_missing_file(tmp_path):
    img = tmp_path / 'a.jpg'; Image.new('RGB', (10, 10)).save(img)
    rows = [{'kind': 'video', 'local_path': '', 'url': 'https://v'},
            {'kind': 'image', 'local_path': str(tmp_path / 'gone.jpg'), 'url': 'https://g'},
            {'kind': 'image', 'local_path': str(img), 'url': 'https://i'}]
    items = mv.media_items(rows)
    assert [(i.kind, i.path) for i in items] == [('image', None), ('image', img), ('video', None)]

def test_make_thumbnail_size(tmp_path):
    p = tmp_path / 'big.png'; Image.new('RGB', (800, 400)).save(p)
    assert mv.make_thumbnail(p, 160).size == (160, 80)

def test_make_thumbnail_corrupt_returns_none(tmp_path):
    p = tmp_path / 'bad.jpg'; p.write_bytes(b'not an image')
    assert mv.make_thumbnail(p) is None

def test_media_strip_renders_without_error(tmp_path):
    from tkinter import Tk
    root = Tk(); root.withdraw()
    try:
        s = mv.MediaStrip(root, on_download=lambda: None)
        s.show([mv.MediaItem('image', None, 'u'), mv.MediaItem('video', None, 'v')]); s.show([])
    finally:
        root.destroy()
```

- [ ] **Step 2: Chạy để thấy lỗi** — FAIL `No module named 'media_view'`.
- [ ] **Step 3: Viết `media_view.py`** theo Interfaces.
- [ ] **Step 4: Chạy test đạt** — 4 passed.
- [ ] **Step 5: Commit** — `git commit -m "feat: media thumbnail strip"`

---

### Task 7: Hộp thoại quản lý Page (`page_dialog.py`)

**Files:**
- Create: `facebook_content_cloner_mvp/page_dialog.py`
- Test: `facebook_content_cloner_mvp/tests/test_page_dialog.py`

**Interfaces:**
- Consumes: `PageStore`, `PageProfile`, `GENERIC_*_PROMPT`, `NHAN_TAM_CREATION_PROMPT`, `DEFAULT_SLUG` (T1).
- Produces: `class PageManagerDialog(Toplevel)`, khởi tạo bằng `__init__(parent, store: PageStore, test_token: Callable[[str, str], str], on_saved: Callable[[str], None])`.
  - Bên trái: `Listbox` tên các Page, cùng nút "＋ Page mới" và "🗑 Xóa".
  - Bên phải: biểu mẫu với các khóa trong `self.vars: dict[str, StringVar]` gồm `name`, `fb_page_id`, `fb_page_token`, `provider`, `hashtags`, `max_similarity`. Ô token dùng `show='●'`. `provider` là `Combobox` với các giá trị `['', 'gemini', 'cloudflare', 'openai']`, nhãn hiển thị "(dùng mặc định)" cho giá trị rỗng.
  - Hai ô `Text` `self.analysis_text` và `self.creation_text` (cao 8 dòng, có thanh cuộn), kèm dòng gợi ý "Dùng {page_name}, {hashtags} trong prompt".
  - Nút "↺ Khôi phục prompt mặc định": slug `DEFAULT_SLUG` lấy `NHAN_TAM_CREATION_PROMPT`, các Page khác lấy `GENERIC_*`.
  - Nút "🔍 Kiểm tra token" gọi `test_token(page_id, token)`, hiện tên Page trả về hoặc lỗi.
  - Nút "💾 Lưu" gọi `self.save() -> bool`.
  - `save()`: tạo `PageProfile` từ biểu mẫu. `max_similarity` không phải số → hiện lỗi và trả `False`. Gọi `store.save`; nếu `ValueError` thì hiện `messagebox.showerror` và trả `False`. Lưu thành công → gọi `on_saved(slug)` và trả `True`.
  - Đổi Page trên Listbox khi biểu mẫu chưa lưu → hỏi `askyesno` có lưu không.
  - Xóa Page → hỏi xác nhận, gọi `store.delete`; nếu là Page cuối thì hiện lỗi.
  - Cửa sổ 980×720, `transient` + `grab_set`.

- [ ] **Step 1: Viết test lỗi trước** (vá `messagebox` để test không bị treo)

```python
import pytest
from tkinter import Tk
import page_dialog as pdlg
from pages import PageStore

@pytest.fixture
def root():
    r = Tk(); r.withdraw(); yield r; r.destroy()

def test_new_page_saved(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pdlg.messagebox, 'showerror', lambda *a, **k: None)
    store = PageStore(tmp_path / 'pages.json'); saved = []
    d = pdlg.PageManagerDialog(root, store, test_token=lambda i, t: 'X', on_saved=saved.append)
    d.new_page()
    d.vars['name'].set('Mẹo Văn Phòng'); d.vars['hashtags'].set('#meo'); d.vars['max_similarity'].set('0.3')
    d.creation_text.delete('1.0', 'end'); d.creation_text.insert('1.0', 'Prompt cho {page_name}')
    assert d.save() is True
    p = store.get('meo-van-phong')
    assert (p.hashtags, p.max_similarity, p.creation_prompt) == ('#meo', 0.3, 'Prompt cho {page_name}')
    assert saved == ['meo-van-phong']

def test_invalid_similarity_not_saved(root, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(pdlg.messagebox, 'showerror', lambda *a, **k: errors.append(a))
    store = PageStore(tmp_path / 'pages.json')
    d = pdlg.PageManagerDialog(root, store, test_token=lambda i, t: 'X', on_saved=lambda s: None)
    d.vars['max_similarity'].set('abc')
    assert d.save() is False and errors
```

- [ ] **Step 2: Chạy để thấy lỗi** — FAIL `No module named 'page_dialog'`.
- [ ] **Step 3: Viết `page_dialog.py`** theo Interfaces. Hàm `new_page()` xóa biểu mẫu, đặt slug rỗng và điền prompt `GENERIC_*`.
- [ ] **Step 4: Chạy test đạt** — 2 passed.
- [ ] **Step 5: Commit** — `git commit -m "feat: page manager dialog"`

---

### Task 8: Hộp thoại đăng bài (`publish_dialog.py`)

**Files:**
- Create: `facebook_content_cloner_mvp/publish_dialog.py`
- Test: `facebook_content_cloner_mvp/tests/test_publish_dialog.py`

**Interfaces:**
- Consumes: `PageProfile` (T1), `publisher.prepare/send/PublishError` (T4), `page_data.mark_published` (T2).
- Produces: `class PublishDialog(Toplevel)`, khởi tạo bằng `__init__(parent, profile: PageProfile, post_id: str, source: str, text: str, media_root: Path, do_send: Callable[[publisher.PublishPlan], str], on_done: Callable[[str], None])`.
  - Hiện "Đăng lên: <tên Page>" và nội dung sẽ đăng (`Text` chỉ đọc).
  - Ô file đính kèm có nút "Chọn…" (`filedialog`, lọc ảnh/video) và nút "✕" để bỏ chọn.
  - Ô hẹn giờ `self.schedule_var`, để trống nghĩa là đăng ngay, có gợi ý định dạng `2026-10-27T20:00`.
  - Checkbox `self.own_media_var` "Tôi có quyền dùng file này".
  - Nút "🚀 Đăng" gọi `self.submit()`: chạy `publisher.prepare(...)` với `profile.max_similarity`. Nếu `PublishError` thì hiện lỗi. Nếu thành công thì hỏi `askyesno` lần cuối, sau đó chạy `do_send(plan)` trong một luồng riêng; xong thì gọi `on_done(fb_id)` qua `after(0, …)` và đóng hộp thoại.
  - Nếu Page chưa có `fb_page_id` hoặc token → nút Đăng bị khóa, kèm dòng đỏ "Chưa cấu hình ID/token cho Page này".

- [ ] **Step 1: Viết test lỗi trước**

```python
import pytest
from pathlib import Path
from tkinter import Tk
import publish_dialog as pdl
from pages import PageProfile

GOOD = 'Chị Hạnh bán bún riêu ở đầu ngõ mười hai năm. Bạn còn nhớ ai từng tử tế với mình?'

@pytest.fixture
def root():
    r = Tk(); r.withdraw(); yield r; r.destroy()

def test_submit_blocked_without_token(root, tmp_path):
    d = pdl.PublishDialog(root, PageProfile(slug='a', name='A'), 'p1', 'nguồn', GOOD, tmp_path, do_send=lambda p: 'x', on_done=lambda f: None)
    assert str(d.publish_btn['state']) == 'disabled'

def test_submit_rejects_bad_schedule(root, tmp_path, monkeypatch):
    errs = []; monkeypatch.setattr(pdl.messagebox, 'showerror', lambda *a, **k: errs.append(a))
    prof = PageProfile(slug='a', name='A', fb_page_id='1', fb_page_token='t')
    d = pdl.PublishDialog(root, prof, 'p1', 'nguồn', GOOD, tmp_path, do_send=lambda p: 'x', on_done=lambda f: None)
    d.schedule_var.set('ngày mai')
    d.submit()
    assert errs
```

- [ ] **Step 2: Chạy để thấy lỗi** — FAIL `No module named 'publish_dialog'`.
- [ ] **Step 3: Viết `publish_dialog.py`** theo Interfaces.
- [ ] **Step 4: Chạy test đạt** — `py -3 -m pytest tests -v`: tất cả đều đạt.
- [ ] **Step 5: Commit** — `git commit -m "feat: publish dialog"`

---

### Task 9: Lắp vào `app.py`

**Files:**
- Modify: `facebook_content_cloner_mvp/app.py` (`App.__init__` 227-317, `start_auto_scrape` 337-400, `refresh`/`select_post`/`save_draft`/`approve` 461-515, `analyze_post`/`create_post` ~595-668, `download` ~688, `__main__`)
- Test: `facebook_content_cloner_mvp/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: tất cả các Task trước.
- Produces (thuộc tính của `App` mà test dùng):
  - `self.store: PageStore` (tạo bằng `PageStore(ROOT / 'pages.json', legacy=load_api_config())`).
  - `self.page_combo: ttk.Combobox` liệt kê tên Page. Chọn Page → `store.set_active` → `refresh()` và `select_post()`.
  - `self.url_text: Text` (cao 3 dòng, thay `self.url_entry`/`self.target_url`); `start_auto_scrape` đọc `self.url_text.get('1.0','end-1c')`.
  - `self.media_strip: MediaStrip` nằm ngay dưới ô "Nguồn & Media"; `select_post` gọi `self.media_strip.show(media_items(rows))`; `on_download` gọi hàm `download()` sẵn có.
  - `self.table` có thêm cột `status` (nhãn "Trạng thái", rộng 90): giá trị là `status` hoặc "—"; danh sách lấy từ `page_data.list_posts(conn, active_slug)`.
  - `analyze_post`/`create_post` dùng `render_prompt(profile.analysis_prompt | creation_prompt, profile.name, profile.hashtags)` và `profile.provider or self.api_config['provider']`. Phân tích lưu bằng `page_data.save_analysis`. Sáng tạo xong thì tự `page_data.save_draft(..., 'review')` và cập nhật dòng trạng thái kèm tỉ lệ trùng.
  - `save_draft`/`approve` dùng `page_data`. `approve` chặn bằng `publisher.check_originality(source, body, profile.max_similarity)` và hiện lỗi kèm các cụm trùng nếu không đạt.
  - Thêm nút "🚀 Đăng lên Page" (mở `PublishDialog`; nháp chưa ở trạng thái `approved` thì cảnh báo) và nút "⚙️ Quản lý Page" (mở `PageManagerDialog`, `on_saved` nạp lại combobox).
  - Phần cài đặt API giữ nguyên, đổi nhãn thành "⚙️ Khóa AI (dùng chung)".
  - `__main__`: `init_db()` + `page_data.migrate(conn, DEFAULT_SLUG)`.
  - Tiêu đề cửa sổ: `Facebook Content Cloner — Page: <tên Page đang chọn>`.
  - Xóa `ai_rewrite`, `rewrite` (code chết, tham chiếu `self.openai` không còn tồn tại).

- [ ] **Step 1: Viết smoke test lỗi trước**

```python
from tkinter import Tk
import app, page_data
from pages import PageProfile, DEFAULT_SLUG

def test_app_switches_page_and_shows_per_page_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'ROOT', tmp_path); monkeypatch.setattr(app, 'DB', tmp_path / 'c.sqlite3')
    app.init_db(); app.import_json(str(app.Path(app.__file__).with_name('sample_posts.json')))
    with app.db() as c:
        page_data.migrate(c, DEFAULT_SLUG)
        page_data.save_draft(c, 'demo_001', DEFAULT_SLUG, 'nháp A')
    root = Tk(); root.withdraw()
    try:
        a = app.App(root)
        a.store.save(PageProfile(slug='b', name='Page B'))
        a.reload_pages()
        a.table.selection_set('demo_001'); a.select_post()
        assert a.draft.get('1.0', 'end-1c') == 'nháp A'
        a.page_combo.set('Page B'); a.on_page_change()
        a.table.selection_set('demo_001'); a.select_post()
        assert a.draft.get('1.0', 'end-1c') == ''
        assert 'Page B' in root.title()
    finally:
        root.destroy()
```
(`reload_pages()` và `on_page_change(event=None)` là hai phương thức mới của `App`.)

- [ ] **Step 2: Chạy để thấy lỗi** — FAIL `AttributeError: 'App' object has no attribute 'store'`.
- [ ] **Step 3: Sửa `app.py`** theo Interfaces.
- [ ] **Step 4: Chạy test đạt** — `py -3 -m pytest tests -v`: tất cả đều đạt.
- [ ] **Step 5: Kiểm tra bằng tay** với `FBCLONER_HOME` trỏ tới thư mục tạm, chạy `py -3 app.py`:
  1. Nhập JSON mẫu.
  2. Tạo Page thứ hai bằng "Quản lý Page".
  3. Đổi qua lại hai Page → nháp tách riêng.
  4. Dán 2 link vào ô URL (2 dòng) → cào được.
  5. Chọn bài có ảnh → thấy ảnh thu nhỏ, bấm vào thì mở ảnh.
  6. Mở Đăng khi Page chưa có token → nút bị khóa.
- [ ] **Step 6: Commit** — `git commit -m "feat: multi-page GUI with media preview and per-page AI prompts"`

---

### Task 10: Tài liệu và skill theo đa Page

**Files:**
- Modify: `CLAUDE.md`, `facebook_content_cloner_mvp/README.md`
- Rename + Modify: `.claude/skills/sang-tao-nhan-tam` → `.claude/skills/sang-tao-noi-dung`; `.claude/skills/quy-trinh-nhan-tam` → `.claude/skills/quy-trinh-noi-dung`
- Modify: `.claude/skills/cao-bai-facebook/SKILL.md`, `.claude/skills/dang-bai-page/SKILL.md`

**Interfaces:**
- Consumes: CLI ở Task 5 (`--page`, `pages`, `page-show`).

- [ ] **Step 1: Cập nhật nội dung**
  - Các skill bỏ giả định một Page. Bước đầu tiên là `py -3 fbtool.py pages` để chọn Page: người dùng nêu tên Page nào thì dùng Page đó, không nêu thì dùng Page đang chọn. Mọi lệnh sau đều thêm `--page <slug>`.
  - `sang-tao-noi-dung` đọc `py -3 fbtool.py --page <slug> page-show` và viết theo `creation_prompt` của Page đó. Giữ `references/giong-van-page.md`, đổi tên thành `vi-du-chuyen-doi-nhan-tam.md` và dùng làm ví dụ cho Page mặc định.
  - `dang-bai-page`: token cấu hình trong GUI → "⚙️ Quản lý Page", hoặc sửa tay `pages.json`. Bỏ phần hướng dẫn biến môi trường `FB_PAGE_*`.
  - `CLAUDE.md`: thêm `pages.py`, `page_data.py`, `publisher.py`, `media_view.py`, `page_dialog.py`, `publish_dialog.py`, file `pages.json`, các bảng `page_*`, lệnh test `py -3 -m pytest tests -v`; bỏ dòng "Không có test tự động".
  - `README.md`: thêm mục "Quản lý nhiều Page" và "Xem ảnh/video"; sửa dòng "không tự đăng".
- [ ] **Step 2: Kiểm tra** — `grep -rn "FB_PAGE_ID\|nhan-tam\b" CLAUDE.md .claude facebook_content_cloner_mvp/README.md`. Chỉ còn `chuyen-doi-nhan-tam` (slug mặc định) và tên file ví dụ.
- [ ] **Step 3: Commit** — `git commit -m "docs: multi-page docs and skills"`
