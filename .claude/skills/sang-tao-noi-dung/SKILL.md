---
name: sang-tao-noi-dung
description: Phân tích bài Facebook đã cào và sáng tạo lại thành bài viết MỚI theo prompt và giọng văn riêng của từng Page đã cấu hình (ví dụ "Chuyện Đời & Nhân Tâm" hay bất kỳ Page nào khác), kiểm tra không trùng với bài nguồn rồi lưu nháp chờ duyệt. Dùng khi người dùng nói "viết lại bài này", "sáng tạo lại", "rewrite", "làm bài mới từ bài nguồn", "phân tích bài", "tạo nội dung cho page X" kèm một post id hoặc bài vừa cào.
---

# Sáng tạo lại nội dung theo từng Page

Thư mục: `D:\facebook_content_research_creator_windows\facebook_content_cloner_mvp`. Mọi lệnh có dạng
`py -3 fbtool.py --page <slug> <lệnh>` (cờ `--page` đứng **trước** lệnh con).

## 0. Chọn Page
`py -3 fbtool.py pages` → danh sách Page (slug, tên, hashtag, `active`). Người dùng nêu tên Page nào thì dùng
slug của Page đó; không nêu thì dùng Page `active: true` và nói rõ đang viết cho Page nào.
Rồi đọc cấu hình: `py -3 fbtool.py --page <slug> page-show` → `creation_prompt` (giọng văn, khung bài,
độ dài, quy tắc), `hashtags`, `max_similarity`. **`creation_prompt` là bản hướng dẫn viết cho Page đó** — làm
theo nó. Với Page mặc định `chuyen-doi-nhan-tam`, xem thêm ví dụ trong `references/vi-du-chuyen-doi-nhan-tam.md`.

## 1. Mỗi bài nguồn
1. **Đọc:** `py -3 fbtool.py --page <slug> show <id>`. Nguồn quá ngắn/rác → báo người dùng, bỏ qua.
2. **Phân tích** (tự làm): cảm xúc/vấn đề cốt lõi, vì sao bài lan tỏa, thông điệp hợp với Page, và danh sách
   **chi tiết đặc thù phải tránh** (tên, nghề, bối cảnh, tình tiết, câu thoại, câu chốt).
   Muốn dùng AI của app: `py -3 fbtool.py --page <slug> analyze <id>` (dùng prompt phân tích của Page).
3. **Viết bài mới** theo `creation_prompt`: giữ chủ đề/thông điệp, thay toàn bộ nhân vật, bối cảnh, diễn biến,
   lời thoại, câu chốt. Bài **sạch, sẵn sàng đăng** (không nhãn "HOOK:", "TIÊU ĐỀ:"…), kết bằng hashtag của Page.
   Ghi vào file tạm trong scratchpad.
4. **Lưu + kiểm tra trùng:** `py -3 fbtool.py --page <slug> save-draft <id> --file "<file>"` → `check.passed`
   phải `true` (theo `max_similarity` của Page, không cụm 7 từ chung). Không đạt → viết khác hẳn đi
   (đổi cấu trúc kể, góc nhìn), đừng chỉ thay vài từ.
5. **Trình bày:** bài mới + 1 dòng "lấy cảm hứng gì, đã đổi gì" + chỉ số trùng. Người dùng đồng ý (có thể sau
   khi sửa) → `py -3 fbtool.py --page <slug> approve <id>`. Gợi ý bước sau: đăng (skill `dang-bai-page`), hoặc
   làm Reel với skill `ke-chuyen-video` nếu là Page Chuyện Đời & Nhân Tâm.

## Nhiều bài / nhiều Page
Làm lần lượt; một bài nguồn có thể viết cho nhiều Page (mỗi Page một nháp riêng). Cuối cùng báo bảng:
Page → id nguồn → tiêu đề bài mới → tỉ lệ trùng → trạng thái. Tránh nhiều bài cùng một thông điệp trong một đợt.

## AI của app thay vì tự viết
`py -3 fbtool.py --page <slug> create <id>` in bài do Gemini/Cloudflare/OpenAI viết theo prompt của Page.
Đọc lại, biên tập cho đúng giọng rồi mới `save-draft`. Llama (Cloudflare) thường tiếng Việt kém.

## Không được
- Giữ tình tiết đặc trưng hay câu chốt của bài gốc; ghép câu từ nhiều bài nguồn.
- Bịa số liệu, bịa trích dẫn gán cho người nổi tiếng, chép câu chữ sách có bản quyền.
- Viết chuyện hư cấu như trải nghiệm thật của admin; nêu tên người thật.
- Lời khuyên y tế, pháp lý, tài chính cụ thể; nội dung chính trị, tôn giáo gây tranh cãi.
