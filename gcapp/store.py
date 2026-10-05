from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import plistlib
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.parsers.expat import ExpatError
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("GCAPP_DATA_DIR", "~/Library/Application Support/GroupChatExplorer")).expanduser()
COLORS = ["#df7253", "#638b70", "#6c84b1", "#b987b7", "#c4a34e", "#5c9eaa", "#a67561", "#8b82b3"]
WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)


def now():
    return datetime.now(timezone.utc).isoformat()


def words(text):
    return WORD.findall(text.casefold())


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    if Path(path).is_file():
        os.chmod(path, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


@contextlib.contextmanager
def registry():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = connect(ROOT / "registry.sqlite")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY,path TEXT NOT NULL,source TEXT NOT NULL,created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,workspace TEXT,kind TEXT,payload TEXT,status TEXT,
      progress REAL DEFAULT 0,message TEXT DEFAULT '',created TEXT,updated TEXT,cancel INTEGER DEFAULT 0);
    """)
    try:
        yield db
        db.commit()
    finally:
        db.close()


def workspace_dir(wid):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", wid):
        raise ValueError("Invalid workspace identifier")
    with registry() as reg:
        if not reg.execute("SELECT 1 FROM workspaces WHERE id=?", (wid,)).fetchone():
            raise KeyError("Workspace not found")
    return ROOT / wid


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY,name TEXT NOT NULL,color TEXT NOT NULL,aliases TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,chat_id TEXT NOT NULL,
 person_id TEXT NOT NULL REFERENCES people(id),ts REAL NOT NULL,text TEXT NOT NULL DEFAULT '',kind TEXT NOT NULL,
 reply_to TEXT,parts TEXT DEFAULT '[]',edits TEXT DEFAULT '[]',raw TEXT DEFAULT '{}',words INTEGER DEFAULT 0,
 reaction_count INTEGER DEFAULT 0,session_id TEXT,topic_id INTEGER,day TEXT,hour INTEGER,weekday INTEGER);
CREATE INDEX IF NOT EXISTS messages_time ON messages(ts,id);
CREATE INDEX IF NOT EXISTS messages_person_time ON messages(person_id,ts);
CREATE INDEX IF NOT EXISTS messages_kind_time ON messages(kind,ts);
CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id,ts);
CREATE INDEX IF NOT EXISTS messages_topic ON messages(topic_id,ts);
CREATE INDEX IF NOT EXISTS messages_reply ON messages(reply_to);
CREATE INDEX IF NOT EXISTS messages_reactions ON messages(kind,reaction_count DESC,ts DESC);
CREATE INDEX IF NOT EXISTS messages_anniversary ON messages(substr(day,6),reaction_count DESC);
CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(text,content='messages',content_rowid='rowid',tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
 INSERT INTO message_fts(rowid,text) VALUES(new.rowid,new.text); END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
 INSERT INTO message_fts(message_fts,rowid,text) VALUES('delete',old.rowid,old.text); END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF text ON messages BEGIN
 INSERT INTO message_fts(message_fts,rowid,text) VALUES('delete',old.rowid,old.text);
 INSERT INTO message_fts(rowid,text) VALUES(new.rowid,new.text); END;
CREATE TABLE IF NOT EXISTS reaction_events(id TEXT PRIMARY KEY,actor TEXT NOT NULL,target TEXT,part INTEGER DEFAULT 0,
 ts REAL NOT NULL,type TEXT NOT NULL,action TEXT NOT NULL,raw TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS reaction_event_time ON reaction_events(ts,actor);
CREATE TABLE IF NOT EXISTS reaction_observations(id TEXT PRIMARY KEY,event_id TEXT,observed_at TEXT,raw TEXT);
CREATE TABLE IF NOT EXISTS reaction_presence(event_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS reactions(actor TEXT,target TEXT,part INTEGER,type TEXT,event_id TEXT,ts REAL,
 PRIMARY KEY(actor,target,part));
CREATE INDEX IF NOT EXISTS reactions_target ON reactions(target);
CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY,message_id TEXT NOT NULL,path TEXT,mime TEXT,
 name TEXT,exists_local INTEGER DEFAULT 0,extracted TEXT DEFAULT '',annotation TEXT DEFAULT '{}',hash TEXT);
CREATE INDEX IF NOT EXISTS attachment_message ON attachments(message_id);
CREATE TABLE IF NOT EXISTS message_threads(message_id TEXT,chat_id TEXT,PRIMARY KEY(message_id,chat_id));
INSERT OR IGNORE INTO message_threads SELECT id,chat_id FROM messages;
CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY,message_id TEXT,url TEXT,domain TEXT,metadata TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS links_message ON links(message_id);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,start REAL,end REAL,count INTEGER,starter TEXT,sources TEXT);
CREATE TABLE IF NOT EXISTS daily(day TEXT,person TEXT,count INTEGER,words INTEGER,hour INTEGER,weekday INTEGER,
 PRIMARY KEY(day,person,hour));
CREATE TABLE IF NOT EXISTS person_stats(person TEXT PRIMARY KEY,messages INTEGER,words INTEGER,active_days INTEGER,
 avg_length REAL,reactions INTEGER,reacted_messages INTEGER,first REAL,last REAL);
CREATE TABLE IF NOT EXISTS eras(id TEXT PRIMARY KEY,name TEXT,start REAL,end REAL,summary TEXT DEFAULT '',
 sources TEXT DEFAULT '[]',manual INTEGER DEFAULT 0,version TEXT DEFAULT 'local-v1');
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,title TEXT,ts REAL,kind TEXT,summary TEXT,sources TEXT,
 manual INTEGER DEFAULT 0,version TEXT DEFAULT 'local-v1');
CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY,label TEXT,terms TEXT,count INTEGER,sources TEXT,version TEXT);
CREATE TABLE IF NOT EXISTS lore(id TEXT PRIMARY KEY,title TEXT,summary TEXT,sources TEXT,start REAL,end REAL,
 people TEXT,count INTEGER,manual INTEGER DEFAULT 0,version TEXT DEFAULT 'local-v1');
CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,kind TEXT,title TEXT,body TEXT,sources TEXT,created TEXT,version TEXT);
CREATE TABLE IF NOT EXISTS passages(id INTEGER PRIMARY KEY,text TEXT,sources TEXT,start REAL,end REAL,topic_id INTEGER,
 version TEXT);
CREATE TABLE IF NOT EXISTS usage(id INTEGER PRIMARY KEY,created TEXT,model TEXT,input_tokens INTEGER,output_tokens INTEGER,kind TEXT);
CREATE TABLE IF NOT EXISTS semantic_match_queries(id TEXT PRIMARY KEY,query TEXT,threshold REAL,revision INTEGER,
 job_id TEXT,ready INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS semantic_matches(query_id TEXT REFERENCES semantic_match_queries(id) ON DELETE CASCADE,
 message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,score REAL,PRIMARY KEY(query_id,message_id));
CREATE INDEX IF NOT EXISTS semantic_matches_message ON semantic_matches(message_id,query_id);
PRAGMA user_version=4;
"""


