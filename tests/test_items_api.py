import importlib

from fastapi.testclient import TestClient


def _build_client(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("APP_TOKEN", "test-token")
    monkeypatch.setenv("DB_PATH", str(db_file))

    import app.core.config as config_module
    import app.core.container as container_module
    import app.main as main_module

    config_module.get_settings.cache_clear()
    container_module.get_repo.cache_clear()
    container_module.get_item_service.cache_clear()

    importlib.reload(config_module)
    importlib.reload(container_module)
    importlib.reload(main_module)

    return TestClient(main_module.app)


def _auth_header():
    return {"Authorization": "Bearer test-token"}


def test_auth_required(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    response = client.get("/v1/items/demo")
    assert response.status_code == 401


def test_upsert_and_get(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    upsert_resp = client.post(
        "/v1/items/clipboard",
        headers=_auth_header(),
        json={"value": "hello"},
    )
    assert upsert_resp.status_code == 200
    body = upsert_resp.json()
    assert body["version"] == 1
    assert body["value"] == "hello"

    get_resp = client.get("/v1/items/clipboard", headers=_auth_header())
    assert get_resp.status_code == 200
    assert get_resp.json()["value"] == "hello"


def test_get_text_value_json(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    upsert_resp = client.post(
        "/v1/items/clipboard",
        headers=_auth_header(),
        json={"value": "hello"},
    )
    assert upsert_resp.status_code == 200

    value_resp = client.get("/v1/text/clipboard", headers=_auth_header())
    assert value_resp.status_code == 200
    assert value_resp.json() == {"value": "hello"}

def test_get_text_value_plain(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    upsert_resp = client.post(
        "/v1/items/clipboard",
        headers=_auth_header(),
        json={"value": "hello text"},
    )
    assert upsert_resp.status_code == 200

    text_resp = client.get("/v1/text/clipboard.txt", headers=_auth_header())
    assert text_resp.status_code == 200
    assert text_resp.text == "hello text"
    assert text_resp.headers["content-type"].startswith("text/plain")


def test_update_and_conflict(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    first = client.post(
        "/v1/items/note",
        headers=_auth_header(),
        json={"value": "v1"},
    )
    assert first.status_code == 200
    assert first.json()["version"] == 1

    second = client.post(
        "/v1/items/note",
        headers=_auth_header(),
        json={"value": "v2", "expected_version": 1},
    )
    assert second.status_code == 200
    assert second.json()["version"] == 2

    conflict = client.post(
        "/v1/items/note",
        headers=_auth_header(),
        json={"value": "v3", "expected_version": 1},
    )
    assert conflict.status_code == 409


def test_incremental_sync(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    a = client.post("/v1/items/a", headers=_auth_header(), json={"value": "1"})
    assert a.status_code == 200
    b = client.post("/v1/items/b", headers=_auth_header(), json={"value": "2"})
    assert b.status_code == 200

    first_page = client.get("/v1/items?limit=1", headers=_auth_header())
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert len(first_body["items"]) == 1
    since = first_body["next_since"]
    assert since

    second_page = client.get(
        f"/v1/items?limit=10&since={since}", headers=_auth_header()
    )
    assert second_page.status_code == 200
    second_items = second_page.json()["items"]
    assert len(second_items) >= 1
