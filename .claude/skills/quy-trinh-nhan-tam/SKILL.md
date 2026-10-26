---
name: quy-trinh-nhan-tam
description: Chạy trọn quy trình nội dung cho page "Chuyện Đời & Nhân Tâm" — cào bài công khai từ page/link Facebook nguồn, chọn bài hợp chủ đề, dùng AI sáng tạo lại thành câu chuyện mới, kiểm tra trùng, duyệt, rồi đăng hoặc hẹn giờ lên page (tùy chọn làm video Reel). Dùng khi người dùng muốn làm cả chuỗi một lần, ví dụ "cào page X rồi viết lại đăng lên page", "làm nội dung tuần này cho Chuyện Đời & Nhân Tâm", "tự động lấy bài và đăng", "lên lịch 5 bài từ page nguồn".
---

# Quy trình trọn gói: Cào → Sáng tạo → Duyệt → Đăng

Skill này điều phối 3 skill con; đọc từng skill khi tới bước đó:
`cao-bai-facebook` → `sang-tao-nhan-tam` → `dang-bai-page` (tùy chọn `ke-chuyen-video`).
Thư mục: `D:\facebook_content_research_creator_windows\facebook_content_cloner_mvp`.

## Đầu vào cần có
- Link nguồn (page/bài/Reel). Không có → hỏi; có thể gợi ý dùng bài đã có trong DB (`fbtool.py list --status none`).
- Số bài muốn ra (mặc định 3), đăng ngay hay hẹn giờ, có làm video không (mặc định: chỉ bài viết).

## Các bước
1. **Cào** (skill `cao-bai-facebook`): lấy gấp ~2 lần số bài cần (để còn lọc), `--no-media` trừ khi cần xem ảnh.
2. **Lọc:** bỏ bài rác/quá ngắn, bài quảng cáo, chính trị, tôn giáo, tin giật gân, chuyện về người thật có tên.
   Chọn bài có cảm xúc/bài học hợp page và **khác bài học với nhau**. Báo danh sách chọn kèm lý do 1 dòng.
3. **Sáng tạo** (skill `sang-tao-nhan-tam`): viết + `save-draft` từng bài, tất cả phải `check.passed`.
4. **Duyệt — điểm dừng bắt buộc:** trình bày tất cả bài mới cùng lúc (đánh số), hỏi người dùng duyệt/sửa/bỏ.
   Chỉ `approve` bài được đồng ý. Không tự duyệt thay người dùng.
5. **(Tùy chọn) Video:** với bài được chọn làm Reel → skill `ke-chuyen-video`, dùng câu chuyện đã duyệt làm
   chủ đề (rút gọn thành lời đọc 170–195 từ theo skill đó).
6. **Đăng** (skill `dang-bai-page`): đề xuất lịch (vd. mỗi ngày 1 bài lúc 20:00, bắt đầu từ ngày mai),
   chạy thử toàn bộ, hiển thị bảng lịch → người dùng xác nhận một lần cho cả lịch → chạy `--yes` từng bài.
7. **Báo cáo cuối:** bảng id nguồn → tiêu đề bài mới → hình thức (chữ/ảnh/video) → giờ đăng → link/fb_post_id;
   bài nào bị bỏ và vì sao.

## Nguyên tắc
- Hai điểm dừng chờ người dùng: duyệt nội dung (bước 4) và xác nhận đăng (bước 6). Không bỏ qua dù đang ở
  chế độ tự động — trừ khi người dùng đã nói rõ trong cuộc trò chuyện này là cho phép đăng không cần hỏi.
- Không đăng lại ảnh/video của bài nguồn; không giữ tình tiết hay câu chốt của bài gốc.
- Bị Facebook chặn khi cào hoặc lỗi quyền khi đăng → dừng bước đó, báo rõ, không thử lách.
