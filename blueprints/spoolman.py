"""Spoolman-compatible REST API.

Exposes a subset of the Spoolman v1 API (https://github.com/Donkie/Spoolman) so
that the existing 3D-printing ecosystem — Moonraker, OctoPrint-Spoolman,
OrcaSlicer, NFC scales such as FilaMan — can read this user's inventory and
report filament usage against it.

Spoolman itself is single-tenant and unauthenticated. Spoolio is multi-user, so
the public API is scoped by a per-user token embedded in the path:

    https://<host>/spoolman/<token>/api/v1/...

The user pastes ``https://<host>/spoolman/<token>`` as the "Spoolman URL" in
their slicer / Moonraker config. A JWT-protected management endpoint
(``/api/integrations/spoolman``) issues and rotates the token.

Mapping (Spoolio -> Spoolman):
  * Manufacturer      -> Vendor
  * FilamentSpool     -> Spool (+ a synthetic per-spool Filament)
Spoolio does not store density/diameter, so Spoolman's required values default
to PLA-ish 1.24 g/cm3 and 1.75 mm; weight<->length is derived from those.
"""

import datetime
import math

from flask import Blueprint, jsonify, request, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
import models
from blueprints._helpers import json_object, limiter
from time_utils import utc_now_naive

spoolman_bp = Blueprint('spoolman', __name__)

# Spoolio doesn't track these; Spoolman requires them (> 0). Defaults match PLA.
DEFAULT_DENSITY = 1.24      # g/cm^3
DEFAULT_DIAMETER = 1.75     # mm
# Version advertised on /info. Some clients refuse to talk to "too old" a
# Spoolman; advertise a recent one. Override with SPOOLMAN_COMPAT_VERSION.
DEFAULT_COMPAT_VERSION = '0.22.1'
SPOOLMAN_RATE_LIMIT = '60 per minute'
spoolman_api_rate_limit = limiter.shared_limit(
    SPOOLMAN_RATE_LIMIT,
    scope='spoolman-token-api',
)
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

# Minimal colour-name -> hex map for color_hex output (Spoolio stores names).
COLOR_HEX = {
    'red': 'e74c3c', 'grey': '888888', 'gray': '888888', 'white': 'ffffff',
    'black': '222222', 'blue': '3498db', 'green': '27ae60', 'yellow': 'f1c40f',
    'orange': 'e67e22', 'purple': '9b59b6', 'pink': 'ff69b4', 'brown': '8b4513',
    'gold': 'ffd700', 'silver': 'c0c0c0', 'teal': '1abc9c', 'cyan': '00bcd4',
    'magenta': 'e91e63', 'lime': '8bc34a', 'beige': 'f5f5dc', 'natural': 'd4c4a8',
    'navy': '001f3f', 'maroon': '800000', 'olive': '808000', 'clear': 'bfefff',
}


# ---------------------------------------------------------------------------
# Conversions & helpers
# ---------------------------------------------------------------------------
def _grams_per_mm(density=DEFAULT_DENSITY, diameter=DEFAULT_DIAMETER):
    """Mass per mm of filament for the given density (g/cm^3) and diameter (mm)."""
    radius_mm = diameter / 2.0
    area_mm2 = math.pi * radius_mm * radius_mm
    # area(mm^2) * length(mm) = volume(mm^3); /1000 -> cm^3; * density -> grams
    return area_mm2 * density / 1000.0


def weight_to_length(weight_g, density=DEFAULT_DENSITY, diameter=DEFAULT_DIAMETER):
    gpm = _grams_per_mm(density, diameter)
    return (weight_g or 0.0) / gpm if gpm else 0.0


def length_to_weight(length_mm, density=DEFAULT_DENSITY, diameter=DEFAULT_DIAMETER):
    return (length_mm or 0.0) * _grams_per_mm(density, diameter)


