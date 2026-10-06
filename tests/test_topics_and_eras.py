import json
from datetime import datetime, timezone

import numpy as np
import pytest

from gcapp import analysis, store, topic_model


def test_substantive_content_excludes_names_filler_and_urls(archive):
    wid, _ = archive
    with store.workspace(wid) as db:
        db.execute("UPDATE people SET name='Daniil Landau' WHERE id='a'")
        stops = topic_model.stopwords(db)
    assert (
        topic_model.content("Daniil Landau bro bro yeah unk unk fr https://example.invalid/college", stops)
        == []
    )
    assert topic_model.content(
        "college applications, scholarship deadlines and admissions essays", stops
    ) == ["college", "applications", "scholarship", "deadlines", "admissions", "essays"]


def test_semantic_discovery_uses_python_labels_and_leaves_filler_unclassified(tmp_path, monkeypatch):
    import hdbscan

    monkeypatch.setattr(store, "ROOT", tmp_path)
    wid = store.create_workspace("Synthetic subjects")
    texts = [
        "admissions application scholarship essays recommendation college",
        "airport beach ferry croatia vacation hotel",
    ]
    records = []
    samples, vectors, encoded = [], [], {}
    for group, text in enumerate(texts):
        for i in range(8):
            mid = f"{group}-{i}"
            records.append(
                dict(
                    schema_version=1,
                    record="message",
                    id=mid,
                    person="a",
                    chat_id="x",
                    ts=1704326400 + i * 7200 + group * 86400 * 30,
                    text=text,
                )
            )
            pid = len(samples) + 1
            samples.append((pid, text))
            vector = [1.0, 0.0] if group == 0 else [0.0, 1.0]
            vectors.append(vector)
            encoded[pid] = vector
    records.append(
        dict(
            schema_version=1,
            record="message",
            id="filler",
            person="a",
            chat_id="x",
            ts=1704326401,
            text="bro yeah unk fr",
        )
    )
    encoded[17] = [1.0, 0.0]

    class Projection:
        def fit_transform(self, values):
            return values

    class Clustering:
        def fit_predict(self, values):
            return np.array([0] * 8 + [1] * 8, dtype=np.int64)

    class Model:
        def encode(self, terms, **kwargs):
            return np.array(
                [[1.0, 0.0] if any(t in texts[0] for t in term.split()) else [0.0, 1.0] for term in terms]
            )

    class Index:
        def get_items(self, ids):
            return np.array([encoded[i] for i in ids])

    monkeypatch.setattr("umap.UMAP", lambda **kwargs: Projection())
    monkeypatch.setattr(hdbscan, "HDBSCAN", lambda **kwargs: Clustering())
    with store.workspace(wid) as db:
        store.import_records(db, records)
        for pid, record in enumerate(records, 1):
            db.execute(
                "INSERT INTO passages(id,text,sources,start,end,version) VALUES(?,?,?,?,?,?)",
                (pid, record["text"], json.dumps([record["id"]]), 0, 0, "minilm-message-v2-r1"),
            )
        topic_model.discover_topics(
            db, samples, vectors, Index(), Model(), topic_model.stopwords(db), lambda *args: None
        )
        topics = db.execute("SELECT * FROM topics").fetchall()
        assert len(topics) == 2
        assert {t["count"] for t in topics} == {8}
        assert db.execute("SELECT topic_id FROM messages WHERE id='filler'").fetchone()[0] is None
        assert all("bro" not in t["label"] and "unk" not in t["label"] for t in topics)
        assert store.meta(db, "topic_model_version") == topic_model.VERSION
        assert all(
            db.execute("SELECT 1 FROM messages WHERE id=?", (sid,)).fetchone()
            for t in topics
            for sid in json.loads(t["sources"])
        )


