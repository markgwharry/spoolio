#include <WiFi.h>
#include <esp_wifi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "SpoolioTlsTrust.h"
#include <ArduinoJson.h>
#include <LovyanGFX.hpp>
#include <XPT2046_Touchscreen.h>

void configureSpoolioTls(WiFiClientSecure& client) {
#if ALLOW_INSECURE_TLS
  client.setInsecure();
#else
  client.setCACert(SPOOLIO_ROOT_CA);
#endif
}

// ---------- Display (HSPI) ----------
#define TFT_CS     15
#define TFT_DC      2
#define TFT_RST    -1
#define TFT_BL     21
#define HSPI_SCLK  14
#define HSPI_MISO  12
#define HSPI_MOSI  13

// ---------- Touch (VSPI) -----------
#define T_CS       27
#define T_IRQ     -1
#define T_SCLK     25
#define T_MISO     39
#define T_MOSI     32

// If your board variant wires touch CS to GPIO33 instead of 27, set this to 1
#ifndef TOUCH_ALT_PINMAP
#define TOUCH_ALT_PINMAP 0
#endif
#if TOUCH_ALT_PINMAP
#undef T_CS
#define T_CS       33
#endif

// LovyanGFX panel setup (ILI9341)
class LGFX : public lgfx::LGFX_Device {
  lgfx::Bus_SPI _bus;
  lgfx::Panel_ILI9341 _panel;
public:
  LGFX() {
    auto b = _bus.config();
    b.spi_host   = HSPI_HOST;
    b.spi_mode   = 0;
    b.freq_write = 40000000;
    b.freq_read  = 16000000;
    b.spi_3wire  = false;
    b.use_lock   = true;
    b.dma_channel= 1;
    b.pin_sclk   = HSPI_SCLK;
    b.pin_mosi   = HSPI_MOSI;
    b.pin_miso   = HSPI_MISO;
    b.pin_dc     = TFT_DC;
    _bus.config(b);

    auto p = _panel.config();
    p.pin_cs   = TFT_CS;
    p.pin_rst  = TFT_RST;
    p.pin_busy = -1;
    p.memory_width  = 240; p.memory_height = 320;
    p.panel_width   = 240; p.panel_height  = 320;
    p.offset_x = 0; p.offset_y = 0;
    p.readable = true; p.invert = false; p.rgb_order = false;
    _panel.config(p); _panel.setBus(&_bus);
    setPanel(&_panel);
  }
};

LGFX tft;
SPIClass vspi(VSPI);
XPT2046_Touchscreen ts(T_CS);

// ---- Touch calibration (ported from working starter) ----
static const bool TOUCH_SWAP_XY = false;
static       bool TOUCH_INVERT_X = true;
static       bool TOUCH_INVERT_Y = true;
static const int RAW_X_MIN = 309,  RAW_X_MAX = 3585;
static const int RAW_Y_MIN = 460,  RAW_Y_MAX = 3367;

// Runtime calibration overrides (set after wizard)
static bool CAL_IN_USE = false;
static bool CAL_SWAP_XY = false;
static bool CAL_INVERT_X = false;
static bool CAL_INVERT_Y = false;
static int  CAL_X_MIN = RAW_X_MIN, CAL_X_MAX = RAW_X_MAX;
static int  CAL_Y_MIN = RAW_Y_MIN, CAL_Y_MAX = RAW_Y_MAX;

static bool readTouchXY(int16_t &sx, int16_t &sy) {
  if (!ts.touched()) return false;
  TS_Point p = ts.getPoint();
  uint16_t rx = p.x, ry = p.y;
  bool sw = CAL_IN_USE ? CAL_SWAP_XY : TOUCH_SWAP_XY;
  bool ix = CAL_IN_USE ? CAL_INVERT_X : TOUCH_INVERT_X;
  bool iy = CAL_IN_USE ? CAL_INVERT_Y : TOUCH_INVERT_Y;
  int xmin = CAL_IN_USE ? CAL_X_MIN : RAW_X_MIN;
  int xmax = CAL_IN_USE ? CAL_X_MAX : RAW_X_MAX;
  int ymin = CAL_IN_USE ? CAL_Y_MIN : RAW_Y_MIN;
  int ymax = CAL_IN_USE ? CAL_Y_MAX : RAW_Y_MAX;
  if (sw) { uint16_t t=rx; rx=ry; ry=t; }
  if (ix) rx = xmin + xmax - rx;
  if (iy) ry = ymin + ymax - ry;
  sx = map((int)rx, xmin, xmax, 0, tft.width());
  sy = map((int)ry, ymin, ymax, 0, tft.height());
  if (sx < 0) sx = 0; else if (sx >= tft.width())  sx = tft.width()-1;
  if (sy < 0) sy = 0; else if (sy >= tft.height()) sy = tft.height()-1;
  return true;
}

