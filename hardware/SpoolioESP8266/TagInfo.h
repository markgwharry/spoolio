#ifndef SPOOLIO_TAGINFO_H
#define SPOOLIO_TAGINFO_H

#include <Arduino.h>

struct TagInfo {
  String rawPayload;  // optional: full NFC payload/UID if available
  String id;
  String material;
  String color;
  String tare;
};

#endif // SPOOLIO_TAGINFO_H