@contextlib.contextmanager
def workspace(wid):
    db = connect(workspace_dir(wid) / "archive.sqlite")
    if db.execute("PRAGMA user_version").fetchone()[0] < 4:
        db.executescript(SCHEMA)
        refresh_person_stats(db)
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def create_workspace(name, wid=None):
    wid = wid or uuid.uuid4().hex
    with registry() as reg:
        reg.execute("INSERT INTO workspaces VALUES(?,?,?)", (wid, name, now()))
    directory = workspace_dir(wid)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with workspace(wid) as db:
        db.executescript(SCHEMA)
        set_meta(db, "timezone", "America/Los_Angeles")
        set_meta(db, "session_gap", 30)
        set_meta(db, "cloud_enabled", False)
        set_meta(db, "revision", 0)
        set_meta(db, "coverage", {})
    return wid


def set_meta(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, json.dumps(value)))


def meta(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def ensure_person(db, pid, name=None):
    n = db.execute("SELECT count(*) FROM people").fetchone()[0]
    db.execute(
        "INSERT OR IGNORE INTO people(id,name,color) VALUES(?,?,?)",
        (pid, name or pid, COLORS[n % len(COLORS)]),
    )


def attachment_path(attachment, root):
    path = Path(attachment.get("path") or "").expanduser()
    if root:
        original = str(path)
        tail = original.split("/Attachments/", 1)[-1] if "/Attachments/" in original else path.name
        candidate = Path(root).expanduser() / tail
        if candidate.is_file():
            return candidate
    return path


def rich_payload_links(record):
    """Optional preview metadata must never prevent retaining an authored message."""
    xml = record.get("payload_xml")
    binary = record.get("payload_binary_b64")
    if not xml and not binary:
        return set(), {}, None
    try:

        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)
            elif isinstance(value, bytes) and value.startswith(b"bplist"):
                yield from strings(plistlib.loads(value))

        data = base64.b64decode(binary, validate=True) if binary else xml.encode()
        decoded = plistlib.loads(data)
        urls = {
            value
            for value in strings(decoded)
            if value.startswith(("https://", "http://")) and not any(c.isspace() for c in value)
        }
        return (
            urls,
            {
                "source": "stored Messages payload",
                "subject": record.get("subject") or "",
                "variant": record.get("variant") or "",
            },
            None,
        )
    except (
        ExpatError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
        plistlib.InvalidFileException,
    ) as error:
        return (
            set(),
            {},
            {
                "schema_version": 1,
                "record": "diagnostic",
                "id": record["id"],
                "phase": "rich message metadata",
                "error": str(error),
            },
        )


