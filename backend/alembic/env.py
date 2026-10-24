
from logging.config import fileConfig

from alembic import context

from app.database import Base, engine
from app import models  # noqa: F401
# Alembic configuration
config = context.config

# Load logging configuration from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Both User and File are registered here
target_metadata = Base.metadata

# Verify that all required models are registered.
required_tables = {
    "users",
    "files",
    "google_connections",
}

missing_tables = required_tables - set(
    target_metadata.tables
)

if missing_tables:
    raise RuntimeError(
        "Alembic metadata is missing tables: "
        + ", ".join(sorted(missing_tables))
    )

def run_migrations_offline() -> None:
    """
    Generate migration SQL without connecting
    to the database.
    """
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Execute migrations against PostgreSQL.
    """
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
