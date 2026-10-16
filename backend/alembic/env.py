
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.database import Base, engine
from app.models.user import User  # Register model metadata


# Alembic configuration
config = context.config

# Initialize logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Metadata describing our SQLAlchemy models
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Generate SQL without connecting to the database.
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
    Run migrations against the actual PostgreSQL database.
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
