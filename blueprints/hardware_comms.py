"""Hardware device communication endpoints (hardware-auth, device-facing)."""

import datetime
import math

from flask import Blueprint, jsonify, request, url_for, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
import models
from hardware_protocol import hardware_protocol_metadata
from time_utils import utc_now_iso, utc_now_naive
from blueprints._helpers import (
    hardware_auth_required,
    event_spools,
    json_object,
    serialize_hardware_device,
    serialize_hardware_event,
    serialize_spool,
)

hardware_comms_bp = Blueprint('hardware_comms', __name__)


@hardware_comms_bp.route('/hardware/heartbeat', methods=['GET'])
@hardware_auth_required
def hardware_heartbeat():
    """Simple heartbeat to keep device online and report server time."""
    device = request.hardware_device
    device_payload = serialize_hardware_device(device)
    wifi_meta = {
        'ssid': getattr(device, 'wifi_ssid', None),
        'password_set': bool(getattr(device, 'wifi_password_encrypted', None)),
        'updated_at': (
            device.wifi_credentials_updated_at.isoformat()
            if getattr(device, 'wifi_credentials_updated_at', None)
            else None
        )
    }
    firmware_meta = None
    if current_app.config.get('FIRMWARE_OTA_ENABLED', False):
        firmware_meta = {
            'latest_endpoint': url_for('firmware.hardware_latest_firmware'),
            'hardware_type': getattr(device, 'hardware_type', None),
            'download_endpoint': url_for('firmware.download_firmware_binary', release_id=0).rsplit('/', 1)[0],
        }
    return jsonify({
        'status': 'ok',
        'server_time': utc_now_iso(),
        'connection_state': device_payload.get('connection_state'),
        'device': device_payload,
        'protocol': hardware_protocol_metadata(),
        'wifi': wifi_meta,
        'firmware': firmware_meta,
    })


@hardware_comms_bp.route('/hardware/config/wifi', methods=['GET'])
@hardware_auth_required
def hardware_wifi_config():
    """Allow hardware to fetch decrypted Wi-Fi credentials when onboarding or rotating networks."""
    from flask import current_app
    device = request.hardware_device
    password = None
    try:
        password, migrated = device.get_wifi_password_and_upgrade()
        if migrated:
            db.session.commit()
            current_app.logger.info(
                'Re-encrypted legacy Wi-Fi credential for device %s',
                device.id,
            )
    except RuntimeError:
        db.session.rollback()
        current_app.logger.exception('Failed to derive Wi-Fi key for device %s', device.id)
        return jsonify({'error': 'Failed to retrieve Wi-Fi credentials'}), 500
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to decrypt Wi-Fi credentials for device %s', device.id)
        return jsonify({'error': 'Unable to decrypt Wi-Fi credentials'}), 500

    wifi_payload = None
    if getattr(device, 'wifi_ssid', None):
        wifi_payload = {
            'ssid': device.wifi_ssid,
            'password': password,
            'updated_at': (
                device.wifi_credentials_updated_at.isoformat()
                if getattr(device, 'wifi_credentials_updated_at', None)
                else None
            )
        }

    return jsonify({
        'device_id': device.device_id,
        'wifi': wifi_payload
    })


