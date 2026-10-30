import pytest

from app.database import Base, engine


@pytest.fixture(autouse=True)
def clean_database():
    """Give every test a new schema without touching a developer's real data."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
