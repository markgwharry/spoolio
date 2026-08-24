"""Authentication and registration routes."""

import json
import datetime
import secrets

from flask import Blueprint, jsonify, request, current_app, g
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from extensions import db
import models
from email_service import (
    send_email_verification,
    send_password_reset,
    send_waitlist_confirmation,
    send_waitlist_notification,
)
from blueprints._helpers import (
    jwt,
    limiter,
    validate_email,
    validate_username,
    validate_password,
    get_current_user,
    serialize_user,
)

auth_bp = Blueprint('auth', __name__)
WAITLIST_ACCEPTED_MESSAGE = (
    'Thanks for your interest in Spoolio. If this address can be added to the '
    'waitlist, we will be in touch.'
)


def _waitlist_accepted_response():
    """Return the same response for new, repeated, and existing-account emails."""
    return jsonify({
        'msg': WAITLIST_ACCEPTED_MESSAGE,
        'waitlisted': True,
    }), 202


def _token_claims(user):
    return {'ver': int(getattr(user, 'token_version', 0) or 0)}


def _registration_action():
    """Return the public action currently offered by /api/register."""
    mode = current_app.config['REGISTRATION_MODE']
    if mode == 'waitlist':
        return 'waitlist'
    if mode == 'closed':
        return 'closed'
    claimed = db.session.get(models.RegistrationBootstrap, 1)
    if claimed is not None or models.User.query.first() is not None:
        return 'closed'
    return 'create-owner'


def _registration_status():
    action = _registration_action()
    return {
        'mode': current_app.config['REGISTRATION_MODE'],
        'action': action,
        'registration_enabled': action == 'create-owner',
        'waitlist_enabled': action == 'waitlist',
        'password_required': action == 'create-owner',
        'setup_code_required': action == 'create-owner',
    }


def _registration_closed_response(status_code=403):
    return jsonify({
        'msg': 'Registration is closed. Ask the server owner for access.',
        **_registration_status(),
    }), status_code


@auth_bp.route('/registration', methods=['GET'])
def registration_status():
    """Describe onboarding without exposing account or waitlist membership."""
    return jsonify(_registration_status())


@jwt.token_in_blocklist_loader
def token_version_mismatch(_jwt_header, jwt_payload):
    """Revoke tokens whose version no longer matches the persisted user."""
    identity = jwt_payload.get('sub')
    try:
        user_id = int(identity)
        token_version = int(jwt_payload.get('ver', 0) or 0)
    except (TypeError, ValueError):
        return True
    user = db.session.get(models.User, user_id)
    if user is None or token_version != int(user.token_version or 0):
        return True
    g.jwt_user = user
    return False


@jwt.revoked_token_loader
def revoked_token_response(_jwt_header, _jwt_payload):
    return jsonify({'msg': 'Token has been revoked'}), 401