// Raw touch read helper for diagnostics (bypasses ts.touched())
static bool readTouchRaw(uint16_t &rx, uint16_t &ry, uint16_t &rz) {
  TS_Point p = ts.getPoint();
  if (p.z < 50) return false; // ignore very light/no touch
  rx = p.x;
  ry = p.y;
  rz = p.z;
  return true;
}

static bool readTouchRawMapped(int16_t &sx, int16_t &sy) {
  uint16_t rx, ry, rz;
  if (!readTouchRaw(rx, ry, rz)) return false;
  (void)rz;
  if (TOUCH_SWAP_XY) { uint16_t t=rx; rx=ry; ry=t; }
  if (TOUCH_INVERT_X) rx = RAW_X_MIN + RAW_X_MAX - rx;
  if (TOUCH_INVERT_Y) ry = RAW_Y_MIN + RAW_Y_MAX - ry;
  sx = map((int)rx, RAW_X_MIN, RAW_X_MAX, 0, tft.width());
  sy = map((int)ry, RAW_Y_MIN, RAW_Y_MAX, 0, tft.height());
  if (sx < 0) sx = 0; else if (sx >= tft.width())  sx = tft.width()-1;
  if (sy < 0) sy = 0; else if (sy >= tft.height()) sy = tft.height()-1;
  return true;
}

// ---- UI colors/helpers ----
static uint16_t COL_BG   = 0x0000;   // black
static uint16_t COL_FG   = 0xFFFF;   // white
static uint16_t COL_ACC  = 0x07E0;   // green
static uint16_t COL_WARN = 0xFBE0;   // yellow
static uint16_t COL_ERR  = 0xF800;   // red
static uint16_t COL_DIM  = 0x8410;   // grey

static void drawHeader(const char* title, uint16_t band=0x39E7) {
  tft.fillRect(0,0,tft.width(),24, band);
  tft.setTextColor(COL_FG, band);
  tft.setFont(&fonts::Font2);
  tft.setTextDatum(textdatum_t::middle_left);
  tft.drawString(title, 8, 12);
}

static void drawWifiBadge() {
  String s = (WiFi.status()==WL_CONNECTED)
    ? ("Wi‑Fi " + WiFi.localIP().toString() + "  ch " + String(WiFi.channel()) + "  RSSI " + String(WiFi.RSSI()))
    : "Wi‑Fi not connected";
  tft.setTextDatum(textdatum_t::top_left);
  tft.setTextColor(COL_DIM, COL_BG);
  tft.setFont(&fonts::Font2);
  tft.drawString(s, 8, 28);
}

static uint16_t colorForState(const char* state) {
  if (!state) return COL_DIM;
  if (!strcmp(state, "uploaded")) return COL_ACC;
  if (!strcmp(state, "stable")) return 0x06D6; // cyan-ish
  if (!strcmp(state, "weighing")) return COL_WARN;
  if (!strcmp(state, "scan_started")) return 0x5ACB; // teal
  if (!strcmp(state, "error")) return COL_ERR;
  if (!strcmp(state, "waiting_removal")) return COL_WARN;
  if (!strcmp(state, "ready")) return 0x2227; // blue-ish
  return COL_DIM;
}

