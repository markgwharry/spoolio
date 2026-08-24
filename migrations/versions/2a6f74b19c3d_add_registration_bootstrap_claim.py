"""add one-time registration bootstrap claim

Revision ID: 2a6f74b19c3d
Revises: 91f3a6c8d2e4
Create Date: 2026-08-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a6f74b19c3d'
down_revision = '91f3a6c8d2e4'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if 'registration_bootstrap' not in inspector.get_table_names():
        op.create_table(
            'registration_bootstrap',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column(
                'claimed_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade():
    if 'registration_bootstrap' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('registration_bootstrap')
