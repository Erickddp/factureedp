"""compras de timbres en línea (Mercado Pago) y vencimiento de cada recarga a 12 meses

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
    with op.batch_alter_table('movimientos_timbres', schema=None) as b:
        b.add_column(sa.Column('vence', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('restantes', sa.Integer(), nullable=True))
        b.add_column(sa.Column('pago_id', sa.Integer(), nullable=True))
    op.create_table(
        'pagos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('paquete', sa.String(length=20), nullable=False),
        sa.Column('timbres', sa.Integer(), nullable=False),
        sa.Column('monto', sa.Numeric(12, 2), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='pendiente'),
        sa.Column('preferencia', sa.String(length=80), nullable=True),
        sa.Column('mp_pago', sa.String(length=40), nullable=True, unique=True),
        sa.Column('detalle', sa.String(length=200), nullable=True),
        sa.Column('creado', sa.DateTime(), nullable=False),
        sa.Column('acreditado', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_pagos_usuario_id', 'pagos', ['usuario_id'])


def downgrade():
    op.drop_table('pagos')
    with op.batch_alter_table('movimientos_timbres', schema=None) as b:
        b.drop_column('pago_id')
        b.drop_column('restantes')
        b.drop_column('vence')
