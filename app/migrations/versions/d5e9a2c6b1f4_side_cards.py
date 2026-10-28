"""side_cards

Revision ID: d5e9a2c6b1f4
Revises: c3d8f1a5b7e2
Create Date: 2026-10-28 23:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e9a2c6b1f4'
down_revision = 'c3d8f1a5b7e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('side_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False, server_default=''),
        sa.Column('text', sa.Text(), nullable=False, server_default=''),
        sa.Column('image_id', sa.Integer(), nullable=True),
        sa.Column('button_label', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('url', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('audience', sa.String(length=10), nullable=False, server_default='both'),
        sa.Column('side', sa.String(length=10), nullable=False, server_default='both'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['image_id'], ['media.id']),
        sa.PrimaryKeyConstraint('id'))


def downgrade():
    op.drop_table('side_cards')
