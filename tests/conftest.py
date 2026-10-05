import pytest

from gcapp import store


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    wid = store.create_workspace("Fixture group")
    records = [
        {"id": "a1", "person": "a", "text": "Cat cat cats! LMAO 👋", "ts": 1704151800},
        {"id": "a2", "person": "a", "text": "The council has spoken.", "ts": 1704153600},
        {"id": "b1", "person": "b", "text": "cathedral cats cat", "ts": 1704153660, "reply_to": "a2"},
        {
            "id": "b2",
            "person": "b",
            "text": "",
            "ts": 1704240000,
            "attachments": [{"id": "missing", "path": "/no/such/image.png", "mime": "image/png"}],
        },
        {"id": "sys", "person": "a", "text": "NameChange(our group)", "ts": 1704240100, "kind": "system"},
    ]
    records = [{"schema_version": 1, "record": "message", "chat_id": "chat", **r} for r in records]
    reactions = [
        {"id": "r1", "person": "b", "target": "a1", "ts": 1704151810, "type": "heart", "action": "add"},
        {"id": "r2", "person": "b", "target": "a1", "ts": 1704151820, "type": "laugh", "action": "add"},
        {"id": "r3", "person": "a", "target": "b1", "ts": 1704153670, "type": "like", "action": "add"},
        {"id": "r4", "person": "a", "target": "b1", "ts": 1704153680, "type": "like", "action": "remove"},
        {
            "id": "orphan",
            "person": "b",
            "target": "absent",
            "ts": 1704153690,
            "type": "heart",
            "action": "add",
        },
    ]
    records += [{"schema_version": 1, "record": "reaction", **r} for r in reactions]
    with store.workspace(wid) as db:
        store.import_records(db, records)
    return wid, records


@pytest.fixture
def api_client(archive):
    from fastapi.testclient import TestClient

    from gcapp.api import SESSION_TOKEN, app

    client = TestClient(app, headers={"X-Session-Token": SESSION_TOKEN})
    return client, archive[0]


@pytest.fixture(autouse=True)
def synthetic_contacts_only(monkeypatch):
    from gcapp import contacts

    monkeypatch.setattr(
        contacts, "read_contacts", lambda *args, **kwargs: {"status": "not_requested", "contacts": []}
    )
