"""store decoded vendor tag metadata on orphan tags

Revision ID: b7e2c4d91a05
Revises: 2a6f74b19c3d
Create Date: 2026-09-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e2c4d91a05'
down_revision = '2a6f74b19c3d'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('orphan_tag')}
    if 'tag_format' not in columns:
        op.add_column('orphan_tag', sa.Column('tag_format', sa.String(length=32), nullable=True))
    if 'tag_metadata' not in columns:
        op.add_column('orphan_tag', sa.Column('tag_metadata', sa.Text(), nullable=True))


def downgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('orphan_tag')}
    with op.batch_alter_table('orphan_tag') as batch_op:
        if 'tag_metadata' in columns:
            batch_op.drop_column('tag_metadata')
        if 'tag_format' in columns:
            batch_op.drop_column('tag_format')
