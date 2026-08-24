#!/usr/bin/env sh
# Spoolio container entrypoint.
#
# Responsibilities on every boot:
#   1. Ensure strong application secrets and any first-owner setup code exist
#      (auto-generate + persist so sessions, encrypted credentials, and secure
#      bootstrap survive restarts).
#   2. Upgrade the database and seed missing reference data (idempotent).
#   3. Hand off to the container command (gunicorn by default).
set -e

SECRETS_FILE="${SPOOLIO_SECRETS_FILE:-/app/instance/.spoolio_secrets}"

mkdir -p "$(dirname "$SECRETS_FILE")" /app/shared/profile_images

# ---------------------------------------------------------------------------
# 1. Secret management
# ---------------------------------------------------------------------------
# Load any previously generated secrets so they remain stable across restarts.
configured_secret_key="${SECRET_KEY:-}"
configured_jwt_secret_key="${JWT_SECRET_KEY:-}"
configured_wifi_credential_key="${WIFI_CREDENTIAL_KEY:-}"
configured_registration_token="${REGISTRATION_TOKEN:-}"
if [ -f "$SECRETS_FILE" ]; then
    # shellcheck disable=SC1090
    . "$SECRETS_FILE"
fi

# Explicit environment values always override persisted generated values.
[ -n "$configured_secret_key" ] && SECRET_KEY="$configured_secret_key"
[ -n "$configured_jwt_secret_key" ] && JWT_SECRET_KEY="$configured_jwt_secret_key"
[ -n "$configured_wifi_credential_key" ] && WIFI_CREDENTIAL_KEY="$configured_wifi_credential_key"
[ -n "$configured_registration_token" ] && REGISTRATION_TOKEN="$configured_registration_token"
export SECRET_KEY JWT_SECRET_KEY WIFI_CREDENTIAL_KEY REGISTRATION_TOKEN

needs_secret_file=0

if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    export SECRET_KEY
    needs_secret_file=1
    echo "[entrypoint] Generated a new SECRET_KEY (persisted to $SECRETS_FILE)."
fi

if [ -z "$JWT_SECRET_KEY" ]; then
    JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    export JWT_SECRET_KEY
    needs_secret_file=1
    echo "[entrypoint] Generated a new JWT_SECRET_KEY (persisted to $SECRETS_FILE)."
fi

if [ -z "$WIFI_CREDENTIAL_KEY" ]; then
    WIFI_CREDENTIAL_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    export WIFI_CREDENTIAL_KEY
    needs_secret_file=1
    echo "[entrypoint] Generated a new WIFI_CREDENTIAL_KEY (persisted to $SECRETS_FILE)."
fi

if [ "${REGISTRATION_MODE:-waitlist}" = "first-user" ] && [ -z "$REGISTRATION_TOKEN" ]; then
    REGISTRATION_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
    export REGISTRATION_TOKEN
    needs_secret_file=1
fi

if [ "$needs_secret_file" = "1" ]; then
    python /app/scripts/write_secret_env.py "$SECRETS_FILE"
fi

if [ "${REGISTRATION_MODE:-waitlist}" = "first-user" ]; then
    echo "[entrypoint] Owner setup code: $REGISTRATION_TOKEN"
fi

# ---------------------------------------------------------------------------
# 2. Database migration + reference-data seed
# ---------------------------------------------------------------------------
echo "[entrypoint] Upgrading and seeding database..."
python setup_db.py

# ---------------------------------------------------------------------------
# 3. Gunicorn tuning + hand-off
# ---------------------------------------------------------------------------
# gunicorn honours GUNICORN_CMD_ARGS, so workers/threads stay configurable via
# environment variables without baking them into the image CMD.
export GUNICORN_CMD_ARGS="--workers=${GUNICORN_WORKERS:-2} --threads=${GUNICORN_THREADS:-4} --timeout=120 --access-logfile=- --error-logfile=-"

echo "[entrypoint] Starting: $*"
exec "$@"
