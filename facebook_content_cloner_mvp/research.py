"""Content analysis and originality checks.
Supports Google Gemini API, Cloudflare Workers AI, and OpenAI.
"""
import json
import re
from difflib import SequenceMatcher
import requests

ANALYSIS_PROMPT = """Bạn là chuyên gia nghiên cứu nội dung Facebook và Reels tại Việt Nam. Chỉ phân tích; không sao chép nguyên văn. Trả lời tiếng Việt bằng các mục rõ ràng:
1. Chủ đề, khán giả mục tiêu và vấn đề/cảm xúc cốt lõi
2. Hook mở đầu và cơ chế tâm lý giữ chân người đọc/người xem
3. Nhịp kể chuyện và điểm chuyển cảm xúc
4. CTA và khả năng kích thích thảo luận / chia sẻ
5. 3 ý tưởng khai thác mới hoàn toàn khác về nhân vật, bối cảnh, tình huống
6. Các chi tiết đặc thù của tác phẩm gốc cần tránh bắt chước
Không bịa đặt số liệu tương tác nếu không có dữ liệu."""

CREATION_PROMPT = """Bạn là biên kịch và chuyên gia sáng tạo nội dung Facebook & Reels hàng đầu.
Nhiệm vụ: Dựa trên chủ đề và cơ chế hiệu quả của bài nguồn, hãy sáng tạo một bài HOÀN TOÀN MỚI với nhân vật, bối cảnh, cốt truyện, diễn biến và lời thoại khác biệt rõ rệt. Tuyệt đối không sao chép câu chữ, không paraphrase thô.
Giọng văn tiếng Việt tự nhiên, chân thực, cuốn hút, giàu cảm xúc.

Đầu ra định dạng chuẩn các phần sau:
TIÊU ĐỀ: (1 dòng ngắn gọn, thu hút)
HOOK: (1–2 câu mở đầu cực mạnh, giữ chân ngay 3 giây đầu)
CÂU CHUYỆN / NỘI DUNG: (250–400 chữ, có cao trào và bài học sâu sắc)
BÀI HỌC / THÔNG ĐIỆP: (1–2 câu ý nghĩa)
CAPTION FACEBOOK: (80–140 chữ kèm biểu tượng cảm xúc phù hợp)
KỊCH BẢN REEL 6 CẢNH: (Thời lượng 45–60s; mỗi cảnh gồm: [Hình ảnh/Góc quay] và [Lời thoại Voiceover])
CTA: (1 câu hỏi mở kích thích người đọc bình luận sôi nổi)
HASHTAG: (5 hashtag thịnh hành)"""


GEMINI_MODELS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
ACTIVE_GEMINI_MODEL = "gemini-3.5-flash"


def test_gemini(api_key: str) -> tuple[bool, str]:
    """Test connection to Google Gemini API by checking working models."""
    global ACTIVE_GEMINI_MODEL
    key = api_key.strip()
    if not key:
        return False, "Chưa nhập Gemini API Key."

    errors = []
    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": "Xin chào, hãy trả lời 'OK'."}]}],
            "generationConfig": {"maxOutputTokens": 10}
        }
        try:
            r = requests.post(url, json=payload, timeout=12)
            if r.status_code == 200:
                ACTIVE_GEMINI_MODEL = model_name
                return True, f"Kết nối Gemini API thành công! (Mô hình: {model_name})"
            else:
                err_text = r.json().get('error', {}).get('message', r.text[:150]) if r.text else f"Status {r.status_code}"
                errors.append(f"{model_name}: {err_text}")
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")

    last_err = errors[0] if errors else "Không thể kết nối"
    return False, f"Lỗi kết nối Gemini: {last_err}"


def test_cloudflare(account_id: str, api_token: str) -> tuple[bool, str]:
    """Test connection to Cloudflare Workers AI."""
    acc_id = account_id.strip()
    token = api_token.strip()
    if not acc_id or not token:
        return False, "Cần nhập đầy đủ Cloudflare Account ID và API Token."
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/run/@cf/meta/llama-3.1-8b-instruct"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"role": "user", "content": "Hi, reply 'OK' to test connection."}],
        "max_tokens": 10
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200 and r.json().get('success', False):
            return True, "Kết nối Cloudflare Workers AI thành công! (Model: Llama-3.1-8b)"
        err_detail = r.text[:200]
        try:
            err_detail = r.json().get('errors', [{}])[0].get('message', err_detail)
        except Exception:
            pass
        return False, f"Lỗi Cloudflare ({r.status_code}): {err_detail}"
    except Exception as exc:
        return False, f"Lỗi mạng khi kết nối Cloudflare: {exc}"


