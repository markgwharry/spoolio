// WARNING: HX711 SCK on GPIO0 (D3) must be held high at boot. Fit a 4.7–10 kΩ pull-up to 3.3 V or route SCK to another pin,
// and disconnect the HX711 while flashing if the pull-up is not fitted, otherwise the ESP8266 will stay in bootloader mode.
//
// Spoolio ESP8266 — OLED + LEDs + NFC + Scale (Live activity + orphan-tag + boot logo)
//
// Hardware: WeMos D1 Mini (ESP8266)
//   OLED (I2C):    SDA=D2 (GPIO4), SCL=D1 (GPIO5)  [SSD1306 by default; SH1106 optional]
//   HX711:         DT=D7 (GPIO13), SCK=D5 (GPIO14)   [moved off GPIO0 to avoid boot issues]
//   PN532 (HSU):   TX=D5 (GPIO14) -> ESP RX, RX=D6 (GPIO12) <- ESP TX
//   WS2812B LEDs:  DIN=D4 (GPIO2) (+ 330Ω series, 1000µF across 5V/GND)
//
// Features:
// - Boot splash with tiny Spoolio logo + short LED swirl animation
// - Orphan tag detection (first time ever seen by THIS device): magenta flash
// - Live OLED status: Ready, Weighing w/ weight, Uploading, Done, and error states
// - Attempts to parse basic fields from NFC payload to show ID / Material / Color / Tare
// - Simple persistence of "seen tags" using EEPROM (hash-based set)
//
// Notes:
// - WiFi: Configured via captive portal (connect to "Spoolio-Setup") or USB serial
// - API key & Device ID: Configured via USB serial commands (type 'help' for options)
// - If your OLED is SH1106, set USE_SH1106 to 1 and include a SH1106 library instead.
//
// -----------------------------------------------------------------------------

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <WiFiManager.h>
#include "SpoolioTlsTrust.h"
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#if !defined(USE_SH1106)
#define USE_SH1106 1
#endif
#if USE_SH1106
#include <Adafruit_SH110X.h>
#else
#include <Adafruit_SSD1306.h>   // SSD1306 default
#endif
#include <PN532_I2C.h>
#include <PN532.h>
#include <ArduinoJson.h>
#include <EEPROM.h>
#include "HX711.h"

struct TagInfo {
  String id;
  String material;
  String color;
  String tare;
  String manufacturer;  // e.g., "Bambu", "Prusament"
  String displayName;   // pre-formatted "Bambu PLA Green" for OLED
  float weightStart;    // initial filament weight (for % remaining calc)
  float tareWeight;     // numeric tare for calculations
};

void configureSpoolioTls(WiFiClientSecure& client) {
#if ALLOW_INSECURE_TLS
  client.setInsecure();
#else
  static BearSSL::X509List trustAnchor(SPOOLIO_ROOT_CA);
  client.setTrustAnchors(&trustAnchor);
#endif
}

// ====== CONFIG ======
// Select OLED controller (default SH1106 for your module). Set to 0 for SSD1306.
#ifndef USE_SH1106
#define USE_SH1106 1
#endif

// -------- Temporary headless/mirror-to-Serial controls --------
// When HEADLESS_DISPLAY == 1, OLED hardware is skipped entirely and all UI is sent to Serial.
// When MIRROR_DISPLAY_TO_SERIAL == 1, text that would go to the OLED is also echoed to Serial.
#ifndef HEADLESS_DISPLAY
#define HEADLESS_DISPLAY 0
#endif
#ifndef MIRROR_DISPLAY_TO_SERIAL
#define MIRROR_DISPLAY_TO_SERIAL 1
#endif

// Option to bypass PN532 entirely while testing OLED/LED/scale
#ifndef DISABLE_NFC
#define DISABLE_NFC 0
#endif

// WiFi credentials managed by WiFiManager (stored in ESP flash automatically)
// API key and device ID stored in EEPROM (configured via USB serial commands)

// Minimum mass (in grams) that must be present on the scale for a read to count.
const float MIN_WEIGHT_GRAMS = 100.0f;

// ---- API configuration ----
const char* api_host = "www.spoolio.co.uk";
const int   api_port = 443;

// EEPROM layout: [0-511: seen tags] [512-575: API key] [576-607: device ID]
#define EEPROM_API_KEY_ADDR   512
#define EEPROM_API_KEY_LEN    64
#define EEPROM_DEVICE_ID_ADDR 576
#define EEPROM_DEVICE_ID_LEN  32
#define EEPROM_TOTAL_SIZE     608

// Runtime config (loaded from EEPROM on boot, set via serial commands)
char api_key[EEPROM_API_KEY_LEN] = "";
char device_id[EEPROM_DEVICE_ID_LEN] = "unconfigured";

// WiFiManager instance
WiFiManager wifiManager;

// API Endpoints
const char* weight_update_endpoint = "/api/hardware/weight-update";
const char* spool_lookup_endpoint  = "/api/hardware/spool/";
const char* event_endpoint         = "/api/hardware/event";
const char* heartbeat_endpoint     = "/api/hardware/heartbeat";

static String buildApiUrl(const char* endpoint) {
  return String("https://") + api_host + endpoint;
}

// ====== OLED ======
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#if USE_SH1106
Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
#define WHITE   SH110X_WHITE
#define BLACK   SH110X_BLACK
#define INVERSE SH110X_INVERSE
#else
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
#define WHITE   SSD1306_WHITE
#define BLACK   SSD1306_BLACK
#define INVERSE SSD1306_INVERSE
#endif

// Track whether the display initialized successfully at runtime (or is disabled in headless mode)
bool gDisplayAvailable = true;

// ====== WS2812 ======
#define LED_PIN    2
#define NUM_LEDS   25
#define BRIGHTNESS 200
Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// ====== PN532 (I2C) ======
PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);

// ====== HX711 ======
#define DT_PIN  D7
#define SCK_PIN D5
HX711 scale;
float calibration_factor = 366.0;  // Calibrated with 380g & 843.5g reference spools (compromise)

// Scale stability helpers
bool scaleNeedsReinit = false;
unsigned long lastScaleRead = 0;

// ====== EEPROM "Seen Tags" (very light hash set) ======
// Note: Total EEPROM is EEPROM_TOTAL_SIZE (608 bytes) - first 512 for tags, rest for config
#define SEEN_SLOTS   64         // number of 8-byte slots (hash + flag) in first 512 bytes
#define SLOT_SIZE    8

// ====== LED Anim ======
enum LedMode { LED_IDLE, LED_WAIT_NFC, LED_READING, LED_MEASURING, LED_UPLOAD, LED_SUCCESS, LED_ERROR, LED_ORPHAN, LED_BOOTSWIRL };
LedMode ledMode = LED_IDLE;
unsigned long animStart = 0;

// ====== NFC Buffers ======
String lastRead1, lastRead2, lastRead3;
String confirmedNFC = "";
String confirmedUidHex = "";
String confirmedAscii = "";      // parsed ASCII payload, if available
String gPendingAscii = "";       // most recent ASCII candidate while confirming

// NFC UX helpers
bool gNfcPresent = false;            // true while a tag is detected near the reader
bool gReadingShown = false;          // whether we've shown the reading UI this session
unsigned long gFirstReadTime = 0;    // timestamp of first ANY read (for absolute timeout)
String gMostSeenUid = "";            // track most frequently seen UID
uint8_t gMostSeenCount = 0;          // count of most seen UID
String gCurrentUid = "";             // current candidate
uint8_t gCurrentCount = 0;           // count of current candidate
const unsigned long NFC_CONFIRM_TIMEOUT_MS = 2000;  // accept any UID after this timeout

// Boot logo bitmap (128x64)
#define LOGO_WIDTH 128
#define LOGO_HEIGHT 64
const uint8_t PROGMEM splash_logo[] = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0xff, 0xfc, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x5f, 0xff, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0xff, 0xff, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0xf8, 0x1f, 0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0xc0, 0x07, 0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x07, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1e, 0x00, 0x07, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1c, 0x00, 0x0f, 0x78, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3c, 0x00, 0x1e, 0x38, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x38, 0x05, 0xbc, 0x3c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x78, 0x0f, 0xf8, 0x3c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x78, 0x1f, 0xf0, 0x3c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x70, 0x3c, 0x78, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x70, 0x38, 0x78, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x70, 0x38, 0x38, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x70, 0x3c, 0x38, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x70, 0x3c, 0x78, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x78, 0x3f, 0xf0, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x78, 0x7f, 0xc0, 0x3c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x38, 0xf3, 0xc0, 0x3c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3d, 0xe0, 0x00, 0x38, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1f, 0xc0, 0x00, 0x78, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0f, 0x80, 0x01, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x80, 0x03, 0xe0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0xe0, 0x07, 0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0xf0, 0x1f, 0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7f, 0xff, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7f, 0xff, 0xfc, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7f, 0xff, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x80, 0x00, 0x01, 0x90, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x0f, 0xc0, 0x00, 0x01, 0x98, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x0c, 0x1f, 0x0e, 0x3d, 0x91, 0xc0, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x0f, 0x1f, 0x1f, 0x7f, 0x93, 0xe0, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x9d, 0xb3, 0xe7, 0x93, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0xd8, 0xb1, 0xe3, 0x92, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x0c, 0xd9, 0xb3, 0xe7, 0x93, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x0f, 0xdf, 0x1f, 0x7f, 0xd3, 0xe0, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x9f, 0x0e, 0x3c, 0xd1, 0xc0, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};

