import os
import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from .models import Base

logger = logging.getLogger("db")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "jobs.db")


def _migrate_existing_db():
    """Add user_id columns to pre-auth tables via ALTER TABLE (safe, idempotent)."""
    if not os.path.exists(DB_PATH):
        return
    try:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            for table, col in [
                ("jobs", "user_id"),
                ("profile", "user_id"),
                ("credentials", "user_id"),
                ("daily_stats", "user_id"),
            ]:
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                if table not in tables:
                    continue
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER")
                    logger.info(f"Migrated: added {col} to {table}")
            conn.commit()
    except Exception as e:
        logger.warning(f"Migration failed: {e}")


_migrate_existing_db()

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
