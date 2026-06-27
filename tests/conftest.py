# heavymetal/tests/conftest.py
"""Pytest fixtures for the gate suite.

Tests run against `fitnessdb_dev` (a snapshot copy of prod), never `fitnessdb`.
Each test runs inside a transaction that is rolled back at teardown — so writes
made by the code under test (ingest/settings/imports all `commit()`) are undone
and the dev snapshot is never mutated.
"""

import os

import pytest
from sqlalchemy.orm import scoped_session, sessionmaker

from backend import create_app
from backend.extensions import db as _db


def _dev_db_url():
    """The dev/test DB URL: explicit TEST_DATABASE_URL, else derive from
    FITNESS_DB_URL by swapping the database name to fitnessdb_dev."""
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.getenv(
        "FITNESS_DB_URL", "postgresql+psycopg://postgres@fedora:5432/fitnessdb"
    )
    head, _, _name = base.rpartition("/")
    return f"{head}/fitnessdb_dev"


@pytest.fixture(scope="session")
def app():
    return create_app({"SQLALCHEMY_DATABASE_URI": _dev_db_url(), "TESTING": True})


@pytest.fixture(scope="session", autouse=True)
def _prepare_schema(app):
    """Ensure the target DB has the schema + the single required user.

    Idempotent: a no-op against the local fitnessdb_dev snapshot (everything
    already exists), but on a fresh CI Postgres it builds the schema directly
    from the models (create_all) and seeds user_id=1 — faster than replaying
    the migration chain, and the squashed baseline produces the same schema.
    """
    from backend.models import User

    with app.app_context():
        _db.create_all()
        if _db.session.get(User, 1) is None:
            _db.session.add(User(id=1, name="Demo", email="demo@example.com"))
            _db.session.commit()
    yield


@pytest.fixture()
def db_session(app):
    """Bind the ORM session to a single connection wrapped in a transaction.

    join_transaction_mode="create_savepoint" turns the code's own commit() calls
    into SAVEPOINT releases inside our outer transaction, which we roll back — so
    nothing persists between tests.
    """
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()

        factory = sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        session = scoped_session(factory)
        original = _db.session
        _db.session = session
        try:
            yield session
        finally:
            session.remove()
            transaction.rollback()
            connection.close()
            _db.session = original


@pytest.fixture()
def client(app, db_session):
    """Test client whose requests share the rolled-back transaction."""
    return app.test_client()
