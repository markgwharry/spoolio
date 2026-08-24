import base64
import datetime
import hashlib
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, has_app_context
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db
from time_utils import utc_now_naive


def _derive_wifi_key(key_source):
    if isinstance(key_source, str):
        key_source = key_source.encode('utf-8')
    digest = hashlib.sha256(key_source).digest()
    return base64.urlsafe_b64encode(digest)


def _wifi_key_materials():
    """Return the current key followed by any legacy decryption fallback."""
    if not has_app_context():
        raise RuntimeError('Wi-Fi credential encryption requires an application context')

    dedicated_key = current_app.config.get('WIFI_CREDENTIAL_KEY')
    legacy_key = current_app.config.get('SECRET_KEY')
    key_sources = [dedicated_key] if dedicated_key else []
    if legacy_key and legacy_key != dedicated_key:
        key_sources.append(legacy_key)
    if not key_sources:
        raise RuntimeError('SECRET_KEY (or WIFI_CREDENTIAL_KEY) must be configured for Wi-Fi credential encryption')
    return [_derive_wifi_key(key_source) for key_source in key_sources]


def _get_wifi_key_material():
    """Return the primary key used for new Wi-Fi credential encryption."""
    return _wifi_key_materials()[0]


def _get_wifi_cipher():
    return Fernet(_get_wifi_key_material())


def encrypt_wifi_secret(plaintext: Optional[str]) -> Optional[bytes]:
    """Encrypt Wi-Fi credential text using the dedicated key when configured."""
    if plaintext is None:
        return None

    cipher = _get_wifi_cipher()
    return cipher.encrypt(plaintext.encode('utf-8'))


def _decrypt_wifi_secret(token: Optional[bytes]):
    """Return decrypted text and the key index that succeeded."""
    if not token:
        return None, None

    for key_index, key_material in enumerate(_wifi_key_materials()):
        try:
            plaintext = Fernet(key_material).decrypt(token).decode('utf-8')
            return plaintext, key_index
        except InvalidToken:
            continue
        except Exception:
            if has_app_context():
                current_app.logger.exception('Unexpected error decrypting Wi-Fi credential')
            return None, None
    if has_app_context():
        current_app.logger.warning('Failed to decrypt Wi-Fi credential: invalid token')
    return None, None


