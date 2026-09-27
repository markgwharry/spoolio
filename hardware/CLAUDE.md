# Hardware and firmware context (ESP8266/ESP32)

- **Canonical scale sketch: `SpoolioESP8266/SpoolioESP8266.ino`.** Wi-Fi comes from the
  WiFiManager captive portal. The device API key and device ID are stored in EEPROM and
  set over USB serial (`api_key <key>`, `device_id <id>`). All sketches use this auth model.
- **Canonical display sketch: `SpoolioCYDDisplay/SpoolioCYDDisplay.ino`.** These are the
  only maintained sketches. `README.md` covers building, provisioning and the physical
  smoke tests.
- **The server contract** is `docs/HARDWARE_PROTOCOL.md` (protocol v1). Keep
  `HARDWARE_PROTOCOL_NAME = "spoolio-hardware"` for v1; it is a published compatibility
  promise. `generic_client.py` is the reference Python client.
- **Never commit real credentials:** no Wi-Fi SSIDs or passwords, device API keys,
  BSSIDs/MACs or LAN IPs. Use the `YOUR_WIFI_SSID`, `YOUR_WIFI_PASSWORD` and
  `YOUR_DEVICE_API_KEY` placeholders.
- **TLS:** maintained sketches trust ISRG Root X1 through `SpoolioTlsTrust.h`.
  `ALLOW_INSECURE_TLS` defaults off and must never be enabled with real credentials.
- **OTA:** no maintained sketch implements a client. The backend surface is disabled by
  default (`FIRMWARE_OTA_ENABLED=false`), so don't claim that OTA works.
- **Bambu Lab tags:** `BambuTag.{h,cpp}` decode MIFARE Classic spool tags on the device.
  The server-side parser is `hardware_tags.py`. `hardware/tests/` holds a host driver that
  `tests/test_bambu_tag_firmware.py` compiles and runs against the firmware code.
- Device-facing endpoints live in `blueprints/hardware.py` and `hardware_comms.py`
  (auth: `Authorization: Bearer <device api key>` via `@hardware_auth_required`).
- **Firmware changes aren't done until they have been flashed and bench-tested.** Say in
  the PR what was tested on which board.
