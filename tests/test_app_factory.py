"""Application-factory configuration regression tests."""

import pytest
from sqlalchemy import text


def test_test_config_is_applied_before_extensions_initialize(app):
    from blueprints._helpers import limiter

    assert app.testing is True
    assert app.config["RATELIMIT_ENABLED"] is False
    assert limiter.enabled is False
    assert app.config["MAIL_SUPPRESS_SEND"] is True
    assert app.extensions["mail"].suppress is True
    assert app.config["JWT_SECRET_KEY"] == "test-jwt-key-32-characters-minimum"
    assert app.config["WIFI_CREDENTIAL_KEY"] == "test-wifi-key-32-characters-minimum"


def test_sqlite_connections_enforce_integrity_and_concurrency_pragmas(app):
    from extensions import db

    with app.app_context():
        foreign_keys = db.session.execute(text("PRAGMA foreign_keys")).scalar()
        busy_timeout = db.session.execute(text("PRAGMA busy_timeout")).scalar()
        journal_mode = db.session.execute(text("PRAGMA journal_mode")).scalar()

    assert foreign_keys == 1
    assert busy_timeout == 5000
    assert journal_mode == "wal"


def test_dedicated_wifi_key_reads_legacy_ciphertext_during_migration(app):
    from models import decrypt_wifi_secret, encrypt_wifi_secret

    with app.app_context():
        dedicated_key = app.config["WIFI_CREDENTIAL_KEY"]
        app.config["WIFI_CREDENTIAL_KEY"] = None
        legacy_ciphertext = encrypt_wifi_secret("legacy-password")

        app.config["WIFI_CREDENTIAL_KEY"] = dedicated_key
        assert decrypt_wifi_secret(legacy_ciphertext) == "legacy-password"

        dedicated_ciphertext = encrypt_wifi_secret("new-password")
        app.config["SECRET_KEY"] = "rotated-session-secret-key-32-characters"
        assert decrypt_wifi_secret(dedicated_ciphertext) == "new-password"


def test_spa_fallback_does_not_probe_files_outside_static_folder(app, tmp_path):
    static_folder = tmp_path / 'static'
    static_folder.mkdir()
    (static_folder / 'index.html').write_text('safe-spa-shell')
    (tmp_path / 'operator-only.txt').write_text('must-not-be-served')
    app.static_folder = str(static_folder)

    response = app.test_client().get('/..%2Foperator-only.txt')

    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'safe-spa-shell'


def _production_config(tmp_path):
    return {
        "SECRET_KEY": "factory-session-secret-with-more-than-32-chars",
        "JWT_SECRET_KEY": "factory-jwt-secret-with-more-than-32-chars",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "PROFILE_IMAGE_FOLDER": str(tmp_path / "profile-images"),
        "FIRMWARE_UPLOAD_FOLDER": str(tmp_path / "firmware"),
    }


def test_production_accepts_strong_factory_secret_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    from app import create_app

    config = _production_config(tmp_path)
    production_app = create_app(config)

    assert production_app.config["SECRET_KEY"] == config["SECRET_KEY"]
    assert production_app.config["JWT_SECRET_KEY"] == config["JWT_SECRET_KEY"]


def test_production_rejects_weak_wifi_credential_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")

    from app import create_app

    config = _production_config(tmp_path)
    config["WIFI_CREDENTIAL_KEY"] = "short"

    with pytest.raises(ValueError, match="WIFI_CREDENTIAL_KEY must be"):
        create_app(config)


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("SECRET_KEY", "SECRET_KEY must be set"),
        ("JWT_SECRET_KEY", "JWT_SECRET_KEY must be set"),
    ],
)
def test_production_rejects_weak_final_factory_secrets(
    tmp_path,
    monkeypatch,
    key,
    message,
):
    monkeypatch.setenv("FLASK_ENV", "production")

    from app import create_app

    config = _production_config(tmp_path)
    config[key] = "short"

    with pytest.raises(ValueError, match=message):
        create_app(config)
