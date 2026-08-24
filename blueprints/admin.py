"""Admin routes: dashboard stats, metadata, firmware CRUD."""

import os
import uuid
import hashlib

from flask import Blueprint, jsonify, request, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from extensions import db
import models
from email_service import send_firmware_release_notification
from blueprints._helpers import (
    admin_required,
    firmware_ota_required,
    get_current_user,
    json_object,
    get_firmware_upload_folder,
    allowed_firmware_file,
    serialize_firmware_release,
    generate_firmware_download_url,
    _email_download_token_expiry,
)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard/stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """Get dashboard statistics for mobile app."""
    user_id = get_jwt_identity()

    total_spools = models.FilamentSpool.query.filter_by(user_id=user_id).count()
    active_spools = models.FilamentSpool.query.filter_by(user_id=user_id, is_active=True).count()
    empty_spools = models.FilamentSpool.query.filter_by(user_id=user_id, is_empty=True).count()
    low_stock_spools = models.FilamentSpool.query.filter(
        models.FilamentSpool.user_id == user_id,
        models.FilamentSpool.weight_remaining <= models.FilamentSpool.low_stock_threshold,
        models.FilamentSpool.is_empty == False
    ).count()

    total_weight = db.session.query(db.func.sum(models.FilamentSpool.weight_remaining)).filter_by(user_id=user_id).scalar() or 0

    return jsonify({
        'total_spools': total_spools,
        'active_spools': active_spools,
        'empty_spools': empty_spools,
        'low_stock_spools': low_stock_spools,
        'total_weight_remaining': total_weight
    })


@admin_bp.route('/admin/metadata', methods=['GET'])
@admin_required
def get_admin_metadata():
    """Aggregate admin metadata for management UI."""
    user_id = get_jwt_identity()

    spool_type_rows = (
        db.session.query(models.SpoolType, db.func.count(models.FilamentSpool.id))
        .outerjoin(
            models.FilamentSpool,
            models.FilamentSpool.spool_type_id == models.SpoolType.id,
        )
        .group_by(models.SpoolType.id)
        .all()
    )
    spool_types = [
        {
            'id': st.id,
            'name': st.name,
            'compatible_with_ams': st.compatible_with_ams,
            'tare_weight': getattr(st, 'tare_weight', 0) or 0,
            'num_spools': int(count or 0),
        }
        for st, count in spool_type_rows
    ]

    manufacturer_rows = (
        db.session.query(models.Manufacturer, db.func.count(models.FilamentSpool.id))
        .outerjoin(
            models.FilamentSpool,
            models.FilamentSpool.manufacturer_id == models.Manufacturer.id,
        )
        .group_by(models.Manufacturer.id)
        .all()
    )
    manufacturers = [
        {
            'id': m.id,
            'name': m.name,
            'num_spools': int(count or 0),
        }
        for m, count in manufacturer_rows
    ]

    subtype_rows = (
        db.session.query(models.FilamentSpool.subtype, db.func.count(models.FilamentSpool.id))
        .filter(
            models.FilamentSpool.user_id == user_id,
            models.FilamentSpool.subtype.isnot(None),
            models.FilamentSpool.subtype != ''
        )
        .group_by(models.FilamentSpool.subtype)
        .all()
    )
    subtypes = [
        {'name': name, 'num_spools': int(count or 0)}
        for (name, count) in subtype_rows
    ]

    return jsonify({
        'spool_types': spool_types,
        'manufacturers': manufacturers,
        'subtypes': subtypes,
        'features': {
            'firmware_ota': bool(current_app.config.get('FIRMWARE_OTA_ENABLED', False)),
        },
    })


@admin_bp.route('/admin/firmware', methods=['GET'])
@firmware_ota_required
@admin_required
def list_firmware_releases():
    """Return all firmware releases for administrative review."""
    releases = (
        models.FirmwareRelease.query
        .order_by(models.FirmwareRelease.created_at.desc())
        .all()
    )
    return jsonify({'releases': [serialize_firmware_release(r, include_signed_url=True) for r in releases]})