def same_source_record(previous, current, encoded):
    if previous == encoded:
        return True
    # A Messages GUID can belong to several selected threads. Membership is
    # retained separately; a different join row is not a message/reaction edit.
    prior = json.loads(previous)
    return {k: v for k, v in prior.items() if k != "chat_id"} == {
        k: v for k, v in current.items() if k != "chat_id"
    }


def import_records(db, records, attachment_root=None, progress=None, full_snapshot=False):
    """Reconcile by original GUID. Reactions are events, never authored messages."""
    changed = 0
    failures = []
    failure_count = 0
    aliases = meta(db, "identity_map", {})
    previous_presence = {r[0] for r in db.execute("SELECT event_id FROM reaction_presence")}
    observed = set() if full_snapshot else set(previous_presence)
    for index, r in enumerate(records):
        if progress and index % 500 == 0:
            progress(index)
        if r.get("schema_version") != 1:
            raise ValueError("Unsupported importer record version")
        if r["record"] == "diagnostic":
            failure_count += 1
            if len(failures) < 100:
                failures.append(r)
            continue
        pid = aliases.get(r.get("person", "unknown"), r.get("person", "unknown"))
        ensure_person(db, pid, r.get("person_name"))
        if r["record"] == "reaction":
            observed.add(r["id"])
            prev = db.execute("SELECT raw FROM reaction_events WHERE id=?", (r["id"],)).fetchone()
            raw = json.dumps(r, sort_keys=True)
            if not prev or not same_source_record(prev[0], r, raw):
                db.execute(
                    "INSERT OR REPLACE INTO reaction_events VALUES(?,?,?,?,?,?,?,?)",
                    (r["id"], pid, r.get("target"), r.get("part", 0), r["ts"], r["type"], r["action"], raw),
                )
                changed += 1
                db.execute(
                    "INSERT OR IGNORE INTO reaction_observations VALUES(?,?,?,?)",
                    (stable_id(raw), r["id"], now(), raw),
                )
            continue
        db.execute("INSERT OR IGNORE INTO message_threads VALUES(?,?)", (r["id"], str(r["chat_id"])))
        text = r.get("text") or ""
        raw = json.dumps(r, sort_keys=True)
        payload_urls, preview, payload_error = rich_payload_links(r)
        if payload_error:
            failure_count += 1
            if len(failures) < 100:
                failures.append(payload_error)
        old = db.execute("SELECT raw FROM messages WHERE id=?", (r["id"],)).fetchone()
        if old and same_source_record(old[0], r, raw):
            for attachment in r.get("attachments", []):
                path = attachment_path(attachment, attachment_root)
                previous = db.execute(
                    "SELECT path,exists_local FROM attachments WHERE id=?", (attachment["id"],)
                ).fetchone()
                if previous and (
                    previous["path"] != str(path) or previous["exists_local"] != int(path.is_file())
                ):
                    db.execute(
                        "UPDATE attachments SET path=?,exists_local=? WHERE id=?",
                        (str(path), int(path.is_file()), attachment["id"]),
                    )
                    changed += 1
            continue
        changed += 1
        db.execute(
            """INSERT INTO messages(id,source_id,chat_id,person_id,ts,text,kind,reply_to,parts,edits,raw,words)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET person_id=excluded.person_id,
          ts=excluded.ts,text=excluded.text,kind=excluded.kind,reply_to=excluded.reply_to,
          parts=excluded.parts,edits=excluded.edits,raw=excluded.raw,words=excluded.words""",
            (
                r["id"],
                str(r.get("source_id", r["id"])),
                str(r["chat_id"]),
                pid,
                r["ts"],
                text,
                r.get("kind", "message"),
                r.get("reply_to"),
                json.dumps(r.get("parts", [])),
                json.dumps(r.get("edits", [])),
                raw,
                len(words(text)),
            ),
        )
        db.execute("DELETE FROM links WHERE message_id=?", (r["id"],))
        urls = set(re.findall(r"https?://[^\s<>]+", text))
        urls.update(payload_urls)
        for url in sorted(urls):
            from urllib.parse import urlparse

            url = url.rstrip(".,!?)\"'")
            db.execute(
                "INSERT INTO links(message_id,url,domain,metadata) VALUES(?,?,?,?)",
                (r["id"], url, urlparse(url).netloc.casefold(), json.dumps(preview)),
            )
        for a in r.get("attachments", []):
            path = attachment_path(a, attachment_root)
            db.execute(
                """INSERT INTO attachments(id,message_id,path,mime,name,exists_local) VALUES(?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET path=excluded.path,exists_local=excluded.exists_local,
              mime=excluded.mime,name=excluded.name""",
                (
                    a["id"],
                    r["id"],
                    str(path),
                    a.get("mime", ""),
                    a.get("name") or path.name,
                    int(path.is_file()),
                ),
            )
            if a.get("transcript"):
                db.execute(
                    "UPDATE attachments SET extracted=?,annotation=? WHERE id=?",
                    (
                        a["transcript"],
                        json.dumps({"text_source": "Messages transcript", "transcript_complete": True}),
                        a["id"],
                    ),
                )
    if observed != previous_presence:
        changed += len(observed ^ previous_presence)
    db.execute("DELETE FROM reaction_presence")
    db.executemany("INSERT INTO reaction_presence VALUES(?)", [(sid,) for sid in observed])
    if changed:
        rebuild(db)
        set_meta(db, "revision", meta(db, "revision", 0) + 1)
        set_meta(db, "semantic_revision", -1)
        db.execute("DELETE FROM topics")
        db.execute("UPDATE messages SET topic_id=NULL")
        db.execute("DELETE FROM passages")
        db.execute("DELETE FROM artifacts WHERE kind='cloud-cache'")
        # User annotations are deliberately independent of regenerated suggestions.
    span = db.execute("SELECT min(ts),max(ts),count(*) FROM messages WHERE kind='message'").fetchone()
    set_meta(
        db,
        "coverage",
        {
            "start": span[0],
            "end": span[1],
            "messages": span[2],
            "changed": changed,
            "diagnostics": failures,
            "parse_failures": failure_count,
            "missing_attachments": db.execute(
                "SELECT count(*) FROM attachments WHERE exists_local=0"
            ).fetchone()[0],
            "unsupported_records": db.execute(
                "SELECT count(*) FROM messages WHERE json_extract(raw,'$.variant') LIKE 'Unknown%'"
            ).fetchone()[0],
            "imported_at": now(),
        },
    )
    return changed