@pytest.fixture
def thematic_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    wid = store.create_workspace("Fictional thematic arcs")
    start = datetime(2024, 1, 4, tzinfo=timezone.utc).timestamp()
    records = []
    for phase, text in enumerate(
        [
            "college applications essays admissions scholarship",
            "croatia ferry beach airport vacation",
            "college dorm roommate move unpacking orientation",
        ]
    ):
        for week in range(2):
            for i in range(10):
                records.append(
                    dict(
                        schema_version=1,
                        record="message",
                        id=f"p{phase}-{week}-{i}",
                        person=["a", "b"][i % 2],
                        chat_id="x",
                        ts=start + phase * 8 * 604800 + week * 604800 + (i // 5) * 86400 + i * 60,
                        text=text,
                    )
                )
    with store.workspace(wid) as db:
        store.import_records(db, records)
        for phase, label in enumerate(["Applications", "Croatia holiday", "Moving into dorms"]):
            db.execute(
                "INSERT INTO topics VALUES(?,?,?,?,?,?)",
                (phase, label, json.dumps([label]), 20, "[]", topic_model.VERSION),
            )
            db.execute("UPDATE messages SET topic_id=? WHERE id LIKE ?", (phase, f"p{phase}-%"))
        store.set_meta(db, "topic_model_version", topic_model.VERSION)
        store.set_meta(db, "semantic_revision", store.meta(db, "revision"))
        store.set_meta(db, "topic_stopwords", sorted(topic_model.stopwords(db)))
        analysis.derive_local(db)
    return wid


def test_eras_follow_topic_shifts_preserve_manual_edits_and_dismissals(thematic_archive):
    wid = thematic_archive
    with store.workspace(wid) as db:
        eras = db.execute("SELECT * FROM eras ORDER BY start").fetchall()
        assert len(eras) == 3
        assert all(e["version"] == topic_model.VERSION for e in eras)
        assert all(eras[i]["end"] < eras[i + 1]["start"] for i in range(2))
        assert "croatia" in eras[1]["name"].lower() or "beach" in eras[1]["name"].lower()
        assert all(
            db.execute("SELECT 1 FROM messages WHERE id=?", (sid,)).fetchone()
            for e in eras
            for sid in json.loads(e["sources"])
        )
        store.set_meta(db, "dismissed_eras", [eras[1]["id"]])
        db.execute("UPDATE eras SET manual=1,name='My application chapter' WHERE id=?", (eras[0]["id"],))
        analysis.derive_local(db)
        assert db.execute("SELECT count(*) FROM eras").fetchone()[0] == 2
        assert (
            db.execute("SELECT name FROM eras WHERE id=?", (eras[0]["id"],)).fetchone()[0]
            == "My application chapter"
        )
        assert db.execute("SELECT 1 FROM eras WHERE id=?", (eras[1]["id"],)).fetchone() is None
        store.set_meta(db, "semantic_revision", -1)
        analysis.derive_local(db)
        assert db.execute("SELECT count(*) FROM eras").fetchone()[0] == 1  # Only manual era remains.


def test_topic_prevalence_conversations_filters_and_delete_api(thematic_archive):
    from fastapi.testclient import TestClient

    from gcapp.api import SESSION_TOKEN, app

    wid = thematic_archive
    client = TestClient(app, headers={"X-Session-Token": SESSION_TOKEN})
    prefix = f"/api/v1/workspaces/{wid}"
    result = client.get(prefix + "/topics").json()
    assert result["ready"] and len(result["topics"]) == 3
    assert sum(t["total"] for t in result["totals"]) == 60
    assert all(0 < point["share"] <= 1 for point in result["trend"])
    detail = client.get(prefix + "/topics/1/conversations").json()
    assert len(detail["conversations"]) >= 2
    assert sum(c["topic_messages"] for c in detail["conversations"]) == 20
    filtered = client.get(prefix + "/topics", params={"person": "b"}).json()
    assert sum(t["total"] for t in filtered["totals"]) == 30
    eras = client.get(prefix + "/timeline").json()["eras"]
    assert client.delete(prefix + "/eras/" + eras[1]["id"]).status_code == 200
    with store.workspace(wid) as db:
        analysis.derive_local(db)
    assert eras[1]["id"] not in {e["id"] for e in client.get(prefix + "/timeline").json()["eras"]}


def test_sparse_periods_do_not_create_eras(archive):
    wid, _ = archive
    with store.workspace(wid) as db:
        store.set_meta(db, "topic_model_version", topic_model.VERSION)
        store.set_meta(db, "semantic_revision", store.meta(db, "revision"))
        db.execute("UPDATE messages SET topic_id=1")
        db.execute("INSERT INTO topics VALUES(1,'Sparse', '[]',4,'[]',?)", (topic_model.VERSION,))
        analysis.derive_local(db)
        assert db.execute("SELECT count(*) FROM eras").fetchone()[0] == 0
