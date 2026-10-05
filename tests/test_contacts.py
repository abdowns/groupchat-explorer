import subprocess
from pathlib import Path

from gcapp import contacts, store


def test_contact_address_normalization():
    assert contacts.address_key("+1 (202) 555-0100") == "12025550100"
    assert contacts.address_key("202-555-0100") == "12025550100"
    assert contacts.address_key("0044 20 7946 0100") == contacts.address_key("+44 20 7946 0100")
    assert contacts.address_key("+49 1234567890") == "491234567890"
    assert contacts.address_key("0049 12345678") == "4912345678"
    assert contacts.address_key(" Name@EXAMPLE.invalid ") == "name@example.invalid"
    assert contacts.address_key("member1234567") == ""
    assert contacts.address_key("unknown") == ""


def test_contact_names_update_existing_people_without_changing_identity(archive, monkeypatch):
    wid, _ = archive
    response = {
        "status": "available",
        "contacts": [
            {"id": "c1", "name": "Zoë Neighbor", "keys": ["12025550100", "zoe@example.invalid"]},
            {"id": "mycard", "name": "My Saved Name", "keys": [], "is_me": True},
        ],
    }
    monkeypatch.setattr(contacts, "read_contacts", lambda *args, **kwargs: response)
    with store.workspace(wid) as db:
        for pid in ("+1 (202) 555-0100", "ZOE@example.invalid", "me", "+12025550199"):
            store.ensure_person(db, pid)
        summary = contacts.sync_names(db)
        assert summary["updated"] == summary["matched"] == 3
        names = dict(db.execute("SELECT id,name FROM people"))
        assert names["+1 (202) 555-0100"] == names["ZOE@example.invalid"] == "Zoë Neighbor"
        assert names["me"] == "My Saved Name"
        assert names["+12025550199"] == "+12025550199"
        assert len(names) == 6  # Same contact does not auto-merge phone/email identities.
        assert contacts.sync_names(db)["updated"] == 0
        response["contacts"][0]["name"] = "Zoë New Name"
        assert contacts.sync_names(db)["updated"] == 2
        db.execute("UPDATE people SET name='My Nickname' WHERE id='ZOE@example.invalid'")
        response["contacts"][0]["name"] = "Zoë Latest"
        assert contacts.sync_names(db)["updated"] == 1
        assert (
            db.execute("SELECT name FROM people WHERE id='ZOE@example.invalid'").fetchone()[0]
            == "My Nickname"
        )


def test_merged_aliases_ambiguous_matches_and_denial(archive, monkeypatch):
    wid, _ = archive
    response = {
        "status": "available",
        "contacts": [
            {"id": "one", "name": "One", "keys": ["12025550100"]},
            {"id": "two", "name": "Two", "keys": ["12025550199"]},
            {"id": "three", "name": "Three", "keys": ["12025550199"]},
        ],
    }
    monkeypatch.setattr(contacts, "read_contacts", lambda *args, **kwargs: response)
    with store.workspace(wid) as db:
        store.set_meta(db, "identity_map", {"+12025550100": "a", "+12025550199": "b"})
        summary = contacts.sync_names(db)
        assert summary["updated"] == 1
        assert summary["ambiguous"] == 1
        assert db.execute("SELECT name FROM people WHERE id='a'").fetchone()[0] == "One"
        assert db.execute("SELECT name FROM people WHERE id='b'").fetchone()[0] == "b"
        response.update(status="denied", contacts=[])
        assert contacts.sync_names(db)["status"] == "denied"
        assert db.execute("SELECT name FROM people WHERE id='a'").fetchone()[0] == "One"


def test_contacts_api_refreshes_all_display_names_and_preserves_manual_override(api_client, monkeypatch):
    client, wid = api_client
    calls = []

    def saved(handles, request_access=False):
        calls.append(request_access)
        return {
            "status": "available",
            "contacts": [{"id": "contact", "name": "Saved Name", "keys": ["12025550100"]}],
        }

    monkeypatch.setattr(contacts, "read_contacts", saved)
    with store.workspace(wid) as db:
        store.set_meta(db, "identity_map", {"+12025550100": "a"})
    path = f"/api/v1/workspaces/{wid}"
    result = client.post(path + "/contacts/sync", json={})
    assert result.status_code == 200 and result.json()["updated"] == 1
    assert calls == [True]
    people = client.get("/api/v1/workspaces").json()[0]["people"]
    assert next(p["name"] for p in people if p["id"] == "a") == "Saved Name"
    messages = client.get(path + "/messages").json()["items"]
    assert next(m["person_id"] for m in messages if m["id"] == "a1") == "a"
    # An explicit rename equal to today's contact name must also survive future changes.
    assert client.patch(path + "/people/a", json={"name": "Saved Name"}).status_code == 200
    monkeypatch.setattr(
        contacts,
        "read_contacts",
        lambda *a, **k: {
            "status": "available",
            "contacts": [{"id": "contact", "name": "Changed Contact", "keys": ["12025550100"]}],
        },
    )
    assert client.post(path + "/contacts/sync", json={}).json()["updated"] == 0
    assert client.get(path + "/settings").json()["contacts"]["matched"] == 1


def test_native_contacts_self_test_without_personal_data():
    helper = Path(contacts.PROJECT / "native/contacts/target/gc-contacts")
    if helper.is_file():
        result = subprocess.run([str(helper), "--self-test"], text=True, capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"
