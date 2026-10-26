---
name: cao-bai-facebook
description: Cào bài viết, Reels, video công khai trên Facebook (link Page, Profile, bài viết, Reel, share link hoặc danh sách link) vào database của app Facebook Content Cloner để làm nguồn tham khảo cho page "Chuyện Đời & Nhân Tâm". Dùng khi người dùng nói "cào bài", "lấy bài từ page...", "scrape facebook", "tải bài/Reels về", "lấy nội dung page X", hoặc dán link facebook.com và muốn lấy nội dung.
---

# Cào bài Facebook công khai

Mọi lệnh chạy trong `D:\facebook_content_research_creator_windows\facebook_content_cloner_mvp` bằng `py -3 fbtool.py`.

## Quy trình
1. **Nhận link.** Chấp nhận: link Page/Profile (`facebook.com/tenpage`), Reel (`/reel/…`, `/share/r/…`),
   video (`/watch/?v=…`, `/videos/…`), bài viết (`/posts/…`, `permalink.php`), hoặc nhiều link một lúc.
   Không có số lượng → mặc định 5. Tối đa 20 bài/lần để tránh bị Facebook chặn.
2. **Cào:**
   ```bash
   py -3 fbtool.py scrape "<link1>" ["<link2>" ...] --limit 5
   ```
   Thêm `--no-media` nếu chỉ cần chữ (nhanh hơn; media cào về cũng không được đăng lại).
   Lệnh chạy lâu (Playwright cuộn trang) — đặt timeout 5–10 phút.
3. **Đánh giá kết quả** (JSON `posts[]`: `id`, `chars`, `preview`):
   - Bài `chars` < 80 hoặc preview toàn chữ giao diện ("Thích", "Bình luận", tên page, "Theo dõi") → bài rác,
     báo cho người dùng; không dùng làm nguồn.
   - `saved: 0` với link Page → Facebook chặn khách chưa đăng nhập. Gợi ý: dán link từng bài/Reel cụ thể,
     hoặc mở GUI (`start_windows.bat`) → "Dán nhanh thủ công".
   - Lỗi thiếu trình duyệt → `py -3 -m playwright install chromium` rồi chạy lại.
4. **Báo lại** dạng bảng ngắn: id → tóm tắt 1 dòng → chủ đề có hợp page không (đời sống, ứng xử, gia đình,
   công sở, lòng tốt, bài học sống). Gợi ý 1–3 bài nên sáng tạo lại → skill `sang-tao-nhan-tam`.

## Xem lại dữ liệu
```bash
py -3 fbtool.py list --limit 20          # có cột status/analyzed/published
py -3 fbtool.py show <id>                # nội dung gốc đầy đủ + media + nháp
```

## Giới hạn
- Chỉ nội dung công khai, không đăng nhập, không dùng cookie, không vượt CAPTCHA hay giới hạn tốc độ.
  Bị chặn thì dừng và báo, không thử lách.
- Media tải về (`Documents\FacebookContentCloner\media`) chỉ để xem tham khảo; nhắc người dùng không đăng lại.
- Không cào hàng loạt nhiều page liên tục; nghỉ giữa các lần cào.
