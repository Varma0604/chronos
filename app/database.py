from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session


def ensure_schema():
    """Create fresh tables and add lease columns to databases from version 0.1.0.

    This deliberately handles the two additive columns introduced before an
    Alembic migration history exists. Future schema changes should use formal
    migrations rather than extending this bootstrap helper.
    """
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
    additions = {
        "lease_owner": "VARCHAR(120)",
        "lease_expires_at": "TIMESTAMP",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {sql_type}"))
