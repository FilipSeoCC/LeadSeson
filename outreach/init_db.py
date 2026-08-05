"""Bootstrap the ai-ops.pl lead acquisition database.

Usage:
    python -m outreach.init_db

See STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md, sekcja 12, krok 1.
"""
from . import models  # noqa: F401 -- import registers models on Base.metadata
from .db import Base, DATABASE_URL, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print(f"OK: schemat leadgen utworzony pod {DATABASE_URL}")
    print("Tabele:", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()
