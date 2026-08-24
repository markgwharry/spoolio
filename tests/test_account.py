"""Authenticated account-management coverage."""

import datetime
import io
from pathlib import Path

from PIL import Image
from sqlalchemy import text


def _png_bytes(color=(120, 80, 200)):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_account_details_require_auth_and_return_only_the_token_owner(
    client,
    user_factory,
    auth_headers_factory,
):
    alice = user_factory(username="account-alice", email="account-alice@example.com")
    bob = user_factory(username="account-bob", email="account-bob@example.com")

    assert client.get("/api/account").status_code == 401

    alice_response = client.get(
        "/api/account",
        headers=auth_headers_factory(alice.id),
    )
    bob_response = client.get(
        "/api/account",
        headers=auth_headers_factory(bob.id),
    )
    assert alice_response.status_code == 200
    assert alice_response.get_json()["user"]["email"] == alice.email
    assert bob_response.get_json()["user"]["email"] == bob.email


def test_email_change_checks_password_uniqueness_and_reverification(
    app,
    client,
    monkeypatch,
    user_factory,
    auth_headers_factory,
):
    alice = user_factory(username="email-alice", email="email-alice@example.com")
    bob = user_factory(username="email-bob", email="email-bob@example.com")
    headers = auth_headers_factory(alice.id)
    sent = []
    monkeypatch.setattr(
        "blueprints.account.send_email_verification",
        lambda user, url: sent.append((user.email, url)) or True,
    )

    wrong_password = client.patch(
        "/api/account/email",
        headers=headers,
        json={"email": "new-alice@example.com", "current_password": "WrongPass1"},
    )
    assert wrong_password.status_code == 403

    cross_user = client.patch(
        "/api/account/email",
        headers=headers,
        json={"email": bob.email.upper(), "current_password": "Aa123456"},
    )
    assert cross_user.status_code == 409

    updated = client.patch(
        "/api/account/email",
        headers=headers,
        json={
            "email": "new-alice@example.com",
            "current_password": "Aa123456",
            "verification_base_url": "https://self-hosted.example.test/",
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["user"]["email"] == "new-alice@example.com"
    assert updated.get_json()["user"]["email_verified"] is False
    assert sent[0][0] == "new-alice@example.com"
    assert sent[0][1].startswith("https://self-hosted.example.test/verify-email/")

    from extensions import db
    import models

    with app.app_context():
        stored_alice = db.session.get(models.User, alice.id)
        stored_bob = db.session.get(models.User, bob.id)
        assert stored_alice.email_verification_token
        assert stored_bob.email == bob.email


def test_password_change_updates_only_the_authenticated_user(
    app,
    client,
    user_factory,
    auth_headers_factory,
):
    alice = user_factory(username="password-alice", email="password-alice@example.com")
    bob = user_factory(username="password-bob", email="password-bob@example.com")
    login = client.post(
        "/api/login",
        json={"username": alice.username, "password": "Aa123456"},
    ).get_json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    from extensions import db
    import models

    with app.app_context():
        stored = db.session.get(models.User, alice.id)
        stored.generate_password_reset_token()
        db.session.commit()

    assert client.patch(
        "/api/account/password",
        headers=headers,
        json={"current_password": "WrongPass1", "new_password": "NewValid2"},
    ).status_code == 403
    assert client.patch(
        "/api/account/password",
        headers=headers,
        json={"current_password": "Aa123456", "new_password": "weak"},
    ).status_code == 400

    response = client.patch(
        "/api/account/password",
        headers=headers,
        json={"current_password": "Aa123456", "new_password": "NewValid2"},
    )
    assert response.status_code == 200
    replacement_tokens = response.get_json()
    assert replacement_tokens["access_token"]
    assert replacement_tokens["refresh_token"]
    assert client.get("/api/account", headers=headers).status_code == 401
    assert client.post(
        "/api/refresh",
        headers={"Authorization": f"Bearer {login['refresh_token']}"},
    ).status_code == 401
    assert client.post(
        "/api/refresh",
        headers={
            "Authorization": f"Bearer {replacement_tokens['refresh_token']}"
        },
    ).status_code == 200

    with app.app_context():
        stored_alice = db.session.get(models.User, alice.id)
        stored_bob = db.session.get(models.User, bob.id)
        assert stored_alice.check_password("NewValid2")
        assert not stored_alice.check_password("Aa123456")
        assert stored_alice.password_reset_token is None
        assert stored_alice.token_version == 1
        assert stored_bob.check_password("Aa123456")


def test_account_mutations_reject_non_object_json(
    client,
    user_factory,
    auth_headers_factory,
):
    user = user_factory(username="json-account", email="json-account@example.com")
    headers = auth_headers_factory(user.id)

    responses = [
        client.patch("/api/account/email", headers=headers, json=[]),
        client.patch("/api/account/password", headers=headers, json=["bad"]),
        client.delete("/api/account", headers=headers, json=["bad"]),
    ]
    assert all(response.status_code == 400 for response in responses)
    assert all(response.is_json for response in responses)


def test_profile_image_upload_serve_replace_and_delete(
    app,
    client,
    user_factory,
    auth_headers_factory,
):
    user = user_factory(username="image-user", email="image-user@example.com")
    headers = auth_headers_factory(user.id)

    first = client.post(
        "/api/account/profile-image",
        headers=headers,
        data={"image": (io.BytesIO(_png_bytes()), "avatar.png")},
        content_type="multipart/form-data",
    )
    assert first.status_code == 200
    first_url = first.get_json()["user"]["profile_image_url"]
    first_name = first_url.rsplit("/", 1)[1]
    first_path = Path(app.config["PROFILE_IMAGE_FOLDER"]) / first_name
    assert first_path.is_file()
    with Image.open(first_path) as image:
        image.verify()

    served = client.get(first_url)
    assert served.status_code == 200
    assert served.mimetype == "image/png"

    second = client.post(
        "/api/account/profile-image",
        headers=headers,
        data={"image": (io.BytesIO(_png_bytes((10, 20, 30))), "replacement.png")},
        content_type="multipart/form-data",
    )
    assert second.status_code == 200
    second_url = second.get_json()["user"]["profile_image_url"]
    assert second_url != first_url
    assert not first_path.exists()

    deleted = client.delete("/api/account/profile-image", headers=headers)
    assert deleted.status_code == 200
    assert deleted.get_json()["user"]["profile_image_url"] is None
    assert client.get(second_url).status_code == 404


def test_profile_image_rejects_invalid_and_oversized_content(
    app,
    client,
    user_factory,
    auth_headers_factory,
):
    user = user_factory(username="invalid-image", email="invalid-image@example.com")
    headers = auth_headers_factory(user.id)
    folder = Path(app.config["PROFILE_IMAGE_FOLDER"])

    unsupported = client.post(
        "/api/account/profile-image",
        headers=headers,
        data={"image": (io.BytesIO(b"not an image"), "avatar.txt")},
        content_type="multipart/form-data",
    )
    assert unsupported.status_code == 400

    disguised = client.post(
        "/api/account/profile-image",
        headers=headers,
        data={"image": (io.BytesIO(b"not an image"), "avatar.png")},
        content_type="multipart/form-data",
    )
    assert disguised.status_code == 400
    assert list(folder.iterdir()) == []

    app.config["MAX_CONTENT_LENGTH"] = 1024
    oversized = client.post(
        "/api/account/profile-image",
        headers=headers,
        data={"image": (io.BytesIO(b"x" * 2048), "large.png")},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 413
    assert oversized.is_json
    assert oversized.get_json()["msg"] == "Request body is too large"


def test_account_deletion_removes_owned_data_without_touching_another_tenant(
    app,
    client,
    user_factory,
    spool_factory,
    hardware_device_factory,
    reference_data,
    auth_headers_factory,
):
    alice = user_factory(username="delete-alice", email="delete-alice@example.com")
    bob = user_factory(username="delete-bob", email="delete-bob@example.com")
    alice_spool = spool_factory(user_id=alice.id, nfc_tag_id="delete-alice-tag")
    bob_spool = spool_factory(user_id=bob.id, nfc_tag_id="delete-bob-tag")
    alice_device = hardware_device_factory(user_id=alice.id)
    bob_device = hardware_device_factory(user_id=bob.id)

    from extensions import db
    import models

    profile_name = "delete-alice.png"
    profile_path = Path(app.config["PROFILE_IMAGE_FOLDER"]) / profile_name
    profile_path.write_bytes(_png_bytes())
    independent_waitlist_email = "independent-waitlist@example.com"

    with app.app_context():
        db.session.execute(text("PRAGMA foreign_keys=ON"))
        db.session.commit()
        alice_model = db.session.get(models.User, alice.id)
        alice_model.profile_image_filename = profile_name
        # Simulate the account having changed to an email already present on
        # the independent waitlist; the email match must not imply ownership.
        alice_model.email = independent_waitlist_email
        alice_spool_model = db.session.get(models.FilamentSpool, alice_spool.id)
        bob_spool_model = db.session.get(models.FilamentSpool, bob_spool.id)

        alice_project = models.Project(user_id=alice.id, name="Alice project")
        bob_project = models.Project(user_id=bob.id, name="Bob project")
        category = models.BitCategory(name="Fasteners")
        db.session.add_all([alice_project, bob_project, category])
        db.session.flush()

        alice_bit = models.Bit(
            user_id=alice.id,
            category_id=category.id,
            name="Alice screw",
            quantity_total=10,
            quantity_remaining=9,
        )
        bob_bit = models.Bit(
            user_id=bob.id,
            category_id=category.id,
            name="Bob screw",
            quantity_total=10,
            quantity_remaining=10,
        )
        db.session.add_all([alice_bit, bob_bit])
        db.session.flush()

        alice_rows = [
            models.SpoolHistory(
                spool_id=alice_spool.id,
                project_id=alice_project.id,
                date=datetime.datetime.now(datetime.timezone.utc),
                weight_used=25,
            ),
            models.BitUsage(
                bit_id=alice_bit.id,
                project_id=alice_project.id,
                quantity_used=1,
                date=datetime.datetime.now(datetime.timezone.utc),
            ),
            models.EmptySpool(
                user_id=alice.id,
                spool_type_id=reference_data.spool_type_id,
                origin_spool_id=alice_spool.id,
            ),
            models.FilamentRefill(
                user_id=alice.id,
                material_id=reference_data.material_id,
                color_id=reference_data.color_id,
                manufacturer_id=reference_data.manufacturer_id,
                group_id=alice_spool_model.group_id,
                weight_total=1000,
                weight_remaining=800,
            ),
            models.OrphanTag(
                nfc_tag_id="delete-alice-orphan",
                hardware_device_id=alice_device.id,
                user_id=alice.id,
            ),
            models.HardwareEvent(
                device_id=alice_device.id,
                user_id=alice.id,
                spool_id=alice_spool.id,
                event_type="weight_update",
            ),
            models.FirmwareRelease(
                version="alice-release",
                hardware_type="scale",
                file_name="alice.bin",
                checksum="alice-checksum",
                created_by=alice.id,
            ),
            models.WaitlistEntry(
                username="independent-person",
                email=independent_waitlist_email,
                notes="Must survive another account's deletion",
            ),
        ]
        bob_rows = [
            models.SpoolHistory(
                spool_id=bob_spool.id,
                project_id=bob_project.id,
                date=datetime.datetime.now(datetime.timezone.utc),
                weight_used=5,
            ),
            models.BitUsage(
                bit_id=bob_bit.id,
                project_id=bob_project.id,
                quantity_used=1,
                date=datetime.datetime.now(datetime.timezone.utc),
            ),
            models.OrphanTag(
                nfc_tag_id="delete-bob-orphan",
                hardware_device_id=bob_device.id,
                user_id=bob.id,
            ),
            models.HardwareEvent(
                device_id=bob_device.id,
                user_id=bob.id,
                spool_id=bob_spool.id,
                event_type="weight_update",
            ),
            models.FirmwareRelease(
                version="bob-release",
                hardware_type="scale",
                file_name="bob.bin",
                checksum="bob-checksum",
                created_by=bob.id,
            ),
        ]
        db.session.add_all(alice_rows + bob_rows)
        db.session.commit()
        alice_project_id = alice_project.id
        alice_bit_id = alice_bit.id
        alice_firmware_id = alice_rows[-2].id
        bob_project_id = bob_project.id
        bob_bit_id = bob_bit.id
        bob_firmware_id = bob_rows[-1].id

    headers = auth_headers_factory(alice.id)
    assert client.delete(
        "/api/account",
        headers=headers,
        json={"current_password": "WrongPass1", "confirm": True},
    ).status_code == 403
    assert client.delete(
        "/api/account",
        headers=headers,
        json={"current_password": "Aa123456", "confirm": False},
    ).status_code == 400
    assert client.delete(
        "/api/account",
        headers=headers,
        json={"current_password": "Aa123456", "confirm": "true"},
    ).status_code == 400

    deleted = client.delete(
        "/api/account",
        headers=headers,
        json={"current_password": "Aa123456", "confirm": True},
    )
    assert deleted.status_code == 200
    assert not profile_path.exists()

    with app.app_context():
        assert db.session.get(models.User, alice.id) is None
        assert models.FilamentSpool.query.filter_by(user_id=alice.id).count() == 0
        assert models.FilamentGroup.query.filter_by(user_id=alice.id).count() == 0
        assert models.Project.query.filter_by(user_id=alice.id).count() == 0
        assert models.FilamentRefill.query.filter_by(user_id=alice.id).count() == 0
        assert models.EmptySpool.query.filter_by(user_id=alice.id).count() == 0
        assert models.HardwareDevice.query.filter_by(user_id=alice.id).count() == 0
        assert models.HardwareEvent.query.filter_by(user_id=alice.id).count() == 0
        assert models.OrphanTag.query.filter_by(user_id=alice.id).count() == 0
        assert models.Bit.query.filter_by(user_id=alice.id).count() == 0
        assert models.BitUsage.query.filter_by(bit_id=alice_bit_id).count() == 0
        # Waitlist submissions have no ownership link to User. A mutable email
        # match is not sufficient authority to delete this independent record.
        waitlist_entry = models.WaitlistEntry.query.filter_by(
            email=independent_waitlist_email
        ).one()
        assert waitlist_entry.notes == "Must survive another account's deletion"
        assert db.session.get(models.Project, alice_project_id) is None
        alice_firmware = db.session.get(models.FirmwareRelease, alice_firmware_id)
        assert alice_firmware is not None
        assert alice_firmware.created_by is None

        assert db.session.get(models.User, bob.id) is not None
        assert db.session.get(models.FilamentSpool, bob_spool.id) is not None
        assert db.session.get(models.Project, bob_project_id) is not None
        assert db.session.get(models.Bit, bob_bit_id) is not None
        assert db.session.get(models.FirmwareRelease, bob_firmware_id).created_by == bob.id
