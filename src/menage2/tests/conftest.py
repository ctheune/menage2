import os
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import alembic.command
import alembic.config
import pytest
import transaction
import webtest
from argon2 import PasswordHasher
from pyramid.paster import get_appsettings
from pyramid.scripting import prepare
from pyramid.testing import DummyRequest, testConfig
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from menage2 import main, models
from menage2.models.meta import Base
from menage2.models.team import Team, TeamMember
from menage2.models.user import User

_ph = PasswordHasher()


def _now():
    return datetime.now(timezone.utc)


def pytest_addoption(parser):
    parser.addoption("--ini", action="store", metavar="INI_FILE")


@pytest.fixture(scope="session")
def ini_file(request):
    return os.path.abspath(request.config.option.ini or "testing.ini")


@pytest.fixture(scope="session")
def app_settings(ini_file):
    return get_appsettings(ini_file)


@pytest.fixture(scope="session")
def setup_database(app_settings, ini_file):
    """Drop, recreate, and migrate the test database once per session."""
    db_name = urlparse(app_settings["sqlalchemy.url"]).path.lstrip("/")
    subprocess.run(["dropdb", "--if-exists", db_name], check=True)
    subprocess.run(["createdb", db_name], check=True)
    alembic.command.upgrade(alembic.config.Config(ini_file), "head")


@pytest.fixture(scope="session")
def dbengine(app_settings, setup_database):
    engine = models.get_engine(app_settings)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app(app_settings, dbengine):
    return main({}, dbengine=dbengine, **app_settings)


@pytest.fixture(scope="session")
def live_server(app):
    """Start the Pyramid app on an ephemeral port and yield its base URL."""
    from waitress import create_server

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        port = s.getsockname()[1]

    import logging

    logging.getLogger("waitress").setLevel(logging.ERROR)
    server = create_server(app, host="localhost", port=port)

    def _run():
        try:
            server.run()
        except OSError:
            pass  # expected when server.close() interrupts the select loop

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.05)
    else:
        server.close()
        raise RuntimeError(f"Test server did not start on port {port}")

    yield f"http://localhost:{port}"

    server.close()


@pytest.fixture
def tm():
    tm = transaction.TransactionManager(explicit=True)
    tm.begin()
    tm.doom()

    yield tm

    tm.abort()


@pytest.fixture
def dbsession(app, tm):
    session_factory = app.registry["dbsession_factory"]
    return models.get_tm_session(session_factory, tm)


@pytest.fixture
def testapp(app, tm, dbsession):
    testapp = webtest.TestApp(
        app,
        extra_environ={
            "HTTP_HOST": "example.com",
            "tm.active": True,
            "tm.manager": tm,
            "app.dbsession": dbsession,
        },
    )
    return testapp


@pytest.fixture
def app_request(app, tm, dbsession):
    with prepare(registry=app.registry) as env:
        request = env["request"]
        request.host = "example.com"
        request.dbsession = dbsession
        request.tm = tm
        yield request


@pytest.fixture
def dummy_request(tm, dbsession):
    request = DummyRequest()
    request.host = "example.com"
    request.dbsession = dbsession
    request.tm = tm
    return request


@pytest.fixture
def dummy_config(dummy_request):
    with testConfig(request=dummy_request) as config:
        yield config


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(dbsession):
    user = User(
        username="admin",
        real_name="Admin User",
        email="admin@example.com",
        password_hash=_ph.hash("correct-password"),
        is_admin=True,
        is_active=True,
        created_at=_now(),
    )
    dbsession.add(user)
    dbsession.flush()
    return user


@pytest.fixture
def regular_user(dbsession):
    user = User(
        username="user",
        real_name="Regular User",
        email="user@example.com",
        password_hash=_ph.hash("user-password"),
        is_admin=False,
        is_active=True,
        created_at=_now(),
    )
    dbsession.add(user)
    dbsession.flush()
    return user


@pytest.fixture
def authenticated_testapp(testapp, admin_user):
    """testapp with an active admin session cookie."""
    testapp.post(
        "/login", {"username": "admin", "password": "correct-password"}, status=303
    )
    return testapp


@pytest.fixture
def user_testapp(testapp, regular_user):
    """testapp with a regular (non-admin) user session cookie."""
    testapp.post(
        "/login", {"username": "user", "password": "user-password"}, status=303
    )
    return testapp


# ---------------------------------------------------------------------------
# Browser test fixtures (Playwright via live_server)
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_db(dbengine):
    """Truncate all tables before and after each browser test."""
    import time as _time

    names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    truncate_sql = text(f"TRUNCATE {names} RESTART IDENTITY CASCADE")

    def _truncate():
        for attempt in range(5):
            try:
                with dbengine.begin() as conn:
                    conn.execute(truncate_sql)
                return
            except Exception:
                if attempt == 4:
                    raise
                _time.sleep(0.2 * (attempt + 1))

    _truncate()
    yield
    _truncate()


@pytest.fixture
def second_user(clean_db, dbengine):
    """Insert a second (non-admin) user 'alice' for browser tests that need a peer."""
    Session = sessionmaker(bind=dbengine)
    session = Session()
    user = User(
        username="alice",
        real_name="Alice",
        email="alice@test.local",
        password_hash=_ph.hash("alicepassword1!"),
        is_admin=False,
        is_active=True,
        created_at=_now(),
    )
    session.add(user)
    session.commit()
    uid = user.id
    session.close()
    return {"id": uid, "username": "alice"}


@pytest.fixture
def team_with_alice(clean_db, dbengine, second_user, browser_admin_user):
    """Create a team named 'house' with alice as a member."""
    Session = sessionmaker(bind=dbengine)
    session = Session()
    team = Team(name="house", created_at=_now())
    session.add(team)
    session.flush()
    member = TeamMember(team_id=team.id, user_id=second_user["id"], role="assignee")
    session.add(member)
    session.commit()
    tid = team.id
    session.close()
    return {"id": tid, "name": "house"}


@pytest.fixture
def browser_admin_user(clean_db, dbengine):
    """Insert a fresh admin user directly into the test DB for browser tests."""
    Session = sessionmaker(bind=dbengine)
    session = Session()
    user = User(
        username="admin",
        real_name="Test Admin",
        email="admin@test.local",
        password_hash=_ph.hash("testpassword1!"),
        is_admin=True,
        is_active=True,
        created_at=_now(),
    )
    session.add(user)
    session.commit()
    session.close()
    return {"username": "admin", "password": "testpassword1!"}
