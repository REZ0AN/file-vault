"""Allow Google-only users and remember Drive uploads.

Revision ID: 74e6b6b7c1a0
Revises: 8409165bba7a
"""

from alembic import op
import sqlalchemy as sa

revision = "74e6b6b7c1a0"
down_revision = "8409165bba7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    op.add_column("files", sa.Column("drive_file_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_google_connections_subject", "google_connections", ["google_subject"])


def downgrade() -> None:
    op.drop_constraint("uq_google_connections_subject", "google_connections", type_="unique")
    op.drop_column("files", "drive_file_id")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
