"""Add truth_status to reports

Revision ID: 0006_truth_status
Revises: 0005_reliability_snapshot
Create Date: 2026-05-13

Phase 8 — Report Truth Validation Layer.
Adds truth_status field to track forensic mathematical verification state.
VERIFIED = all math cross-checks passed.
FAILED   = integrity mismatch detected; report access restricted.
UNVERIFIED = new report, not yet processed by the async pipeline.
"""

from alembic import op
import sqlalchemy as sa

revision = '0006_truth_status'
down_revision = '0005_reliability_snapshot'
branch_labels = None
depends_on = None

def upgrade():
    # Idempotent: check if column exists before adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('reports')]
    
    if 'truth_status' not in columns:
        op.add_column('reports', sa.Column('truth_status', sa.String(), nullable=True, server_default='UNVERIFIED'))
    
    # Backfill existing reports as UNVERIFIED so they can be re-verified on next access
    op.execute("UPDATE reports SET truth_status = 'UNVERIFIED' WHERE truth_status IS NULL")

def downgrade():
    op.drop_column('reports', 'truth_status')
