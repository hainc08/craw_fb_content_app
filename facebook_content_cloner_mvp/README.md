# Facebook Content Cloner — Windows MVP

Ứng dụng Python Tkinter cho nội dung Page được chủ sở hữu cho phép sử dụng. Hỗ trợ nhiều Page; chỉ đăng bài đã duyệt khi bạn xác nhận, không vượt hạn chế Facebook.

## Chạy trên Windows
1. Cài Python 3.11–3.13 từ python.org và bật **Add Python to PATH** (Tkinter thường đi kèm Python bản Windows).
2. Giải nén ZIP, nhấn đúp `start_windows.bat` (hoặc `py -3 -m pip install -r requirements.txt` rồi `py -3 app.py`).
3. Chọn **Nhập JSON** và thử file `sample_posts.json` trước. Chọn bài, sửa bản nháp, bấm **Lưu nháp**, **Duyệt**, rồi **Xuất TXT**.
4. File SQLite và media được lưu trong `Documents\FacebookContentCloner` của tài khoản Windows.
5. Muốn biên dịch EXE: nhấn `build_exe.bat`; file ở `dist\FacebookContentCloner.exe`. Biên dịch trên Windows để có EXE Windows; đây là script build, ZIP không chứa file EXE có sẵn.

## Sử dụng tính năng Cào tự động từ Link Facebook
1. Khởi động ứng dụng bằng `start_windows.bat` (hoặc `cd facebook_content_cloner_mvp` rồi `py -3 app.py`).
2. **Dán Link Facebook** vào ô nhập trên cùng:
   - Hỗ trợ link Reels (`facebook.com/reel/...`, `facebook.com/share/r/...`), link Video Watch (`facebook.com/watch/?v=...`), link Post cá nhân/Fanpage, hoặc danh sách nhiều URL.
3. **Nhập số bài cần cào**: Ví dụ `1`, `5`, `10`.
4. Bấm nút: **⚡ CÀO BÀI & TẢI MEDIA**:
   - Ứng dụng tự động bóc tách tiêu đề, toàn bộ caption bài viết, và **tự động tải toàn bộ video MP4 & ảnh bìa về máy** (lưu tại `Documents\FacebookContentCloner\media`).
   - Bấm nút **📂 Mở thư mục Media** để xem ngay các file video/ảnh đã tải về máy.
5. Chọn bài viết trong danh sách để:
   - **Phân tích AI**: Phân tích chủ đề, hook giữ chân, nhịp cảm xúc, CTA.
   - **Sáng tạo mới**: Tạo kịch bản Reel 6 cảnh, câu chuyện mới, caption và hashtag riêng biệt.
   - **Kiểm tra trùng**: Đối soát tỷ lệ trùng lặp.
   - **Duyệt & Xuất TXT / CSV**.

## Lấy dữ liệu qua Meta API
- Chủ Page cấp quyền Facebook/task access cần thiết hoặc tự xuất JSON giao cho bạn. Chỉ lời đồng ý sử dụng nội dung KHÔNG thay quyền API.
- Tạo Meta App và lấy Page Access Token bằng luồng Meta được hỗ trợ. Các quyền phổ biến để đọc Page là `pages_show_list`, `pages_read_engagement`, `pages_read_user_content` tùy loại dữ liệu và quyền người dùng; có thể phải được duyệt/App Review.
- Dùng `GET /me/accounts` với User Token phù hợp để tìm Page ID và Page Access Token. Không nhập URL `facebook.com/share/...` vào ô Page ID; URL chia sẻ không phải Page ID.
- Điền ID dạng số, Page token, số bài rồi bấm **Đồng bộ Graph API**. Ứng dụng chỉ lấy `/PAGE_ID/posts` và trường `attachments`, số lượng tối đa 1000/lần. Một số bài/Reels hoặc ảnh/video gốc không được trả về trong trường này.
- Nếu thiếu Reels, dùng tính năng **Cào URL / Reels** hoặc JSON có URL media hợp lệ.

