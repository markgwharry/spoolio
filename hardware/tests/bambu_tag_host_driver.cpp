// Desktop driver for BambuTag.cpp, used by tests/test_bambu_tag_firmware.py.
// Usage: bambu_tag_host_driver <uid-hex> [<256 bytes of blocks 0-15 as hex>]
// Prints derived keys and, when blocks are given, the parsed fields.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../SpoolioESP8266/BambuTag.h"

static bool parseHex(const char* hex, uint8_t* out, size_t len) {
  if (strlen(hex) != len * 2) return false;
  for (size_t i = 0; i < len; i++) {
    unsigned int v;
    if (sscanf(hex + i * 2, "%2x", &v) != 1) return false;
    out[i] = (uint8_t)v;
  }
  return true;
}

static void printKeys(const char* label, uint8_t keys[BAMBU_SECTOR_COUNT][BAMBU_KEY_LEN]) {
  printf("%s", label);
  for (int s = 0; s < BAMBU_SECTOR_COUNT; s++) {
    printf(s ? " " : "=");
    for (int i = 0; i < BAMBU_KEY_LEN; i++) printf("%02X", keys[s][i]);
  }
  printf("\n");
}

int main(int argc, char** argv) {
  if (argc < 2) return 2;
  uint8_t uid[BAMBU_UID_LEN];
  if (!parseHex(argv[1], uid, sizeof(uid))) return 2;

  uint8_t keys[BAMBU_SECTOR_COUNT][BAMBU_KEY_LEN];
  if (!bambuDeriveKeys(uid, sizeof(uid), BAMBU_KEY_A, keys)) return 3;
  printKeys("keys_a", keys);
  if (!bambuDeriveKeys(uid, sizeof(uid), BAMBU_KEY_B, keys)) return 3;
  printKeys("keys_b", keys);

  if (argc < 3) return 0;
  uint8_t blocks[BAMBU_READ_BLOCKS][BAMBU_BLOCK_LEN];
  if (!parseHex(argv[2], &blocks[0][0], sizeof(blocks))) return 2;
  BambuTagInfo info;
  printf("valid=%d\n", bambuParseBlocks(blocks, uid, sizeof(uid), info) ? 1 : 0);
  printf("chip_uid=%s\ntray_uuid=%s\nvariant_id=%s\nmaterial_id=%s\n",
         info.chipUid, info.trayUuid, info.variantId, info.materialId);
  printf("material=%s\nvariant=%s\ncolor_hex=%s\nproduction_date=%s\n",
         info.material, info.variant, info.colorHex, info.productionDate);
  printf("spool_weight=%u\ndiameter=%.2f\ndrying_temp=%u\ndrying_hours=%u\n",
         info.spoolWeight, info.diameter, info.dryingTemp, info.dryingHours);
  printf("nozzle_temp_min=%u\nnozzle_temp_max=%u\n", info.nozzleTempMin, info.nozzleTempMax);
  return 0;
}