def call_gemini(api_key: str, instruction: str, source: str, max_tokens: int = 2500) -> str:
    """Invoke Google Gemini API with automatic model fallback."""
    global ACTIVE_GEMINI_MODEL
    key = api_key.strip()
    if not key:
        raise ValueError("Chưa cấu hình Gemini API Key.")

    # Try active model first, then others
    models_to_try = [ACTIVE_GEMINI_MODEL] + [m for m in GEMINI_MODELS if m != ACTIVE_GEMINI_MODEL]
    last_error = ""

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        payload = {
            "system_instruction": {
                "parts": [{"text": instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": source[:16000]}]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": max_tokens
            }
        }
        try:
            r = requests.post(url, json=payload, timeout=(10, 100))
            if r.status_code == 200:
                ACTIVE_GEMINI_MODEL = model_name
                data = r.json()
                candidates = data.get('candidates', [])
                if not candidates:
                    raise RuntimeError("Gemini không trả về kết quả.")
                parts = candidates[0].get('content', {}).get('parts', [])
                text = "".join(p.get('text', '') for p in parts)
                if text.strip():
                    return text.strip()
            else:
                last_error = f"{model_name} HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            last_error = str(exc)

    raise RuntimeError(f"Tất cả mô hình Gemini đều lỗi. Lỗi cuối: {last_error}")


def call_cloudflare(account_id: str, api_token: str, instruction: str, source: str, max_tokens: int = 2500) -> str:
    """Invoke Cloudflare Workers AI."""
    acc_id = account_id.strip()
    token = api_token.strip()
    if not acc_id or not token:
        raise ValueError("Chưa cấu hình Cloudflare Account ID hoặc API Token.")

    url = f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/run/@cf/meta/llama-3.1-8b-instruct"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": source[:12000]}
        ],
        "max_tokens": max_tokens
    }
    r = requests.post(url, headers=headers, json=payload, timeout=(10, 120))
    if not r.ok:
        try:
            err = r.json().get('errors', [{}])[0].get('message', r.text[:250])
        except Exception:
            err = r.text[:250]
        raise RuntimeError(f"Cloudflare AI Error ({r.status_code}): {err}")
    
    data = r.json()
    response = data.get('result', {}).get('response', '')
    if not response.strip():
        raise RuntimeError("Cloudflare AI không trả về nội dung.")
    return response.strip()


def generate_ai(provider: str, keys: dict, instruction: str, source: str, max_tokens: int = 2500) -> str:
    """Dispatch AI generation request to the selected provider."""
    prov = provider.lower()
    if prov == 'gemini':
        key = keys.get('gemini_key', '')
        return call_gemini(key, instruction, source, max_tokens)
    elif prov == 'cloudflare':
        acc_id = keys.get('cloudflare_account_id', '')
        token = keys.get('cloudflare_token', '')
        return call_cloudflare(acc_id, token, instruction, source, max_tokens)
    elif prov == 'openai':
        key = keys.get('openai_key', '')
        if not key:
            raise ValueError("Chưa cấu hình OpenAI API Key.")
        # Fallback OpenAI
        payload = {
            'model': 'gpt-4.1-mini',
            'input': [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': instruction}]},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': source[:16000]}]}
            ],
            'max_output_tokens': max_tokens
        }
        r = requests.post('https://api.openai.com/v1/responses',
                          headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                          json=payload, timeout=(10, 100))
        if not r.ok:
            raise RuntimeError(f"OpenAI Error: {r.text[:200]}")
        res = r.json()
        txt = ''.join(item.get('text', '') for out in res.get('output', [])
                      for item in out.get('content', []) if item.get('type') == 'output_text')
        return txt.strip()
    else:
        raise ValueError(f"Nhà cung cấp AI không được hỗ trợ: {provider}")


def render_prompt(template: str, page_name: str, hashtags: str) -> str:
    """Thay {page_name}, {hashtags}; giữ nguyên mọi dấu ngoặc nhọn khác."""
    return template.replace('{page_name}', page_name).replace('{hashtags}', hashtags)


def analyze(source: str, provider: str, keys: dict, instruction: str | None = None) -> str:
    if not source.strip():
        raise ValueError("Bài nguồn chưa có nội dung để phân tích.")
    return generate_ai(provider, keys, instruction or ANALYSIS_PROMPT, source, 1800)


def create_new(source: str, analysis: str, provider: str, keys: dict, instruction: str | None = None) -> str:
    if not source.strip():
        raise ValueError("Bài nguồn chưa có nội dung.")
    prompt_input = f"BÀI NGUỒN:\n{source[:11000]}\n\nPHÂN TÍCH INSIGHT:\n{analysis[:7000]}"
    return generate_ai(provider, keys, instruction or CREATION_PROMPT, prompt_input, 2600)


def similarity(source: str, draft: str) -> dict:
    def clean(s):
        return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', s.lower(), flags=re.UNICODE)).strip()

    a, b = clean(source), clean(draft)
    if not a or not b:
        return {'sequence_ratio': 0.0, 'shared_phrases': []}
    seq = SequenceMatcher(None, a[:20000], b[:20000]).ratio()
    words_a = a.split()
    words_b = b.split()
    n = 7
    grams = {tuple(words_a[i:i + n]) for i in range(max(0, len(words_a) - n + 1))}
    shared = sorted({' '.join(words_b[i:i + n]) for i in range(max(0, len(words_b) - n + 1)) if tuple(words_b[i:i + n]) in grams})
    return {'sequence_ratio': round(seq, 3), 'shared_phrases': shared[:15]}
