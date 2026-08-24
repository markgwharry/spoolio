# Spoolio hardware

This directory has two maintained reference Arduino sketches.

| Target | Maintained sketch | Role |
| --- | --- | --- |
| WeMos D1 Mini / ESP8266 | `SpoolioESP8266/SpoolioESP8266.ino` | NFC and HX711 scale client, with optional OLED and LEDs |
| ESP32 Cheap Yellow Display | `SpoolioCYDDisplay/SpoolioCYDDisplay.ino` | Touchscreen status display client |

## ESP8266 provisioning

1. In Spoolio's Hardware page, register a device and copy the plaintext API
   key when it is shown. Spoolio stores only its digest and cannot show it again.
2. Flash `SpoolioESP8266`. Open the USB serial monitor at 115200 baud.
3. Enter `api_key <key>` and `device_id <device-id>`. Enter `config` to verify
   that both are set; the key is only shown as a short prefix.
4. Join the `Spoolio-Setup` access point and open `http://192.168.4.1`, or enter
   `wifi_ap` over serial, to choose the device's Wi-Fi network.
5. Use `status`, `i2cscan`, `tare`, and `weight` for the first bench checks.

For timestamped serial output, install `pyserial` and run
`python hardware/serial_monitor.py <port>` from the repository root.

The canonical sketch supports these compile-time options near its configuration
section:

- `HEADLESS_DISPLAY=1` skips the OLED.
- `MIRROR_DISPLAY_TO_SERIAL=1` mirrors display messages to USB serial.
- `USE_SH1106=1` selects SH1106; set it to `0` for SSD1306.
- `DISABLE_NFC=1` permits scale/display development without the PN532.

## ESP32-CYD provisioning

`SpoolioCYDDisplay` is currently a reference display client, not a zero-touch
installer. Before compiling, replace `YOUR_WIFI_SSID`, `YOUR_WIFI_PASSWORD`,
and `YOUR_DEVICE_API_KEY` in the sketch. Change `API_HOST` if you are using a
self-hosted service. Leave `USE_BSSID_LOCK` disabled unless you deliberately
provide the access point BSSID for a controlled deployment.

## Build verification

The consolidated sketches were compiled with Arduino CLI using ESP8266 core
3.1.2, ESP32 core 3.3.5, and WiFiManager 2.0.17. Typical commands are:

```bash
arduino-cli compile --fqbn esp8266:esp8266:d1_mini hardware/SpoolioESP8266
arduino-cli compile --fqbn esp32:esp32:esp32 hardware/SpoolioCYDDisplay
```

Install the libraries included by each sketch before compiling. The ESP8266
build uses WiFiManager, ArduinoJson, HX711, Adafruit display/NeoPixel, and PN532
libraries. The CYD build uses ArduinoJson, LovyanGFX, and XPT2046_Touchscreen.

A successful compile does not prove pin mapping, boot behavior, NFC reads, load
cell calibration, touchscreen calibration, Wi-Fi reliability, or an end-to-end
TLS session. Flash and bench-test those items on the exact hardware revision.

## TLS trust

Maintained sketches validate the server using the ISRG Root X1 CA stored in
their local `SpoolioTlsTrust.h`. `ALLOW_INSECURE_TLS` defaults to `0`. Never turn
it on in a device carrying a real API key; it exists only for isolated local
diagnostics.

When the service certificate chain changes:

1. Inspect the live chain (for example with `openssl s_client`) and identify the
   issuing trust anchor.
2. Download the PEM only from the certificate authority's official site.
3. Replace the CA in both maintained `SpoolioTlsTrust.h` files.
4. Compile both sketches, then flash-test a real HTTPS heartbeat before release.

## Firmware updates

Neither maintained sketch implements OTA. Firmware is flashed over USB. The
server's release/download endpoints are disabled by default with
`FIRMWARE_OTA_ENABLED=false`; enabling them is only appropriate when developing
and validating a compatible client.

The sketches are starting points for community hardware, not a claim of compatibility
with every board or scale. Contributions should document exact pins, dependencies,
compile results, and separate physical bench validation.
