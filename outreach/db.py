"""Database engine/session setup for the ai-ops.pl lead acquisition system.

Krok 1 sekcji 12 STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md: baza danych + schemat
leada jako fundament pod moduły audytu, głosu, wideo, outreachu i mikro-apki.

Independent from the existing Q4/Customer Care pipeline in backend/data_service.py
(CSV/XLSX-based) — this is the new leadgen system's own store.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("LEADGEN_DATABASE_URL", f"sqlite:///{DATA_DIR / 'leadgen.db'}")

# check_same_thread=False: FastAPI/Streamlit may touch the session from a
# different thread than the one that created it; irrelevant for Postgres.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
