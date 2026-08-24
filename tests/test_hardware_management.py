"""Hardware management, communications, firmware, and dashboard coverage."""

import datetime
import io
from urllib.parse import urlsplit

from time_utils import utc_now_naive


def _device_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def test_device_registration_wifi_rotation_and_deletion_are_owner_scoped(
    app,
    client,
    user_factory,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-device", email="alice-device@example.com")
    bob = user_factory(username="bob-device", email="bob-device@example.com")
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)

    for invalid_field, invalid_value in (
        ("hardware_type", []),
        ("hardware_type", {"unexpected": True}),
        ("hardware_type", 42),
        ("location", []),
    ):
        invalid_registration = client.post(
            "/api/hardware/register",
            headers=alice_headers,
            json={
                "device_id": "invalid-metadata-device",
                "name": "Invalid metadata",
                invalid_field: invalid_value,
            },
        )
        assert invalid_registration.status_code == 400

    registered = client.post(
        "/api/hardware/register",
        headers=alice_headers,
        json={
            "device_id": "scale-v2-001",
            "name": "Workbench scale",
            "location": "Workshop",
            "hardware_type": "open-scale-v2",
        },
    )
    assert registered.status_code == 201
    body = registered.get_json()
    device_id = body["device"]["id"]
    original_key = body["api_key"]
    assert original_key

    from extensions import db
    import models

    with app.app_context():
        stored_device = db.session.get(models.HardwareDevice, device_id)
        assert stored_device.api_key == models.HardwareDevice.hash_api_key(original_key)
        assert stored_device.api_key != original_key
        stored_digest = stored_device.api_key

    assert client.get(
        "/api/hardware/heartbeat", headers=_device_headers(stored_digest)
    ).status_code == 401

    assert client.get(
        "/api/hardware/devices", headers=bob_headers
    ).get_json() == []
    assert client.post(
        "/api/hardware/register",
        headers=bob_headers,
        json={"device_id": "scale-v2-001", "name": "Duplicate"},
    ).status_code == 409

    for response in (
        client.get(f"/api/hardware/devices/{device_id}/wifi", headers=bob_headers),
        client.put(
            f"/api/hardware/devices/{device_id}/wifi",
            headers=bob_headers,
            json={"ssid": "wrong-owner"},
        ),
        client.post(
            f"/api/hardware/devices/{device_id}/regenerate-key",
            headers=bob_headers,
        ),
        client.delete(f"/api/hardware/devices/{device_id}", headers=bob_headers),
    ):
        assert response.status_code == 404

    wifi = client.put(
        f"/api/hardware/devices/{device_id}/wifi",
        headers=alice_headers,
        json={"ssid": "Workshop WiFi", "password": "test-password"},
    )
    assert wifi.status_code == 200
    assert wifi.get_json()["wifi_password_set"] is True
    assert "password" not in wifi.get_json()

    config = client.get(
        "/api/hardware/config/wifi", headers=_device_headers(original_key)
    )
    assert config.status_code == 200
    assert config.get_json()["wifi"] == {
        "ssid": "Workshop WiFi",
        "password": "test-password",
        "updated_at": config.get_json()["wifi"]["updated_at"],
    }
    heartbeat = client.get(
        "/api/hardware/heartbeat", headers=_device_headers(original_key)
    )
    assert heartbeat.status_code == 200
    assert heartbeat.get_json()["device"]["connection_state"] == "online"
    assert heartbeat.get_json()["protocol"] == {
        "name": "spoolio-hardware",
        "version": "1",
        "weight_unit": "g",
        "weight_type": "gross",
        "max_gross_weight": 10000.0,
    }

    rotated = client.post(
        f"/api/hardware/devices/{device_id}/regenerate-key",
        headers=alice_headers,
    )
    assert rotated.status_code == 200
    new_key = rotated.get_json()["api_key"]
    assert new_key != original_key
    with app.app_context():
        stored_device = db.session.get(models.HardwareDevice, device_id)
        assert stored_device.api_key == models.HardwareDevice.hash_api_key(new_key)
        assert stored_device.api_key != new_key
    assert client.get(
        "/api/hardware/heartbeat", headers=_device_headers(original_key)
    ).status_code == 401
    assert client.get(
        "/api/hardware/heartbeat", headers=_device_headers(new_key)
    ).status_code == 200

    linked_spool = spool_factory(user_id=alice.id, nfc_tag_id="delete-device-tag")

    with app.app_context():
        stored_spool = db.session.get(models.FilamentSpool, linked_spool.id)
        stored_spool.hardware_device_id = device_id
        event = models.HardwareEvent(
            device_id=device_id,
            user_id=alice.id,
            event_type="ready",
        )
        orphan = models.OrphanTag(
            nfc_tag_id="delete-device-orphan",
            hardware_device_id=device_id,
            user_id=alice.id,
        )
        db.session.add_all([event, orphan])
        db.session.commit()
        event_id = event.id
        orphan_id = orphan.id

    assert client.delete(
        f"/api/hardware/devices/{device_id}", headers=alice_headers
    ).status_code == 200

    with app.app_context():
        assert db.session.get(models.HardwareDevice, device_id) is None
        assert db.session.get(models.FilamentSpool, linked_spool.id).hardware_device_id is None
        assert db.session.get(models.HardwareEvent, event_id).device_id is None
        assert db.session.get(models.OrphanTag, orphan_id).hardware_device_id is None


