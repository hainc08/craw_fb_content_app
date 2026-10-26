import datetime as dt
from pathlib import Path

import pytest

import publisher as pb

NOW = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
GOOD = 'Chị Hạnh bán bún riêu ở đầu ngõ mười hai năm. Bạn còn nhớ ai từng tử tế với mình? #chuyendoi'
SRC = 'Một người thợ già kiểm tra từng đường chỉ trước khi giao đôi giày.'
NOWHERE = Path('C:/nowhere')


def test_prepare_text_ok():
    plan = pb.prepare(SRC, GOOD, 0.35, None, NOWHERE, now=NOW)
    assert plan.kind == 'text' and plan.scheduled_ts is None and plan.check['passed']


def test_prepare_rejects_copy():
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, SRC, 0.35, None, NOWHERE, now=NOW)


def test_prepare_rejects_template_markers():
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, 'TIÊU ĐỀ: abc\n' + GOOD, 0.35, None, NOWHERE, now=NOW)


def test_prepare_blocks_scraped_media(tmp_path):
    f = tmp_path / 'media' / 'p1' / 'a.jpg'
    f.parent.mkdir(parents=True)
    f.write_bytes(b'x')
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, GOOD, 0.35, str(f), tmp_path / 'media', now=NOW)
    assert pb.prepare(SRC, GOOD, 0.35, str(f), tmp_path / 'media', now=NOW, i_own_media=True).kind == 'photo'


def test_prepare_video_kind_and_bad_extension(tmp_path):
    v = tmp_path / 'v.mp4'
    v.write_bytes(b'x')
    t = tmp_path / 'a.gif'
    t.write_bytes(b'x')
    assert pb.prepare(SRC, GOOD, 0.35, str(v), tmp_path / 'media', now=NOW).kind == 'video'
    with pytest.raises(pb.PublishError):
        pb.prepare(SRC, GOOD, 0.35, str(t), tmp_path / 'media', now=NOW)


def test_parse_schedule_vietnam_time_and_bounds():
    expected = int(dt.datetime(2026, 10, 26, 13, 0, tzinfo=dt.timezone.utc).timestamp())
    assert pb.parse_schedule('2026-10-26T20:00', NOW) == expected
    for bad in ['2026-10-26T19:05', '2026-12-30T20:00', 'ngày mai']:  # 5 phút nữa / quá 30 ngày / sai định dạng
        with pytest.raises(pb.PublishError):
            pb.parse_schedule(bad, NOW)


def test_send_text_scheduled_uses_header_not_url():
    calls = []

    class Resp:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {'id': '1_2'}

    class Session:
        def post(self, url, headers, data, files, timeout):
            calls.append((url, headers, data))
            return Resp()

    plan = pb.PublishPlan(GOOD, 'text', None, 1800000000, {})
    assert pb.send(plan, '123', 'tok', Session(), 'v26.0') == '1_2'
    url, headers, data = calls[0]
    assert url == 'https://graph.facebook.com/v26.0/123/feed' and 'tok' not in url
    assert headers['Authorization'] == 'Bearer tok'
    assert data == {'message': GOOD, 'published': 'false', 'scheduled_publish_time': '1800000000'}
