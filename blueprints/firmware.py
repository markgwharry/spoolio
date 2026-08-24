"""Hardware-facing firmware endpoints."""

import os

from flask import Blueprint, jsonify, request, current_app, send_file, url_for

from extensions import db
import models
from blueprints._helpers import (
    firmware_ota_required,
    hardware_auth_required,
    get_firmware_upload_folder,
    verify_firmware_download_token,
    serialize_firmware_release,
)

firmware_bp = Blueprint('firmware', __name__)


@firmware_bp.route('/hardware/firmware/latest', methods=['GET'])
@firmware_ota_required
@hardware_auth_required
def hardware_latest_firmware():
    """Return metadata for the latest active firmware release for this device."""
    device = request.hardware_device
    hardware_type = request.args.get('hardware_type') or getattr(device, 'hardware_type', None)
    if not hardware_type:
        return jsonify({'error': 'hardware_type is required'}), 400

    release = (
        models.FirmwareRelease.query
        .filter_by(hardware_type=hardware_type, is_active=True)
        .order_by(models.FirmwareRelease.created_at.desc())
        .first()
    )

    poll_after = int(current_app.config.get('FIRMWARE_POLL_INTERVAL_SECONDS', 300))

    if not release:
        return jsonify({
            'release': None,
            'poll_after_seconds': poll_after,
            'hardware_type': hardware_type
        })

    return jsonify({
        'release': serialize_firmware_release(release, include_signed_url=True),
        'poll_after_seconds': poll_after,
        'hardware_type': hardware_type,
    })


@firmware_bp.route('/hardware/firmware/download/<int:release_id>', methods=['GET'])
@firmware_ota_required
def download_firmware_binary(release_id):
    """Serve a firmware binary when provided with a valid signed token."""
    token = request.args.get('token')
    if not verify_firmware_download_token(token, release_id):
        return jsonify({'error': 'Invalid or expired download token'}), 403

    release = db.session.get(models.FirmwareRelease, release_id)
    if not release:
        return jsonify({'error': 'Firmware release not found'}), 404

    firmware_path = os.path.join(get_firmware_upload_folder(), release.file_name)
    if not os.path.exists(firmware_path):
        return jsonify({'error': 'Firmware binary unavailable'}), 404

    try:
        response = send_file(
            firmware_path,
            as_attachment=True,
            download_name=release.original_filename or os.path.basename(release.file_name)
        )
    except Exception:
        current_app.logger.exception('Failed to stream firmware binary %s', firmware_path)
        return jsonify({'error': 'Failed to stream firmware binary'}), 500

    response.headers['X-Firmware-Version'] = release.version
    response.headers['X-Firmware-Checksum'] = release.checksum
    response.headers['X-Firmware-Hardware-Type'] = release.hardware_type
    response.headers['Cache-Control'] = 'no-store'
    return response
