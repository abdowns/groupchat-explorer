from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, OrderedDict, defaultdict, deque
from datetime import date, datetime, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

from .store import message, meta, scope, words

_cache = OrderedDict()
_cache_lock = Lock()


def cached_query(db, name, arguments, compute):
    path = db.execute("PRAGMA database_list").fetchone()[2]
    key = (
        path,
        meta(db, "revision", 0),
        meta(db, "semantic_revision", -1),
        meta(db, "timezone"),
        datetime.now(ZoneInfo(meta(db, "timezone", "UTC"))).date().isoformat(),
        name,
        json.dumps(arguments, sort_keys=True),
    )
    with _cache_lock:
        serialized = _cache.get(key)
    if serialized is None:
        data = compute()
        serialized = json.dumps(data)
        with _cache_lock:
            _cache[key] = serialized
            while len(_cache) > 32:
                _cache.popitem(last=False)
        return data
    return json.loads(serialized)


def overview(db, filters):
    return cached_query(db, "overview", filters, lambda: _overview(db, filters))


def _overview(db, filters):
    if set(filters) - {"person"}:
        return _overview_filtered(db, filters)
    # Whole-history queries use aggregates maintained by import/refresh.
    condition = "WHERE s.person=?" if filters.get("person") else ""
    args = [filters["person"]] if filters.get("person") else []
    people = [
        dict(r)
        for r in db.execute(
            f"SELECT p.*,s.messages,s.words,s.active_days,s.avg_length,s.reactions,s.reacted_messages,s.first,s.last FROM person_stats s JOIN people p ON p.id=s.person {condition} ORDER BY s.messages DESC",
            args,
        )
    ]
    day_condition = "WHERE person=?" if args else ""
    activity = [
        dict(r)
        for r in db.execute(
            f"SELECT day,person person_id,sum(count) count FROM daily {day_condition} GROUP BY day,person ORDER BY day",
            args,
        )
    ]
    heatmap = [
        dict(r)
        for r in db.execute(
            f"SELECT weekday,hour,sum(count) count FROM daily {day_condition} GROUP BY weekday,hour", args
        )
    ]
    total = {
        "messages": sum(p["messages"] for p in people),
        "words": sum(p["words"] for p in people),
        "start": min((p["first"] for p in people), default=None),
        "end": max((p["last"] for p in people), default=None),
        "reactions": sum(p["reactions"] for p in people),
        "active_days": len({r["day"] for r in activity}),
        "members": len(people),
    }
    for p in people:
        p["share"] = p["messages"] / max(1, total["messages"])
        p["reactions_per_message"] = p["reactions"] / p["messages"]
        p["reaction_rate"] = p["reacted_messages"] / p["messages"]
    where, query_args = scope(db, **filters)
    today = datetime.now(ZoneInfo(meta(db, "timezone", "UTC"))).strftime("%m-%d")
    memories = [
        message(db, r)
        for r in db.execute(
            f"SELECT m.* FROM messages m WHERE {where} AND substr(day,6)=? ORDER BY reaction_count DESC LIMIT 6",
            query_args + [today],
        )
    ]
    top = [
        message(db, r)
        for r in db.execute(
            f"SELECT m.* FROM messages m WHERE {where} ORDER BY reaction_count DESC,ts DESC LIMIT 8",
            query_args,
        )
    ]
    return {
        "totals": total,
        "people": people,
        "activity": activity,
        "heatmap": heatmap,
        "memories": memories,
        "top_messages": top,
        "coverage": meta(db, "coverage", {}),
    }


def _overview_filtered(db, filters):
    where, args = scope(db, **filters)
    total = dict(
        db.execute(
            f"""SELECT count(*) messages,coalesce(sum(words),0) words,
      min(ts) start,max(ts) end,coalesce(sum(reaction_count),0) reactions,
      count(DISTINCT day) active_days,count(DISTINCT person_id) members
      FROM messages m WHERE {where}""",
            args,
        ).fetchone()
    )
    people = [
        dict(r)
        for r in db.execute(
            f"""SELECT p.*,count(*) messages,sum(m.words) words,
      count(DISTINCT day) active_days,avg(length(m.text)) avg_length,
      sum(m.reaction_count) reactions,sum(m.reaction_count>0) reacted_messages,
      min(m.ts) first,max(m.ts) last FROM messages m JOIN people p ON p.id=m.person_id
      WHERE {where} GROUP BY p.id ORDER BY messages DESC""",
            args,
        )
    ]
    for p in people:
        p["share"] = p["messages"] / max(1, total["messages"])
        p["reactions_per_message"] = p["reactions"] / p["messages"]
        p["reaction_rate"] = p["reacted_messages"] / p["messages"]
    activity = [
        dict(r)
        for r in db.execute(
            f"SELECT day,person_id,count(*) count FROM messages m WHERE {where} GROUP BY day,person_id ORDER BY day",
            args,
        )
    ]
    heatmap = [
        dict(r)
        for r in db.execute(
            f"SELECT weekday,hour,count(*) count FROM messages m WHERE {where} GROUP BY weekday,hour", args
        )
    ]
    today = datetime.now(ZoneInfo(meta(db, "timezone", "UTC"))).strftime("%m-%d")
    memories = [
        message(db, r)
        for r in db.execute(
            f"SELECT m.* FROM messages m WHERE {where} AND substr(day,6)=? ORDER BY reaction_count DESC LIMIT 6",
            args + [today],
        )
    ]
    top = [
        message(db, r)
        for r in db.execute(
            f"SELECT m.* FROM messages m WHERE {where} ORDER BY reaction_count DESC,ts DESC LIMIT 8", args
        )
    ]
    return {
        "totals": total,
        "people": people,
        "activity": activity,
        "heatmap": heatmap,
        "memories": memories,
        "top_messages": top,
        "coverage": meta(db, "coverage", {}),
    }


