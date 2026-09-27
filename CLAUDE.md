# Filamentarium (formerly Spoolio)

A self-hosted 3D-printing filament tracker with IoT hardware. It tracks spools by weight, manages projects and print usage, and takes live weights, NFC scans and Bambu Lab spool tags from ESP8266/ESP32 scales and displays. It is being renamed and redesigned around a "library" model: spools are catalogued, shelved, lent to printers and returned.

## Start here (for agents)

- **`design/`** holds the Filamentarium design system. It contains `README.md` (the brand book: voice, vocabulary, colour, type, patterns), `tokens.json`/`tokens.css`, and reference components in `components/`. Read the brand book before touching any UI.
- Directory-scoped context lives in `frontend/CLAUDE.md` and `hardware/CLAUDE.md`.
- The protocol spec is `docs/HARDWARE_PROTOCOL.md`, and the Spoolman-compatible API is described in `docs/SPOOLMAN_API.md`.
- Hosted-service operations (production deploy, host config, operator runbooks) live in a separate private ops repo, not here.

## Tech stack

- **Backend:** Flask 3.1, SQLAlchemy and SQLite by default (Postgres/MySQL via `SQLALCHEMY_DATABASE_URI`), in `app.py` and `models.py`.
- **Frontend:** React 19, React Router 7 and Vite (`frontend/src/`), with Vitest for tests.
- **Hardware:** ESP8266 (HX711 load cell, PN532 NFC, OLED) and an ESP32 Cheap Yellow Display client (`hardware/`).
- **Auth:** JWT (Flask-JWT-Extended) with `token_version` revocation. Hardware devices use per-device API keys, stored as SHA-256 digests.
- **Self-hosting:** `Dockerfile` and `docker-compose.yml`, with the image published to ghcr on `v*` tags.

## Commands

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export FLASK_ENV=development
python setup_db.py
python -m pytest                      # pytest.ini turns DeprecationWarnings into errors
python -m pip_audit -r requirements.txt

# Frontend
cd frontend && npm ci
npm start                             # proxies /api and /spoolman to :5000
npm test
npm run build
npm audit --omit=dev --audit-level=critical

# Container (needs a Docker daemon)
docker build --tag spoolio:test .     # becomes filamentarium:test with the rename
```

Run the backend and frontend gates before every commit.

## Key files

- `models.py`: all models (User, FilamentSpool, FilamentGroup, SpoolHistory, Project, HardwareDevice, HardwareEvent, OrphanTag, FirmwareRelease, FilamentRefill, EmptySpool, Bit…).
- `blueprints/`: the REST API by domain. `_helpers.py` holds the serializers and shared utilities.
- `hardware_protocol.py`, `hardware_tags.py`, `blueprints/hardware.py` and `hardware_comms.py`: the device protocol v1, Bambu tag parsing, and the device and orphan-tag endpoints.
- `frontend/src/AuthContext.jsx`: `authFetch`. ALL authenticated API calls go through it.
- `frontend/src/Dashboard.jsx` is a compact container. Its logic lives in `src/hooks/` and `src/components/dashboard/`.
- `migrations/versions/`: Alembic is the only way to change the schema. `setup_db.py` upgrades, then seeds reference data.
- `tests/test_release_contracts.py` asserts publication-safety rules and literal strings in CI, compose and the Dockerfile. Update it deliberately; never weaken it.

## API structure

All endpoints are under `/api`, registered in `blueprints/__init__.py`.

- **Auth and account:** registration, waitlist/owner setup, login/refresh, email verification, password reset, account.
- **Inventory:** `/api/spools`, `/api/groups`, `/api/refills`, `/api/emptyspools`, the metadata tables, `/api/projects`, `/api/spoolhistory` and `/api/bits`.
- **Hardware, user-facing:** `/api/hardware/devices` and `/api/hardware/orphans` (list, link, create-spool, delete).
- **Hardware, device-facing:** heartbeat, spool lookup, weight update, events and display cards, all using `@hardware_auth_required`.
- **Spoolman compatibility:** `/spoolman/<token>/api/v1/*`, registered **without** `/api`. It is the model for per-user query scoping.

## Development rules

- **Every list and detail query is scoped** to the authenticated user or the authenticated device's owner. New endpoints need cross-user isolation tests.
- Auth decorators are `@jwt_required()`, `@hardware_auth_required` and `@admin_required`.
- Never commit Wi-Fi details, device keys, tokens, production data, LAN IPs or personal addresses. Use the `YOUR_*` placeholders.
- Hardware changes are not done until they have been physically flashed and bench-tested. Say in the PR what was tested.
- Keep PRs focused. State any migration, deployment, security or physical-validation boundary.

## Rules for the rename

Nothing may break an existing Spoolio install or a flashed device.

- **Env vars:** read `FILAMENTARIUM_*` first, fall back to `SPOOLIO_*`, and log a deprecation warning when the old name is used.
- **Secrets file:** if `/app/instance/.spoolio_secrets` exists, keep using it. Losing it makes stored device Wi-Fi passwords undecryptable.
- **Docker volumes:** keep `spoolio-data` and `spoolio-shared`, pinned with an explicit `name:`.
- **Hardware protocol:** keep `HARDWARE_PROTOCOL_NAME = "spoolio-hardware"` for v1. It is a published compatibility promise.
- **Firmware host:** flashed firmware calls `www.spoolio.co.uk`, and that must keep working. New firmware takes the host from setup and defaults to `https://filamentarium.app`.
- **Upgrade test:** every rename change needs a test that starts from a Spoolio-era configuration.

## Rules for the frontend (design system)

- **Styles come from `design/tokens.css` only.** No raw hex values and no `!important` in new code.
- **Two themes:** Daylight (the default) and Reading lamp, set with `data-theme="daylight|lamp"` on `<html>`. Follow `prefers-color-scheme`, and let the toggle override it.
- **Fonts:** Literata for names of things, IBM Plex Sans for the UI, IBM Plex Mono for weights, dates and accession numbers. Self-host them.
- **Filament colours** appear only on the neutral `swatch-ground`, via Swatch, SpoolSpine or SpoolDrawing.
- **Vocabulary:** Accession, Shelf/dry box, Lend/Return, Circulation, Ledger, Acquisitions, Archive, Bookplate, Marginalia. Accession numbers read "No. 0142".
- **Copy:** British English and sentence case. No emoji, no exclamation marks. Units are written `612 g`, `190–230 °C`, `18% RH`.
- **Controls** are at least 44px tall. Use `<button>`, never `<div onClick>`. Reuse `ConfirmDialog` for modals.
