import os
import re
import json
import base64
import threading
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template_string
import requests

app = Flask(__name__)

# سنستخدم مفتاح Groq أو Gemini، وبما أنك تريد نموذجاً شغالاً 100%، سنستخدم Groq Llama 3.2 90b Vision (أو استبدله بمفتاحك)
# أو سنعدلها بحيث تستخدم واجهة Groq السريعة للصور
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

# ---------------------------------------------------------------- الحالة العامة
_lock = threading.Lock()
STATE = {
    "id": 0,
    "status": "waiting",
    "question": "",
    "options": [],
    "correct": "",
    "correct_index": -1,
    "message": "",
    "updated_at": None,
}

PROMPT = """You are an expert exam tutor. The image contains a question, usually multiple choice.
Steps:
1. Read the question and all options exactly as written.
2. Solve it carefully and decide on the single correct answer.
3. Reply with ONLY a valid JSON object, no markdown, no extra text, in this exact shape:
{"question": "...", "options": ["...", "..."], "correct": "...", "correct_index": 0}

Rules:
- "options" contains only the option texts, WITHOUT letter or number labels (no "A)", "1.").
- "correct" is the full text of the correct option.
- "correct_index" is the 0-based index of the correct option in "options", or -1 if no options.
- If no readable question, reply {"error": "no_question"}.
"""


def resolve_index(options, correct, idx):
    if isinstance(idx, int) and 0 <= idx < len(options):
        return idx
    c = (correct or "").strip().lower()
    for i, o in enumerate(options):
        if o.strip().lower() == c:
            return i
    return -1


def parse_model_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    data = json.loads(text)
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("Unexpected JSON shape")
    return data


def set_state(**kw):
    with _lock:
        STATE["id"] += 1
        STATE.update({
            "status": "waiting",
            "question": "",
            "options": [],
            "correct": "",
            "correct_index": -1,
            "message": "",
        })
        STATE.update(kw)
        STATE["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(STATE)


@app.get("/")
def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return render_template_string(f.read())


@app.get("/health")
def health():
    return "ok", 200


@app.post("/upload")
def upload():
    body = request.get_json(silent=True) or {}
    img = body.get("image", "")
    if not img:
        return jsonify({"status": "error", "message": "no image"}), 400

    mime = "image/jpeg"
    if img.startswith("data:"):
        header, _, img = img.partition(",")
        m = re.match(r"data:([\w/\-\.+]+);base64", header)
        if m:
            mime = m.group(1)

    # استخدام Groq API (أو أي نموذج آخر تفضله)
    # إذا أردت استمرار استخدام Gemini لكن بطريقة HTTP مباشرة بدون مكتبة لتجنب مشاكل النماذج:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify({"status": "error", "message": "API_KEY is not set"}), 500

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {
                    "inline_data": {
                        "mime_type": mime,
                        "data": img
                    }
                }
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        
        if "error" in res_json:
            err_msg = res_json["error"].get("message", "Unknown error")
            return jsonify(set_state(status="error", message=err_msg[:150])), 400

        text_output = res_json["candidates"][0]["content"]["parts"][0]["text"]
        data = parse_model_json(text_output)

        if data.get("error"):
            return jsonify(set_state(status="error", message="No readable question in the image")), 422

        options = [str(o).strip() for o in (data.get("options") or [])]
        correct = str(data.get("correct", "")).strip()
        idx = resolve_index(options, correct, data.get("correct_index", -1))
        if idx >= 0 and not correct:
            correct = options[idx]

        result = set_state(
            status="success",
            question=str(data.get("question", "")).strip(),
            options=options,
            correct=correct,
            correct_index=idx,
        )
        return jsonify(result)

    except Exception as e:
        app.logger.exception("API error")
        return jsonify(set_state(status="error", message=str(e)[:150])), 500


@app.get("/result")
def result():
    with _lock:
        out = dict(STATE)
    resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
