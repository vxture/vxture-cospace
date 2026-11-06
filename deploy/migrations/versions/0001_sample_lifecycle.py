"""Initial synthetic lifecycle schema. Frozen definitions; no domain metadata import."""
from alembic import op
import sqlalchemy as sa

revision = '0001_sample_lifecycle'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cospace_sample_scenes',
        sa.Column('scene_id', sa.String(), primary_key=True),
        sa.Column('release_id', sa.String(), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False))
    op.create_table('cospace_sample_releases',
        sa.Column('scene_id', sa.String(), sa.ForeignKey('cospace_sample_scenes.scene_id'), primary_key=True),
        sa.Column('release_id', sa.String(), primary_key=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('sha256', sa.String(), nullable=False))
    op.create_table('cospace_sample_events',
        sa.Column('event_id', sa.String(), primary_key=True),
        sa.Column('scene_id', sa.String(), nullable=False),
        sa.Column('release_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=True))
    op.create_table('cospace_sample_references',
        sa.Column('scene_id', sa.String(), primary_key=True),
        sa.Column('kind', sa.String(), primary_key=True),
        sa.Column('identity', sa.String(), primary_key=True),
        sa.Column('sha256', sa.String(), nullable=False))


def downgrade():
    # Never silently destroy registered samples, pointers or audit history.
    bind = op.get_bind()
    for name in ('cospace_sample_scenes', 'cospace_sample_releases',
                 'cospace_sample_events', 'cospace_sample_references'):
        count = bind.execute(sa.text(f'SELECT COUNT(*) FROM {name}')).scalar_one()
        if count:
            raise RuntimeError('downgrade refused: sample database contains data; preserve and migrate explicitly')
    for name in ('cospace_sample_references', 'cospace_sample_events',
                 'cospace_sample_releases', 'cospace_sample_scenes'):
        op.drop_table(name)
