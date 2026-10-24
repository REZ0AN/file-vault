"""Allow central Drive storage while retaining legacy file bytes for migration.

Revision ID: 9d38c7a10f21
Revises: 74e6b6b7c1a0
"""

from alembic import op
import sqlalchemy as sa

revision = "9d38c7a10f21"
down_revision = "74e6b6b7c1a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("storage_folder_id", sa.String(255), nullable=True))
    op.add_column("files", sa.Column("storage_drive_file_id", sa.String(255), nullable=True))
    op.alter_column("files", "content", existing_type=sa.LargeBinary(), nullable=True)
    op.create_unique_constraint("uq_files_storage_drive_file_id", "files", ["storage_drive_file_id"])


def downgrade() -> None:
    # A downgrade needs all file bytes restored first; refuse silent data loss.
    connection = op.get_bind()
    missing = connection.execute(sa.text("SELECT count(*) FROM files WHERE content IS NULL")).scalar_one()
    if missing:
        raise RuntimeError("Restore PostgreSQL file bytes before downgrading central Drive storage")
    op.drop_constraint("uq_files_storage_drive_file_id", "files", type_="unique")
    op.alter_column("files", "content", existing_type=sa.LargeBinary(), nullable=False)
    op.drop_column("files", "storage_drive_file_id")
    op.drop_column("users", "storage_folder_id")
