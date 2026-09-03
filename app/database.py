import os
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 - muss vor create_all()/_add_missing_columns()
# importiert sein, damit SQLModel.metadata die Tabellen überhaupt kennt.
# Wird sonst nur zufällig durch die Importreihenfolge anderer Module
# sichergestellt (z.B. weil main.py die Router importiert, die ihrerseits
# app.models importieren) - das ist fragil, u.a. bricht init_db() sonst
# lautlos (create_all() legt dann null Tabellen an), wenn es als erstes
# aus einem Skript aufgerufen wird, das app.models noch nicht kennt.

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "brewlog.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def _add_missing_columns() -> None:
    """Kleine, bewusst simple Selbst-Migration: legt beim Start neue Spalten
    an, die eine neuere Version des Modells kennt, die eigentliche
    SQLite-Datei aber noch nicht hat - so bricht die App nach einem
    Update nicht direkt mit "no such column" ab, wie es sonst der Fall
    wäre, weil `create_all()` nur komplett fehlende Tabellen anlegt,
    bestehende Tabellen aber nicht verändert.

    Deckt nur den (in dieser App bisher einzig vorkommenden) Fall neuer,
    nullable bzw. mit einfachem Skalar-Default versehener Spalten ab -
    keine vollständige Migration (keine umbenannten/gelöschten Spalten,
    keine Typänderungen). Für sowas bräuchte es ein echtes
    Migrationswerkzeug wie Alembic.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                col_type = column.type.compile(conn.dialect)
                default_sql = ""
                default = column.default
                if default is not None and getattr(default, "is_scalar", False):
                    value = default.arg
                    if isinstance(value, bool):
                        default_sql = f" DEFAULT {int(value)}"
                    elif isinstance(value, (int, float)):
                        default_sql = f" DEFAULT {value}"
                    elif isinstance(value, str):
                        default_sql = f" DEFAULT '{value}'"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_sql}'))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    with Session(engine) as session:
        from app.models import Settings

        if session.get(Settings, 1) is None:
            session.add(Settings(id=1))
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
