import base64
import json
import plistlib
import sqlite3
import subprocess
from pathlib import Path

import pytest

from gcapp import analysis, analytics, cloud, store


def test_counts_reaction_state_and_denominators(archive):
    wid, _ = archive
    with store.workspace(wid) as db:
        result = analytics.overview(db, {})
        assert result["totals"]["messages"] == 4
        assert result["totals"]["reactions"] == 1
        people = {p["id"]: p for p in result["people"]}
        assert people["a"]["reactions_per_message"] == 0.5
        assert people["a"]["reaction_rate"] == 0.5
        assert people["b"]["reactions_per_message"] == 0
        assert db.execute("SELECT type FROM reactions WHERE target='a1'").fetchone()[0] == "laugh"
        assert db.execute("SELECT count(*) FROM reactions WHERE target='b1'").fetchone()[0] == 0
        r = analytics.reactions(db, {}, 20)
        assert r["rankings"] == []
        assert r["unresolved"] == 1


def test_word_boundaries_variants_normalization_and_filters(archive):
    wid, _ = archive
    with store.workspace(wid) as db:
        exact = analytics.word_explorer(db, {}, "cat")
        assert exact["occurrences"] == 3
        p = {p["id"]: p for p in exact["people"]}
        assert p["a"]["occurrences"] == 2
        assert p["a"]["messages"] == 1
        assert p["a"]["per_1000"] == 2000 / 8
        assert analytics.word_explorer(db, {}, "cat", "substring")["occurrences"] == 6
        assert analytics.word_explorer(db, {}, "cat", "variants")["occurrences"] == 5
        assert analytics.word_explorer(db, {}, "THE council", "phrase")["occurrences"] == 1
        assert analytics.word_explorer(db, {"person": "b"}, "cat")["occurrences"] == 1
        assert analytics.word_explorer(db, {"start": 1704240000}, "cat")["occurrences"] == 0


def test_refresh_reconciles_old_reactions_and_preserves_annotations(archive):
    wid, records = archive
    with store.workspace(wid) as db:
        store.set_meta(db, "semantic_revision", 1)
        assert store.import_records(db, records) == 0
        db.execute("INSERT INTO eras VALUES('manual','My chapter',0,9999999999,'story','[]',1,'manual-v1')")
        fresh = [dict(r) for r in records if r["id"] not in ("r1", "r2")]
        fresh[0]["text"] = "Edited original cat"
        fresh[0]["edits"] = [
            {"part": 0, "status": "Edited", "history": [{"ts": 1704151800, "text": "original"}]}
        ]
        assert store.import_records(db, fresh, full_snapshot=True) > 0
        assert db.execute("SELECT reaction_count FROM messages WHERE id='a1'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM reaction_observations WHERE event_id='r2'").fetchone()[0] == 1
        assert store.meta(db, "semantic_revision") == -1
        assert (
            db.execute("SELECT count(*) FROM message_fts WHERE message_fts MATCH 'Edited'").fetchone()[0] == 1
        )
        analysis.derive_local(db)
        assert db.execute("SELECT name FROM eras WHERE id='manual'").fetchone()[0] == "My chapter"


def test_timezone_sessions_and_pagination(archive):
    wid, _ = archive
    with store.workspace(wid) as db:
        store.set_meta(db, "timezone", "America/Los_Angeles")
        store.rebuild(db)
        la = db.execute("SELECT day FROM messages WHERE id='a2'").fetchone()[0]
        store.set_meta(db, "timezone", "UTC")
        store.rebuild(db)
        utc = db.execute("SELECT day FROM messages WHERE id='a2'").fetchone()[0]
        assert la != utc
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 2
        one = store.list_messages(db, {}, limit=2)
        two = store.list_messages(db, {}, limit=2, cursor=one["next_cursor"])
        assert len({m["id"] for m in one["items"] + two["items"]}) == 4
        assert two["next_cursor"] is None
        empty = analytics.overview(db, {"person": "nobody"})
        assert empty["totals"]["messages"] == 0


def test_cloud_citation_validation_and_exact_numbers(archive):
    wid, _ = archive
    with store.workspace(wid) as db:
        answer = cloud.numerical_answer(db, {}, "How many messages are there?")
        assert "4 messages" in answer["summary"]
        assert answer["method"] == "SQL aggregate"
    good = cloud.Narrative(
        title="Story",
        summary="Example",
        claims=[cloud.Claim(text="A quote", sources=["a1"])],
        insufficient_evidence=False,
    )
    cloud.validate_citations(good, {"a1"})
    with pytest.raises(ValueError, match="unavailable"):
        cloud.validate_citations(good, {"b1"})
    with pytest.raises(ValueError, match="no source"):
        cloud.validate_citations(
            cloud.Narrative(title="Story", summary="Example", claims=[], insufficient_evidence=False), {"a1"}
        )


