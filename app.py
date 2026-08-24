import os
from pathlib import Path, PureWindowsPath

from flask import Flask, send_from_directory, request
from flask_cors import CORS
from werkzeug.exceptions import NotFound, RequestEntityTooLarge
from werkzeug.utils import safe_join, secure_filename

from blueprints import register_blueprints
from commands import register_cli
from email_service import init_mail
from extensions import db, migrate
import models

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent


def _environment_flag(name, default=False):
    """Return a strict, case-insensitive boolean environment flag."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}

def _load_env_files():
    """Load environment variables from known locations if python-dotenv is available."""
    if not load_dotenv:
        return
    # Support a parent-level service configuration and a checkout-local override.
    env_candidates = [
        BASE_DIR.parent / '.env',
        BASE_DIR / '.env',
    ]
    for env_path in env_candidates:
        if env_path.is_file():
            load_dotenv(env_path, override=False)

_load_env_files()


def _normalize_database_uri(app, db_uri):
    """Resolve the final configured database URI before SQLAlchemy sees it."""
    if not db_uri:
        instance_folder = Path(app.instance_path)
        current_default = instance_folder / 'filament.db'
        legacy_default = instance_folder / 'instance' / 'filament.db'
        db_path = (
            legacy_default
            if legacy_default.is_file() and not current_default.exists()
            else current_default
        )
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    if not isinstance(db_uri, str):
        raise ValueError('SQLALCHEMY_DATABASE_URI must be a string')
    if db_uri == 'sqlite:///:memory:':
        return db_uri
    if db_uri.startswith('sqlite:///') and not db_uri.startswith('sqlite:////'):
        relative_path = db_uri.replace('sqlite:///', '', 1)
        if PureWindowsPath(relative_path).is_absolute():
            return db_uri
        safe_db_name = secure_filename(relative_path)
        if not safe_db_name or safe_db_name != relative_path:
            raise ValueError(
                'Relative SQLite database paths must be a filename inside the '
                'instance folder'
            )
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{Path(app.instance_path) / safe_db_name}"
    return db_uri


def create_app(config=None):
    app = Flask(__name__, static_folder='static')

    # Production configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        os.environ.get('SQLALCHEMY_DATABASE_URI')
        or os.environ.get('DATABASE_URL')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', '')
    app.config['WIFI_CREDENTIAL_KEY'] = os.environ.get('WIFI_CREDENTIAL_KEY')
    app.config['REGISTRATION_MODE'] = os.environ.get(
        'REGISTRATION_MODE',
        'waitlist',
    ).strip().lower()
    app.config['REGISTRATION_TOKEN'] = os.environ.get('REGISTRATION_TOKEN', '')
    app.config['WAITLIST_NOTIFICATION_EMAIL'] = os.environ.get(
        'WAITLIST_NOTIFICATION_EMAIL'
    )
    app.config['FIRMWARE_OTA_ENABLED'] = _environment_flag(
        'FIRMWARE_OTA_ENABLED',
        default=False,
    )
    try:
        max_content_length = int(
            os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
        )
        if max_content_length <= 0:
            raise ValueError
        app.config['MAX_CONTENT_LENGTH'] = max_content_length
    except (TypeError, ValueError):
        app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    profile_folder = os.environ.get('PROFILE_IMAGE_FOLDER') or os.path.join(app.root_path, 'shared', 'profile_images')
    app.config['PROFILE_IMAGE_FOLDER'] = profile_folder

    os.makedirs(app.instance_path, exist_ok=True)
    firmware_folder = os.environ.get('FIRMWARE_UPLOAD_FOLDER') or os.path.join(app.instance_path, 'firmware')
    app.config['FIRMWARE_UPLOAD_FOLDER'] = firmware_folder
    firmware_secret = os.environ.get('FIRMWARE_DOWNLOAD_SECRET')
    if firmware_secret:
        app.config['FIRMWARE_DOWNLOAD_SECRET'] = firmware_secret

    # Disable debug mode in production
    app.config['DEBUG'] = False

    # Apply caller-provided configuration before any extension or blueprint is
    # initialized. Tests rely on this to suppress mail and disable rate limits.
    if config:
        app.config.update(config)

    app.config['SQLALCHEMY_DATABASE_URI'] = _normalize_database_uri(
        app,
        app.config.get('SQLALCHEMY_DATABASE_URI'),
    )

    registration_mode = app.config.get('REGISTRATION_MODE')
    if not isinstance(registration_mode, str):
        raise ValueError('REGISTRATION_MODE must be waitlist, first-user, or closed')
    registration_mode = registration_mode.strip().lower()
    if registration_mode not in {'waitlist', 'first-user', 'closed'}:
        raise ValueError('REGISTRATION_MODE must be waitlist, first-user, or closed')
    app.config['REGISTRATION_MODE'] = registration_mode
    registration_token = app.config.get('REGISTRATION_TOKEN')
    if registration_mode == 'first-user' and (
        not isinstance(registration_token, str)
        or len(registration_token) < 16
    ):
        raise ValueError(
            'REGISTRATION_TOKEN must be set to at least 16 characters in first-user mode'
        )

    # Validate the final values after applying caller overrides. This prevents
    # factory configuration from bypassing production secret requirements.
    weak_secrets = {
        '',
        'your-secret-key-change-this',
        'your-jwt-secret-key-change-this',
        'change-me',
        'secret',
    }
    secret_key = app.config.get('SECRET_KEY') or ''
    jwt_secret_key = app.config.get('JWT_SECRET_KEY') or ''
    is_production = os.environ.get('FLASK_ENV') == 'production'

    if is_production:
        if not isinstance(secret_key, str) or secret_key in weak_secrets or len(secret_key) < 32:
            raise ValueError(
                'SECURITY ERROR: SECRET_KEY must be set to a strong random value (min 32 chars) in production. '
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        if not isinstance(jwt_secret_key, str) or jwt_secret_key in weak_secrets or len(jwt_secret_key) < 32:
            raise ValueError(
                'SECURITY ERROR: JWT_SECRET_KEY must be set to a strong random value (min 32 chars) in production. '
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        wifi_credential_key = app.config.get('WIFI_CREDENTIAL_KEY')
        if wifi_credential_key and (
            not isinstance(wifi_credential_key, str)
            or wifi_credential_key in weak_secrets
            or len(wifi_credential_key) < 32
        ):
            raise ValueError(
                'SECURITY ERROR: WIFI_CREDENTIAL_KEY must be a strong random '
                'value (min 32 chars) when configured in production.'
            )
    else:
        # Development fallbacks with warning
        if not isinstance(secret_key, str) or secret_key in weak_secrets:
            import warnings
            warnings.warn('Using weak SECRET_KEY - do not use in production!', stacklevel=2)
            secret_key = 'dev-only-secret-key-do-not-use-in-prod'
        if not isinstance(jwt_secret_key, str) or jwt_secret_key in weak_secrets:
            import warnings
            warnings.warn('Using weak JWT_SECRET_KEY - do not use in production!', stacklevel=2)
            jwt_secret_key = 'dev-only-jwt-secret-do-not-use-in-prod'

    app.config['SECRET_KEY'] = secret_key
    app.config['JWT_SECRET_KEY'] = jwt_secret_key

    if not app.config.get('WIFI_CREDENTIAL_KEY'):
        app.logger.warning(
            'WIFI_CREDENTIAL_KEY is not configured; Wi-Fi credentials will '
            'continue using SECRET_KEY for backward compatibility'
        )

    # These directories are trusted operator configuration, not request data. They
    # intentionally support absolute mounted-volume paths outside the checkout.
    # codeql[py/path-injection]
    os.makedirs(app.config['PROFILE_IMAGE_FOLDER'], exist_ok=True)
    # codeql[py/path-injection]
    os.makedirs(app.config['FIRMWARE_UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(BASE_DIR / 'migrations'))

    # Initialize email service
    init_mail(app)

    # Enable CORS with restricted origins
    allowed_origins = [
        origin.strip()
        for origin in os.environ.get('CORS_ORIGINS', '').split(',')
        if origin.strip()
    ]
    if not allowed_origins:
        allowed_origins = [
            'http://localhost:8000',
            'http://127.0.0.1:8000',
        ]
        if os.environ.get('FLASK_ENV') == 'development':
            allowed_origins.extend([
                'http://localhost:5173',
                'http://localhost:5000',
                'http://127.0.0.1:5173',
                'http://127.0.0.1:5000',
            ])
    CORS(app, origins=allowed_origins)

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    # Register API blueprints
    register_blueprints(app)
    register_cli(app)

    def _serve_static(filename: str):
        """Serve built assets regardless of whether they live at root or under ./static."""
        static_folder = app.static_folder or 'static'
        direct_path = os.path.join(static_folder, filename)
        if os.path.exists(direct_path):
            return send_from_directory(static_folder, filename)
        nested_path = os.path.join(static_folder, 'static', filename)
        if os.path.exists(nested_path):
            return send_from_directory(static_folder, f'static/{filename}')
        raise NotFound()

    # Override the default static endpoint to support current and legacy build layouts.
    app.view_functions['static'] = _serve_static

    # Serve React app
    @app.route('/')
    def serve():
        static_folder = app.static_folder or 'static'
        return send_from_directory(static_folder, 'index.html')

    @app.route('/account')
    def serve_account():
        static_folder = app.static_folder or 'static'
        return send_from_directory(static_folder, 'index.html')

    # Catch all routes and serve React app
    @app.route('/<path:path>')
    def static_proxy(path):
        static_folder = app.static_folder or 'static'
        # Try to serve the file from static folder
        file_path = safe_join(static_folder, path)
        if file_path and os.path.isfile(file_path):
            return send_from_directory(static_folder, path)
        # If file doesn't exist, serve index.html (for React Router)
        return send_from_directory(static_folder, 'index.html')

    @app.errorhandler(404)
    def handle_not_found(error):
        # Allow API routes and other static assets to return true 404s
        if request.path.startswith('/api/') or request.path.startswith('/spoolman/'):
            return error
        static_folder = app.static_folder or 'static'
        return send_from_directory(static_folder, 'index.html'), 200

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(error):
        if request.path.startswith('/api/'):
            return {'msg': 'Request body is too large'}, 413
        return error

    return app

if __name__ == '__main__':
    app = create_app()
    if os.environ.get('FLASK_ENV') != 'production':
        from flask_migrate import upgrade

        with app.app_context():
            upgrade(directory=str(BASE_DIR / 'migrations'))
    app.run(debug=False, host='0.0.0.0', port=5000)
