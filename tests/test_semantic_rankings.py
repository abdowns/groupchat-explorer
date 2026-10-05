import json

import numpy as np
import pytest

from gcapp import analysis, jobs, semantic_rankings, store


@pytest.fixture
def semantic_archive(archive, monkeypatch):
    wid, _ = archive
    vectors = {1: [0.8, 0.6], 2: [0.9, 0.4358899], 3: [0.7, 0.7141428], 4: [0.2, 0.9797959], 5: [1.0, 0.0]}

    class Model:
        def encode(self, texts, **kwargs):
            return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)

    class Index:
        def get_items(self, ids):
            return np.array([vectors[pid] for pid in ids], dtype=np.float32)

    monkeypatch.setattr(analysis, "embedding_model", lambda: Model())
    monkeypatch.setattr(analysis, "loaded_index", lambda *args: Index())
    with store.workspace(wid) as db:
        store.set_meta(db, "semantic_revision", store.meta(db, "revision", 0))
        store.set_meta(db, "semantic_message_version", 2)
        for pid, sources, version in [
            (1, ["a1"], "minilm-message-v2-r1"),
            (2, ["a1"], "minilm-message-v2-r1"),  # Same message's second chunk.
            (3, ["b1"], "minilm-message-v2-r1"),
            (4, ["a2"], "minilm-message-v2-r1"),
            (5, ["a2", "b2"], "minilm-v1-r1"),  # Context must not credit either author.
        ]:
            db.execute(
                "INSERT INTO passages(id,text,sources,start,end,version) VALUES(?,?,?,?,?,?)",
                (pid, "synthetic embedding", json.dumps(sources), 0, 0, version),
            )
    (store.workspace_dir(wid) / "semantic.hnsw").write_bytes(b"synthetic")
    return wid


def run_query(wid, query="dating and romance", threshold=0.5):
    with store.workspace(wid) as db:
        result = semantic_rankings.enqueue(db, wid, query, threshold)
    with store.registry() as db:
        job = dict(db.execute("SELECT * FROM jobs WHERE id=?", (result["job_id"],)).fetchone())
    jobs.execute(job)
    return result


def test_semantic_full_corpus_counts_denominators_chunks_and_context(semantic_archive):
    wid = semantic_archive
    run_query(wid)
    with store.workspace(wid) as db:
        result = semantic_rankings.ranking(db, wid, {}, "dating and romance", 0.5, 1)
        assert result["ready"] and result["matching_messages"] == 2
        assert result["total_messages"] == 4  # Includes the attachment-only authored message.
        assert {r["id"]: (r["matches"], r["messages"], r["per_1000"]) for r in result["people"]} == {
            "a": (1, 2, 500),
            "b": (1, 2, 500),
        }
        assert sum(r["count"] for r in result["trend"]) == 2
        assert {m["id"] for m in result["messages"]} == {"a1", "b1"}
        assert db.execute("SELECT score FROM semantic_matches WHERE message_id='a1'").fetchone()[
            0
        ] == pytest.approx(0.9)
        assert semantic_rankings.enqueue(db, wid, "dating and romance", 0.5)["ready"]  # Reuse completed work.
        assert semantic_rankings.ranking(db, wid, {}, "dating and romance", 0.5, 20)["people"] == []


def test_semantic_filters_thresholds_and_paginated_sources(semantic_archive):
    wid = semantic_archive
    run_query(wid)
    run_query(wid, threshold=0.85)
    with store.workspace(wid) as db:
        filtered = semantic_rankings.ranking(db, wid, {"person": "b"}, "dating and romance", 0.5, 1)
        assert filtered["total_messages"] == 2 and filtered["matching_messages"] == 1
        assert filtered["people"][0]["per_1000"] == 500
        before = semantic_rankings.ranking(db, wid, {"end": 1704151801}, "dating and romance", 0.5, 1)
        assert before["total_messages"] == before["matching_messages"] == 1
        strict = semantic_rankings.ranking(db, wid, {}, "dating and romance", 0.85, 1)
        assert strict["matching_messages"] == 1
        assert next(p for p in strict["people"] if p["id"] == "b")["per_1000"] == 0
        first = semantic_rankings.matches(db, wid, {}, "dating and romance", 0.5, 1, None)
        second = semantic_rankings.matches(db, wid, {}, "dating and romance", 0.5, 1, first["next_cursor"])
        assert first["items"][0]["id"] != second["items"][0]["id"]
        assert second["next_cursor"] is None
        store.set_meta(db, "revision", store.meta(db, "revision", 0) + 1)
        assert semantic_rankings.state(db, wid, "dating and romance", 0.5)["status"] == "index_required"
        with pytest.raises(ValueError, match="Rebuild"):
            semantic_rankings.compute_matches(wid, {"query_id": "old", "revision": -1}, lambda *args: None)


def test_semantic_api_enqueues_worker_and_returns_traceable_matches(semantic_archive, api_client):
    client, wid = api_client
    path = f"/api/v1/workspaces/{wid}"
    assert client.get(path + "/semantic-words", params={"q": "romance"}).json()["status"] == "not_analyzed"
    queued = client.post(path + "/semantic-words/analyze", json={"q": "romance", "threshold": 0.5}).json()
    assert queued["status"] == "queued"
    assert (
        client.post(path + "/semantic-words/analyze", json={"q": "romance", "threshold": 0.5}).json()[
            "status"
        ]
        == "queued"
    )
    with store.registry() as db:
        row = dict(db.execute("SELECT * FROM jobs WHERE id=?", (queued["job_id"],)).fetchone())
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
    jobs.execute(row)
    result = client.get(
        path + "/semantic-words", params={"q": "romance", "threshold": 0.5, "minimum": 1}
    ).json()
    assert result["matching_messages"] == 2 and result["total_messages"] == 4
    page = client.get(
        path + "/semantic-matches", params={"q": "romance", "threshold": 0.5, "person": "a"}
    ).json()
    assert [m["id"] for m in page["items"]] == ["a1"]
    assert (
        client.post(path + "/semantic-words/analyze", json={"q": "romance", "threshold": 2}).status_code
        == 422
    )
    assert client.post(path + "/semantic-words/analyze", json={"q": " "}).status_code == 400
    with store.workspace(wid) as db:
        store.set_meta(db, "semantic_message_version", 0)
    assert client.get(path + "/semantic-words", params={"q": "romance"}).json()["status"] == "index_required"


def test_semantic_job_cancellation_rolls_back_partial_matches(semantic_archive):
    wid = semantic_archive
    with store.workspace(wid) as db:
        queued = semantic_rankings.enqueue(db, wid, "romance", 0.5)
    with store.registry() as db:
        payload = json.loads(
            db.execute("SELECT payload FROM jobs WHERE id=?", (queued["job_id"],)).fetchone()[0]
        )

    def cancelled(progress, message):
        if progress > 0.01:
            raise jobs.Cancelled()

    with pytest.raises(jobs.Cancelled):
        semantic_rankings.compute_matches(wid, payload, cancelled)
    with store.workspace(wid) as db:
        assert db.execute("SELECT count(*) FROM semantic_matches").fetchone()[0] == 0
        assert not db.execute("SELECT ready FROM semantic_match_queries").fetchone()[0]
