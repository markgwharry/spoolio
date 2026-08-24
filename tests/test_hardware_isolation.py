"""Cross-tenant regression tests for hardware and related owner boundaries."""


def _device_headers(device):
    return {"Authorization": f"Bearer {device.api_key}"}


def test_device_cannot_read_or_mutate_another_tenants_spool(
    app,
    client,
    user_factory,
    hardware_device_factory,
    spool_factory,
):
    alice = user_factory(username="alice-hw", email="alice-hw@example.com")
    bob = user_factory(username="bob-hw", email="bob-hw@example.com")
    alice_device = hardware_device_factory(user_id=alice.id)
    bob_device = hardware_device_factory(user_id=bob.id)
    bob_spool = spool_factory(user_id=bob.id, nfc_tag_id="bob-private-tag")

    response = client.get(
        "/api/hardware/spool/bob-private-tag",
        headers=_device_headers(alice_device),
    )
    assert response.status_code == 404

    response = client.post(
        "/api/hardware/weight-update",
        headers=_device_headers(alice_device),
        json={"nfc_tag_id": "bob-private-tag", "weight": 900.0},
    )
    assert response.status_code == 404

    response = client.post(
        "/api/hardware/event",
        headers=_device_headers(alice_device),
        json={"event_type": "scan_start", "nfc_tag_id": "bob-private-tag"},
    )
    assert response.status_code == 200
    assert response.get_json()["event"]["spool_id"] is None
    assert response.get_json()["event"]["spool"] is None

    from extensions import db
    import models

    with app.app_context():
        stored = db.session.get(models.FilamentSpool, bob_spool.id)
        assert stored.weight_remaining == 1000.0
        assert stored.hardware_device_id is None
        assert models.SpoolHistory.query.filter_by(spool_id=bob_spool.id).count() == 0
        alice_events = models.HardwareEvent.query.filter_by(user_id=alice.id).all()
        assert alice_events
        assert all(event.spool_id is None for event in alice_events)

    response = client.get(
        "/api/hardware/spool/bob-private-tag",
        headers=_device_headers(bob_device),
    )
    assert response.status_code == 200
    assert response.get_json()["id"] == bob_spool.id

    response = client.post(
        "/api/hardware/weight-update",
        headers=_device_headers(bob_device),
        json={"nfc_tag_id": "bob-private-tag", "weight": 900.0},
    )
    assert response.status_code == 200
    assert response.get_json()["net_weight"] == 700.0

    with app.app_context():
        stored = db.session.get(models.FilamentSpool, bob_spool.id)
        assert stored.weight_remaining == 700.0
        assert stored.hardware_device_id == bob_device.id
        assert models.SpoolHistory.query.filter_by(spool_id=bob_spool.id).count() == 1


def test_duplicate_unknown_tag_scan_does_not_overwrite_another_tenants_orphan(
    app,
    client,
    user_factory,
    hardware_device_factory,
):
    alice = user_factory(username="alice-orphan", email="alice-orphan@example.com")
    bob = user_factory(username="bob-orphan", email="bob-orphan@example.com")
    alice_device = hardware_device_factory(user_id=alice.id)
    bob_device = hardware_device_factory(user_id=bob.id)

    first = client.post(
        "/api/hardware/weight-update",
        headers=_device_headers(alice_device),
        json={"nfc_tag_id": "shared-unknown-tag", "weight": 650.0},
    )
    assert first.status_code == 404
    assert first.get_json()["orphan_recorded"] is True

    second = client.post(
        "/api/hardware/weight-update",
        headers=_device_headers(bob_device),
        json={"nfc_tag_id": "shared-unknown-tag", "weight": 525.0},
    )
    assert second.status_code == 404
    assert second.get_json()["orphan_recorded"] is False
    assert second.get_json()["orphan_conflict"] is True

    import models

    with app.app_context():
        orphans = models.OrphanTag.query.filter_by(
            nfc_tag_id="shared-unknown-tag"
        ).all()
        assert len(orphans) == 1
        assert orphans[0].user_id == alice.id
        assert orphans[0].hardware_device_id == alice_device.id
        assert orphans[0].last_weight == 650.0

        bob_event = models.HardwareEvent.query.filter_by(
            user_id=bob.id,
            event_type="orphan",
        ).one()
        assert bob_event.spool_id is None


