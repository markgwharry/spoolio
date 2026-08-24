"""add token-version session revocation

Revision ID: 4c7d9e2a1b6f
Revises: 8e53af78b2ed
Create Date: 2026-08-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4c7d9e2a1b6f'
down_revision = '8e53af78b2ed'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    user_columns = {column['name'] for column in inspector.get_columns('user')}
    if 'token_version' not in user_columns:
        op.add_column(
            'user',
            sa.Column(
                'token_version',
                sa.Integer(),
                nullable=False,
                server_default='0',
            ),
        )

def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('token_version')
