"""Decoded vendor tags (Bambu Lab) and identifier fallback on device endpoints."""

from hardware_tags import normalize_tag_metadata, suggest_color_name, suggest_subtype

TRAY_UUID = "A1B2C3D4E5F60718293A4B5C6D7E8F90"
CHIP_UID = "5AC3F21B"
BAMBU_TAG = {
    "format": "bambu",
    "chip_uid": CHIP_UID,
    "material": "PLA",
    "variant": "PLA Basic",
    "material_id": "GFA00",
    "variant_id": "A00-W1",
    "color_hex": "#FFFFFFFF",
    "spool_weight": 1000,
    "diameter": 1.75,
    "nozzle_temp_min": 190,
    "nozzle_temp_max": 230,
    "production_date": "2024_01_15_10_30",
}


def device_headers(device):
    return {"Authorization": f"Bearer {device.api_key}"}


def test_normalize_tag_metadata_keeps_valid_fields_and_drops_bad_ones():
    cleaned = normalize_tag_metadata({
        **BAMBU_TAG,
        "format": "Bambu",
        "spool_weight": float("nan"),
        "nozzle_temp_max": True,
        "variant": "\x00PLA Basic\x07",
        "unexpected": "ignored",
    })
    assert cleaned["format"] == "bambu"
    assert cleaned["color_hex"] == "#FFFFFF"
    assert cleaned["variant"] == "PLA Basic"
    assert cleaned["chip_uid"] == CHIP_UID
    assert "spool_weight" not in cleaned
    assert "nozzle_temp_max" not in cleaned
    assert "unexpected" not in cleaned
    assert normalize_tag_metadata({"material": "PLA"}) is None
    assert normalize_tag_metadata(None) is None


def test_suggestions_from_tag_values():
    assert suggest_color_name("#FFFFFF") == "white"
    assert suggest_color_name("#0A0A0A") == "black"
    assert suggest_color_name("not-a-colour") is None
    assert suggest_subtype("PLA", "PLA Basic") == "Basic"
    assert suggest_subtype("PETG", "PETG") is None
    assert suggest_subtype("PLA", "Support for PLA") == "Support for PLA"


def test_unknown_bambu_tag_is_recorded_with_decoded_metadata(
    client,
    user,
    hardware_device_factory,
    auth_headers_factory,
):
    device = hardware_device_factory(user_id=user.id)

    response = client.post(
        "/api/hardware/weight-update",
        headers=device_headers(device),
        json={
            "nfc_tag_id": TRAY_UUID,
            "fallback_tag_id": CHIP_UID,
            "weight": 1250.0,
            "tag": BAMBU_TAG,
        },
    )
    assert response.status_code == 404
    assert response.get_json()["orphan_recorded"] is True

    orphans = client.get(
        "/api/hardware/orphans",
        headers=auth_headers_factory(user.id),
    ).get_json()["orphans"]
    assert len(orphans) == 1
    assert orphans[0]["nfc_tag_id"] == TRAY_UUID
    assert orphans[0]["tag_format"] == "bambu"
    assert orphans[0]["tag_metadata"]["variant_id"] == "A00-W1"
    assert orphans[0]["suggestions"] == {
        "material": "PLA",
        "subtype": "Basic",
        "color": "white",
        "weight_start": 1000,
        "manufacturer": "Bambu Lab",
    }


def test_invalid_tag_or_fallback_types_are_rejected(client, user, hardware_device_factory):
    device = hardware_device_factory(user_id=user.id)
    for extra in ({"tag": "bambu"}, {"fallback_tag_id": 123}):
        response = client.post(
            "/api/hardware/weight-update",
            headers=device_headers(device),
            json={"nfc_tag_id": TRAY_UUID, "weight": 900.0, **extra},
        )
        assert response.status_code == 400


