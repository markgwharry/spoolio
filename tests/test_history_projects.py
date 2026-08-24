"""Project, usage-history, analytics, and export coverage."""

import csv
import datetime
import io

from time_utils import utc_now_naive


def _create_project(client, headers, name="Open scale", **overrides):
    payload = {"name": name}
    payload.update(overrides)
    response = client.post("/api/projects/", headers=headers, json=payload)
    assert response.status_code == 201
    return response.get_json()


def test_project_crud_and_listing_are_tenant_scoped(
    app,
    client,
    user_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-project", email="alice-project@example.com")
    bob = user_factory(username="bob-project", email="bob-project@example.com")
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)
    assert client.post(
        "/api/projects/", headers=alice_headers, json={"name": 123}
    ).status_code == 400
    assert client.post(
        "/api/projects/",
        headers=alice_headers,
        json={"name": "Bad budget", "budget_grams": -1},
    ).status_code == 400
    alice_project = _create_project(
        client,
        alice_headers,
        description="Scale enclosure",
        budget_grams=500,
    )
    bob_project = _create_project(client, bob_headers, name="Bob private build")

    from extensions import db
    import models

    with app.app_context():
        legacy = models.Project(user_id=None, name="Legacy shared project")
        db.session.add(legacy)
        db.session.commit()
        legacy_id = legacy.id

    listing = client.get("/api/projects/", headers=alice_headers)
    assert listing.status_code == 200
    visible_ids = {project["id"] for project in listing.get_json()["projects"]}
    assert alice_project["id"] in visible_ids
    assert legacy_id in visible_ids
    assert bob_project["id"] not in visible_ids

    foreign_url = f"/api/projects/{bob_project['id']}"
    assert client.get(foreign_url, headers=alice_headers).status_code == 404
    assert client.put(
        foreign_url,
        headers=alice_headers,
        json={"name": "Hijacked"},
    ).status_code == 404
    assert client.delete(foreign_url, headers=alice_headers).status_code == 404

    assert client.get(
        f"/api/projects/{legacy_id}", headers=alice_headers
    ).status_code == 404

    updated = client.put(
        f"/api/projects/{alice_project['id']}",
        headers=alice_headers,
        json={"name": "Scale v2", "status": "completed", "budget_grams": 625},
    )
    assert updated.status_code == 200
    assert updated.get_json()["name"] == "Scale v2"
    assert updated.get_json()["status"] == "completed"
    assert client.delete(
        f"/api/projects/{alice_project['id']}", headers=alice_headers
    ).status_code == 200


