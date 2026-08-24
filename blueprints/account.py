"""Account management routes."""

import os
import uuid

from flask import Blueprint, jsonify, request, current_app, send_from_directory
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from PIL import Image, ImageOps, UnidentifiedImageError

from extensions import db
import models
from blueprints._helpers import (
    get_current_user,
    validate_email,
    validate_password,
    allowed_profile_image,
    get_profile_image_folder,
    serialize_account,
    limiter,
)
from email_service import send_email_verification

account_bp = Blueprint('account', __name__)


@account_bp.route('/account', methods=['GET'])
@jwt_required()
def get_account_details():
    user = get_current_user()
    if not user:
        return jsonify({'msg': 'User not found'}), 404
    return jsonify({'user': serialize_account(user)})


@account_bp.route('/account/email', methods=['PATCH'])
@limiter.limit("5 per minute")
@jwt_required()
def update_account_email():
    user = get_current_user()
    if not user:
        return jsonify({'msg': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    email_value = data.get('email')
    new_email = email_value.strip() if isinstance(email_value, str) else ''
    password_value = data.get('current_password')
    current_password = password_value if isinstance(password_value, str) else ''

    if not new_email or not current_password:
        return jsonify({'msg': 'Email and current password are required'}), 400

    if not validate_email(new_email):
        return jsonify({'msg': 'Invalid email format'}), 400

    if not user.check_password(current_password):
        return jsonify({'msg': 'Current password is incorrect'}), 403

    if new_email.lower() == user.email.lower():
        return jsonify({
            'msg': 'Email address is unchanged.',
            'user': serialize_account(user)
        })

    existing = models.User.query.filter(
        db.func.lower(models.User.email) == new_email.lower(),
        models.User.id != user.id
    ).first()
    if existing:
        return jsonify({'msg': 'Email already in use'}), 409

    user.email = new_email
    user.email_verified = False
    verification_token = user.generate_email_verification_token()

    try:
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to update email')
        db.session.rollback()
        return jsonify({'msg': 'Failed to update email'}), 500

    base_override_value = data.get('verification_base_url')
    base_override = base_override_value.strip() if isinstance(base_override_value, str) else ''
    if base_override:
        base_url = base_override.rstrip('/')
    else:
        base_url = (request.host_url or '').rstrip('/')
    verification_url = f"{base_url}/verify-email/{verification_token}" if base_url else f"/verify-email/{verification_token}"
    verification_sent = send_email_verification(user, verification_url)

    return jsonify({
        'msg': 'Email updated. Verification required for the new address.',
        'verification_email_sent': verification_sent,
        'user': serialize_account(user)
    })


@account_bp.route('/account/password', methods=['PATCH'])
@limiter.limit("5 per minute")
@jwt_required()
def update_account_password():
    user = get_current_user()
    if not user:
        return jsonify({'msg': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    current_password_value = data.get('current_password')
    new_password_value = data.get('new_password')
    current_password = current_password_value if isinstance(current_password_value, str) else ''
    new_password = new_password_value if isinstance(new_password_value, str) else ''

    if not current_password or not new_password:
        return jsonify({'msg': 'Current and new passwords are required'}), 400

    if not user.check_password(current_password):
        return jsonify({'msg': 'Current password is incorrect'}), 403

    if new_password == current_password:
        return jsonify({'msg': 'New password must be different from the current password'}), 400

    pw_valid, pw_error = validate_password(new_password)
    if not pw_valid:
        return jsonify({'msg': pw_error}), 400

    user.set_password(new_password)
    user.clear_password_reset_token()
    user.token_version = int(user.token_version or 0) + 1

    try:
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to update password')
        db.session.rollback()
        return jsonify({'msg': 'Failed to update password'}), 500

    claims = {'ver': int(user.token_version or 0)}
    return jsonify({
        'msg': 'Password updated successfully',
        'access_token': create_access_token(
            identity=str(user.id),
            additional_claims=claims,
        ),
        'refresh_token': create_refresh_token(
            identity=str(user.id),
            additional_claims=claims,
        ),
        'user': serialize_account(user),
    })


@account_bp.route('/account/profile-image', methods=['POST'])
@jwt_required()
def upload_profile_image():
    user = get_current_user()
    if not user:
        return jsonify({'msg': 'User not found'}), 404

    if 'image' not in request.files:
        return jsonify({'msg': 'No image uploaded'}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'msg': 'No image uploaded'}), 400

    if not allowed_profile_image(file.filename):
        return jsonify({'msg': 'Unsupported file type'}), 400

    extension = file.filename.rsplit('.', 1)[1].lower()
    generated_name = secure_filename(f"user_{user.id}_{uuid.uuid4().hex}.{extension}")
    folder = get_profile_image_folder()
    file_path = os.path.join(folder, generated_name)
    temporary_path = f"{file_path}.tmp"
    image_format = {
        'jpg': 'JPEG',
        'jpeg': 'JPEG',
        'png': 'PNG',
        'gif': 'GIF',
        'webp': 'WEBP',
    }[extension]

    try:
        with Image.open(file.stream) as candidate:
            candidate.verify()
        file.stream.seek(0)
        with Image.open(file.stream) as source:
            source.load()
            clean = ImageOps.exif_transpose(source)
            if image_format == 'JPEG' and clean.mode not in {'RGB', 'L'}:
                clean = clean.convert('RGB')
            clean.save(temporary_path, format=image_format)
        os.replace(temporary_path, file_path)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        return jsonify({'msg': 'Invalid image file'}), 400
    except Exception:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        current_app.logger.exception('Failed to process profile image')
        return jsonify({'msg': 'Failed to save profile image'}), 500

    previous_filename = user.profile_image_filename
    user.profile_image_filename = generated_name

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            os.remove(file_path)
        except OSError:
            pass
        current_app.logger.exception('Failed to update profile image')
        return jsonify({'msg': 'Failed to update profile image'}), 500

    if previous_filename:
        old_path = os.path.join(folder, os.path.basename(previous_filename))
        try:
            if os.path.exists(old_path):
                os.remove(old_path)
        except OSError:
            current_app.logger.warning('Failed to remove previous profile image', exc_info=True)

    return jsonify({
        'msg': 'Profile image updated',
        'user': serialize_account(user)
    })


@account_bp.route('/account/profile-image', methods=['DELETE'])
@jwt_required()
def delete_profile_image():
    user = get_current_user()
    if not user:
        return jsonify({'msg': 'User not found'}), 404

    if not user.profile_image_filename:
        return jsonify({'msg': 'No profile image to remove'}), 400

    folder = get_profile_image_folder()
    filename = os.path.basename(user.profile_image_filename)
    user.profile_image_filename = None

    try:
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to remove profile image')
        db.session.rollback()
        return jsonify({'msg': 'Failed to remove profile image'}), 500

    image_path = os.path.join(folder, filename)
    try:
        if os.path.exists(image_path):
            os.remove(image_path)
    except OSError:
        current_app.logger.warning('Failed to delete profile image file', exc_info=True)

    return jsonify({
        'msg': 'Profile image removed',
        'user': serialize_account(user)
    })


@account_bp.route('/account', methods=['DELETE'])
@jwt_required()
def delete_account():
    user = get_current_user()
    if not user:
        return jsonify({'msg': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    current_password_value = data.get('current_password')
    current_password = current_password_value if isinstance(current_password_value, str) else ''
    confirm = data.get('confirm', False)

    if not current_password:
        return jsonify({'msg': 'Current password is required to delete the account'}), 400

    if not user.check_password(current_password):
        return jsonify({'msg': 'Current password is incorrect'}), 403

    if confirm is not True:
        return jsonify({'msg': 'Account deletion not confirmed. Set "confirm" to true to proceed.'}), 400

    profile_filename = user.profile_image_filename

    try:
        spools = models.FilamentSpool.query.filter_by(user_id=user.id).all()
        spool_ids = [spool.id for spool in spools]
        project_ids = [
            row[0]
            for row in db.session.query(models.Project.id).filter_by(user_id=user.id).all()
        ]
        device_ids = [
            row[0]
            for row in db.session.query(models.HardwareDevice.id).filter_by(user_id=user.id).all()
        ]
        bit_ids = [
            row[0]
            for row in db.session.query(models.Bit.id).filter_by(user_id=user.id).all()
        ]

        empty_query = db.session.query(models.EmptySpool)
        if spool_ids:
            empty_query = empty_query.filter(
                or_(
                    models.EmptySpool.user_id == user.id,
                    models.EmptySpool.origin_spool_id.in_(spool_ids)
                )
            )
        else:
            empty_query = empty_query.filter(models.EmptySpool.user_id == user.id)
        empty_query.delete(synchronize_session=False)

        db.session.query(models.FilamentRefill).filter_by(user_id=user.id).delete(synchronize_session=False)

        if bit_ids:
            db.session.query(models.BitUsage).filter(
                models.BitUsage.bit_id.in_(bit_ids)
            ).delete(
                synchronize_session=False
            )
        if project_ids:
            db.session.query(models.BitUsage).filter(
                models.BitUsage.project_id.in_(project_ids)
            ).update({models.BitUsage.project_id: None}, synchronize_session=False)
        db.session.query(models.Bit).filter_by(user_id=user.id).delete(synchronize_session=False)

        if spool_ids:
            db.session.query(models.SpoolHistory).filter(
                models.SpoolHistory.spool_id.in_(spool_ids)
            ).delete(synchronize_session=False)
        if project_ids:
            db.session.query(models.SpoolHistory).filter(
                models.SpoolHistory.project_id.in_(project_ids)
            ).update({models.SpoolHistory.project_id: None}, synchronize_session=False)

        event_filters = [models.HardwareEvent.user_id == user.id]
        if spool_ids:
            event_filters.append(models.HardwareEvent.spool_id.in_(spool_ids))
        if device_ids:
            event_filters.append(models.HardwareEvent.device_id.in_(device_ids))
        db.session.query(models.HardwareEvent).filter(or_(*event_filters)).delete(
            synchronize_session=False
        )

        orphan_filters = [models.OrphanTag.user_id == user.id]
        if device_ids:
            orphan_filters.append(models.OrphanTag.hardware_device_id.in_(device_ids))
        db.session.query(models.OrphanTag).filter(or_(*orphan_filters)).delete(
            synchronize_session=False
        )

        if device_ids:
            linked_spools = db.session.query(models.FilamentSpool).filter(
                models.FilamentSpool.hardware_device_id.in_(device_ids)
            )
            if spool_ids:
                linked_spools = linked_spools.filter(
                    ~models.FilamentSpool.id.in_(spool_ids)
                )
            linked_spools.update(
                {models.FilamentSpool.hardware_device_id: None},
                synchronize_session=False,
            )

        if spool_ids:
            db.session.query(models.FilamentSpool).filter(
                models.FilamentSpool.id.in_(spool_ids)
            ).delete(synchronize_session=False)

        db.session.query(models.FilamentGroup).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.session.query(models.Project).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.session.query(models.HardwareDevice).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.session.query(models.FirmwareRelease).filter_by(created_by=user.id).update(
            {models.FirmwareRelease.created_by: None},
            synchronize_session=False,
        )

        db.session.delete(user)
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to delete account')
        db.session.rollback()
        return jsonify({'msg': 'Failed to delete account'}), 500

    if profile_filename:
        folder = get_profile_image_folder()
        profile_path = os.path.join(folder, os.path.basename(profile_filename))
        try:
            if os.path.exists(profile_path):
                os.remove(profile_path)
        except OSError:
            current_app.logger.warning('Failed to remove profile image after account deletion', exc_info=True)

    return jsonify({'msg': 'Account deleted successfully'})


@account_bp.route('/account/profile-image/<path:filename>', methods=['GET'])
def serve_profile_image(filename):
    safe_name = os.path.basename(filename)
    if not safe_name:
        return jsonify({'msg': 'Image not found'}), 404

    user = models.User.query.filter_by(profile_image_filename=safe_name).first()
    if not user:
        return jsonify({'msg': 'Image not found'}), 404

    folder = get_profile_image_folder()
    return send_from_directory(folder, safe_name)
