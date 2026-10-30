"""JWT login, public metric catalog, and datasource workspace isolation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.auth import create_token, decode_token, hash_password, is_public, verify_password
from app.db import Base, get_db
from app.main import app
from app.metrics.registry import list_metrics
from app.models import DataSource, User
from app.seed import ensure_auth_users


def test_passwords_are_bcrypt_and_tokens_are_jwt():
    stored = hash_password("123456")
    assert stored.startswith("$2")
    assert verify_password("123456", stored)
    assert not verify_password("654321", stored)
    assert not verify_password("123456", "admin")

    class Fake:
        id = 7
        username = "admin"

    token = create_token(Fake())
    payload = decode_token(token)
    assert payload["sub"] == "admin"
    assert payload["uid"] == 7
    assert "password" not in payload


def test_metric_catalog_is_public_and_datasource_page_is_not():
    assert is_public("GET", "/api/v1/metric/list")
    assert is_public("GET", "/api/v1/health")
    assert is_public("POST", "/api/v1/login")
    assert not is_public("GET", "/api/v1/datasource/page")
    assert not is_public("POST", "/api/v1/metric/sql/preview")
    assert len(list_metrics()) == 28


def _client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with Session() as session:
        ensure_auth_users(session)
        from app.models import Workspace

        admin = session.query(User).filter(User.username == "admin").one()
        user = session.query(User).filter(User.username == "user").one()
        admin_ws = session.query(Workspace).filter(Workspace.name == "admin's default").one().id
        user_ws = session.query(Workspace).filter(Workspace.name == "user's default").one().id
        session.add(DataSource(id=1, uuid="admin-ds", name="admin-mysql", type="mysql", param="{}", workspace_id=admin_ws, create_by=admin.id, update_by=admin.id))
        session.add(DataSource(id=2, uuid="user-ds", name="user-mysql", type="mysql", param="{}", workspace_id=user_ws, create_by=user.id, update_by=user.id))
        session.commit()
        ids = {"admin": admin_ws, "user": user_ws}

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    return client, ids


def test_login_isolates_datasource_page(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "init_database", lambda: None)
    monkeypatch.setattr(main, "start_background", lambda: None)
    client, ids = _client()
    try:
        catalog = client.get("/api/v1/metric/list")
        assert catalog.status_code == 200
        assert len(catalog.json()["data"]) == 28
        assert client.get("/api/v1/datasource/page").status_code == 401
        assert client.post("/api/v1/metric/sql/preview", json={}).status_code == 401

        user_login = client.post("/api/v1/login", json={"username": "user", "password": "123456"})
        assert user_login.status_code == 200
        user_token = user_login.json()["data"]["token"]
        assert user_login.json()["token"] == user_token
        user_headers = {"Authorization": f"Bearer {user_token}"}
        own = client.get("/api/v1/datasource/page", headers=user_headers, params={"workspaceId": ids["user"]})
        assert own.status_code == 200
        assert [row["name"] for row in own.json()["data"]["records"]] == ["user-mysql"]
        foreign = client.get("/api/v1/datasource/page", headers=user_headers, params={"workspaceId": ids["admin"]})
        assert foreign.status_code == 403

        admin_login = client.post("/api/v1/login", json={"username": "admin", "password": "123456"})
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['data']['token']}"}
        admin_page = client.get("/api/v1/datasource/page", headers=admin_headers, params={"workspaceId": ids["admin"]})
        assert [row["name"] for row in admin_page.json()["data"]["records"]] == ["admin-mysql"]
        assert client.post("/api/v1/login", json={"username": "admin", "password": "nope"}).status_code == 400

        registered = client.post("/api/v1/register", json={"username": "newcomer", "email": "n@example.com", "password": "123456"})
        assert registered.status_code == 200
        assert registered.json()["data"]["workspaces"][0]["name"] == "newcomer's default"
    finally:
        app.dependency_overrides.clear()
