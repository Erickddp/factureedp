"""Aviso de novedades (casilla opcional) y cierre de cuenta pedido por la persona

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuarios') as b:
        b.add_column(sa.Column('novedades', sa.Boolean(), nullable=False, server_default='0'))
        b.add_column(sa.Column('cierre_solicitado', sa.DateTime()))


def downgrade():
    with op.batch_alter_table('usuarios') as b:
        b.drop_column('cierre_solicitado')
        b.drop_column('novedades')
