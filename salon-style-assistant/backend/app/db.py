import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, String, JSON, Integer, Text, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("DATA_DIR", ROOT / ".runtime"))
DATA.mkdir(parents=True, exist_ok=True)
URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA / 'salon.db'}")
engine = create_engine(URL, connect_args={"check_same_thread": False, "timeout": 30} if URL.startswith("sqlite") else {}, pool_pre_ping=True)
if URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")

class Base(DeclarativeBase): pass
def uid(): return uuid.uuid4().hex
def now(): return datetime.now(timezone.utc).isoformat()

class Record(Base):
    """Versioned MVP records. Kind-scoped IDs are only accessed through tenant checks."""
    __tablename__ = "records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    salon_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

Session = sessionmaker(engine, expire_on_commit=False)
@contextmanager
def transaction():
    with Session() as db:
        try:
            # SQLite serializes mutation transactions; PostgreSQL locks touched rows.
            if URL.startswith("sqlite"):
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

def add(db, kind, salon, data, parent="", id=None):
    r = Record(id=id or uid(), kind=kind, salon_id=salon, parent_id=parent, data=data)
    db.add(r)
    db.flush()
    return r

def change(record, **values): record.data = {**record.data, **values}
