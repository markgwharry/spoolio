"""Hardware device management routes (user-facing, JWT-authenticated)."""

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError

from extensions import db
import models
from time_utils import utc_now_naive
from blueprints._helpers import (
    limiter,
    hardware_auth_required,
    latest_linked_spools,
    json_object,
    serialize_hardware_device,
    serialize_spool,
    serialize_orphan_tag,
)

hardware_bp = Blueprint('hardware', __name__)

# Upper bound for a single gross weight reading (grams). Covers the largest
# consumer filament spools with generous headroom; readings above this are
# treated as sensor errors rather than real measurements.
MAX_GROSS_WEIGHT_GRAMS = 10000.0


@hardware_bp.route('/hardware/register', methods=['POST'])
@jwt_required()
def register_hardware_device():
    """Register a new hardware device."""
    current_user_id = get_jwt_identity()
    data = json_object()

    if data is None:
        return jsonify({'error': 'JSON object required'}), 400

    device_id_value = data.get('device_id')
    name_value = data.get('name')
    location_value = data.get('location')
    hardware_type_value = data.get('hardware_type')
    if location_value is not None and not isinstance(location_value, str):
        return jsonify({'error': 'location must be text'}), 400
    if hardware_type_value is not None and not isinstance(hardware_type_value, str):
        return jsonify({'error': 'hardware_type must be text'}), 400
    device_id = device_id_value.strip() if isinstance(device_id_value, str) else ''
    name = name_value.strip() if isinstance(name_value, str) else ''
    location = location_value.strip() if isinstance(location_value, str) else ''
    hardware_type = hardware_type_value.strip() if isinstance(hardware_type_value, str) else ''

    if not device_id or not name:
        return jsonify({'error': 'Device ID and name are required'}), 400

    existing_device = models.HardwareDevice.query.filter_by(device_id=device_id).first()
    if existing_device:
        return jsonify({'error': 'Device ID already registered'}), 409

    device = models.HardwareDevice(
        device_id=device_id,
        name=name,
        location=location,
        hardware_type=hardware_type or None,
        user_id=current_user_id
    )
    api_key = device.generate_api_key()

    db.session.add(device)
    db.session.commit()

    return jsonify({
        'message': 'Device registered successfully',
        'device': serialize_hardware_device(device),
        'api_key': api_key
    }), 201


@hardware_bp.route('/hardware/devices', methods=['GET'])
@jwt_required()
def get_hardware_devices():
    """Get all hardware devices for the current user."""
    current_user_id = get_jwt_identity()
    devices = models.HardwareDevice.query.filter_by(user_id=current_user_id).all()
    linked_spools = latest_linked_spools(devices)
    return jsonify([
        serialize_hardware_device(device, linked_spools.get(device.id))
        for device in devices
    ])


def _hardware_wifi_payload(device):
    return {
        'id': device.id,
        'wifi_ssid': getattr(device, 'wifi_ssid', None),
        'wifi_password_set': bool(getattr(device, 'wifi_password_encrypted', None)),
        'wifi_credentials_updated_at': (
            device.wifi_credentials_updated_at.isoformat()
            if getattr(device, 'wifi_credentials_updated_at', None)
            else None
        )
    }


@hardware_bp.route('/hardware/devices/<int:device_id>/wifi', methods=['GET'])
@jwt_required()
def get_hardware_device_wifi(device_id):
    """Return Wi-Fi metadata for a specific hardware device owned by the user."""
    current_user_id = get_jwt_identity()
    device = models.HardwareDevice.query.filter_by(id=device_id, user_id=current_user_id).first()

    if not device:
        return jsonify({'error': 'Device not found'}), 404

    return jsonify(_hardware_wifi_payload(device))


