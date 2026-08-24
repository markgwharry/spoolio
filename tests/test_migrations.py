import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from sqlalchemy import inspect

from app import create_app
from extensions import db
import models


REPO_ROOT = Path(__file__).resolve().parents[1]
HEAD_REVISION = '2a6f74b19c3d'
HOT_PATH_INDEXES = {
    'ix_filament_spool_user_id',
    'ix_spool_history_spool_id',
    'ix_spool_history_project_id',
    'ix_bit_user_id',
    'ix_hardware_event_user_id',
    'ix_hardware_event_created_at',
}


def run_upgrade(database_path):
    environment = os.environ.copy()
    environment.update({
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_path}',
        'SECRET_KEY': 'migration-test-secret-key-that-is-long-enough',
        'JWT_SECRET_KEY': 'migration-test-jwt-key-that-is-long-enough',
        'WIFI_CREDENTIAL_KEY': 'migration-test-wifi-key-that-is-long-enough',
    })
    return subprocess.run(
        [sys.executable, '-m', 'flask', '--app', 'app:create_app', 'db', 'upgrade'],
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def run_setup(database_path):
    environment = os.environ.copy()
    environment.update({
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_path}',
        'SECRET_KEY': 'migration-test-secret-key-that-is-long-enough',
        'JWT_SECRET_KEY': 'migration-test-jwt-key-that-is-long-enough',
        'WIFI_CREDENTIAL_KEY': 'migration-test-wifi-key-that-is-long-enough',
    })
    return subprocess.run(
        [sys.executable, 'setup_db.py'],
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def create_current_schema(database_path):
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_path}',
        'SECRET_KEY': 'migration-test-secret-key-that-is-long-enough',
        'JWT_SECRET_KEY': 'migration-test-jwt-key-that-is-long-enough',
        'WIFI_CREDENTIAL_KEY': 'migration-test-wifi-key-that-is-long-enough',
    })
    with app.app_context():
        db.create_all()


def sqlite_rows(database_path, statement):
    with sqlite3.connect(database_path) as connection:
        return connection.execute(statement).fetchall()


def test_upgrade_builds_fresh_database_from_migrations(tmp_path):
    database_path = tmp_path / 'fresh.db'

    run_upgrade(database_path)
    run_upgrade(database_path)

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_path}',
        'SECRET_KEY': 'migration-test-secret-key-that-is-long-enough',
        'JWT_SECRET_KEY': 'migration-test-jwt-key-that-is-long-enough',
        'WIFI_CREDENTIAL_KEY': 'migration-test-wifi-key-that-is-long-enough',
    })
    with app.app_context():
        table_names = set(inspect(db.engine).get_table_names())

    assert set(db.metadata.tables) <= table_names
    assert 'registration_bootstrap' in table_names
    assert sqlite_rows(database_path, 'SELECT version_num FROM alembic_version') == [
        (HEAD_REVISION,),
    ]
    assert sqlite_rows(database_path, 'SELECT COUNT(*) FROM bit_category') == [(8,)]
    assert 'token_version' in {
        row[1] for row in sqlite_rows(database_path, "PRAGMA table_info('user')")
    }
    assert sqlite_rows(database_path, 'PRAGMA integrity_check') == [('ok',)]


