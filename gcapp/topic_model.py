"""Discover evidence-backed themes, suppress conversational filler, and trace temporal arcs."""

import json
import math
import re
from collections import Counter, defaultdict

import numpy as np

from .store import meta, set_meta, stable_id, words

VERSION = "semantic-topics-v3"
# Conversational stopwords are generic language cleanup, never a list of topics.
FILLER = set(
    "bro bruh dude yeah yea ye yep yup yes nah nope ok okay lol lmao lmfao rofl fr ngl tbh idk imo omg wtf tf ts unk damn goddamn bet literally really just like know think gonna wanna got getting says said say hey hi hello thanks thank haha hahaha huh hmm um uh yo shit fuck fucking doesnt didnt dont cant isnt im ive youre thats theres hes shes ill sure cool crazy insane sleepy reaction reacted sent message attachment image photo https http com www".split()
)


def stopwords(db):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    stops = set(ENGLISH_STOP_WORDS) | FILLER
    for row in db.execute("SELECT id,name,aliases FROM people"):
        for value in [row["id"], row["name"], *json.loads(row["aliases"] or "[]")]:
            stops.update(t for t in words(str(value)) if len(t) > 1)
    frequency = Counter()
    total = 0
    for row in db.execute("SELECT text FROM messages WHERE kind='message' AND words>0"):
        frequency.update(set(words(row["text"])))
        total += 1
    # Archive-specific, ubiquitous short filler; do not discard ordinary topic nouns.
    if total >= 50:
        stops.update(t for t, count in frequency.items() if count / total > 0.3 and len(t) <= 3)
    return stops


def content(text, stops):
    text = re.sub(r"https?://\S+", " ", text)
    return [t for t in words(text) if t not in stops and len(t) > 2 and not t.isnumeric()]


def representative_terms(texts, labels, vectors, model, stops):
    """Document IDF + class frequency, semantic relevance, and phrase diversity."""
    from sklearn.feature_extraction.text import CountVectorizer

    def phrases(text):
        # Keep phrases contiguous in original sentences; removing stopwords
        # first would invent labels such as "date wants" or "dormitory packed".
        for line in text.splitlines():
            tokens = words(line)
            for i, token in enumerate(tokens):
                if token in stops or len(token) <= 2 or token.isnumeric():
                    continue
                yield token
                if i + 1 < len(tokens):
                    nxt = tokens[i + 1]
                    if nxt not in stops and len(nxt) > 2 and not nxt.isnumeric() and token != nxt:
                        yield token + " " + nxt

    vectorizer = CountVectorizer(analyzer=phrases, min_df=2, max_features=16000)
    try:
        counts = vectorizer.fit_transform(texts).astype(float)
    except ValueError:
        return {}
    terms = vectorizer.get_feature_names_out()
    df = np.asarray((counts > 0).sum(axis=0)).ravel()
    idf = np.log((1 + len(texts)) / (1 + df)) + 1
    output = {}
    for label in sorted({int(value) for value in labels if value >= 0}):
        indices = np.flatnonzero(labels == label)
        # Sublinear TF stops repeated words from winning; common terms have lower IDF.
        term_counts = np.asarray(counts[indices].sum(axis=0)).ravel()
        scores = np.log1p(term_counts) * idf
        candidates = scores.argsort()[-40:][::-1]
        candidates = [
            j
            for j in candidates
            if term_counts[j] >= 2 and len(set(terms[j].split())) == len(terms[j].split())
        ]
        if not candidates:
            continue
        centroid = vectors[indices].mean(axis=0)
        centroid /= max(np.linalg.norm(centroid), 1e-8)
        term_vectors = model.encode(
            [str(terms[j]) for j in candidates], normalize_embeddings=True, show_progress_bar=False
        )
        similarities = np.asarray(term_vectors) @ centroid
        ranked = sorted(
            zip(candidates, similarities),
            key=lambda item: scores[item[0]] * max(0, item[1]) * (1.15 if " " in terms[item[0]] else 1),
            reverse=True,
        )
        chosen = []
        for j, similarity in ranked:
            term = str(terms[j])
            if similarity < 0.15 or any(set(term.split()) & set(t.split()) for t in chosen):
                continue
            chosen.append(term)
            if len(chosen) == 5:
                break
        if chosen:
            output[label] = (chosen, centroid)
    return output


