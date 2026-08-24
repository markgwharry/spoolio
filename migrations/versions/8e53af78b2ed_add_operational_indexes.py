"""add operational indexes

Revision ID: 8e53af78b2ed
Revises: 9259be5e50f1
Create Date: 2026-08-23 10:02:13.925525

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8e53af78b2ed'
down_revision = '9259be5e50f1'
branch_labels = None
depends_on = None


INDEXES = (
    ('ix_waitlist_entry_email', 'waitlist_entry', ('email',)),
    ('ix_waitlist_entry_created_at', 'waitlist_entry', ('created_at',)),
    ('ix_hardware_device_user_id', 'hardware_device', ('user_id',)),
    ('ix_filament_spool_hardware_device_id', 'filament_spool', ('hardware_device_id',)),
    ('ix_orphan_tag_last_seen', 'orphan_tag', ('last_seen',)),
    ('ix_firmware_release_hardware_type', 'firmware_release', ('hardware_type',)),
    ('ix_firmware_release_is_active', 'firmware_release', ('is_active',)),
    ('ix_filament_spool_user_id', 'filament_spool', ('user_id',)),
    ('ix_spool_history_spool_id', 'spool_history', ('spool_id',)),
    ('ix_spool_history_project_id', 'spool_history', ('project_id',)),
    ('ix_bit_user_id', 'bit', ('user_id',)),
    ('ix_hardware_event_user_id', 'hardware_event', ('user_id',)),
    ('ix_hardware_event_created_at', 'hardware_event', ('created_at',)),
)


def _has_index_for_columns(table_name, column_names):
    inspector = sa.inspect(op.get_bind())
    indexes = inspector.get_indexes(table_name)
    unique_constraints = inspector.get_unique_constraints(table_name)
    existing = {
        tuple(item['column_names'])
        for item in indexes + unique_constraints
        if item.get('column_names')
    }
    return tuple(column_names) in existing


def upgrade():
    for index_name, table_name, column_names in INDEXES:
        if not _has_index_for_columns(table_name, column_names):
            op.create_index(index_name, table_name, list(column_names), unique=False)


def downgrade():
    for index_name, table_name, _ in reversed(INDEXES):
        names = {
            item['name']
            for item in sa.inspect(op.get_bind()).get_indexes(table_name)
        }
        if index_name in names:
            op.drop_index(index_name, table_name=table_name)