def rebuild(db):
    tz = ZoneInfo(meta(db, "timezone", "America/Los_Angeles"))
    db.execute("DELETE FROM reactions")
    for r in db.execute(
        "SELECT e.* FROM reaction_events e JOIN reaction_presence p ON p.event_id=e.id ORDER BY ts,id"
    ):
        if r["action"] == "remove":
            db.execute(
                "DELETE FROM reactions WHERE actor=? AND target=? AND part=? AND type=?",
                (r["actor"], r["target"], r["part"], r["type"]),
            )
        else:
            db.execute(
                "INSERT OR REPLACE INTO reactions VALUES(?,?,?,?,?,?)",
                (r["actor"], r["target"], r["part"], r["type"], r["id"], r["ts"]),
            )
    db.execute("UPDATE messages SET reaction_count=(SELECT count(*) FROM reactions WHERE target=messages.id)")
    db.execute("DELETE FROM sessions")
    db.execute("DELETE FROM daily")
    gap = meta(db, "session_gap", 30) * 60
    session = None
    last = None
    daily = {}
    updates = []

    def flush_session():
        if session:
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?)",
                (
                    session["id"],
                    session["start"],
                    session["end"],
                    session["count"],
                    session["starter"],
                    json.dumps(session["sources"]),
                ),
            )

    for r in db.execute("SELECT id,ts,person_id,words FROM messages WHERE kind='message' ORDER BY ts,id"):
        if last is None or r["ts"] - last > gap:
            flush_session()
            session = {
                "id": r["id"],
                "start": r["ts"],
                "end": r["ts"],
                "count": 0,
                "starter": r["person_id"],
                "sources": [],
            }
        session["end"] = last = r["ts"]
        session["count"] += 1
        if len(session["sources"]) < 30:
            session["sources"].append(r["id"])
        dt = datetime.fromtimestamp(r["ts"], tz)
        key = (dt.date().isoformat(), r["person_id"], dt.hour)
        value = daily.setdefault(key, [0, 0, dt.weekday()])
        value[0] += 1
        value[1] += r["words"]
        updates.append((session["id"], key[0], dt.hour, dt.weekday(), r["id"]))
        if len(updates) == 5000:
            db.executemany("UPDATE messages SET session_id=?,day=?,hour=?,weekday=? WHERE id=?", updates)
            updates.clear()
    flush_session()
    db.executemany("UPDATE messages SET session_id=?,day=?,hour=?,weekday=? WHERE id=?", updates)
    db.executemany(
        "INSERT INTO daily VALUES(?,?,?,?,?,?)",
        [(d, p, c, w, h, wd) for (d, p, h), (c, w, wd) in daily.items()],
    )
    refresh_person_stats(db)