@admin_bp.route('/admin/firmware', methods=['POST'])
@firmware_ota_required
@admin_required
def create_firmware_release():
    """Upload a firmware binary and create a release entry."""
    form = request.form or {}
    version = (form.get('version') or '').strip()
    hardware_type = (form.get('hardware_type') or '').strip()
    release_notes = form.get('release_notes')
    manual_instructions = form.get('manual_instructions')
    activate_flag = str(form.get('is_active', '')).lower() in {'1', 'true', 'yes', 'on'}

    firmware_file = request.files.get('binary') or request.files.get('file')

    if not version or not hardware_type:
        return jsonify({'error': 'Version and hardware_type are required'}), 400

    if not firmware_file or not firmware_file.filename:
        return jsonify({'error': 'Firmware binary is required'}), 400

    if not allowed_firmware_file(firmware_file.filename):
        return jsonify({'error': 'Unsupported firmware file type'}), 400

    upload_folder = get_firmware_upload_folder()
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(firmware_file.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    path = os.path.join(upload_folder, unique_name)

    checksum_hash = hashlib.sha256()
    total_size = 0
    try:
        firmware_file.stream.seek(0)
        with open(path, 'wb') as fh:
            while True:
                chunk = firmware_file.stream.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                checksum_hash.update(chunk)
                total_size += len(chunk)
        firmware_file.stream.seek(0)
    except Exception:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                current_app.logger.exception('Failed to clean up firmware upload %s', path)
        current_app.logger.exception('Failed to write firmware binary to disk')
        return jsonify({'error': 'Failed to store firmware binary'}), 500

    release = models.FirmwareRelease(
        version=version,
        hardware_type=hardware_type,
        file_name=unique_name,
        original_filename=filename,
        file_size=total_size,
        checksum=checksum_hash.hexdigest(),
        release_notes=release_notes,
        manual_instructions=manual_instructions,
        is_active=activate_flag,
        created_by=getattr(get_current_user(), 'id', None),
    )

    try:
        db.session.add(release)
        db.session.flush()
        release.download_url = url_for('firmware.download_firmware_binary', release_id=release.id)
        if release.is_active:
            siblings = models.FirmwareRelease.query.filter(
                models.FirmwareRelease.hardware_type == release.hardware_type,
                models.FirmwareRelease.id != release.id
            ).all()
            for sibling in siblings:
                if sibling.is_active:
                    sibling.is_active = False
        db.session.commit()
    except Exception:
        db.session.rollback()
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                current_app.logger.exception('Failed to remove firmware file after DB rollback: %s', path)
        current_app.logger.exception('Failed to create firmware release entry')
        return jsonify({'error': 'Unable to create firmware release'}), 500

    return jsonify({'release': serialize_firmware_release(release, include_signed_url=True)}), 201


@admin_bp.route('/admin/firmware/<int:release_id>', methods=['PATCH'])
@firmware_ota_required
@admin_required
def update_firmware_release(release_id):
    """Update release metadata (notes, instructions, activation state)."""
    release = db.session.get(models.FirmwareRelease, release_id)
    if not release:
        return jsonify({'error': 'Firmware release not found'}), 404

    data = json_object()
    if data is None:
        return jsonify({'error': 'JSON object required'}), 400
    updated = False

    if 'version' in data:
        version_value = data.get('version')
        if version_value is not None and not isinstance(version_value, str):
            return jsonify({'error': 'version must be text'}), 400
        version = version_value.strip() if isinstance(version_value, str) else ''
        if version:
            release.version = version
            updated = True

    if 'release_notes' in data:
        if (
            data.get('release_notes') is not None
            and not isinstance(data.get('release_notes'), str)
        ):
            return jsonify({'error': 'release_notes must be text'}), 400
        release.release_notes = data.get('release_notes')
        updated = True

    if 'manual_instructions' in data:
        if (
            data.get('manual_instructions') is not None
            and not isinstance(data.get('manual_instructions'), str)
        ):
            return jsonify({'error': 'manual_instructions must be text'}), 400
        release.manual_instructions = data.get('manual_instructions')
        updated = True

    if 'is_active' in data:
        if not isinstance(data.get('is_active'), bool):
            return jsonify({'error': 'is_active must be a boolean'}), 400
        desired_active = data.get('is_active')
        if desired_active and not release.is_active:
            siblings = models.FirmwareRelease.query.filter(
                models.FirmwareRelease.hardware_type == release.hardware_type,
                models.FirmwareRelease.id != release.id
            ).all()
            for sibling in siblings:
                if sibling.is_active:
                    sibling.is_active = False
        release.is_active = desired_active
        updated = True

    if updated:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed to update firmware release %s', release_id)
            return jsonify({'error': 'Unable to update firmware release'}), 500

    return jsonify({'release': serialize_firmware_release(release, include_signed_url=True)})


@admin_bp.route('/admin/firmware/<int:release_id>/activate', methods=['POST'])
@firmware_ota_required
@admin_required
def activate_firmware_release(release_id):
    """Mark a firmware release as active for its hardware type."""
    release = db.session.get(models.FirmwareRelease, release_id)
    if not release:
        return jsonify({'error': 'Firmware release not found'}), 404

    try:
        release.is_active = True
        siblings = models.FirmwareRelease.query.filter(
            models.FirmwareRelease.hardware_type == release.hardware_type,
            models.FirmwareRelease.id != release.id
        ).all()
        for sibling in siblings:
            if sibling.is_active:
                sibling.is_active = False
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to activate firmware release %s', release_id)
        return jsonify({'error': 'Unable to activate firmware release'}), 500

    return jsonify({'release': serialize_firmware_release(release, include_signed_url=True)})


@admin_bp.route('/admin/firmware/<int:release_id>/notify', methods=['POST'])
@firmware_ota_required
@admin_required
def notify_firmware_release(release_id):
    """Email owners of matching hardware about an available firmware release."""
    release = db.session.get(models.FirmwareRelease, release_id)
    if not release:
        return jsonify({'error': 'Firmware release not found'}), 404

    payload = json_object()
    if payload is None:
        return jsonify({'error': 'JSON object required'}), 400
    extra_message = payload.get('message')
    if extra_message is not None and not isinstance(extra_message, str):
        return jsonify({'error': 'message must be text'}), 400

    recipients_query = (
        db.session.query(models.User)
        .join(models.HardwareDevice, models.HardwareDevice.user_id == models.User.id)
        .filter(models.HardwareDevice.hardware_type == release.hardware_type)
        .filter(models.User.email_verified.is_(True))
        .distinct()
    )
    recipients = recipients_query.all()

    sent = 0
    long_lived_expiry = _email_download_token_expiry()
    download_url = generate_firmware_download_url(
        release,
        expires=long_lived_expiry,
        external=True,
    )
    for user in recipients:
        try:
            if send_firmware_release_notification(
                user,
                release,
                download_url,
                manual_instructions=release.manual_instructions,
                extra_message=extra_message,
            ):
                sent += 1
        except Exception:
            current_app.logger.exception('Failed to notify %s about firmware release %s', user.email, release_id)

    return jsonify({
        'release': serialize_firmware_release(release, include_signed_url=True),
        'notified': sent,
        'requested': len(recipients),
        'recipient_count': len(recipients),
    })
