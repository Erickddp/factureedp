"""correo verificado en las cuentas que se registran solas

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuarios', schema=None) as b:
        # las cuentas que ya existen quedan verificadas: las dio de alta el administrador o entraron con Google
        b.add_column(sa.Column('correo_verificado', sa.Boolean(), nullable=False, server_default='1'))


def downgrade():
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.drop_column('correo_verificado')