// Draw wrapped text within a max width. Returns next y coordinate.
static int drawWrapped(const String& text, int x, int y, int maxWidth, int lineGap) {
  if (text.length() == 0) return y;
  tft.setTextDatum(textdatum_t::top_left);
  tft.setFont(&fonts::Font2);

  const int lineHeight = tft.fontHeight();
  String line = "";
  int start = 0;
  while (start < (int)text.length()) {
    int space = text.indexOf(' ', start);
    if (space < 0) space = text.length();
    String word = text.substring(start, space);
    String trial = (line.length() == 0) ? word : (line + " " + word);
    if (tft.textWidth(trial) <= maxWidth) {
      line = trial;
      start = space + 1;
    } else {
      if (line.length() == 0) {
        // Very long word – hard wrap with hyphen
        String chunk = "";
        for (int i = 0; i < (int)word.length(); ++i) {
          String next = chunk + word[i];
          if (tft.textWidth(next + "-") > maxWidth && chunk.length() > 0) {
            tft.drawString(chunk + "-", x, y);
            y += lineHeight + lineGap;
            chunk = "";
          }
          chunk += word[i];
        }
        if (chunk.length() > 0) {
          line = chunk;
          start = space + 1;
        }
      } else {
        // Flush current line, retry word on new line
        tft.drawString(line, x, y);
        y += lineHeight + lineGap;
        line = "";
      }
    }
  }
  if (line.length() > 0) {
    tft.drawString(line, x, y);
    y += tft.fontHeight() + lineGap;
  }
  return y;
}

// WiFi Configuration (replicated from CYD Spoolio Start)
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
// Network addressing uses DHCP by default.
// Optional: lock to an AP BSSID/channel for multi-AP SSIDs.
// Fill in your AP's BSSID and channel before enabling this setting.
uint8_t WIFI_BSSID[6] = {0x00,0x00,0x00,0x00,0x00,0x00};
const int WIFI_CH = 0;
const bool USE_BSSID_LOCK = false;

// API Configuration
const char* API_HOST = "https://www.spoolio.co.uk";   // include scheme for secure client
const char* API_KEY  = "YOUR_DEVICE_API_KEY"; // obtain from device registration

// Endpoints
const char* ENDPOINT_HEARTBEAT    = "/api/hardware/heartbeat";
const char* ENDPOINT_CARDS        = "/api/hardware/display/cards";
const char* ENDPOINT_LIVE_STATUS  = "/api/hardware/live/status";

// Carousel settings
unsigned long lastRotate = 0;
const unsigned long rotateIntervalMs = 12000; // 12s
int currentCardIndex = 0;

// Backlight pin defined above

// Live view control
bool liveViewEnabled = true;
unsigned long lastLivePoll = 0;
const unsigned long livePollIntervalMs = 1000;

// Touch / swipe tracking
bool isTouchActive = false;
int16_t touchStartX = 0, touchStartY = 0;
int16_t touchLastX = 0, touchLastY = 0;
unsigned long touchStartMs = 0;

// Target AP details (filled by scan)
uint8_t targetBSSID[6] = {0};
int targetChannel = 0;
bool targetFound = false;

// Wi‑Fi event logging
void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
      Serial.printf("[WiFi] Disconnected. Reason: %d\n", (int)info.wifi_sta_disconnected.reason);
      break;
    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      Serial.println("[WiFi] Connected to AP");
      break;
    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      Serial.printf("[WiFi] Got IP: %s\n", WiFi.localIP().toString().c_str());
      break;
    default:
      break;
  }
}

// Simple helper to do GET with Bearer auth
bool httpGetJson(const String& url, DynamicJsonDocument& outDoc) {
  WiFiClientSecure client;
  configureSpoolioTls(client);
  HTTPClient http;
  http.begin(client, url);
  http.addHeader("Authorization", String("Bearer ") + API_KEY);
  http.setTimeout(8000);
  int code = http.GET();
  if (code > 0 && code < 400) {
    String payload = http.getString();
    DeserializationError err = deserializeJson(outDoc, payload);
    http.end();
    return !err;
  }
  http.end();
  return false;
}

// Minimal card rendering via Serial; replace with TFT drawing for CYD
void renderDashboard(const JsonObject& data) {
  Serial.println("[Card] Dashboard");
  Serial.printf("Total: %d, In-use: %d, Empty: %d, Low: %d, Today: %d\n",
    (int)data["total_spools"], (int)data["in_use"], (int)data["empty"],
    (int)data["low_stock"], (int)data["today_scans"]);
}

