"""cuentas de invitado: entran sin registrarse y su trabajo se borra a la hora

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.add_column(sa.Column('invitado', sa.Boolean(), nullable=False, server_default='0'))
        b.add_column(sa.Column('expira', sa.DateTime()))


def downgrade():
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.drop_column('expira')
        b.drop_column('invitado')
