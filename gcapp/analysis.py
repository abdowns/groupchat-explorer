from __future__ import annotations

import hashlib
import json
import os
import random
from collections import Counter
from functools import lru_cache

import numpy as np

from .store import meta, scope, set_meta, stable_id, words, workspace, workspace_dir

STOP = set(
    "the a an i it to and of is in you we that this for on my are so be was at me with but or not have do just can our your from will im its as what".split()
)


def derive_local(db, progress=None):
    """Deterministic, evidence-linked suggestions. Manual annotations survive refresh."""
    db.execute("DELETE FROM eras WHERE manual=0")
    db.execute("DELETE FROM events WHERE manual=0")
    db.execute("DELETE FROM lore WHERE manual=0")
    candidates = Counter()
    for i, row in enumerate(
        db.execute("SELECT id,ts,text,person_id,topic_id FROM messages WHERE kind='message' ORDER BY ts,id")
    ):
        if progress and i % 2000 == 0:
            progress(0.1, f"Finding patterns in {i:,} messages")
        tokens = words(row["text"])
        # Bounded candidate discovery, followed by exact counts for shortlisted phrases.
        for n in (2, 3, 4):
            candidates.update(
                " ".join(tokens[j : j + n])
                for j in range(min(len(tokens) - n + 1, 30))
                if sum(t not in STOP for t in tokens[j : j + n]) >= 2
            )
        if len(candidates) > 100000:
            candidates = Counter(dict(candidates.most_common(10000)))
    shortlist = {p for p, n in candidates.most_common(60) if n >= 4}
    phrase_stats = {
        p: {"count": 0, "people": set(), "sources": [], "start": None, "end": None} for p in shortlist
    }
    for row in db.execute("SELECT id,ts,text,person_id FROM messages WHERE kind='message' ORDER BY ts,id"):
        tokens = words(row["text"])
        observed = (
            set(" ".join(tokens[j : j + n]) for n in (2, 3, 4) for j in range(len(tokens) - n + 1))
            & shortlist
        )
        for p in observed:
            s = phrase_stats[p]
            s["count"] += 1
            s["people"].add(row["person_id"])
            s["start"] = s["start"] or row["ts"]
            s["end"] = row["ts"]
            if len(s["sources"]) < 40:
                s["sources"].append(row["id"])
    chosen = []
    for phrase, s in sorted(
        phrase_stats.items(), key=lambda x: x[1]["count"] * len(x[1]["people"]), reverse=True
    ):
        if len(s["people"]) < 2 or any(phrase in p or p in phrase for p in chosen):
            continue
        chosen.append(phrase)
        db.execute(
            "INSERT INTO lore VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                stable_id("lore" + phrase),
                phrase,
                f"Earliest observed use followed by {s['count']:,} messages from {len(s['people'])} members.",
                json.dumps(s["sources"]),
                s["start"],
                s["end"],
                json.dumps(sorted(s["people"])),
                s["count"],
                0,
                "local-v1",
            ),
        )
        if len(chosen) >= 16:
            break
    from .topic_model import suggest_eras

    suggest_eras(db)
    top_sessions = db.execute(
        "SELECT s.*,s.count+coalesce(sum(m.reaction_count),0)*2+sum(m.reply_to IS NOT NULL)*2 engagement FROM sessions s JOIN messages m ON m.session_id=s.id GROUP BY s.id ORDER BY engagement DESC LIMIT 16"
    ).fetchall()
    for s in top_sessions:
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
            (
                stable_id("event" + s["id"]),
                f"{s['count']:,} messages in one conversation",
                s["start"],
                "burst",
                "An unusually active exchange. Explore the messages to see what happened.",
                s["sources"],
                0,
                "local-v1",
            ),
        )
    last = None
    for s in db.execute("SELECT * FROM sessions ORDER BY start"):
        if last and s["start"] - last > 21 * 86400:
            days = int((s["start"] - last) / 86400)
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                (
                    stable_id("revival" + s["id"]),
                    f"Back after {days} quiet days",
                    s["start"],
                    "revival",
                    "A conversation restarted after a long gap in the observed archive.",
                    s["sources"],
                    0,
                    "local-v1",
                ),
            )
        last = s["end"]
    for r in db.execute("SELECT * FROM messages WHERE kind='system' ORDER BY ts"):
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
            (
                stable_id("system" + r["id"]),
                r["text"] or "Group update",
                r["ts"],
                "group",
                "Recorded group event",
                json.dumps([r["id"]]),
                0,
                "local-v1",
            ),
        )