// ====== Utility ======
void oledMsg(const String& l1, const String& l2="", const String& l3="") {
#if MIRROR_DISPLAY_TO_SERIAL
  Serial.println("[UI] " + l1);
  if (l2.length()) Serial.println("      " + l2);
  if (l3.length()) Serial.println("      " + l3);
#endif
  if (gDisplayAvailable) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(WHITE);
    display.setCursor(0,0);
    display.println(l1);
    if (l2.length()) display.println(l2);
    if (l3.length()) display.println(l3);
    display.display();
  }
}

void oledWeighScreen(const TagInfo& ti, float weight, const String& status) {
#if MIRROR_DISPLAY_TO_SERIAL
  Serial.print("[Weigh] "); Serial.println(ti.displayName.length() ? ti.displayName : "(unknown spool)");
  Serial.print("        Tare: "); Serial.print(ti.tare.length() ? ti.tare : "?"); Serial.println(" g");
  Serial.print("        Weight: "); Serial.print(weight, 1); Serial.println(" g");
  Serial.print("        Status: "); Serial.println(status);
#endif
  if (gDisplayAvailable) {
    display.clearDisplay();
    display.setTextColor(WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    // Show display name (e.g., "Bambu PLA Green") - truncate if too long
    String dispName = ti.displayName.length() ? ti.displayName : "(unknown)";
    if (dispName.length() > 21) dispName = dispName.substring(0, 20) + ".";
    display.println(dispName);
    // Show tare weight on second line
    display.print("Tare: ");
    display.print(ti.tare.length() ? ti.tare : "?");
    display.println(" g");

    // Large weight display
    display.setTextSize(2);
    display.setCursor(0, 24);
    char buf[16]; dtostrf(weight, 5, 1, buf);
    display.print(buf); display.println(" g");

    // Status at bottom
    display.setTextSize(1);
    display.setCursor(0, 56);
    display.print(status);
    display.display();
  }
}

// Enhanced weighing screen with progress bar and remaining filament
void oledWeighScreenWithProgress(const TagInfo& ti, float weight, float progress, unsigned long elapsed, unsigned long duration) {
  if (!gDisplayAvailable) return;

  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);

  // Show display name
  String dispName = ti.displayName.length() ? ti.displayName : "(unknown)";
  if (dispName.length() > 21) dispName = dispName.substring(0, 20) + ".";
  display.println(dispName);

  // Calculate and show remaining filament (weight - tare)
  float remaining = weight - ti.tareWeight;
  if (remaining < 0) remaining = 0;
  display.print("Filament: ");
  display.print(remaining, 0);
  display.print("g");

  // Show percentage if we have weight_start
  if (ti.weightStart > 0) {
    int pct = (int)((remaining / ti.weightStart) * 100);
    if (pct > 100) pct = 100;
    if (pct < 0) pct = 0;
    display.print(" (");
    display.print(pct);
    display.print("%)");
  }
  display.println();

  // Large weight display
  display.setTextSize(2);
  display.setCursor(0, 22);
  char buf[16]; dtostrf(weight, 5, 1, buf);
  display.print(buf); display.println(" g");

  // Progress bar (full width, near bottom)
  int barY = 48;
  int barHeight = 8;
  int barWidth = 120;
  int barX = 4;

  // Draw bar outline
  display.drawRect(barX, barY, barWidth, barHeight, WHITE);

  // Fill progress
  int fillWidth = (int)(progress * (barWidth - 2));
  if (fillWidth > 0) {
    display.fillRect(barX + 1, barY + 1, fillWidth, barHeight - 2, WHITE);
  }

  // Time remaining text
  display.setTextSize(1);
  display.setCursor(0, 58);
  if (progress < 1.0) {
    int secsLeft = (duration - elapsed) / 1000;
    display.print("Stabilizing... ");
    display.print(secsLeft);
    display.print("s");
  } else {
    display.print("Uploading...");
  }

  display.display();
}

// Draw animated checkmark for success screen
void oledSuccessScreen(const TagInfo& ti, float weight, int animFrame) {
  if (!gDisplayAvailable) return;

  display.clearDisplay();
  display.setTextColor(WHITE);

  // Draw checkmark animation (grows from center)
  int cx = 100;  // checkmark center x
  int cy = 20;   // checkmark center y
  int size = min(animFrame * 2, 16);  // grow up to size 16

  if (size > 0) {
    // Checkmark: short line down-left, long line down-right
    int x1 = cx - size/2;
    int y1 = cy;
    int x2 = cx - size/4;
    int y2 = cy + size/2;
    int x3 = cx + size/2;
    int y3 = cy - size/3;

    display.drawLine(x1, y1, x2, y2, WHITE);
    display.drawLine(x2, y2, x3, y3, WHITE);
    // Draw thicker by offsetting
    display.drawLine(x1, y1+1, x2, y2+1, WHITE);
    display.drawLine(x2, y2+1, x3, y3+1, WHITE);
  }

  // Circle around checkmark
  if (animFrame > 4) {
    int radius = min((animFrame - 4) * 2, 14);
    display.drawCircle(cx, cy + 2, radius, WHITE);
  }

  // Text info
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Saved!");

  // Show remaining filament prominently
  float remaining = weight - ti.tareWeight;
  if (remaining < 0) remaining = 0;

  display.setTextSize(2);
  display.setCursor(0, 14);
  display.print(remaining, 0);
  display.print("g");

  // Percentage bar if we have start weight
  if (ti.weightStart > 0) {
    int pct = (int)((remaining / ti.weightStart) * 100);
    if (pct > 100) pct = 100;
    if (pct < 0) pct = 0;

    // Draw percentage bar
    int barY = 38;
    int barWidth = 80;
    display.setTextSize(1);
    display.setCursor(0, barY);
    display.print(pct);
    display.print("% left");

    // Mini bar
    display.drawRect(0, barY + 10, barWidth, 6, WHITE);
    int fillWidth = (pct * (barWidth - 2)) / 100;
    if (fillWidth > 0) {
      display.fillRect(1, barY + 11, fillWidth, 4, WHITE);
    }
  }

  display.setTextSize(1);
  display.setCursor(0, 56);
  String dispName = ti.displayName.length() ? ti.displayName : "";
  if (dispName.length() > 21) dispName = dispName.substring(0, 20) + ".";
  display.print(dispName);

  display.display();
}

// Draw a small animated spool icon
void drawSpoolIcon(int x, int y, int frame) {
  // Outer ring (spool sides)
  display.drawCircle(x, y, 14, WHITE);
  display.drawCircle(x, y, 13, WHITE);

  // Inner hub
  display.fillCircle(x, y, 4, WHITE);

  // Filament wound on spool - rotating lines
  for (int i = 0; i < 6; i++) {
    float angle = (i * 60 + frame * 15) * PI / 180.0;
    int x1 = x + cos(angle) * 6;
    int y1 = y + sin(angle) * 6;
    int x2 = x + cos(angle) * 11;
    int y2 = y + sin(angle) * 11;
    display.drawLine(x1, y1, x2, y2, WHITE);
  }
}