## Format JSON nhập
Một mảng `[{"id":"...","message":"...","created_time":"...","permalink_url":"...","attachments":{"data":[...]}}]` hoặc object `{"data":[...]}`. Các URL trực tiếp có thể nằm trong `attachments.data[].media.image.src` (ảnh) hoặc `attachments.data[].media.source` (video). Không có media URL thì vẫn lưu caption.

## Cấu hình AI: Google Gemini & Cloudflare Workers AI (Mới)
- Bấm nút **⚙️ Cài đặt API AI (Gemini / Cloudflare)** ở góc dưới bên phải:
  1. **Google Gemini (Khuyên dùng)**:
     - Nhập `Gemini API Key` (lấy miễn phí tại [aistudio.google.com](https://aistudio.google.com)).
     - Bấm nút **🔍 Kiểm tra kết nối Gemini** để xác nhận key hoạt động tốt.
     - Mô hình sử dụng: `gemini-1.5-flash` tốc độ cao, khả năng diễn đạt tiếng Việt tự nhiên và sâu sắc.
  2. **Cloudflare Workers AI**:
     - Nhập `Cloudflare Account ID` và `Cloudflare API Token`.
     - Bấm nút **🔍 Kiểm tra kết nối Cloudflare** để kiểm tra mô hình `Llama-3.1-8b-instruct`.
  3. Bấm **💾 Lưu Cấu Hình & Sử Dụng**:
     - Hệ thống tự động ghi nhớ key vào `Documents\FacebookContentCloner\api_config.json`, lần sau mở app không cần nhập lại.
- Sau khi chọn bài viết:
  - Bấm **Phân tích AI**: Trích xuất Hook, khán giả, nhịp điệu và insight bài gốc.
  - Bấm **Sáng tạo mới**: Tạo kịch bản Reel 6 cảnh, câu chuyện mới 250-400 từ, bài học, caption và hashtag.
  - Bấm **Kiểm tra trùng**: Đối soát tỷ lệ trùng chuỗi với bài gốc.
  - Bấm **Duyệt** -> **Xuất TXT**.

## Xử lý lỗi
- `OAuthException` / 190: token không hợp lệ hoặc hết hạn -> tạo lại token và kiểm tra quyền Meta.
- 10 / 200 / 403: thiếu Page access / app permission / feature, cần chủ Page cấp quyền hoặc làm App Review; KHÔNG vòng qua chặn.
- 4 / 17 / 32 / 613 / 429: giới hạn API -> giảm số lượng, đợi theo hướng dẫn Meta, không tạo tài khoản/token để né giới hạn.
- 400 unknown field: Meta thay đổi schema -> giảm field về `id,message,created_time,permalink_url` và kiểm tra tài liệu phiên bản đang dùng.
- Media `403` hoặc content-type `text/html`: URL chỉ là preview, đã hết hạn hoặc không được phép tải; xin link/download trực tiếp từ chủ Page. Đừng tìm cách lấy cookie hoặc giải mã stream bị bảo vệ.
- Media giới hạn 150MB/file. Tính năng download chạy theo từng bài, không tiếp tục tự động ở nền khi đóng app.

## Giới hạn bảo mật và chất lượng của MVP
- Chưa có OAuth GUI, token nhập thủ công và chỉ nằm trong RAM khi dùng UI (không lưu SQLite). Tránh chia sẻ token qua chat hoặc commit Git.
- JSON phải đến từ nguồn tin cậy; nhập dữ liệu nguồn lạ chỉ khi đã kiểm tra. URL tải media có thể truy cập các địa chỉ HTTPS mà JSON cung cấp; chỉ tải JSON đáng tin và tránh URL nội bộ.
- Không có phát hiện sao chép nội dung bằng mô hình chuyên dụng; cần người duyệt nội dung.
- Không có login scraper/browser automation, không download Reels bị hạn chế, không cloud sync. Đây là MVP kiểm chứng tính năng chứ không phải công cụ bảo đảm tải được 100% media Facebook.
- Quyền sử dụng lại ảnh/video và âm nhạc cần được cho phép riêng; cấp quyền lấy dữ liệu không tự động cấp quyền sử dụng mọi tác phẩm của bên thứ ba.

## Nâng cấp nghiên cứu & sáng tạo (bản 1.1)
- **Phân tích AI**: đọc caption/transcript bài nguồn và lưu insight vào bảng `research`.
- **Sáng tạo mới**: tạo câu chuyện mới, caption, kịch bản Reel 6 cảnh, CTA, hashtag. Nguồn là tham khảo chủ đề, không phải văn bản để đổi từ.
- **Kiểm tra trùng**: so khớp chuỗi và cụm 7 từ chung, chỉ là chỉ báo để người dùng xét duyệt, không phải đánh giá pháp lý.
- **Lưu nháp / Duyệt / Xuất TXT**: chỉ đăng khi bấm "🚀 Đăng lên Page" và xác nhận (bản 1.3).
- **Video**: lưu MP4 nếu nguồn cấp link tải hợp lệ; để nghiên cứu nội dung video, cần thêm transcript hoặc mô tả video vào trường `message` trong JSON nguồn. Phiên bản này KHÔNG tự bóc tiếng/nhận dạng video.
- Khi Graph API bị chặn, yêu cầu chủ Page cấp quyền tương ứng hoặc cung cấp JSON/media trực tiếp; không dùng crawler né xác thực hoặc CAPTCHA.
- API key được nhập trong phiên làm việc hoặc biến môi trường `OPENAI_API_KEY` và không lưu trong database.

## CLI `fbtool.py` — dùng cho Claude Code / tự động hóa
Dùng chung DB và `pages.json` với GUI, không mở cửa sổ. Xem `py -3 fbtool.py -h` và `CLAUDE.md` ở thư mục gốc.
- Cờ `--page <slug>` đặt trước lệnh con (bỏ trống = Page đang chọn); `pages` liệt kê Page, `page-show` xem prompt.
- `scrape`, `list`, `show`, `analyze`, `create`, `save-draft`, `check`, `approve`, `page-info`, `publish`.
- `approve`/`publish` chặn nháp quá giống nguồn (theo ngưỡng trùng của Page, hoặc trùng cụm 7 từ) và chặn đăng lại media cào về.
- `publish` mặc định chạy thử; thêm `--yes` để đăng thật bằng Page ID/token của Page (token cần quyền `pages_manage_posts`).

## Quản lý nhiều Page (bản 1.3)
- Thanh trên cùng: **Page đang làm** — chọn Page; danh sách bài, phân tích, nháp, trạng thái đều theo Page này.
  Bài cào về dùng chung cho mọi Page, mỗi Page có nháp riêng.
- **⚙️ Quản lý Page**: thêm/sửa/xóa Page. Mỗi Page có: tên, Facebook Page ID (số), Page Access Token
  (kèm nút Kiểm tra token), nhà cung cấp AI (hoặc dùng mặc định chung), hashtag, ngưỡng trùng, **prompt phân tích**
  và **prompt sáng tạo** riêng (dùng `{page_name}`, `{hashtags}` để chèn tên Page và hashtag; có nút khôi phục mặc định).
- Cấu hình lưu ở `Documents\FacebookContentCloner\pages.json` (token chỉ nằm ở đây, không vào database).
- Khóa AI (Gemini/Cloudflare/OpenAI) vẫn nhập một lần ở **⚙️ Khóa AI (dùng chung)**.

## Xem ảnh/video & đăng bài (bản 1.3)
- Ô **Link Facebook** nhận nhiều link, mỗi dòng một link.
- Chọn bài → khung **Ảnh & Video đã cào** hiện ảnh thu nhỏ và ô video; bấm để mở bằng ứng dụng mặc định.
  Mục chưa tải có nút **⬇ Tải media còn thiếu**.
- **Sáng tạo mới** viết theo prompt của Page và tự lưu nháp; **Duyệt** chỉ đạt khi bài mới đủ khác bài nguồn.
- **🚀 Đăng lên Page**: đăng chữ / kèm ảnh / video, có thể hẹn giờ (giờ VN, 10 phút–30 ngày). Không cho đăng lại
  file media cào từ bài người khác trừ khi bạn xác nhận có quyền.

## Kiểm thử
`py -3 -m pip install -r requirements-dev.txt` rồi `py -3 -m pytest tests -v`.
