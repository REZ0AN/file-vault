"""Historical OAuth transaction table; retained for existing database history.

Revision ID: 4de12eb47637
Revises: 5ac4e02cb364
"""

from alembic import op
import sqlalchemy as sa

revision = "4de12eb47637"
down_revision = "5ac4e02cb364"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_oauth_transactions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("browser_binding_hash", sa.String(64), nullable=False),
        sa.Column("pkce_verifier_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("consumed_at IS NULL OR consumed_at >= created_at", name="ck_google_oauth_transactions_consumed"),
        sa.CheckConstraint("expires_at > created_at", name="ck_google_oauth_transactions_expiry"),
        sa.UniqueConstraint("state_hash", name="uq_google_oauth_transactions_state_hash"),
    )
    op.create_index("ix_google_oauth_transactions_expires_at", "google_oauth_transactions", ["expires_at"])
    op.create_index("ix_google_oauth_transactions_user_id", "google_oauth_transactions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_google_oauth_transactions_user_id", table_name="google_oauth_transactions")
    op.drop_index("ix_google_oauth_transactions_expires_at", table_name="google_oauth_transactions")
    op.drop_table("google_oauth_transactions")