// Idle/ready screen with WiFi status and animated spool
void oledReadyScreen() {
  if (!gDisplayAvailable) return;

  display.clearDisplay();
  display.setTextColor(WHITE);

  // Animated spool icon on the right side
  int frame = (millis() / 200) % 24;
  drawSpoolIcon(100, 28, frame);

  // WiFi icon in top right corner
  int wifiX = 110;
  int wifiY = 0;
  if (WiFi.status() == WL_CONNECTED) {
    int rssi = WiFi.RSSI();
    int bars = 1;
    if (rssi > -60) bars = 4;
    else if (rssi > -70) bars = 3;
    else if (rssi > -80) bars = 2;

    for (int i = 0; i < 4; i++) {
      int barH = 2 + i * 2;
      int barX = wifiX + i * 4;
      if (i < bars) {
        display.fillRect(barX, wifiY + 8 - barH, 3, barH, WHITE);
      } else {
        display.drawRect(barX, wifiY + 8 - barH, 3, barH, WHITE);
      }
    }
  } else {
    // WiFi disconnected - small X
    display.drawLine(wifiX + 2, wifiY + 2, wifiX + 10, wifiY + 8, WHITE);
    display.drawLine(wifiX + 10, wifiY + 2, wifiX + 2, wifiY + 8, WHITE);
  }

  // Main title with larger text
  display.setTextSize(2);
  display.setCursor(0, 0);
  display.println("Spoolio");

  // Instruction text
  display.setTextSize(1);
  display.setCursor(0, 22);
  display.println("Place spool");
  display.println("on scale");

  // Animated arrow pointing down
  int arrowY = 44 + ((millis() / 300) % 3);
  display.setCursor(30, arrowY);
  display.print("v v v");

  // Show IP address at bottom if connected
  display.setCursor(0, 56);
  if (WiFi.status() == WL_CONNECTED) {
    display.print(WiFi.localIP());
  } else {
    display.print("WiFi offline");
  }

  display.display();
}

// NFC reading screen with animated spinner
void oledNfcReadingScreen(int frame) {
  if (!gDisplayAvailable) return;

  display.clearDisplay();
  display.setTextColor(WHITE);

  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Reading NFC...");
  display.println();
  display.println("Hold spool steady");

  // Draw spinning indicator
  int cx = 100;
  int cy = 40;
  int radius = 12;

  // Draw circle outline
  display.drawCircle(cx, cy, radius, WHITE);

  // Draw rotating dot
  float angle = (frame % 12) * (2 * 3.14159 / 12);
  int dotX = cx + (int)(cos(angle) * (radius - 3));
  int dotY = cy + (int)(sin(angle) * (radius - 3));
  display.fillCircle(dotX, dotY, 3, WHITE);

  // Progress dots at bottom
  display.setCursor(0, 56);
  int progress = frame % 8;
  for (int i = 0; i < 8; i++) {
    if (i <= progress) {
      display.fillRect(i * 8, 58, 6, 4, WHITE);
    } else {
      display.drawRect(i * 8, 58, 6, 4, WHITE);
    }
  }

  display.display();
}

// ---- API helpers ----
void ledAnimate();
void handleSerialCommands();

static bool postEvent(const char* eventType, const String& tagId, const String& message = String()) {
  if (!eventType || !eventType[0]) return false;
  if (WiFi.status() != WL_CONNECTED) return false;
  WiFiClientSecure client; configureSpoolioTls(client);
  HTTPClient http;
  if (!http.begin(client, buildApiUrl(event_endpoint))) return false;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + api_key);
  DynamicJsonDocument doc(256);
  doc["event_type"] = eventType;
  if (tagId.length()) doc["nfc_tag_id"] = tagId;
  if (message.length()) doc["message"] = message;
  String payload; serializeJson(doc, payload);
  http.POST(payload);
  http.end();
  return true;
}

// Fetch spool information from API by tag ID
// Returns true if successful and populates the TagInfo struct
static bool fetchSpoolInfo(const String& tagId, TagInfo& ti) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[API] WiFi not connected, skipping lookup");
    return false;
  }

  Serial.print("[API] Looking up tag: "); Serial.println(tagId);

  WiFiClientSecure client;
  configureSpoolioTls(client);
  client.setTimeout(3000);  // 3 second timeout

  HTTPClient http;
  http.setTimeout(3000);
  String url = buildApiUrl(spool_lookup_endpoint) + tagId;
  Serial.print("[API] URL: "); Serial.println(url);

  if (!http.begin(client, url)) {
    Serial.println("[API] Failed to begin HTTP request");
    return false;
  }

  http.addHeader("Authorization", String("Bearer ") + api_key);

  Serial.println("[API] Sending GET request...");
  int code = http.GET();
  Serial.print("[API] Response code: "); Serial.println(code);

  if (code == 200) {
    String response = http.getString();
    Serial.print("[API] Response: "); Serial.println(response);
    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, response);
    if (!error) {
      // Extract fields from JSON response
      if (doc.containsKey("id")) {
        ti.id = String(doc["id"].as<int>());
      }

      // Try to get material name, fall back to ID if not available
      if (doc.containsKey("material") && doc["material"].is<JsonObject>()) {
        ti.material = doc["material"]["name"].as<String>();
      } else if (doc.containsKey("material_name")) {
        ti.material = doc["material_name"].as<String>();
      } else if (doc.containsKey("material_id")) {
        ti.material = "Mat#" + String(doc["material_id"].as<int>());
      }

      // Try to get color name, fall back to ID if not available
      if (doc.containsKey("color") && doc["color"].is<JsonObject>()) {
        ti.color = doc["color"]["name"].as<String>();
      } else if (doc.containsKey("color_name")) {
        ti.color = doc["color_name"].as<String>();
      } else if (doc.containsKey("color_id")) {
        ti.color = "Col#" + String(doc["color_id"].as<int>());
      }

      // Try various tare weight fields
      if (doc.containsKey("tare_weight")) {
        ti.tareWeight = doc["tare_weight"].as<float>();
        ti.tare = String(ti.tareWeight, 1);
      }

      // Get initial filament weight for percentage calculation
      if (doc.containsKey("weight_start")) {
        ti.weightStart = doc["weight_start"].as<float>();
      }

      // Get manufacturer name
      if (doc.containsKey("manufacturer") && doc["manufacturer"].is<JsonObject>()) {
        ti.manufacturer = doc["manufacturer"]["name"].as<String>();
      } else if (doc.containsKey("manufacturer_name")) {
        ti.manufacturer = doc["manufacturer_name"].as<String>();
      }

      // Build display name: "Bambu PLA Green" format
      ti.displayName = "";
      if (ti.manufacturer.length()) {
        ti.displayName = ti.manufacturer + " ";
      }
      if (ti.material.length()) {
        ti.displayName += ti.material;
      }
      if (ti.color.length()) {
        if (ti.displayName.length()) ti.displayName += " ";
        ti.displayName += ti.color;
      }
      if (ti.displayName.length() == 0) {
        ti.displayName = "Unknown spool";
      }

      http.end();
      Serial.print("[API] Parsed - ID:"); Serial.print(ti.id);
      Serial.print(" Display:"); Serial.print(ti.displayName);
      Serial.print(" Tare:"); Serial.println(ti.tare);
      return true;
    } else {
      Serial.print("[API] JSON parse error: "); Serial.println(error.c_str());
    }
  } else if (code > 0) {
    Serial.print("[API] HTTP error: "); Serial.println(code);
  } else {
    Serial.print("[API] Connection error: "); Serial.println(http.errorToString(code));
  }

  http.end();
  return false;
}

// Returns: 0=OK, 1=Orphan (404), 2=Other error
static uint8_t uploadWeightApi(const String& tagId, float weight) {
  if (WiFi.status() != WL_CONNECTED) return 2;

  WiFiClientSecure client;
  configureSpoolioTls(client);
  client.setTimeout(1500);

  HTTPClient http;
  if (!http.begin(client, buildApiUrl(weight_update_endpoint))) return 2;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + api_key);

  DynamicJsonDocument doc(256);
  doc["nfc_tag_id"] = tagId;
  doc["weight"] = weight;
  String payload; serializeJson(doc, payload);

  int code = http.POST(payload);
  if (code > 0) {
    Serial.printf("Upload response: %d\n", code);
    if (code == 404) {
      String body = http.getString();
      if (body.length()) Serial.println(body);
      http.end();
      return 1;
    }
  } else {
    Serial.printf("Upload failed: %s\n", http.errorToString(code).c_str());
  }
  http.end();
  return (code >= 200 && code < 300) ? 0 : 2;
}

