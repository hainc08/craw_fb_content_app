import research


def _capture(monkeypatch):
    seen = {}

    def fake(provider, keys, instruction, source, max_tokens):
        seen['instruction'] = instruction
        return 'ok'
    monkeypatch.setattr(research, 'generate_ai', fake)
    return seen


def test_render_prompt_replaces_placeholders():
    assert research.render_prompt('Viết cho {page_name}. Tag: {hashtags}', 'Page A', '#a #b') == \
        'Viết cho Page A. Tag: #a #b'


def test_render_prompt_keeps_other_braces():
    t = 'Trả JSON {"title": "..."} cho {page_name}'
    assert research.render_prompt(t, 'X', '') == 'Trả JSON {"title": "..."} cho X'


def test_create_new_uses_custom_instruction(monkeypatch):
    seen = _capture(monkeypatch)
    research.create_new('nguồn', '', 'gemini', {}, instruction='PROMPT RIÊNG')
    assert seen['instruction'] == 'PROMPT RIÊNG'


def test_analyze_default_instruction(monkeypatch):
    seen = _capture(monkeypatch)
    research.analyze('nguồn', 'gemini', {})
    assert seen['instruction'] == research.ANALYSIS_PROMPT
