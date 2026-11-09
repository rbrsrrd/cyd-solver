import os
from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

# قراءة مفتاح الـ API من متغيرات النظام بأمان
API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

latest_result = {
    "status": "waiting",
    "question": "انتظار التقاط صورة...",
    "options": [],
    "correct": ""
}

@app.route('/upload', methods=['POST'])
def upload_image():
    global latest_result
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    
    file = request.files['image']
    image_bytes = file.read()
    
    import base64
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"
        
        prompt_text = """
        تحليل هذه الصورة التي تحتوي على سؤال واختيارات.
        قم باستخراج السؤال، والخيارات المتاحة، وحدد الإجابة الصحيحة بدقة.
        أجب حصرياً بصيغة JSON نظيفة بدون أي إضافات تحتوي على المفاتيح التالية:
        {
          "question": "نص السؤال المستخرج",
          "options": ["الخيار A", "الخيار B", "الخيار C", "الخيار D"],
          "correct": "الحرف أو النص الخاص بالإجابة الصحيحة"
        }
        """
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": encoded_image
                            }
                        }
                    ]
                }
            ]
        }
        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=payload)
        res_json = response.json()
        
        text_response = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        
        if text_response.startswith("```json"):
            text_response = text_response[7:-3].strip()
        elif text_response.startswith("```"):
            text_response = text_response[3:-3].strip()
            
        data = json.loads(text_response)
        latest_result = {
            "status": "success",
            "question": data.get("question", ""),
            "options": data.get("options", []),
            "correct": data.get("correct", "")
        }
        
        return jsonify({"status": "success", "data": latest_result})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/result', methods=['GET'])
def get_result():
    global latest_result
    return jsonify(latest_result)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)