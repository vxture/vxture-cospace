"""Frozen import and immutable dataset schema."""
from alembic import op
import sqlalchemy as sa

revision = '0002_dataset_imports'
down_revision = '0001_sample_lifecycle'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cospace_imports',
        sa.Column('import_id', sa.String(), primary_key=True),
        sa.Column('scene_id', sa.String(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('request_sha256', sa.String(), nullable=False),
        sa.Column('request', sa.JSON(), nullable=False), sa.Column('actor', sa.String(), nullable=False),
        sa.Column('requested_at', sa.String(), nullable=False), sa.Column('state', sa.String(), nullable=False),
        sa.Column('diagnostic', sa.JSON()), sa.Column('dataset_id', sa.String()), sa.Column('committed_at', sa.String()),
        sa.UniqueConstraint('scene_id', 'idempotency_key', name='uq_cospace_import_request'))
    op.create_table('cospace_datasets',
        sa.Column('dataset_id', sa.String(), primary_key=True),
        sa.Column('import_id', sa.String(), sa.ForeignKey('cospace_imports.import_id'), nullable=False, unique=True),
        sa.Column('manifest', sa.JSON(), nullable=False), sa.Column('sha256', sa.String(), nullable=False))


def downgrade():
    for table in ('cospace_datasets', 'cospace_imports'):
        if op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar_one():
            raise RuntimeError('downgrade refused: import data must be preserved')
    op.drop_table('cospace_datasets')
    op.drop_table('cospace_imports')
