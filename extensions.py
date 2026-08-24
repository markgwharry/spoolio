import sqlite3

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate(compare_type=True, render_as_batch=True)


@event.listens_for(Engine, 'connect')
def configure_sqlite_connection(dbapi_connection, connection_record):
    """Apply integrity and write-concurrency settings to every SQLite connection."""
    del connection_record
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.execute('PRAGMA journal_mode=WAL')
    finally:
        cursor.close()
