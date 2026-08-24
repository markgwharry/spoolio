"""Shared pytest fixtures for isolated Spoolio API tests."""

from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    email: str
    spoolman_token: str | None
    is_admin: bool


@dataclass(frozen=True)
class ReferenceData:
    material_id: int
    color_id: int
    manufacturer_id: int
    spool_type_id: int


@dataclass(frozen=True)
class SpoolRecord:
    id: int
    user_id: int
    nfc_tag_id: str | None


@dataclass(frozen=True)
class HardwareDeviceRecord:
    id: int
    user_id: int | None
    api_key: str
    hardware_type: str | None


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Create an app backed by a fresh SQLite database for each test."""
    database_path = tmp_path / "spoolio-test.db"
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-characters-minimum")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-key-32-characters-minimum")
    monkeypatch.setenv("WIFI_CREDENTIAL_KEY", "test-wifi-key-32-characters-minimum")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", f"sqlite:///{database_path}")
    monkeypatch.setenv("PROFILE_IMAGE_FOLDER", str(tmp_path / "profile-images"))
    monkeypatch.setenv("FIRMWARE_UPLOAD_FOLDER", str(tmp_path / "firmware"))

    from app import create_app
    from extensions import db
    import models  # noqa: F401 - registers the model metadata

    test_app = create_app({
        "TESTING": True,
        "RATELIMIT_ENABLED": False,
        "RATELIMIT_HEADERS_ENABLED": True,
        "MAIL_SUPPRESS_SEND": True,
        "FIRMWARE_OTA_ENABLED": True,
        "REGISTRATION_MODE": "waitlist",
        "REGISTRATION_TOKEN": "test-registration-token-32-chars",
    })

    with test_app.app_context():
        db.create_all()

    yield test_app

    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def rate_limited_app(tmp_path, monkeypatch):
    """Create an isolated app with Flask-Limiter enabled."""
    database_path = tmp_path / "spoolio-rate-limit-test.db"
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-characters-minimum")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-key-32-characters-minimum")
    monkeypatch.setenv("WIFI_CREDENTIAL_KEY", "test-wifi-key-32-characters-minimum")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", f"sqlite:///{database_path}")
    monkeypatch.setenv("PROFILE_IMAGE_FOLDER", str(tmp_path / "profile-images"))
    monkeypatch.setenv("FIRMWARE_UPLOAD_FOLDER", str(tmp_path / "firmware"))

    from app import create_app
    from extensions import db
    import models  # noqa: F401 - registers the model metadata

    test_app = create_app({
        "TESTING": True,
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_HEADERS_ENABLED": True,
        "MAIL_SUPPRESS_SEND": True,
        "FIRMWARE_OTA_ENABLED": True,
        "REGISTRATION_MODE": "waitlist",
        "REGISTRATION_TOKEN": "test-registration-token-32-chars",
    })
    with test_app.app_context():
        db.create_all()

    yield test_app

    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def rate_limited_client(rate_limited_app):
    return rate_limited_app.test_client()


@pytest.fixture()
def user_factory(app):
    """Return a helper that creates persisted users."""
    created = 0

    def create_user(*, username=None, email=None, password="Aa123456",
                    with_spoolman_token=True, email_verified=True,
                    is_admin=False):
        nonlocal created
        created += 1
        username = username or f"user{created}"
        email = email or f"{username}@example.com"

        from extensions import db
        import models

        with app.app_context():
            model = models.User(
                username=username,
                email=email,
                email_verified=email_verified,
                is_admin=is_admin,
            )
            model.set_password(password)
            if with_spoolman_token:
                model.generate_spoolman_token()
            db.session.add(model)
            db.session.commit()
            return UserRecord(
                id=model.id,
                username=model.username,
                email=model.email,
                spoolman_token=model.spoolman_token,
                is_admin=model.is_admin,
            )

    return create_user


@pytest.fixture()
def user(user_factory):
    return user_factory(username="alice", email="alice@example.com")


@pytest.fixture()
def reference_data(app):
    from extensions import db
    import models

    with app.app_context():
        material = models.Material(name="PLA")
        color = models.Color(name="Red")
        manufacturer = models.Manufacturer(name="Acme")
        spool_type = models.SpoolType(name="Standard", tare_weight=200.0)
        db.session.add_all([material, color, manufacturer, spool_type])
        db.session.commit()
        return ReferenceData(
            material_id=material.id,
            color_id=color.id,
            manufacturer_id=manufacturer.id,
            spool_type_id=spool_type.id,
        )


@pytest.fixture()
def spool_factory(app, reference_data):
    created = 0

    def create_spool(*, user_id, nfc_tag_id=None, weight_start=1000.0,
                     weight_remaining=1000.0):
        nonlocal created
        created += 1

        from extensions import db
        import models

        with app.app_context():
            group = models.FilamentGroup(
                material_id=reference_data.material_id,
                color_id=reference_data.color_id,
                user_id=user_id,
                name=f"PLA Red {created}",
            )
            db.session.add(group)
            db.session.flush()

            model = models.FilamentSpool(
                material_id=reference_data.material_id,
                color_id=reference_data.color_id,
                manufacturer_id=reference_data.manufacturer_id,
                spool_type_id=reference_data.spool_type_id,
                group_id=group.id,
                user_id=user_id,
                nfc_tag_id=nfc_tag_id,
                weight_start=weight_start,
                weight_remaining=weight_remaining,
            )
            db.session.add(model)
            db.session.commit()
            return SpoolRecord(
                id=model.id,
                user_id=model.user_id,
                nfc_tag_id=model.nfc_tag_id,
            )

    return create_spool


@pytest.fixture()
def spool(user, spool_factory):
    return spool_factory(user_id=user.id)


@pytest.fixture()
def hardware_device_factory(app):
    created = 0

    def create_hardware_device(*, user_id, hardware_type="scale"):
        nonlocal created
        created += 1

        from extensions import db
        import models

        with app.app_context():
            api_key = f"test-device-key-{created}"
            model = models.HardwareDevice(
                device_id=f"test-device-{created}",
                name=f"Test Device {created}",
                hardware_type=hardware_type,
                api_key=models.HardwareDevice.hash_api_key(api_key),
                user_id=user_id,
            )
            db.session.add(model)
            db.session.commit()
            return HardwareDeviceRecord(
                id=model.id,
                user_id=model.user_id,
                api_key=api_key,
                hardware_type=model.hardware_type,
            )

    return create_hardware_device


@pytest.fixture()
def auth_headers_factory(app):
    def create_headers(user_id):
        from flask_jwt_extended import create_access_token

        with app.app_context():
            token = create_access_token(identity=str(user_id))
        return {"Authorization": f"Bearer {token}"}

    return create_headers
