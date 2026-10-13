"""modo soporte: registro de cada entrada del administrador a la cuenta de un usuario

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'accesos_soporte',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('admin_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('motivo', sa.String(length=200), nullable=True),
        sa.Column('ip', sa.String(length=60), nullable=True),
        sa.Column('inicio', sa.DateTime(), nullable=False),
        sa.Column('hasta', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_accesos_soporte_admin_id', 'accesos_soporte', ['admin_id'])
    op.create_index('ix_accesos_soporte_usuario_id', 'accesos_soporte', ['usuario_id'])


def downgrade():
    op.drop_table('accesos_soporte')
