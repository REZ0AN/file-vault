import os
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# 1. Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# 2. PostgreSQL configuration
DB_USER = os.getenv("DB_USER", "filevault")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "filevault_db")

if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD is not configured")


# 3. Build the database URL
DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)


# 4. Create the SQLAlchemy Engine
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
    pool_pre_ping=True,
    echo=False,
)


# 5. Configure session creation
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# 6. Base class for ORM models
class Base(DeclarativeBase):
    pass


# 7. FastAPI database dependency
def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