@auth_bp.record_once
def setup_jwt(state):
    app = state.app
    app.config.setdefault('JWT_ACCESS_TOKEN_EXPIRES', datetime.timedelta(minutes=15))
    app.config.setdefault('JWT_REFRESH_TOKEN_EXPIRES', datetime.timedelta(days=30))
    jwt.init_app(app)
    limiter.init_app(app)


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    mode = current_app.config['REGISTRATION_MODE']
    if mode == 'closed':
        return _registration_closed_response()
    if mode == 'first-user':
        if db.session.get(models.RegistrationBootstrap, 1) is not None:
            return _registration_closed_response()
        # End the read transaction before competing for the singleton INSERT.
        # Concurrent unclaimed requests still race only on the primary key.
        db.session.rollback()
    # The singleton INSERT remains the atomic check. We deliberately do not
    # pre-query the user table, and the claim lookup transaction above has been
    # closed before SQLite competes for the write.
    action = 'waitlist' if mode == 'waitlist' else 'create-owner'

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    username_value = data.get('username')
    email_value = data.get('email')
    username = username_value.strip() if isinstance(username_value, str) else ''
    email = email_value.strip() if isinstance(email_value, str) else ''
    password = data.get('password')

    if action == 'create-owner':
        registration_token = data.get('registration_token')
        expected_token = current_app.config['REGISTRATION_TOKEN']
        if (
            not isinstance(registration_token, str)
            or not secrets.compare_digest(registration_token, expected_token)
        ):
            return jsonify({'msg': 'Invalid owner setup code'}), 403

    if not username or not email:
        return jsonify({'msg': 'Missing required fields'}), 400

    if not validate_username(username):
        return jsonify({'msg': 'Username must be 3-20 characters, alphanumeric and underscore only'}), 400

    if not validate_email(email):
        return jsonify({'msg': 'Invalid email format'}), 400

    if password is not None and not isinstance(password, str):
        return jsonify({'msg': 'Password must be text'}), 400

    if action == 'create-owner' and not password:
        return jsonify({'msg': 'Password is required'}), 400

    if password:
        pw_valid, pw_error = validate_password(password)
        if not pw_valid:
            return jsonify({'msg': pw_error}), 400

    if action == 'create-owner':
        # The singleton row is inserted in the same transaction as the owner.
        # Its primary key is the cross-worker/cross-process claim: concurrent
        # requests cannot both create an administrator, even with distinct
        # usernames and email addresses.
        try:
            claim = models.RegistrationBootstrap(id=1)
            db.session.add(claim)
            db.session.flush()

            if models.User.query.first() is not None:
                db.session.commit()
                return _registration_closed_response()

            user = models.User(
                username=username,
                email=email,
                email_verified=True,
                is_admin=True,
            )
            user.set_password(password)
            db.session.add(user)
            existing_waitlist = models.WaitlistEntry.query.filter_by(
                email=email,
            ).first()
            if existing_waitlist is not None:
                db.session.delete(existing_waitlist)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return _registration_closed_response(status_code=409)

        return jsonify({
            'msg': 'Owner account created. You can now log in.',
            'account_created': True,
            'user': serialize_user(user),
        }), 201

    existing_user = models.User.query.filter_by(email=email).first()
    if existing_user:
        return _waitlist_accepted_response()

    existing_waitlist = models.WaitlistEntry.query.filter_by(email=email).first()
    sanitized_payload = {}
    if isinstance(data, dict):
        sanitized_payload = {k: v for k, v in data.items() if k != 'password'}
    if existing_waitlist:
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()
        existing_waitlist.ip_address = ip_address or existing_waitlist.ip_address
        user_agent = request.headers.get('User-Agent')
        if user_agent:
            existing_waitlist.user_agent = user_agent[:512]
        referrer = request.headers.get('Referer') or request.headers.get('Referrer')
        if referrer:
            existing_waitlist.referrer = referrer[:255]
        try:
            existing_waitlist.raw_payload = json.dumps(sanitized_payload)
        except (TypeError, ValueError):
            pass
        db.session.commit()
        return _waitlist_accepted_response()

    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr or '')
    if ip_address:
        ip_address = ip_address.split(',')[0].strip()
    user_agent = request.headers.get('User-Agent')
    referrer = request.headers.get('Referer') or request.headers.get('Referrer')

    try:
        raw_payload = json.dumps(sanitized_payload)
    except (TypeError, ValueError):
        raw_payload = None

    entry = models.WaitlistEntry(
        username=username or None,
        email=email,
        ip_address=ip_address or None,
        user_agent=user_agent[:512] if user_agent else None,
        referrer=referrer[:255] if referrer else None,
        raw_payload=raw_payload
    )

    db.session.add(entry)
    db.session.commit()

    confirmation_sent = send_waitlist_confirmation(entry)
    owner_notified = send_waitlist_notification(entry)

    if not confirmation_sent:
        current_app.logger.warning(
            'Waitlist confirmation email could not be sent for entry %s',
            entry.id,
        )
    if not owner_notified:
        current_app.logger.warning(
            'Waitlist owner notification could not be sent for entry %s',
            entry.id,
        )

    return _waitlist_accepted_response()


