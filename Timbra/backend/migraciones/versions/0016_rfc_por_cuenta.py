"""El RFC de un emisor es único dentro de cada cuenta, no en todo Timbra

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('emisores') as b:
        b.drop_index('ix_emisores_rfc')
        b.create_index('ix_emisores_rfc', ['rfc'], unique=False)
        b.create_index('uq_emisores_usuario_rfc', ['usuario_id', 'rfc'], unique=True)


def downgrade():
    with op.batch_alter_table('emisores') as b:
        b.drop_index('uq_emisores_usuario_rfc')
        b.drop_index('ix_emisores_rfc')
        b.create_index('ix_emisores_rfc', ['rfc'], unique=True)
