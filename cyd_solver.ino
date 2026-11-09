/*
  CYD (ESP32-2432S028) - عارض الأسئلة والإجابات
  المكتبات المطلوبة: TFT_eSPI + ArduinoJson (الإصدار 7.x)
  لوحة ESP32 في Arduino IDE: "ESP32 Dev Module" (يُفضّل core 2.0.17)
*/
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>

// ------------------------------ الإعدادات ------------------------------
const char* WIFI_SSID  = "render";
const char* WIFI_PASS  = "12345678";
const char* RESULT_URL = "https://YOUR-APP-NAME.onrender.com/result";  // <-- غيّره
const unsigned long POLL_MS = 5000;   // الفاصل بين كل طلب وآخر
#define BL_PIN 21                     // الإضاءة الخلفية

// ------------------------------ المتغيرات ------------------------------
TFT_eSPI tft = TFT_eSPI();
long lastId = -1;
unsigned long lastPoll = 0;

const int SCR_W = 320, SCR_H = 240;   // وضع أفقي (Rotation 1)
const int PAD = 6, FOOT = 24;
const int LIMIT_Y = SCR_H - FOOT - 2;

// ------------------------------ أدوات مساعدة ------------------------------
// الخطوط المدمجة لا تدعم إلا ASCII، نستبدل غيرها بـ '?'
String toAscii(const String& s) {
  String out;
  out.reserve(s.length());
  for (size_t i = 0; i < s.length(); i++) {
    uint8_t c = (uint8_t)s[i];
    if (c < 0x80) {
      if (c == '\n' || c == '\r' || c == '\t') out += ' ';
      else out += (char)c;
    } else if (c >= 0xC0) {
      out += '?';
    }
  }
  return out;
}

// يلفّ النص على عدة أسطر؛ draw=false فقط للحساب
int wrapText(const String& text, int x, int y, int maxW, int lineH, bool draw) {
  int lines = 0;
  String line = "";
  int n = text.length(), start = 0;

  auto emit = [&](const String& l) {
    if (draw && y + lineH <= LIMIT_Y + 2) tft.drawString(l, x, y);
    y += lineH;
    lines++;
  };

  while (start < n) {
    int sp = text.indexOf(' ', start);
    if (sp < 0) sp = n;
    String word = text.substring(start, sp);
    start = sp + 1;
    if (word.length() == 0) continue;
    String test = line.length() ? line + " " + word : word;
    if (tft.textWidth(test) > maxW && line.length()) {
      emit(line);
      line = word;
    } else {
      line = test;
    }
  }
  if (line.length()) emit(line);
  return lines;
}

void showMessage(const String& msg, uint16_t color) {
  tft.fillScreen(TFT_BLACK);
  tft.setTextFont(2);
  tft.setTextColor(color, TFT_BLACK);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(toAscii(msg), SCR_W / 2, SCR_H / 2);
  tft.setTextDatum(TL_DATUM);
}

