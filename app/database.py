import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "brewlog.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        from app.models import Settings

        if session.get(Settings, 1) is None:
            session.add(Settings(id=1))
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
