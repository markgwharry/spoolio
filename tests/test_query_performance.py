"""Regression coverage for bounded-query collection endpoints."""

import contextlib
import datetime

from sqlalchemy import event

from time_utils import utc_now_naive


@contextlib.contextmanager
def _sql_statements(app):
    """Collect SQL executed inside a narrowly scoped operation."""
    from extensions import db

    statements = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    with app.app_context():
        engine = db.engine
        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            yield statements
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)


def test_hardware_collection_serializers_use_one_batch_query(
    app,
    user,
    spool_factory,
    hardware_device_factory,
):
    from blueprints._helpers import (
        event_spools,
        latest_linked_spools,
        serialize_hardware_device,
        serialize_hardware_event,
    )
    from extensions import db
    import models

    devices = [hardware_device_factory(user_id=user.id) for _ in range(4)]
    spools = [spool_factory(user_id=user.id) for _ in devices]

    with app.app_context():
        for offset, (device_record, spool_record) in enumerate(zip(devices, spools)):
            spool = db.session.get(models.FilamentSpool, spool_record.id)
            spool.hardware_device_id = device_record.id
            spool.hardware_last_update = utc_now_naive() + datetime.timedelta(
                seconds=offset
            )
            db.session.add(models.HardwareEvent(
                device_id=device_record.id,
                user_id=user.id,
                event_type="weight_update",
                spool_id=spool.id,
                weight=spool.weight_remaining,
            ))
        db.session.commit()
        device_models = models.HardwareDevice.query.order_by(models.HardwareDevice.id).all()
        event_models = models.HardwareEvent.query.order_by(models.HardwareEvent.id).all()

        with _sql_statements(app) as device_sql:
            latest = latest_linked_spools(device_models)
            payloads = [
                serialize_hardware_device(device, latest.get(device.id))
                for device in device_models
            ]
        assert len(device_sql) == 1
        assert all(payload["last_linked_spool"] is not None for payload in payloads)

        with _sql_statements(app) as event_sql:
            linked = event_spools(event_models)
            payloads = [
                serialize_hardware_event(hardware_event, linked.get(hardware_event.id))
                for hardware_event in event_models
            ]
        assert len(event_sql) == 1
        assert all(payload["spool"] is not None for payload in payloads)


def test_collection_endpoints_have_bounded_query_counts(
    app,
    client,
    user_factory,
    spool_factory,
    auth_headers_factory,
):
    from extensions import db
    import models

    admin = user_factory(
        username="query-admin",
        email="query-admin@example.com",
        is_admin=True,
    )
    owner = user_factory(username="query-owner", email="query-owner@example.com")
    spools = [spool_factory(user_id=owner.id) for _ in range(5)]

    with app.app_context():
        projects = [
            models.Project(user_id=owner.id, name=f"Query project {index}")
            for index in range(5)
        ]
        db.session.add_all(projects)
        db.session.flush()
        for spool_record, project in zip(spools, projects):
            db.session.add(models.SpoolHistory(
                spool_id=spool_record.id,
                project_id=project.id,
                date=utc_now_naive(),
                weight_used=10,
            ))
        for index in range(5):
            db.session.add(models.SpoolType(name=f"Query type {index}"))
            db.session.add(models.Manufacturer(name=f"Query maker {index}"))
        db.session.commit()

    with _sql_statements(app) as history_sql:
        response = client.get(
            "/api/spoolhistory/",
            headers=auth_headers_factory(owner.id),
        )
    assert response.status_code == 200
    assert len(response.get_json()["history"]) == 5
    assert len(history_sql) <= 2

    with _sql_statements(app) as metadata_sql:
        response = client.get(
            "/api/admin/metadata",
            headers=auth_headers_factory(admin.id),
        )
    assert response.status_code == 200
    assert len(metadata_sql) <= 4

    with _sql_statements(app) as vendor_sql:
        response = client.get(
            f"/spoolman/{owner.spoolman_token}/api/v1/vendor"
        )
    assert response.status_code == 200
    assert len(vendor_sql) <= 2
