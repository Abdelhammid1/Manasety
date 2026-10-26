"""clients.show_name

Revision ID: a7c1e4d9b2f0
Revises: 37232ef33095
Create Date: 2026-10-27 01:40:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c1e4d9b2f0'
down_revision = '37232ef33095'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('clients', sa.Column('show_name', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('clients', 'show_name')
