"""Tests for the Spoolman-compatible integration API."""


def test_info_and_health(client, user):
    response = client.get(f"/spoolman/{user.spoolman_token}/api/v1/info")
    assert response.status_code == 200
    assert response.get_json()["db_type"] == "sqlite"
    assert "version" in response.get_json()

    response = client.get(f"/spoolman/{user.spoolman_token}/api/v1/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"


def test_invalid_token_rejected(client):
    response = client.get("/spoolman/not-a-real-token/api/v1/spool")
    assert response.status_code == 401


def test_invalid_token_probing_is_rate_limited(rate_limited_client):
    endpoints = [
        "/spoolman/not-a-real-token/api/v1/info",
        "/spoolman/not-a-real-token/api/v1/health",
        "/spoolman/not-a-real-token/api/v1/spool",
    ]
    responses = [
        rate_limited_client.get(
            endpoints[index % len(endpoints)],
            headers={"X-Real-IP": "198.51.100.10"},
        )
        for index in range(61)
    ]

    assert all(response.status_code == 401 for response in responses[:60])
    assert responses[60].status_code == 429
    assert responses[0].headers["X-RateLimit-Limit"] == "60"
    assert "X-RateLimit-Remaining" in responses[0].headers
    assert rate_limited_client.get(
        endpoints[0],
        headers={"X-Real-IP": "198.51.100.11"},
    ).status_code == 401


def test_spool_listing_and_shape(client, user, spool):
    response = client.get(f"/spoolman/{user.spoolman_token}/api/v1/spool")
    assert response.status_code == 200
    spools = response.get_json()
    assert len(spools) == 1

    result = spools[0]
    assert result["id"] == spool.id
    assert result["remaining_weight"] == 1000.0
    assert result["used_weight"] == 0.0
    assert result["spool_weight"] == 200.0
    assert result["filament"]["material"] == "PLA"
    assert result["filament"]["vendor"]["name"] == "Acme"
    assert result["filament"]["density"] > 0
    assert result["filament"]["diameter"] > 0
    assert result["remaining_length"] > 0


def test_use_by_weight_decrements_and_logs(app, client, user, spool):
    response = client.put(
        f"/spoolman/{user.spoolman_token}/api/v1/spool/{spool.id}/use",
        json={"use_weight": 250.0},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["remaining_weight"] == 750.0
    assert body["used_weight"] == 250.0
    assert body["last_used"] is not None

    with app.app_context():
        import models

        rows = models.SpoolHistory.query.filter_by(spool_id=spool.id).all()
        assert len(rows) == 1
        assert rows[0].weight_used == 250.0


def test_use_by_length_converts_to_weight(client, user, spool):
    from blueprints.spoolman import length_to_weight

    use_length = 1000.0
    expected_grams = length_to_weight(use_length)
    response = client.put(
        f"/spoolman/{user.spoolman_token}/api/v1/spool/{spool.id}/use",
        json={"use_length": use_length},
    )
    assert response.status_code == 200
    remaining = response.get_json()["remaining_weight"]
    assert abs(remaining - (1000.0 - expected_grams)) < 1e-6


def test_use_requires_exactly_one_param(client, user, spool):
    endpoint = f"/spoolman/{user.spoolman_token}/api/v1/spool/{spool.id}/use"

    response = client.put(endpoint, json={"use_weight": 10, "use_length": 10})
    assert response.status_code == 400

    response = client.put(endpoint, json={})
    assert response.status_code == 400

    response = client.put(endpoint, json=[1])
    assert response.status_code == 400


def test_use_caps_history_at_remaining(app, client, user, spool):
    from extensions import db
    import models

    with app.app_context():
        model = db.session.get(models.FilamentSpool, spool.id)
        model.weight_remaining = 100.0
        db.session.commit()

    response = client.put(
        f"/spoolman/{user.spoolman_token}/api/v1/spool/{spool.id}/use",
        json={"use_weight": 250.0},
    )
    assert response.status_code == 200
    assert response.get_json()["remaining_weight"] == 0.0

    with app.app_context():
        rows = models.SpoolHistory.query.filter_by(spool_id=spool.id).all()
        assert len(rows) == 1
        assert rows[0].weight_used == 100.0


def test_inactive_spool_excluded_by_default(app, client, user, spool):
    from extensions import db
    import models

    with app.app_context():
        base = db.session.get(models.FilamentSpool, spool.id)
        inactive = models.FilamentSpool(
            material_id=base.material_id,
            color_id=base.color_id,
            manufacturer_id=base.manufacturer_id,
            spool_type_id=base.spool_type_id,
            group_id=base.group_id,
            user_id=base.user_id,
            weight_start=1000.0,
            weight_remaining=1000.0,
            is_active=False,
        )
        db.session.add(inactive)
        db.session.commit()

    endpoint = f"/spoolman/{user.spoolman_token}/api/v1/spool"
    assert len(client.get(endpoint).get_json()) == 1
    assert len(client.get(f"{endpoint}?allow_archived=true").get_json()) == 2


def test_cross_user_spool_not_accessible(client, user_factory, spool):
    bob = user_factory(username="bob", email="bob@example.com", password="Bb123456")

    response = client.get(
        f"/spoolman/{bob.spoolman_token}/api/v1/spool/{spool.id}"
    )
    assert response.status_code == 404

    response = client.get(f"/spoolman/{bob.spoolman_token}/api/v1/spool")
    assert response.get_json() == []
