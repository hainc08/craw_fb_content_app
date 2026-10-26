---
name: sang-tao-nhan-tam
description: Phân tích bài Facebook đã cào và sáng tạo lại thành bài viết MỚI (câu chuyện đời thường có bài học đối nhân xử thế kiểu Đắc Nhân Tâm) theo giọng page "Chuyện Đời & Nhân Tâm", kiểm tra không trùng với bài nguồn rồi lưu nháp chờ duyệt. Dùng khi người dùng nói "viết lại bài này", "sáng tạo lại", "rewrite", "làm bài mới từ bài nguồn", "phân tích bài", "tạo nội dung cho page Chuyện Đời & Nhân Tâm" kèm một post id hoặc bài vừa cào.
---

# Sáng tạo lại nội dung cho "Chuyện Đời & Nhân Tâm"

Thư mục làm việc: `D:\facebook_content_research_creator_windows\facebook_content_cloner_mvp`.
Đọc `references/giong-van-page.md` trước khi viết.

## Quy trình cho mỗi bài nguồn
1. **Đọc nguồn:** `py -3 fbtool.py show <id>`. Nguồn quá ngắn/rác → báo người dùng, bỏ qua.
2. **Phân tích** (tự làm, không cần gọi API): rút ra
   - cảm xúc / nỗi niềm cốt lõi, khán giả, vì sao bài lan tỏa (hook, chuyển cảm xúc, CTA);
   - **bài học** gắn với một nguyên tắc ứng xử (lắng nghe, khen thật lòng, nhận lỗi, biết ơn, giữ ranh giới…);
   - danh sách **chi tiết đặc thù của bài gốc phải tránh**: tên, nghề, bối cảnh, tình tiết, câu thoại, câu chốt.
   Nếu người dùng muốn dùng AI của app: `py -3 fbtool.py analyze <id>` (Gemini mặc định) và đọc kết quả.
3. **Viết bài mới** theo khung trong reference: giữ *chủ đề/bài học*, thay **toàn bộ** nhân vật, bối cảnh,
   diễn biến, lời thoại, câu chốt. Không dịch/paraphrase câu nào của bản gốc.
   Ghi bài **sạch, sẵn sàng đăng** (không có nhãn "HOOK:", "TIÊU ĐỀ:"…) vào file tạm trong scratchpad.
4. **Lưu + kiểm tra trùng:**
   ```bash
   py -3 fbtool.py save-draft <id> --file "<đường dẫn file>"
   ```
   Kết quả `check.passed` phải `true` (sequence_ratio ≤ 0.35, không cụm 7 từ chung). Không đạt → viết lại
   khác hơn nữa (đổi cấu trúc kể, góc nhìn), lưu lại. Đừng chỉ thay vài từ để lách ngưỡng — ngưỡng là sàn
   tối thiểu, mục tiêu là một câu chuyện khác hẳn.
5. **Trình bày cho người dùng:** bài mới đầy đủ + 1 dòng "lấy cảm hứng chủ đề gì, đã đổi những gì" +
   chỉ số trùng. Hỏi duyệt. Người dùng đồng ý (có thể sau khi sửa) → `py -3 fbtool.py approve <id>`.
   Sau khi duyệt, gợi ý: đăng ngay (skill `dang-bai-page`) hoặc làm video Reel (skill `ke-chuyen-video`,
   truyền câu chuyện vừa viết làm chủ đề).

## Nhiều bài
Làm lần lượt; cuối cùng báo bảng: id nguồn → tiêu đề bài mới → sequence_ratio → trạng thái.
Tránh viết nhiều bài cùng một bài học trong một đợt — page cần đa dạng.

## Dùng AI của app thay vì tự viết
Khi người dùng muốn (vd. để tiết kiệm): `py -3 fbtool.py create <id>` in ra bản có các mục
TIÊU ĐỀ/HOOK/CÂU CHUYỆN/CAPTION/KỊCH BẢN REEL/HASHTAG. Bản này **không đăng thẳng được**: biên tập lại thành
bài sạch theo giọng page rồi mới `save-draft`. Bản Llama của Cloudflare thường tiếng Việt kém, cần sửa nhiều.

## Không được
- Giữ nguyên tình tiết đặc trưng hay câu chốt của bài gốc; ghép câu từ nhiều bài nguồn.
- Bịa số liệu, bịa trích dẫn gán cho Dale Carnegie hay người nổi tiếng; chép câu chữ sách Đắc Nhân Tâm.
- Viết như trải nghiệm thật của admin ("hôm qua mình gặp…") khi chuyện là hư cấu.
- Lời khuyên y tế, pháp lý, tài chính cụ thể; nội dung chính trị, tôn giáo gây tranh cãi; nêu tên người thật.
