"""UTC clock helpers with explicit storage and wire-format semantics."""

import datetime


def utc_now():
    """Return a timezone-aware UTC timestamp for comparisons and token expiry."""
    return datetime.datetime.now(datetime.timezone.utc)


def utc_now_naive():
    """Return naive UTC for legacy ``DateTime`` columns and SQLite compatibility."""
    return utc_now().replace(tzinfo=None)


def utc_now_iso():
    """Return an RFC 3339 UTC timestamp for API responses."""
    return utc_now().isoformat().replace('+00:00', 'Z')