def refresh_person_stats(db):
    db.execute("DELETE FROM person_stats")
    db.execute("""INSERT INTO person_stats SELECT person_id,count(*),sum(words),count(DISTINCT day),
      avg(length(text)),sum(reaction_count),sum(reaction_count>0),min(ts),max(ts)
      FROM messages WHERE kind='message' GROUP BY person_id""")


def scope(
    db, start=None, end=None, person=None, era=None, topic=None, session=None, kind="message", alias="m"
):
    sql, params = (["1=1"], []) if kind == "all" else ([f"{alias}.kind=?"], [kind])
    if era:
        e = db.execute("SELECT start,end FROM eras WHERE id=?", (era,)).fetchone()
        if not e:
            raise ValueError("Era not found")
        start = max(start, e[0]) if start is not None else e[0]
        end = min(end, e[1]) if end is not None else e[1]
    for field, value, op in [
        ("ts", start, ">="),
        ("ts", end, "<="),
        ("person_id", person, "="),
        ("topic_id", topic, "="),
        ("session_id", session, "="),
    ]:
        if value is not None and value != "":
            sql.append(f"{alias}.{field}{op}?")
            params.append(value)
    return " AND ".join(sql), params


def message(db, row):
    r = dict(row)
    for key in ("parts", "edits"):
        r[key] = json.loads(r[key])
    raw = json.loads(r.pop("raw", "{}"))
    r["source_metadata"] = {
        key: raw[key]
        for key in (
            "service",
            "subject",
            "variant",
            "announcement",
            "effect",
            "date_read",
            "date_delivered",
            "payload_xml",
            "payload_binary_b64",
            "reply_part",
        )
        if raw.get(key) is not None
    }
    r["source_metadata"]["threads"] = [
        str(row[0])
        for row in db.execute("SELECT chat_id FROM message_threads WHERE message_id=?", (r["id"],))
    ]
    r["reactions"] = [
        dict(x) for x in db.execute("SELECT actor,type,part,ts FROM reactions WHERE target=?", (r["id"],))
    ]
    r["attachments"] = [
        dict(x)
        for x in db.execute(
            "SELECT id,name,mime,exists_local,extracted FROM attachments WHERE message_id=?", (r["id"],)
        )
    ]
    return r


