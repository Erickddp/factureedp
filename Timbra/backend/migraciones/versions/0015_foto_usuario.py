"""Foto de perfil de la cuenta (la de Google, guardada como imagen pequeña)

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuarios') as b:
        b.add_column(sa.Column('foto', sa.Text()))


def downgrade():
    with op.batch_alter_table('usuarios') as b:
        b.drop_column('foto')
