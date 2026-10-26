---
name: quy-trinh-noi-dung
description: Chạy trọn quy trình nội dung cho một hoặc nhiều Facebook Page đã cấu hình (Chuyện Đời & Nhân Tâm hoặc Page khác) — cào bài công khai từ page/link nguồn, chọn bài hợp chủ đề Page, dùng AI sáng tạo lại theo prompt của Page, kiểm tra trùng, duyệt, rồi đăng hoặc hẹn giờ (tùy chọn làm video Reel). Dùng khi người dùng muốn làm cả chuỗi một lần, ví dụ "cào page X rồi viết lại đăng lên page Y", "làm nội dung tuần này cho các page", "lên lịch 5 bài từ page nguồn".
---

# Quy trình trọn gói: Cào → Sáng tạo → Duyệt → Đăng

Điều phối 3 skill con; đọc từng skill khi tới bước đó:
`cao-bai-facebook` → `sang-tao-noi-dung` → `dang-bai-page` (tùy chọn `ke-chuyen-video`).
Thư mục: `D:\facebook_content_research_creator_windows\facebook_content_cloner_mvp`.

## Đầu vào
- **Page đích:** `py -3 fbtool.py pages`. Người dùng không nêu → dùng Page `active` và nói rõ. Page chưa có
  trong danh sách → nhờ người dùng tạo trong GUI ("⚙️ Quản lý Page") trước.
- Link nguồn (page/bài/Reel), hoặc dùng bài đã có trong DB: `py -3 fbtool.py --page <slug> list --status none`.
- Số bài (mặc định 3 mỗi Page), đăng ngay hay hẹn giờ, có làm video không (mặc định: chỉ bài viết).

## Các bước
1. **Cào** (skill `cao-bai-facebook`): lấy gấp ~2 lần số bài cần, `--no-media` trừ khi cần xem ảnh.
2. **Lọc theo từng Page:** đọc `page-show` để biết chủ đề/giọng của Page; bỏ bài rác, quảng cáo, chính trị,
   tôn giáo, giật gân, chuyện về người thật có tên. Chọn bài hợp Page và khác thông điệp với nhau.
3. **Sáng tạo** (skill `sang-tao-noi-dung`) với `--page <slug>`; tất cả nháp phải `check.passed`.
4. **Duyệt — điểm dừng bắt buộc:** trình bày tất cả bài mới (đánh số, ghi rõ Page). Chỉ `approve` bài người dùng
   đồng ý.
5. **(Tùy chọn) Video** cho Page Chuyện Đời & Nhân Tâm → skill `ke-chuyen-video` với câu chuyện đã duyệt.
6. **Đăng** (skill `dang-bai-page`): đề xuất lịch (vd mỗi Page 1 bài/ngày lúc 20:00 từ ngày mai), chạy thử toàn bộ,
   hiện bảng lịch → người dùng xác nhận một lần → chạy `--yes` từng bài.
7. **Báo cáo:** bảng Page → id nguồn → tiêu đề → hình thức → giờ đăng → fb_post_id; bài bị bỏ và vì sao.

## Nguyên tắc
- Hai điểm dừng chờ người dùng: duyệt nội dung (bước 4) và xác nhận đăng (bước 6), trừ khi người dùng đã nói rõ
  trong cuộc trò chuyện này là cho đăng không cần hỏi.
- Không đăng lại ảnh/video của bài nguồn; không giữ tình tiết hay câu chốt của bài gốc.
- Không đăng cùng một bài viết lại lên nhiều Page giống hệt nhau — mỗi Page một bài riêng theo prompt của nó.
- Bị Facebook chặn khi cào hoặc lỗi quyền khi đăng → dừng bước đó, báo rõ, không thử lách.
