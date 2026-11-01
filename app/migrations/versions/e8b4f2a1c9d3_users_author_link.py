"""users.author_id: link a dashboard user to the author they write as

Revision ID: e8b4f2a1c9d3
Revises: d5e9a2c6b1f4
Create Date: 2026-10-30 10:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'e8b4f2a1c9d3'
down_revision = 'd5e9a2c6b1f4'
branch_labels = None
depends_on = None

FK_NAME = 'fk_users_author_id_authors'


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('author_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(FK_NAME, 'authors', ['author_id'], ['id'], ondelete='SET NULL')
    # Abdelhamid writes as author #1 (shalaby). Only his user row is touched, and only if author #1 really is
    # "shalaby" (a re-seeded DB may have someone else as #1) and he is not linked yet.
    op.execute(sa.text(
        "UPDATE users SET author_id = 1 "
        "WHERE lower(email) = 'abdelhamid@manasety.ai' AND author_id IS NULL "
        "AND EXISTS (SELECT 1 FROM authors WHERE id = 1 AND slug = 'shalaby')"
    ))


def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint(FK_NAME, type_='foreignkey')
        batch.drop_column('author_id')
