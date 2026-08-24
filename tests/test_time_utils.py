"""Clock-helper contracts for database storage and API timestamps."""

import datetime

from time_utils import utc_now, utc_now_iso, utc_now_naive


def test_utc_clock_formats_are_explicit():
    aware = utc_now()
    stored = utc_now_naive()
    wire = utc_now_iso()

    assert aware.tzinfo is datetime.timezone.utc
    assert stored.tzinfo is None
    assert wire.endswith('Z')
    assert datetime.datetime.fromisoformat(wire.replace('Z', '+00:00')).tzinfo is not None