@lru_cache(maxsize=2)
def embedding_model(name="sentence-transformers/all-MiniLM-L6-v2"):
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ValueError("Install analysis dependencies: .venv/bin/pip install -e '.[analysis]'") from e
    torch.set_num_threads(4)
    return SentenceTransformer(name, device="mps" if torch.backends.mps.is_available() else "cpu")


def build_semantics(wid, progress):
    import hnswlib

    from .topic_model import content, discover_topics, stopwords

    progress(0.01, "Loading the local embedding model (first run downloads model weights)")
    model = embedding_model()
    directory = workspace_dir(wid)
    with workspace(wid) as db:
        revision = meta(db, "revision", 0)
        db.execute("DELETE FROM passages")
        db.execute("DELETE FROM topics")
        db.execute("UPDATE messages SET topic_id=NULL")
        stops = stopwords(db)
        total = db.execute("SELECT count(*) FROM messages WHERE kind='message'").fetchone()[0]
        batch, passage_ids, labels, eligible = [], [], [], []
        capacity = max(1000, total * 2)
        index = hnswlib.Index(space="cosine", dim=384)
        index.init_index(max_elements=capacity, ef_construction=100, M=16)
        index.set_num_threads(4)
        passage_vectors = []
        topic_samples = []
        processed = 0
        counter = 0
        reservoir = random.Random(174)
        sample_seen = 0
        duplicates = Counter()
        cache = directory / "embedding-cache"
        cache.mkdir(exist_ok=True)

        def encoded(texts):
            digest = hashlib.sha256(json.dumps(["minilm-v1", texts], ensure_ascii=False).encode()).hexdigest()
            path = cache / (digest + ".npy")
            if path.is_file():
                return np.load(path, allow_pickle=False)
            result = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
            temp = cache / (digest + ".pending.npy")
            np.save(temp, result)
            os.replace(temp, path)
            return result

        def flush():
            nonlocal counter, sample_seen
            if not batch:
                return
            vectors = encoded(batch)
            if counter + len(batch) > index.get_max_elements():
                index.resize_index(counter + len(batch) + 1000)
            index.add_items(vectors, labels)
            # Topic discovery sees only substantive, speaker-free conversation passages.
            for pid, vector, text, candidate in zip(passage_ids, vectors, batch, eligible):
                if not candidate:
                    continue
                fingerprint = hashlib.sha256(text.encode()).hexdigest()
                if duplicates[fingerprint] >= 2:
                    continue
                if len(duplicates) < 100000:
                    duplicates[fingerprint] += 1
                sample_seen += 1
                if len(topic_samples) < 12000:
                    topic_samples.append((pid, text))
                    passage_vectors.append(vector)
                else:
                    position = reservoir.randrange(sample_seen)
                    if position < 12000:
                        topic_samples[position] = (pid, text)
                        passage_vectors[position] = vector
            counter += len(batch)
            batch.clear()
            labels.clear()
            passage_ids.clear()
            eligible.clear()

        def add(text, sources, start, end, individual=False):
            tokens = model.tokenizer.encode(text, add_special_tokens=False)
            for offset in range(0, len(tokens), 180):
                chunk = model.tokenizer.decode(tokens[max(0, offset - 30) : offset + 180])
                if not chunk.strip():
                    continue
                row = db.execute(
                    "INSERT INTO passages(text,sources,start,end,version) VALUES(?,?,?,?,?)",
                    (
                        chunk,
                        json.dumps(sources),
                        start,
                        end,
                        f"minilm-message-v2-r{revision}" if individual else f"minilm-v1-r{revision}",
                    ),
                )
                batch.append(chunk)
                labels.append(row.lastrowid)
                passage_ids.append(row.lastrowid)
                eligible.append(not individual and len(set(words(chunk))) >= 5)
                if len(batch) >= 96:
                    flush()

        session, buffer, ids, start, end = None, [], [], None, None
        for r in db.execute(
            "SELECT id,ts,text,person_id,session_id FROM messages WHERE kind='message' ORDER BY ts,id"
        ):
            if r["session_id"] != session or len(buffer) >= 8:
                if buffer:
                    add("\n".join(buffer), ids, start, end)
                buffer, ids, start = [], [], r["ts"]
                session = r["session_id"]
            if r["text"].strip():
                add(r["text"], [r["id"]], r["ts"], r["ts"], individual=True)
            tokens = content(r["text"], stops)
            if len(set(tokens)) >= 2:
                if not buffer:
                    start = r["ts"]
                buffer.append(" ".join(tokens))
                ids.append(r["id"])
                end = r["ts"]
            processed += 1
            if processed % 200 == 0:
                progress(
                    0.05 + 0.65 * processed / max(1, total), f"Embedding {processed:,} / {total:,} messages"
                )
        if buffer:
            add("\n".join(buffer), ids, start, end)
        flush()
        if counter == 0:
            raise ValueError("No text is available to index")
        progress(0.75, "Discovering substantive conversation themes")
        discover_topics(db, topic_samples, passage_vectors, index, model, stops, progress)
        progress(0.94, "Saving the search index")
        temp = directory / "semantic.pending.hnsw"
        index.save_index(str(temp))
        os.replace(temp, directory / "semantic.hnsw")
        db.execute("DELETE FROM semantic_match_queries")
        set_meta(db, "semantic_message_version", 2)
        set_meta(db, "semantic_revision", revision)
        set_meta(db, "semantic_passages", counter)
        derive_local(db)
    progress(1, "Semantic search and topics ready")


