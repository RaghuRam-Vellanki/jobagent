import os
import shutil
import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from .models import Base

logger = logging.getLogger("db")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "jobs.db")


def _backup_and_drop_old_schema():
    """If DB exists without user_id columns (v1 schema), back it up and remove it."""
    if not os.path.exists(DB_PATH):
        return
    try:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            if "users" not in tables:
                backup = DB_PATH.replace(".db", "_v1_backup.db")
                shutil.copy(DB_PATH, backup)
                os.remove(DB_PATH)
                logger.info(f"Backed up v1 DB to {backup}, creating multi-tenant schema")
    except Exception as e:
        logger.warning(f"Migration check failed: {e}")


_backup_and_drop_old_schema()

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
