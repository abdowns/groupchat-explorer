"""Whole-corpus semantic prevalence with individual authorship and inspectable matches."""

import json
import uuid

import numpy as np

from . import analysis, jobs
from .store import list_messages, meta, registry, scope, stable_id, workspace, workspace_dir


def index_ready(db, wid):
    return (
        meta(db, "semantic_message_version", 0) == 2
        and meta(db, "semantic_revision", -1) == meta(db, "revision", 0)
        and (workspace_dir(wid) / "semantic.hnsw").is_file()
    )


def query_id(db, query, threshold):
    query = query.strip()
    if not query:
        raise ValueError("Describe a topic, word, or phrase to analyze")
    return stable_id(json.dumps(["semantic-prevalence-v2", query, threshold, meta(db, "revision", 0)]))


def state(db, wid, query, threshold):
    qid = query_id(db, query, threshold)
    if not index_ready(db, wid):
        return {"id": qid, "ready": False, "status": "index_required"}
    row = db.execute("SELECT * FROM semantic_match_queries WHERE id=?", (qid,)).fetchone()
    if row and row["ready"]:
        return {"id": qid, "ready": True, "status": "complete"}
    if row and row["job_id"]:
        with registry() as reg:
            job = reg.execute(
                "SELECT id,status,progress,message FROM jobs WHERE id=?", (row["job_id"],)
            ).fetchone()
        if job:
            details = dict(job)
            details["job_id"] = details.pop("id")
            return {"id": qid, "ready": False, **details}
    return {"id": qid, "ready": False, "status": "not_analyzed"}


def enqueue(db, wid, query, threshold):
    status = state(db, wid, query, threshold)
    if status["status"] == "index_required":
        raise ValueError("Build or rebuild the local semantic index in Settings & analysis first")
    if status["ready"] or status["status"] in ("queued", "running"):
        return status
    qid = query_id(db, query, threshold)
    jid = uuid.uuid4().hex
    db.execute(
        "INSERT INTO semantic_match_queries VALUES(?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET ready=0,job_id=excluded.job_id",
        (qid, query.strip(), threshold, meta(db, "revision", 0), jid),
    )
    db.commit()  # Make the query visible before the worker can claim its job.
    jid = jobs.enqueue(
        wid,
        "semantic-ranking",
        {
            "query_id": qid,
            "query": query.strip(),
            "threshold": threshold,
            "revision": meta(db, "revision", 0),
        },
        jid=jid,
    )
    return {"id": qid, "ready": False, "status": "queued", "job_id": jid}


def compute_matches(wid, payload, progress):
    with workspace(wid) as db:
        if not index_ready(db, wid) or payload["revision"] != meta(db, "revision", 0):
            raise ValueError("The archive changed. Rebuild the semantic index and analyze the topic again.")
        qid = payload["query_id"]
        if not db.execute("SELECT 1 FROM semantic_match_queries WHERE id=?", (qid,)).fetchone():
            raise ValueError("The index was rebuilt. Analyze this topic again.")
        progress(0.01, "Comparing the topic against every authored message")
        vector = np.asarray(analysis.embedding_model().encode([payload["query"]], normalize_embeddings=True))[
            0
        ]
        path = workspace_dir(wid) / "semantic.hnsw"
        index = analysis.loaded_index(str(path), path.stat().st_mtime_ns)
        db.execute("DELETE FROM semantic_matches WHERE query_id=?", (qid,))
        total = db.execute(
            "SELECT count(*) FROM passages WHERE version LIKE 'minilm-message-v2-r%'"
        ).fetchone()[0]
        processed = 0
        cursor = 0
        while True:
            rows = db.execute(
                "SELECT id,json_extract(sources,'$[0]') AS message_id FROM passages "
                "WHERE id>? AND version LIKE 'minilm-message-v2-r%' AND json_array_length(sources)=1 ORDER BY id LIMIT 1024",
                (cursor,),
            ).fetchall()
            if not rows:
                break
            vectors = np.asarray(index.get_items([r["id"] for r in rows]), dtype=np.float32)
            scores = vectors @ vector
            matched = [
                (qid, row["message_id"], float(score))
                for row, score in zip(rows, scores)
                if score >= payload["threshold"]
            ]
            db.executemany(
                "INSERT INTO semantic_matches VALUES(?,?,?) ON CONFLICT(query_id,message_id) "
                "DO UPDATE SET score=max(score,excluded.score)",
                matched,
            )
            processed += len(rows)
            cursor = rows[-1]["id"]
            progress(
                min(0.99, processed / max(1, total)), f"Compared {processed:,} / {total:,} message chunks"
            )
        db.execute("UPDATE semantic_match_queries SET ready=1 WHERE id=?", (qid,))
    progress(1, "Semantic topic matches ready")


def ranking(db, wid, filters, query, threshold, minimum):
    status = state(db, wid, query, threshold)
    if not status["ready"]:
        return status
    qid = status["id"]
    where, args = scope(db, **filters)
    rows = db.execute(
        f"SELECT p.id,p.name,p.color,count(*) AS messages,count(s.message_id) AS matches "
        f"FROM messages m JOIN people p ON p.id=m.person_id "
        f"LEFT JOIN semantic_matches s ON s.message_id=m.id AND s.query_id=? WHERE {where} GROUP BY p.id",
        [qid] + args,
    ).fetchall()
    people = [dict(r, per_1000=r["matches"] * 1000 / r["messages"]) for r in rows if r["messages"] >= minimum]
    people.sort(key=lambda r: (-r["per_1000"], -r["matches"], r["id"]))
    trend = [
        dict(r)
        for r in db.execute(
            f"SELECT substr(m.day,1,7) AS date,count(*) AS count FROM messages m "
            f"JOIN semantic_matches s ON s.message_id=m.id AND s.query_id=? WHERE {where} GROUP BY date ORDER BY date",
            [qid] + args,
        )
    ]
    return {
        **status,
        "query": query.strip(),
        "threshold": threshold,
        "minimum": minimum,
        "people": people,
        "matching_messages": sum(r["matches"] for r in rows),
        "total_messages": sum(r["messages"] for r in rows),
        "trend": trend,
        "messages": list_messages(db, filters, 12, semantic_query=qid)["items"],
    }


def matches(db, wid, filters, query, threshold, limit, cursor):
    status = state(db, wid, query, threshold)
    if not status["ready"]:
        raise ValueError("Analyze this semantic topic before browsing its matches")
    return list_messages(db, filters, limit, cursor, semantic_query=status["id"])
