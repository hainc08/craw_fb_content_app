---
name: dang-bai-page
description: Đăng hoặc hẹn giờ bài viết đã duyệt (chữ, kèm ảnh, hoặc video) lên Facebook Page "Chuyện Đời & Nhân Tâm" qua Meta Graph API bằng fbtool.py. Dùng khi người dùng nói "đăng bài", "post lên page", "lên lịch đăng", "hẹn giờ đăng", "publish", hoặc muốn đưa nội dung/video đã làm lên page.
---

# Đăng bài lên Page "Chuyện Đời & Nhân Tâm"

Thư mục: `D:\facebook_content_research_creator_windows\facebook_content_cloner_mvp`.
Đăng bài là hành động **công khai, khó rút lại** — luôn chạy thử và chờ người dùng xác nhận.

## Lần đầu: cấu hình token
Cần `FB_PAGE_ID` và `FB_PAGE_TOKEN` (Page Access Token quyền `pages_manage_posts`, `pages_read_engagement`),
đặt bằng biến môi trường hoặc khóa `fb_page_id`, `fb_page_token` trong
`%USERPROFILE%\Documents\FacebookContentCloner\api_config.json`.
- Chưa có → hướng dẫn: Meta for Developers → tạo App → Graph API Explorer → chọn quyền trên → lấy User Token →
  `GET /me/accounts` → lấy `id` và `access_token` của page. Nên đổi sang token dài hạn.
- Để người dùng tự dán token vào file (gợi ý họ mở file bằng Notepad). Không yêu cầu dán token vào chat,
  không in token ra màn hình.
- Kiểm tra: `py -3 fbtool.py page-info` → phải thấy đúng tên page "Chuyện Đời & Nhân Tâm". Sai page thì dừng.

## Quy trình đăng
1. Chọn bài: `py -3 fbtool.py list --status approved`. Chưa duyệt → dùng skill `sang-tao-nhan-tam` trước.
2. Chọn hình thức:
   - Chỉ chữ: không thêm cờ.
   - Kèm ảnh: `--image <file>` — ảnh tự làm/AI (vd. ảnh bìa của `ke-chuyen-video`:
     `D:\ke-chuyen-video\out\<id>\thumbnail_<id>.png`).
   - Video: `--video <file.mp4>` (vd. `D:\ke-chuyen-video\out\<id>\video_<id>.mp4`); đăng dạng video trên page.
   - Hẹn giờ: `--schedule 2026-10-27T20:00` (giờ Việt Nam, cách hiện tại 10 phút–30 ngày).
     Khung giờ tốt cho page chuyện đời: 11:30–12:30 và 20:00–22:00.
3. **Chạy thử:** `py -3 fbtool.py publish <id> [cờ...]` → cho người dùng xem nguyên văn `text`, loại bài,
   file đính kèm, giờ hẹn. Hỏi xác nhận rõ ràng.
4. Người dùng đồng ý → chạy lại y hệt kèm `--yes`. Báo `fb_post_id` và link.
5. Nội dung có ảnh/giọng AI → nhắc bật nhãn "Nội dung do AI tạo" (Meta Business Suite) nếu cần.

## Lỗi thường gặp
- `fbtool` báo "media cào từ bài người khác" → không đăng file đó; tạo ảnh/video riêng.
  Chỉ thêm `--i-own-media` khi người dùng khẳng định có quyền.
- "quá giống bài nguồn" / "còn các mục khung" → quay lại `sang-tao-nhan-tam` để sửa bài.
- Meta 190 / OAuthException: token hết hạn → lấy token mới. 200/10: thiếu quyền `pages_manage_posts`.
- 368 / bị hạn chế tính năng: page bị Facebook giới hạn — dừng đăng, báo người dùng.
- Đã đăng rồi → fbtool chặn đăng trùng; muốn đăng lại phải là bài mới.

## Thay thế
Không muốn dùng Graph API: xuất bài (`fbtool.py show <id>`) để người dùng tự dán vào Meta Business Suite,
hoặc dùng Metricool (nếu đã kết nối) để lên lịch.

Không đăng quá 3–4 bài/ngày; không đăng hàng loạt bài giống nhau.