def test_history_listing_patch_and_bulk_assignment_are_tenant_scoped(
    app,
    client,
    user_factory,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-history", email="alice-history@example.com")
    bob = user_factory(username="bob-history", email="bob-history@example.com")
    alice_spool = spool_factory(user_id=alice.id)
    bob_spool = spool_factory(user_id=bob.id)
    alice_headers = auth_headers_factory(alice.id)

    from extensions import db
    import models

    with app.app_context():
        bob_project = models.Project(user_id=bob.id, name="Bob private project")
        db.session.add(bob_project)
        db.session.flush()
        project = models.Project(user_id=alice.id, name="Batch assignment")
        alice_history = models.SpoolHistory(
            spool_id=alice_spool.id,
            date=utc_now_naive(),
            weight_used=25,
            notes="draft",
            project_id=bob_project.id,
        )
        bob_history = models.SpoolHistory(
            spool_id=bob_spool.id,
            date=utc_now_naive(),
            weight_used=50,
            notes="private",
        )
        db.session.add_all([project, alice_history, bob_history])
        db.session.commit()
        project_id = project.id
        alice_history_id = alice_history.id
        bob_history_id = bob_history.id

    listing = client.get("/api/spoolhistory/", headers=alice_headers)
    assert listing.status_code == 200
    assert [row["id"] for row in listing.get_json()["history"]] == [alice_history_id]
    assert listing.get_json()["history"][0]["project_id"] is None
    assert listing.get_json()["history"][0]["project_name"] is None

    assert client.patch(
        f"/api/spoolhistory/{bob_history_id}/",
        headers=alice_headers,
        json={"notes": "not mine"},
    ).status_code == 404

    updated = client.patch(
        f"/api/spoolhistory/{alice_history_id}/",
        headers=alice_headers,
        json={"notes": "confirmed", "project_id": project_id},
    )
    assert updated.status_code == 200
    assert updated.get_json()["history"]["notes"] == "confirmed"

    bulk = client.post(
        "/api/spoolhistory/bulk-assign",
        headers=alice_headers,
        json={
            "history_ids": [alice_history_id, bob_history_id],
            "project_id": None,
        },
    )
    assert bulk.status_code == 200
    assert bulk.get_json()["updated_count"] == 1

    with app.app_context():
        assert db.session.get(models.SpoolHistory, alice_history_id).project_id is None
        assert db.session.get(models.SpoolHistory, bob_history_id).notes == "private"


def test_project_analytics_and_csv_ignore_foreign_usage_and_escape_formulas(
    app,
    client,
    user_factory,
    spool_factory,
    auth_headers_factory,
):
    alice = user_factory(username="alice-export", email="alice-export@example.com")
    bob = user_factory(username="bob-export", email="bob-export@example.com")
    alice_spool = spool_factory(user_id=alice.id, weight_start=1000)
    bob_spool = spool_factory(user_id=bob.id, weight_start=1000)
    alice_headers = auth_headers_factory(alice.id)
    bob_headers = auth_headers_factory(bob.id)

    from extensions import db
    import models

    with app.app_context():
        project = models.Project(user_id=alice.id, name="Export target")
        alice_category = models.BitCategory(name="Fasteners")
        bob_category = models.BitCategory(name="Private parts")
        db.session.add_all([project, alice_category, bob_category])
        db.session.flush()
        alice_bit = models.Bit(
            user_id=alice.id,
            category_id=alice_category.id,
            name="M2 screw",
            quantity_total=100,
            quantity_remaining=98,
            price=10,
        )
        bob_bit = models.Bit(
            user_id=bob.id,
            category_id=bob_category.id,
            name="Secret component",
            quantity_total=100,
            quantity_remaining=90,
        )
        db.session.add_all([alice_bit, bob_bit])
        db.session.flush()
        now = utc_now_naive()
        db.session.add_all([
            models.SpoolHistory(
                spool_id=alice_spool.id,
                project_id=project.id,
                date=now,
                weight_used=40,
                notes="=HYPERLINK(\"https://example.test\")",
            ),
            # Deliberately corrupt cross-tenant links prove read paths recheck
            # the inventory owner instead of trusting project_id alone.
            models.SpoolHistory(
                spool_id=bob_spool.id,
                project_id=project.id,
                date=now,
                weight_used=900,
                notes="BOB PRIVATE",
            ),
            models.BitUsage(
                bit_id=alice_bit.id,
                project_id=project.id,
                quantity_used=2,
                date=now,
                notes="+SUM(1,1)",
            ),
            models.BitUsage(
                bit_id=bob_bit.id,
                project_id=project.id,
                quantity_used=10,
                date=now,
                notes="BOB BIT PRIVATE",
            ),
        ])
        db.session.commit()
        project_id = project.id

    analytics = client.get(
        f"/api/projects/{project_id}/analytics", headers=alice_headers
    )
    assert analytics.status_code == 200
    body = analytics.get_json()
    assert body["total_grams"] == 40
    assert body["entry_count"] == 1
    assert body["bits_total_used"] == 2
    assert body["bits_entry_count"] == 1

    assert client.get(
        f"/api/projects/{project_id}/analytics", headers=bob_headers
    ).status_code == 404
    assert client.get(
        f"/api/projects/{project_id}/export.csv", headers=bob_headers
    ).status_code == 404

    exported = client.get(
        f"/api/projects/{project_id}/export.csv", headers=alice_headers
    )
    assert exported.status_code == 200
    assert exported.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(exported.get_data(as_text=True))))
    assert [row["type"] for row in rows] == ["filament", "bit"]
    assert {row["notes"] for row in rows} == {
        "'=HYPERLINK(\"https://example.test\")",
        "'+SUM(1,1)",
    }
    assert "BOB PRIVATE" not in exported.get_data(as_text=True)


def test_deleting_project_preserves_usage_and_unassigns_it(
    app,
    client,
    user,
    spool,
    auth_headers_factory,
):
    headers = auth_headers_factory(user.id)
    project = _create_project(client, headers, name="Temporary project")

    used = client.post(
        f"/api/spools/{spool.id}/use",
        headers=headers,
        json={"weight_used": 10, "project_id": project["id"]},
    )
    assert used.status_code == 200
    assert client.delete(
        f"/api/projects/{project['id']}", headers=headers
    ).status_code == 200

    from extensions import db
    import models

    with app.app_context():
        history = models.SpoolHistory.query.filter_by(spool_id=spool.id).one()
        assert history.project_id is None
        assert db.session.get(models.Project, project["id"]) is None
