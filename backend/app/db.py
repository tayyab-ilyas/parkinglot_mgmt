import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://parking:parking@localhost:5432/parking")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    # Services commit explicitly; leaving the block without commit rolls back.
    with SessionLocal() as db:
        yield db
