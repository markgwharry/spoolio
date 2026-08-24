"""Shared helpers, decorators, serializers, and constants used across API blueprints."""

import os
import re
import time
import hmac
import hashlib
import base64
import datetime
import ipaddress

from flask import jsonify, request, current_app, g, url_for
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from sqlalchemy import and_, or_
from werkzeug.utils import secure_filename

from extensions import db
import models
from time_utils import utc_now_naive

# ---------------------------------------------------------------------------
# Singletons – initialised once and shared across blueprints
# ---------------------------------------------------------------------------

jwt = JWTManager()


def get_client_address():
    """Trust nginx X-Real-IP only when the immediate peer is local."""
    peer = get_remote_address()
    if peer in {'127.0.0.1', '::1'}:
        forwarded = request.headers.get('X-Real-IP', '').strip()
        try:
            return str(ipaddress.ip_address(forwarded)) if forwarded else peer
        except ValueError:
            return peer
    return peer


limiter = Limiter(
    key_func=get_client_address,
    default_limits=[],
    storage_uri="memory://",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_FIRMWARE_EXTENSIONS = {'bin', 'uf2', 'hex', 'zip'}
FIRMWARE_TOKEN_TTL_SECONDS = 300
FIRMWARE_EMAIL_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # one week
WEIGHT_INCREASE_TOLERANCE = 5.0
DEFAULT_REFILL_THRESHOLD = 50.0
HARDWARE_ONLINE_THRESHOLD = 120

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def error_response(msg, status=500):
    """Return a standard JSON error response."""
    return jsonify({'error': msg}), status


def json_object():
    """Return an object JSON body, or ``None`` for malformed/other JSON types."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def get_current_user():
    """Return the current user instance for authenticated routes."""
    user_id = get_jwt_identity()
    if not user_id:
        return None
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        pass
    verified_user = getattr(g, 'jwt_user', None)
    if verified_user is not None and str(verified_user.id) == str(user_id):
        return verified_user
    return db.session.get(models.User, user_id)


def get_user_device_or_404(device_id, user_id):
    """Return a HardwareDevice owned by *user_id* or abort with 404 JSON."""
    device = models.HardwareDevice.query.filter_by(id=device_id, user_id=user_id).first()
    if not device:
        return None
    return device


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def validate_email(email):
    """Basic email validation with header injection protection."""
    if not email:
        return False
    if '\n' in email or '\r' in email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_username(username):
    """Username validation – alphanumeric and underscore only."""
    return re.match(r'^[a-zA-Z0-9_]{3,20}$', username) is not None


def validate_password(password):
    """Password validation – minimum 8 characters with complexity requirements.

    Returns (is_valid, error_message) tuple.
    """
    if len(password) < 8:
        return False, 'Password must be at least 8 characters'
    if not re.search(r'[A-Z]', password):
        return False, 'Password must contain at least one uppercase letter'
    if not re.search(r'[a-z]', password):
        return False, 'Password must contain at least one lowercase letter'
    if not re.search(r'[0-9]', password):
        return False, 'Password must contain at least one number'
    return True, ''


# ---------------------------------------------------------------------------
# Profile image helpers
# ---------------------------------------------------------------------------


def get_profile_image_folder():
    """Return the folder where profile images are stored, creating it if needed."""
    folder = current_app.config.get(
        'PROFILE_IMAGE_FOLDER',
        os.path.join(current_app.root_path, 'shared', 'profile_images')
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def allowed_profile_image(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMAGE_EXTENSIONS
    )


def build_profile_image_url(user):
    filename = getattr(user, 'profile_image_filename', None)
    if not filename or not filename.strip():
        return None
    safe_name = os.path.basename(filename)
    if not safe_name:
        return None
    return f"/api/account/profile-image/{safe_name}"


# ---------------------------------------------------------------------------
# Firmware helpers
# ---------------------------------------------------------------------------


def firmware_ota_required(view):
    """Hide the dormant OTA surface unless an operator explicitly enables it."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_app.config.get('FIRMWARE_OTA_ENABLED', False):
            return jsonify({'error': 'Firmware OTA is disabled'}), 404
        return view(*args, **kwargs)

    return wrapped


def get_firmware_upload_folder():
    """Return the folder that stores firmware binaries, creating it if required."""
    folder = current_app.config.get(
        'FIRMWARE_UPLOAD_FOLDER',
        os.path.join(current_app.instance_path, 'firmware')
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def allowed_firmware_file(filename):
    return (
        '.' in (filename or '')
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_FIRMWARE_EXTENSIONS
    )


def _firmware_secret_bytes():
    secret = (
        current_app.config.get('FIRMWARE_DOWNLOAD_SECRET')
        or current_app.config.get('SECRET_KEY')
        or 'change-me'
    )
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    return secret


def generate_firmware_download_token(release_id, expires=None):
    """Create a short-lived download token for a firmware release."""
    if expires is None:
        expires = int(time.time()) + FIRMWARE_TOKEN_TTL_SECONDS
    payload = f"{release_id}:{int(expires)}"
    signature = hmac.new(_firmware_secret_bytes(), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    token_bytes = f"{payload}:{signature}".encode('utf-8')
    return base64.urlsafe_b64encode(token_bytes).decode('utf-8').rstrip('=')


def verify_firmware_download_token(token, release_id):
    """Validate a download token, ensuring it targets the requested release."""
    if not token:
        return False
    try:
        padding = '=' * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode((token + padding).encode('utf-8')).decode('utf-8')
        parts = decoded.split(':', 2)
        if len(parts) != 3:
            return False
        release_str, expires_str, signature = parts
        if int(release_str) != int(release_id):
            return False
        expires = int(expires_str)
        if expires < int(time.time()):
            return False
        expected_payload = f"{release_str}:{expires_str}"
        expected_signature = hmac.new(
            _firmware_secret_bytes(),
            expected_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)
    except Exception:
        return False


def generate_firmware_download_url(release, expires=None, external=False):
    token = generate_firmware_download_token(release.id, expires)
    return url_for(
        'firmware.download_firmware_binary',
        release_id=release.id,
        token=token,
        _external=external
    )


def _email_download_token_expiry():
    """Return a long-lived expiry timestamp for emailed firmware links."""
    ttl_value = current_app.config.get(
        'FIRMWARE_EMAIL_TOKEN_TTL_SECONDS',
        FIRMWARE_EMAIL_TOKEN_TTL_SECONDS,
    )
    try:
        ttl_seconds = int(ttl_value)
    except (TypeError, ValueError):
        current_app.logger.warning(
            'Invalid FIRMWARE_EMAIL_TOKEN_TTL_SECONDS %r; defaulting to %s seconds',
            ttl_value,
            FIRMWARE_EMAIL_TOKEN_TTL_SECONDS,
        )
        ttl_seconds = FIRMWARE_EMAIL_TOKEN_TTL_SECONDS

    if ttl_seconds <= 0:
        current_app.logger.warning(
            'Non-positive FIRMWARE_EMAIL_TOKEN_TTL_SECONDS %r; using default %s seconds',
            ttl_seconds,
            FIRMWARE_EMAIL_TOKEN_TTL_SECONDS,
        )
        ttl_seconds = FIRMWARE_EMAIL_TOKEN_TTL_SECONDS

    return int(time.time()) + ttl_seconds


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def serialize_material(material):
    return {'id': material.id, 'name': material.name}


def serialize_color(color):
    return {'id': color.id, 'name': color.name}


def serialize_manufacturer(manufacturer):
    return {'id': manufacturer.id, 'name': manufacturer.name}


def serialize_spool_type(spool_type):
    return {
        'id': spool_type.id,
        'name': spool_type.name,
        'compatible_with_ams': spool_type.compatible_with_ams,
        'tare_weight': getattr(spool_type, 'tare_weight', 0) or 0
    }


def serialize_group(group):
    return {
        'id': group.id,
        'name': group.name,
        'material_id': group.material_id,
        'color_id': group.color_id,
        'user_id': group.user_id
    }


def serialize_spool(spool):
    return {
        'id': spool.id,
        'material_id': spool.material_id,
        'material_name': spool.material.name if spool.material else None,
        'color_id': spool.color_id,
        'color_name': spool.color.name if spool.color else None,
        'manufacturer_id': spool.manufacturer_id,
        'manufacturer_name': spool.manufacturer.name if spool.manufacturer else None,
        'spool_type_id': spool.spool_type_id,
        'tare_weight': spool.spool_type.tare_weight if spool.spool_type else 0,
        'group_id': spool.group_id,
        'user_id': spool.user_id,
        'weight_start': spool.weight_start,
        'weight_remaining': spool.weight_remaining,
        'is_active': spool.is_active,
        'is_empty': spool.is_empty,
        'notes': spool.notes,
        'subtype': spool.subtype,
        'low_stock_threshold': spool.low_stock_threshold,
        'purchase_date': spool.purchase_date.isoformat() if spool.purchase_date else None,
        'last_used_date': spool.last_used_date.isoformat() if spool.last_used_date else None,
        'barcode': spool.barcode,
        'serial_number': spool.serial_number,
        'nfc_tag_id': getattr(spool, 'nfc_tag_id', None),
        'price': getattr(spool, 'price', None)
    }


def serialize_empty_spool(empty):
    return {
        'id': empty.id,
        'user_id': empty.user_id,
        'spool_type_id': empty.spool_type_id,
        'origin_spool_id': empty.origin_spool_id,
        'created_at': empty.created_at.isoformat() if getattr(empty, 'created_at', None) else None,
        'notes': getattr(empty, 'notes', None)
    }


def serialize_refill(refill):
    return {
        'id': refill.id,
        'user_id': refill.user_id,
        'material_id': refill.material_id,
        'color_id': refill.color_id,
        'manufacturer_id': refill.manufacturer_id,
        'group_id': refill.group_id,
        'weight_total': refill.weight_total,
        'weight_remaining': refill.weight_remaining,
        'subtype': getattr(refill, 'subtype', None),
        'purchase_date': refill.purchase_date.isoformat() if getattr(refill, 'purchase_date', None) else None,
        'notes': getattr(refill, 'notes', None),
        'price': getattr(refill, 'price', None),
        'barcode': getattr(refill, 'barcode', None),
        'serial_number': getattr(refill, 'serial_number', None),
        'created_at': refill.created_at.isoformat() if getattr(refill, 'created_at', None) else None
    }


def serialize_orphan_tag(orphan):
    return {
        'id': orphan.id,
        'nfc_tag_id': orphan.nfc_tag_id,
        'first_seen': orphan.first_seen.isoformat() if orphan.first_seen else None,
        'last_seen': orphan.last_seen.isoformat() if orphan.last_seen else None,
        'last_weight': orphan.last_weight,
        'hardware_device_id': orphan.hardware_device_id,
        'user_id': orphan.user_id,
    }


def serialize_spool_history(history):
    return {
        'id': history.id,
        'spool_id': history.spool_id,
        'date': history.date.isoformat() if history.date else None,
        'weight_used': history.weight_used,
        'notes': history.notes,
        'project_id': getattr(history, 'project_id', None),
        'project_name': getattr(history.project, 'name', None) if getattr(history, 'project', None) else None
    }


def serialize_bit_category(category):
    return {'id': category.id, 'name': category.name}


def serialize_bit(bit):
    return {
        'id': bit.id,
        'user_id': bit.user_id,
        'category_id': bit.category_id,
        'category_name': bit.category.name if bit.category else None,
        'name': bit.name,
        'description': bit.description,
        'quantity_total': bit.quantity_total,
        'quantity_remaining': bit.quantity_remaining,
        'low_stock_threshold': bit.low_stock_threshold,
        'unit': bit.unit,
        'price': bit.price,
        'supplier': bit.supplier,
        'purchase_date': bit.purchase_date.isoformat() if bit.purchase_date else None,
        'notes': bit.notes,
        'is_active': bit.is_active,
        'created_at': bit.created_at.isoformat() if bit.created_at else None,
    }


def serialize_bit_usage(usage):
    return {
        'id': usage.id,
        'bit_id': usage.bit_id,
        'bit_name': usage.bit.name if usage.bit else None,
        'category_name': usage.bit.category.name if usage.bit and usage.bit.category else None,
        'project_id': usage.project_id,
        'project_name': usage.project.name if usage.project else None,
        'quantity_used': usage.quantity_used,
        'date': usage.date.isoformat() if usage.date else None,
        'notes': usage.notes,
    }


def serialize_firmware_release(release, include_signed_url=False):
    if not release:
        return None
    base_download_url = release.download_url or url_for('firmware.download_firmware_binary', release_id=release.id)
    data = {
        'id': release.id,
        'version': release.version,
        'hardware_type': release.hardware_type,
        'original_filename': release.original_filename,
        'download_url': base_download_url,
        'release_notes': release.release_notes,
        'manual_instructions': release.manual_instructions,
        'checksum': release.checksum,
        'is_active': release.is_active,
        'created_at': release.created_at.isoformat() if release.created_at else None,
        'file_size': release.file_size,
    }
    if include_signed_url:
        data['signed_download_url'] = generate_firmware_download_url(release)
    return data


def serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'email_verified': getattr(user, 'email_verified', False),
        'profile_image_url': build_profile_image_url(user),
        'is_admin': getattr(user, 'is_admin', False)
    }


def serialize_account(user):
    data = serialize_user(user)
    data.update({
        'created_at': user.created_at.isoformat() if getattr(user, 'created_at', None) else None,
    })
    return data


_NOT_PRELOADED = object()


def latest_linked_spools(devices):
    """Load the newest owner-matched spool for each device in one query."""
    devices_by_id = {device.id: device for device in devices}
    if not devices_by_id:
        return {}

    try:
        ranked_spools = (
            db.session.query(
                models.FilamentSpool.id.label('spool_id'),
                db.func.row_number().over(
                    partition_by=models.FilamentSpool.hardware_device_id,
                    order_by=(
                        models.FilamentSpool.hardware_last_update.desc(),
                        models.FilamentSpool.id.desc(),
                    ),
                ).label('position'),
            )
            .join(
                models.HardwareDevice,
                models.HardwareDevice.id == models.FilamentSpool.hardware_device_id,
            )
            .filter(models.HardwareDevice.id.in_(devices_by_id))
            .filter(or_(
                models.FilamentSpool.user_id == models.HardwareDevice.user_id,
                and_(
                    models.FilamentSpool.user_id.is_(None),
                    models.HardwareDevice.user_id.is_(None),
                ),
            ))
            .subquery()
        )
        spools = (
            models.FilamentSpool.query
            .join(
                ranked_spools,
                ranked_spools.c.spool_id == models.FilamentSpool.id,
            )
            .filter(ranked_spools.c.position == 1)
            .options(
                db.joinedload(models.FilamentSpool.material),
                db.joinedload(models.FilamentSpool.color),
                db.joinedload(models.FilamentSpool.manufacturer),
            )
            .all()
        )
    except Exception:
        return {}
    return {spool.hardware_device_id: spool for spool in spools}


def event_spools(events):
    """Load owner-matched spools referenced by hardware events in one query."""
    events = list(events)
    spool_ids = {event.spool_id for event in events if event.spool_id is not None}
    if not spool_ids:
        return {}

    try:
        spools_by_id = {
            spool.id: spool
            for spool in (
                models.FilamentSpool.query
                .filter(models.FilamentSpool.id.in_(spool_ids))
                .options(
                    db.joinedload(models.FilamentSpool.material),
                    db.joinedload(models.FilamentSpool.color),
                    db.joinedload(models.FilamentSpool.manufacturer),
                )
                .all()
            )
        }
    except Exception:
        return {}
    return {
        event.id: spool
        for event in events
        if (spool := spools_by_id.get(event.spool_id)) is not None
        and str(spool.user_id) == str(getattr(event, 'user_id', None))
    }


def serialize_hardware_device(device, last_linked_spool=_NOT_PRELOADED):
    """Serialize hardware device with connection state and last linked spool metadata."""
    try:
        threshold_seconds = int(
            current_app.config.get('HARDWARE_ONLINE_THRESHOLD_SECONDS', HARDWARE_ONLINE_THRESHOLD)
        )
    except Exception:
        threshold_seconds = HARDWARE_ONLINE_THRESHOLD

    last_seen = getattr(device, 'last_seen', None)
    last_seen_iso = last_seen.isoformat() if last_seen else None
    is_online = False
    if last_seen:
        try:
            is_online = (utc_now_naive() - last_seen).total_seconds() <= threshold_seconds
        except Exception:
            is_online = False
    connection_state = 'online' if is_online else 'offline'

    if last_linked_spool is _NOT_PRELOADED:
        try:
            spool = (
                models.FilamentSpool.query
                .filter_by(
                    hardware_device_id=device.id,
                    user_id=getattr(device, 'user_id', None),
                )
                .options(
                    db.joinedload(models.FilamentSpool.material),
                    db.joinedload(models.FilamentSpool.color),
                    db.joinedload(models.FilamentSpool.manufacturer),
                )
                .order_by(models.FilamentSpool.hardware_last_update.desc(), models.FilamentSpool.id.desc())
                .first()
            )
        except Exception:
            spool = None
    else:
        spool = last_linked_spool

    last_linked_spool = None
    if spool:
        last_linked_spool = {
            'id': spool.id,
            'material_name': getattr(getattr(spool, 'material', None), 'name', None),
            'color_name': getattr(getattr(spool, 'color', None), 'name', None),
            'manufacturer_name': getattr(getattr(spool, 'manufacturer', None), 'name', None),
            'nfc_tag_id': getattr(spool, 'nfc_tag_id', None),
            'hardware_last_update': spool.hardware_last_update.isoformat() if getattr(spool, 'hardware_last_update', None) else None,
            'weight_remaining': getattr(spool, 'weight_remaining', None)
        }

    return {
        'id': device.id,
        'device_id': device.device_id,
        'name': device.name,
        'location': device.location,
        'hardware_type': getattr(device, 'hardware_type', None),
        'last_seen': last_seen_iso,
        'status': connection_state,
        'connection_state': connection_state,
        'is_online': is_online,
        'created_at': device.created_at.isoformat() if device.created_at else None,
        'last_linked_spool': last_linked_spool,
        'wifi_ssid': getattr(device, 'wifi_ssid', None),
        'wifi_password_set': bool(getattr(device, 'wifi_password_encrypted', None)),
        'wifi_credentials_updated_at': (
            device.wifi_credentials_updated_at.isoformat()
            if getattr(device, 'wifi_credentials_updated_at', None)
            else None
        )
    }


def serialize_hardware_event(event, spool=_NOT_PRELOADED):
    if spool is _NOT_PRELOADED:
        try:
            spool = (
                models.FilamentSpool.query
                .filter_by(
                    id=event.spool_id,
                    user_id=getattr(event, 'user_id', None),
                )
                .options(
                    db.joinedload(models.FilamentSpool.material),
                    db.joinedload(models.FilamentSpool.color),
                    db.joinedload(models.FilamentSpool.manufacturer),
                )
                .first()
                if event.spool_id else None
            )
        except Exception:
            spool = None

    def safe_name(obj, attr):
        try:
            return getattr(obj, attr).name if getattr(obj, attr) else None
        except Exception:
            return None

    return {
        'id': event.id,
        'event_type': event.event_type,
        'nfc_tag_id': event.nfc_tag_id,
        'spool_id': spool.id if spool else None,
        'weight': event.weight,
        'message': event.message,
        'created_at': event.created_at.isoformat() if event.created_at else None,
        'spool': (
            {
                'id': spool.id,
                'material': safe_name(spool, 'material'),
                'color': safe_name(spool, 'color'),
                'manufacturer': safe_name(spool, 'manufacturer'),
                'weight_remaining': getattr(spool, 'weight_remaining', None)
            } if spool else None
        )
    }


# ---------------------------------------------------------------------------
# Shared domain helpers
# ---------------------------------------------------------------------------


def _ensure_group(user_id, material_id, color_id):
    group = models.FilamentGroup.query.filter_by(
        user_id=user_id,
        material_id=material_id,
        color_id=color_id
    ).first()
    if not group:
        color = db.session.get(models.Color, color_id)
        material = db.session.get(models.Material, material_id)
        group_name = f"{getattr(color, 'name', 'Unknown')} {getattr(material, 'name', 'Material')}".strip()
        group = models.FilamentGroup(
            user_id=user_id,
            material_id=material_id,
            color_id=color_id,
            name=group_name
        )
        db.session.add(group)
        # Keep group creation atomic with the spool/refill that needs it.
        db.session.flush()
    return group


def _maybe_create_empty_from_spool(spool):
    """Create an EmptySpool record if the spool is empty and not already logged."""
    try:
        if spool.is_empty and spool.spool_type_id:
            exists = models.EmptySpool.query.filter_by(origin_spool_id=spool.id).first()
            if not exists:
                empty = models.EmptySpool(
                    user_id=spool.user_id,
                    spool_type_id=spool.spool_type_id,
                    origin_spool_id=spool.id
                )
                db.session.add(empty)
                db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to create empty spool placeholder')
        db.session.rollback()


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def admin_required(fn):
    """Decorator ensuring the current JWT identity is marked as an administrator."""

    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or not getattr(user, 'is_admin', False):
            return jsonify({'error': 'Admin privileges required'}), 403
        return fn(*args, **kwargs)

    return wrapper


def hardware_auth_required(f):
    """Decorator to authenticate hardware devices using API key."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401

        parts = auth_header.split(' ', 1)
        if len(parts) != 2 or not parts[1].strip():
            return jsonify({'error': 'Malformed authorization header'}), 400

        api_key = parts[1].strip()
        api_key_digest = models.HardwareDevice.hash_api_key(api_key)
        device = (
            models.HardwareDevice.query
            .filter_by(api_key=api_key_digest)
            .with_for_update(read=True)
            .first()
        )

        if not device:
            return jsonify({'error': 'Invalid API key'}), 401

        try:
            device.update_last_seen()
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.warning('Failed to update device last_seen timestamp')

        request.hardware_device = device
        return f(*args, **kwargs)

    return decorated_function
