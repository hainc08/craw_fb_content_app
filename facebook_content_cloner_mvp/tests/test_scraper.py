import scraper


def test_ytdlp_message_prefers_description_without_stats_title():
    info = {'id': '1', 'title': '8.2K views · 71 reactions | Câu thơ hay | Thi Nhân Các',
            'description': 'Câu thơ hay #ThiNhanCac', 'webpage_url': 'https://www.facebook.com/reel/1'}
    assert scraper.parse_ytdlp_info(info)['message'] == 'Câu thơ hay #ThiNhanCac'


def test_pick_permalink_strips_tracking_but_keeps_story_query():
    hrefs = ['https://www.facebook.com/thinhancac.studio',
             'https://www.facebook.com/reel/1375994561021860/?__cft__[0]=AZg&__tn__=%2CO']
    assert scraper.pick_permalink(hrefs) == 'https://www.facebook.com/reel/1375994561021860/'
    story = ['https://www.facebook.com/permalink.php?story_fbid=pfbid02abc&id=1000&__cft__[0]=x']
    assert scraper.pick_permalink(story) == 'https://www.facebook.com/permalink.php?story_fbid=pfbid02abc&id=1000'
    assert scraper.pick_permalink(['https://www.facebook.com/abc/posts/pfbid0xyz?__cft__=1']) == \
        'https://www.facebook.com/abc/posts/pfbid0xyz'
    assert scraper.pick_permalink(['https://www.facebook.com/abc']) is None


def test_clean_post_text_removes_header_and_ui_noise():
    raw = ('Thi Nhân Các\nĐủ điều kiện nhận tiền hoa hồng\n \n·\n20 giờ trước\n20 giờ\n·\n'
           'Quyết “chừa” rồi lại… chẳng chừa.\nTrong Chừa rượu, Nguyễn Khuyến kể chuyện.\n'
           'Tất cả cảm xúc:\n71\nThích\nBình luận\nChia sẻ\nẨn bớt')
    assert scraper.clean_post_text(raw, 'Thi Nhân Các') == \
        'Quyết “chừa” rồi lại… chẳng chừa.\nTrong Chừa rượu, Nguyễn Khuyến kể chuyện.'


def test_clean_post_text_keeps_page_name_inside_body():
    raw = 'Thi Nhân Các\n1 ngày\nCảm ơn các bạn đã theo dõi Thi Nhân Các!'
    assert scraper.clean_post_text(raw, 'Thi Nhân Các') == 'Cảm ơn các bạn đã theo dõi Thi Nhân Các!'


def test_content_images_skips_avatars_and_duplicates():
    imgs = [('https://scontent.xx.fbcdn.net/avatar.jpg', 40, 40),
            ('https://scontent.xx.fbcdn.net/a.jpg', 500, 500),
            ('https://scontent.xx.fbcdn.net/a.jpg', 500, 500),
            ('https://static.xx.fbcdn.net/rsrc.php/emoji.png', 16, 16),
            ('data:image/gif;base64,xx', 600, 600),
            ('https://scontent.xx.fbcdn.net/b.jpg', 0, 0)]
    assert scraper.content_images(imgs) == ['https://scontent.xx.fbcdn.net/a.jpg', 'https://scontent.xx.fbcdn.net/b.jpg']


def test_ytdlp_picks_progressive_format_with_audio():
    info = {'id': '2', 'description': 'x', 'formats': [
        {'format_id': '11a', 'url': 'https://v/audio.m4a', 'vcodec': 'none', 'acodec': 'mp4a.40.5'},
        {'format_id': 'sd', 'url': 'https://v/sd.mp4', 'vcodec': None, 'acodec': None},
        {'format_id': 'hd', 'url': 'https://v/hd.mp4', 'vcodec': None, 'acodec': None},
        {'format_id': '99v', 'url': 'https://v/video_only_1080.mp4', 'vcodec': 'av01', 'acodec': 'none'}]}
    media = scraper.parse_ytdlp_info(info)['attachments']['data'][0]['media']
    assert media['source'] == 'https://v/hd.mp4'


def test_ytdlp_skips_video_only_when_muxed_exists():
    info = {'id': '3', 'description': 'x', 'formats': [
        {'format_id': 'a', 'url': 'https://v/muxed.mp4', 'vcodec': 'h264', 'acodec': 'aac'},
        {'format_id': 'b', 'url': 'https://v/video_only.mp4', 'vcodec': 'h264', 'acodec': 'none'}]}
    assert scraper.parse_ytdlp_info(info)['attachments']['data'][0]['media']['source'] == 'https://v/muxed.mp4'


def test_clean_post_text_strips_inline_see_less_and_player_time():
    raw = 'Thi Nhân Các\n1 ngày\nCâu thơ hay #ThiNhanCac Ẩn bớt\n0:00 / 0:31\nNội dung tiếp… Xem thêm'
    assert scraper.clean_post_text(raw, 'Thi Nhân Các') == 'Câu thơ hay #ThiNhanCac\nNội dung tiếp…'


def test_video_post_prefers_ytdlp_caption():
    page_text = 'Câu thơ hay #ThiNhanCac\nphụ đề chạy trên video dài dài dài dài'
    assert scraper.choose_caption(page_text, 'Câu thơ hay #ThiNhanCac', is_video=True) == 'Câu thơ hay #ThiNhanCac'
    assert scraper.choose_caption(page_text, '', is_video=True) == page_text
    assert scraper.choose_caption('bài dài hơn', 'ngắn', is_video=False) == 'bài dài hơn'


def test_ytdlp_truncated_description_falls_back_to_title():
    info = {'id': '4', 'description': 'Mỗi bước trưởng thành đều in...',
            'title': '2K views · 33 reactions | Mỗi bước trưởng thành đều in bóng thầy cô. 🌿 #ThiNhanCac | Thi Nhân Các'}
    assert scraper.parse_ytdlp_info(info)['message'] == 'Mỗi bước trưởng thành đều in bóng thầy cô. 🌿 #ThiNhanCac'


def test_choose_caption_uses_page_text_when_ytdlp_truncated():
    assert scraper.choose_caption('Câu đầy đủ đến hết bài.', 'Câu đầy đủ...', is_video=True) == 'Câu đầy đủ đến hết bài.'