// Non-blocking Serial command handler for configuration and debugging
void handleSerialCommands() {
  static String buf = "";
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      String cmdOriginal = buf; buf = "";  // Keep original case for API key
      cmdOriginal.trim();
      String cmd = cmdOriginal;
      cmd.toLowerCase();
      if (cmd.length() == 0) return;

      if (cmd == "h" || cmd == "help") {
        Serial.println("");
        Serial.println("=== Spoolio Serial Commands ===");
        Serial.println("");
        Serial.println("WiFi Configuration:");
        Serial.println("  wifi_status     Show WiFi connection status");
        Serial.println("  wifi_ap         Start AP mode for WiFi setup");
        Serial.println("  wifi_reset      Clear saved WiFi and restart");
        Serial.println("");
        Serial.println("Device Configuration:");
        Serial.println("  api_key <key>   Set API key (from spoolio.co.uk)");
        Serial.println("  device_id <id>  Set device identifier");
        Serial.println("  config          Show current configuration");
        Serial.println("");
        Serial.println("Scale Commands:");
        Serial.println("  t/tare          Zero the scale");
        Serial.println("  w/weight        Read current weight");
        Serial.println("  c <factor>      Set calibration factor");
        Serial.println("");
        Serial.println("Diagnostics:");
        Serial.println("  status          Show system status");
        Serial.println("  i2cscan         Scan I2C bus");
        Serial.println("  reboot          Restart device");
        Serial.println("");
        return;
      }

      // === WiFi Commands ===
      if (cmd == "wifi_status") {
        Serial.println("[WiFi] Status:");
        if (WiFi.status() == WL_CONNECTED) {
          Serial.print("  Connected to: "); Serial.println(WiFi.SSID());
          Serial.print("  IP address:   "); Serial.println(WiFi.localIP());
          Serial.print("  Signal:       "); Serial.print(WiFi.RSSI()); Serial.println(" dBm");
        } else {
          Serial.println("  Not connected");
        }
        Serial.print("  MAC address:  "); Serial.println(WiFi.macAddress());
        return;
      }

      if (cmd == "wifi_ap") {
        Serial.println("[WiFi] Starting AP mode for configuration...");
        Serial.println("  1. Connect to WiFi network: Spoolio-Setup");
        Serial.println("  2. Open http://192.168.4.1 in browser");
        Serial.println("  3. Select your WiFi network and enter password");
        oledMsg("WiFi Setup", "Connect to:", "Spoolio-Setup");
        ledBeginMode(LED_ORPHAN);
        wifiManager.setConfigPortalTimeout(300);  // 5 min timeout
        if (!wifiManager.startConfigPortal("Spoolio-Setup")) {
          Serial.println("[WiFi] Config portal timed out or cancelled");
        } else {
          Serial.println("[WiFi] Configuration saved, restarting...");
        }
        delay(1000);
        ESP.restart();
        return;
      }

      if (cmd == "wifi_reset") {
        Serial.println("[WiFi] Clearing saved credentials and restarting...");
        wifiManager.resetSettings();
        delay(500);
        ESP.restart();
        return;
      }

      // === Device Configuration Commands ===
      if (cmd.startsWith("api_key ")) {
        String key = cmdOriginal.substring(8);  // Use original case
        key.trim();
        if (key.length() > 0 && key.length() < EEPROM_API_KEY_LEN) {
          saveApiKeyToEeprom(key.c_str());
          Serial.print("[Config] API key set: ");
          for (int i = 0; i < 8 && i < key.length(); i++) Serial.print(key[i]);
          Serial.println("...");
        } else {
          Serial.println("Usage: api_key <your-api-key>");
          Serial.println("  Get your API key from the Hardware page at spoolio.co.uk");
        }
        return;
      }

      if (cmd.startsWith("device_id ")) {
        String id = cmdOriginal.substring(10);
        id.trim();
        if (id.length() > 0 && id.length() < EEPROM_DEVICE_ID_LEN) {
          saveDeviceIdToEeprom(id.c_str());
          Serial.print("[Config] Device ID set: "); Serial.println(device_id);
        } else {
          Serial.println("Usage: device_id <your-device-id>");
        }
        return;
      }

      if (cmd == "config") {
        Serial.println("[Config] Current configuration:");
        Serial.print("  Device ID:  "); Serial.println(device_id);
        Serial.print("  API key:    ");
        if (strlen(api_key) > 0) {
          for (int i = 0; i < 8 && api_key[i]; i++) Serial.print(api_key[i]);
          Serial.println("...");
        } else {
          Serial.println("(not set)");
        }
        Serial.print("  API host:   "); Serial.println(api_host);
        Serial.print("  WiFi SSID:  "); Serial.println(WiFi.SSID().length() > 0 ? WiFi.SSID() : "(not connected)");
        return;
      }

      if (cmd == "reboot" || cmd == "restart") {
        Serial.println("[System] Restarting...");
        delay(500);
        ESP.restart();
        return;
      }

      // === Scale Commands ===
      if (cmd == "t" || cmd == "tare") {
        scale.tare();
        Serial.println("[Scale] Tare complete");
        return;
      }

      if (cmd == "w" || cmd == "weight") {
        float w = scale.get_units(10);
        Serial.print("[Scale] Weight: "); Serial.print(w, 1); Serial.println(" g");
        return;
      }

      if (cmd.startsWith("c ") || cmd.startsWith("cal ") || cmd.startsWith("cf ")) {
        int sp = cmd.indexOf(' ');
        if (sp > 0) {
          float f = cmd.substring(sp+1).toFloat();
          if (f != 0.0f) {
            calibration_factor = f;
            scale.set_scale(calibration_factor);
            Serial.print("[Scale] Calibration factor set to "); Serial.println(calibration_factor, 3);
            return;
          }
        }
        Serial.println("Usage: c <factor>  e.g., c 439.0");
        return;
      }

      // === Diagnostics ===
      if (cmd == "status") {
        Serial.println("[Status]");
        Serial.print("  WiFi:       "); Serial.println(WiFi.isConnected() ? "connected" : "not connected");
        if (WiFi.isConnected()) {
          Serial.print("  IP:         "); Serial.println(WiFi.localIP());
          Serial.print("  RSSI:       "); Serial.print(WiFi.RSSI()); Serial.println(" dBm");
        }
        Serial.print("  Display:    "); Serial.println(gDisplayAvailable ? "available" : "headless");
        Serial.print("  Device ID:  "); Serial.println(device_id);
        Serial.print("  API key:    "); Serial.println(strlen(api_key) > 0 ? "configured" : "NOT SET");
#if DISABLE_NFC
        Serial.println("  NFC:        disabled");
#else
        Serial.println("  NFC:        enabled");
#endif
        Serial.print("  Cal factor: "); Serial.println(calibration_factor, 3);
        return;
      }

      if (cmd == "i2cscan" || cmd == "i2c") {
        Serial.println("[I2C] Scanning...");
        byte found = 0;
        for (byte addr = 1; addr < 127; addr++) {
          Wire.beginTransmission(addr);
          byte err = Wire.endTransmission();
          if (err == 0) {
            Serial.print("  Found device at 0x");
            if (addr < 16) Serial.print('0');
            Serial.println(addr, HEX);
            found++;
          }
        }
        if (found == 0) Serial.println("  No I2C devices detected");
        // Try OLED reinit
        bool ok = false;
        if (!gDisplayAvailable) {
#if USE_SH1106
          ok = display.begin(0x3C, true);
          if (!ok) ok = display.begin(0x3D, true);
#else
          ok = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
          if (!ok) ok = display.begin(SSD1306_SWITCHCAPVCC, 0x3D);
#endif
          gDisplayAvailable = ok;
        }
        Serial.println(String("[I2C] OLED: ") + (gDisplayAvailable ? "OK" : "not found"));
        return;
      }

      Serial.println("Unknown command. Type 'help' for options.");
    } else {
      if (buf.length() < 64) buf += ch;
    }
  }
}

void setLEDColor(uint32_t c) { for(uint8_t i=0;i<NUM_LEDS;i++) strip.setPixelColor(i, c); strip.show(); }

void ledBeginMode(uint8_t m) { ledMode = (LedMode)m; animStart = millis(); }

// Helper: HSV to RGB for rainbow effects
uint32_t hsvToColor(uint16_t h, uint8_t s, uint8_t v) {
  uint8_t region = h / 43;
  uint8_t remainder = (h - (region * 43)) * 6;
  uint8_t p = (v * (255 - s)) >> 8;
  uint8_t q = (v * (255 - ((s * remainder) >> 8))) >> 8;
  uint8_t t = (v * (255 - ((s * (255 - remainder)) >> 8))) >> 8;

  switch (region) {
    case 0:  return strip.Color(v, t, p);
    case 1:  return strip.Color(q, v, p);
    case 2:  return strip.Color(p, v, t);
    case 3:  return strip.Color(p, q, v);
    case 4:  return strip.Color(t, p, v);
    default: return strip.Color(v, p, q);
  }
}

