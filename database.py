"""SQLAlchemy engine and session factory for SnapFit."""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_PATH = Path(__file__).parent / "snapfit.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yield a DB session, close on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
