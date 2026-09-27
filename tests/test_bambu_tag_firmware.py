"""Host-compiled checks for the scale firmware's Bambu Lab tag decoder.

Builds hardware/SpoolioESP8266/BambuTag.cpp with the desktop compiler and
compares its key derivation with an independent HKDF implementation and its
parser with a synthetic tag image. Skipped when no C++ compiler or OpenSSL
headers are available.
"""

import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

REPO_ROOT = Path(__file__).resolve().parents[1]
HARDWARE = REPO_ROOT / "hardware"
MASTER_SALT = bytes.fromhex("9a759cf2c4f7caff222cb9769b41bc96")
UID = bytes.fromhex("5AC3F21B")


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler or not Path("/usr/include/openssl/hmac.h").exists():
        pytest.skip("C++ compiler or OpenSSL headers unavailable")
    output = tmp_path_factory.mktemp("bambu") / "driver"
    subprocess.run(
        [
            compiler,
            "-std=c++11",
            "-Wall",
            "-Werror",
            "-Wno-deprecated-declarations",
            str(HARDWARE / "tests" / "bambu_tag_host_driver.cpp"),
            str(HARDWARE / "SpoolioESP8266" / "BambuTag.cpp"),
            "-lcrypto",
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def run_driver(driver, *args):
    result = subprocess.run(
        [str(driver), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def expected_keys(info):
    okm = HKDF(
        algorithm=hashes.SHA256(),
        length=96,
        salt=MASTER_SALT,
        info=info,
    ).derive(UID)
    return " ".join(okm[i:i + 6].hex().upper() for i in range(0, 96, 6))


def padded(text, length=16):
    return text.encode("ascii").ljust(length, b"\x00")


def synthetic_blocks():
    blocks = [bytes(16)] * 16
    blocks[0] = UID + bytes(12)
    blocks[1] = padded("A00-W1", 8) + padded("GFA00", 8)
    blocks[2] = padded("PLA")
    blocks[4] = padded("PLA Basic")
    blocks[5] = (
        bytes([0x00, 0xAE, 0x42, 0xFF])
        + struct.pack("<H", 1000)
        + bytes(2)
        + struct.pack("<f", 1.75)
        + bytes(4)
    )
    blocks[6] = struct.pack("<HHHHHH", 55, 8, 1, 35, 230, 190) + bytes(4)
    blocks[9] = bytes.fromhex("A1B2C3D4E5F60718293A4B5C6D7E8F90")
    blocks[12] = padded("2024_01_15_10_30")
    return blocks


def test_key_derivation_matches_reference_hkdf(driver):
    output = run_driver(driver, UID.hex())
    assert output["keys_a"] == expected_keys(b"RFID-A\x00")
    assert output["keys_b"] == expected_keys(b"RFID-B\x00")


def test_parser_decodes_bambu_blocks(driver):
    output = run_driver(driver, UID.hex(), b"".join(synthetic_blocks()).hex())
    assert output == {
        "keys_a": expected_keys(b"RFID-A\x00"),
        "keys_b": expected_keys(b"RFID-B\x00"),
        "valid": "1",
        "chip_uid": "5AC3F21B",
        "tray_uuid": "A1B2C3D4E5F60718293A4B5C6D7E8F90",
        "variant_id": "A00-W1",
        "material_id": "GFA00",
        "material": "PLA",
        "variant": "PLA Basic",
        "color_hex": "#00AE42",
        "production_date": "2024_01_15_10_30",
        "spool_weight": "1000",
        "diameter": "1.75",
        "drying_temp": "55",
        "drying_hours": "8",
        "nozzle_temp_min": "190",
        "nozzle_temp_max": "230",
    }


def test_parser_rejects_tags_without_tray_uuid_or_material(driver):
    blocks = synthetic_blocks()
    blocks[9] = bytes(16)
    assert run_driver(driver, UID.hex(), b"".join(blocks).hex())["valid"] == "0"

    blocks = synthetic_blocks()
    blocks[2] = bytes(16)
    assert run_driver(driver, UID.hex(), b"".join(blocks).hex())["valid"] == "0"
