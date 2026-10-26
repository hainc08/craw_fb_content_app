# Facebook Content Research & Creator — page "Chuyện Đời & Nhân Tâm"

Công cụ Windows để: cào bài công khai trên Facebook → phân tích → sáng tạo lại thành nội dung **mới** theo
giọng page "Chuyện Đời & Nhân Tâm" → duyệt → đăng lên Page.

## Cấu trúc

```
start_windows.bat                 # mở GUI (gọi facebook_content_cloner_mvp/start_windows.bat)
facebook_content_cloner_mvp/
  app.py        # GUI Tkinter + SQLite + tải media + Graph API đọc Page (fetch_page)
  scraper.py    # cào URL: Page/Profile → Playwright headless; Reel/Video/Post → yt-dlp (fallback Playwright)
  research.py   # AI: Gemini (mặc định, tự thử nhiều model) / Cloudflare Llama 3.1 / OpenAI; similarity()
  fbtool.py     # CLI không GUI dùng lại các module trên — các skill dùng file này
  sample_posts.json, build_exe.bat (PyInstaller → dist/FacebookContentCloner.exe)
.claude/skills/   # skill của dự án (xem bên dưới)
```

## Dữ liệu
- Thư mục dữ liệu: `%USERPROFILE%\Documents\FacebookContentCloner` (đổi bằng biến `FBCLONER_HOME`).
  - `content.sqlite3`: bảng `posts` (nguồn), `media`, `research` (phân tích), `drafts` (body, status),
    `published` (do fbtool tạo: post_id → fb_post_id).
  - `media/<post_id>/`: ảnh/video đã cào — **chỉ để tham khảo, không đăng lại**.
  - `api_config.json`: khóa AI (`provider`, `gemini_key`, `cloudflare_*`, `openai_key`) và tùy chọn
    `fb_page_id`, `fb_page_token`. Không bao giờ in giá trị khóa ra màn hình hay commit.
- Trạng thái nháp: `review` → `approved` → `published` / `scheduled`.

## CLI (chạy trong `facebook_content_cloner_mvp/`, Python 3.14 qua `py -3`)
```
py -3 fbtool.py scrape <url...> [--limit 5] [--no-media]
py -3 fbtool.py list [--status none|review|approved|published|scheduled]
py -3 fbtool.py show <id>
py -3 fbtool.py analyze <id> [--provider gemini|cloudflare|openai]   # lưu vào research
py -3 fbtool.py create <id>                                          # AI của app viết, chỉ in ra
py -3 fbtool.py save-draft <id> --file draft.txt                     # lưu nháp + tự kiểm tra trùng
py -3 fbtool.py check <id>        # exit 2 nếu quá giống nguồn
py -3 fbtool.py approve <id>      # chỉ duyệt khi qua kiểm tra trùng
py -3 fbtool.py page-info         # kiểm tra token Page
py -3 fbtool.py publish <id> [--image f | --video f] [--schedule 2026-10-27T20:00] [--yes]
```
Output là JSON (UTF-8). `publish` mặc định **chạy thử**; chỉ thêm `--yes` sau khi người dùng xác nhận.

## Quy tắc nội dung (bắt buộc)
- Bài nguồn chỉ là **tham khảo chủ đề / cơ chế cảm xúc**. Bản mới phải có nhân vật, bối cảnh, diễn biến,
  lời thoại khác hẳn; không paraphrase câu-đổi-câu. Ngưỡng tự động: `sequence_ratio ≤ 0.35` và không trùng
  cụm 7 từ nào (`fbtool.py` chặn duyệt/đăng nếu vượt).
- Không đăng lại ảnh/video/nhạc cào về (fbtool chặn file nằm trong `media/`). Dùng ảnh tự tạo/AI
  hoặc làm video bằng skill `ke-chuyen-video`.
- Không bịa trích dẫn gán cho Dale Carnegie hay người nổi tiếng; không chép văn bản sách Đắc Nhân Tâm.
- Chuyện hư cấu thì không viết như trải nghiệm có thật của page; không nêu tên người thật.
- Chỉ cào nội dung **công khai**, số lượng nhỏ (≤ 20 bài/lần), không đăng nhập, không vượt CAPTCHA/chặn.
- Đăng bài là hành động công khai: luôn cho người dùng xem bản cuối và xác nhận trước khi `--yes`.

## Skill dự án
| Skill | Dùng khi |
|---|---|
| `cao-bai-facebook` | Cào bài/Reels công khai từ link Page/bài viết vào DB |
| `sang-tao-nhan-tam` | Phân tích bài nguồn và viết lại thành bài mới theo giọng page |
| `dang-bai-page` | Đăng / hẹn giờ bài đã duyệt lên Page Chuyện Đời & Nhân Tâm |
| `quy-trinh-nhan-tam` | Làm trọn: cào → chọn bài → sáng tạo → duyệt → đăng (tùy chọn làm video) |

Skill toàn cục liên quan: `ke-chuyen-video` (biến câu chuyện thành Reel 9:16 cho page này).

## Lưu ý kỹ thuật
- Playwright cần trình duyệt: `py -3 -m playwright install chromium` nếu báo thiếu.
- Facebook thường chặn khách chưa đăng nhập → Page có thể trả ít bài hoặc toàn chữ rác giao diện
  ("Thích", "Bình luận"...). Khi đó dùng link bài/Reel cụ thể (yt-dlp ổn định hơn) hoặc dán tay qua GUI.
- `created_time` của bài cào bằng Playwright là thời điểm cào, không phải ngày đăng thật.
- Graph API: `GRAPH_VERSION = 'v26.0'` trong app.py. Đăng cần Page Access Token có quyền
  `pages_manage_posts`, `pages_read_engagement`. Hẹn giờ: 10 phút – 30 ngày.
- Không có test tự động; kiểm tra bằng `FBCLONER_HOME=<thư mục tạm>` + `sample_posts.json` để khỏi đụng DB thật.