void ledAnimate() {
  unsigned long t = millis() - animStart;
  switch (ledMode) {
    case LED_BOOTSWIRL: {
      // Rainbow chase on boot
      for (uint8_t i = 0; i < NUM_LEDS; i++) {
        uint16_t hue = ((i * 256 / NUM_LEDS) + (t / 4)) % 256;
        uint8_t brightness = (i <= (t / 50) % NUM_LEDS) ? 150 : 20;
        strip.setPixelColor(i, hsvToColor(hue, 255, brightness));
      }
      strip.show();
      if (t > 1500) ledBeginMode(LED_IDLE);
      break;
    }
    case LED_IDLE: {
      // Gentle blue breathing with occasional sparkle
      float phase = (sin((millis() % 4000) * 2 * PI / 4000.0) + 1.0) / 2.0;
      uint8_t baseV = 5 + (uint8_t)(phase * 25);
      for (uint8_t i = 0; i < NUM_LEDS; i++) {
        // Add subtle wave across strip
        float wavePhase = (sin((millis() % 2000) * 2 * PI / 2000.0 + i * 0.3) + 1.0) / 2.0;
        uint8_t v = baseV + (uint8_t)(wavePhase * 15);
        strip.setPixelColor(i, strip.Color(0, v / 4, v));
      }
      // Occasional sparkle
      if ((millis() / 100) % 30 == 0) {
        uint8_t sparkle = (millis() / 100) % NUM_LEDS;
        strip.setPixelColor(sparkle, strip.Color(80, 80, 100));
      }
      strip.show();
      break;
    }
    case LED_WAIT_NFC: {
      // Warm orange/amber pulse with rotating highlight
      float phase = (sin((millis() % 2000) * 2 * PI / 2000.0) + 1.0) / 2.0;
      uint8_t baseR = 30 + (uint8_t)(phase * 120);
      uint8_t baseG = 15 + (uint8_t)(phase * 40);

      uint8_t highlightPos = (millis() / 80) % NUM_LEDS;
      for (uint8_t i = 0; i < NUM_LEDS; i++) {
        // Distance from highlight creates a soft glow
        int dist = abs((int)i - (int)highlightPos);
        if (dist > NUM_LEDS / 2) dist = NUM_LEDS - dist;
        float glow = 1.0 - (dist / (float)(NUM_LEDS / 2));
        glow = glow * glow;  // Square for sharper falloff

        uint8_t r = baseR + (uint8_t)(glow * 80);
        uint8_t g = baseG + (uint8_t)(glow * 30);
        strip.setPixelColor(i, strip.Color(r, g, 0));
      }
      strip.show();
      break;
    }
    case LED_READING: {
      // Cyan/purple comet effect spinning around
      uint8_t head = (t / 30) % NUM_LEDS;
      for (uint8_t i = 0; i < NUM_LEDS; i++) {
        int dist = (head - i + NUM_LEDS) % NUM_LEDS;
        if (dist < 6) {
          // Comet tail - fades from cyan to purple
          uint8_t fade = 255 - (dist * 40);
          uint8_t r = (dist * 40);
          uint8_t g = fade;
          uint8_t b = 200;
          strip.setPixelColor(i, strip.Color(r, g, b));
        } else {
          // Background dim purple
          strip.setPixelColor(i, strip.Color(10, 0, 20));
        }
      }
      strip.show();
      break;
    }
    case LED_MEASURING: {
      // Progress fill with teal color and shimmer
      float progress = (float)(t % 2000) / 2000.0;
      uint8_t fillTo = (uint8_t)(progress * NUM_LEDS);

      for (uint8_t i = 0; i < NUM_LEDS; i++) {
        if (i < fillTo) {
          // Filled portion - teal with shimmer
          float shimmer = (sin((millis() % 500) * 2 * PI / 500.0 + i * 0.5) + 1.0) / 2.0;
          uint8_t v = 100 + (uint8_t)(shimmer * 50);
          strip.setPixelColor(i, strip.Color(0, v, v - 20));
        } else if (i == fillTo) {
          // Leading edge - bright white
          strip.setPixelColor(i, strip.Color(150, 200, 200));
        } else {
          // Unfilled - dim
          strip.setPixelColor(i, strip.Color(0, 10, 10));
        }
      }
      strip.show();
      break;
    }
    case LED_UPLOAD: {
      // Quick pulse traveling up the strip
      uint8_t pulse1 = (t / 25) % NUM_LEDS;
      uint8_t pulse2 = (pulse1 + NUM_LEDS / 2) % NUM_LEDS;

      for (uint8_t i = 0; i < NUM_LEDS; i++) {
        int d1 = abs((int)i - (int)pulse1);
        int d2 = abs((int)i - (int)pulse2);
        int minDist = min(d1, d2);

        uint8_t v = (minDist < 3) ? (180 - minDist * 50) : 20;
        strip.setPixelColor(i, strip.Color(v, v, v));
      }
      strip.show();
      break;
    }
    case LED_SUCCESS: {
      // Green burst that expands from center then settles
      if (t < 500) {
        // Expanding burst
        uint8_t center = NUM_LEDS / 2;
        uint8_t radius = (t * NUM_LEDS) / 1000;
        for (uint8_t i = 0; i < NUM_LEDS; i++) {
          int dist = abs((int)i - (int)center);
          if (dist <= radius) {
            uint8_t v = 180 - (dist * 10);
            strip.setPixelColor(i, strip.Color(0, v, 0));
          } else {
            strip.setPixelColor(i, strip.Color(0, 0, 0));
          }
        }
      } else if (t < 1500) {
        // Gentle pulse
        float phase = (sin((t - 500) * 2 * PI / 400.0) + 1.0) / 2.0;
        uint8_t v = 120 + (uint8_t)(phase * 60);
        setLEDColor(strip.Color(0, v, 0));
      } else {
        // Fade out
        uint8_t fade = max(0, 180 - (int)((t - 1500) / 3));
        setLEDColor(strip.Color(0, fade, 0));
      }
      strip.show();
      if (t > 2500) ledBeginMode(LED_WAIT_NFC);
      break;
    }
    case LED_ERROR: {
      // Red strobe with shake effect
      uint8_t phase = (t / 80) % 4;
      if (phase == 0 || phase == 2) {
        setLEDColor(strip.Color(220, 0, 0));
      } else {
        setLEDColor(strip.Color(30, 0, 0));
      }
      if (t > 2500) ledBeginMode(LED_WAIT_NFC);
      break;
    }
    case LED_ORPHAN: {
      // Magenta sparkle effect for new/unknown tag
      for (uint8_t i = 0; i < NUM_LEDS; i++) {
        float phase = (sin((t / 100.0) + i * 0.8) + 1.0) / 2.0;
        uint8_t v = 50 + (uint8_t)(phase * 170);
        strip.setPixelColor(i, strip.Color(v, 0, v));
      }
      strip.show();
      if (t > 2000) ledBeginMode(LED_WAIT_NFC);
      break;
    }
  }
}

// Derive how many identical NFC reads we have in a row (0..3)
static uint8_t stableReadProgress() {
  if (lastRead1.length() == 0) return 0;
  if (lastRead1 == lastRead2 && lastRead2 == lastRead3) return 3;
  if (lastRead1 == lastRead2) return 2;
  return 1;
}

// Update OLED while reading NFC to reassure the user
void updateReadingUI() {
  if (!gDisplayAvailable) return;
  if (!gNfcPresent) return;
  if (confirmedNFC.length()) return;

  // Use animated NFC reading screen
  static int nfcAnimFrame = 0;
  static unsigned long lastFrameUpdate = 0;

  if (millis() - lastFrameUpdate > 100) {
    lastFrameUpdate = millis();
    nfcAnimFrame++;
  }

  oledNfcReadingScreen(nfcAnimFrame);

  if (!gReadingShown) {
    Serial.println("[NFC] Tag detected, reading...");
    gReadingShown = true;
  }
}

// ====== EEPROM Tag Registry ======
uint32_t fnv1a(const String& s) {
  uint32_t h = 2166136261u;
  for (size_t i=0;i<s.length();++i) { h ^= (uint8_t)s[i]; h *= 16777619u; }
  return h;
}
void seenInit() { EEPROM.begin(EEPROM_TOTAL_SIZE); }

// ====== EEPROM Config Storage ======
void loadApiKeyFromEeprom() {
  char buf[EEPROM_API_KEY_LEN];
  for (int i = 0; i < EEPROM_API_KEY_LEN; i++) {
    buf[i] = EEPROM.read(EEPROM_API_KEY_ADDR + i);
  }
  buf[EEPROM_API_KEY_LEN - 1] = '\0';
  // Check if valid (non-empty and printable first char)
  if (buf[0] >= 32 && buf[0] <= 126) {
    strncpy(api_key, buf, EEPROM_API_KEY_LEN);
    Serial.print("[Config] API key loaded: ");
    // Show first 8 chars only for security
    for (int i = 0; i < 8 && api_key[i]; i++) Serial.print(api_key[i]);
    Serial.println("...");
  } else {
    Serial.println("[Config] No API key configured - use 'api_key <key>' command");
  }
}