def reactions(db, filters, minimum=20):
    data = overview(db, filters)
    where, args = scope(db, **filters)
    matrix = [
        dict(r)
        for r in db.execute(
            f"""SELECT r.actor,m.person_id recipient,r.type,count(*) count
      FROM reactions r JOIN messages m ON m.id=r.target WHERE {where}
      GROUP BY r.actor,m.person_id,r.type""",
            args,
        )
    ]
    # Given uses the observable reaction event timestamp, received uses the target timestamp.
    received_filters = dict(filters)
    received_filters.pop("person", None)
    _, _args = scope(db, **received_filters)
    start, end = filters.get("start"), filters.get("end")
    if filters.get("era"):
        e = db.execute("SELECT start,end FROM eras WHERE id=?", (filters["era"],)).fetchone()
        start = max(start, e[0]) if start is not None else e[0]
        end = min(end, e[1]) if end is not None else e[1]
    conditions, params = ["e.action='add'", "m.kind='message'"], []
    for clause, value in [
        ("e.ts>=?", start),
        ("e.ts<=?", end),
        ("e.actor=?", filters.get("person")),
        ("m.topic_id=?", filters.get("topic")),
        ("m.session_id=?", filters.get("session")),
    ]:
        if value is not None:
            conditions.append(clause)
            params.append(value)
    given = [
        dict(r)
        for r in db.execute(
            f"""SELECT e.actor,e.type,count(*) count FROM reaction_events e
       JOIN messages m ON m.id=e.target WHERE {" AND ".join(conditions)} GROUP BY e.actor,e.type""",
            params,
        )
    ]
    unresolved = db.execute(
        "SELECT count(*) FROM reaction_events e LEFT JOIN messages m ON m.id=e.target WHERE m.id IS NULL"
    ).fetchone()[0]
    return {
        "people": data["people"],
        "matrix": matrix,
        "given": given,
        "top_messages": data["top_messages"],
        "minimum": minimum,
        "unresolved": unresolved,
        "rankings": sorted(
            [p for p in data["people"] if p["messages"] >= minimum],
            key=lambda p: p["reactions_per_message"],
            reverse=True,
        ),
        "activity": data["activity"],
        "trend": [
            dict(r)
            for r in db.execute(
                f"SELECT substr(m.day,1,7) month,r.type,count(*) count FROM reactions r JOIN messages m ON m.id=r.target WHERE {where} GROUP BY month,r.type ORDER BY month",
                args,
            )
        ],
        "date_basis": {
            "received": "target message",
            "given": "add event; replacements are separate observed actions",
        },
    }


def word_explorer(db, filters, query, mode="word"):
    return cached_query(db, "words", [filters, query, mode], lambda: _word_explorer(db, filters, query, mode))


