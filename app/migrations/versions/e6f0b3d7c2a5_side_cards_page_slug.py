"""side_cards.page_slug

Revision ID: e6f0b3d7c2a5
Revises: d5e9a2c6b1f4
"""
from alembic import op

revision = "e6f0b3d7c2a5"
down_revision = "d5e9a2c6b1f4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE side_cards ADD COLUMN IF NOT EXISTS page_slug VARCHAR(120) NOT NULL DEFAULT ''")


def downgrade():
    op.execute("ALTER TABLE side_cards DROP COLUMN IF EXISTS page_slug")
