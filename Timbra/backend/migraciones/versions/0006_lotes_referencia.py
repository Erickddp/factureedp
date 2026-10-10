"""lotes de facturas, perfiles de importación y referencia (folio de la hoja)

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('facturas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referencia', sa.String(length=60), nullable=True))
        batch_op.create_index('ix_facturas_referencia', ['referencia'], unique=False)
    op.create_table(
        'perfiles_lote',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('emisor_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('usos', sa.Integer(), server_default='0', nullable=False),
        sa.Column('creado', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('perfiles_lote', schema=None) as batch_op:
        batch_op.create_index('ix_perfiles_lote_emisor_id', ['emisor_id'], unique=False)
    op.create_table(
        'lotes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('emisor_id', sa.Integer(), nullable=False),
        sa.Column('perfil_id', sa.Integer(), nullable=True),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('creado', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id']),
        sa.ForeignKeyConstraint(['perfil_id'], ['perfiles_lote.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('lotes', schema=None) as batch_op:
        batch_op.create_index('ix_lotes_emisor_id', ['emisor_id'], unique=False)
    op.create_table(
        'lote_filas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lote_id', sa.Integer(), nullable=False),
        sa.Column('emisor_id', sa.Integer(), nullable=False),
        sa.Column('n', sa.Integer(), nullable=False),
        sa.Column('datos', sa.JSON(), nullable=False),
        sa.Column('estado', sa.String(length=12), nullable=False),
        sa.Column('etapa', sa.String(length=12), nullable=True),
        sa.Column('serie', sa.String(length=25), nullable=True),
        sa.Column('folio', sa.String(length=40), nullable=True),
        sa.Column('referencia', sa.String(length=60), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('resumen', sa.JSON(), nullable=False),
        sa.Column('errores', sa.JSON(), nullable=False),
        sa.Column('avisos', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('factura_id', sa.Integer(), nullable=True),
        sa.Column('intentos', sa.Integer(), server_default='0', nullable=False),
        sa.Column('actualizado', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['lote_id'], ['lotes.id']),
        sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id']),
        sa.ForeignKeyConstraint(['factura_id'], ['facturas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('lote_filas', schema=None) as batch_op:
        batch_op.create_index('ix_lote_filas_lote_id', ['lote_id'], unique=False)
        batch_op.create_index('ix_lote_filas_emisor_id', ['emisor_id'], unique=False)
        batch_op.create_index('ix_lote_filas_estado', ['estado'], unique=False)


def downgrade():
    op.drop_table('lote_filas')
    op.drop_table('lotes')
    op.drop_table('perfiles_lote')
    with op.batch_alter_table('facturas', schema=None) as batch_op:
        batch_op.drop_index('ix_facturas_referencia')
        batch_op.drop_column('referencia')