void renderRecentActivity(const JsonArray& arr) {
  Serial.println("[Card] Recent Activity");
  for (JsonObject evt : arr) {
    const char* type = evt["event_type"] | "";
    const char* tag  = evt["nfc_tag_id"] | "";
    double weight = evt["weight"] | 0.0;
    const char* time = evt["created_at"] | "";
    Serial.printf("%-12s %8s  %5.1fg  %s\n", type, tag, weight, time);
  }
}

void renderBuySoon(const JsonArray& arr) {
  Serial.println("[Card] Buy Soon");
  for (JsonObject s : arr) {
    const char* mat = s["material"] | "";
    const char* col = s["color"] | "";
    double remain = s["weight_remaining"] | 0.0;
    Serial.printf("%-8s %-10s  %5.1fg left\n", mat, col, remain);
  }
}

void renderInventory(const JsonArray& arr) {
  Serial.println("[Card] Inventory");
  int i = 0;
  for (JsonObject s : arr) {
    if (i++ >= 8) break; // show top 8 rows
    const char* mat = s["material"] | "";
    const char* col = s["color"] | "";
    double remain = s["weight_remaining"] | 0.0;
    Serial.printf("%-8s %-10s  %5.1fg\n", mat, col, remain);
  }
}

void renderStatus(const JsonObject& data) {
  Serial.println("[Card] Status");
  const char* server = data["server"] | "";
  const char* time   = data["server_time"] | "";
  Serial.printf("Server: %s  Time: %s\n", server, time);
}

void renderCards() {
  DynamicJsonDocument doc(8192);
  String url = String(API_HOST) + ENDPOINT_CARDS;
  if (!httpGetJson(url, doc)) {
    Serial.println("Failed to load cards");
    return;
  }
  JsonArray cards = doc["cards"].as<JsonArray>();
  if (cards.isNull() || cards.size() == 0) {
    Serial.println("No cards available");
    return;
  }

  currentCardIndex = currentCardIndex % cards.size();
  JsonObject card = cards[currentCardIndex].as<JsonObject>();
  const char* type = card["type"] | "";
  // Draw to TFT instead of Serial for browsing
  tft.fillScreen(COL_BG);
  tft.setTextColor(COL_FG, COL_BG);
  tft.setTextDatum(textdatum_t::top_left);
  tft.setFont(&fonts::Font2);
  tft.setTextSize(1);
  int y = 0;
  const int lh = tft.fontHeight();
  if (strcmp(type, "dashboard") == 0) {
    drawHeader("Dashboard", 0x2227);
    y = 28;
    JsonObject d = card["data"].as<JsonObject>();
    tft.setCursor(8, y); tft.printf("Total spools: %d", (int)d["total_spools"]); y += lh + 4;
    tft.setCursor(8, y); tft.printf("In use: %d", (int)d["in_use"]); y += lh + 4;
    tft.setCursor(8, y); tft.printf("Empty: %d", (int)d["empty"]); y += lh + 4;
    tft.setCursor(8, y); tft.printf("Low stock: %d", (int)d["low_stock"]); y += lh + 4;
    tft.setCursor(8, y); tft.printf("Today scans: %d", (int)d["today_scans"]); y += lh + 4;
  } else if (strcmp(type, "recent_activity") == 0) {
    drawHeader("Recent Activity", 0x5ACB);
    y = 28;
    int shown = 0;
    for (JsonObject evt : card["data"].as<JsonArray>()) {
      if (shown++ >= 8) break;
      const char* et = evt["event_type"] | "";
      const char* tg = evt["nfc_tag_id"] | "";
      double w = evt["weight"] | 0.0;
      const char* tm = evt["created_at"] | "";
      y = drawWrapped(String(et) + "  " + String(tg) + "  " + String(w, 1) + "g", 8, y, tft.width()-16, 2);
      y = drawWrapped(String(tm), 8, y, tft.width()-16, 2);
      y += 4;
    }
  } else if (strcmp(type, "buy_soon") == 0) {
    drawHeader("Buy Soon", 0xFBE0);
    y = 28;
    int shown = 0;
    for (JsonObject s : card["data"].as<JsonArray>()) {
      if (shown++ >= 8) break;
      const char* mat = s["material"] | "";
      const char* col = s["color"] | "";
      double rem = s["weight_remaining"] | 0.0;
      tft.setCursor(8, y); tft.printf("%s %s  %.0fg", mat, col, rem); y += lh + 2;
    }
  } else if (strcmp(type, "inventory") == 0) {
    drawHeader("Inventory", 0x39E7);
    y = 28;
    int shown = 0;
    for (JsonObject s : card["data"].as<JsonArray>()) {
      if (shown++ >= 10) break;
      const char* mat = s["material"] | "";
      const char* col = s["color"] | "";
      double rem = s["weight_remaining"] | 0.0;
      tft.setCursor(8, y); tft.printf("%s %s  %.0fg", mat, col, rem); y += lh + 2;
    }
  } else if (strcmp(type, "status") == 0) {
    drawHeader("Status", 0x2227);
    y = 28;
    JsonObject d = card["data"].as<JsonObject>();
    const char* server = d["server"] | "";
    const char* time   = d["server_time"] | "";
    tft.setCursor(8, y); tft.printf("Server: %s", server); y += lh + 4;
    y = drawWrapped(String("Time: ") + String(time), 8, y, tft.width()-16, 2);
  } else {
    drawHeader("Unknown", COL_WARN); y = 28;
    y = drawWrapped(String("Unknown card type"), 8, y, tft.width()-16, 2);
  }
}