def _word_explorer(db, filters, query, mode="word"):
    if not query.strip():
        return {
            "people": [],
            "trend": [],
            "messages": [],
            "occurrences": 0,
            "matching_messages": 0,
            "first": None,
            "last": None,
        }
    where, args = scope(db, **filters)
    query = query.strip().casefold()
    if not any(v is not None for k, v in filters.items() if k not in ("person", "kind")):
        totals = {r["person"]: r["words"] for r in db.execute("SELECT person,words FROM person_stats")}
    else:
        totals = {
            r[0]: r[1]
            for r in db.execute(
                f"SELECT person_id,sum(words) FROM messages m WHERE {where} GROUP BY person_id", args
            )
        }
    expression = " ".join(words(query))
    fts = '"' + expression.replace('"', '""') + '"'
    if mode in ("word", "phrase") and expression:
        rows = db.execute(
            f"SELECT m.id,m.ts,m.text,m.person_id,m.day FROM message_fts f JOIN messages m ON m.rowid=f.rowid WHERE message_fts MATCH ? AND {where} ORDER BY m.ts",
            [fts] + args,
        )
    elif mode == "substring":
        rows = db.execute(
            f"SELECT m.id,m.ts,m.text,m.person_id,m.day FROM messages m WHERE {where} AND instr(lower(m.text),?)>0 ORDER BY ts",
            args + [query],
        )
    else:
        rows = db.execute(
            f"SELECT m.id,m.ts,m.text,m.person_id,m.day FROM messages m WHERE {where} ORDER BY ts", args
        )
    if mode in ("word", "phrase"):
        pattern = re.compile(
            r"(?<![\w’'])" + r"\s+".join(re.escape(x) for x in query.split()) + r"(?![\w’'])", re.UNICODE
        )
    if mode == "variants":
        from nltk.stem import PorterStemmer

        stemmer = PorterStemmer()
        stem = stemmer.stem(query)
    stats = defaultdict(lambda: {"occurrences": 0, "messages": 0, "first": None, "last": None})
    trend = Counter()
    ids = deque(maxlen=200)
    first = last = None
    total_matches = 0
    variants = Counter()
    for r in rows:
        text = r["text"].casefold()
        if mode == "substring":
            count = text.count(query)
        elif mode == "variants":
            found = [w for w in words(text) if stemmer.stem(w) == stem]
            variants.update(found)
            count = len(found)
        else:
            count = len(pattern.findall(text))
        if not count:
            continue
        s = stats[r["person_id"]]
        s["occurrences"] += count
        s["messages"] += 1
        s["first"] = s["first"] if s["first"] is not None else r["ts"]
        s["last"] = r["ts"]
        trend[r["day"][:7]] += count
        total_matches += 1
        if first is None:
            first = r["ts"]
        last = r["ts"]
        ids.append(r["id"])
    persons = {r["id"]: dict(r) for r in db.execute("SELECT * FROM people")}
    people = [
        {
            **persons[p],
            **s,
            "total_words": totals[p],
            "per_1000": s["occurrences"] * 1000 / totals[p] if totals[p] else None,
        }
        for p, s in stats.items()
    ]
    people.sort(key=lambda p: p["occurrences"], reverse=True)
    return {
        "people": people,
        "trend": [{"date": d, "count": n} for d, n in sorted(trend.items())],
        "message_ids": list(ids)[::-1],
        "occurrences": sum(s["occurrences"] for s in stats.values()),
        "matching_messages": total_matches,
        "first": first,
        "last": last,
        "variants": dict(variants),
    }