void saveApiKeyToEeprom(const char* key) {
  for (int i = 0; i < EEPROM_API_KEY_LEN; i++) {
    EEPROM.write(EEPROM_API_KEY_ADDR + i, i < strlen(key) ? key[i] : 0);
  }
  EEPROM.commit();
  strncpy(api_key, key, EEPROM_API_KEY_LEN);
  Serial.println("[Config] API key saved to EEPROM");
}

void loadDeviceIdFromEeprom() {
  char buf[EEPROM_DEVICE_ID_LEN];
  for (int i = 0; i < EEPROM_DEVICE_ID_LEN; i++) {
    buf[i] = EEPROM.read(EEPROM_DEVICE_ID_ADDR + i);
  }
  buf[EEPROM_DEVICE_ID_LEN - 1] = '\0';
  // Check if valid (non-empty and printable first char)
  if (buf[0] >= 32 && buf[0] <= 126) {
    strncpy(device_id, buf, EEPROM_DEVICE_ID_LEN);
    Serial.print("[Config] Device ID loaded: "); Serial.println(device_id);
  } else {
    Serial.println("[Config] No device ID configured - use 'device_id <id>' command");
  }
}

void saveDeviceIdToEeprom(const char* id) {
  for (int i = 0; i < EEPROM_DEVICE_ID_LEN; i++) {
    EEPROM.write(EEPROM_DEVICE_ID_ADDR + i, i < strlen(id) ? id[i] : 0);
  }
  EEPROM.commit();
  strncpy(device_id, id, EEPROM_DEVICE_ID_LEN);
  Serial.println("[Config] Device ID saved to EEPROM");
}
bool seenHas(uint32_t h) {
  for (int i=0;i<SEEN_SLOTS;i++) {
    int base = i*SLOT_SIZE;
    uint32_t hv = 0;
    for (int b=0;b<4;b++) hv |= (EEPROM.read(base+b) << (8*b));
    uint8_t flag = EEPROM.read(base+4);
    if (flag==1 && hv==h) return true;
  }
    return false;
  }
void seenAdd(uint32_t h) {
  for (int i=0;i<SEEN_SLOTS;i++) {
    int base = i*SLOT_SIZE;
    uint8_t flag = EEPROM.read(base+4);
    if (flag!=1) {
      for (int b=0;b<4;b++) EEPROM.write(base+b, (h >> (8*b)) & 0xFF);
      EEPROM.write(base+4, 1);
      EEPROM.commit();
      return;
    }
  }
  // if full, overwrite slot 0
  for (int b=0;b<4;b++) EEPROM.write(b, (h >> (8*b)) & 0xFF);
  EEPROM.write(4, 1);
  EEPROM.commit();
}

// ====== WIFI (using WiFiManager) ======
void configModeCallback(WiFiManager *myWiFiManager) {
  Serial.println("[WiFi] Entered config portal mode");
  Serial.print("  Connect to WiFi network: "); Serial.println(myWiFiManager->getConfigPortalSSID());
  Serial.println("  Then open http://192.168.4.1 in your browser");
  oledMsg("WiFi Setup Mode", "Connect to:", myWiFiManager->getConfigPortalSSID());
  ledBeginMode(LED_ORPHAN);  // Magenta indicates config mode
}

void connectToWiFi() {
  oledMsg("WiFi: connecting...");

  // Configure WiFiManager callbacks and timeouts
  wifiManager.setAPCallback(configModeCallback);
  wifiManager.setConnectTimeout(15);        // 15 seconds to try saved credentials
  wifiManager.setConfigPortalTimeout(300);  // 5 minutes in AP mode before giving up

  Serial.println("[WiFi] Attempting connection...");

  // First try saved credentials quickly
  WiFi.mode(WIFI_STA);
  WiFi.begin();  // Uses credentials saved by WiFiManager

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    ledAnimate();
    handleSerialCommands();
    delay(100);
    if ((millis() - start) % 2000 < 100) {
      oledMsg("WiFi: connecting...", String((millis() - start) / 1000) + "s");
    }
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] Connected with saved credentials");
    oledMsg("WiFi: connected", WiFi.localIP().toString(), WiFi.SSID());
    Serial.print("  SSID: "); Serial.println(WiFi.SSID());
    Serial.print("  IP: "); Serial.println(WiFi.localIP());
    ledBeginMode(LED_SUCCESS);
    delay(1000);
    return;
  }

  // Saved credentials failed - start captive portal
  Serial.println("[WiFi] No saved credentials or connection failed");
  Serial.println("[WiFi] Starting captive portal: Spoolio-Setup");
  oledMsg("WiFi Setup", "Connect to:", "Spoolio-Setup");

  // This blocks until configured or timeout
  bool connected = wifiManager.autoConnect("Spoolio-Setup");

  if (connected) {
    oledMsg("WiFi: connected", WiFi.localIP().toString(), WiFi.SSID());
    Serial.print("[WiFi] Connected to: "); Serial.println(WiFi.SSID());
    Serial.print("[WiFi] IP: "); Serial.println(WiFi.localIP());
    ledBeginMode(LED_SUCCESS);
    delay(1000);
  } else {
    oledMsg("WiFi: FAILED", "Use 'wifi_ap' via", "USB serial to retry");
    Serial.println("[WiFi] Connection failed - use 'wifi_ap' serial command to reconfigure");
    ledBeginMode(LED_ERROR);
    delay(2000);
  }
}

bool ensureWiFiHealthy(unsigned long timeoutMs = 20000, unsigned long retryIntervalMs = 5000) {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  oledMsg("WiFi reconnect", "Reconnecting...");
  unsigned long start = millis();
  unsigned long lastRetry = 0;

  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    unsigned long now = millis();
    if (lastRetry == 0 || now - lastRetry >= retryIntervalMs) {
      WiFi.reconnect();  // Uses saved credentials from WiFiManager
      lastRetry = now;
    }
    ledAnimate();
    handleSerialCommands();
    delay(100);
  }

  if (WiFi.status() == WL_CONNECTED) {
    oledMsg("WiFi restored", WiFi.localIP().toString());
    return true;
  }

  oledMsg("WiFi error", "Reconnect failed", "Use 'wifi_ap' command");
  return false;
}

// ====== NFC ======
void readNFC();
void waitForValidNFC() {
  confirmedNFC = "";
  confirmedUidHex = "";
  confirmedAscii = "";
  gPendingAscii = "";
  lastRead1 = lastRead2 = lastRead3 = "";
  gFirstReadTime = 0;
  gMostSeenUid = "";
  gMostSeenCount = 0;
  gCurrentUid = "";
  gCurrentCount = 0;
  Serial.println("[NFC] Waiting for tag...");
  oledReadyScreen();  // Use animated ready screen
  ledBeginMode(LED_WAIT_NFC);
  gReadingShown = false;
#if DISABLE_NFC
  delay(500);
  confirmedNFC = "MANUAL"; // bypass for testing
  confirmedUidHex = confirmedNFC;
  return;
#endif
  unsigned long lastReadyUpdate = 0;
  while (confirmedNFC == "") {
    readNFC();

    // Update display - either reading screen or animated ready screen
    if (gNfcPresent) {
      updateReadingUI();
    } else if (millis() - lastReadyUpdate > 100) {
      // Refresh ready screen animation periodically when no tag present
      oledReadyScreen();
      lastReadyUpdate = millis();
    }

    ledAnimate();
    handleSerialCommands();
    yield();  // Feed watchdog
    delay(10);  // Faster polling for more read attempts
  }
  Serial.print("[NFC] Confirmed: "); Serial.println(confirmedNFC);

  // Small delay after NFC to let RF field settle before weighing
  delay(150);
}

String hexToAscii(uint8_t* hex) {
  String ascii = "";
  for (uint8_t i=0;i<4;i++) if (hex[i] >= 32 && hex[i] <= 126) ascii += (char)hex[i];
  return ascii;
}

String uidToHex(const uint8_t* uid, uint8_t uidLength) {
  static const char HEX_DIGITS[] = "0123456789ABCDEF";
  String uidHex; uidHex.reserve(uidLength*2);
  for (uint8_t i=0;i<uidLength;i++) {
    uidHex += HEX_DIGITS[uid[i] >> 4];
    uidHex += HEX_DIGITS[uid[i] & 0x0F];
  }
  return uidHex;
}

String extractRelevantText(String text) {
  int startPos = text.indexOf("ID");
  int endPos   = text.indexOf("203", startPos);
  if (startPos!=-1 && endPos!=-1) return text.substring(startPos, endPos+3);
  return text;
}

