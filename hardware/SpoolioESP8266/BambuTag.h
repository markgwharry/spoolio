#ifndef SPOOLIO_BAMBUTAG_H
#define SPOOLIO_BAMBUTAG_H

// Bambu Lab filament tags: MIFARE Classic 1K with a 4-byte UID. Every sector is
// locked with a key derived from the UID (HKDF-SHA256, public master salt).
// Layout and derivation follow the Bambu Research Group's RFID-Tag-Guide:
//   block 1   bytes 0-7 material variant ID ("A00-W1"), 8-15 material ID ("GFA00")
//   block 2   filament type ("PLA")
//   block 4   detailed filament type ("PLA Basic")
//   block 5   bytes 0-3 colour RGBA, 4-5 spool weight (g, LE), 8-11 diameter (float, LE)
//   block 6   bytes 0-1 drying temp, 2-3 drying hours, 8-9 max / 10-11 min nozzle temp
//   block 9   tray UUID, identical on both tags of one spool
//   block 12  production date/time ("2024_01_15_10_30")
// Everything Spoolio uses lives in sectors 0-3 (blocks 0-15).
//
// This file has no Arduino dependencies so the parser and key derivation can be
// unit-tested on a desktop (see hardware/tests/bambu_tag_host_test.cpp).

#include <stddef.h>
#include <stdint.h>

#define BAMBU_UID_LEN        4
#define BAMBU_KEY_LEN        6
#define BAMBU_SECTOR_COUNT   16
#define BAMBU_READ_SECTORS   4
#define BAMBU_BLOCK_LEN      16
#define BAMBU_READ_BLOCKS    (BAMBU_READ_SECTORS * 4)

enum BambuKeyType { BAMBU_KEY_A = 0, BAMBU_KEY_B = 1 };

struct BambuTagInfo {
  char chipUid[BAMBU_UID_LEN * 2 + 1];  // raw chip UID as hex
  char trayUuid[33];                    // block 9 as 32 hex chars
  char variantId[9];
  char materialId[9];
  char material[17];
  char variant[17];
  char colorHex[8];                     // "#RRGGBB"
  char productionDate[17];
  uint16_t spoolWeight;                 // grams of filament, 0 if unknown
  float diameter;                       // mm, 0 if unknown
  uint16_t dryingTemp;
  uint16_t dryingHours;
  uint16_t nozzleTempMin;
  uint16_t nozzleTempMax;
};

// Derive the 16 per-sector keys (A or B) for a 4-byte UID. Returns false on a
// bad UID length or a crypto failure.
bool bambuDeriveKeys(const uint8_t* uid, uint8_t uidLen, BambuKeyType type,
                     uint8_t keys[BAMBU_SECTOR_COUNT][BAMBU_KEY_LEN]);

// Decode sectors 0-3. Returns false unless the blocks carry a non-empty tray
// UUID and filament type, so a foreign MIFARE Classic tag that happens to
// authenticate is not mistaken for a Bambu spool.
bool bambuParseBlocks(const uint8_t blocks[BAMBU_READ_BLOCKS][BAMBU_BLOCK_LEN],
                      const uint8_t* uid, uint8_t uidLen, BambuTagInfo& out);

#endif  // SPOOLIO_BAMBUTAG_H