def list_messages(
    db,
    filters,
    limit=60,
    cursor=None,
    direction="desc",
    ids=None,
    word=None,
    word_mode="word",
    reply_person=None,
    started_by=None,
    with_person=None,
    semantic_query=None,
):
    where, params = scope(db, **filters)
    if semantic_query:
        where += " AND m.id IN (SELECT message_id FROM semantic_matches WHERE query_id=?)"
        params.append(semantic_query)
    if reply_person:
        where += " AND m.reply_to IN (SELECT id FROM messages WHERE person_id=?)"
        params.append(reply_person)
    if started_by:
        where += " AND m.session_id IN (SELECT id FROM sessions WHERE starter=?)"
        params.append(started_by)
    if with_person:
        where += " AND m.session_id IN (SELECT session_id FROM messages WHERE person_id=?)"
        params.append(with_person)
    if word:
        word = word.strip().casefold()
        if word_mode == "variants":
            from nltk.stem import PorterStemmer

            stemmer = PorterStemmer()
            stem = stemmer.stem(word)

            def test(text):
                return any(stemmer.stem(token) == stem for token in words(text))
        elif word_mode == "substring":

            def test(text):
                return word in text.casefold()
        else:
            expression = re.compile(
                r"(?<![\w’'])" + r"\s+".join(re.escape(t) for t in word.split()) + r"(?![\w’'])"
            )

            def test(text):
                return bool(expression.search(text.casefold()))

            fts = '"' + " ".join(words(word)).replace('"', '""') + '"'
            if fts != '""':
                where += " AND m.rowid IN (SELECT rowid FROM message_fts WHERE message_fts MATCH ?)"
                params.append(fts)
        db.create_function("word_match", 1, test)
        where += " AND word_match(m.text)=1"
    if ids is not None:
        if not ids:
            return {"items": [], "next_cursor": None}
        where += " AND m.id IN (" + ",".join("?" for _ in ids) + ")"
        params.extend(ids)
    if cursor:
        try:
            ts, mid = json.loads(bytes.fromhex(cursor).decode())
        except (ValueError, TypeError, UnicodeDecodeError):
            raise ValueError("Invalid message cursor")
        op = "<" if direction == "desc" else ">"
        where += f" AND (m.ts,m.id){op}(?,?)"
        params.extend([ts, mid])
    order = "DESC" if direction == "desc" else "ASC"
    rows = db.execute(
        f"SELECT m.* FROM messages m WHERE {where} ORDER BY m.ts {order},m.id {order} LIMIT ?",
        params + [limit + 1],
    ).fetchall()
    page = rows[:limit]
    last = page[-1] if len(rows) > limit else None
    return {
        "items": [message(db, r) for r in page],
        "next_cursor": json.dumps([last["ts"], last["id"]]).encode().hex() if last else None,
    }


def stable_id(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]
