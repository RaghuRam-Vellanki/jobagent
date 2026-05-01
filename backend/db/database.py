import os
import logging
import sqlalchemy as sa
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


# V1 columns added at runtime via ALTER TABLE — keep this list in sync with models.py.
# Each entry: (table_name, column_name, full DDL fragment after "ADD COLUMN").
_V1_COLUMNS = [
    ("profile", "persona", "persona VARCHAR(32) NOT NULL DEFAULT 'early_career'"),
    ("profile", "preferred_cities", "preferred_cities TEXT NOT NULL DEFAULT '[]'"),
    ("profile", "graduation_year", "graduation_year INTEGER"),
    ("profile", "auto_run_enabled", "auto_run_enabled BOOLEAN NOT NULL DEFAULT 0"),
    ("profile", "auto_run_time", "auto_run_time VARCHAR(8) NOT NULL DEFAULT '09:00'"),
    ("jobs", "apply_channel", "apply_channel VARCHAR(16) NOT NULL DEFAULT 'external'"),
    ("jobs", "external_apply_url", "external_apply_url TEXT"),
]


def _ensure_columns(eng):
    """Idempotent ALTER TABLE for V1 columns. Safe on every startup."""
    try:
        inspector = sa.inspect(eng)
        existing_tables = set(inspector.get_table_names())
        with eng.begin() as conn:
            for table, col, ddl in _V1_COLUMNS:
                if table not in existing_tables:
                    continue
                cols = {c["name"] for c in inspector.get_columns(table)}
                if col in cols:
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")
                logger.info(f"Migrated: added {col} to {table}")
    except Exception as e:
        logger.warning(f"V1 column migration failed: {e}")


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_columns(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