def discover_topics(db, samples, vectors, index, model, stops, progress):
    import hdbscan
    from umap import UMAP

    db.execute("DELETE FROM topics")
    db.execute("UPDATE passages SET topic_id=NULL")
    db.execute("UPDATE messages SET topic_id=NULL")
    set_meta(db, "topic_stopwords", sorted(stops))
    set_meta(db, "topic_model_version", VERSION)
    if len(samples) < 10:
        set_meta(db, "topic_quality", {"documents": len(samples), "topics": 0})
        return
    vectors = np.asarray(vectors, dtype=np.float32)
    reduced = UMAP(
        n_neighbors=min(15, len(samples) - 1),
        n_components=min(5, len(samples) - 2),
        min_dist=0,
        metric="cosine",
        random_state=42,
        n_jobs=1,
    ).fit_transform(vectors)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=max(5, min(30, len(samples) // 80)), min_samples=3, cluster_selection_method="eom"
    )
    labels = clusterer.fit_predict(reduced)
    original_texts = []
    for pid, text in samples:
        row = db.execute("SELECT sources FROM passages WHERE id=?", (pid,)).fetchone()
        ids = json.loads(row[0]) if row else []
        original_texts.append(
            "\n".join(
                r[0][:1000] for sid in ids for r in db.execute("SELECT text FROM messages WHERE id=?", (sid,))
            )
            or text
        )
    representations = representative_terms(original_texts, labels, vectors, model, stops)
    # Merge near-identical cluster fragments, retaining unrelated or uncertain material as noise.
    learned = []
    for label, (terms, centroid) in representations.items():
        indices = np.flatnonzero(labels == label)
        coherence = float((vectors[indices] @ centroid).mean())
        if coherence < 0.4:
            continue
        duplicate = next((t for t in learned if float(t[2] @ centroid) > 0.86), None)
        if duplicate:
            labels[labels == label] = duplicate[0]
        else:
            learned.append((label, terms, centroid))
    if not learned:
        set_meta(db, "topic_quality", {"documents": len(samples), "topics": 0})
        return
    centroids = np.asarray([t[2] for t in learned])
    for label, terms, _ in learned:
        db.execute(
            "INSERT INTO topics VALUES(?,?,?,?,?,?)",
            (label, " · ".join(terms[:2]).title(), json.dumps(terms), 0, "[]", VERSION),
        )
    # Score every individual message in batches. Context does not give filler replies a topic.
    cursor = 0
    processed = 0
    while True:
        rows = db.execute(
            "SELECT p.id,json_extract(p.sources,'$[0]') AS sid,m.text FROM passages p JOIN messages m ON m.id=json_extract(p.sources,'$[0]') WHERE p.id>? AND p.version LIKE 'minilm-message-v2-r%' ORDER BY p.id LIMIT 512",
            (cursor,),
        ).fetchall()
        if not rows:
            break
        vectors_batch = np.asarray(index.get_items([r["id"] for r in rows]))
        sims = vectors_batch @ centroids.T
        for row, sim in zip(rows, sims):
            tokens = content(row["text"], stops)
            if len(set(tokens)) < 2:
                continue
            best = int(sim.argmax())
            runner_up = float(np.partition(sim, -2)[-2]) if len(sim) > 1 else 0
            if sim[best] < 0.45 or sim[best] - runner_up < 0.04:
                continue
            label = learned[best][0]
            db.execute("UPDATE passages SET topic_id=? WHERE id=?", (label, row["id"]))
            db.execute("UPDATE messages SET topic_id=? WHERE id=? AND topic_id IS NULL", (label, row["sid"]))
        processed += len(rows)
        cursor = rows[-1]["id"]
        progress(0.8, f"Assigning meaningful themes to {processed:,} message chunks")
    for label, _, _ in learned:
        ids = [
            r[0]
            for r in db.execute(
                "SELECT id FROM messages WHERE topic_id=? ORDER BY reaction_count DESC,ts LIMIT 30", (label,)
            )
        ]
        count = db.execute("SELECT count(*) FROM messages WHERE topic_id=?", (label,)).fetchone()[0]
        sessions = db.execute(
            "SELECT count(DISTINCT session_id) FROM messages WHERE topic_id=?", (label,)
        ).fetchone()[0]
        if count < 5 or sessions < 2:
            db.execute("UPDATE messages SET topic_id=NULL WHERE topic_id=?", (label,))
            db.execute("UPDATE passages SET topic_id=NULL WHERE topic_id=?", (label,))
            db.execute("DELETE FROM topics WHERE id=?", (label,))
        else:
            db.execute("UPDATE topics SET count=?,sources=? WHERE id=?", (count, json.dumps(ids), label))
    set_meta(
        db,
        "topic_quality",
        {
            "documents": len(samples),
            "topics": db.execute("SELECT count(*) FROM topics").fetchone()[0],
            "classified_messages": db.execute(
                "SELECT count(*) FROM messages WHERE topic_id IS NOT NULL"
            ).fetchone()[0],
        },
    )


def cosine(a, b):
    den = math.sqrt(sum(x * x for x in a.values()) * sum(x * x for x in b.values()))
    return sum(x * b.get(k, 0) for k, x in a.items()) / den if den else 0


def suggest_eras(db):
    if meta(db, "topic_model_version") != VERSION or meta(db, "semantic_revision", -1) != meta(
        db, "revision", 0
    ):
        return
    stops = set(meta(db, "topic_stopwords", []))
    labels = {r["id"]: r["label"] for r in db.execute("SELECT id,label FROM topics")}
    weeks = defaultdict(
        lambda: {
            "topics": Counter(),
            "vocab": Counter(),
            "ids": [],
            "sessions": set(),
            "start": None,
            "end": 0,
        }
    )
    document_frequency = Counter()
    for row in db.execute(
        "SELECT id,ts,day,text,topic_id,session_id FROM messages WHERE kind='message' AND topic_id IS NOT NULL ORDER BY ts,id"
    ):
        tokens = content(row["text"], stops)
        w = weeks[int(row["ts"] // 604800)]
        w["topics"][row["topic_id"]] += 1
        w["vocab"].update(tokens)
        w["ids"].append(row["id"]) if len(w["ids"]) < 30 else None
        w["sessions"].add(row["session_id"])
        w["start"] = row["ts"] if w["start"] is None else w["start"]
        w["end"] = row["ts"]
        document_frequency.update(set(tokens))
    total = sum(sum(w["topics"].values()) for w in weeks.values())
    idf = {t: math.log(1 + total / (1 + n)) for t, n in document_frequency.items()}
    segments = []
    current = []
    previous = None
    for number, week in sorted(weeks.items()):
        if sum(week["topics"].values()) < 8 or len(week["sessions"]) < 2:
            if current:
                segments.append(current)
                current = []
            previous = None
            continue
        vocab = {t: n * idf[t] for t, n in week["vocab"].items()}
        if previous:
            pn, pw, pv = previous
            shift = 0.6 * (1 - cosine(pw["topics"], week["topics"])) + 0.4 * (1 - cosine(pv, vocab))
            if (
                number - pn > 2
                or shift > 0.38
                or (1 - cosine(pv, vocab) > 0.65 and sum(week["topics"].values()) >= 16)
            ):
                segments.append(current)
                current = []
        current.append(week)
        previous = number, week, vocab
    if current:
        segments.append(current)
    dismissed = set(meta(db, "dismissed_eras", []))
    manuals = db.execute("SELECT id,start,end FROM eras WHERE manual=1").fetchall()
    for segment in segments:
        counts = sum((w["topics"] for w in segment), Counter())
        count = sum(counts.values())
        if count < 16:
            continue
        dominant, dominant_count = counts.most_common(1)[0]
        if dominant_count / count < 0.35:
            continue
        vocab = sum((w["vocab"] for w in segment), Counter())
        terms = sorted(
            (t for t in vocab if vocab[t] >= 3 and document_frequency[t] >= 2),
            key=lambda t: math.log1p(vocab[t]) * idf[t],
            reverse=True,
        )[:3]
        start, end = segment[0]["start"], segment[-1]["end"]
        eid = stable_id(f"semantic-era:{start}")
        if eid in dismissed or any(
            eid == e["id"]
            or max(0, min(end, e["end"]) - max(start, e["start"]))
            / max(1, max(end, e["end"]) - min(start, e["start"]))
            > 0.75
            for e in manuals
        ):
            continue
        name = labels[dominant]
        sources = [sid for w in segment for sid in w["ids"]][:30]
        summary = f"{count:,} topic-linked messages across {len(segment)} active weeks. Main theme: {labels[dominant]}. Distinctive language: {', '.join(terms)}. Boundaries follow changes in topic mix and distinctive vocabulary; inspect the conversations to interpret this arc."
        db.execute(
            "INSERT OR IGNORE INTO eras VALUES(?,?,?,?,?,?,?,?)",
            (eid, name, start, end, summary, json.dumps(sources), 0, VERSION),
        )
