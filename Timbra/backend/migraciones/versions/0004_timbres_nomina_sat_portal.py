"""timbres nomina sat portal cobranza recurrentes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05 23:59:44.359551
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cfdi_sat',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emisor_id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('direccion', sa.String(length=10), nullable=False),
    sa.Column('tipo', sa.String(length=1), nullable=True),
    sa.Column('fecha', sa.DateTime(), nullable=True),
    sa.Column('rfc_emisor', sa.String(length=13), nullable=False),
    sa.Column('nombre_emisor', sa.String(length=300), nullable=True),
    sa.Column('rfc_receptor', sa.String(length=13), nullable=False),
    sa.Column('nombre_receptor', sa.String(length=300), nullable=True),
    sa.Column('subtotal', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('descuento', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('iva', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('iva_retenido', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('isr_retenido', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('total', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('moneda', sa.String(length=3), nullable=True),
    sa.Column('metodo_pago', sa.String(length=3), nullable=True),
    sa.Column('forma_pago', sa.String(length=2), nullable=True),
    sa.Column('uso_cfdi', sa.String(length=4), nullable=True),
    sa.Column('estado', sa.String(length=12), nullable=False),
    sa.Column('xml', sa.LargeBinary(), nullable=True),
    sa.Column('creado', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('emisor_id', 'uuid')
    )
    with op.batch_alter_table('cfdi_sat', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cfdi_sat_emisor_id'), ['emisor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cfdi_sat_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_cfdi_sat_uuid'), ['uuid'], unique=False)

    op.create_table('empleados',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emisor_id', sa.Integer(), nullable=False),
    sa.Column('num_empleado', sa.String(length=15), nullable=False),
    sa.Column('rfc', sa.String(length=13), nullable=False),
    sa.Column('curp', sa.String(length=18), nullable=False),
    sa.Column('nombre', sa.String(length=300), nullable=False),
    sa.Column('codigo_postal', sa.String(length=5), nullable=False),
    sa.Column('nss', sa.String(length=15), nullable=True),
    sa.Column('tipo_contrato', sa.String(length=2), nullable=False),
    sa.Column('tipo_regimen', sa.String(length=2), nullable=False),
    sa.Column('tipo_jornada', sa.String(length=2), nullable=True),
    sa.Column('periodicidad_pago', sa.String(length=2), nullable=False),
    sa.Column('clave_ent_fed', sa.String(length=3), nullable=False),
    sa.Column('fecha_inicio', sa.DateTime(), nullable=True),
    sa.Column('departamento', sa.String(length=100), nullable=True),
    sa.Column('puesto', sa.String(length=100), nullable=True),
    sa.Column('riesgo_puesto', sa.String(length=2), nullable=True),
    sa.Column('banco', sa.String(length=3), nullable=True),
    sa.Column('cuenta_bancaria', sa.String(length=18), nullable=True),
    sa.Column('salario_diario', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('sdi', sa.Numeric(precision=18, scale=6), nullable=True),
    sa.Column('emails', sa.JSON(), nullable=False),
    sa.Column('receta', sa.JSON(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('emisor_id', 'num_empleado')
    )
    with op.batch_alter_table('empleados', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_empleados_emisor_id'), ['emisor_id'], unique=False)

    op.create_table('solicitudes_sat',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emisor_id', sa.Integer(), nullable=False),
    sa.Column('id_solicitud', sa.String(length=60), nullable=True),
    sa.Column('direccion', sa.String(length=10), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('desde', sa.DateTime(), nullable=False),
    sa.Column('hasta', sa.DateTime(), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('mensaje', sa.Text(), nullable=True),
    sa.Column('paquetes', sa.JSON(), nullable=False),
    sa.Column('descargados', sa.Integer(), nullable=False),
    sa.Column('creado', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('actualizado', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('solicitudes_sat', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_solicitudes_sat_emisor_id'), ['emisor_id'], unique=False)

    op.create_table('tickets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emisor_id', sa.Integer(), nullable=False),
    sa.Column('folio', sa.String(length=40), nullable=False),
    sa.Column('fecha', sa.DateTime(), nullable=False),
    sa.Column('total', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('forma_pago', sa.String(length=2), nullable=False),
    sa.Column('conceptos', sa.JSON(), nullable=False),
    sa.Column('factura_id', sa.Integer(), nullable=True),
    sa.Column('creado', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['emisor_id'], ['emisores.id'], ),
    sa.ForeignKeyConstraint(['factura_id'], ['facturas.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('emisor_id', 'folio')
    )
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tickets_emisor_id'), ['emisor_id'], unique=False)

    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dias_credito', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('ultimo_recordatorio', sa.DateTime(), nullable=True))

    with op.batch_alter_table('emisores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fiel_cer', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('fiel_key_enc', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('fiel_password_enc', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('fiel_vence', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('registro_patronal', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('curp', sa.String(length=18), nullable=True))
        batch_op.add_column(sa.Column('portal_activo', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('portal_clave', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('portal_config', sa.JSON(), server_default='{}', nullable=False))
        batch_op.add_column(sa.Column('cobranza_auto', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_unique_constraint('uq_emisores_portal_clave', ['portal_clave'])

    with op.batch_alter_table('facturas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('empleado_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_facturas_empleado_id'), ['empleado_id'], unique=False)
        batch_op.create_foreign_key('fk_facturas_empleado', 'empleados', ['empleado_id'], ['id'])

    with op.batch_alter_table('pacs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('timbres_contratados', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('timbres_desde', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('timbres_alerta', sa.Integer(), server_default='50', nullable=False))

    with op.batch_alter_table('plantillas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('favorita', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('recurrente', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('dia', sa.Integer(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('proxima', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('auto_timbrar', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('enviar_email', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('ultima_factura_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('ultimo_error', sa.Text(), nullable=True))



def downgrade():
    with op.batch_alter_table('plantillas', schema=None) as batch_op:
        batch_op.drop_column('ultimo_error')
        batch_op.drop_column('ultima_factura_id')
        batch_op.drop_column('enviar_email')
        batch_op.drop_column('auto_timbrar')
        batch_op.drop_column('proxima')
        batch_op.drop_column('dia')
        batch_op.drop_column('recurrente')
        batch_op.drop_column('favorita')

    with op.batch_alter_table('pacs', schema=None) as batch_op:
        batch_op.drop_column('timbres_alerta')
        batch_op.drop_column('timbres_desde')
        batch_op.drop_column('timbres_contratados')

    with op.batch_alter_table('facturas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_facturas_empleado', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_facturas_empleado_id'))
        batch_op.drop_column('empleado_id')

    with op.batch_alter_table('emisores', schema=None) as batch_op:
        batch_op.drop_constraint('uq_emisores_portal_clave', type_='unique')
        batch_op.drop_column('cobranza_auto')
        batch_op.drop_column('portal_config')
        batch_op.drop_column('portal_clave')
        batch_op.drop_column('portal_activo')
        batch_op.drop_column('registro_patronal')
        batch_op.drop_column('curp')
        batch_op.drop_column('fiel_vence')
        batch_op.drop_column('fiel_password_enc')
        batch_op.drop_column('fiel_key_enc')
        batch_op.drop_column('fiel_cer')

    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.drop_column('ultimo_recordatorio')
        batch_op.drop_column('dias_credito')

    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tickets_emisor_id'))

    op.drop_table('tickets')
    with op.batch_alter_table('solicitudes_sat', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_solicitudes_sat_emisor_id'))

    op.drop_table('solicitudes_sat')
    with op.batch_alter_table('empleados', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_empleados_emisor_id'))

    op.drop_table('empleados')
    with op.batch_alter_table('cfdi_sat', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cfdi_sat_uuid'))
        batch_op.drop_index(batch_op.f('ix_cfdi_sat_fecha'))
        batch_op.drop_index(batch_op.f('ix_cfdi_sat_emisor_id'))

    op.drop_table('cfdi_sat')
