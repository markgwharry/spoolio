# Contributing to Spoolio

Thanks for helping make filament tracking easier to adapt, self-host, and connect
to new scale hardware.

## Development setup

Create a Python virtual environment, install the backend dependencies, and prepare
an isolated development database:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export FLASK_ENV=development
python setup_db.py
```

Install and run the frontend separately when working on the UI:

```bash
cd frontend
npm ci
npm start
```

## Before opening a pull request

Run the same core gates as CI:

```bash
python -m pytest
python -m pip_audit -r requirements.txt
cd frontend
npm test
npm audit --omit=dev --audit-level=critical
npm run build
```

- Keep every database change in an Alembic migration under `migrations/versions/`.
- Add cross-user tests for any query that reads or mutates user-owned data.
- Never commit real device keys, Wi-Fi details, tokens, production data, or personal
  operator addresses. Use the placeholders already present in the examples.
- Keep hardware changes compatible with secure TLS and the documented provisioning
  flow. A successful compile does not replace a physical flash and bench test.
- Keep pull requests focused and describe any migration, deployment, security, or
  physical-validation boundary explicitly.

## Reporting security issues

Do not include credentials, personal data, or working exploit details in a public
issue. Follow [SECURITY.md](SECURITY.md) for a private reporting route.
