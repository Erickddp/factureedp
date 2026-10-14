"""términos de uso y aviso de privacidad aceptados por cuenta

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.add_column(sa.Column('terminos_version', sa.String(length=20), nullable=True))
        b.add_column(sa.Column('terminos_aceptados', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('terminos_ip', sa.String(length=45), nullable=True))


def downgrade():
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.drop_column('terminos_ip')
        b.drop_column('terminos_aceptados')
        b.drop_column('terminos_version')