def test_hardware_wifi_config_lazily_reencrypts_legacy_ciphertext(
    app,
    client,
    user,
    hardware_device_factory,
):
    from extensions import db
    import models

    device_record = hardware_device_factory(user_id=user.id)

    with app.app_context():
        dedicated_key = app.config["WIFI_CREDENTIAL_KEY"]
        old_session_key = app.config["SECRET_KEY"]
        app.config["WIFI_CREDENTIAL_KEY"] = None
        device = db.session.get(models.HardwareDevice, device_record.id)
        device.set_wifi_credentials("Legacy network", "legacy-password")
        db.session.commit()
        legacy_ciphertext = bytes(device.wifi_password_encrypted)
        app.config["WIFI_CREDENTIAL_KEY"] = dedicated_key

    first_config = client.get(
        "/api/hardware/config/wifi",
        headers=_device_headers(device_record.api_key),
    )
    assert first_config.status_code == 200
    assert first_config.get_json()["wifi"]["password"] == "legacy-password"

    with app.app_context():
        migrated = db.session.get(models.HardwareDevice, device_record.id)
        assert migrated.wifi_password_encrypted != legacy_ciphertext
        app.config["SECRET_KEY"] = "rotated-session-secret-key-32-characters"
        assert migrated.get_wifi_password() == "legacy-password"
        app.config["SECRET_KEY"] = old_session_key


