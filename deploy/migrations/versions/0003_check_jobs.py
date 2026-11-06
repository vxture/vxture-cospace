"""Frozen one-shot synthetic check jobs, attempts and events."""
from alembic import op
import sqlalchemy as sa

revision = '0003_check_jobs'
down_revision = '0002_dataset_imports'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cospace_jobs', sa.Column('job_id', sa.String(), primary_key=True),
        sa.Column('spec', sa.JSON(), nullable=False), sa.Column('sha256', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False), sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False), sa.Column('requested_at', sa.String(), nullable=False))
    op.create_table('cospace_attempts', sa.Column('attempt_id', sa.String(), primary_key=True),
        sa.Column('job_id', sa.String(), sa.ForeignKey('cospace_jobs.job_id'), nullable=False, unique=True),
        sa.Column('state', sa.String(), nullable=False), sa.Column('started_at', sa.String(), nullable=False),
        sa.Column('finished_at', sa.String()), sa.Column('diagnostic', sa.JSON()), sa.Column('artifact', sa.JSON()))
    op.create_table('cospace_job_events', sa.Column('event_id', sa.String(), primary_key=True),
        sa.Column('job_id', sa.String(), sa.ForeignKey('cospace_jobs.job_id'), nullable=False),
        sa.Column('state', sa.String(), nullable=False), sa.Column('created_at', sa.String(), nullable=False))


def downgrade():
    for table in ('cospace_job_events', 'cospace_attempts', 'cospace_jobs'):
        if op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar_one():
            raise RuntimeError('downgrade refused: job history must be preserved')
    for table in ('cospace_job_events', 'cospace_attempts', 'cospace_jobs'):
        op.drop_table(table)
