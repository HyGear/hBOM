"""Database engine, session management, and non-destructive schema migration."""
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from config import DATABASE_URL, ECHO_SQL

Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=ECHO_SQL, pool_pre_ping=True)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA foreign_keys=ON")
        finally:
            cur.close()


SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
SessionLocal = scoped_session(SessionFactory)


def _run_safe_migrations():
    """Adds v2.0 columns and composite indexes to existing tables without data loss."""
    alter_statements = [
        "ALTER TABLE parts ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT 'MAKE'",
        "ALTER TABLE parts ADD COLUMN unit_weight FLOAT NOT NULL DEFAULT 0.0",
        "ALTER TABLE part_pending_updates ADD COLUMN new_source_type VARCHAR(16) NOT NULL DEFAULT 'MAKE'",
        "ALTER TABLE part_pending_updates ADD COLUMN new_unit_weight FLOAT NOT NULL DEFAULT 0.0",
        "ALTER TABLE bom_items ADD COLUMN superseded_by_eco VARCHAR(32)",
        "ALTER TABLE engineering_changes ADD COLUMN created_by VARCHAR(64) NOT NULL DEFAULT 'System'",
        "ALTER TABLE engineering_changes ADD COLUMN approved_by VARCHAR(64)",
        "ALTER TABLE engineering_changes ADD COLUMN released_by VARCHAR(64)",
        "ALTER TABLE drawings ADD COLUMN file_sha256 VARCHAR(64) NOT NULL DEFAULT ''",
        "ALTER TABLE drawing_revision_history ADD COLUMN file_sha256 VARCHAR(64) NOT NULL DEFAULT ''",
        "ALTER TABLE drawing_revision_history ADD COLUMN registered_by VARCHAR(64) NOT NULL DEFAULT 'System'",
        "ALTER TABLE eco_attachments ADD COLUMN file_sha256 VARCHAR(64) NOT NULL DEFAULT ''",
    ]
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_bom_parent_status ON bom_items (parent_pn, status)",
        "CREATE INDEX IF NOT EXISTS ix_bom_child_status ON bom_items (child_pn, status)",
        "CREATE INDEX IF NOT EXISTS ix_part_type_status ON parts (part_type, release_status)",
    ]
    with engine.begin() as conn:
        for stmt in alter_statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
        for idx_stmt in index_statements:
            try:
                conn.execute(text(idx_stmt))
            except Exception:
                pass


def init_db():
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _run_safe_migrations()


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_users_and_audit_columns():
    """Migrates SQLite schema for users and audit columns and seeds default accounts."""
    import hashlib
    from sqlalchemy import text

    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            userid VARCHAR(50) PRIMARY KEY,
            password_hash VARCHAR(128) NOT NULL,
            role VARCHAR(40) NOT NULL DEFAULT 'VIEWER (Read-Only)',
            full_name VARCHAR(120) NOT NULL DEFAULT '',
            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            email VARCHAR(120) NOT NULL DEFAULT ''
        )
        """,
        "ALTER TABLE engineering_changes ADD COLUMN created_by VARCHAR(50) DEFAULT 'admin'",
        "ALTER TABLE engineering_changes ADD COLUMN approved_by VARCHAR(50) DEFAULT NULL",
        "ALTER TABLE parts ADD COLUMN created_by VARCHAR(50) DEFAULT 'engineer'",
        "ALTER TABLE parts ADD COLUMN approved_by VARCHAR(50) DEFAULT NULL",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass

        demo_hash = hashlib.sha256("demo".encode("utf-8")).hexdigest()
        default_users = [
            ("viewer", "VIEWER (Read-Only)", "View Only User", "ACTIVE", "viewer@hbom.local"),
            ("engineer", "DESIGNER (Create/Modify)", "Design Engineer", "ACTIVE", "engineer@hbom.local"),
            ("approver", "APPROVER (Approve/Release)", "Engineering Approver", "ACTIVE", "approver@hbom.local"),
            ("admin", "ADMIN (Full Access)", "System Administrator", "ACTIVE", "admin@hbom.local"),
        ]
        for uid, role, fname, st, email in default_users:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO users (userid, password_hash, role, full_name, status, email) "
                    "VALUES (:uid, :pwd, :role, :fname, :st, :email)"
                ),
                {"uid": uid, "pwd": demo_hash, "role": role, "fname": fname, "st": st, "email": email},
            )

try:
    ensure_users_and_audit_columns()
except Exception:
    pass
