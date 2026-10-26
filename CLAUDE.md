# Facebook Content Research & Creator — đa Page

Công cụ Windows để: cào bài công khai trên Facebook → xem nội dung + ảnh/video → AI viết lại thành nội dung
**mới** theo prompt riêng của từng Page → duyệt → đăng lên Page. Hỗ trợ nhiều Page (mặc định có
"Chuyện Đời & Nhân Tâm", slug `chuyen-doi-nhan-tam`).

## Cấu trúc (`facebook_content_cloner_mvp/`)
| File | Việc |
|---|---|
| `app.py` | GUI Tkinter: chọn Page, ô URL nhiều dòng, danh sách bài + trạng thái theo Page, dải ảnh/video, phân tích/sáng tạo/duyệt/đăng. Cũng chứa `db()`, `init_db()`, `insert_post`, `save_media`, `graph_get` |
| `scraper.py` | Cào URL: Page/Profile → Playwright headless; Reel/Video/Post → yt-dlp (fallback Playwright) |
| `research.py` | AI: Gemini (mặc định, tự thử nhiều model) / Cloudflare Llama 3.1 / OpenAI; `render_prompt`, `similarity` |
| `pages.py` | `PageProfile`, `PageStore` (đọc/ghi `pages.json`, Page đang chọn), prompt mặc định |
| `page_data.py` | Nháp / phân tích / đã đăng theo cặp (bài nguồn, Page) |
| `publisher.py` | Kiểm tra (trùng, khung mẫu, media cào về, giờ hẹn) + gửi Graph API — dùng chung GUI và CLI |
| `media_view.py` | Dải ảnh thu nhỏ/ô video (Pillow) |
| `page_dialog.py` / `publish_dialog.py` | Hộp thoại Quản lý Page / Đăng bài |
| `fbtool.py` | CLI không GUI — các skill dùng file này |
| `tests/` | pytest: `py -3 -m pytest tests -v` (chạy trong `facebook_content_cloner_mvp/`) |

## Dữ liệu
- Thư mục: `%USERPROFILE%\Documents\FacebookContentCloner` (đổi bằng biến `FBCLONER_HOME`).
  - `pages.json`: `{"active": slug, "pages": [PageProfile...]}` — tên, `fb_page_id`, `fb_page_token`, `provider`
    ('' = dùng chung), `hashtags`, `analysis_prompt`, `creation_prompt` (placeholder `{page_name}`, `{hashtags}`),
    `max_similarity`. File hỏng → tự đổi tên `.bak` và tạo lại Page mặc định.
  - `api_config.json`: khóa AI dùng chung (`provider`, `gemini_key`, `cloudflare_*`, `openai_key`).
  - `content.sqlite3`: `posts`, `media` (dùng chung mọi Page); `page_drafts`, `page_research`, `page_published`
    (khóa `(post_id, page_slug)`). Bảng cũ `drafts`/`research` chỉ còn để migrate sang Page mặc định.
  - `media/<post_id>/`: ảnh/video cào về — **chỉ để tham khảo, không đăng lại**.
- Token Page chỉ nằm trong `pages.json`: không vào SQLite, không in ra màn hình/log (`public_dict()` bỏ token).
- Trạng thái nháp: `review` → `approved` → `published` / `scheduled`.

## CLI (trong `facebook_content_cloner_mvp/`, cờ `--page` đứng TRƯỚC lệnh con)
```
py -3 fbtool.py pages                                  # danh sách Page (không token)
py -3 fbtool.py --page <slug> page-show                # cấu hình + prompt đã render
py -3 fbtool.py scrape <url...> [--limit 5] [--no-media]
py -3 fbtool.py --page <slug> list [--status none|review|approved|published|scheduled]
py -3 fbtool.py --page <slug> show <id>
py -3 fbtool.py --page <slug> analyze|create <id> [--provider ...]
py -3 fbtool.py --page <slug> save-draft <id> --file draft.txt
py -3 fbtool.py --page <slug> check|approve <id>
py -3 fbtool.py --page <slug> page-info
py -3 fbtool.py --page <slug> publish <id> [--image f | --video f] [--schedule 2026-10-27T20:00] [--yes]
```
Output JSON UTF-8. `publish` mặc định **chạy thử**; chỉ thêm `--yes` sau khi người dùng xác nhận.

## Quy tắc nội dung (bắt buộc)
- Bài nguồn chỉ là tham khảo chủ đề / cơ chế cảm xúc. Bản mới phải có nhân vật, bối cảnh, diễn biến, lời thoại
  khác hẳn. Ngưỡng tự động: `sequence_ratio ≤ max_similarity` của Page (mặc định 0.35) và 0 cụm 7 từ chung.
- Không đăng lại ảnh/video/nhạc cào về (publisher chặn file trong `media/`).
- Không bịa trích dẫn gán cho người nổi tiếng; không chép văn bản sách có bản quyền; không nêu tên người thật.
- Chỉ cào nội dung công khai, ít một (≤ 20 bài/lần), không đăng nhập, không vượt CAPTCHA/chặn.
- Đăng bài là hành động công khai: luôn cho người dùng xem bản cuối và xác nhận.

## Skill dự án (`.claude/skills/`)
| Skill | Dùng khi |
|---|---|
| `cao-bai-facebook` | Cào bài/Reels công khai vào DB |
| `sang-tao-noi-dung` | Viết lại bài nguồn theo prompt của một Page |
| `dang-bai-page` | Đăng / hẹn giờ bài đã duyệt lên một Page |
| `quy-trinh-noi-dung` | Làm trọn cho một hoặc nhiều Page |

Skill toàn cục liên quan: `ke-chuyen-video` (Reel 9:16 cho Page Chuyện Đời & Nhân Tâm).

## Lưu ý kỹ thuật
- Playwright cần trình duyệt: `py -3 -m playwright install chromium`.
- Cào link Page: Facebook bật hộp "Xem thêm từ …" khóa cuộn với khách chưa đăng nhập; scraper bấm nút X của hộp
  rồi cuộn, lấy khối `div[aria-posinset]`. Khách chỉ xem được ~8–10 bài đầu → muốn nhiều hơn thì dán link từng bài.
  Không đăng nhập, không lách giới hạn đó.
- Reel/video: caption + MP4 lấy qua yt-dlp; chọn bản `hd`/`sd` ghép sẵn tiếng (các luồng DASH khác chỉ có hình
  hoặc chỉ có tiếng). Description bị Facebook cắt ("...") thì lấy caption trong title.
- `created_time` của bài cào bằng Playwright là lúc cào, không phải ngày đăng.
- Graph API `v26.0`; đăng cần token quyền `pages_manage_posts`; hẹn giờ 10 phút – 30 ngày, giờ không múi = giờ VN.
- Tk không an toàn đa luồng: luồng phụ không gọi widget; `publish_dialog` dùng hàng đợi + `after()` để nhận kết quả.
- Test GUI dựng `Tk()` ẩn — cần phiên Windows có màn hình. Dev deps: `py -3 -m pip install -r requirements-dev.txt`.
