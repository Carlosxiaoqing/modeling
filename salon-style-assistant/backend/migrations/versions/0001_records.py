"""Initial versioned MVP record store."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None

def upgrade():
    # Supports an existing local demo created before migrations were introduced.
    if 'records' not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table('records', sa.Column('id', sa.String(64), primary_key=True), sa.Column('kind', sa.String(32), nullable=False), sa.Column('salon_id', sa.String(64), nullable=False), sa.Column('parent_id', sa.String(64), nullable=False), sa.Column('revision', sa.Integer(), nullable=False), sa.Column('data', sa.JSON(), nullable=False), sa.Column('created_at', sa.String(40), nullable=False))
        for field in ['kind', 'salon_id', 'parent_id']: op.create_index('ix_records_' + field, 'records', [field])

def downgrade():
    op.drop_table('records')