// Read NTAG user pages if present; always stabilize by UID hex
void readNtagOrUid(const uint8_t* uid, uint8_t uidLength) {
  String uidHex = uidToHex(uid, uidLength);

  // Try to read just a few key pages quickly (4, 5, 6, 7)
  uint8_t buf[4];
  String asciiText = "";
  bool anyPage = false;

  for (uint8_t page=4; page<=7; page++) {
    if (nfc.mifareultralight_ReadPage(page, buf)) {
      String pageText = hexToAscii(buf);
      if (pageText.length() > 0) {
        asciiText += pageText;
        anyPage = true;
      }
    }
    yield(); // Keep system responsive
  }

  // Record ASCII candidate (for display) but confirm using UID for stability
  if (anyPage) {
    String filtered = extractRelevantText(asciiText);
    if (filtered.length()) {
      gPendingAscii = filtered;
    }
  }

  // Start timeout clock on first read (any UID)
  if (gFirstReadTime == 0) {
    gFirstReadTime = millis();
    Serial.print("[NFC] First read: "); Serial.println(uidHex);
  }

  // Track which UID we've seen most often
  if (uidHex == gCurrentUid) {
    gCurrentCount++;
  } else {
    // New UID - if current was more popular, it becomes "most seen"
    if (gCurrentCount > gMostSeenCount) {
      gMostSeenUid = gCurrentUid;
      gMostSeenCount = gCurrentCount;
    }
    gCurrentUid = uidHex;
    gCurrentCount = 1;
  }

  // Update most seen if current is now winning
  if (gCurrentCount > gMostSeenCount) {
    gMostSeenUid = gCurrentUid;
    gMostSeenCount = gCurrentCount;
  }

  // Shift history for consecutive-match detection
  lastRead3 = lastRead2; lastRead2 = lastRead1; lastRead1 = uidHex;

  // Confirm after 2 identical consecutive reads
  if (lastRead1 == lastRead2 && lastRead1.length() > 0) {
    confirmedNFC = uidHex;
    confirmedUidHex = uidHex;
    if (gPendingAscii.length()) confirmedAscii = gPendingAscii;
    Serial.println("[NFC] Confirmed (2 matching reads)");
    return;
  }

  // Timeout fallback: after 2 seconds, accept whatever UID we have
  if ((millis() - gFirstReadTime) >= NFC_CONFIRM_TIMEOUT_MS) {
    // Prefer the most-seen UID, but fall back to current if we only got one read
    String acceptUid = gMostSeenUid.length() > 0 ? gMostSeenUid : gCurrentUid;
    if (acceptUid.length() > 0) {
      confirmedNFC = acceptUid;
      confirmedUidHex = acceptUid;
      if (gPendingAscii.length()) confirmedAscii = gPendingAscii;
      Serial.print("[NFC] Confirmed (timeout: ");
      Serial.print(acceptUid);
      Serial.print(" seen ");
      Serial.print(gMostSeenCount > 0 ? gMostSeenCount : gCurrentCount);
      Serial.println(" times)");
      return;
    }
  }
}

void readNFC() {
  uint8_t uid[7] = {0}; uint8_t uidLength = 0;

  // Give more time for tag detection - 500ms allows slower tags to respond
  bool ok = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 500);

  // Debug: show every read attempt result
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 1000) {
    lastDebug = millis();
    if (gFirstReadTime > 0) {
      Serial.printf("[NFC] Scan: %s, reads=%d, elapsed=%lums\n",
        ok ? "found" : "none",
        gMostSeenCount + gCurrentCount,
        millis() - gFirstReadTime);
    }
  }

  gNfcPresent = ok;
  if (ok) {
    if (ledMode != LED_READING) {
      ledBeginMode(LED_READING);
    }
    readNtagOrUid(uid, uidLength);
  } else {
    // Tag not detected this scan - but check if we should accept what we've seen
    // This handles the case where the tag was read but is now intermittent
    if (gFirstReadTime > 0 && (millis() - gFirstReadTime) >= NFC_CONFIRM_TIMEOUT_MS) {
      String acceptUid = gMostSeenUid.length() > 0 ? gMostSeenUid : gCurrentUid;
      if (acceptUid.length() > 0) {
        confirmedNFC = acceptUid;
        confirmedUidHex = acceptUid;
        if (gPendingAscii.length()) confirmedAscii = gPendingAscii;
        Serial.print("[NFC] Confirmed (timeout while not detecting - best: ");
        Serial.print(acceptUid);
        Serial.print(" seen ");
        Serial.print(gMostSeenCount > 0 ? gMostSeenCount : gCurrentCount);
        Serial.println(" times)");
        return;
      }
    }

    // Only check reader health if we've never seen a tag at all in 10+ seconds
    static unsigned long lastNfcCheck = 0;
    if (millis() - lastNfcCheck > 10000 && gFirstReadTime == 0) {
      lastNfcCheck = millis();
      uint32_t version = nfc.getFirmwareVersion();
      if (!version) {
        Serial.println("[NFC] Reader unresponsive, attempting reset...");
        nfc.begin();
        delay(100);
        version = nfc.getFirmwareVersion();
        if (version) {
          nfc.SAMConfig();
          nfc.setPassiveActivationRetries(0xFF);
          Serial.println("[NFC] Reader recovered");
        } else {
          Serial.println("[NFC] Reader still unresponsive");
        }
      }
    }
  }
}

// naive field parser trying to find key/value hints in the ascii payload
TagInfo parseTagInfo(const String& txt) {
  TagInfo ti;
  // very basic patterns; adjust to your payload
  // ID
  int i = txt.indexOf("ID");
  if (i!=-1) { int j = txt.indexOf("&", i+2); if (j==-1) j = min(i+20, (int)txt.length()); ti.id = txt.substring(i, j); }
  // material
  int m = txt.indexOf("material=");
  if (m!=-1) { int j = txt.indexOf("&", m+9); if (j==-1) j = m+30; ti.material = txt.substring(m+9, j); }
  // color
  int c = txt.indexOf("color=");
  if (c!=-1) { int j = txt.indexOf("&", c+6); if (j==-1) j = c+30; ti.color = txt.substring(c+6, j); }
  // tare
  int t = txt.indexOf("tare=");
  if (t!=-1) { int j = txt.indexOf("&", t+5); if (j==-1) j = t+10; ti.tare = txt.substring(t+5, j); }
  return ti;
}

// ====== WEIGHT ======
float measureStableWeight(const TagInfo& ti) {
  ledBeginMode(LED_MEASURING);
  oledWeighScreen(ti, 0.0, "Measuring...");

  const unsigned long duration = 2000;
  const float threshold = MIN_WEIGHT_GRAMS;  // Simple minimum to detect spool presence
  const float maxFluctuation = 5.0;

  // Reinitialize scale if needed (after NFC interference)
  if (scaleNeedsReinit) {
    Serial.println("[SCALE] Reinitializing after interference...");
    scale.power_down();
    delay(100);
    scale.power_up();
    scale.set_scale(calibration_factor);
    scaleNeedsReinit = false;
  }

  // Ensure the ADC is responsive before attempting a read
  if (!scale.wait_ready_timeout(1500)) {
    Serial.println("HX711 not ready (start)");
    oledMsg("Scale not ready", "Check wiring");
    ledBeginMode(LED_ERROR);
    scaleNeedsReinit = true;
    return -1;
  }

  unsigned long start = millis();
  float initialWeight = scale.get_units(5);

  // Check for invalid readings (interference)
  if (initialWeight < -1000.0 || initialWeight > 10000.0) {
    Serial.printf("Invalid weight reading: %.1f g (interference?)\n", initialWeight);
    oledMsg("Scale interference", "Remove NFC tag", "Retry");
    ledBeginMode(LED_ERROR);
    scaleNeedsReinit = true;
    return -1;
  }

  if (initialWeight < threshold) {
    Serial.printf("Weight %.1f g below minimum %.1f g.\n", initialWeight, threshold);
    oledMsg("Too light", String("Need >= ") + String(threshold, 1) + " g", "Add spool or retry");
    ledBeginMode(LED_ERROR);
    return -1;
  }

  float lastWeight = initialWeight;
  while (millis() - start < duration) {
    // Do not block if ADC isn't ready; keep UI alive
    if (!scale.wait_ready_timeout(300)) {
      handleSerialCommands();
      ledAnimate();
      delay(40);
      continue;
    }
    float current = scale.get_units(5);
    if (abs(current - initialWeight) > maxFluctuation) {
      Serial.println("Weight fluctuating too much.");
      oledMsg("Weight unstable", "Hold steady or retry");
      ledBeginMode(LED_ERROR);
      return -1;
    }
    lastWeight = current;

    // Use the new progress bar screen
    unsigned long elapsed = millis() - start;
    float progress = (float)elapsed / (float)duration;
    if (progress > 1.0) progress = 1.0;
    oledWeighScreenWithProgress(ti, current, progress, elapsed, duration);

    handleSerialCommands();
    ledAnimate();
    delay(60);
  }

  Serial.printf("Stable weight: %.1f g\n", lastWeight);
  oledWeighScreenWithProgress(ti, lastWeight, 1.0, duration, duration);
  return lastWeight;
}

