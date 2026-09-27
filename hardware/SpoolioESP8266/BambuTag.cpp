#include "BambuTag.h"

#include <stdio.h>
#include <string.h>

#if defined(ESP8266)
#include <bearssl/bearssl.h>  // shipped with the ESP8266 Arduino core
#elif defined(ARDUINO)
#error "BambuTag.cpp needs an HMAC-SHA256 backend for this board"
#else
#include <openssl/evp.h>
#include <openssl/hmac.h>
#endif

namespace {

// HKDF salt published in the RFID-Tag-Guide.
const uint8_t kMasterSalt[16] = {
  0x9a, 0x75, 0x9c, 0xf2, 0xc4, 0xf7, 0xca, 0xff,
  0x22, 0x2c, 0xb9, 0x76, 0x9b, 0x41, 0xbc, 0x96,
};

// HKDF "info" strings include their trailing NUL (7 bytes).
const uint8_t kInfoKeyA[] = {'R', 'F', 'I', 'D', '-', 'A', 0};
const uint8_t kInfoKeyB[] = {'R', 'F', 'I', 'D', '-', 'B', 0};

bool hmacSha256(const uint8_t* key, size_t keyLen,
                const uint8_t* a, size_t aLen,
                const uint8_t* b, size_t bLen,
                uint8_t c, bool withC, uint8_t out[32]) {
#if defined(ESP8266)
  br_hmac_key_context kc;
  br_hmac_context ctx;
  br_hmac_key_init(&kc, &br_sha256_vtable, key, keyLen);
  br_hmac_init(&ctx, &kc, 0);
  if (aLen) br_hmac_update(&ctx, a, aLen);
  if (bLen) br_hmac_update(&ctx, b, bLen);
  if (withC) br_hmac_update(&ctx, &c, 1);
  br_hmac_out(&ctx, out);
  return true;
#else
  uint8_t buf[32 + 16 + 1];
  size_t n = 0;
  memcpy(buf + n, a, aLen); n += aLen;
  memcpy(buf + n, b, bLen); n += bLen;
  if (withC) buf[n++] = c;
  unsigned int outLen = 0;
  return HMAC(EVP_sha256(), key, (int)keyLen, buf, n, out, &outLen) && outLen == 32;
#endif
}

// Copy a fixed-width tag field, keeping printable ASCII and trimming padding.
void copyText(char* dst, size_t dstLen, const uint8_t* src, size_t srcLen) {
  size_t n = 0;
  for (size_t i = 0; i < srcLen && n + 1 < dstLen; i++) {
    if (src[i] == 0) break;
    if (src[i] >= 0x20 && src[i] <= 0x7e) dst[n++] = (char)src[i];
  }
  while (n > 0 && dst[n - 1] == ' ') n--;
  dst[n] = '\0';
}

uint16_t readU16(const uint8_t* p) {
  return (uint16_t)(p[0] | (p[1] << 8));
}

void toHex(char* dst, const uint8_t* src, size_t len) {
  static const char digits[] = "0123456789ABCDEF";
  for (size_t i = 0; i < len; i++) {
    dst[i * 2] = digits[src[i] >> 4];
    dst[i * 2 + 1] = digits[src[i] & 0x0f];
  }
  dst[len * 2] = '\0';
}

}  // namespace

bool bambuDeriveKeys(const uint8_t* uid, uint8_t uidLen, BambuKeyType type,
                     uint8_t keys[BAMBU_SECTOR_COUNT][BAMBU_KEY_LEN]) {
  if (!uid || uidLen != BAMBU_UID_LEN) return false;
  const uint8_t* info = (type == BAMBU_KEY_B) ? kInfoKeyB : kInfoKeyA;
  const size_t infoLen = sizeof(kInfoKeyA);

  // HKDF-Extract: PRK = HMAC(salt, UID)
  uint8_t prk[32];
  if (!hmacSha256(kMasterSalt, sizeof(kMasterSalt), uid, uidLen, nullptr, 0, 0, false, prk)) {
    return false;
  }

  // HKDF-Expand to 16 keys x 6 bytes = 96 bytes (three SHA-256 blocks).
  uint8_t okm[96];
  uint8_t t[32];
  size_t tLen = 0;
  for (uint8_t counter = 1; counter <= 3; counter++) {
    if (!hmacSha256(prk, sizeof(prk), t, tLen, info, infoLen, counter, true, t)) return false;
    tLen = sizeof(t);
    memcpy(okm + (counter - 1) * 32, t, 32);
  }
  for (int i = 0; i < BAMBU_SECTOR_COUNT; i++) {
    memcpy(keys[i], okm + i * BAMBU_KEY_LEN, BAMBU_KEY_LEN);
  }
  return true;
}

bool bambuParseBlocks(const uint8_t blocks[BAMBU_READ_BLOCKS][BAMBU_BLOCK_LEN],
                      const uint8_t* uid, uint8_t uidLen, BambuTagInfo& out) {
  memset(&out, 0, sizeof(out));
  if (!uid || uidLen != BAMBU_UID_LEN) return false;
  toHex(out.chipUid, uid, uidLen);

  bool anyUuidByte = false;
  for (int i = 0; i < 16; i++) anyUuidByte |= (blocks[9][i] != 0);
  if (!anyUuidByte) return false;
  toHex(out.trayUuid, blocks[9], 16);

  copyText(out.variantId, sizeof(out.variantId), blocks[1], 8);
  copyText(out.materialId, sizeof(out.materialId), blocks[1] + 8, 8);
  copyText(out.material, sizeof(out.material), blocks[2], 16);
  copyText(out.variant, sizeof(out.variant), blocks[4], 16);
  copyText(out.productionDate, sizeof(out.productionDate), blocks[12], 16);
  if (out.material[0] == '\0') return false;

  snprintf(out.colorHex, sizeof(out.colorHex), "#%02X%02X%02X",
           blocks[5][0], blocks[5][1], blocks[5][2]);
  out.spoolWeight = readU16(blocks[5] + 4);

  float diameter = 0;
  memcpy(&diameter, blocks[5] + 8, sizeof(diameter));  // little-endian IEEE-754
  out.diameter = (diameter > 0.5f && diameter < 5.0f) ? diameter : 0;

  out.dryingTemp = readU16(blocks[6]);
  out.dryingHours = readU16(blocks[6] + 2);
  out.nozzleTempMax = readU16(blocks[6] + 8);
  out.nozzleTempMin = readU16(blocks[6] + 10);
  return true;
}