void renderLive() {
  DynamicJsonDocument doc(4096);
  String url = String(API_HOST) + ENDPOINT_LIVE_STATUS;
  if (!httpGetJson(url, doc)) {
    Serial.println("Live status unavailable");
    // Screen message
    tft.fillScreen(COL_BG);
    tft.setTextColor(COL_FG, COL_BG);
    tft.setFont(&fonts::Font2);
    tft.setTextDatum(textdatum_t::top_left);
    tft.drawString("Live status unavailable", 8, 8);
    return;
  }
  const char* state = doc["state"] | "waiting";
  const char* msg   = doc["message"] | "";
  Serial.printf("[Live] %-14s  %s\n", state, msg);
  // Draw header + state pill (remove Wi‑Fi details)
  tft.fillScreen(COL_BG);
  drawHeader("Live", colorForState(state));
  tft.setTextColor(COL_FG, COL_BG);
  tft.setTextDatum(textdatum_t::top_left);
  // Compute a safe starting Y below the Wi‑Fi badge
  tft.setFont(&fonts::Font2);
  tft.setTextSize(1);
  int y = 28 + 6; // header band + padding
  const int lh = tft.fontHeight();
  tft.setFont(&fonts::Font2);
  // State tag
  String stateLine = String("[") + state + "]";
  tft.drawString(stateLine, 8, y);
  // Place status message below the state tag with full width, small font
  y += lh + 6;
  y = drawWrapped(String(msg), 8, y, tft.width() - 16, 2);
  // Enrich text output with weights and match/orphan details if present
  if (doc.containsKey("gross_weight")) {
    Serial.printf("  Gross: %.1f g\n", (double)doc["gross_weight"].as<double>());
    tft.setCursor(8, y+8); tft.printf("Gross: %.1f g", (double)doc["gross_weight"].as<double>());
    y += lh + 8;
  }
  if (doc.containsKey("net_weight")) {
    Serial.printf("  Net:   %.1f g\n", (double)doc["net_weight"].as<double>());
    tft.setCursor(8, y); tft.printf("Net:   %.1f g", (double)doc["net_weight"].as<double>());
    y += lh + 8;
  }
  if (doc.containsKey("tare_applied")) {
    Serial.printf("  Tare:  %.1f g\n", (double)doc["tare_applied"].as<double>());
    tft.setCursor(8, y); tft.printf("Tare:  %.1f g", (double)doc["tare_applied"].as<double>());
    y += lh + 8;
  }
  JsonObject last = doc["last_event"].as<JsonObject>();
  if (!last.isNull()) {
    const char* et = last["event_type"] | "";
    const char* tag = last["nfc_tag_id"] | "";
    Serial.printf("  Event: %s  Tag: %s\n", et, tag);
    JsonObject spool = last["spool"].as<JsonObject>();
    if (!spool.isNull()) {
      const char* mat = spool["material"] | "";
      const char* col = spool["color"] | "";
      const char* mfg = spool["manufacturer"] | "";
      double remain = spool["weight_remaining"] | 0.0;
      Serial.printf("  Spool: %s %s | %s | %.1fg left\n", mat, col, mfg, remain);
      tft.setCursor(8, y); tft.printf("Event: %s", et); y += lh + 6;
      tft.setCursor(8, y); tft.printf("Tag:   %s", tag); y += lh + 6;
      tft.setCursor(8, y); tft.printf("Spool: %s %s", mat, col); y += lh + 6;
      tft.setCursor(8, y); tft.printf("Mfg:   %s", mfg); y += lh + 6;
      tft.setCursor(8, y); tft.printf("Left:  %.1f g", remain); y += lh + 6;
    } else if (strcmp(et, "orphan") == 0) {
      Serial.println("  Spool: (orphan tag)\n");
      tft.setCursor(8, y); tft.printf("Event: %s", et); y += lh + 6;
      tft.setCursor(8, y); tft.printf("Tag:   %s", tag); y += lh + 6;
      y = drawWrapped(String("Spool: (orphan tag)"), 8, y, tft.width()-16, 2);
    }
  }

  // Auto-dismiss after a successful upload within ~12s
  static unsigned long liveShownSince = 0;
  if (strcmp(state, "uploaded") == 0) {
    if (liveShownSince == 0) liveShownSince = millis();
    if (millis() - liveShownSince > 12000) {
      liveViewEnabled = false;
      liveShownSince = 0;
      Serial.println("[Live] Auto-dismiss");
      // Immediately switch to background cards
      renderCards();
      lastRotate = millis();
    }
  } else {
    liveShownSince = 0;
  }
}

