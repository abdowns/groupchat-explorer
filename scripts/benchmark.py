"""A million-message synthetic archive. No real Messages data is read."""

import argparse
import json
import os
import resource
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--messages", type=int, default=1_000_000)
parser.add_argument("--report", type=Path)
args = parser.parse_args()
os.environ["GCAPP_DATA_DIR"] = tempfile.mkdtemp(prefix="gcapp-benchmark-")

from gcapp import analysis, analytics, store  # noqa: E402

wid = store.create_workspace("Million-message synthetic benchmark")
sentences = [
    "coffee after the morning run anyone",
    "we almost missed our flight at the airport",
    "the council has spoken again lmao",
    "birthday dinner this weekend please",
    "marathon training with friends is fun",
    "our reunion photos from the mountain cabin",
]
start = time.perf_counter()
with store.workspace(wid) as db:
    for i in range(6):
        store.ensure_person(db, f"person-{i}", f"Person {i}")
    sql = "INSERT INTO messages(id,source_id,chat_id,person_id,ts,text,kind,words,session_id,day,hour,weekday) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
    for base in range(0, args.messages, 5000):
        batch = []
        for i in range(base, min(args.messages, base + 5000)):
            ts = 1554742800 + (i // 40) * 5400 + (i % 40) * 10
            dt = datetime.fromtimestamp(ts, timezone.utc)
            batch.append(
                (
                    f"bench-{i}",
                    str(i),
                    "synthetic",
                    f"person-{i % 6}",
                    ts,
                    sentences[i % 6],
                    "message",
                    len(store.words(sentences[i % 6])),
                    f"session-{i // 40}",
                    dt.date().isoformat(),
                    dt.hour,
                    dt.weekday(),
                )
            )
        db.executemany(sql, batch)
        if base % 100000 == 0:
            print(f"Inserted {base:,} messages", flush=True)
    store.set_meta(db, "coverage", {"messages": args.messages})
    store.set_meta(db, "revision", 1)
    store.refresh_person_stats(db)
    db.execute(
        "INSERT INTO daily SELECT day,person_id,count(*),sum(words),hour,weekday FROM messages GROUP BY day,person_id,hour"
    )
    db.execute("ANALYZE")
elapsed = time.perf_counter() - start
report = {
    "messages": args.messages,
    "fixture_build_seconds": round(elapsed, 3),
    "runtime": "Apple Silicon / Python 3.12 / SQLite FTS5",
    "queries": {},
}
with store.workspace(wid) as db:
    queries = {
        "overview": lambda: analytics.overview(db, {}),
        "member_overview": lambda: analytics.overview(db, {"person": "person-2"}),
        "lexical_search": lambda: analysis.lexical_search(db, {}, "airport flight"),
        "word_counts": lambda: analytics.word_explorer(db, {}, "lmao"),
    }
    for name, query in queries.items():
        runs = []
        for _ in range(3):
            t = time.perf_counter()
            query()
            runs.append(round(time.perf_counter() - t, 4))
        report["queries"][name] = {"cold_seconds": runs[0], "warm_seconds": min(runs[1:])}
report["peak_memory_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024), 1)
report["database_mb"] = round((store.workspace_dir(wid) / "archive.sqlite").stat().st_size / (1024 * 1024), 1)
report["notes"] = (
    "Direct synthetic fixture insertion; local text inference throughput and cloud latency are not benchmarked. Semantic search is validated separately on the 6,947-message demo."
)
print(json.dumps(report, indent=2), flush=True)
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
shutil.rmtree(store.ROOT)