def test_events_live_status_and_display_cards_stay_with_the_device_owner(
    app,
    client,
    user_factory,
    hardware_device_factory,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-live", email="alice-live@example.com")
    bob = user_factory(username="bob-live", email="bob-live@example.com")
    alice_device = hardware_device_factory(user_id=alice.id, hardware_type="scale")
    alice_display = hardware_device_factory(user_id=alice.id, hardware_type="display")
    bob_device = hardware_device_factory(user_id=bob.id, hardware_type="scale")
    alice_spool = spool_factory(
        user_id=alice.id,
        nfc_tag_id="alice-live-tag",
        weight_remaining=700,
    )
    bob_spool = spool_factory(user_id=bob.id, nfc_tag_id="bob-live-tag")

    for event in (
        {"event_type": "stable_weight", "nfc_tag_id": "alice-live-tag", "weight": 900},
        {"event_type": "weight_update", "nfc_tag_id": "alice-live-tag", "weight": 700},
    ):
        response = client.post(
            "/api/hardware/event",
            headers=_device_headers(alice_device.api_key),
            json=event,
        )
        assert response.status_code == 200

    assert client.post(
        "/api/hardware/event",
        headers=_device_headers(bob_device.api_key),
        json={"event_type": "error", "message": "Bob private event"},
    ).status_code == 200

    from extensions import db
    import models

    with app.app_context():
        # A corrupted legacy association must not make another tenant's spool
        # metadata visible through the event serializer.
        corrupted = models.HardwareEvent(
            device_id=alice_device.id,
            user_id=alice.id,
            event_type="legacy",
            spool_id=bob_spool.id,
            created_at=utc_now_naive() - datetime.timedelta(seconds=5),
        )
        db.session.add(corrupted)
        db.session.commit()
        corrupted_id = corrupted.id

    recent = client.get(
        "/api/hardware/events/recent?limit=20",
        headers=auth_headers_factory(alice.id),
    )
    assert recent.status_code == 200
    events = recent.get_json()["events"]
    assert all(event["message"] != "Bob private event" for event in events)
    corrupted_json = next(event for event in events if event["id"] == corrupted_id)
    assert corrupted_json["spool_id"] is None
    assert corrupted_json["spool"] is None

    assert client.get(
        f"/api/hardware/live/status?device_id={bob_device.id}",
        headers=_device_headers(alice_display.api_key),
    ).status_code == 404
    live = client.get(
        f"/api/hardware/live/status?device_id={alice_device.id}",
        headers=_device_headers(alice_display.api_key),
    )
    assert live.status_code == 200
    assert live.get_json()["state"] == "uploaded"
    assert live.get_json()["gross_weight"] == 900
    assert live.get_json()["net_weight"] == 700
    assert live.get_json()["tare_applied"] == 200

    # Display-only devices do not emit measurement events themselves, so the
    # default view must show the latest event from any scale owned by the user.
    owner_live = client.get(
        "/api/hardware/live/status",
        headers=_device_headers(alice_display.api_key),
    )
    assert owner_live.status_code == 200
    assert owner_live.get_json()["state"] == "uploaded"
    assert owner_live.get_json()["last_event"]["nfc_tag_id"] == "alice-live-tag"
    assert owner_live.get_json()["device"]["id"] == alice_display.id

    cards = client.get(
        "/api/hardware/display/cards",
        headers=_device_headers(alice_device.api_key),
    )
    assert cards.status_code == 200
    inventory = next(
        card for card in cards.get_json()["cards"] if card["type"] == "inventory"
    )
    assert {row["id"] for row in inventory["data"]} == {alice_spool.id}


def test_admin_stats_metadata_and_firmware_lifecycle(
    app,
    client,
    user_factory,
    hardware_device_factory,
    spool_factory,
    auth_headers_factory,
):
    admin = user_factory(
        username="firmware-owner",
        email="firmware-owner@example.com",
        is_admin=True,
    )
    member = user_factory(username="firmware-member", email="firmware-member@example.com")
    admin_headers = auth_headers_factory(admin.id)
    member_headers = auth_headers_factory(member.id)
    member_spool = spool_factory(user_id=member.id, weight_remaining=125)
    device = hardware_device_factory(user_id=member.id, hardware_type="open-scale-v2")

    stats = client.get("/api/dashboard/stats", headers=member_headers)
    assert stats.status_code == 200
    assert stats.get_json()["total_spools"] == 1
    assert stats.get_json()["total_weight_remaining"] == 125
    assert member_spool.id

    assert client.get("/api/admin/metadata", headers=member_headers).status_code == 403
    metadata = client.get("/api/admin/metadata", headers=admin_headers)
    assert metadata.status_code == 200
    assert metadata.get_json()["features"]["firmware_ota"] is True
    assert client.get("/api/admin/firmware", headers=member_headers).status_code == 403

    upload = client.post(
        "/api/admin/firmware",
        headers=admin_headers,
        data={
            "version": "2.0.0",
            "hardware_type": "open-scale-v2",
            "is_active": "true",
            "release_notes": "First public hardware-agnostic build",
            "binary": (io.BytesIO(b"firmware-v2-bytes"), "scale-v2.bin"),
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201
    release = upload.get_json()["release"]
    assert release["is_active"] is True
    assert release["checksum"]

    latest = client.get(
        "/api/hardware/firmware/latest",
        headers=_device_headers(device.api_key),
    )
    assert latest.status_code == 200
    latest_release = latest.get_json()["release"]
    assert latest_release["id"] == release["id"]
    signed_url = latest_release["signed_download_url"]

    assert client.get(
        f"/api/hardware/firmware/download/{release['id']}"
    ).status_code == 403
    parsed = urlsplit(signed_url)
    downloaded = client.get(parsed.path + "?" + parsed.query)
    assert downloaded.status_code == 200
    assert downloaded.data == b"firmware-v2-bytes"
    assert downloaded.headers["X-Firmware-Version"] == "2.0.0"
    assert downloaded.headers["Cache-Control"] == "no-store"

    assert client.patch(
        f"/api/admin/firmware/{release['id']}",
        headers=member_headers,
        json={"version": "hijacked"},
    ).status_code == 403
    updated = client.patch(
        f"/api/admin/firmware/{release['id']}",
        headers=admin_headers,
        json={"version": "2.0.1", "release_notes": "Validated update"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["release"]["version"] == "2.0.1"

    from extensions import db
    import models

    with app.app_context():
        stored = db.session.get(models.FirmwareRelease, release["id"])
        assert stored.created_by == admin.id
        assert stored.file_size == len(b"firmware-v2-bytes")


def test_firmware_ota_surface_is_hidden_when_disabled(
    app,
    client,
    user_factory,
    hardware_device_factory,
    auth_headers_factory,
):
    admin = user_factory(
        username="disabled-ota-admin",
        email="disabled-ota-admin@example.com",
        is_admin=True,
    )
    device = hardware_device_factory(user_id=admin.id, hardware_type="open-scale-v2")
    admin_headers = auth_headers_factory(admin.id)

    app.config["FIRMWARE_OTA_ENABLED"] = False

    metadata = client.get("/api/admin/metadata", headers=admin_headers)
    assert metadata.status_code == 200
    assert metadata.get_json()["features"]["firmware_ota"] is False

    heartbeat = client.get(
        "/api/hardware/heartbeat",
        headers=_device_headers(device.api_key),
    )
    assert heartbeat.status_code == 200
    assert heartbeat.get_json()["firmware"] is None

    assert client.get("/api/admin/firmware", headers=admin_headers).status_code == 404
    assert client.get(
        "/api/hardware/firmware/latest",
        headers=_device_headers(device.api_key),
    ).status_code == 404
    assert client.get("/api/hardware/firmware/download/1").status_code == 404


def test_remaining_hardware_and_admin_json_routes_reject_bad_bodies(
    app,
    client,
    user_factory,
    hardware_device_factory,
    spool_factory,
    auth_headers_factory,
):
    admin = user_factory(
        username="json-admin",
        email="json-admin@example.com",
        is_admin=True,
    )
    device = hardware_device_factory(user_id=admin.id, hardware_type="scale")
    spool = spool_factory(user_id=admin.id, nfc_tag_id="finite-tag")
    headers = auth_headers_factory(admin.id)

    from extensions import db
    import models

    with app.app_context():
        release = models.FirmwareRelease(
            version="json-test",
            hardware_type="scale",
            file_name="json-test.bin",
            checksum="0" * 64,
            created_by=admin.id,
        )
        db.session.add(release)
        db.session.commit()
        release_id = release.id

    malformed = {
        "data": "{not-json",
        "content_type": "application/json",
    }
    responses = [
        client.post("/api/hardware/register", headers=headers, **malformed),
        client.put(
            f"/api/hardware/devices/{device.id}/wifi",
            headers=headers,
            **malformed,
        ),
        client.post(
            "/api/hardware/weight-update",
            headers=_device_headers(device.api_key),
            **malformed,
        ),
        client.post("/api/hardware/orphans/link", headers=headers, **malformed),
        client.post(
            "/api/hardware/event",
            headers=_device_headers(device.api_key),
            **malformed,
        ),
        client.patch(
            f"/api/admin/firmware/{release_id}",
            headers=headers,
            **malformed,
        ),
        client.post(
            f"/api/admin/firmware/{release_id}/notify",
            headers=headers,
            **malformed,
        ),
    ]
    assert all(response.status_code == 400 for response in responses)
    assert all(response.is_json for response in responses)

    assert client.post(
        "/api/hardware/register",
        headers=headers,
        json={"device_id": 123, "name": ["bad"]},
    ).status_code == 400
    assert client.post(
        "/api/hardware/event",
        headers=_device_headers(device.api_key),
        json={"event_type": {"bad": True}},
    ).status_code == 400
    assert client.post(
        "/api/hardware/event",
        headers=_device_headers(device.api_key),
        json={"event_type": "scan_start", "nfc_tag_id": ["bad"]},
    ).status_code == 400
    assert client.put(
        f"/api/hardware/devices/{device.id}/wifi",
        headers=headers,
        json={"ssid": "workshop", "clear_password": "false"},
    ).status_code == 400
    assert client.post(
        "/api/hardware/weight-update",
        headers=_device_headers(device.api_key),
        json={"nfc_tag_id": ["bad"], "weight": 100},
    ).status_code == 400
    for non_finite in (float("nan"), float("inf"), float("-inf")):
        assert client.post(
            "/api/hardware/weight-update",
            headers=_device_headers(device.api_key),
            json={"nfc_tag_id": "finite-tag", "weight": non_finite},
        ).status_code == 400
        assert client.post(
            "/api/hardware/event",
            headers=_device_headers(device.api_key),
            json={"event_type": "stable_weight", "weight": non_finite},
        ).status_code == 400
    assert client.post(
        "/api/hardware/orphans/link",
        headers=headers,
        json={"nfc_tag_id": "tag", "spool_id": {"bad": True}},
    ).status_code == 400
    assert client.post(
        "/api/hardware/orphans/link",
        headers=headers,
        json={"nfc_tag_id": "tag", "spool_id": spool.id + 0.9},
    ).status_code == 400
    assert client.patch(
        f"/api/admin/firmware/{release_id}",
        headers=headers,
        json={"is_active": "false"},
    ).status_code == 400
    assert client.patch(
        f"/api/admin/firmware/{release_id}",
        headers=headers,
        json={"version": ["bad"]},
    ).status_code == 400

    # The malformed calls must not mutate or delete unrelated owned records.
    with app.app_context():
        assert db.session.get(models.FilamentSpool, spool.id) is not None
        assert db.session.get(models.FirmwareRelease, release_id).is_active is False
