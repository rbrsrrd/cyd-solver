import os
import base64
from flask import Flask, request, jsonify, render_template_string
import google.generativeai as genai

app = Flask(__name__)

# إعداد مفتاح Gemini API من متغيّرات البيئة
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# متغير تخزين النتيجة الحالية
current_quiz = {
    "status": "waiting",
    "question": "انتظار التقاط صورة...",
    "options": [],
    "correct": ""
}

# 1. واجهة الموقع الخاص بنا (HTML + JS)
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CYD Quiz Solver</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; text-align: center; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 15px; }
        h2 { margin-bottom: 15px; color: #38bdf8; font-size: 1.4rem; }
        .camera-box { width: 100%; max-width: 450px; background: #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; position: relative; }
        video { width: 100%; display: block; object-fit: cover; }
        .btn-container { padding: 15px; background: #1e293b; }
        button { width: 100%; background: #22c55e; color: #022c22; border: none; padding: 15px; font-size: 1.1rem; font-weight: bold; border-radius: 12px; cursor: pointer; transition: 0.2s; }
        button:active { transform: scale(0.98); background: #16a34a; }
        #status-box { margin-top: 15px; width: 100%; max-width: 450px; padding: 15px; border-radius: 12px; background: #1e293b; border: 1px solid #334155; text-align: right; font-size: 0.95rem; line-height: 1.5; }
        .success-text { color: #4ade80; font-weight: bold; }
    </style>
</head>
<body>
    <h2>المتكمّل - التقاط الأسئلة 📸</h2>
    
    <div class="camera-box">
        <video id="webcam" autoplay playsinline></video>
        <div class="btn-container">
            <button id="capture-btn">التقاط وإرسال للذكاء الاصطناعي 🚀</button>
        </div>
    </div>

    <canvas id="canvas" style="display:none;"></canvas>

    <div id="status-box">
        <b>الحالة:</b> <span id="status-text">الكاميرا جاهزة للالتقاط...</span>
        <div id="result-details" style="margin-top: 10px;"></div>
    </div>

    <script>
        const video = document.getElementById('webcam');
        const canvas = document.getElementById('canvas');
        const captureBtn = document.getElementById('capture-btn');
        const statusText = document.getElementById('status-text');
        const resultDetails = document.getElementById('result-details');

        // طلب تشغيل الكاميرا الخلفية مباشرة
        navigator.mediaDevices.getUserMedia({ 
            video: { facingMode: { exact: "environment" } } 
        }).catch(() => {
            // في حال عدم وجود كاميرا خلفية (أو في اللابتوب) تفتح الكاميرا المتاحة
            return navigator.mediaDevices.getUserMedia({ video: true });
        }).then(stream => {
            video.srcObject = stream;
        }).catch(err => {
            statusText.innerText = "فشل تشغيل الكاميرا: " + err.message;
        });

        captureBtn.addEventListener('click', () => {
            if (!video.srcObject) return;
            
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            
            const base64Image = canvas.toDataURL('image/jpeg', 0.85);

            statusText.innerText = "جاري رفع الصورة وتحليلها عبر Gemini...";
            resultDetails.innerHTML = "";
            captureBtn.disabled = true;

            fetch('/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: base64Image })
            })
            .then(res => res.json())
            .then(data => {
                captureBtn.disabled = false;
                if (data.status === 'success') {
                    statusText.innerText = "تم الحل بنجاح وإرساله للشاشة!";
                    resultDetails.innerHTML = `
                        <b>السؤال:</b> ${data.question}<br>
                        <b>الإجابة الصحيحة:</b> <span class="success-text">${data.correct}</span>
                    `;
                } else {
                    statusText.innerText = "حدث خطأ أثناء معالجة السؤال!";
                }
            })
            .catch(err => {
                captureBtn.disabled = false;
                statusText.innerText = "خطأ في الاتصال بالسيرفر!";
            });
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_PAGE)

@app.route('/upload', methods=['POST'])
def upload_image():
    global current_quiz
    try:
        data = request.get_json()
        image_b64 = data.get('image', '').split(',')[-1]
        image_bytes = base64.b64decode(image_b64)

        # استدعاء نموذج Gemini Vision
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = """
        تحليل الصورة واستخراج سؤال اختيار من متعدد منه.
        قم بإرجاع النتيجة بتنسيق JSON فقط بالشكل التالي دون أي نصوص إضافية:
        {
          "question": "نص السؤال هنا",
          "options": ["A) الخيار الأول", "B) الخيار الثاني", "C) الخيار الثالث", "D) الخيار الرابع"],
          "correct": "الخيار الصحيح فقط دون زيادة"
        }
        """

        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])

        # معالجة استجابة JSON
        import json
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean_json)

        current_quiz = {
            "status": "success",
            "question": parsed.get("question", ""),
            "options": parsed.get("options", []),
            "correct": parsed.get("correct", "")
        }

        return jsonify(current_quiz)

    except Exception as e:
        print("Error processing image:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/result', methods=['GET'])
def get_result():
    return jsonify(current_quiz)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
