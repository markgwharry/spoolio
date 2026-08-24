"""hash remaining legacy device keys

Revision ID: 91f3a6c8d2e4
Revises: 4c7d9e2a1b6f
Create Date: 2026-08-23

"""
import hashlib

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '91f3a6c8d2e4'
down_revision = '4c7d9e2a1b6f'
branch_labels = None
depends_on = None


DIGEST_PREFIX = 'sha256$'


def _api_key_digest(value):
    if value is None or value.startswith(DIGEST_PREFIX):
        return value
    # Device keys are random 256-bit tokens. This migration creates the same
    # indexable lookup digest as HardwareDevice.hash_api_key; it is not hashing a
    # human-chosen password.
    # codeql[py/weak-sensitive-data-hashing]
    digest = hashlib.sha256(value.encode('utf-8')).hexdigest()
    return f'{DIGEST_PREFIX}{digest}'


def upgrade():
    hardware_device = sa.table(
        'hardware_device',
        sa.column('id', sa.Integer()),
        sa.column('api_key', sa.String(length=255)),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(hardware_device.c.id, hardware_device.c.api_key)
    ).mappings().all()
    for row in rows:
        digest = _api_key_digest(row['api_key'])
        if digest != row['api_key']:
            connection.execute(
                hardware_device.update()
                .where(hardware_device.c.id == row['id'])
                .values(api_key=digest)
            )


def downgrade():
    raise RuntimeError(
        'Device API-key hashing is irreversible; restore a pre-upgrade backup '
        'instead of downgrading this revision.'
    )
