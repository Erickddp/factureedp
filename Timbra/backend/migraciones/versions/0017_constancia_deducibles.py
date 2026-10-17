"""constancia fiscal, decisiones de deducibilidad y lo aprendido

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'constancia_fiscal',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('emisor_id', sa.Integer(), sa.ForeignKey('emisores.id'), nullable=False),
        sa.Column('rfc', sa.String(13), nullable=False),
        sa.Column('nombre', sa.String(300), nullable=False, server_default=''),
        sa.Column('curp', sa.String(18)),
        sa.Column('cp', sa.String(5), nullable=False, server_default=''),
        sa.Column('id_cif', sa.String(20)),
        sa.Column('emitida_el', sa.String(10)),
        sa.Column('regimenes', sa.JSON()),
        sa.Column('actividades', sa.JSON()),
        sa.Column('obligaciones', sa.JSON()),
        sa.Column('domicilio', sa.JSON()),
        sa.Column('archivo', sa.String(300), nullable=False, server_default=''),
        sa.Column('subida_por', sa.Integer()),
        sa.Column('creado', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_constancia_fiscal_emisor_id', 'constancia_fiscal', ['emisor_id'])
    op.create_table(
        'xml_deduccion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('emisor_id', sa.Integer(), sa.ForeignKey('emisores.id'), nullable=False),
        sa.Column('uuid', sa.String(40), nullable=False),
        sa.Column('decision', sa.String(14), nullable=False),
        sa.Column('porcentaje', sa.Float()),
        sa.Column('nota', sa.String(300)),
        sa.Column('aprendida', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('rfc_proveedor', sa.String(13)),
        sa.Column('claves', sa.String(120)),
        sa.Column('decidido_por', sa.Integer()),
        sa.Column('decidido_el', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('emisor_id', 'uuid'),
    )
    op.create_index('ix_xml_deduccion_emisor_id', 'xml_deduccion', ['emisor_id'])
    op.create_table(
        'pref_deduccion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('emisor_id', sa.Integer(), sa.ForeignKey('emisores.id'), nullable=False),
        sa.Column('tipo', sa.String(6), nullable=False),
        sa.Column('valor', sa.String(13), nullable=False),
        sa.Column('si', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('no', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('emisor_id', 'tipo', 'valor'),
    )
    op.create_index('ix_pref_deduccion_emisor_id', 'pref_deduccion', ['emisor_id'])


def downgrade():
    op.drop_index('ix_pref_deduccion_emisor_id', 'pref_deduccion')
    op.drop_table('pref_deduccion')
    op.drop_index('ix_xml_deduccion_emisor_id', 'xml_deduccion')
    op.drop_table('xml_deduccion')
    op.drop_index('ix_constancia_fiscal_emisor_id', 'constancia_fiscal')
    op.drop_table('constancia_fiscal')