def test_keyword_search_is_parameterized(archive):
    wid, _ = archive
    with store.workspace(wid) as db:
        assert "a1" in analysis.lexical_search(db, {}, "LMAO")
        analysis.lexical_search(db, {}, '"; DROP TABLE messages; --')
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 5


def test_api_security_games_identity_and_source_context(api_client):
    client, wid = api_client
    prefix = f"/api/v1/workspaces/{wid}"
    assert client.post("/api/v1/demo", headers={"X-Session-Token": ""}, json={}).status_code == 403
    assert client.get("/api/v1/config", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/v1/config", headers={"Host": "evil.example"}).status_code == 403
    assert client.get(prefix + "/messages/a1/context").status_code == 200
    assert client.get(prefix + "/attachments/missing").status_code == 400
    assert client.post(prefix + "/cloud/generate", json={"kind": "lore"}).status_code == 400
    assert (
        client.post(
            prefix + "/cloud/generate",
            json={"kind": "qa", "question": "How many messages?", "approved": True},
        ).json()["result"]["method"]
        == "SQL aggregate"
    )
    assert client.post(prefix + "/eras", json={"name": "bad", "start": 10, "end": 1}).status_code == 400
    for kind in ("who", "finish", "year"):
        # Add a long message so every game has usable evidence.
        with store.workspace(wid) as db:
            store.import_records(
                db,
                [
                    {
                        "schema_version": 1,
                        "record": "message",
                        "id": "long",
                        "chat_id": "chat",
                        "person": "a",
                        "ts": 1704151810,
                        "text": "we almost missed our flight at the airport",
                    }
                ],
            )
        game = client.get(prefix + f"/games?kind={kind}").json()
        assert "answer" not in game
        answer = client.post(
            prefix + f"/games/{game['id']}/answer", json={"answer": game["options"][0]["id"]}
        ).json()
        assert answer["message_id"] == "long"
    assert client.patch(prefix + "/people/a", json={"merge_into": "b"}).status_code == 200
    with store.workspace(wid) as db:
        assert db.execute("SELECT count(*) FROM messages WHERE person_id='a'").fetchone()[0] == 0
        assert store.meta(db, "identity_map")["a"] == "b"


def test_snapshot_copies_wal_and_does_not_change_source(tmp_path, monkeypatch):
    from gcapp import ingestion

    monkeypatch.setattr(ingestion, "ROOT", tmp_path / "data")
    monkeypatch.setattr(store, "ROOT", tmp_path / "data")
    source = tmp_path / "chat.db"
    db = sqlite3.connect(source)
    db.execute("PRAGMA journal_mode=WAL")
    for table in ("message", "chat", "handle", "chat_message_join"):
        db.execute(f"CREATE TABLE {table}(id)")
    db.execute("INSERT INTO message VALUES(42)")
    db.commit()
    iid = ingestion.snapshot(str(source))
    info = ingestion.import_info(iid)
    copied = sqlite3.connect(info["path"])
    assert copied.execute("SELECT id FROM message").fetchone()[0] == 42
    assert db.execute("SELECT id FROM message").fetchone()[0] == 42
    copied.close()
    db.close()


def test_rust_importer_on_synthetic_apple_schema(tmp_path, monkeypatch):
    binary = Path(__file__).resolve().parents[1] / "importer/target/release/gc-importer"
    if not binary.is_file():
        pytest.skip("Build Rust importer for integration test")
    path = tmp_path / "chat.db"
    db = sqlite3.connect(path)
    columns = """guid TEXT,text TEXT,service TEXT,handle_id INTEGER,destination_caller_id TEXT,subject TEXT,
    date INTEGER,date_read INTEGER,date_delivered INTEGER,is_from_me INTEGER,is_read INTEGER,item_type INTEGER,
    other_handle INTEGER,share_status INTEGER,share_direction INTEGER,group_title TEXT,group_action_type INTEGER,
    associated_message_guid TEXT,associated_message_type INTEGER,balloon_bundle_id TEXT,expressive_send_style_id TEXT,
    thread_originator_guid TEXT,thread_originator_part TEXT,date_edited INTEGER,associated_message_emoji TEXT,
    attributedBody BLOB,message_summary_info BLOB,payload_data BLOB"""
    db.executescript(
        f"CREATE TABLE message(ROWID INTEGER PRIMARY KEY,{columns});CREATE TABLE handle(ROWID INTEGER PRIMARY KEY,id TEXT);CREATE TABLE chat(ROWID INTEGER PRIMARY KEY,display_name TEXT,chat_identifier TEXT);CREATE TABLE chat_message_join(chat_id INTEGER,message_id INTEGER);CREATE TABLE chat_handle_join(chat_id INTEGER,handle_id INTEGER);CREATE TABLE attachment(ROWID INTEGER PRIMARY KEY,guid TEXT,filename TEXT,mime_type TEXT,uti TEXT,transfer_name TEXT,total_bytes INTEGER,is_sticker INTEGER,hide_attachment INTEGER);CREATE TABLE message_attachment_join(message_id INTEGER,attachment_id INTEGER);"
    )
    db.executemany("INSERT INTO handle(id) VALUES(?)", [("a",), ("b",)])
    db.execute("INSERT INTO chat(display_name,chat_identifier) VALUES('Fixture','chat')")
    db.executemany("INSERT INTO chat_handle_join VALUES(1,?)", [(1,), (2,)])
    guid = "12345678-1234-1234-1234-123456789012"
    db.execute(
        "INSERT INTO message(guid,text,date,is_from_me,handle_id,item_type,group_action_type,is_read,share_status) VALUES(?,?,600000000000000000,1,0,0,0,0,0)",
        (guid, "Hi 👋 café"),
    )
    payload = plistlib.dumps(
        {"root": plistlib.UID(1), "url": "https://example.invalid/fixture"}, fmt=plistlib.FMT_BINARY
    )
    db.execute("UPDATE message SET payload_data=? WHERE ROWID=1", (payload,))
    db.execute("INSERT INTO chat_message_join VALUES(1,1)")
    fixture = Path(__file__).parent / "fixtures/attributed-body.bin"
    db.execute(
        "INSERT INTO message(guid,date,is_from_me,handle_id,attributedBody) VALUES(?,600000000000000001,0,1,?)",
        ("22345678-1234-1234-1234-123456789012", fixture.read_bytes()),
    )
    db.execute("INSERT INTO chat_message_join VALUES(1,2)")
    db.execute("INSERT INTO handle(id) VALUES('a')")
    db.execute(
        "INSERT INTO message(guid,text,date,is_from_me,handle_id,associated_message_guid,associated_message_type) VALUES('reaction-fixture','',600000000000000002,0,3,?,2003)",
        ("p:0/" + guid,),
    )
    db.execute("INSERT INTO chat_message_join VALUES(1,3)")
    db.execute("INSERT INTO chat(display_name,chat_identifier) VALUES('Independent','other')")
    db.executemany("INSERT INTO chat_handle_join VALUES(2,?)", [(1,), (2,)])
    db.execute(
        "INSERT INTO message(guid,text,date,is_from_me,handle_id) VALUES('unselected','Do not import this other chat',600000000000000003,0,2)"
    )
    db.execute("INSERT INTO chat_message_join VALUES(2,4)")
    db.commit()
    db.close()
    result = subprocess.run([str(binary), "export", str(path), "1"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]["text"] == "Hi 👋 café"
    assert records[0]["person"] == "me"
    assert records[0]["ts"] == 1578307200
    assert records[0]["payload_xml"] is None
    decoded = plistlib.loads(base64.b64decode(records[0]["payload_binary_b64"]))
    assert decoded["root"] == plistlib.UID(1) and decoded["url"] == "https://example.invalid/fixture"
    assert records[1]["text"] == "Café 👋 — an entirely fictional message."
    assert records[1]["parts"][0]["kind"] == "run"

    assert records[2]["record"] == "reaction" and records[2]["type"] == "laugh"
    assert records[2]["person"] == "a" and records[2]["target"] == guid
    from gcapp import ingestion

    monkeypatch.setattr(store, "ROOT", tmp_path / "runtime")
    monkeypatch.setattr(ingestion, "ROOT", tmp_path / "runtime")
    iid = ingestion.snapshot(str(path))
    assert len(ingestion.discover(iid)) == 2
    wid = store.create_workspace("Selected only")
    assert ingestion.perform_import(wid, iid, [1]) > 0
    with store.workspace(wid) as db:
        assert db.execute("SELECT count(*) FROM messages WHERE kind='message'").fetchone()[0] == 2
        assert db.execute("SELECT 1 FROM messages WHERE id='unselected'").fetchone() is None
        assert (
            db.execute("SELECT url FROM links WHERE message_id=?", (guid,)).fetchone()[0]
            == "https://example.invalid/fixture"
        )
        assert db.execute("SELECT reaction_count FROM messages WHERE id=?", (guid,)).fetchone()[0] == 1
    assert ingestion.refresh(wid) == 0