def test_lookup_and_weight_update_fall_back_to_chip_uid(
    app,
    client,
    user,
    spool_factory,
    hardware_device_factory,
):
    spool = spool_factory(user_id=user.id, nfc_tag_id=CHIP_UID)
    device = hardware_device_factory(user_id=user.id)

    missing = client.get(f"/api/hardware/spool/{TRAY_UUID}", headers=device_headers(device))
    assert missing.status_code == 404
    found = client.get(
        f"/api/hardware/spool/{TRAY_UUID}?fallback={CHIP_UID}",
        headers=device_headers(device),
    )
    assert found.status_code == 200
    assert found.get_json()["id"] == spool.id

    response = client.post(
        "/api/hardware/weight-update",
        headers=device_headers(device),
        json={
            "nfc_tag_id": TRAY_UUID,
            "fallback_tag_id": CHIP_UID,
            "weight": 900.0,
            "tag": BAMBU_TAG,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["net_weight"] == 700.0

    event = client.post(
        "/api/hardware/event",
        headers=device_headers(device),
        json={
            "event_type": "scan_start",
            "nfc_tag_id": TRAY_UUID,
            "fallback_tag_id": CHIP_UID,
        },
    )
    assert event.get_json()["event"]["spool_id"] == spool.id

    import models

    with app.app_context():
        assert models.OrphanTag.query.count() == 0
        latest = models.HardwareEvent.query.filter_by(event_type="weight_update").one()
        assert latest.nfc_tag_id == CHIP_UID


def test_primary_identifier_wins_over_fallback(
    client,
    user,
    spool_factory,
    hardware_device_factory,
):
    tray_spool = spool_factory(user_id=user.id, nfc_tag_id=TRAY_UUID)
    spool_factory(user_id=user.id, nfc_tag_id=CHIP_UID)
    device = hardware_device_factory(user_id=user.id)
    found = client.get(
        f"/api/hardware/spool/{TRAY_UUID}?fallback={CHIP_UID}",
        headers=device_headers(device),
    )
    assert found.get_json()["id"] == tray_spool.id


def test_fallback_never_resolves_another_tenants_spool(
    client,
    user_factory,
    spool_factory,
    hardware_device_factory,
):
    alice = user_factory(username="alice-tag", email="alice-tag@example.com")
    bob = user_factory(username="bob-tag", email="bob-tag@example.com")
    spool_factory(user_id=bob.id, nfc_tag_id=CHIP_UID)
    alice_device = hardware_device_factory(user_id=alice.id)

    lookup = client.get(
        f"/api/hardware/spool/{TRAY_UUID}?fallback={CHIP_UID}",
        headers=device_headers(alice_device),
    )
    assert lookup.status_code == 404
    update = client.post(
        "/api/hardware/weight-update",
        headers=device_headers(alice_device),
        json={"nfc_tag_id": TRAY_UUID, "fallback_tag_id": CHIP_UID, "weight": 900.0},
    )
    assert update.status_code == 404
    assert update.get_json()["orphan_recorded"] is True


def record_bambu_orphan(client, device, weight=1250.0, tag=BAMBU_TAG):
    response = client.post(
        "/api/hardware/weight-update",
        headers=device_headers(device),
        json={"nfc_tag_id": TRAY_UUID, "weight": weight, "tag": tag},
    )
    assert response.get_json()["orphan_recorded"] is True


def test_create_spool_from_bambu_orphan(
    app,
    client,
    user,
    reference_data,
    hardware_device_factory,
    auth_headers_factory,
):
    import models
    from extensions import db

    with app.app_context():
        db.session.add(models.Manufacturer(name="Bambu"))
        db.session.commit()
    device = hardware_device_factory(user_id=user.id)
    record_bambu_orphan(client, device)

    response = client.post(
        "/api/hardware/orphans/create-spool",
        headers=auth_headers_factory(user.id),
        json={
            "nfc_tag_id": TRAY_UUID,
            "spool_type_id": reference_data.spool_type_id,
            "color": "Jade White",
        },
    )
    assert response.status_code == 201, response.get_json()
    spool = response.get_json()["spool"]
    assert spool["nfc_tag_id"] == TRAY_UUID
    assert spool["weight_start"] == 1000.0
    # 1250 g gross minus the 200 g spool-type tare, capped at the full weight.
    assert spool["weight_remaining"] == 1000.0
    assert spool["subtype"] == "Basic"

    with app.app_context():
        created = db.session.get(models.FilamentSpool, spool["id"])
        assert created.material_id == reference_data.material_id  # reused "PLA"
        assert created.manufacturer.name == "Bambu"  # reused existing spelling
        assert created.color.name == "Jade White"
        assert created.hardware_device_id == device.id
        assert "A00-W1" in created.notes
        assert models.OrphanTag.query.count() == 0

    measured = client.post(
        "/api/hardware/weight-update",
        headers=device_headers(device),
        json={"nfc_tag_id": TRAY_UUID, "weight": 1100.0},
    )
    assert measured.status_code == 200
    assert measured.get_json()["net_weight"] == 900.0


def test_create_spool_from_orphan_validates_input(
    client,
    user,
    reference_data,
    hardware_device_factory,
    auth_headers_factory,
):
    device = hardware_device_factory(user_id=user.id)
    record_bambu_orphan(client, device)
    headers = auth_headers_factory(user.id)

    no_type = client.post(
        "/api/hardware/orphans/create-spool",
        headers=headers,
        json={"nfc_tag_id": TRAY_UUID},
    )
    assert no_type.status_code == 400
    bad_weight = client.post(
        "/api/hardware/orphans/create-spool",
        headers=headers,
        json={
            "nfc_tag_id": TRAY_UUID,
            "spool_type_id": reference_data.spool_type_id,
            "weight_start": -5,
        },
    )
    assert bad_weight.status_code == 400
    unknown = client.post(
        "/api/hardware/orphans/create-spool",
        headers=headers,
        json={"nfc_tag_id": "NOPE", "spool_type_id": reference_data.spool_type_id},
    )
    assert unknown.status_code == 404


def test_create_spool_from_orphan_requires_names_without_metadata(
    client,
    user,
    reference_data,
    hardware_device_factory,
    auth_headers_factory,
):
    device = hardware_device_factory(user_id=user.id)
    client.post(
        "/api/hardware/weight-update",
        headers=device_headers(device),
        json={"nfc_tag_id": "04A1B2C3D4", "weight": 500.0},
    )
    response = client.post(
        "/api/hardware/orphans/create-spool",
        headers=auth_headers_factory(user.id),
        json={"nfc_tag_id": "04A1B2C3D4", "spool_type_id": reference_data.spool_type_id},
    )
    assert response.status_code == 400
    assert "required" in response.get_json()["error"]


def test_create_spool_from_another_tenants_orphan_is_refused(
    app,
    client,
    user_factory,
    reference_data,
    hardware_device_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-create", email="alice-create@example.com")
    bob = user_factory(username="bob-create", email="bob-create@example.com")
    bob_device = hardware_device_factory(user_id=bob.id)
    record_bambu_orphan(client, bob_device)

    response = client.post(
        "/api/hardware/orphans/create-spool",
        headers=auth_headers_factory(alice.id),
        json={"nfc_tag_id": TRAY_UUID, "spool_type_id": reference_data.spool_type_id},
    )
    assert response.status_code == 404
    alice_orphans = client.get(
        "/api/hardware/orphans",
        headers=auth_headers_factory(alice.id),
    ).get_json()["orphans"]
    assert alice_orphans == []

    import models

    with app.app_context():
        assert models.FilamentSpool.query.count() == 0
        assert models.OrphanTag.query.count() == 1
