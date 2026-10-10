"""cuentas separadas: dueño de emisores y PAC, nombre de usuario e inicio de sesión con Google

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('usuario', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('google_sub', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('google_email', sa.String(length=200), nullable=True))
        batch_op.create_index('ix_usuarios_usuario', ['usuario'], unique=True)
        batch_op.create_index('ix_usuarios_google_sub', ['google_sub'], unique=True)
    with op.batch_alter_table('emisores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('usuario_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_emisores_usuario_id', ['usuario_id'], unique=False)
        batch_op.create_foreign_key('fk_emisores_usuario', 'usuarios', ['usuario_id'], ['id'])
    with op.batch_alter_table('pacs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('usuario_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_pacs_usuario_id', ['usuario_id'], unique=False)
        batch_op.create_foreign_key('fk_pacs_usuario', 'usuarios', ['usuario_id'], ['id'])
    # Todo lo que ya existía es del primer administrador
    con = op.get_bind()
    admin = con.execute(sa.text("SELECT id FROM usuarios WHERE admin ORDER BY id LIMIT 1")).scalar()
    if admin is None:
        admin = con.execute(sa.text("SELECT id FROM usuarios ORDER BY id LIMIT 1")).scalar()
    if admin is not None:
        con.execute(sa.text("UPDATE emisores SET usuario_id = :u WHERE usuario_id IS NULL"), {"u": admin})
        con.execute(sa.text("UPDATE pacs SET usuario_id = :u WHERE usuario_id IS NULL"), {"u": admin})


def downgrade():
    with op.batch_alter_table('pacs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pacs_usuario', type_='foreignkey')
        batch_op.drop_index('ix_pacs_usuario_id')
        batch_op.drop_column('usuario_id')
    with op.batch_alter_table('emisores', schema=None) as batch_op:
        batch_op.drop_constraint('fk_emisores_usuario', type_='foreignkey')
        batch_op.drop_index('ix_emisores_usuario_id')
        batch_op.drop_column('usuario_id')
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_index('ix_usuarios_google_sub')
        batch_op.drop_index('ix_usuarios_usuario')
        batch_op.drop_column('google_email')
        batch_op.drop_column('google_sub')
        batch_op.drop_column('usuario')