// ------------------------------ رسم السؤال والخيارات ------------------------------
void drawResult(const String& qRaw, JsonArray opts, int cIdx, const String& correctRaw) {
  String q = toAscii(qRaw);
  int n = min((int)opts.size(), 8);
  String optTxt[8];
  for (int i = 0; i < n; i++) {
    String o = opts[i].as<String>();
    optTxt[i] = String((char)('A' + i)) + ") " + toAscii(o);
  }

  // اختيار أكبر خط يتّسع له المحتوى (خط 2 ثم خط 1)
  int font = 2, lineH = 18;
  for (font = 2;; font--) {
    tft.setTextFont(font);
    lineH = tft.fontHeight() + 2;
    int total = wrapText(q, PAD, 0, SCR_W - 2 * PAD, lineH, false) * lineH + 6;
    for (int i = 0; i < n; i++)
      total += wrapText(optTxt[i], PAD + 2, 0, SCR_W - 2 * PAD - 4, lineH, false) * lineH + 4;
    if (total <= LIMIT_Y || font == 1) break;
  }

  tft.fillScreen(TFT_BLACK);
  tft.setTextFont(font);

  // السؤال
  int y = 2;
  tft.setTextColor(TFT_CYAN, TFT_BLACK);
  int ql = wrapText(q, PAD, y, SCR_W - 2 * PAD, lineH, true);
  y += ql * lineH + 6;

  // الخيارات (الصحيح بخلفية خضراء)
  for (int i = 0; i < n; i++) {
    int lines = wrapText(optTxt[i], PAD + 2, y, SCR_W - 2 * PAD - 4, lineH, false);
    bool ok = (i == cIdx);
    if (ok) {
      tft.fillRoundRect(2, y - 2, SCR_W - 4, lines * lineH + 3, 4, TFT_GREEN);
      tft.setTextColor(TFT_BLACK, TFT_GREEN);
    } else {
      tft.setTextColor(TFT_WHITE, TFT_BLACK);
    }
    wrapText(optTxt[i], PAD + 2, y, SCR_W - 2 * PAD - 4, lineH, true);
    y += lines * lineH + 4;
  }

  // الشريط السفلي: الإجابة
  tft.fillRect(0, SCR_H - FOOT, SCR_W, FOOT, TFT_DARKGREEN);
  tft.setTextFont(2);
  tft.setTextColor(TFT_WHITE, TFT_DARKGREEN);
  String ans;
  if (cIdx >= 0 && cIdx < n) ans = "ANSWER: " + String((char)('A' + cIdx)) + " - " + toAscii(opts[cIdx].as<String>());
  else ans = "ANSWER: " + toAscii(correctRaw);
  while (tft.textWidth(ans) > SCR_W - 8 && ans.length() > 4) ans.remove(ans.length() - 1);
  tft.drawString(ans, 4, SCR_H - FOOT + 4);
}

// ------------------------------ جلب النتيجة ------------------------------
void fetchResult() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    return;
  }

  WiFiClientSecure client;
  client.setInsecure();               // بدون تحقق من الشهادة (للتبسيط)
  HTTPClient http;
  http.setTimeout(30000);             // Render المجاني قد يحتاج وقتاً للاستيقاظ
  http.setFollowRedirects(HTTPC_FORCE_FOLLOW_REDIRECTS);

  if (!http.begin(client, RESULT_URL)) return;
  int code = http.GET();

  if (code == 200) {
    String payload = http.getString();
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      long id = doc["id"] | 0L;
      if (id != lastId) {             // نعيد الرسم فقط عند وصول نتيجة جديدة
        lastId = id;
        String status = doc["status"] | "waiting";
        if (status == "success") {
          drawResult(doc["question"] | "", doc["options"].as<JsonArray>(),
                     doc["correct_index"] | -1, doc["correct"] | "");
        } else if (status == "error") {
          showMessage("Error: " + String(doc["message"] | "unknown"), TFT_RED);
        } else {
          showMessage("Waiting for a question...", TFT_YELLOW);
        }
      }
    } else {
      Serial.println(String("JSON error: ") + err.c_str());
    }
  } else {
    Serial.printf("HTTP error: %d\n", code);
  }
  http.end();
}

// ------------------------------ setup / loop ------------------------------
void setup() {
  Serial.begin(115200);

  pinMode(BL_PIN, OUTPUT);
  digitalWrite(BL_PIN, HIGH);         // تشغيل الإضاءة الخلفية

  tft.init();
  tft.setRotation(1);                 // جرّب 3 إذا كانت الشاشة مقلوبة
  tft.fillScreen(TFT_BLACK);

  showMessage("Connecting to WiFi...", TFT_WHITE);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected: " + WiFi.localIP().toString());
  showMessage("WiFi OK - contacting server...", TFT_GREEN);

  fetchResult();
  lastPoll = millis();
}

void loop() {
  if (millis() - lastPoll >= POLL_MS) {
    lastPoll = millis();
    fetchResult();
  }
}
