import os
import re
import json
import base64
import threading
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template_string
import requests

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
DISPLAY_LANG = os.environ.get("DISPLAY_LANG", "en")

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

LANG_RULE = (
    "Write the question, options and correct answer in English (translate if the "
    "original is in another language) and use plain ASCII characters only "
    "(write math like x^2, sqrt(x), pi, <=, >=)."
    if DISPLAY_LANG == "en"
    else "Keep the original language of the question and options."
)

PROMPT = f"""You are an expert exam tutor. The image contains a question, usually multiple choice.
Steps:
1. Read the question and all options exactly as written.
2. Solve it carefully and decide on the single correct answer.
3. Reply with ONLY a valid JSON object, no markdown, no extra text, in this exact shape:
{{"question": "...", "options": ["...", "..."], "correct": "...", "correct_index": 0}}

Rules:
- "options" contains only the option texts, WITHOUT letter or number labels (no "A)", "1.").
- "correct" is the full text of the correct option (or a short final answer if there are no options).
- "correct_index" is the 0-based index of the correct option in "options", or -1 if there are no options.
- If the question has no options, return "options": [] and put the answer in "correct".
- {LANG_RULE}
- If the image has no readable question, reply {{"error": "no_question"}}.
"""


def resolve_index(options, correct, idx):
    if isinstance(idx, int) and 0 <= idx < len(options):
        return idx
    c = (correct or "").strip().lower()
    for i, o in enumerate(options):
        if o.strip().lower() == c:
            return i
    m = re.match(r"^\(?([a-hA-H])[\)\.\:]?$", (correct or "").strip())
    if m:
        i = ord(m.group(1).upper()) - 65
        if i < len(options):
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
        STATE.update(
            {
                "status": "waiting",
                "question": "",
                "options": [],
                "correct": "",
                "correct_index": -1,
                "message": "",
            }
        )
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
    if not GROQ_API_KEY:
        return jsonify({"status": "error", "message": "GROQ_API_KEY is not set"}), 500

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

    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.2-90b-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{img}"
                        }
                    }
                ]
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        res_json = response.json()

        if "error" in res_json:
            err_msg = res_json["error"].get("message", "Groq API Error")
            return jsonify(set_state(status="error", message=err_msg[:150])), 400

        text_output = res_json["choices"][0]["message"]["content"]
        data = parse_model_json(text_output)

        if data.get("error"):
            return jsonify(
                set_state(status="error", message="No readable question in the image")
            ), 422

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
