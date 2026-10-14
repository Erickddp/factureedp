"""timbrado para terceros: PAC de la plataforma y saldo de timbres por cuenta

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pacs', schema=None) as b:
        b.add_column(sa.Column('plataforma', sa.Boolean(), nullable=False, server_default='0'))
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.add_column(sa.Column('timbres', sa.Integer(), nullable=False, server_default='3'))
    op.create_table(
        'movimientos_timbres',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('saldo', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.String(length=200), nullable=True),
        sa.Column('admin_id', sa.Integer(), nullable=True),
        sa.Column('creado', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_movimientos_timbres_usuario_id', 'movimientos_timbres', ['usuario_id'])


def downgrade():
    op.drop_table('movimientos_timbres')
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.drop_column('timbres')
    with op.batch_alter_table('pacs', schema=None) as b:
        b.drop_column('plataforma')