def person_profile(db, filters, pid):
    filters = {**filters, "person": pid}
    data = overview(db, filters)
    where, args = scope(db, **filters)
    vocab, phrases, emoji = Counter(), Counter(), Counter()
    lengths = []
    for r in db.execute(f"SELECT text,words FROM messages m WHERE {where}", args):
        tokens = words(r[0])
        vocab.update(tokens)
        phrases.update(" ".join(tokens[i : i + 2]) for i in range(len(tokens) - 1))
        emoji.update(re.findall(r"[\U0001f300-\U0001faff\u2600-\u27bf]", r[0]))
        lengths.append(r[1])
    days = sorted({r["day"] for r in data["activity"]})
    longest = current = 0
    prev = None
    for d in days:
        dt = date.fromisoformat(d)
        current = current + 1 if prev and dt - prev == timedelta(days=1) else 1
        longest = max(longest, current)
        prev = dt
    stop = {
        "the",
        "a",
        "i",
        "it",
        "to",
        "and",
        "of",
        "is",
        "in",
        "you",
        "we",
        "that",
        "this",
        "for",
        "on",
        "my",
        "are",
        "so",
        "be",
        "was",
        "at",
        "me",
    }
    return {
        **data,
        "favorite_words": [{"word": w, "count": c} for w, c in vocab.most_common() if w not in stop][:20],
        "phrases": [{"word": w, "count": c} for w, c in phrases.most_common(12)],
        "emoji": [{"word": w, "count": c} for w, c in emoji.most_common(12)],
        "longest_streak": longest,
        "word_lengths": Counter(min(100, n // 5 * 5) for n in lengths),
        "topics": [
            dict(r)
            for r in db.execute(
                f"SELECT t.id,t.label,count(*) count FROM messages m JOIN topics t ON t.id=m.topic_id WHERE {where} GROUP BY t.id ORDER BY count DESC",
                args,
            )
        ],
    }


def conversations(db, filters):
    where, args = scope(db, **filters)
    sessions = [
        dict(r)
        for r in db.execute(
            f"""SELECT s.*,count(*) filtered_count FROM messages m
      JOIN sessions s ON s.id=m.session_id WHERE {where} GROUP BY s.id ORDER BY filtered_count DESC LIMIT 80""",
            args,
        )
    ]
    for s in sessions:
        s["sources"] = json.loads(s["sources"])
    starters = [
        dict(r)
        for r in db.execute(
            f"SELECT s.starter,count(DISTINCT s.id) count FROM messages m JOIN sessions s ON s.id=m.session_id WHERE {where} GROUP BY s.starter",
            args,
        )
    ]
    replies = [
        dict(r)
        for r in db.execute(
            f"""SELECT m.person_id actor,p.person_id recipient,count(*) count,
      avg(m.ts-p.ts) seconds FROM messages m JOIN messages p ON m.reply_to=p.id
      WHERE {where} AND p.kind='message' GROUP BY m.person_id,p.person_id""",
            args,
        )
    ]
    pairs = [
        dict(r)
        for r in db.execute(
            f"""WITH members AS (SELECT DISTINCT session_id,person_id FROM messages m WHERE {where})
      SELECT a.person_id actor,b.person_id recipient,count(*) count FROM members a JOIN members b
      ON a.session_id=b.session_id AND a.person_id<b.person_id GROUP BY a.person_id,b.person_id""",
            args,
        )
    ]
    return {
        "sessions": sessions,
        "starters": starters,
        "replies": replies,
        "co_participation": pairs,
        "inferred_responses": [
            dict(r)
            for r in db.execute(
                f"WITH adjacent AS (SELECT id,person_id,ts,session_id,lag(person_id) OVER (ORDER BY ts,id) prior,lag(ts) OVER (ORDER BY ts,id) prior_ts,lag(session_id) OVER (ORDER BY ts,id) prior_session FROM messages WHERE kind='message') SELECT a.person_id actor,a.prior recipient,count(*) count,avg(a.ts-a.prior_ts) seconds FROM adjacent a JOIN messages m ON m.id=a.id WHERE {where} AND a.person_id<>a.prior AND a.session_id=a.prior_session GROUP BY actor,recipient",
                args,
            )
        ],
        "session_gap": meta(db, "session_gap", 30),
    }


def recap(db, filters):
    data = overview(db, filters)
    conv = conversations(db, filters)
    where, args = scope(db, **filters)
    eras = [dict(r) for r in db.execute("SELECT * FROM eras ORDER BY start")]
    awards = []
    if data["people"]:
        awards.append(
            {
                "title": "The conversation engine",
                "person": data["people"][0]["id"],
                "metric": f"{data['people'][0]['messages']:,} messages",
            }
        )
        eligible = [p for p in data["people"] if p["messages"] >= 20]
        if eligible:
            winner = max(eligible, key=lambda p: p["reactions_per_message"])
            awards.append(
                {
                    "title": "The crowd favorite",
                    "person": winner["id"],
                    "metric": f"{winner['reactions_per_message']:.2f} reactions per message",
                }
            )
        if conv["starters"]:
            winner = max(conv["starters"], key=lambda p: p["count"])
            awards.append(
                {
                    "title": "The spark",
                    "person": winner["starter"],
                    "metric": f"Started {winner['count']:,} conversations",
                }
            )
    comparisons = []
    for e in eras:
        ew = f"{where} AND m.ts>=? AND m.ts<=?"
        row = dict(
            db.execute(
                f"SELECT count(*) messages,sum(words) words,sum(reaction_count) reactions,count(DISTINCT person_id) members FROM messages m WHERE {ew}",
                args + [e["start"], e["end"]],
            ).fetchone()
        )
        comparisons.append({"id": e["id"], "name": e["name"], **row})
    data.update(
        {
            "awards": awards,
            "era_comparison": comparisons,
            "busiest_conversations": conv["sessions"][:3],
            "topics": [
                dict(r)
                for r in db.execute(
                    f"SELECT t.label,count(*) count FROM messages m JOIN topics t ON t.id=m.topic_id WHERE {where} GROUP BY t.id ORDER BY count DESC LIMIT 5",
                    args,
                )
            ],
        }
    )
    return data


def export_csv(db, filters):
    people = overview(db, filters)["people"]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["Person", "Messages", "Words", "Active days", "Reactions received", "Reactions per message", "Share"]
    )
    for p in people:
        # Prevent spreadsheet formula execution in user-controlled names.
        name = p["name"]
        if name.startswith(("=", "+", "-", "@")):
            name = "'" + name
        writer.writerow(
            [
                name,
                p["messages"],
                p["words"],
                p["active_days"],
                p["reactions"],
                p["reactions_per_message"],
                p["share"],
            ]
        )
    return out.getvalue()