void scanNearbyNetworks() {
  Serial.println("\nScanning WiFi networks...");
  int n = WiFi.scanNetworks();
  if (n <= 0) {
    Serial.println("No networks found");
    return;
  }
  for (int i = 0; i < n; i++) {
    Serial.printf("%2d) %-32s  ch:%2d  RSSI:%4d  %s\n",
      i + 1,
      WiFi.SSID(i).c_str(),
      WiFi.channel(i),
      WiFi.RSSI(i),
      WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "open" : "secured");
  }
  Serial.println();
}

bool findTargetAP(const char* ssid) {
  targetFound = false;
  memset(targetBSSID, 0, sizeof(targetBSSID));
  targetChannel = 0;
  int n = WiFi.scanNetworks();
  if (n <= 0) return false;
  int bestRSSI = -999;
  for (int i = 0; i < n; i++) {
    String s = WiFi.SSID(i);
    if (s == String(ssid)) {
      int rssi = WiFi.RSSI(i);
      if (rssi > bestRSSI) {
        bestRSSI = rssi;
        targetChannel = WiFi.channel(i);
        const uint8_t* b = WiFi.BSSID(i);
        if (b) memcpy(targetBSSID, b, 6);
        targetFound = true;
      }
    }
  }
  if (targetFound) {
    Serial.printf("Best AP ch:%d  BSSID:%02X:%02X:%02X:%02X:%02X:%02X  RSSI:%d\n",
      targetChannel, targetBSSID[0], targetBSSID[1], targetBSSID[2], targetBSSID[3], targetBSSID[4], targetBSSID[5], bestRSSI);
  }
  WiFi.scanDelete();
  return targetFound;
}

void connectWiFi() {
  WiFi.onEvent(onWiFiEvent);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_ps(WIFI_PS_NONE);
  WiFi.disconnect(true, true);
  delay(100);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setHostname("Spoolio-CYD");
  WiFi.setTxPower(WIFI_POWER_19_5dBm);
  // Configure the regulatory domain; network addressing is provided by DHCP.
  wifi_country_t gb = {"GB", 1, 13, WIFI_COUNTRY_POLICY_AUTO};
  esp_wifi_set_country(&gb);

  Serial.printf("STA MAC: %s\n", WiFi.macAddress().c_str());
  Serial.printf("Connecting to %s", WIFI_SSID);
  if (USE_BSSID_LOCK) {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CH, WIFI_BSSID, true);
  } else {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi failed");
  }
}