// ====== BOOT ======
void bootSplash() {
  // logo + short LED animation, then startup text
#if MIRROR_DISPLAY_TO_SERIAL
  Serial.println("Spoolio");
  Serial.println("Starting up...");
#endif
  ledBeginMode(LED_BOOTSWIRL);
  unsigned long t0 = millis();
  // Show logo first (~600 ms)
  if (gDisplayAvailable) {
    display.clearDisplay();
    display.drawBitmap((SCREEN_WIDTH - LOGO_WIDTH) / 2, (SCREEN_HEIGHT - LOGO_HEIGHT) / 2, splash_logo, LOGO_WIDTH, LOGO_HEIGHT, WHITE);
    display.display();
  }
  while (millis() - t0 < 600) { ledAnimate(); delay(10); }
  // Then show text for the remainder (~600 ms)
  if (gDisplayAvailable) {
    display.clearDisplay();
    display.setTextColor(WHITE);
    display.setTextSize(2);
    display.setCursor(6, 8);
    display.println("Spoolio");
    display.setTextSize(1);
    display.setCursor(8, 32);
    display.println("Starting up...");
    display.display();
  }
  while (millis() - t0 < 1200) { ledAnimate(); delay(10); }
}

// ====== SETUP / LOOP ======
void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("\n\n=== Spoolio Hardware Starting ===");
  Serial.println("Type 'help' for serial commands\n");

  // LEDs
  strip.begin(); strip.setBrightness(BRIGHTNESS);
  // quick power-on proof that LEDs are wired
  setLEDColor(strip.Color(20, 20, 20));
  delay(120);
  setLEDColor(strip.Color(0,0,0));

  // I2C OLED
#if HEADLESS_DISPLAY
  gDisplayAvailable = false;
  Serial.println("HEADLESS: OLED disabled; mirroring UI to Serial.");
#else
  Wire.begin(D2 /*SDA*/, D1 /*SCL*/);
  // Keep I2C at a conservative clock to play well with multiple devices
  Wire.setClock(100000);
#ifdef ESP8266
  Wire.setClockStretchLimit(150000); // ~150ms
#endif
#if USE_SH1106
  bool ok = display.begin(0x3C, true);
  if (!ok) { ok = display.begin(0x3D, true); }
#else
  bool ok = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (!ok) { ok = display.begin(SSD1306_SWITCHCAPVCC, 0x3D); }
#endif
  gDisplayAvailable = ok;
  if (!gDisplayAvailable) {
    Serial.println("OLED init failed; continuing headless.");
  }
#endif

  bootSplash();

  // Initialize EEPROM and load saved configuration
  seenInit();
  loadApiKeyFromEeprom();
  loadDeviceIdFromEeprom();

  // Check if device is configured
  if (strlen(api_key) == 0) {
    Serial.println("");
    Serial.println("*** DEVICE NOT CONFIGURED ***");
    Serial.println("Use these serial commands to set up:");
    Serial.println("  api_key <your-key>    - Set API key from spoolio.co.uk");
    Serial.println("  device_id <name>      - Set device identifier");
    Serial.println("");
    oledMsg("Setup Required", "Use USB serial", "Type 'help'");
    delay(2000);
  }

  // WiFi (uses WiFiManager - will start captive portal if not configured)
  connectToWiFi();

  // NFC
#if DISABLE_NFC
  oledMsg("NFC", "Disabled for test");
#else
  oledMsg("NFC", "Initialising reader...");
  nfc.begin();
  uint32_t versiondata = 0;
  for (uint8_t attempt = 0; attempt < 3 && !versiondata; ++attempt) {
    versiondata = nfc.getFirmwareVersion();
    delay(60);
  }
  if (!versiondata) {
    Serial.println("PN53x not found.");
    oledMsg("PN532 not found");
  } else {
    nfc.SAMConfig();
    // Maximize RF field power and detection sensitivity
    nfc.setPassiveActivationRetries(0xFF);  // Keep trying indefinitely
    nfc.setRFField(0x02, 1);  // Enable RF field with auto-on
    Serial.print("PN532 firmware 0x"); Serial.println(versiondata, HEX);
    Serial.println("[NFC] RF field active, max retries enabled");
  }
#endif

  // Scale
  scale.begin(DT_PIN, SCK_PIN);
  scale.set_gain(128);
  scale.power_up();
  scale.set_scale(calibration_factor);
  // Avoid blocking forever if HX711 isn't wired/ready
  if (!scale.wait_ready_timeout(2000)) {
    Serial.println("HX711 not ready at boot; skipping tare");
    oledMsg("Scale init", "HX711 not ready");
  } else {
  scale.tare();
  }
  delay(300);

  oledReadyScreen();
  ledBeginMode(LED_WAIT_NFC);
}

void loop() {
  ledAnimate();
  Serial.println("\n===== Ready for scan =====");

  // Wait NFC
  waitForValidNFC();

  // Try to fetch spool info from API first, fall back to parsing tag ASCII
  TagInfo ti;
  String tagId = confirmedUidHex.length() ? confirmedUidHex : confirmedNFC;
  Serial.print("[NFC] Tag: "); Serial.println(tagId);
  bool fetchedFromApi = false;

  if (WiFi.status() == WL_CONNECTED) {
    oledMsg("Looking up...", tagId);
    fetchedFromApi = fetchSpoolInfo(tagId, ti);
  } else {
    Serial.println("[WARN] WiFi offline - using local data");
  }

  // If API fetch failed, try parsing from tag ASCII data
  if (!fetchedFromApi && confirmedAscii.length()) {
    ti = parseTagInfo(confirmedAscii);
    Serial.println("[NFC] Using tag ASCII data");
  }

  // If we still don't have a display name, create one from what we have
  if (ti.displayName.length() == 0) {
    if (ti.material.length() || ti.color.length()) {
      ti.displayName = ti.material + " " + ti.color;
      ti.displayName.trim();
    }
  }

  postEvent("scan_start", tagId);

  // Track if we've seen this tag before (local device memory)
  uint32_t h = fnv1a(tagId);
  if (!seenHas(h)) {
    seenAdd(h);
    postEvent("first_scan", tagId, "First time on this device");
  }

  // Measure
  float weight = measureStableWeight(ti);
  if (weight <= 0) {
    delay(1200);
    postEvent("error", tagId, "unstable_or_too_light");
    oledReadyScreen();
    ledBeginMode(LED_WAIT_NFC);
    return;
  }

  // Send
  ledBeginMode(LED_UPLOAD);
  if (!ensureWiFiHealthy()) {
    postEvent("error", tagId, "wifi_reconnect_failed");
    ledBeginMode(LED_ERROR);
    delay(2000);
    oledReadyScreen();
    ledBeginMode(LED_WAIT_NFC);
    return;
  }
  uint8_t up = uploadWeightApi(tagId, weight);
  if (up == 0) {
    // Success - show animated success screen
    ledBeginMode(LED_SUCCESS);
    Serial.println("[OK] Weight uploaded successfully");

    // Animate the success screen
    unsigned long animStart = millis();
    while (millis() - animStart < 2500) {
      int frame = (millis() - animStart) / 100;
      oledSuccessScreen(ti, weight, frame);
      ledAnimate();
      delay(50);
    }
  } else if (up == 1) {
    // 404 - tag not registered on server
    oledMsg("New spool", "Weight saved", "Register at spoolio.co.uk");
    ledBeginMode(LED_ORPHAN);
    Serial.println("[WARN] Tag not registered - recorded as orphan");
    delay(2000);
  } else {
    // Network/server error
    oledMsg("Upload failed", "Check WiFi", "Will retry next time");
    ledBeginMode(LED_ERROR);
    Serial.println("[ERROR] Upload failed - network issue");
    delay(2000);
  }

  // Wait removal
  const float removalThreshold = 10.0;
  unsigned long t0 = millis();
  while (true) {
    float w = scale.get_units(3);
    if (abs(w) < removalThreshold) break;
    if (millis() - t0 > 10000) break;
    oledReadyScreen();  // Show ready screen while waiting for removal
    ledAnimate();
    delay(80);
  }

  oledReadyScreen();
  ledBeginMode(LED_WAIT_NFC);
}
