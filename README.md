# Spoolio

Spoolio is a self-hostable inventory manager for 3D-printing filament. Track
spools by weight, material, colour, manufacturer and spool type; manage print
projects and budgets; and (optionally) wire up ESP8266/ESP32 hardware with NFC
and a load cell for automatic, real-time weight tracking.

- **Backend:** Flask 3 + SQLAlchemy (SQLite by default, Postgres-ready)
- **Frontend:** React 19 single-page app
- **Hardware (optional):** ESP8266/ESP32 + HX711 load cell + PN532 NFC
- **Auth:** JWT for users, per-device API keys for hardware

---

## Quick start (Docker)

The fastest way to run your own Spoolio server. Requires Docker with the
Compose plugin.

```bash
git clone https://github.com/markgwharry/spoolio.git
cd spoolio
cp .env.example .env        # optional — sensible defaults work out of the box
docker compose up -d
docker compose logs spoolio          # copy the "Owner setup code"
```

This pulls the published image for both 64-bit Intel/AMD and 64-bit Arm hosts.
For a reproducible deployment, set `SPOOLIO_IMAGE` in `.env` to a numbered tag
such as `ghcr.io/markgwharry/spoolio:0.1.0`. To build the checked-out source
instead, run `docker compose up -d --build`.

Then open <http://localhost:8000> and create the owner account. This one-time
account is verified automatically and receives administrator access; browser
registration closes as soon as it has been created. The setup code prevents a
different network visitor from claiming the administrator account first.

On first run the container automatically:
- generates and persists strong `SECRET_KEY` / `JWT_SECRET_KEY` values,
- creates the SQLite database and seeds common materials/colours/manufacturers,
- builds and serves the React frontend.

Your data lives in named Docker volumes (`spoolio-data`, `spoolio-shared`) and
survives restarts and image rebuilds.

> **Email is optional.** The one-time owner account does not need email
> verification. Password-reset and hosted-waitlist email require SMTP; see
> `.env.example` to enable it.

Create additional users from a trusted terminal without reopening public
registration. The command prompts for the password without placing it in shell
history:

```bash
docker compose exec spoolio flask create-user --username alice --email alice@example.com
# Add --admin only when the new account should administer shared metadata.
```

### Common operations

```bash
docker compose logs -f spoolio      # tail logs
docker compose down                 # stop (data preserved in volumes)
docker compose pull && docker compose up -d --no-build   # update release image
```

---

## Local development

Run the backend and frontend separately for hot-reload.

**Backend:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_ENV=development      # uses dev fallback secrets
python setup_db.py                # Alembic upgrade + idempotent reference seed
python app.py                     # serves on http://localhost:5000
```

Database operator and rehearsal steps are documented in
[`docs/deployment/DATABASE_MIGRATIONS.md`](docs/deployment/DATABASE_MIGRATIONS.md).

**Frontend:**
```bash
cd frontend
npm install
npm start                         # http://localhost:5173, proxying the API
```

The frontend toolchain requires Node.js 22.12 or newer.

To produce a production bundle served by Flask, run `./build_frontend.sh`,
which builds the React app into `static/`.

---

## Configuration

All configuration is via environment variables (or a `.env` file). The most
common ones:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SPOOLIO_IMAGE` | `ghcr.io/markgwharry/spoolio:latest` | Compose image; pin a release tag for reproducibility |
| `FLASK_ENV` | `production` | `production` enforces strong secrets |
| `SECRET_KEY` | _(auto in Docker)_ | Flask session/crypto key (≥32 chars in prod) |
| `JWT_SECRET_KEY` | _(auto in Docker)_ | JWT signing key (≥32 chars in prod) |
| `REGISTRATION_MODE` | app: `waitlist`; Docker: `first-user` | `first-user`, `waitlist`, or `closed` onboarding |
| `REGISTRATION_TOKEN` | _(auto in Docker)_ | Secret code required to claim the first owner account |
| `DATABASE_URL` | SQLite under `instance/` | SQLAlchemy database URI |
| `CORS_ORIGINS` | localhost | Comma-separated allowed browser origins |
| `MAX_CONTENT_LENGTH` | `16777216` | Maximum request-body size in bytes (16 MiB) |
| `FIRMWARE_OTA_ENABLED` | `false` | Expose dormant firmware distribution APIs for compatible custom clients |
| `MAIL_*` | unset | SMTP settings (optional) |
| `WAITLIST_NOTIFICATION_EMAIL` | unset | Optional internal recipient for hosted waitlist alerts |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` | `2` / `4` | Server concurrency |

See [`.env.example`](.env.example) for the full list.

> **Note:** the default rate limiter stores counters in-process. If you run more
> than one Gunicorn worker behind a shared deployment, configure a Redis backend
> for `Flask-Limiter` so limits are enforced across workers.

---

## Integrations

Spoolio exposes a **Spoolman-compatible API**, so tools that already speak
[Spoolman](https://github.com/Donkie/Spoolman) — Moonraker, OctoPrint-Spoolman,
OrcaSlicer, NFC scales like FilaMan — can read your inventory and auto-decrement
spools as you print. You get a per-user token URL to paste in as the "Spoolman
server." See [`docs/SPOOLMAN_API.md`](docs/SPOOLMAN_API.md).

## Project structure

```
app.py                Flask app factory, security headers, static serving
wsgi.py               WSGI entry point (gunicorn wsgi:app)
models.py             SQLAlchemy models
blueprints/           REST API, organised by domain (auth, spools, hardware, …)
email_service.py      Transactional email helpers
frontend/             React single-page app (built into static/)
hardware/             Two maintained reference sketches and provisioning notes
scripts/              SQLite backup, email test, and Docker secret helpers
Dockerfile            Multi-stage build (frontend + Python runtime)
docker-compose.yml    One-command self-host
docker/entrypoint.sh  Secret generation + DB init + gunicorn launch
```

---

## Hardware (optional)

The `hardware/` directory contains Arduino sketches for ESP8266/ESP32 devices
that read spool weight from an HX711 load cell and identify spools via a PN532
NFC reader. The ESP8266 scale is provisioned through its captive portal and USB
serial console; the reference ESP32-CYD display uses placeholder values that
must be replaced locally before compiling. See [`hardware/README.md`](hardware/README.md).

Generate a device API key by registering a device from the Hardware page in the
app; never commit real credentials back into the repository. Community devices
can implement the board-neutral [Hardware Protocol v1](docs/HARDWARE_PROTOCOL.md)
and use the included Python simulator before any physical scale is connected.

---

## Contributing and security

Development setup, test gates, migration rules, and pull-request expectations are in
[`CONTRIBUTING.md`](CONTRIBUTING.md). Report vulnerabilities through the private route
described in [`SECURITY.md`](SECURITY.md), never in a public issue with exploit or
credential details.

The public repository intentionally excludes the hosted service's infrastructure,
deployment credentials, production database, and operator runbooks. A hosted instance
is available at [spoolio.co.uk](https://www.spoolio.co.uk); access may be
waitlist-controlled. Self-hosted deployments are operated and supported separately.

Release tags matching `v*` publish a container to
`ghcr.io/markgwharry/spoolio` for `linux/amd64` and `linux/arm64`, with an SBOM
and build provenance. Numbered tags are the reproducible installation path;
`latest` follows the newest stable release.

---

## License

Spoolio is licensed under the [Apache License 2.0](LICENSE).