def test_upgrade_adopts_current_schema_without_losing_rows(tmp_path):
    database_path = tmp_path / 'current.db'
    create_current_schema(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO material (name) VALUES ('PRESERVE_ME')")
        for index_name in HOT_PATH_INDEXES:
            connection.execute(f'DROP INDEX IF EXISTS {index_name}')
        connection.commit()

    assert sqlite_rows(
        database_path,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'",
    ) == []

    run_upgrade(database_path)

    assert sqlite_rows(database_path, 'SELECT name FROM material') == [('PRESERVE_ME',)]
    assert sqlite_rows(database_path, 'SELECT version_num FROM alembic_version') == [
        (HEAD_REVISION,),
    ]
    index_names = {
        row[0]
        for row in sqlite_rows(
            database_path,
            "SELECT name FROM sqlite_master WHERE type='index'",
        )
    }
    assert HOT_PATH_INDEXES <= index_names
    assert sqlite_rows(database_path, 'PRAGMA integrity_check') == [('ok',)]


def test_upgrade_repairs_supported_partial_schema(tmp_path):
    database_path = tmp_path / 'partial.db'
    create_current_schema(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO hardware_device (device_id, name, api_key, status, created_at) "
            "VALUES ('preserve-device', 'Preserve Device', 'preserve-key', 'offline', CURRENT_TIMESTAMP)"
        )
        connection.execute('ALTER TABLE hardware_device DROP COLUMN hardware_type')
        connection.commit()

    run_upgrade(database_path)

    hardware_columns = {
        row[1] for row in sqlite_rows(database_path, "PRAGMA table_info('hardware_device')")
    }
    assert 'hardware_type' in hardware_columns
    assert sqlite_rows(
        database_path,
        'SELECT device_id, name FROM hardware_device',
    ) == [('preserve-device', 'Preserve Device')]
    assert sqlite_rows(
        database_path,
        'SELECT api_key FROM hardware_device',
    ) == [(models.HardwareDevice.hash_api_key('preserve-key'),)]
    assert sqlite_rows(database_path, 'SELECT version_num FROM alembic_version') == [
        (HEAD_REVISION,),
    ]
    assert sqlite_rows(database_path, 'PRAGMA integrity_check') == [('ok',)]

    migrated_app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_path}',
        'SECRET_KEY': 'migration-test-secret-key-that-is-long-enough',
        'JWT_SECRET_KEY': 'migration-test-jwt-key-that-is-long-enough',
        'WIFI_CREDENTIAL_KEY': 'migration-test-wifi-key-that-is-long-enough',
    })
    response = migrated_app.test_client().get(
        '/api/hardware/heartbeat',
        headers={'Authorization': 'Bearer preserve-key'},
    )
    assert response.status_code == 200
    assert sqlite_rows(
        database_path,
        'SELECT api_key FROM hardware_device',
    ) == [(models.HardwareDevice.hash_api_key('preserve-key'),)]


def test_upgrade_does_not_double_hash_device_key_digests(tmp_path):
    database_path = tmp_path / 'device-keys.db'
    create_current_schema(database_path)
    existing_digest = models.HardwareDevice.hash_api_key('already-hashed-key')
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO hardware_device (device_id, name, api_key, status, created_at) "
            "VALUES ('legacy-device', 'Legacy Device', 'legacy-key', 'offline', CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO hardware_device (device_id, name, api_key, status, created_at) "
            "VALUES ('digested-device', 'Digested Device', ?, 'offline', CURRENT_TIMESTAMP)",
            (existing_digest,),
        )
        connection.commit()

    run_upgrade(database_path)
    run_upgrade(database_path)

    assert sqlite_rows(
        database_path,
        'SELECT device_id, api_key FROM hardware_device ORDER BY device_id',
    ) == [
        ('digested-device', existing_digest),
        ('legacy-device', models.HardwareDevice.hash_api_key('legacy-key')),
    ]


def test_setup_wrapper_upgrades_and_seeds_idempotently(tmp_path):
    database_path = tmp_path / 'setup.db'

    run_setup(database_path)
    run_setup(database_path)

    assert sqlite_rows(database_path, 'SELECT COUNT(*) FROM material') == [(3,)]
    assert sqlite_rows(database_path, 'SELECT COUNT(*) FROM color') == [(5,)]
    assert sqlite_rows(database_path, 'SELECT COUNT(*) FROM manufacturer') == [(3,)]
    assert sqlite_rows(database_path, 'SELECT COUNT(*) FROM spool_type') == [(3,)]
    assert sqlite_rows(database_path, 'SELECT version_num FROM alembic_version') == [
        (HEAD_REVISION,),
    ]
