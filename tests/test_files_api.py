import importlib

from fastapi.testclient import TestClient


def _build_client(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    file_dir = tmp_path / "files"
    monkeypatch.setenv("APP_TOKEN", "test-token")
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("FILE_STORAGE_PATH", str(file_dir))

    import app.core.config as config_module
    import app.core.container as container_module
    import app.main as main_module

    config_module.get_settings.cache_clear()
    container_module.get_repo.cache_clear()
    container_module.get_item_service.cache_clear()
    container_module.get_file_service.cache_clear()

    importlib.reload(config_module)
    importlib.reload(container_module)
    importlib.reload(main_module)

    return TestClient(main_module.app)


def _auth_header():
    return {"Authorization": "Bearer test-token"}


def test_upload_and_download(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    upload = client.put(
        "/v1/files/avatar",
        headers=_auth_header(),
        files={"file": ("me.txt", b"hello file", "text/plain")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["key"] == "avatar"
    assert body["version"] == 1
    assert body["size_bytes"] == 10

    meta = client.get("/v1/files/avatar/meta", headers=_auth_header())
    assert meta.status_code == 200
    assert meta.json()["checksum_sha256"] == body["checksum_sha256"]

    download = client.get("/v1/files/avatar", headers=_auth_header())
    assert download.status_code == 200
    assert download.content == b"hello file"
    assert download.headers["content-type"].startswith("text/plain")


def test_file_conflict(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    first = client.put(
        "/v1/files/doc",
        headers=_auth_header(),
        files={"file": ("doc.txt", b"v1", "text/plain")},
    )
    assert first.status_code == 200

    second = client.put(
        "/v1/files/doc?expected_version=1",
        headers=_auth_header(),
        files={"file": ("doc.txt", b"v2", "text/plain")},
    )
    assert second.status_code == 200
    assert second.json()["version"] == 2

    conflict = client.put(
        "/v1/files/doc?expected_version=1",
        headers=_auth_header(),
        files={"file": ("doc.txt", b"v3", "text/plain")},
    )
    assert conflict.status_code == 409


def test_list_files_since(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    a = client.put(
        "/v1/files/a",
        headers=_auth_header(),
        files={"file": ("a.txt", b"aaa", "text/plain")},
    )
    assert a.status_code == 200

    b = client.put(
        "/v1/files/b",
        headers=_auth_header(),
        files={"file": ("b.txt", b"bbb", "text/plain")},
    )
    assert b.status_code == 200

    first_page = client.get("/v1/files?limit=1", headers=_auth_header())
    assert first_page.status_code == 200
    body = first_page.json()
    assert len(body["files"]) == 1
    since = body["next_since"]
    assert since

    second_page = client.get(
        f"/v1/files?limit=10&since={since}", headers=_auth_header()
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["files"]) >= 1


def test_soft_delete_blocks_meta_and_download(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    upload = client.put(
        "/v1/files/report",
        headers=_auth_header(),
        files={"file": ("report.txt", b"hello", "text/plain")},
    )
    assert upload.status_code == 200

    deleted = client.delete("/v1/files/report", headers=_auth_header())
    assert deleted.status_code == 200
    deleted_body = deleted.json()
    assert deleted_body["is_deleted"] is True
    assert deleted_body["deleted_at"] is not None

    meta = client.get("/v1/files/report/meta", headers=_auth_header())
    assert meta.status_code == 404

    download = client.get("/v1/files/report", headers=_auth_header())
    assert download.status_code == 404

    file_list = client.get("/v1/files", headers=_auth_header())
    assert file_list.status_code == 200
    files = file_list.json()["files"]
    tombstone = [item for item in files if item["key"] == "report"]
    assert len(tombstone) == 1
    assert tombstone[0]["is_deleted"] is True


def test_gc_purges_deleted_record_and_blob(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    upload = client.put(
        "/v1/files/cleanup",
        headers=_auth_header(),
        files={"file": ("cleanup.txt", b"cleanup", "text/plain")},
    )
    assert upload.status_code == 200

    deleted = client.delete("/v1/files/cleanup", headers=_auth_header())
    assert deleted.status_code == 200

    gc_resp = client.post("/v1/files/gc?grace_seconds=0", headers=_auth_header())
    assert gc_resp.status_code == 200
    gc_body = gc_resp.json()
    assert gc_body["scanned"] >= 1
    assert gc_body["deleted_records"] >= 1
    assert gc_body["deleted_blobs"] >= 1

    file_list = client.get("/v1/files", headers=_auth_header())
    assert file_list.status_code == 200
    keys = [item["key"] for item in file_list.json()["files"]]
    assert "cleanup" not in keys
