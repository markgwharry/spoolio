"""Bits inventory and usage-history coverage."""

import datetime

from time_utils import utc_now_naive


def _create_category(client, headers, name="Fasteners"):
    response = client.post(
        "/api/bitcategories/", headers=headers, json={"name": name}
    )
    assert response.status_code in (200, 201)
    return response.get_json()["id"]


def _create_bit(client, headers, default_category_id, **overrides):
    payload = {
        "category_id": default_category_id,
        "name": "M2 screw",
        "quantity_total": 100,
        "quantity_remaining": 80,
        "low_stock_threshold": 10,
        "unit": "pcs",
        "price": 12.50,
    }
    payload.update(overrides)
    return client.post("/api/bits/", headers=headers, json=payload)


def test_bit_crud_validation_and_listing_are_tenant_scoped(
    app,
    client,
    user_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-bits", email="alice-bits@example.com")
    bob = user_factory(username="bob-bits", email="bob-bits@example.com")
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)
    category_id = _create_category(client, alice_headers)
    assert _create_category(client, bob_headers, "fasteners") == category_id

    for overrides in (
        {"quantity_total": -1},
        {"quantity_total": 5, "quantity_remaining": 6},
        {"name": ""},
        {"category_id": 999999},
        {"category_id": []},
    ):
        assert _create_bit(
            client, alice_headers, category_id, **overrides
        ).status_code == 400

    created = _create_bit(client, alice_headers, category_id)
    assert created.status_code == 201
    bit_id = created.get_json()["bit"]["id"]
    assert client.get("/api/bits/", headers=bob_headers).get_json()["bits"] == []

    assert client.patch(
        f"/api/bits/{bit_id}/",
        headers=bob_headers,
        json={"name": "not mine"},
    ).status_code == 404
    assert client.delete(
        f"/api/bits/{bit_id}/", headers=bob_headers
    ).status_code == 404
    assert client.patch(
        f"/api/bits/{bit_id}/",
        headers=alice_headers,
        json={"quantity_remaining": -1},
    ).status_code == 400
    assert client.patch(
        f"/api/bits/{bit_id}/",
        headers=alice_headers,
        json={"category_id": 999999},
    ).status_code == 400

    updated = client.patch(
        f"/api/bits/{bit_id}/",
        headers=alice_headers,
        json={"name": "M2 x 6 screw", "quantity_remaining": 75},
    )
    assert updated.status_code == 200
    assert updated.get_json()["bit"]["name"] == "M2 x 6 screw"
    assert client.delete(
        f"/api/bits/{bit_id}/", headers=alice_headers
    ).status_code == 200

    from extensions import db
    import models

    with app.app_context():
        assert db.session.get(models.Bit, bit_id) is None