@hardware_bp.route('/hardware/devices/<int:device_id>/wifi', methods=['PUT'])
@jwt_required()
def update_hardware_device_wifi(device_id):
    """Store or rotate encrypted Wi-Fi credentials for a hardware device."""
    current_user_id = get_jwt_identity()
    device = models.HardwareDevice.query.filter_by(id=device_id, user_id=current_user_id).first()

    if not device:
        return jsonify({'error': 'Device not found'}), 404

    data = json_object()
    if data is None:
        return jsonify({'error': 'JSON object required'}), 400
    ssid_value = data.get('ssid')
    ssid = ssid_value.strip() if isinstance(ssid_value, str) else ''

    if not ssid:
        return jsonify({'error': 'SSID is required'}), 400

    clear_password = data.get('clear_password', False)
    if not isinstance(clear_password, bool):
        return jsonify({'error': 'clear_password must be a boolean'}), 400
    password_provided = 'password' in data
    new_password = None

    if password_provided:
        candidate = data.get('password')
        if candidate is None:
            return jsonify({'error': 'Password must be a string when provided'}), 400
        if not isinstance(candidate, str):
            return jsonify({'error': 'Password must be a string'}), 400
        if not candidate:
            return jsonify({'error': 'Password cannot be empty. Use clear_password to remove the stored password.'}), 400
        new_password = candidate

    if clear_password and new_password:
        return jsonify({'error': 'Provide either a new password or set clear_password, not both.'}), 400

    try:
        if clear_password:
            device.set_wifi_credentials(ssid, password='')
        else:
            device.set_wifi_credentials(ssid, password=new_password if password_provided else None)
        db.session.commit()
    except RuntimeError:
        current_app.logger.exception('Failed to persist Wi-Fi credentials for device %s', device.id)
        db.session.rollback()
        return jsonify({'error': 'Failed to store Wi-Fi credentials'}), 500
    except Exception:
        current_app.logger.exception('Failed to persist Wi-Fi credentials for device %s', device.id)
        db.session.rollback()
        return jsonify({'error': 'Failed to store Wi-Fi credentials'}), 500

    return jsonify({
        **_hardware_wifi_payload(device),
        'message': 'Wi-Fi credentials updated successfully'
    })


@hardware_bp.route('/hardware/devices/<int:device_id>', methods=['DELETE'])
@jwt_required()
def delete_hardware_device(device_id):
    """Delete a hardware device."""
    current_user_id = get_jwt_identity()
    device = models.HardwareDevice.query.filter_by(id=device_id, user_id=current_user_id).first()

    if not device:
        return jsonify({'error': 'Device not found'}), 404

    try:
        # Preserve inventory and event history while removing references that
        # would otherwise violate SQLite foreign keys when the device goes.
        models.HardwareEvent.query.filter_by(device_id=device.id).update(
            {models.HardwareEvent.device_id: None},
            synchronize_session=False,
        )
        models.OrphanTag.query.filter_by(hardware_device_id=device.id).update(
            {models.OrphanTag.hardware_device_id: None},
            synchronize_session=False,
        )
        models.FilamentSpool.query.filter_by(hardware_device_id=device.id).update(
            {models.FilamentSpool.hardware_device_id: None},
            synchronize_session=False,
        )
        db.session.delete(device)
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to delete hardware device %s', device.id)
        db.session.rollback()
        return jsonify({'error': 'Failed to delete device'}), 500

    return jsonify({'message': 'Device deleted successfully'})


@hardware_bp.route('/hardware/devices/<int:device_id>/regenerate-key', methods=['POST'])
@jwt_required()
def regenerate_hardware_device_key(device_id):
    """Regenerate the API key for a hardware device owned by the current user."""
    current_user_id = get_jwt_identity()
    device = models.HardwareDevice.query.filter_by(id=device_id, user_id=current_user_id).first()

    if not device:
        return jsonify({'error': 'Device not found'}), 404

    new_key = device.generate_api_key()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to regenerate API key'}), 500

    return jsonify({
        'message': 'API key regenerated successfully',
        'device': serialize_hardware_device(device),
        'api_key': new_key
    })


@hardware_bp.route('/hardware/spool/<nfc_tag_id>', methods=['GET'])
@limiter.limit("60 per minute")
@hardware_auth_required
def get_spool_by_nfc(nfc_tag_id):
    """Get spool information by NFC tag ID."""
    current_user_id = getattr(request.hardware_device, 'user_id', None)
    spool = models.FilamentSpool.query.filter_by(
        nfc_tag_id=nfc_tag_id,
        user_id=current_user_id,
    ).first()

    if not spool:
        return jsonify({'error': 'Spool not found for NFC tag'}), 404

    return jsonify(serialize_spool(spool))


