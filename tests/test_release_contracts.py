"""Regression checks for public release automation and safe examples."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_ci_tests_and_smoke_tests_without_host_credentials():
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text()

    assert "uses: actions/checkout@v7" in workflow
    assert "pull_request:" in workflow
    assert 'docker build --tag spoolio:test .' in workflow
    assert 'http://127.0.0.1:8000/api/health' in workflow
    assert 'http://127.0.0.1:8000/api/registration' in workflow
    assert 'data["action"] == "create-owner"' in workflow
    assert 'npm audit --omit=dev --audit-level=critical' in workflow
    assert 'python -m pip_audit -r requirements.txt' in workflow
    assert 'ghcr.io/gitleaks/gitleaks:v8.30.0' in workflow
    assert 'git /repo --no-banner --redact' in workflow
    assert 'SSH_PRIVATE_KEY' not in workflow
    assert 'scp ' not in workflow


def test_tagged_container_release_uses_ghcr_only():
    workflow = (REPO_ROOT / ".github/workflows/publish-container.yml").read_text()

    assert 'tags:' in workflow
    assert '- "v*"' in workflow
    assert 'packages: write' in workflow
    assert 'registry: ghcr.io' in workflow
    assert 'ghcr.io/${{ github.repository_owner }}/spoolio' in workflow
    assert 'push: true' in workflow
    assert 'workflow_dispatch:' not in workflow


def test_self_hosted_image_defaults_to_one_time_owner_registration():
    dockerfile = (REPO_ROOT / 'Dockerfile').read_text()
    compose = (REPO_ROOT / 'docker-compose.yml').read_text()

    assert 'REGISTRATION_MODE=first-user' in dockerfile
    assert 'REGISTRATION_MODE: ${REGISTRATION_MODE:-first-user}' in compose


def test_wal_aware_database_backup_helper_is_included():
    backup_helper = (REPO_ROOT / "scripts/backup_sqlite.py").read_text()

    assert "source.backup(destination)" in backup_helper
    assert "PRAGMA integrity_check" in backup_helper


def test_docker_uses_the_alembic_upgrade_path():
    docker_entrypoint = (REPO_ROOT / "docker/entrypoint.sh").read_text()
    setup_script = (REPO_ROOT / "setup_db.py").read_text()

    assert 'python setup_db.py' in docker_entrypoint
    assert "upgrade(directory=str(BASE_DIR / 'migrations'))" in setup_script
    assert 'db.create_all()' not in setup_script


def test_sqlite_backup_includes_committed_wal_pages(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "backup.db"

    with sqlite3.connect(source) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE events (value TEXT NOT NULL)")
        writer.commit()
        writer.execute("INSERT INTO events VALUES ('committed-in-wal')")
        writer.commit()
        assert source.with_name(f"{source.name}-wal").exists()

        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/backup_sqlite.py"),
                str(source),
                str(target),
            ],
            check=True,
        )

    with sqlite3.connect(target) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("SELECT value FROM events").fetchall() == [
            ("committed-in-wal",)
        ]


def test_persisted_secret_writer_round_trips_shell_metacharacters(tmp_path):
    target = tmp_path / ".spoolio_secrets"
    injection_marker = tmp_path / "injected"
    values = {
        "SECRET_KEY": (
            "session-secret-with-more-than-32-chars'; touch "
            f"{injection_marker}; echo '"
        ),
        "JWT_SECRET_KEY": 'jwt-secret-with-"quotes"-and-$-more-than-32-chars',
        "WIFI_CREDENTIAL_KEY": "wifi-secret-$(false)-with-more-than-32-chars",
        "REGISTRATION_TOKEN": "registration-secret-$value-with-more-than-16-chars",
    }
    environment = os.environ.copy()
    environment.update(values)

    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/write_secret_env.py"),
            str(target),
        ],
        check=True,
        env=environment,
    )
    loaded = subprocess.run(
        [
            "sh",
            "-c",
            '. "$1"; printf "%s\\n%s\\n%s\\n%s\\n" '
            '"$SECRET_KEY" "$JWT_SECRET_KEY" "$WIFI_CREDENTIAL_KEY" '
            '"$REGISTRATION_TOKEN"',
            "sh",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert loaded.stdout.splitlines() == [
        values["SECRET_KEY"],
        values["JWT_SECRET_KEY"],
        values["WIFI_CREDENTIAL_KEY"],
        values["REGISTRATION_TOKEN"],
    ]
    assert not injection_marker.exists()
    assert target.stat().st_mode & 0o777 == 0o600


def test_hardware_examples_do_not_embed_the_scrubbed_lan_plan():
    example_paths = sorted((REPO_ROOT / "hardware").rglob("*.ino"))
    assert example_paths
    examples = "\n".join(path.read_text() for path in example_paths)

    assert "192.168.1.250" not in examples
    assert "192.168.1.10" not in examples
    assert "WiFi.config(ip, gw, sn, dns)" not in examples


def test_release_excludes_generated_and_retired_trees():
    tracked_retired = subprocess.run(
        [
            "git",
            "ls-files",
            "static",
            "application",
            "mobile",
            "src",
            "shared",
            "Spool Tracker",
            "infra",
            "hardware/archive",
            "scripts/deploy.sh",
            "scripts/monitor.sh",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked_retired.stdout.strip() == ""


def test_tracked_tree_excludes_retired_personal_operator_identifiers():
    forbidden = (
        'mark' + '@wharry.co.uk',
        'Mark ' + '@ Spoolio',
        'admin' + '@spoolio.co.uk',
    )
    tracked = subprocess.run(
        ['git', 'ls-files', '-z'],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b'\0')

    matches = []
    for relative_bytes in tracked:
        if not relative_bytes:
            continue
        relative = relative_bytes.decode()
        content = (REPO_ROOT / relative).read_bytes().decode('utf-8', errors='ignore')
        for identifier in forbidden:
            if identifier.lower() in content.lower():
                matches.append(f'{relative}: contains retired operator identifier')

    assert matches == []


def test_license_security_guidance_and_contributor_templates_are_present():
    required = (
        'LICENSE',
        'CONTRIBUTING.md',
        'SECURITY.md',
        '.github/ISSUE_TEMPLATE/bug_report.md',
        '.github/ISSUE_TEMPLATE/feature_request.md',
        '.github/pull_request_template.md',
    )

    for relative in required:
        assert (REPO_ROOT / relative).is_file(), f'missing {relative}'