def test_restock_and_use_cap_real_inventory_and_enforce_project_ownership(
    app,
    client,
    user_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-bit-use", email="alice-bit-use@example.com")
    bob = user_factory(username="bob-bit-use", email="bob-bit-use@example.com")
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)
    category_id = _create_category(client, alice_headers, "Electronics")
    bit = _create_bit(
        client,
        alice_headers,
        category_id,
        name="JST connector",
        quantity_total=5,
        quantity_remaining=2,
        purchase_date="2026-08-01",
    ).get_json()["bit"]

    from extensions import db
    import models

    with app.app_context():
        alice_project = models.Project(user_id=alice.id, name="Scale V2")
        bob_project = models.Project(user_id=bob.id, name="Bob private")
        db.session.add_all([alice_project, bob_project])
        db.session.commit()
        alice_project_id = alice_project.id
        bob_project_id = bob_project.id

    assert client.post(
        f"/api/bits/{bit['id']}/restock",
        headers=bob_headers,
        json={"quantity": 5},
    ).status_code == 404
    assert client.post(
        f"/api/bits/{bit['id']}/restock",
        headers=alice_headers,
        json={"quantity": -1},
    ).status_code == 400
    restocked = client.post(
        f"/api/bits/{bit['id']}/restock",
        headers=alice_headers,
        # This is the shape sent by the current React restock form when its
        # optional metadata inputs are blank.
        json={"quantity": 3, "price": None, "purchase_date": None},
    )
    assert restocked.status_code == 200
    assert restocked.get_json()["bit"]["quantity_total"] == 8
    assert restocked.get_json()["bit"]["quantity_remaining"] == 5
    assert restocked.get_json()["bit"]["price"] == 12.5
    assert restocked.get_json()["bit"]["purchase_date"] == "2026-08-01"

    assert client.post(
        f"/api/bits/{bit['id']}/use",
        headers=alice_headers,
        json={"quantity_used": 1, "project_id": bob_project_id},
    ).status_code == 400
    used = client.post(
        f"/api/bits/{bit['id']}/use",
        headers=alice_headers,
        json={"quantity_used": 99, "project_id": alice_project_id},
    )
    assert used.status_code == 200
    assert used.get_json()["bit"]["quantity_remaining"] == 0
    assert used.get_json()["usage"]["quantity_used"] == 5

    with app.app_context():
        usage = models.BitUsage.query.filter_by(bit_id=bit["id"]).one()
        assert usage.quantity_used == 5
        assert usage.project_id == alice_project_id


def test_bit_usage_history_patch_delete_and_project_names_are_tenant_scoped(
    app,
    client,
    user_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-bit-history", email="alice-bit-history@example.com")
    bob = user_factory(username="bob-bit-history", email="bob-bit-history@example.com")
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)
    category_id = _create_category(client, alice_headers, "Displays")
    alice_bit = _create_bit(client, alice_headers, category_id).get_json()["bit"]
    bob_bit = _create_bit(
        client, bob_headers, category_id, name="Bob display"
    ).get_json()["bit"]

    from extensions import db
    import models

    with app.app_context():
        alice_project = models.Project(user_id=alice.id, name="Alice project")
        bob_project = models.Project(user_id=bob.id, name="Bob secret project")
        db.session.add_all([alice_project, bob_project])
        db.session.flush()
        alice_usage = models.BitUsage(
            bit_id=alice_bit["id"],
            project_id=bob_project.id,
            quantity_used=1,
            date=utc_now_naive(),
            notes="legacy link",
        )
        bob_usage = models.BitUsage(
            bit_id=bob_bit["id"],
            quantity_used=2,
            date=utc_now_naive(),
            notes="Bob private usage",
        )
        db.session.add_all([alice_usage, bob_usage])
        db.session.commit()
        alice_project_id = alice_project.id
        alice_usage_id = alice_usage.id
        bob_usage_id = bob_usage.id

    listing = client.get("/api/bitusage/", headers=alice_headers)
    assert listing.status_code == 200
    assert [row["id"] for row in listing.get_json()["usage"]] == [alice_usage_id]
    assert listing.get_json()["usage"][0]["project_id"] is None
    assert listing.get_json()["usage"][0]["project_name"] is None

    assert client.patch(
        f"/api/bitusage/{bob_usage_id}/",
        headers=alice_headers,
        json={"notes": "not mine"},
    ).status_code == 404
    assert client.delete(
        f"/api/bitusage/{bob_usage_id}/", headers=alice_headers
    ).status_code == 404

    updated = client.patch(
        f"/api/bitusage/{alice_usage_id}/",
        headers=alice_headers,
        json={"notes": "confirmed", "project_id": alice_project_id},
    )
    assert updated.status_code == 200
    assert updated.get_json()["usage"]["project_name"] == "Alice project"
    assert client.delete(
        f"/api/bitusage/{alice_usage_id}/", headers=alice_headers
    ).status_code == 200

    with app.app_context():
        assert db.session.get(models.BitUsage, alice_usage_id) is None
        assert db.session.get(models.BitUsage, bob_usage_id) is not None
