"""Validation and helpers for decoded spool-tag metadata sent by devices.

A device that can decode a vendor tag (for example a Bambu Lab MIFARE Classic
tag) may attach what it read as an optional ``tag`` object. Spoolio keeps it on
the orphan record so the owner can create the spool without retyping it. The
metadata is advisory: invalid fields are dropped rather than failing the
measurement that carried them.
"""

import json
import math
import re

TAG_FORMAT_PATTERN = re.compile(r'^[a-z0-9_-]{1,32}$')
COLOR_HEX_PATTERN = re.compile(r'^#?([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?$')
IDENTIFIER_PATTERN = re.compile(r'^[0-9A-Fa-f]{8,64}$')

# field name -> maximum length for short printable strings
TEXT_FIELDS = {
    'material': 32,
    'variant': 64,
    'material_id': 16,
    'variant_id': 16,
    'production_date': 32,
}

# field name -> inclusive (minimum, maximum)
NUMBER_FIELDS = {
    'spool_weight': (1, 10_000),
    'diameter': (0.5, 5),
    'nozzle_temp_min': (0, 500),
    'nozzle_temp_max': (0, 500),
    'drying_temp': (0, 200),
    'drying_time_h': (0, 96),
}

BAMBU_MANUFACTURER_NAMES = ('Bambu Lab', 'Bambu')

# Coarse reference palette for suggesting a colour name from a tag's RGB value.
# The owner always confirms the name; this only saves typing the common case.
BASIC_COLOR_NAMES = (
    ('white', (255, 255, 255)),
    ('black', (0, 0, 0)),
    ('grey', (128, 128, 128)),
    ('silver', (192, 192, 192)),
    ('red', (200, 30, 30)),
    ('orange', (255, 130, 0)),
    ('yellow', (250, 220, 0)),
    ('green', (0, 160, 60)),
    ('blue', (0, 90, 200)),
    ('cyan', (0, 190, 210)),
    ('purple', (120, 50, 160)),
    ('pink', (240, 120, 170)),
    ('brown', (120, 70, 30)),
    ('beige', (225, 205, 160)),
)


def _clean_text(value, max_length):
    if not isinstance(value, str):
        return None
    text = ''.join(ch for ch in value if ch.isprintable()).strip()
    if not text:
        return None
    return text[:max_length]


def _clean_number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < minimum or number > maximum:
        return None
    return int(number) if number.is_integer() else number


def normalize_tag_metadata(value):
    """Return a cleaned copy of a device ``tag`` object, or ``None``.

    Raises ``ValueError`` only when ``value`` is present but not an object; any
    individual field that fails validation is silently dropped.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('tag must be an object')

    tag_format = value.get('format')
    if not isinstance(tag_format, str) or not TAG_FORMAT_PATTERN.match(tag_format.strip().lower()):
        return None
    cleaned = {'format': tag_format.strip().lower()}

    chip_uid = value.get('chip_uid')
    if isinstance(chip_uid, str) and IDENTIFIER_PATTERN.match(chip_uid.strip()):
        cleaned['chip_uid'] = chip_uid.strip().upper()

    for field, max_length in TEXT_FIELDS.items():
        text = _clean_text(value.get(field), max_length)
        if text is not None:
            cleaned[field] = text

    color_hex = value.get('color_hex')
    if isinstance(color_hex, str):
        match = COLOR_HEX_PATTERN.match(color_hex.strip())
        if match:
            cleaned['color_hex'] = '#' + match.group(1).upper()

    for field, (minimum, maximum) in NUMBER_FIELDS.items():
        number = _clean_number(value.get(field), minimum, maximum)
        if number is not None:
            cleaned[field] = number

    return cleaned


def suggest_color_name(color_hex):
    """Return the nearest basic colour name for ``#RRGGBB``, or ``None``."""
    if not isinstance(color_hex, str):
        return None
    match = COLOR_HEX_PATTERN.match(color_hex.strip())
    if not match:
        return None
    rgb = tuple(int(match.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    return min(
        BASIC_COLOR_NAMES,
        key=lambda item: sum((a - b) ** 2 for a, b in zip(rgb, item[1])),
    )[0]


def suggest_subtype(material, variant):
    """Derive a subtype from a detailed name: ('PLA', 'PLA Basic') -> 'Basic'."""
    if not variant:
        return None
    if material and variant.lower().startswith(material.lower()):
        remainder = variant[len(material):].strip(' -_')
        return remainder or None
    return None if material and variant.lower() == material.lower() else variant


def tag_suggestions(metadata):
    """Return owner-facing defaults derived from stored tag metadata."""
    if not metadata:
        return {}
    suggestions = {}
    material = metadata.get('material')
    if material:
        suggestions['material'] = material
    subtype = suggest_subtype(material, metadata.get('variant'))
    if subtype:
        suggestions['subtype'] = subtype
    color_name = suggest_color_name(metadata.get('color_hex'))
    if color_name:
        suggestions['color'] = color_name
    if metadata.get('spool_weight'):
        suggestions['weight_start'] = metadata['spool_weight']
    if metadata.get('format') == 'bambu':
        suggestions['manufacturer'] = BAMBU_MANUFACTURER_NAMES[0]
    return suggestions


def load_orphan_tag_metadata(orphan):
    """Decode an orphan's stored tag metadata, tolerating legacy or bad rows."""
    raw = getattr(orphan, 'tag_metadata', None)
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def store_orphan_tag_metadata(orphan, metadata):
    """Replace an orphan's tag metadata with an already-normalized object."""
    if not metadata:
        return
    orphan.tag_format = metadata.get('format')
    orphan.tag_metadata = json.dumps(metadata, sort_keys=True)