def test_orphan_link_accepts_legacy_rows_but_delete_requires_owned_records(
    app,
    client,
    user_factory,
    hardware_device_factory,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-link", email="alice-link@example.com")
    bob = user_factory(username="bob-link", email="bob-link@example.com")
    alice_spool = spool_factory(user_id=alice.id)
    bob_device = hardware_device_factory(user_id=bob.id)

    from extensions import db
    import models

    with app.app_context():
        bob_orphan = models.OrphanTag(nfc_tag_id="bob-orphan", user_id=bob.id)
        null_orphan = models.OrphanTag(
            nfc_tag_id="legacy-orphan",
            user_id=None,
            last_weight=750.0,
        )
        foreign_legacy_orphan = models.OrphanTag(
            nfc_tag_id="foreign-legacy-orphan",
            user_id=None,
            last_weight=625.0,
            hardware_device_id=bob_device.id,
        )
        alice_orphan = models.OrphanTag(nfc_tag_id="alice-orphan", user_id=alice.id)
        db.session.add_all([
            bob_orphan,
            null_orphan,
            foreign_legacy_orphan,
            alice_orphan,
        ])
        db.session.commit()
        bob_orphan_id = bob_orphan.id
        null_orphan_id = null_orphan.id
        foreign_legacy_orphan_id = foreign_legacy_orphan.id
        alice_orphan_id = alice_orphan.id

    alice_headers = auth_headers_factory(alice.id)
    response = client.get("/api/hardware/orphans", headers=alice_headers)
    assert response.status_code == 200
    visible_tags = {row["nfc_tag_id"] for row in response.get_json()["orphans"]}
    assert "legacy-orphan" in visible_tags
    assert "foreign-legacy-orphan" not in visible_tags

    response = client.post(
        "/api/hardware/orphans/link",
        headers=alice_headers,
        json={"nfc_tag_id": "bob-orphan", "spool_id": alice_spool.id},
    )
    assert response.status_code == 409

    response = client.post(
        "/api/hardware/orphans/link",
        headers=alice_headers,
        json={
            "nfc_tag_id": "foreign-legacy-orphan",
            "spool_id": alice_spool.id,
        },
    )
    assert response.status_code == 409

    response = client.post(
        "/api/hardware/orphans/link",
        headers=alice_headers,
        json={"nfc_tag_id": "legacy-orphan", "spool_id": alice_spool.id},
    )
    assert response.status_code == 200
    assert response.get_json()["spool"]["nfc_tag_id"] == "legacy-orphan"

    assert client.delete(
        "/api/hardware/orphans/bob-orphan", headers=alice_headers
    ).status_code == 404
    assert client.delete(
        "/api/hardware/orphans/legacy-orphan", headers=alice_headers
    ).status_code == 404
    assert client.delete(
        "/api/hardware/orphans/alice-orphan", headers=alice_headers
    ).status_code == 200

    with app.app_context():
        stored_spool = db.session.get(models.FilamentSpool, alice_spool.id)
        assert stored_spool.nfc_tag_id == "legacy-orphan"
        assert stored_spool.weight_remaining == 550.0
        assert stored_spool.hardware_device_id is None
        assert db.session.get(models.OrphanTag, bob_orphan_id) is not None
        assert db.session.get(models.OrphanTag, null_orphan_id) is None
        assert db.session.get(models.OrphanTag, foreign_legacy_orphan_id) is not None
        assert db.session.get(models.OrphanTag, alice_orphan_id) is None


def test_empty_spool_delete_rejects_foreign_and_unowned_rows(
    app,
    client,
    user_factory,
    reference_data,
    auth_headers_factory,
):
    alice = user_factory(username="alice-empty", email="alice-empty@example.com")
    bob = user_factory(username="bob-empty", email="bob-empty@example.com")

    from extensions import db
    import models

    with app.app_context():
        alice_empty = models.EmptySpool(
            user_id=alice.id, spool_type_id=reference_data.spool_type_id
        )
        bob_empty = models.EmptySpool(
            user_id=bob.id, spool_type_id=reference_data.spool_type_id
        )
        null_empty = models.EmptySpool(
            user_id=None, spool_type_id=reference_data.spool_type_id
        )
        db.session.add_all([alice_empty, bob_empty, null_empty])
        db.session.commit()
        alice_empty_id = alice_empty.id
        bob_empty_id = bob_empty.id
        null_empty_id = null_empty.id

    headers = auth_headers_factory(alice.id)
    assert client.delete(
        f"/api/empty-spools/{bob_empty_id}/", headers=headers
    ).status_code == 404
    assert client.delete(
        f"/api/empty-spools/{null_empty_id}/", headers=headers
    ).status_code == 404
    assert client.delete(
        f"/api/empty-spools/{alice_empty_id}/", headers=headers
    ).status_code == 200

    with app.app_context():
        assert db.session.get(models.EmptySpool, alice_empty_id) is None
        assert db.session.get(models.EmptySpool, bob_empty_id) is not None
        assert db.session.get(models.EmptySpool, null_empty_id) is not None


def test_firmware_notifications_only_target_matching_device_owners(
    app,
    client,
    monkeypatch,
    user_factory,
    hardware_device_factory,
    auth_headers_factory,
):
    admin = user_factory(
        username="firmware-admin",
        email="firmware-admin@example.com",
        is_admin=True,
    )
    matching_owner = user_factory(
        username="matching-owner",
        email="matching-owner@example.com",
    )
    user_factory(username="bystander", email="bystander@example.com")
    hardware_device_factory(user_id=matching_owner.id, hardware_type="esp32-cyd")

    from extensions import db
    import models

    with app.app_context():
        matching_release = models.FirmwareRelease(
            version="1.2.3",
            hardware_type="esp32-cyd",
            file_name="firmware-1.2.3.bin",
            checksum="abc123",
            created_by=admin.id,
        )
        unmatched_release = models.FirmwareRelease(
            version="9.9.9",
            hardware_type="unowned-hardware",
            file_name="firmware-9.9.9.bin",
            checksum="def456",
            created_by=admin.id,
        )
        db.session.add_all([matching_release, unmatched_release])
        db.session.commit()
        matching_release_id = matching_release.id
        unmatched_release_id = unmatched_release.id

    notified = []

    def fake_notification(user, *_args, **_kwargs):
        notified.append(user.email)
        return True

    monkeypatch.setattr(
        "blueprints.admin.send_firmware_release_notification",
        fake_notification,
    )
    headers = auth_headers_factory(admin.id)

    response = client.post(
        f"/api/admin/firmware/{matching_release_id}/notify",
        headers=headers,
        json={},
    )
    assert response.status_code == 200
    assert response.get_json()["recipient_count"] == 1
    assert response.get_json()["requested"] == 1
    assert response.get_json()["notified"] == 1
    assert notified == [matching_owner.email]

    response = client.post(
        f"/api/admin/firmware/{unmatched_release_id}/notify",
        headers=headers,
        json={},
    )
    assert response.status_code == 200
    assert response.get_json()["recipient_count"] == 0
    assert response.get_json()["requested"] == 0
    assert response.get_json()["notified"] == 0
    assert notified == [matching_owner.email]
