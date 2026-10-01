import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import Base, get_db, make_engine
from app.main import app


@pytest.fixture
def client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)

    def dependency():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()
