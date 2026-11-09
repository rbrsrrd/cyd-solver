// ضع هذا الملف مكان: Documents/Arduino/libraries/TFT_eSPI/User_Setup.h
// إعدادات لوحة ESP32-2432S028 (CYD) - شاشة ILI9341 مقاس 2.8 بوصة

#define USER_SETUP_ID 202

#define ILI9341_2_DRIVER      // إذا ظهرت ألوان/صورة خاطئة جرّب ILI9341_DRIVER بدلها
#define TFT_WIDTH  240
#define TFT_HEIGHT 320

// #define TFT_INVERSION_ON   // فعّلها لو كانت الألوان معكوسة (بعض إصدارات اللوحة)

#define USE_HSPI_PORT
#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14
#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST  -1

#define TFT_BL   21           // الإضاءة الخلفية
#define TFT_BACKLIGHT_ON HIGH

#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4
#define SMOOTH_FONT

#define SPI_FREQUENCY       40000000
#define SPI_READ_FREQUENCY  20000000
