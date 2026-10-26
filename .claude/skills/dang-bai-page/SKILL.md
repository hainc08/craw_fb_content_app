---
name: dang-bai-page
description: Đăng hoặc hẹn giờ bài viết đã duyệt (chữ, kèm ảnh, hoặc video) lên một Facebook Page đã cấu hình (Chuyện Đời & Nhân Tâm hoặc Page khác) qua Meta Graph API bằng fbtool.py. Dùng khi người dùng nói "đăng bài", "post lên page", "lên lịch đăng", "hẹn giờ đăng", "publish", hoặc muốn đưa nội dung/video đã làm lên page.
---

# Đăng bài lên Facebook Page

Thư mục: `D:\facebook_content_research_creator_windows\facebook_content_cloner_mvp`.
Đăng bài là hành động **công khai, khó rút lại** — luôn chạy thử và chờ người dùng xác nhận.
Người dùng cũng có thể tự đăng trong GUI: chọn Page ở thanh trên → chọn bài → "🚀 Đăng lên Page".

## Chọn Page và kiểm tra token
1. `py -3 fbtool.py pages` → chọn slug (theo tên người dùng nêu, hoặc Page `active`). `has_token: false` → chưa
   cấu hình.
2. Cấu hình: người dùng mở GUI → "⚙️ Quản lý Page" → điền Facebook Page ID (số) và Page Access Token (quyền
   `pages_manage_posts`, `pages_read_engagement`) → "🔍 Kiểm tra token" → Lưu. (Hoặc tự sửa
   `%USERPROFILE%\Documents\FacebookContentCloner\pages.json`.) Không yêu cầu dán token vào chat, không in token.
   Lấy token: Meta for Developers → App → Graph API Explorer → chọn quyền → `GET /me/accounts` → `id` và
   `access_token` của page; nên dùng token dài hạn.
3. `py -3 fbtool.py --page <slug> page-info` → phải thấy đúng tên Page. Sai Page thì dừng.

## Quy trình đăng
1. Bài đã duyệt: `py -3 fbtool.py --page <slug> list --status approved`. Chưa duyệt → skill `sang-tao-noi-dung`.
2. Hình thức:
   - Chỉ chữ: không thêm cờ.
   - Kèm ảnh: `--image <file>` (ảnh tự làm/AI, vd ảnh bìa `D:\ke-chuyen-video\out\<id>\thumbnail_<id>.png`).
   - Video: `--video <file.mp4>` (vd `D:\ke-chuyen-video\out\<id>\video_<id>.mp4`).
   - Hẹn giờ: `--schedule 2026-10-27T20:00` (giờ Việt Nam, cách hiện tại 10 phút–30 ngày).
3. **Chạy thử:** `py -3 fbtool.py --page <slug> publish <id> [cờ...]` → cho người dùng xem tên Page, nguyên văn
   `text`, loại bài, file, giờ hẹn. Hỏi xác nhận rõ ràng.
4. Đồng ý → chạy lại y hệt kèm `--yes`. Báo `fb_post_id` và link.
5. Có ảnh/giọng AI → nhắc bật nhãn "Nội dung do AI tạo" nếu cần.

## Lỗi thường gặp
- "media cào từ bài người khác" → không đăng file đó. Chỉ thêm `--i-own-media` khi người dùng khẳng định có quyền.
- "quá giống bài nguồn" / "còn các mục khung" → quay lại `sang-tao-noi-dung`.
- "chưa có Facebook Page ID / token" → cấu hình như trên.
- Meta 190: token hết hạn. 200/10: thiếu quyền `pages_manage_posts`. 368: page bị hạn chế — dừng, báo người dùng.
- "đã đăng lên …" → mỗi bài chỉ đăng một lần trên mỗi Page.

Không đăng quá 3–4 bài/ngày mỗi Page; không đăng hàng loạt bài giống nhau lên nhiều Page.
