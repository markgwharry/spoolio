# Database migrations

Spoolio uses Flask-Migrate/Alembic as the only schema-management path. The
historical `migrate_*.py` scripts are retired and must not be copied back into a
deployment.

## Normal upgrade

Activate the application virtual environment, select the same database URI the
application uses, and run:

```bash
export SQLALCHEMY_DATABASE_URI="sqlite:////absolute/path/to/filament.db"
flask --app app:create_app db upgrade
flask --app app:create_app db current
```

`python setup_db.py` runs the same upgrade and then idempotently seeds the
shared material, colour, manufacturer, and spool-type reference values. Docker
runs this wrapper automatically on startup.

The first Alembic baseline is adoption-aware:

- an empty database receives the complete schema;
- an unversioned database that already has the current tables is adopted without
  recreating tables or changing application rows;
- supported legacy omissions are repaired before the database is marked current.

The next revision adds the retained legacy indexes and the user/relationship
indexes used by inventory, history, bits, firmware, waitlist, and hardware query
paths.

## Deployment safety

Back up the database before running `flask db upgrade`. For SQLite, the included
`scripts/backup_sqlite.py` helper uses SQLite's backup API so committed WAL pages are
included:

```bash
python scripts/backup_sqlite.py /path/to/filament.db /path/to/filament.backup.db
```

Only restart the application after the backup and migration have both succeeded. A
missing database is treated as a fresh install and is created by Alembic.

Do not run `flask db downgrade` across the adoption baseline. It cannot know
which tables predated Alembic, so its downgrade deliberately refuses to drop
them. Restore the pre-migration SQLite backup instead.

## Rehearse against a copy

Stop or quiesce writes before taking the production backup. With the copy on a
non-production host:

```bash
sqlite3 /path/to/source.db ".backup '/path/to/rehearsal.db'"
sqlite3 /path/to/rehearsal.db "PRAGMA integrity_check;"

export SQLALCHEMY_DATABASE_URI="sqlite:////path/to/rehearsal.db"
flask --app app:create_app db upgrade
flask --app app:create_app db current
sqlite3 /path/to/rehearsal.db "PRAGMA integrity_check;"
```

Confirm representative users, inventory, projects, hardware devices, and usage
history remain present. Keep the untouched source backup until the deployed
release has passed its observation window.

## Creating future revisions

```bash
flask --app app:create_app db migrate -m "describe the schema change"
flask --app app:create_app db upgrade
flask --app app:create_app db check
```

Review generated migrations before running them. New migration tests should use
real disposable SQLite files and cover both data preservation and repeated
upgrade safety.