void sendHeartbeat() {
  DynamicJsonDocument doc(2048);
  String url = String(API_HOST) + ENDPOINT_HEARTBEAT;
  if (httpGetJson(url, doc)) {
    Serial.println("Heartbeat ok");
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  // Init TFT
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);
  tft.init();
  tft.setRotation(1);
  tft.fillScreen(0x0000);
  // Init touch
  vspi.begin(T_SCLK, T_MISO, T_MOSI, T_CS);
  ts.begin(vspi);
  ts.setRotation(1);
  // Boot text
  tft.setCursor(4, 4);
  tft.setTextSize(2);
  tft.setTextColor(0xFFFF, 0x0000);
  tft.print("Spoolio CYD — booting…");
  // Ensure default text scale is 1 for subsequent UI draws
  tft.setTextSize(1);
  // Quick touch self-test: draw dots where touches are detected for 3 seconds.
  // Long-press (>1.2s) anywhere during this window to enter calibration wizard.
  unsigned long selfTestUntil = millis() + 3000;
  bool longPressArmed = false;
  unsigned long pressStart = 0;
  while (millis() < selfTestUntil) {
    int16_t sx, sy;
    if (readTouchRawMapped(sx, sy)) {
      if (!longPressArmed) { longPressArmed = true; pressStart = millis(); }
      tft.fillCircle(sx, sy, 3, COL_ACC);
      if (millis() - pressStart > 1200) {
        // Enter calibration
        break;
      }
    } else {
      longPressArmed = false;
    }
    delay(20);
  }
  if (longPressArmed && millis() - pressStart > 1200) {
    // Calibration wizard
    tft.fillScreen(COL_BG);
    drawHeader("Calibrate Touch", 0x5ACB);
    tft.setTextColor(COL_FG, COL_BG);
    tft.setFont(&fonts::Font2);
    tft.setTextDatum(textdatum_t::top_left);
    int cx[4] = { 24, tft.width()-24, tft.width()-24, 24 };
    int cy[4] = { 40, 40, tft.height()-24, tft.height()-24 };
    uint64_t rawAccX[4] = {0,0,0,0}, rawAccY[4] = {0,0,0,0};
    uint16_t cnt[4] = {0,0,0,0};
    for (int i=0;i<4;i++) {
      tft.fillScreen(COL_BG);
      drawHeader("Calibrate Touch", 0x5ACB);
      tft.setCursor(8, 28);
      tft.printf("Touch and hold target %d", i+1);
      tft.drawFastHLine(cx[i]-8, cy[i], 16, COL_ACC);
      tft.drawFastVLine(cx[i], cy[i]-8, 16, COL_ACC);
      unsigned long holdStart = 0;
      while (true) {
        uint16_t rx, ry, rz;
        if (readTouchRaw(rx, ry, rz)) {
          if (holdStart == 0) holdStart = millis();
          (void)rz;
          rawAccX[i] += rx;
          rawAccY[i] += ry;
          cnt[i]++;
          if (millis() - holdStart > 600) break;
        } else {
          holdStart = 0;
        }
        delay(10);
      }
      delay(200);
    }
    // Derive min/max and swap/invert suggestions
    double avgRawX[4], avgRawY[4];
    for (int i=0;i<4;i++) {
      avgRawX[i] = (double)rawAccX[i] / (double)max(1, (int)cnt[i]);
      avgRawY[i] = (double)rawAccY[i] / (double)max(1, (int)cnt[i]);
    }
    double spanXRawX = (avgRawX[1] > avgRawX[0]) ? (avgRawX[1] - avgRawX[0]) : (avgRawX[0] - avgRawX[1]);
    double spanXRawY = (avgRawY[1] > avgRawY[0]) ? (avgRawY[1] - avgRawY[0]) : (avgRawY[0] - avgRawY[1]);
    bool suggestSwap = (spanXRawX < spanXRawY);
    double leftX  = suggestSwap ? avgRawY[0] : avgRawX[0];
    double rightX = suggestSwap ? avgRawY[1] : avgRawX[1];
    double topY   = suggestSwap ? avgRawX[0] : avgRawY[0];
    double botY   = suggestSwap ? avgRawX[2] : avgRawY[2];
    int mx0 = (int)min(leftX, rightX), mx1 = (int)max(leftX, rightX);
    int my0 = (int)min(topY, botY),    my1 = (int)max(topY, botY);
    bool invX = (leftX > rightX);
    bool invY = (topY > botY);
    CAL_IN_USE = true;
    CAL_SWAP_XY = suggestSwap;
    CAL_INVERT_X = invX;
    CAL_INVERT_Y = invY;
    CAL_X_MIN = mx0; CAL_X_MAX = mx1;
    CAL_Y_MIN = my0; CAL_Y_MAX = my1;
    Serial.printf("[Cal] X_MIN=%d X_MAX=%d invX=%d\n", CAL_X_MIN, CAL_X_MAX, (int)CAL_INVERT_X);
    Serial.printf("[Cal] Y_MIN=%d Y_MAX=%d invY=%d\n", CAL_Y_MIN, CAL_Y_MAX, (int)CAL_INVERT_Y);
    Serial.printf("[Cal] swapXY=%d\n", (int)CAL_SWAP_XY);
    // Confirm screen
    tft.fillScreen(COL_BG);
    drawHeader("Calibration Applied", 0x5ACB);
    tft.setCursor(8, 28);
    tft.printf("X:%d..%d inv:%d", CAL_X_MIN, CAL_X_MAX, (int)CAL_INVERT_X);
    tft.setCursor(8, 48);
    tft.printf("Y:%d..%d inv:%d", CAL_Y_MIN, CAL_Y_MAX, (int)CAL_INVERT_Y);
    tft.setCursor(8, 68);
    tft.printf("swapXY:%d", (int)CAL_SWAP_XY);
    delay(1200);
  }
  connectWiFi();
  sendHeartbeat();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    delay(1000);
    return;
  }

  // Rotate cards periodically
  unsigned long now = millis();
  // Touch handling: swipe left/right to change cards, tap to toggle Live; long press to toggle browse mode
  static bool wasTouching = false;
  int16_t x=0, y=0;
  if (readTouchXY(x, y)) {
    if (!wasTouching) {
      wasTouching = true;
      isTouchActive = true;
      touchStartX = touchLastX = x;
      touchStartY = touchLastY = y;
      touchStartMs = now;
    } else {
      touchLastX = x;
      touchLastY = y;
    }
  } else if (wasTouching) {
    // Touch released: interpret gesture
    wasTouching = false;
    if (isTouchActive) {
      isTouchActive = false;
      int16_t dx = touchLastX - touchStartX;
      int16_t dy = touchLastY - touchStartY;
      unsigned long dt = now - touchStartMs;
      const int16_t swipeThreshold = 40;   // pixels
      const int16_t swipeSlopeLimit = 2;   // horizontal dominance
      const unsigned long tapTime = 300;   // ms
      const unsigned long longPressTime = 800; // ms
      const int16_t tapMove = 10;          // pixels

      if (abs(dx) > swipeThreshold && abs(dx) > swipeSlopeLimit * abs(dy)) {
        // Horizontal swipe: change cards and leave Live if needed
        liveViewEnabled = false;
        if (dx < 0) {
          // Swipe left -> next card
          currentCardIndex++;
        } else {
          // Swipe right -> previous card
          currentCardIndex = (currentCardIndex - 1);
          if (currentCardIndex < 0) currentCardIndex = 0; // clamp at 0 if unknown size
        }
        renderCards();
        lastRotate = now;
      } else if (dt <= tapTime && abs(dx) < tapMove && abs(dy) < tapMove) {
        // Tap: toggle Live view
        liveViewEnabled = !liveViewEnabled;
        if (liveViewEnabled) {
          renderLive();
        } else {
          renderCards();
          lastRotate = now;
        }
      } else if (dt >= longPressTime && abs(dx) < tapMove && abs(dy) < tapMove) {
        // Long press: toggle between browse cards and live
        liveViewEnabled = false;
        renderCards();
        lastRotate = now;
      }
    }
  }

  if (!liveViewEnabled && now - lastRotate > rotateIntervalMs) {
    lastRotate = now;
    renderCards();
    currentCardIndex++;
  }

  // Poll live status when enabled to mirror serial monitor states in near-real time
  if (liveViewEnabled && now - lastLivePoll > livePollIntervalMs) {
    lastLivePoll = now;
    renderLive();
  }

  delay(50);
}
