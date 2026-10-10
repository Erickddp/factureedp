"""terceros y configuración de la barra de Facturar

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'terceros',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('emisor_id', sa.Integer(), nullable=False),
        sa.Column('rfc', sa.String(length=13), nullable=False),
        sa.Column('nombre', sa.String(length=300), nullable=False),
        sa.Column('regimen_fiscal', sa.String(length=3), nullable=False),
        sa.Column('codigo_postal', sa.String(length=5), nullable=False),
        sa.Column('alias', sa.String(length=80), nullable=True),
        sa.Column('concepto', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('usos', sa.Integer(), server_default='0', nullable=False),
        sa.Column('creado', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('emisor_id', 'rfc', name='uq_terceros_emisor_rfc'),
    )
    with op.batch_alter_table('terceros', schema=None) as batch_op:
        batch_op.create_index('ix_terceros_emisor_id', ['emisor_id'], unique=False)
    with op.batch_alter_table('emisores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('config_facturar', sa.JSON(), server_default='{}', nullable=False))


def downgrade():
    with op.batch_alter_table('emisores', schema=None) as batch_op:
        batch_op.drop_column('config_facturar')
    with op.batch_alter_table('terceros', schema=None) as batch_op:
        batch_op.drop_index('ix_terceros_emisor_id')
    op.drop_table('terceros')