@auth_bp.route('/health', methods=['GET'])
def health():
    """Unauthenticated health probe used by external monitors."""
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        current_app.logger.exception('Health check database probe failed')
        return jsonify({
            'status': 'error',
            'checks': {'database': False},
        }), 500
    return jsonify({'status': 'ok', 'checks': {'database': True}})


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'msg': 'Username and password are required'}), 400
    username = data.get('username')
    password = data.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return jsonify({'msg': 'Username and password are required'}), 400
    user = models.User.query.filter_by(username=username).first()
    lockout_expired = False

    if user and user.locked_until:
        now = datetime.datetime.now(datetime.timezone.utc)
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=datetime.timezone.utc)
        if now < locked_until:
            return jsonify({'msg': 'Account temporarily locked due to too many failed attempts. Try again later.'}), 429
        user.failed_login_attempts = 0
        user.locked_until = None
        lockout_expired = True

    if user and user.check_password(password):
        if user.failed_login_attempts > 0 or lockout_expired:
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()

        if not user.email_verified:
            return jsonify({
                'msg': 'Please verify your email address before logging in. Check your email for a verification link.',
                'email_verification_required': True
            }), 401

        claims = _token_claims(user)
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims=claims,
        )
        refresh_token = create_refresh_token(
            identity=str(user.id),
            additional_claims=claims,
        )
        return jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': serialize_user(user)
        })

    if user:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
        db.session.commit()

    return jsonify({'msg': 'Invalid credentials'}), 401


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Exchange a valid refresh token for a new access token."""
    identity = get_jwt_identity()
    user = get_current_user()
    if user is None:
        return jsonify({'msg': 'User not found'}), 404
    new_access_token = create_access_token(
        identity=identity,
        additional_claims=_token_claims(user),
    )
    return jsonify({'access_token': new_access_token})


@auth_bp.route('/logout', methods=['POST'])
@jwt_required(verify_type=False)
def logout():
    """Invalidate every access and refresh token for the current user."""
    user = get_current_user()
    if user is None:
        return jsonify({'msg': 'User not found'}), 404
    user.token_version = int(user.token_version or 0) + 1
    db.session.commit()
    return jsonify({'msg': 'Logged out successfully'})


@auth_bp.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    user_id = get_jwt_identity()
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        pass
    user = db.session.get(models.User, user_id)
    if user:
        return jsonify({'msg': f'Hello, {user.username}! This is a protected endpoint.'})
    else:
        return jsonify({'msg': 'User not found.'}), 404


@auth_bp.route('/verify-email/<token>', methods=['GET'])
def verify_email(token):
    """Verify email address with token."""
    user = models.User.query.filter_by(email_verification_token=token).first()

    if not user:
        return jsonify({'msg': 'Invalid or expired verification token'}), 400

    if user.verify_email_token(token):
        db.session.commit()
        return jsonify({'msg': 'Email verified successfully! You can now log in.'})
    else:
        return jsonify({'msg': 'Invalid or expired verification token'}), 400


@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per minute")
def forgot_password():
    """Request password reset."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    email_value = data.get('email')
    email = email_value.strip() if isinstance(email_value, str) else ''

    if not email:
        return jsonify({'msg': 'Email is required'}), 400

    generic_msg = 'If an account with that email exists, a password reset email has been sent.'
    user = models.User.query.filter_by(email=email).first()

    if user:
        reset_token = user.generate_password_reset_token()
        db.session.commit()

        base_url = request.host_url.rstrip('/')
        reset_url = f"{base_url}/reset-password/{reset_token}"

        if not send_password_reset(user, reset_url):
            current_app.logger.warning('Password reset email could not be sent for user %s', user.id)

    return jsonify({'msg': generic_msg})


@auth_bp.route('/reset-password/<token>', methods=['POST'])
@limiter.limit("5 per minute")
def reset_password(token):
    """Reset password with token."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    new_password = data.get('password', '')

    if not isinstance(new_password, str) or not new_password:
        return jsonify({'msg': 'New password is required'}), 400

    pw_valid, pw_error = validate_password(new_password)
    if not pw_valid:
        return jsonify({'msg': pw_error}), 400

    user = models.User.query.filter_by(password_reset_token=token).first()

    if not user:
        return jsonify({'msg': 'Invalid or expired reset token'}), 400

    if user.verify_password_reset_token(token):
        user.set_password(new_password)
        user.clear_password_reset_token()
        user.token_version = int(user.token_version or 0) + 1
        db.session.commit()
        return jsonify({'msg': 'Password reset successfully! You can now log in with your new password.'})
    else:
        return jsonify({'msg': 'Invalid or expired reset token'}), 400


@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend email verification."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    email_value = data.get('email')
    email = email_value.strip() if isinstance(email_value, str) else ''

    if not email:
        return jsonify({'msg': 'Email is required'}), 400

    generic_msg = 'If that email is registered, a verification email has been sent.'

    user = models.User.query.filter_by(email=email).first()

    if not user or user.email_verified:
        return jsonify({'msg': generic_msg})

    verification_token = user.generate_email_verification_token()
    db.session.commit()

    base_url = request.host_url.rstrip('/')
    verification_url = f"{base_url}/verify-email/{verification_token}"

    send_email_verification(user, verification_url)
    return jsonify({'msg': generic_msg})
