"""articles.audience

Revision ID: c3d8f1a5b7e2
Revises: a7c1e4d9b2f0
Create Date: 2026-10-28 21:30:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d8f1a5b7e2'
down_revision = 'a7c1e4d9b2f0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('articles', sa.Column('audience', sa.String(length=10), nullable=False, server_default='both'))


def downgrade():
    op.drop_column('articles', 'audience')