@hardware_comms_bp.route('/hardware/events/recent', methods=['GET'])
@jwt_required()
def get_recent_hardware_events():
    """Recent hardware events for the current user (for activity feeds)."""
    user_id = get_jwt_identity()
    try:
        limit = max(1, min(int(request.args.get('limit', 10)), 100))
    except (ValueError, TypeError):
        limit = 10
    try:
        events = (
            models.HardwareEvent.query
            .filter((models.HardwareEvent.user_id == user_id) | (models.HardwareEvent.user_id.is_(None)))
            .order_by(models.HardwareEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        spools_by_event = event_spools(events)
        return jsonify({
            'events': [
                serialize_hardware_event(event, spools_by_event.get(event.id))
                for event in events
            ]
        })
    except Exception:
        return jsonify({'events': []})


@hardware_comms_bp.route('/hardware/live/status', methods=['GET'])
@hardware_auth_required
def live_status():
    """Return a simple live scan state inferred from recent events."""
    authenticated_device = request.hardware_device
    current_user_id = getattr(authenticated_device, 'user_id', None)
    target_device_id = None
    device_param = request.args.get('device_id')
    if device_param is not None:
        try:
            target_device_id = int(device_param)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid device_id'}), 400
        target_device = models.HardwareDevice.query.filter_by(
            id=target_device_id,
            user_id=current_user_id,
        ).first()
        if target_device is None:
            return jsonify({'error': 'Device not found'}), 404
    elif current_user_id is None:
        # Legacy unowned credentials must not see every other unowned device.
        target_device_id = authenticated_device.id
    try:
        window_seconds = max(1, min(int(request.args.get('window_seconds', 20)), 300))
    except (ValueError, TypeError):
        window_seconds = 20

    device_payload = serialize_hardware_device(authenticated_device)

    cutoff = utc_now_naive() - datetime.timedelta(seconds=window_seconds)
    query = models.HardwareEvent.query.filter(
        models.HardwareEvent.created_at >= cutoff,
        models.HardwareEvent.user_id == current_user_id,
    )
    if target_device_id is not None:
        query = query.filter(models.HardwareEvent.device_id == target_device_id)

    try:
        last_event = query.order_by(models.HardwareEvent.created_at.desc()).first()
    except Exception:
        last_event = None

    state = {
        'state': 'waiting',
        'message': 'Ready to receive',
        'last_event': None
    }
    if last_event:
        event_json = serialize_hardware_event(last_event)
        state['last_event'] = event_json
        if last_event.event_type == 'weight_update':
            state['state'] = 'uploaded'
            state['message'] = 'Weight uploaded and matched' if last_event.spool_id else 'Weight uploaded'
            try:
                stable_query = models.HardwareEvent.query.filter(
                    models.HardwareEvent.event_type == 'stable_weight',
                    models.HardwareEvent.device_id == last_event.device_id,
                    models.HardwareEvent.user_id == current_user_id,
                    models.HardwareEvent.created_at <= last_event.created_at,
                )
                if last_event.nfc_tag_id is not None:
                    stable_query = stable_query.filter(
                        models.HardwareEvent.nfc_tag_id == last_event.nfc_tag_id
                    )
                stable_evt = stable_query.order_by(
                    models.HardwareEvent.created_at.desc()
                ).first()
            except Exception:
                stable_evt = None
            gross = float(getattr(stable_evt, 'weight', 0) or 0) if stable_evt else None
            net = float(getattr(last_event, 'weight', 0) or 0) if last_event else None
            if gross is not None and gross > 0:
                state['gross_weight'] = gross
            if net is not None and net >= 0:
                state['net_weight'] = net
            if gross is not None and net is not None and gross >= net:
                state['tare_applied'] = round(gross - net, 3)
        elif last_event.event_type == 'orphan':
            state['state'] = 'uploaded'
            state['message'] = 'Uploaded, tag not linked (orphan)'
            try:
                stable_query = models.HardwareEvent.query.filter(
                    models.HardwareEvent.event_type == 'stable_weight',
                    models.HardwareEvent.device_id == last_event.device_id,
                    models.HardwareEvent.user_id == current_user_id,
                )
                if last_event.nfc_tag_id is not None:
                    stable_query = stable_query.filter(
                        models.HardwareEvent.nfc_tag_id == last_event.nfc_tag_id
                    )
                stable_evt = stable_query.order_by(
                    models.HardwareEvent.created_at.desc()
                ).first()
                if stable_evt and getattr(stable_evt, 'weight', None) is not None:
                    state['gross_weight'] = float(stable_evt.weight or 0)
            except Exception:
                pass
        elif last_event.event_type == 'scan_start':
            state['state'] = 'scan_started'
            state['message'] = 'NFC detected — weighing…'
        elif last_event.event_type == 'weighing':
            state['state'] = 'weighing'
            state['message'] = 'Weighing in progress…'
        elif last_event.event_type == 'stable_weight':
            state['state'] = 'stable'
            try:
                state['message'] = f"Stable weight {float(last_event.weight or 0):.0f} g"
            except Exception:
                state['message'] = 'Stable weight detected'
            try:
                if getattr(last_event, 'weight', None) is not None:
                    state['gross_weight'] = float(last_event.weight or 0)
            except Exception:
                pass
        elif last_event.event_type == 'error':
            state['state'] = 'error'
            state['message'] = last_event.message or 'Measurement error'
        elif last_event.event_type in ('ready', 'ready_to_weigh'):
            state['state'] = 'ready'
            state['message'] = 'Connected, ready to weigh'
        elif last_event.event_type in ('waiting_clear', 'waiting_removal'):
            state['state'] = 'waiting_removal'
            state['message'] = 'Unstable/too low — please remove and try again'

    state['device'] = device_payload
    state['connection_state'] = device_payload.get('connection_state')
    return jsonify(state)


@hardware_comms_bp.route('/hardware/display/cards', methods=['GET'])
@hardware_auth_required
def display_cards():
    """Aggregate data for the CYD display carousel."""
    device = request.hardware_device
    user_id = getattr(device, 'user_id', None)

    if not user_id:
        return jsonify({'cards': [
            {'type': 'status', 'data': {'server': 'ok', 'server_time': utc_now_iso(), 'device': serialize_hardware_device(device)}},
        ]})

    total_spools = models.FilamentSpool.query.filter_by(user_id=user_id).count()
    active_spools = models.FilamentSpool.query.filter_by(user_id=user_id, is_active=True).count()
    empty_spools = models.FilamentSpool.query.filter_by(user_id=user_id, is_empty=True).count()
    low_stock_spools = models.FilamentSpool.query.filter(
        models.FilamentSpool.user_id == user_id,
        models.FilamentSpool.weight_remaining <= models.FilamentSpool.low_stock_threshold,
        models.FilamentSpool.is_empty == False
    ).count()

    today_events = 0
    try:
        today_start = datetime.datetime.combine(utc_now_naive().date(), datetime.time.min)
        today_events = models.HardwareEvent.query.filter(
            models.HardwareEvent.user_id == user_id,
            models.HardwareEvent.created_at >= today_start
        ).count()
    except Exception:
        today_events = 0

    dashboard = {
        'type': 'dashboard',
        'data': {
            'total_spools': total_spools,
            'in_use': max(0, active_spools - empty_spools),
            'empty': empty_spools,
            'low_stock': low_stock_spools,
            'today_scans': today_events
        }
    }

    try:
        recent_events = (
            models.HardwareEvent.query
            .filter(models.HardwareEvent.user_id == user_id)
            .order_by(models.HardwareEvent.created_at.desc())
            .limit(8)
            .all()
        )
    except Exception:
        recent_events = []
    recent_spools_by_event = event_spools(recent_events)
    recent_activity = {
        'type': 'recent_activity',
        'data': [
            serialize_hardware_event(event, recent_spools_by_event.get(event.id))
            for event in recent_events
        ]
    }

    low_spools = (
        models.FilamentSpool.query
        .filter(
            models.FilamentSpool.user_id == user_id,
            models.FilamentSpool.is_empty == False,
            models.FilamentSpool.low_stock_threshold.isnot(None),
            models.FilamentSpool.weight_remaining <= models.FilamentSpool.low_stock_threshold
        )
        .order_by(models.FilamentSpool.weight_remaining.asc())
        .limit(8)
        .all()
    )

    def spool_summary(s):
        return {
            'id': s.id,
            'material': getattr(s.material, 'name', None) if hasattr(s, 'material') else None,
            'color': getattr(s.color, 'name', None) if hasattr(s, 'color') else None,
            'manufacturer': getattr(s.manufacturer, 'name', None) if hasattr(s, 'manufacturer') else None,
            'weight_remaining': s.weight_remaining,
            'low_stock_threshold': s.low_stock_threshold
        }

    buy_soon = {
        'type': 'buy_soon',
        'data': [spool_summary(s) for s in low_spools]
    }

    inv_spools = (
        models.FilamentSpool.query
        .filter(models.FilamentSpool.user_id == user_id)
        .order_by(models.FilamentSpool.is_empty.asc(), models.FilamentSpool.weight_remaining.desc())
        .limit(12)
        .all()
    )
    inventory = {
        'type': 'inventory',
        'data': [spool_summary(s) for s in inv_spools]
    }

    status = {
        'type': 'status',
        'data': {
            'server': 'ok',
            'server_time': utc_now_iso(),
            'device': serialize_hardware_device(device)
        }
    }

    return jsonify({'cards': [dashboard, recent_activity, buy_soon, inventory, status]})


@hardware_comms_bp.route('/hardware/event', methods=['POST'])
@hardware_auth_required
def hardware_event():
    """Allow hardware devices to log ephemeral events (scan_start, weighing, stable_weight)."""
    data = json_object()
    if data is None:
        return jsonify({'error': 'JSON object required'}), 400
    event_type_value = data.get('event_type')
    event_type = event_type_value.strip() if isinstance(event_type_value, str) else ''
    if not event_type:
        return jsonify({'error': 'event_type is required'}), 400
    nfc_tag_value = data.get('nfc_tag_id')
    message_value = data.get('message')
    if nfc_tag_value is not None and not isinstance(nfc_tag_value, str):
        return jsonify({'error': 'nfc_tag_id must be text'}), 400
    if message_value is not None and not isinstance(message_value, str):
        return jsonify({'error': 'message must be text'}), 400
    nfc_tag_id = (
        nfc_tag_value.strip() or None
        if isinstance(nfc_tag_value, str)
        else None
    )
    message = (
        message_value.strip() or None
        if isinstance(message_value, str)
        else None
    )
    weight_val = data.get('weight')
    try:
        weight = float(weight_val) if weight_val is not None else None
    except (ValueError, TypeError):
        return jsonify({'error': 'weight must be a finite number'}), 400
    if weight is not None and not math.isfinite(weight):
        return jsonify({'error': 'weight must be a finite number'}), 400

    spool = None
    if nfc_tag_id:
        spool = models.FilamentSpool.query.filter_by(
            nfc_tag_id=nfc_tag_id,
            user_id=getattr(request.hardware_device, 'user_id', None),
        ).first()

    evt = models.HardwareEvent(
        device_id=request.hardware_device.id,
        user_id=getattr(request.hardware_device, 'user_id', None),
        event_type=event_type,
        nfc_tag_id=nfc_tag_id,
        spool_id=(spool.id if spool else None),
        weight=weight,
        message=message
    )
    db.session.add(evt)
    db.session.commit()
    return jsonify({'event': serialize_hardware_event(evt)})