def decrypt_wifi_secret(token: Optional[bytes]) -> Optional[str]:
    """Decrypt Wi-Fi credential text, including legacy SECRET_KEY ciphertext."""
    plaintext, _ = _decrypt_wifi_secret(token)
    return plaintext

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    profile_image_filename = db.Column(db.String(255), nullable=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(100), unique=True, nullable=True)
    email_verification_expires = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(100), unique=True, nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    token_version = db.Column(db.Integer, default=0, nullable=False)
    # Per-user token for the Spoolman-compatible integration API. Lets external
    # tools (Moonraker, OctoPrint-Spoolman, slicers) reach this user's inventory
    # at /spoolman/<token>/api/v1/... without Spoolman-style anonymous access.
    spoolman_token = db.Column(db.String(64), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    spools = db.relationship('FilamentSpool', backref='user', lazy=True)
    groups = db.relationship('FilamentGroup', backref='user', lazy=True)
    projects = db.relationship('Project', backref='user', lazy=True)
    firmware_releases = db.relationship('FirmwareRelease', backref='creator', lazy=True)
    bits = db.relationship('Bit', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_email_verification_token(self):
        """Generate a secure token for email verification"""
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        return self.email_verification_token

    def generate_password_reset_token(self):
        """Generate a secure token for password reset"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        return self.password_reset_token

    def verify_email_token(self, token):
        """Verify email verification token"""
        now = datetime.datetime.now(datetime.timezone.utc)
        # Handle both naive and aware datetimes for backwards compatibility
        expires = self.email_verification_expires
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        if (self.email_verification_token == token and
            expires and
            expires > now):
            self.email_verified = True
            self.email_verification_token = None
            self.email_verification_expires = None
            return True
        return False

    def verify_password_reset_token(self, token):
        """Verify password reset token"""
        now = datetime.datetime.now(datetime.timezone.utc)
        # Handle both naive and aware datetimes for backwards compatibility
        expires = self.password_reset_expires
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        return (self.password_reset_token == token and
                expires and
                expires > now)

    def clear_password_reset_token(self):
        """Clear password reset token after use"""
        self.password_reset_token = None
        self.password_reset_expires = None

    def generate_spoolman_token(self):
        """Generate (or rotate) this user's Spoolman integration token."""
        self.spoolman_token = secrets.token_urlsafe(32)
        return self.spoolman_token


class WaitlistEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    referrer = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    raw_payload = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False, index=True)


class RegistrationBootstrap(db.Model):
    """Singleton claim that permanently closes one-time owner registration."""

    id = db.Column(db.Integer, primary_key=True)
    claimed_at = db.Column(
        db.DateTime,
        default=utc_now_naive,
        nullable=False,
    )

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    groups = db.relationship('FilamentGroup', backref='material', lazy=True)
    spools = db.relationship('FilamentSpool', backref='material', lazy=True)

class Color(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    groups = db.relationship('FilamentGroup', backref='color', lazy=True)
    spools = db.relationship('FilamentSpool', backref='color', lazy=True)

class Manufacturer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    spools = db.relationship('FilamentSpool', backref='manufacturer', lazy=True)

class SpoolType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    compatible_with_ams = db.Column(db.Boolean, default=False)
    # Empty spool tare weight in grams; used to subtract from gross scale readings
    tare_weight = db.Column(db.Float, nullable=True, default=0)
    spools = db.relationship('FilamentSpool', backref='spool_type', lazy=True)

class FilamentGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    color_id = db.Column(db.Integer, db.ForeignKey('color.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    spools = db.relationship('FilamentSpool', backref='group', lazy=True)

# Simple project/print-job entity to associate usage entries
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='active', nullable=False)
    budget_grams = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    # Relationship to history entries
    usages = db.relationship('SpoolHistory', backref='project', lazy=True)
    bit_usages = db.relationship('BitUsage', backref='project', lazy=True)

class FilamentSpool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    color_id = db.Column(db.Integer, db.ForeignKey('color.id'), nullable=False)
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturer.id'), nullable=False)
    spool_type_id = db.Column(db.Integer, db.ForeignKey('spool_type.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('filament_group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    weight_start = db.Column(db.Float, nullable=False)
    weight_remaining = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_empty = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    subtype = db.Column(db.String(100), nullable=True)
    low_stock_threshold = db.Column(db.Float, nullable=True, default=100)
    purchase_date = db.Column(db.Date, nullable=True)
    last_used_date = db.Column(db.DateTime, nullable=True)
    barcode = db.Column(db.String(100), nullable=True, unique=True)
    serial_number = db.Column(db.String(100), nullable=True, unique=True)
    nfc_tag_id = db.Column(db.String(100), nullable=True, unique=True)
    hardware_last_update = db.Column(db.DateTime, nullable=True)
    hardware_device_id = db.Column(
        db.Integer,
        db.ForeignKey('hardware_device.id'),
        nullable=True,
        index=True,
    )
    # New: per-spool price (e.g., GBP)
    price = db.Column(db.Float, nullable=True)
    # Ensure spool history is removed when a spool is deleted
    history = db.relationship('SpoolHistory', backref='spool', lazy=True, cascade="all, delete-orphan")

class SpoolHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spool_id = db.Column(db.Integer, db.ForeignKey('filament_spool.id'), nullable=False, index=True)
    date = db.Column(db.DateTime, nullable=False)
    weight_used = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True, index=True)

class HardwareDevice(db.Model):
    API_KEY_DIGEST_PREFIX = 'sha256$'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    hardware_type = db.Column(db.String(100), nullable=True)
    # SHA-256 digest only. The plaintext credential is returned once when it is
    # generated and is never persisted.
    api_key = db.Column(db.String(255), unique=True, nullable=False)
    last_seen = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='offline', nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    wifi_ssid = db.Column(db.String(255), nullable=True)
    wifi_password_encrypted = db.Column(db.LargeBinary, nullable=True)
    wifi_credentials_updated_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def hash_api_key(api_key):
        """Return the stable digest used for API-key lookup and persistence."""
        digest = hashlib.sha256(api_key.encode('utf-8')).hexdigest()
        return f'{HardwareDevice.API_KEY_DIGEST_PREFIX}{digest}'

    def set_api_key(self, api_key):
        """Persist only the digest of an existing plaintext device key."""
        self.api_key = self.hash_api_key(api_key)

    def generate_api_key(self):
        """Generate a device key, persist its digest, and return plaintext once."""
        api_key = secrets.token_urlsafe(32)
        self.set_api_key(api_key)
        return api_key

    def update_last_seen(self):
        """Update the last seen timestamp"""
        self.last_seen = utc_now_naive()
        self.status = 'online'

    def set_wifi_credentials(self, ssid: str, password: Optional[str] = None):
        """Store Wi-Fi credentials, encrypting the password before persisting."""
        self.wifi_ssid = ssid
        if password is not None:
            if password == '':
                self.wifi_password_encrypted = None
            else:
                self.wifi_password_encrypted = encrypt_wifi_secret(password)
        self.wifi_credentials_updated_at = utc_now_naive()

    def clear_wifi_credentials(self):
        """Remove any stored Wi-Fi credentials for the device."""
        self.wifi_ssid = None
        self.wifi_password_encrypted = None
        self.wifi_credentials_updated_at = utc_now_naive()

    def get_wifi_password(self) -> Optional[str]:
        """Return the decrypted Wi-Fi password, if one is stored."""
        return decrypt_wifi_secret(self.wifi_password_encrypted)

    def get_wifi_password_and_upgrade(self):
        """Decrypt and stage legacy ciphertext for dedicated-key persistence."""
        plaintext, key_index = _decrypt_wifi_secret(self.wifi_password_encrypted)
        migrated = plaintext is not None and key_index is not None and key_index > 0
        if migrated:
            self.wifi_password_encrypted = encrypt_wifi_secret(plaintext)
        return plaintext, migrated

    @property
    def has_wifi_password(self) -> bool:
        return bool(self.wifi_password_encrypted)


class OrphanTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nfc_tag_id = db.Column(db.String(100), unique=True, nullable=False)
    first_seen = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    last_seen = db.Column(db.DateTime, default=utc_now_naive, nullable=False, index=True)
    last_weight = db.Column(db.Float, nullable=True)
    hardware_device_id = db.Column(db.Integer, db.ForeignKey('hardware_device.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class HardwareEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Link to device and user for scoping
    device_id = db.Column(db.Integer, db.ForeignKey('hardware_device.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    # Event metadata
    event_type = db.Column(db.String(50), nullable=False)  # e.g., 'scan_start', 'weight_update', 'orphan', 'error'
    nfc_tag_id = db.Column(db.String(100), nullable=True)
    spool_id = db.Column(db.Integer, db.ForeignKey('filament_spool.id'), nullable=True)
    weight = db.Column(db.Float, nullable=True)  # net filament weight if known
    message = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False, index=True)


# Represents a firmware binary that can be deployed to hardware devices
class FirmwareRelease(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(64), nullable=False)
    hardware_type = db.Column(db.String(100), nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    download_url = db.Column(db.String(255), nullable=True)
    release_notes = db.Column(db.Text, nullable=True)
    manual_instructions = db.Column(db.Text, nullable=True)
    checksum = db.Column(db.String(128), nullable=False)
    is_active = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

# Represents a physical empty spool core available for reuse
class EmptySpool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    spool_type_id = db.Column(db.Integer, db.ForeignKey('spool_type.id'), nullable=False)
    # Optional back-reference to the spool that became empty and created this record
    origin_spool_id = db.Column(db.Integer, db.ForeignKey('filament_spool.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    notes = db.Column(db.Text, nullable=True)


# Represents filament inventory not currently on a spool (refill cartridges/rolls)
class FilamentRefill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    color_id = db.Column(db.Integer, db.ForeignKey('color.id'), nullable=False)
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturer.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('filament_group.id'), nullable=False)
    # Weight in grams
    weight_total = db.Column(db.Float, nullable=False)
    weight_remaining = db.Column(db.Float, nullable=False)
    # Optional metadata for parity with FilamentSpool
    subtype = db.Column(db.String(100), nullable=True)
    purchase_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=True)
    barcode = db.Column(db.String(100), nullable=True, unique=True)
    serial_number = db.Column(db.String(100), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)


# ----- Bits (hardware components) tracking -----

class BitCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    bits = db.relationship('Bit', backref='category', lazy=True)


class Bit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('bit_category.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    quantity_total = db.Column(db.Integer, nullable=False)
    quantity_remaining = db.Column(db.Integer, nullable=False)
    low_stock_threshold = db.Column(db.Integer, nullable=True, default=10)
    unit = db.Column(db.String(20), default='pcs', nullable=False)
    price = db.Column(db.Float, nullable=True)
    supplier = db.Column(db.String(200), nullable=True)
    purchase_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    usages = db.relationship('BitUsage', backref='bit', lazy=True, cascade="all, delete-orphan")


class BitUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bit_id = db.Column(db.Integer, db.ForeignKey('bit.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    quantity_used = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text, nullable=True)
