"""Stable constants advertised to hardware clients."""

HARDWARE_PROTOCOL_NAME = "spoolio-hardware"
HARDWARE_PROTOCOL_VERSION = "1"
HARDWARE_WEIGHT_UNIT = "g"
MAX_GROSS_WEIGHT_GRAMS = 10_000.0


def hardware_protocol_metadata():
    """Return the machine-readable hardware protocol contract."""
    return {
        "name": HARDWARE_PROTOCOL_NAME,
        "version": HARDWARE_PROTOCOL_VERSION,
        "weight_unit": HARDWARE_WEIGHT_UNIT,
        "weight_type": "gross",
        "max_gross_weight": MAX_GROSS_WEIGHT_GRAMS,
    }
