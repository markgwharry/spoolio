"""Application factory configuration contracts."""

import pytest


def test_invalid_registration_mode_is_rejected():
    from app import create_app

    with pytest.raises(ValueError, match='REGISTRATION_MODE'):
        create_app({'REGISTRATION_MODE': 'open-to-everyone'})


def test_first_user_mode_requires_a_strong_setup_token():
    from app import create_app

    with pytest.raises(ValueError, match='REGISTRATION_TOKEN'):
        create_app({
            'REGISTRATION_MODE': 'first-user',
            'REGISTRATION_TOKEN': 'too-short',
        })


def test_relative_sqlite_path_cannot_escape_instance_folder(monkeypatch):
    monkeypatch.setenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///../escaped.db')

    from app import create_app

    with pytest.raises(ValueError, match='must be a filename inside the instance'):
        create_app()


def test_factory_database_override_wins_before_environment_validation(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///../escaped.db')

    from app import create_app

    app = create_app({
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-session-key-with-more-than-32-chars',
        'JWT_SECRET_KEY': 'test-jwt-key-with-more-than-32-characters',
        'WIFI_CREDENTIAL_KEY': 'test-wifi-key-with-more-than-32-characters',
        'PROFILE_IMAGE_FOLDER': str(tmp_path / 'profile-images'),
        'FIRMWARE_UPLOAD_FOLDER': str(tmp_path / 'firmware'),
        'RATELIMIT_ENABLED': False,
        'MAIL_SUPPRESS_SEND': True,
    })

    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'


def test_windows_absolute_sqlite_uri_is_preserved():
    from app import _normalize_database_uri

    class AppStub:
        instance_path = '/unused'

    uri = 'sqlite:///C:/spoolio/filament.db'

    assert _normalize_database_uri(AppStub(), uri) == uri
