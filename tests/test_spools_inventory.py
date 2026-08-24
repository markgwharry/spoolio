"""Core spool and shared inventory API coverage."""


def _spool_payload(reference_data, **overrides):
    payload = {
        "material_id": reference_data.material_id,
        "color_id": reference_data.color_id,
        "manufacturer_id": reference_data.manufacturer_id,
        "spool_type_id": reference_data.spool_type_id,
        "weight_start": 1000,
        "weight_remaining": 850,
    }
    payload.update(overrides)
    return payload


def _refill_payload(reference_data, **overrides):
    payload = {
        "material_id": reference_data.material_id,
        "color_id": reference_data.color_id,
        "manufacturer_id": reference_data.manufacturer_id,
        "weight_total": 750,
    }
    payload.update(overrides)
    return payload


def test_spool_crud_auto_groups_and_lookup_are_tenant_scoped(
    app,
    client,
    user_factory,
    reference_data,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-spools", email="alice-spools@example.com")
    bob = user_factory(username="bob-spools", email="bob-spools@example.com")
    bob_spool = spool_factory(user_id=bob.id)
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)

    first = client.post(
        "/api/spools/",
        headers=alice_headers,
        json=_spool_payload(
            reference_data,
            # Browser select values arrive as strings in the current UI.
            material_id=str(reference_data.material_id),
            color_id=str(reference_data.color_id),
            manufacturer_id=str(reference_data.manufacturer_id),
            spool_type_id=str(reference_data.spool_type_id),
            barcode="alice-barcode",
            serial_number="alice-serial",
            subtype="Silk",
        ),
    )
    assert first.status_code == 201
    first_spool = first.get_json()["spool"]

    second = client.post(
        "/api/spools/",
        headers=alice_headers,
        json=_spool_payload(reference_data, weight_remaining=600),
    )
    assert second.status_code == 201
    assert second.get_json()["spool"]["group_id"] == first_spool["group_id"]

    listing = client.get("/api/spools/", headers=alice_headers)
    assert listing.status_code == 200
    assert {row["id"] for row in listing.get_json()["spools"]} == {
        first_spool["id"],
        second.get_json()["spool"]["id"],
    }

    groups = client.get("/api/groups/", headers=alice_headers).get_json()["groups"]
    assert groups == [{
        "id": first_spool["group_id"],
        "name": "Red PLA",
        "material_id": reference_data.material_id,
        "color_id": reference_data.color_id,
        "user_id": alice.id,
    }]

    assert client.get(
        "/api/spools/barcode/alice-barcode", headers=bob_headers
    ).status_code == 404
    assert client.get(
        "/api/spools/serial/alice-serial", headers=alice_headers
    ).get_json()["spool"]["id"] == first_spool["id"]

    assert client.patch(
        f"/api/spools/{bob_spool.id}/",
        headers=alice_headers,
        json={"notes": "not mine"},
    ).status_code == 404
    assert client.delete(
        f"/api/spools/{bob_spool.id}/", headers=alice_headers
    ).status_code == 404

    updated = client.patch(
        f"/api/spools/{first_spool['id']}/",
        headers=alice_headers,
        json={"notes": "dry box"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["spool"]["notes"] == "dry box"
    assert client.delete(
        f"/api/spools/{first_spool['id']}/", headers=alice_headers
    ).status_code == 200

    import models

    with app.app_context():
        assert models.FilamentSpool.query.filter_by(id=bob_spool.id).one()
        assert models.FilamentGroup.query.filter_by(user_id=alice.id).count() == 1


def test_spool_creation_validates_references_weights_dates_and_json(
    client,
    user,
    reference_data,
    auth_headers_factory,
):
    headers = auth_headers_factory(user.id)

    invalid_payloads = [
        _spool_payload(reference_data, material_id=999999),
        _spool_payload(reference_data, manufacturer_id=[]),
        _spool_payload(reference_data, weight_start=-1),
        _spool_payload(reference_data, weight_start=100, weight_remaining=101),
        _spool_payload(reference_data, purchase_date="22/08/2026"),
    ]
    for payload in invalid_payloads:
        response = client.post("/api/spools/", headers=headers, json=payload)
        assert response.status_code == 400

    malformed = client.post(
        "/api/spools/",
        headers=headers,
        data="{bad-json",
        content_type="application/json",
    )
    assert malformed.status_code == 400


def test_spool_update_validates_numeric_reference_boolean_and_date_fields(
    app,
    client,
    user,
    spool,
    auth_headers_factory,
):
    headers = auth_headers_factory(user.id)
    endpoint = f"/api/spools/{spool.id}/"
    invalid_updates = [
        {"weight_remaining": -1},
        {"weight_start": "not-a-number"},
        {"weight_start": 100, "weight_remaining": 101},
        {"low_stock_threshold": "nan"},
        {"price": -0.01},
        {"manufacturer_id": 999999},
        {"manufacturer_id": []},
        {"manufacturer_id": {}},
        {"spool_type_id": 999999},
        {"spool_type_id": []},
        {"is_empty": "true"},
        {"notes": {"unexpected": "object"}},
        {"purchase_date": "22/08/2026"},
    ]
    for payload in invalid_updates:
        response = client.patch(endpoint, headers=headers, json=payload)
        assert response.status_code == 400, payload

    updated = client.patch(
        endpoint,
        headers=headers,
        json={
            "weight_start": "1200",
            "weight_remaining": "600",
            "low_stock_threshold": "125",
            "price": None,
            "purchase_date": "",
            "is_active": False,
        },
    )
    assert updated.status_code == 200
    result = updated.get_json()["spool"]
    assert result["weight_start"] == 1200
    assert result["weight_remaining"] == 600
    assert result["low_stock_threshold"] == 125
    assert result["price"] is None
    assert result["purchase_date"] is None
    assert result["is_active"] is False

    from extensions import db
    import models

    with app.app_context():
        stored = db.session.get(models.FilamentSpool, spool.id)
        assert stored.weight_start == 1200
        assert stored.weight_remaining == 600
        stored.weight_remaining = 1300
        db.session.commit()

    metadata_only = client.patch(
        endpoint,
        headers=headers,
        json={"notes": "refilled above original baseline"},
    )
    assert metadata_only.status_code == 200
    assert metadata_only.get_json()["spool"]["notes"] == (
        "refilled above original baseline"
    )


def test_spool_usage_caps_history_and_enforces_spool_and_project_ownership(
    app,
    client,
    user_factory,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-use", email="alice-use@example.com")
    bob = user_factory(username="bob-use", email="bob-use@example.com")
    alice_spool = spool_factory(
        user_id=alice.id,
        nfc_tag_id="emptied-tag",
        weight_remaining=100,
    )

    from extensions import db
    import models

    with app.app_context():
        alice_project = models.Project(user_id=alice.id, name="Alice build")
        bob_project = models.Project(user_id=bob.id, name="Bob build")
        db.session.add_all([alice_project, bob_project])
        db.session.commit()
        alice_project_id = alice_project.id
        bob_project_id = bob_project.id

    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)

    assert client.post(
        f"/api/spools/{alice_spool.id}/use",
        headers=bob_headers,
        json={"weight_used": 10},
    ).status_code == 404
    assert client.post(
        f"/api/spools/{alice_spool.id}/use",
        headers=alice_headers,
        json={"weight_used": -10},
    ).status_code == 400
    assert client.post(
        f"/api/spools/{alice_spool.id}/use",
        headers=alice_headers,
        json={"weight_used": 10, "project_id": bob_project_id},
    ).status_code == 400

    used = client.post(
        f"/api/spools/{alice_spool.id}/use",
        headers=alice_headers,
        json={
            "weight_used": 250,
            "project_id": alice_project_id,
            "notes": "final print",
        },
    )
    assert used.status_code == 200
    assert used.get_json()["spool"]["weight_remaining"] == 0
    assert used.get_json()["spool"]["nfc_tag_id"] is None

    with app.app_context():
        history = models.SpoolHistory.query.filter_by(spool_id=alice_spool.id).one()
        assert history.weight_used == 100
        assert history.project_id == alice_project_id
        empty = models.EmptySpool.query.filter_by(
            origin_spool_id=alice_spool.id,
            user_id=alice.id,
        ).one()
        event = models.HardwareEvent(
            user_id=alice.id,
            event_type="weight_update",
            spool_id=alice_spool.id,
        )
        db.session.add(event)
        db.session.commit()
        empty_id = empty.id
        event_id = event.id

    assert client.delete(
        f"/api/spools/{alice_spool.id}/",
        headers=alice_headers,
    ).status_code == 200

    with app.app_context():
        assert db.session.get(models.EmptySpool, empty_id).origin_spool_id is None
        assert db.session.get(models.HardwareEvent, event_id).spool_id is None


def test_refill_empty_spool_and_assembly_are_owner_scoped(
    app,
    client,
    user_factory,
    reference_data,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-refill", email="alice-refill@example.com")
    bob = user_factory(username="bob-refill", email="bob-refill@example.com")
    alice_origin = spool_factory(user_id=alice.id)
    bob_origin = spool_factory(user_id=bob.id)
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)

    assert client.post(
        "/api/empty-spools/",
        headers=alice_headers,
        json={
            "spool_type_id": reference_data.spool_type_id,
            "origin_spool_id": bob_origin.id,
        },
    ).status_code == 400

    empty_response = client.post(
        "/api/empty-spools/",
        headers=alice_headers,
        json={
            "spool_type_id": reference_data.spool_type_id,
            "origin_spool_id": alice_origin.id,
        },
    )
    assert empty_response.status_code == 201
    empty_id = empty_response.get_json()["empty_spool"]["id"]

    refill_response = client.post(
        "/api/refills/",
        headers=alice_headers,
        json=_refill_payload(reference_data, weight_remaining=0),
    )
    assert refill_response.status_code == 201
    assert refill_response.get_json()["refill"]["weight_remaining"] == 0

    usable_refill = client.post(
        "/api/refills/",
        headers=alice_headers,
        json=_refill_payload(reference_data, notes="vacuum packed"),
    ).get_json()["refill"]

    assert client.get("/api/refills/", headers=bob_headers).get_json()["refills"] == []
    assert client.patch(
        f"/api/refills/{usable_refill['id']}/",
        headers=bob_headers,
        json={"notes": "not mine"},
    ).status_code == 404
    assert client.post(
        "/api/assemble/",
        headers=bob_headers,
        json={"refill_id": usable_refill["id"], "empty_spool_id": empty_id},
    ).status_code == 404

    assembled = client.post(
        "/api/assemble/",
        headers=alice_headers,
        json={"refill_id": usable_refill["id"], "empty_spool_id": empty_id},
    )
    assert assembled.status_code == 200
    assert assembled.get_json()["spool"]["user_id"] == alice.id
    assert assembled.get_json()["spool"]["weight_remaining"] == 750

    from extensions import db
    import models

    with app.app_context():
        assert db.session.get(models.EmptySpool, empty_id) is None
        assert db.session.get(models.FilamentRefill, usable_refill["id"]) is None


def test_inventory_metadata_and_subtypes_have_expected_access_boundaries(
    app,
    client,
    user_factory,
    reference_data,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-inventory", email="alice-inventory@example.com")
    bob = user_factory(username="bob-inventory", email="bob-inventory@example.com")
    admin = user_factory(
        username="admin-inventory",
        email="admin-inventory@example.com",
        is_admin=True,
    )
    alice_spool = spool_factory(user_id=alice.id)
    bob_spool = spool_factory(user_id=bob.id)
    alice_headers = auth_headers_factory(alice.id)

    created = client.post(
        "/api/materials/", headers=alice_headers, json={"name": "PETG"}
    )
    duplicate = client.post(
        "/api/materials/", headers=alice_headers, json={"name": "petg"}
    )
    assert created.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.get_json()["id"] == created.get_json()["id"]
    assert client.post(
        "/api/spooltypes/",
        headers=alice_headers,
        json={"name": "Bad tare", "tare_weight": -1},
    ).status_code == 400

    assert client.delete(
        f"/api/manufacturers/{reference_data.manufacturer_id}",
        headers=alice_headers,
    ).status_code == 403
    assert client.delete(
        f"/api/manufacturers/{reference_data.manufacturer_id}",
        headers=auth_headers_factory(admin.id),
    ).status_code == 409

    from extensions import db
    import models

    with app.app_context():
        refill_manufacturer = models.Manufacturer(name="Refill only")
        empty_spool_type = models.SpoolType(name="Empty only", tare_weight=180)
        alice_group_id = db.session.get(
            models.FilamentSpool,
            alice_spool.id,
        ).group_id
        db.session.add_all([refill_manufacturer, empty_spool_type])
        db.session.flush()
        db.session.add_all([
            models.FilamentRefill(
                user_id=alice.id,
                material_id=reference_data.material_id,
                color_id=reference_data.color_id,
                manufacturer_id=refill_manufacturer.id,
                group_id=alice_group_id,
                weight_total=500,
                weight_remaining=500,
            ),
            models.EmptySpool(
                user_id=alice.id,
                spool_type_id=empty_spool_type.id,
            ),
        ])
        db.session.get(models.FilamentSpool, alice_spool.id).subtype = "Silk"
        db.session.get(models.FilamentSpool, bob_spool.id).subtype = "Silk"
        db.session.commit()
        refill_manufacturer_id = refill_manufacturer.id
        empty_spool_type_id = empty_spool_type.id

    admin_headers = auth_headers_factory(admin.id)
    refill_blocked = client.delete(
        f"/api/manufacturers/{refill_manufacturer_id}",
        headers=admin_headers,
    )
    assert refill_blocked.status_code == 409
    assert refill_blocked.get_json()["num_refills"] == 1
    empty_blocked = client.delete(
        f"/api/spooltypes/{empty_spool_type_id}",
        headers=admin_headers,
    )
    assert empty_blocked.status_code == 409
    assert empty_blocked.get_json()["num_empty_spools"] == 1

    assert client.get(
        "/api/subtypes/", headers=alice_headers
    ).get_json()["subtypes"] == ["Silk"]
    cleared = client.delete("/api/subtypes/Silk", headers=alice_headers)
    assert cleared.status_code == 200
    assert cleared.get_json()["rows_affected"] == 1

    with app.app_context():
        assert db.session.get(models.FilamentSpool, alice_spool.id).subtype is None
        assert db.session.get(models.FilamentSpool, bob_spool.id).subtype == "Silk"