def _to_iso(value):
    """Serialise a date/datetime to an ISO-8601 UTC string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
        return dt.isoformat()
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day,
                                 tzinfo=datetime.timezone.utc).isoformat()
    return None


def _color_hex(color_name):
    if not color_name:
        return None
    return COLOR_HEX.get(color_name.strip().lower())


def _compat_version():
    return current_app.config.get('SPOOLMAN_COMPAT_VERSION', DEFAULT_COMPAT_VERSION)


# ---------------------------------------------------------------------------
# Serializers (Spoolio -> Spoolman shapes)
# ---------------------------------------------------------------------------
def serialize_vendor(manufacturer):
    if manufacturer is None:
        return None
    return {
        'id': manufacturer.id,
        'registered': _to_iso(EPOCH),
        'name': manufacturer.name,
        'comment': None,
        'empty_spool_weight': None,
        'external_id': None,
        'extra': {},
    }


def serialize_filament(spool):
    """A synthetic Spoolman Filament derived from a single Spoolio spool."""
    material = spool.material.name if spool.material else None
    color = spool.color.name if spool.color else None
    name_parts = [p for p in (material, color) if p]
    tare = None
    if spool.spool_type is not None:
        tare = getattr(spool.spool_type, 'tare_weight', None)
    return {
        'id': spool.id,
        'registered': _to_iso(spool.purchase_date) or _to_iso(EPOCH),
        'name': ' '.join(name_parts) or None,
        'vendor': serialize_vendor(spool.manufacturer),
        'material': material,
        'price': spool.price,
        'density': DEFAULT_DENSITY,
        'diameter': DEFAULT_DIAMETER,
        'weight': spool.weight_start,
        'spool_weight': tare,
        'article_number': spool.barcode,
        'comment': None,
        'settings_extruder_temp': None,
        'settings_bed_temp': None,
        'color_hex': _color_hex(color),
        'multi_color_hexes': None,
        'multi_color_direction': None,
        'external_id': None,
        'extra': {},
    }


def serialize_spool(spool):
    start = float(spool.weight_start or 0.0)
    remaining = max(0.0, float(spool.weight_remaining or 0.0))
    used = max(0.0, start - remaining)
    tare = None
    if spool.spool_type is not None:
        tare = getattr(spool.spool_type, 'tare_weight', None)

    # first/last used from history if available, else last_used_date.
    history_dates = [h.date for h in (spool.history or []) if h.date]
    first_used = min(history_dates) if history_dates else None
    last_used = max(history_dates) if history_dates else spool.last_used_date

    archived = bool(spool.is_empty) or (spool.is_active is False)

    return {
        'id': spool.id,
        'registered': _to_iso(spool.purchase_date) or _to_iso(EPOCH),
        'first_used': _to_iso(first_used),
        'last_used': _to_iso(last_used),
        'filament': serialize_filament(spool),
        'price': spool.price,
        'remaining_weight': remaining,
        'initial_weight': start,
        'spool_weight': tare,
        'used_weight': used,
        'remaining_length': weight_to_length(remaining),
        'used_length': weight_to_length(used),
        'location': None,
        'lot_nr': spool.serial_number,
        'comment': spool.notes,
        'archived': archived,
        'extra': {},
    }


# ---------------------------------------------------------------------------
# Token scoping
# ---------------------------------------------------------------------------
def _user_for_token(token):
    """Resolve the owning user for a Spoolman integration token, or None."""
    if not token:
        return None
    return models.User.query.filter_by(spoolman_token=token).first()


def _unauthorized():
    return jsonify({'message': 'Invalid Spoolman integration token'}), 401


def _user_spools(user, include_archived=False):
    q = models.FilamentSpool.query.filter_by(user_id=user.id)
    if not include_archived:
        # The serializer reports both empty and inactive spools as "archived",
        # so exclude both here unless archived spools are explicitly requested —
        # otherwise a slicer could decrement a spool the user deactivated.
        q = q.filter(
            models.FilamentSpool.is_empty.is_(False),
            models.FilamentSpool.is_active.isnot(False),
        )
    return q.order_by(models.FilamentSpool.id.asc()).all()


def _get_user_spool(user, spool_id):
    return models.FilamentSpool.query.filter_by(id=spool_id, user_id=user.id).first()


# ---------------------------------------------------------------------------
# Public Spoolman API  (scoped by /spoolman/<token>/api/v1/...)
# ---------------------------------------------------------------------------
@spoolman_bp.route('/spoolman/<token>/api/v1/info', methods=['GET'])
@spoolman_api_rate_limit
def spm_info(token):
    if _user_for_token(token) is None:
        return _unauthorized()
    return jsonify({
        'version': _compat_version(),
        'debug_mode': False,
        'automatic_backups': False,
        'data_dir': '',
        'backups_dir': '',
        'db_type': 'sqlite',
        'git_commit': None,
        'build_date': None,
    })


@spoolman_bp.route('/spoolman/<token>/api/v1/health', methods=['GET'])
@spoolman_api_rate_limit
def spm_health(token):
    if _user_for_token(token) is None:
        return _unauthorized()
    return jsonify({'status': 'healthy'})


@spoolman_bp.route('/spoolman/<token>/api/v1/vendor', methods=['GET'])
@spoolman_api_rate_limit
def spm_vendors(token):
    user = _user_for_token(token)
    if user is None:
        return _unauthorized()
    manufacturers = (
        models.Manufacturer.query
        .join(
            models.FilamentSpool,
            models.FilamentSpool.manufacturer_id == models.Manufacturer.id,
        )
        .filter(models.FilamentSpool.user_id == user.id)
        .distinct()
        .order_by(models.Manufacturer.id)
        .all()
    )
    return jsonify([serialize_vendor(manufacturer) for manufacturer in manufacturers])


@spoolman_bp.route('/spoolman/<token>/api/v1/vendor/<int:vendor_id>', methods=['GET'])
@spoolman_api_rate_limit
def spm_vendor(token, vendor_id):
    user = _user_for_token(token)
    if user is None:
        return _unauthorized()
    owned = models.FilamentSpool.query.filter_by(
        user_id=user.id, manufacturer_id=vendor_id).first()
    if not owned:
        return jsonify({'message': 'Vendor not found'}), 404
    return jsonify(serialize_vendor(owned.manufacturer))


@spoolman_bp.route('/spoolman/<token>/api/v1/filament', methods=['GET'])
@spoolman_api_rate_limit
def spm_filaments(token):
    user = _user_for_token(token)
    if user is None:
        return _unauthorized()
    spools = _user_spools(user, include_archived=True)
    return jsonify([serialize_filament(s) for s in spools])


@spoolman_bp.route('/spoolman/<token>/api/v1/filament/<int:filament_id>', methods=['GET'])
@spoolman_api_rate_limit
def spm_filament(token, filament_id):
    user = _user_for_token(token)
    if user is None:
        return _unauthorized()
    spool = _get_user_spool(user, filament_id)
    if not spool:
        return jsonify({'message': 'Filament not found'}), 404
    return jsonify(serialize_filament(spool))


@spoolman_bp.route('/spoolman/<token>/api/v1/spool', methods=['GET'])
@spoolman_api_rate_limit
def spm_spools(token):
    user = _user_for_token(token)
    if user is None:
        return _unauthorized()
    allow_archived = request.args.get('allow_archived', 'false').lower() in ('1', 'true', 'yes')
    spools = _user_spools(user, include_archived=allow_archived)
    return jsonify([serialize_spool(s) for s in spools])


@spoolman_bp.route('/spoolman/<token>/api/v1/spool/<int:spool_id>', methods=['GET'])
@spoolman_api_rate_limit
def spm_spool(token, spool_id):
    user = _user_for_token(token)
    if user is None:
        return _unauthorized()
    spool = _get_user_spool(user, spool_id)
    if not spool:
        return jsonify({'message': 'Spool not found'}), 404
    return jsonify(serialize_spool(spool))


@spoolman_bp.route('/spoolman/<token>/api/v1/spool/<int:spool_id>/use', methods=['PUT'])
@spoolman_api_rate_limit
def spm_spool_use(token, spool_id):
    """Report filament consumption. Body: exactly one of use_weight | use_length.

    This is the integration that lets slicers/Moonraker auto-decrement a spool.
    """
    user = _user_for_token(token)
    if user is None:
        return _unauthorized()
    spool = _get_user_spool(user, spool_id)
    if not spool:
        return jsonify({'message': 'Spool not found'}), 404

    data = json_object()
    if data is None:
        return jsonify({'message': 'JSON object required'}), 400
    use_weight = data.get('use_weight')
    use_length = data.get('use_length')
    if (use_weight is None) == (use_length is None):
        return jsonify({'message': 'Provide exactly one of use_weight or use_length'}), 400

    try:
        if use_weight is not None:
            grams = float(use_weight)
        else:
            grams = length_to_weight(float(use_length))
    except (TypeError, ValueError):
        return jsonify({'message': 'Invalid use_weight/use_length value'}), 400

    if grams < 0:
        return jsonify({'message': 'Usage must be non-negative'}), 400

    now = utc_now_naive()
    previous_remaining = max(0.0, float(spool.weight_remaining or 0.0))
    # Only deduct (and log) what was actually on the spool, so reporting more
    # than remains doesn't inflate usage history / analytics.
    actual_used = min(grams, previous_remaining)
    spool.weight_remaining = previous_remaining - actual_used
    spool.last_used_date = now
    if spool.weight_remaining <= 0:
        spool.is_empty = True

    # Mirror Spoolio's own usage logging so the history/analytics stay correct.
    if actual_used > 0:
        db.session.add(models.SpoolHistory(
            spool_id=spool.id,
            date=now,
            weight_used=actual_used,
            notes='Spoolman API usage',
        ))

    try:
        db.session.commit()
    except Exception:
        current_app.logger.exception('Spoolman /use failed')
        db.session.rollback()
        return jsonify({'message': 'Failed to record usage'}), 500

    return jsonify(serialize_spool(spool))


# ---------------------------------------------------------------------------
# Management (JWT-protected): issue / rotate / disable the integration token
# ---------------------------------------------------------------------------
def _integration_payload(user):
    base = request.host_url.rstrip('/')
    spoolman_url = f"{base}/spoolman/{user.spoolman_token}" if user.spoolman_token else None
    return {
        'enabled': bool(user.spoolman_token),
        'token': user.spoolman_token,
        'spoolman_url': spoolman_url,
        'hint': 'Paste spoolman_url as the Spoolman server URL in Moonraker / '
                'OctoPrint-Spoolman / your slicer.',
    }


@spoolman_bp.route('/api/integrations/spoolman', methods=['GET'])
@jwt_required()
def spm_integration_get():
    user = db.session.get(models.User, get_jwt_identity())
    if not user:
        return jsonify({'message': 'User not found'}), 404
    return jsonify(_integration_payload(user))


@spoolman_bp.route('/api/integrations/spoolman', methods=['POST'])
@jwt_required()
def spm_integration_enable():
    """Generate the token if absent, or rotate it when ?rotate=true."""
    user = db.session.get(models.User, get_jwt_identity())
    if not user:
        return jsonify({'message': 'User not found'}), 404
    rotate = request.args.get('rotate', 'false').lower() in ('1', 'true', 'yes')
    if not user.spoolman_token or rotate:
        user.generate_spoolman_token()
        db.session.commit()
    return jsonify(_integration_payload(user))


@spoolman_bp.route('/api/integrations/spoolman', methods=['DELETE'])
@jwt_required()
def spm_integration_disable():
    user = db.session.get(models.User, get_jwt_identity())
    if not user:
        return jsonify({'message': 'User not found'}), 404
    user.spoolman_token = None
    db.session.commit()
    return jsonify(_integration_payload(user))
