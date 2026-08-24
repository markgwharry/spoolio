"""baseline schema

Revision ID: 9259be5e50f1
Revises:
Create Date: 2026-08-23 10:00:05.917704

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9259be5e50f1'
down_revision = None
branch_labels = None
depends_on = None


DEFAULT_BIT_CATEGORIES = (
    'Fasteners',
    'Electronics',
    'Heat Set Inserts',
    'Springs',
    'Bearings',
    'Magnets',
    'Adhesives',
    'Other',
)


def _table_names():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_table(name, *elements):
    """Create a baseline table while safely adopting an existing database."""
    if name not in _table_names():
        op.create_table(name, *elements)


def _add_column_if_missing(table_name, column):
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    columns = {item['name'] for item in inspector.get_columns(table_name)}
    if column.name not in columns:
        op.add_column(table_name, column)


def _ensure_unique_index(table_name, index_name, column_names):
    inspector = sa.inspect(op.get_bind())
    indexed_columns = {
        tuple(item['column_names'])
        for item in inspector.get_indexes(table_name)
        if item.get('column_names')
    }
    constrained_columns = {
        tuple(item['column_names'])
        for item in inspector.get_unique_constraints(table_name)
        if item.get('column_names')
    }
    if tuple(column_names) not in indexed_columns | constrained_columns:
        op.create_index(index_name, table_name, column_names, unique=True)


def _reconcile_legacy_columns():
    """Fold the supported legacy-script additions into the Alembic baseline."""
    columns = {
        'user': (
            sa.Column('profile_image_filename', sa.String(length=255), nullable=True),
            sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('email_verification_token', sa.String(length=100), nullable=True),
            sa.Column('email_verification_expires', sa.DateTime(), nullable=True),
            sa.Column('password_reset_token', sa.String(length=100), nullable=True),
            sa.Column('password_reset_expires', sa.DateTime(), nullable=True),
            sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('locked_until', sa.DateTime(), nullable=True),
            sa.Column('spoolman_token', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        ),
        'spool_type': (
            sa.Column('compatible_with_ams', sa.Boolean(), nullable=True, server_default=sa.false()),
            sa.Column('tare_weight', sa.Float(), nullable=True, server_default='0'),
        ),
        'project': (
            sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
            sa.Column('budget_grams', sa.Float(), nullable=True),
        ),
        'filament_spool': (
            sa.Column('subtype', sa.String(length=100), nullable=True),
            sa.Column('low_stock_threshold', sa.Float(), nullable=True, server_default='100'),
            sa.Column('purchase_date', sa.Date(), nullable=True),
            sa.Column('last_used_date', sa.DateTime(), nullable=True),
            sa.Column('barcode', sa.String(length=100), nullable=True),
            sa.Column('serial_number', sa.String(length=100), nullable=True),
            sa.Column('nfc_tag_id', sa.String(length=100), nullable=True),
            sa.Column('hardware_last_update', sa.DateTime(), nullable=True),
            sa.Column(
                'hardware_device_id',
                sa.Integer(),
                sa.ForeignKey('hardware_device.id'),
                nullable=True,
            ),
            sa.Column('price', sa.Float(), nullable=True),
        ),
        'spool_history': (
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('project.id'), nullable=True),
        ),
        'hardware_device': (
            sa.Column('hardware_type', sa.String(length=100), nullable=True),
            sa.Column('wifi_ssid', sa.String(length=255), nullable=True),
            sa.Column('wifi_password_encrypted', sa.LargeBinary(), nullable=True),
            sa.Column('wifi_credentials_updated_at', sa.DateTime(), nullable=True),
        ),
    }
    for table_name, table_columns in columns.items():
        for column in table_columns:
            _add_column_if_missing(table_name, column)

    _ensure_unique_index('user', 'ix_user_spoolman_token', ['spoolman_token'])
    _ensure_unique_index('filament_spool', 'ix_filament_spool_barcode', ['barcode'])
    _ensure_unique_index('filament_spool', 'ix_filament_spool_serial_number', ['serial_number'])
    _ensure_unique_index('filament_spool', 'ix_filament_spool_nfc_tag_id', ['nfc_tag_id'])


def _seed_bit_categories():
    connection = op.get_bind()
    existing = {
        row[0].lower()
        for row in connection.execute(sa.text('SELECT name FROM bit_category'))
    }
    for name in DEFAULT_BIT_CATEGORIES:
        if name.lower() not in existing:
            connection.execute(
                sa.text('INSERT INTO bit_category (name) VALUES (:name)'),
                {'name': name},
            )


def upgrade():
    # Each create is conditional so a schema built by the retired migrate_*.py
    # scripts is adopted without recreating tables or touching application rows.
    _create_table('bit_category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    _create_table('color',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    _create_table('manufacturer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    _create_table('material',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    _create_table('spool_type',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('compatible_with_ams', sa.Boolean(), nullable=True),
    sa.Column('tare_weight', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    _create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=128), nullable=False),
    sa.Column('profile_image_filename', sa.String(length=255), nullable=True),
    sa.Column('email_verified', sa.Boolean(), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('email_verification_token', sa.String(length=100), nullable=True),
    sa.Column('email_verification_expires', sa.DateTime(), nullable=True),
    sa.Column('password_reset_token', sa.String(length=100), nullable=True),
    sa.Column('password_reset_expires', sa.DateTime(), nullable=True),
    sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(), nullable=True),
    sa.Column('spoolman_token', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('email_verification_token'),
    sa.UniqueConstraint('password_reset_token'),
    sa.UniqueConstraint('spoolman_token'),
    sa.UniqueConstraint('username')
    )
    _create_table('waitlist_entry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('referrer', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('raw_payload', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('bit',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('quantity_total', sa.Integer(), nullable=False),
    sa.Column('quantity_remaining', sa.Integer(), nullable=False),
    sa.Column('low_stock_threshold', sa.Integer(), nullable=True),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('supplier', sa.String(length=200), nullable=True),
    sa.Column('purchase_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['bit_category.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('filament_group',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('color_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.ForeignKeyConstraint(['color_id'], ['color.id'], ),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('firmware_release',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.String(length=64), nullable=False),
    sa.Column('hardware_type', sa.String(length=100), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('download_url', sa.String(length=255), nullable=True),
    sa.Column('release_notes', sa.Text(), nullable=True),
    sa.Column('manual_instructions', sa.Text(), nullable=True),
    sa.Column('checksum', sa.String(length=128), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('hardware_device',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('hardware_type', sa.String(length=100), nullable=True),
    sa.Column('api_key', sa.String(length=255), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('wifi_ssid', sa.String(length=255), nullable=True),
    sa.Column('wifi_password_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('wifi_credentials_updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('api_key'),
    sa.UniqueConstraint('device_id')
    )
    _create_table('project',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('budget_grams', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('bit_usage',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bit_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('quantity_used', sa.Integer(), nullable=False),
    sa.Column('date', sa.DateTime(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['bit_id'], ['bit.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('filament_refill',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('color_id', sa.Integer(), nullable=False),
    sa.Column('manufacturer_id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('weight_total', sa.Float(), nullable=False),
    sa.Column('weight_remaining', sa.Float(), nullable=False),
    sa.Column('subtype', sa.String(length=100), nullable=True),
    sa.Column('purchase_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('barcode', sa.String(length=100), nullable=True),
    sa.Column('serial_number', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['color_id'], ['color.id'], ),
    sa.ForeignKeyConstraint(['group_id'], ['filament_group.id'], ),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturer.id'], ),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('barcode'),
    sa.UniqueConstraint('serial_number')
    )
    _create_table('filament_spool',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('color_id', sa.Integer(), nullable=False),
    sa.Column('manufacturer_id', sa.Integer(), nullable=False),
    sa.Column('spool_type_id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('weight_start', sa.Float(), nullable=False),
    sa.Column('weight_remaining', sa.Float(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_empty', sa.Boolean(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('subtype', sa.String(length=100), nullable=True),
    sa.Column('low_stock_threshold', sa.Float(), nullable=True),
    sa.Column('purchase_date', sa.Date(), nullable=True),
    sa.Column('last_used_date', sa.DateTime(), nullable=True),
    sa.Column('barcode', sa.String(length=100), nullable=True),
    sa.Column('serial_number', sa.String(length=100), nullable=True),
    sa.Column('nfc_tag_id', sa.String(length=100), nullable=True),
    sa.Column('hardware_last_update', sa.DateTime(), nullable=True),
    sa.Column('hardware_device_id', sa.Integer(), nullable=True),
    sa.Column('price', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['color_id'], ['color.id'], ),
    sa.ForeignKeyConstraint(['group_id'], ['filament_group.id'], ),
    sa.ForeignKeyConstraint(['hardware_device_id'], ['hardware_device.id'], ),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturer.id'], ),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ),
    sa.ForeignKeyConstraint(['spool_type_id'], ['spool_type.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('barcode'),
    sa.UniqueConstraint('nfc_tag_id'),
    sa.UniqueConstraint('serial_number')
    )
    _create_table('orphan_tag',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nfc_tag_id', sa.String(length=100), nullable=False),
    sa.Column('first_seen', sa.DateTime(), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=False),
    sa.Column('last_weight', sa.Float(), nullable=True),
    sa.Column('hardware_device_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['hardware_device_id'], ['hardware_device.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nfc_tag_id')
    )
    _create_table('empty_spool',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('spool_type_id', sa.Integer(), nullable=False),
    sa.Column('origin_spool_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['origin_spool_id'], ['filament_spool.id'], ),
    sa.ForeignKeyConstraint(['spool_type_id'], ['spool_type.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('hardware_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('nfc_tag_id', sa.String(length=100), nullable=True),
    sa.Column('spool_id', sa.Integer(), nullable=True),
    sa.Column('weight', sa.Float(), nullable=True),
    sa.Column('message', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['hardware_device.id'], ),
    sa.ForeignKeyConstraint(['spool_id'], ['filament_spool.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('spool_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('spool_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.DateTime(), nullable=False),
    sa.Column('weight_used', sa.Float(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.ForeignKeyConstraint(['spool_id'], ['filament_spool.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _reconcile_legacy_columns()
    _seed_bit_categories()


def downgrade():
    raise RuntimeError(
        'The adoption baseline cannot be downgraded safely. Restore the '
        'pre-migration database backup instead.'
    )
