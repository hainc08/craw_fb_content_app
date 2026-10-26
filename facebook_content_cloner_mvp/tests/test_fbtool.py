import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def env_for(tmp_path):
    return {**os.environ, 'FBCLONER_HOME': str(tmp_path), 'PYTHONIOENCODING': 'utf-8'}


def run(tmp_path, *args):
    r = subprocess.run([sys.executable, str(HERE / 'fbtool.py'), *args], capture_output=True,
                       text=True, encoding='utf-8', env=env_for(tmp_path))
    return r.returncode, r.stdout, r.stderr


def import_sample(tmp_path):
    code = (f"import sys; sys.path.insert(0, r'{HERE}'); import app; app.init_db(); "
            f"app.import_json(r'{HERE / 'sample_posts.json'}')")
    subprocess.run([sys.executable, '-c', code], env=env_for(tmp_path), check=True)


def test_pages_hides_token(tmp_path):
    (tmp_path / 'api_config.json').write_text(
        json.dumps({'fb_page_id': '1', 'fb_page_token': 'SECRET'}), encoding='utf-8')
    code, out, _ = run(tmp_path, 'pages')
    assert code == 0 and 'SECRET' not in out
    pages = json.loads(out)
    assert pages[0]['has_token'] is True and pages[0]['active'] is True


def test_page_show_renders_prompt(tmp_path):
    code, out, _ = run(tmp_path, 'page-show')
    d = json.loads(out)
    assert code == 0 and '{page_name}' not in d['creation_prompt']
    assert 'Chuyện Đời & Nhân Tâm' in d['creation_prompt']


def test_drafts_are_per_page(tmp_path):
    run(tmp_path, 'pages')  # tạo pages.json mặc định
    store = json.loads((tmp_path / 'pages.json').read_text(encoding='utf-8'))
    store['pages'].append({'slug': 'b', 'name': 'B'})
    (tmp_path / 'pages.json').write_text(json.dumps(store, ensure_ascii=False), encoding='utf-8')
    import_sample(tmp_path)
    f = tmp_path / 'd.txt'
    f.write_text('Chị Hạnh bán bún riêu ở đầu ngõ mười hai năm, nhớ khẩu vị từng khách quen.', encoding='utf-8')
    assert run(tmp_path, '--page', 'b', 'save-draft', 'demo_001', '--file', str(f))[0] == 0
    _, out_b, _ = run(tmp_path, '--page', 'b', 'show', 'demo_001')
    _, out_a, _ = run(tmp_path, 'show', 'demo_001')
    assert json.loads(out_b)['draft'].startswith('Chị Hạnh')
    assert json.loads(out_a)['draft'] is None


def test_publish_dry_run_names_page(tmp_path):
    import_sample(tmp_path)
    f = tmp_path / 'd.txt'
    f.write_text('Chị Hạnh bán bún riêu ở đầu ngõ mười hai năm, nhớ khẩu vị từng khách quen.', encoding='utf-8')
    run(tmp_path, 'save-draft', 'demo_001', '--file', str(f))
    assert run(tmp_path, 'approve', 'demo_001')[0] == 0
    code, out, _ = run(tmp_path, 'publish', 'demo_001')
    d = json.loads(out)
    assert code == 0 and d['dry_run'] is True and d['page'] == 'Chuyện Đời & Nhân Tâm' and d['kind'] == 'text'


def test_unknown_page_errors(tmp_path):
    code, _, err = run(tmp_path, '--page', 'khong-co', 'list')
    assert code == 1 and 'khong-co' in err