def lexical_search(db, filters, query, limit=100):
    tokens = words(query)
    if not tokens:
        return []
    expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
    where, args = scope(db, **filters)
    return [
        r[0]
        for r in db.execute(
            f"SELECT m.id FROM message_fts JOIN messages m ON m.rowid=message_fts.rowid WHERE message_fts MATCH ? AND {where} ORDER BY bm25(message_fts) LIMIT ?",
            [expression] + args + [limit],
        )
    ]


@lru_cache(maxsize=2)
def loaded_index(path, modified):
    import hnswlib

    index = hnswlib.Index(space="cosine", dim=384)
    index.load_index(path)
    index.set_ef(400)
    index.set_num_threads(4)
    return index


def search(db, wid, filters, query, mode="hybrid", limit=60):
    lexical = lexical_search(db, filters, query, max(100, limit)) if mode != "semantic" else []
    semantic = []
    ready = (
        meta(db, "semantic_revision", -1) == meta(db, "revision", 0)
        and (workspace_dir(wid) / "semantic.hnsw").is_file()
    )
    if mode in ("semantic", "hybrid") and ready:
        model = embedding_model()
        path = workspace_dir(wid) / "semantic.hnsw"
        index = loaded_index(str(path), path.stat().st_mtime_ns)
        where, args = scope(db, **filters)
        k = min(index.get_current_count(), max(200, limit * 8))
        labels, distances = index.knn_query(model.encode([query], normalize_embeddings=True), k=k)
        seen = set()
        for pid, distance in zip(labels[0], distances[0]):
            if distance > 0.85:
                continue
            row = db.execute("SELECT sources FROM passages WHERE id=?", (int(pid),)).fetchone()
            if not row:
                continue
            for sid in json.loads(row[0]):
                if (
                    sid not in seen
                    and db.execute(
                        f"SELECT 1 FROM messages m WHERE {where} AND m.id=?", args + [sid]
                    ).fetchone()
                ):
                    semantic.append(sid)
                    seen.add(sid)
    elif mode == "semantic":
        raise ValueError("Build the local semantic index in Settings → Analysis first")
    scores = Counter()
    for ranking in (lexical, semantic):
        for rank, sid in enumerate(ranking):
            scores[sid] += 1 / (60 + rank + 1)
    return {
        "ids": [sid for sid, _ in scores.most_common(limit)],
        "semantic_ready": ready,
        "mode_used": mode if ready or mode == "keyword" else "keyword",
        "scores": dict(scores),
    }
