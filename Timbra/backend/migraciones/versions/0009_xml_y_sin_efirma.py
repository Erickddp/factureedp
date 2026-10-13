"""módulo de XML (descarga del SAT y lectura) y la e.firma deja de guardarse

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'xml_cfdi',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('emisor_id', sa.Integer(), sa.ForeignKey('emisores.id'), nullable=False),
        sa.Column('uuid', sa.String(length=40), nullable=False),
        sa.Column('tipo', sa.String(length=10), nullable=False),
        sa.Column('fecha', sa.String(length=19), nullable=False, server_default=''),
        sa.Column('clase', sa.String(length=1), nullable=False, server_default=''),
        sa.Column('comprobante', sa.String(length=12), nullable=False, server_default=''),
        sa.Column('serie', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('folio', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('rfc_emisor', sa.String(length=13), nullable=False, server_default=''),
        sa.Column('nombre_emisor', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('rfc_receptor', sa.String(length=13), nullable=False, server_default=''),
        sa.Column('nombre_receptor', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('subtotal', sa.Float(), nullable=False, server_default='0'),
        sa.Column('iva', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total', sa.Float(), nullable=False, server_default='0'),
        sa.Column('moneda', sa.String(length=3), nullable=False, server_default=''),
        sa.Column('metodo', sa.String(length=3), nullable=False, server_default=''),
        sa.Column('estatus', sa.String(length=10), nullable=False, server_default='Vigente'),
        sa.Column('cancelado_el', sa.String(length=19), nullable=True),
        sa.Column('origen', sa.String(length=8), nullable=False, server_default='sat'),
        sa.Column('archivo', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('filas', sa.JSON(), nullable=False),
        sa.Column('busca', sa.Text(), nullable=False, server_default=''),
        sa.Column('creado', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('emisor_id', 'uuid', 'tipo'),
    )
    op.create_index('ix_xml_cfdi_emisor_id', 'xml_cfdi', ['emisor_id'])
    op.create_index('ix_xml_cfdi_emisor_fecha', 'xml_cfdi', ['emisor_id', 'fecha'])
    op.create_table(
        'xml_trabajos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('emisor_id', sa.Integer(), sa.ForeignKey('emisores.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('clase', sa.String(length=6), nullable=False),
        sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('estado', sa.String(length=14), nullable=False, server_default='curso'),
        sa.Column('avance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mensaje', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('resumen', sa.JSON(), nullable=False),
        sa.Column('registro', sa.Text(), nullable=False, server_default=''),
        sa.Column('archivo', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('creado', sa.DateTime(), nullable=False),
        sa.Column('terminado', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_xml_trabajos_emisor_id', 'xml_trabajos', ['emisor_id'])
    # La e.firma equivale a la firma autógrafa: deja de guardarse. Lo que hubiera guardado se borra aquí.
    op.execute("UPDATE emisores SET fiel_cer = NULL, fiel_key_enc = NULL, fiel_password_enc = NULL, fiel_vence = NULL")
    # Solicitudes al SAT del módulo anterior: dependían de la e.firma guardada y ya no se pueden continuar.
    op.execute("DELETE FROM solicitudes_sat")


def downgrade():
    op.drop_table('xml_trabajos')
    op.drop_table('xml_cfdi')
