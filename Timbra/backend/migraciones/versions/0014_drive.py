"""Google Drive por cuenta: conexión (token cifrado) y archivos ya copiados

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'drive_conexiones',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('google_email', sa.String(200)),
        sa.Column('refresh_enc', sa.LargeBinary()),
        sa.Column('carpeta_id', sa.String(120)),
        sa.Column('estado', sa.String(14), nullable=False, server_default='activa'),
        sa.Column('error', sa.Text()),
        sa.Column('subidos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ultimo', sa.DateTime()),
        sa.Column('creado', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_drive_conexiones_usuario_id', 'drive_conexiones', ['usuario_id'], unique=True)
    op.create_table(
        'drive_archivos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('ruta', sa.String(400), nullable=False),
        sa.Column('drive_id', sa.String(120), nullable=False),
        sa.Column('creado', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('usuario_id', 'ruta'),
    )
    op.create_index('ix_drive_archivos_usuario_id', 'drive_archivos', ['usuario_id'])


def downgrade():
    op.drop_index('ix_drive_archivos_usuario_id', 'drive_archivos')
    op.drop_table('drive_archivos')
    op.drop_index('ix_drive_conexiones_usuario_id', 'drive_conexiones')
    op.drop_table('drive_conexiones')