@hardware_bp.route('/hardware/weight-update', methods=['POST'])
@limiter.limit("30 per minute")
@hardware_auth_required
def update_spool_weight():
    """Update spool weight from hardware device."""
    data = json_object()

    if data is None:
        return jsonify({'error': 'JSON object required'}), 400

    nfc_tag_value = data.get('nfc_tag_id')
    nfc_tag_id = nfc_tag_value.strip() if isinstance(nfc_tag_value, str) else ''
    weight = data.get('weight')
    timestamp = data.get('timestamp')

    if not nfc_tag_id or weight is None:
        return jsonify({'error': 'NFC tag ID and weight are required'}), 400

    current_user_id = getattr(request.hardware_device, 'user_id', None)
    spool = models.FilamentSpool.query.filter_by(
        nfc_tag_id=nfc_tag_id,
        user_id=current_user_id,
    ).first()
    if not spool:
        orphan = models.OrphanTag.query.filter_by(
            nfc_tag_id=nfc_tag_id,
            user_id=current_user_id,
        ).first()
        if not orphan and current_user_id is not None:
            orphan = models.OrphanTag.query.filter_by(
                nfc_tag_id=nfc_tag_id,
                user_id=None,
            ).first()

        orphan_recorded = False
        orphan_conflict = False
        if orphan:
            orphan.last_seen = utc_now_naive()
            try:
                orphan.last_weight = float(weight) if weight is not None else None
            except Exception:
                orphan.last_weight = None
            orphan.hardware_device_id = request.hardware_device.id
            if current_user_id and not orphan.user_id:
                orphan.user_id = current_user_id
            orphan_recorded = True
        else:
            conflicting_orphan = models.OrphanTag.query.filter_by(
                nfc_tag_id=nfc_tag_id,
            ).first()
            if conflicting_orphan:
                orphan_conflict = True
            else:
                try:
                    last_weight_val = float(weight) if weight is not None else None
                except Exception:
                    last_weight_val = None
                orphan = models.OrphanTag(
                    nfc_tag_id=nfc_tag_id,
                    last_weight=last_weight_val,
                    hardware_device_id=request.hardware_device.id,
                    user_id=current_user_id,
                )
                db.session.add(orphan)
                orphan_recorded = True

        def queue_orphan_event():
            evt = models.HardwareEvent(
                device_id=request.hardware_device.id,
                user_id=current_user_id,
                event_type='orphan',
                nfc_tag_id=nfc_tag_id,
                weight=None,
                message='NFC tag not linked to any spool'
            )
            db.session.add(evt)

        try:
            queue_orphan_event()
        except Exception as e:
            current_app.logger.warning('Failed to log orphan hardware event: %s', e)
        try:
            db.session.commit()
        except IntegrityError:
            # A simultaneous scan can win the globally unique orphan-tag insert.
            # Treat it as a cross-owner conflict instead of returning a 500.
            db.session.rollback()
            orphan_recorded = False
            orphan_conflict = True
            try:
                queue_orphan_event()
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Failed to log duplicate orphan scan')

        response = {
            'error': 'Spool not found for NFC tag',
            'orphan_recorded': orphan_recorded,
        }
        if orphan_conflict:
            response['orphan_conflict'] = True
        return jsonify(response), 404

    try:
        weight = float(weight)
        if weight < 0:
            return jsonify({'error': 'Weight cannot be negative'}), 400
        # Reject physically implausible readings (largest consumer spools are ~10kg
        # gross). This guards against scale glitches and malformed/abusive payloads
        # corrupting usage calculations.
        if weight > MAX_GROSS_WEIGHT_GRAMS:
            return jsonify({'error': 'Weight exceeds maximum supported value'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid weight value'}), 400

    tare_weight = 0
    try:
        if spool.spool_type and getattr(spool.spool_type, 'tare_weight', None) is not None:
            tare_weight = float(spool.spool_type.tare_weight or 0)
    except Exception:
        tare_weight = 0

    net_weight = max(0.0, float(weight) - tare_weight)

    try:
        previous_remaining = float(spool.weight_remaining or 0)
    except Exception:
        previous_remaining = 0.0

    raw_weight_used = previous_remaining - net_weight
    weight_used = raw_weight_used
    increase_detected = False
    refill_detected = False

    try:
        tolerance = float(current_app.config.get('WEIGHT_INCREASE_TOLERANCE', 5.0))
    except Exception:
        tolerance = 5.0

    try:
        starting_weight = float(spool.weight_start or 0)
    except Exception:
        starting_weight = 0.0

    default_refill_threshold = max(50.0, starting_weight * 0.2) if starting_weight else 50.0
    try:
        refill_threshold = float(current_app.config.get('WEIGHT_REFILL_THRESHOLD', default_refill_threshold))
    except Exception:
        refill_threshold = default_refill_threshold

    if raw_weight_used < 0:
        increase_detected = True
        increase_amount = abs(raw_weight_used)
        weight_used = 0.0

        minor_increase = increase_amount <= tolerance
        was_low = previous_remaining < (starting_weight * 0.3) if starting_weight else True
        if minor_increase:
            net_weight = previous_remaining
        elif increase_amount >= refill_threshold or (was_low and increase_amount > tolerance * 2):
            refill_detected = True

        message = (
            f"Minor weight increase of {increase_amount:.2f}g detected; treated as measurement tolerance."
            if minor_increase
            else (
                "Significant weight increase detected; treating as refill and resetting baseline."
                if refill_detected
                else f"Weight increased by {increase_amount:.2f}g; updating baseline without consumption."
            )
        )

        try:
            evt = models.HardwareEvent(
                device_id=request.hardware_device.id,
                user_id=getattr(request.hardware_device, 'user_id', None),
                event_type='refill_detected' if refill_detected else 'weight_increase_detected',
                nfc_tag_id=nfc_tag_id,
                spool_id=spool.id,
                weight=net_weight,
                message=message
            )
            db.session.add(evt)
        except Exception as e:
            current_app.logger.warning('Failed to log weight increase event: %s', e)

    spool.weight_remaining = net_weight
    spool.hardware_last_update = utc_now_naive()
    spool.hardware_device_id = request.hardware_device.id
    spool.is_empty = net_weight <= 0

    if weight_used > 0:
        history = models.SpoolHistory(
            spool_id=spool.id,
            date=utc_now_naive(),
            weight_used=weight_used,
            notes=f"Hardware update from {request.hardware_device.name}"
        )
        db.session.add(history)

    try:
        evt = models.HardwareEvent(
            device_id=request.hardware_device.id,
            user_id=getattr(request.hardware_device, 'user_id', None),
            event_type='weight_update',
            nfc_tag_id=nfc_tag_id,
            spool_id=spool.id,
            weight=net_weight,
            message='Weight updated from hardware'
        )
        db.session.add(evt)
    except Exception as e:
        current_app.logger.warning('Failed to log weight update event: %s', e)

    db.session.commit()

    return jsonify({
        'message': 'Weight updated successfully',
        'spool': serialize_spool(spool),
        'weight_used': weight_used,
        'tare_weight_applied': tare_weight,
        'net_weight': net_weight,
        'increase_detected': increase_detected,
        'refill_detected': refill_detected
    })


# --- Orphan Tags ---

def _claimable_orphan_tags(user_id):
    """Return orphan rows owned by, or safely claimable by, ``user_id``."""
    return models.OrphanTag.query.outerjoin(
        models.HardwareDevice,
        models.OrphanTag.hardware_device_id == models.HardwareDevice.id,
    ).filter(
        (models.OrphanTag.user_id == user_id)
        | (
            models.OrphanTag.user_id.is_(None)
            & (
                models.OrphanTag.hardware_device_id.is_(None)
                | models.HardwareDevice.user_id.is_(None)
                | (models.HardwareDevice.user_id == user_id)
            )
        )
    )


@hardware_bp.route('/hardware/orphans', methods=['GET'])
@jwt_required()
def list_orphan_tags():
    """List orphan NFC tag reads that are not yet linked to a spool."""
    current_user_id = get_jwt_identity()
    orphans = _claimable_orphan_tags(current_user_id).order_by(
        models.OrphanTag.last_seen.desc()
    ).all()
    return jsonify({'orphans': [serialize_orphan_tag(o) for o in orphans]})


@hardware_bp.route('/hardware/orphans/link', methods=['POST'])
@jwt_required()
def link_orphan_tag():
    """Link an orphan NFC tag to a spool and remove the orphan record."""
    current_user_id = get_jwt_identity()
    data = json_object()
    if data is None:
        return jsonify({'error': 'JSON object required'}), 400
    nfc_tag_value = data.get('nfc_tag_id')
    nfc_tag_id = nfc_tag_value.strip() if isinstance(nfc_tag_value, str) else ''
    spool_id_value = data.get('spool_id')
    try:
        if isinstance(spool_id_value, bool):
            raise ValueError
        if isinstance(spool_id_value, float) and not spool_id_value.is_integer():
            raise ValueError
        spool_id = int(spool_id_value)
        if spool_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        spool_id = None
    if not nfc_tag_id or spool_id is None:
        return jsonify({'error': 'nfc_tag_id and spool_id are required'}), 400

    spool = models.FilamentSpool.query.filter_by(id=spool_id, user_id=current_user_id).first()
    if not spool:
        return jsonify({'error': 'Spool not found'}), 404

    existing = models.FilamentSpool.query.filter_by(nfc_tag_id=nfc_tag_id).first()
    if existing and existing.id != spool.id:
        return jsonify({'error': 'NFC tag already linked to another spool'}), 409

    orphan = _claimable_orphan_tags(current_user_id).filter(
        models.OrphanTag.nfc_tag_id == nfc_tag_id
    ).first()
    if not orphan and models.OrphanTag.query.filter_by(nfc_tag_id=nfc_tag_id).first():
        return jsonify({'error': 'NFC tag is associated with another account'}), 409

    spool.nfc_tag_id = nfc_tag_id
    if orphan:
        try:
            if orphan.last_weight is not None:
                tare_weight = 0.0
                try:
                    if spool.spool_type and getattr(spool.spool_type, 'tare_weight', None) is not None:
                        tare_weight = float(spool.spool_type.tare_weight or 0)
                except Exception:
                    tare_weight = 0.0
                net_weight = max(0.0, float(orphan.last_weight) - tare_weight)

                previous_remaining = float(spool.weight_remaining or 0)
                weight_used = previous_remaining - net_weight

                if weight_used > 0:
                    history = models.SpoolHistory(
                        spool_id=spool.id,
                        date=utc_now_naive(),
                        weight_used=weight_used,
                        notes="First hardware measurement after linking NFC tag"
                    )
                    db.session.add(history)
                    spool.last_used_date = utc_now_naive()

                spool.weight_remaining = net_weight
                spool.hardware_last_update = utc_now_naive()
                if orphan.hardware_device_id:
                    orphan_device = db.session.get(
                        models.HardwareDevice,
                        orphan.hardware_device_id,
                    )
                    if orphan_device and str(orphan_device.user_id) == str(current_user_id):
                        spool.hardware_device_id = orphan.hardware_device_id
                spool.is_empty = net_weight <= 0
        except Exception:
            pass
        db.session.delete(orphan)

    db.session.commit()
    return jsonify({'message': 'Tag linked successfully', 'spool': serialize_spool(spool)})


@hardware_bp.route('/hardware/orphans/<nfc_tag_id>', methods=['DELETE'])
@jwt_required()
def delete_orphan_tag(nfc_tag_id):
    """Delete an orphan NFC tag record."""
    current_user_id = get_jwt_identity()
    orphan = models.OrphanTag.query.filter_by(
        nfc_tag_id=nfc_tag_id,
        user_id=current_user_id,
    ).first()
    if not orphan:
        return jsonify({'error': 'Orphan tag not found'}), 404
    db.session.delete(orphan)
    db.session.commit()
    return jsonify({'message': 'Orphan tag deleted'})
