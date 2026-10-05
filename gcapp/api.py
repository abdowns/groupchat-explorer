from __future__ import annotations

import asyncio
import importlib.util
import json
import random
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analysis, analytics, cloud, contacts, ingestion, jobs, media
from .store import (
    ROOT,
    create_workspace,
    list_messages,
    message,
    meta,
    now,
    rebuild,
    registry,
    scope,
    set_meta,
    workspace,
    workspace_dir,
)

PROJECT = Path(__file__).resolve().parent.parent
SESSION_TOKEN = secrets.token_urlsafe(32)
ALLOWED_ORIGINS = {
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (8765, 5173, 4173)
}


@asynccontextmanager
async def lifespan(app):
    stop, thread = jobs.start_worker()
    yield
    stop.set()
    thread.join(timeout=2)


app = FastAPI(title="Group Chat Explorer", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.url.hostname
    origin = request.headers.get("origin")
    if host not in ("127.0.0.1", "localhost", "testserver"):
        return JSONResponse({"detail": "Only loopback hosts are allowed"}, status_code=403)
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Browser origin is not allowed"}, status_code=403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail": "Cross-site access is not allowed"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS") and not secrets.compare_digest(
        request.headers.get("x-session-token", ""), SESSION_TOKEN
    ):
        return JSONResponse({"detail": "Invalid local session token"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(KeyError)
async def key_error(request, exc):
    return JSONResponse({"detail": str(exc).strip("'")}, status_code=404)


class Filters(BaseModel):
    start: float | None = None
    end: float | None = None
    person: str | None = None
    era: str | None = None
    topic: int | None = None
    session: str | None = None


def filter_params(
    start: float | None = None,
    end: float | None = None,
    person: str | None = None,
    era: str | None = None,
    topic: int | None = None,
    session: str | None = None,
):
    if start is not None and end is not None and end < start:
        raise ValueError("End must be after start")
    return Filters(start=start, end=end, person=person, era=era, topic=topic, session=session).model_dump(
        exclude_none=True
    )


class PersonView(BaseModel):
    id: str
    name: str
    color: str
    aliases: str = "[]"


class MessageView(BaseModel):
    id: str
    source_id: str
    chat_id: str
    person_id: str
    ts: float
    text: str
    kind: str
    reply_to: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    parts: list[dict[str, Any]]
    edits: list[dict[str, Any]]
    words: int
    reaction_count: int
    session_id: str | None = None
    topic_id: int | None = None
    day: str | None = None
    reactions: list[dict[str, Any]]
    attachments: list[dict[str, Any]]


class MessagePage(BaseModel):
    items: list[MessageView]
    next_cursor: str | None = None


class WorkspaceView(BaseModel):
    id: str
    name: str
    created: str
    people: list[PersonView]
    coverage: dict[str, Any]
    demo: bool


class ImportDiscovery(BaseModel):
    path: str = "~/Library/Messages/chat.db"


class ImportSelection(BaseModel):
    import_id: str
    name: str = Field(min_length=1, max_length=120)
    chat_ids: list[int] = Field(min_length=1)
    attachment_root: str | None = None


class AnalysisJob(BaseModel):
    kind: Literal["semantic", "local", "media", "refresh"]
    ocr: bool = True
    images: bool = True
    audio: bool = True


class EraInput(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    start: float
    end: float
    summary: str = ""
    sources: list[str] = []


class EventInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    ts: float
    summary: str = ""
    sources: list[str] = []


class SettingsInput(BaseModel):
    timezone: str | None = None
    session_gap: int | None = Field(default=None, ge=1, le=1440)
    cloud_enabled: bool | None = None
    cloud_model: str | None = Field(default=None, max_length=120)
    api_key: str | None = Field(default=None, max_length=300)


@app.get("/api/v1/workspaces/{wid}/date-bounds")
def date_bounds(wid: str, day: str):
    with workspace(wid) as db:
        timezone = ZoneInfo(meta(db, "timezone", "America/Los_Angeles"))
    parsed = datetime.fromisoformat(day)
    if parsed.time() != datetime.min.time():
        raise ValueError("Supply a calendar date YYYY-MM-DD")
    from datetime import timedelta

    begin = parsed.replace(tzinfo=timezone)
    return {"start": begin.timestamp(), "end": (begin + timedelta(days=1)).timestamp() - 0.001}


class CloudInput(BaseModel):
    kind: Literal["eras", "lore", "recap", "qa"]
    filters: Filters = Filters()
    question: str = Field(default="", max_length=2000)
    approved: bool = False


class PersonInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    merge_into: str | None = None


class AwardInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    person: str
    metric: str = Field(max_length=200)


@app.get("/api/v1/config")
def config():
    return {"session_token": SESSION_TOKEN, "version": "0.1.0", "data_directory": str(ROOT)}


@app.get("/api/v1/workspaces", response_model=list[WorkspaceView])
def workspaces():
    with registry() as reg:
        rows = [dict(r) for r in reg.execute("SELECT * FROM workspaces ORDER BY created DESC")]
    for row in rows:
        with workspace(row["id"]) as db:
            row.update(
                people=[dict(r) for r in db.execute("SELECT * FROM people")],
                coverage=meta(db, "coverage", {}),
                demo=meta(db, "demo", False),
            )
    return rows


@app.post("/api/v1/demo")
def demo():
    from .demo import create_demo

    return {"id": create_demo()}


@app.post("/api/v1/imports/discover")
def discover(body: ImportDiscovery):
    iid = ingestion.snapshot(body.path)
    return {"import_id": iid, "chats": ingestion.discover(iid)}


@app.post("/api/v1/imports/select")
def select_import(body: ImportSelection):
    available = {r["id"] for r in ingestion.discover(body.import_id)}
    if not set(body.chat_ids).issubset(available):
        raise ValueError("Select valid group chats from this snapshot")
    wid = create_workspace(body.name)
    jid = jobs.enqueue(wid, "import", body.model_dump())
    return {"workspace_id": wid, "job_id": jid}


@app.get("/api/v1/workspaces/{wid}/messages", response_model=MessagePage)
def messages(
    wid: str,
    filters=Depends(filter_params),
    limit: int = Query(60, ge=1, le=200),
    cursor: str | None = None,
    direction: Literal["asc", "desc"] = "desc",
    ids: str | None = None,
    kind: Literal["message", "system", "all"] = "message",
    word: str | None = None,
    word_mode: Literal["word", "phrase", "substring", "variants"] = "word",
    reply_person: str | None = None,
    started_by: str | None = None,
    with_person: str | None = None,
):
    with workspace(wid) as db:
        return list_messages(
            db,
            {**filters, "kind": kind},
            limit,
            cursor,
            direction,
            ids.split(",")[:200] if ids is not None else None,
            word=word,
            word_mode=word_mode,
            reply_person=reply_person,
            started_by=started_by,
            with_person=with_person,
        )


@app.get("/api/v1/workspaces/{wid}/reaction-targets", response_model=MessagePage)
def reaction_targets(
    wid: str,
    actor: str | None = None,
    recipient: str | None = None,
    reaction_type: str | None = None,
    basis: Literal["given", "received"] = "received",
    filters=Depends(filter_params),
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=200),
):
    with workspace(wid) as db:
        if basis == "received":
            where, args = scope(db, **filters)
            table = "reactions"
        else:
            table = "reaction_events"
            selected = dict(filters)
            start, end = selected.pop("start", None), selected.pop("end", None)
            if selected.get("era"):
                era = db.execute("SELECT start,end FROM eras WHERE id=?", (selected.pop("era"),)).fetchone()
                if not era:
                    raise ValueError("Era not found")
                start = max(start, era[0]) if start is not None else era[0]
                end = min(end, era[1]) if end is not None else era[1]
            giver = selected.pop("person", None)
            actor = actor or giver
            where, args = scope(db, **selected)
            where += " AND r.action='add'"
            if start is not None:
                where += " AND r.ts>=?"
                args.append(start)
            if end is not None:
                where += " AND r.ts<=?"
                args.append(end)
        for field, value in [("r.actor", actor), ("m.person_id", recipient), ("r.type", reaction_type)]:
            if value:
                where += f" AND {field}=?"
                args.append(value)
        if cursor:
            try:
                ts, mid = json.loads(bytes.fromhex(cursor))
            except (ValueError, TypeError):
                raise ValueError("Invalid message cursor")
            where += " AND (m.ts,m.id)<(?,?)"
            args.extend([ts, mid])
        rows = db.execute(
            f"SELECT DISTINCT m.* FROM {table} r JOIN messages m ON m.id=r.target WHERE {where} ORDER BY m.ts DESC,m.id DESC LIMIT ?",
            args + [limit + 1],
        ).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        return {
            "items": [message(db, r) for r in rows],
            "next_cursor": json.dumps([rows[-1]["ts"], rows[-1]["id"]]).encode().hex() if more else None,
        }


@app.get("/api/v1/workspaces/{wid}/messages/{mid}/context", response_model=MessagePage)
def context(wid: str, mid: str):
    with workspace(wid) as db:
        target = db.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
        if not target:
            raise KeyError("Message not found")
        before = db.execute(
            "SELECT * FROM messages WHERE (ts,id)<(?,?) ORDER BY ts DESC,id DESC LIMIT 15",
            (target["ts"], mid),
        ).fetchall()
        after = db.execute(
            "SELECT * FROM messages WHERE (ts,id)>(?,?) ORDER BY ts,id LIMIT 20", (target["ts"], mid)
        ).fetchall()
        return {
            "items": [message(db, r) for r in list(reversed(before)) + [target] + after],
            "next_cursor": None,
        }


@app.get("/api/v1/workspaces/{wid}/messages/{mid}/thread", response_model=MessagePage)
def reply_thread(wid: str, mid: str):
    with workspace(wid) as db:
        if not db.execute("SELECT 1 FROM messages WHERE id=?", (mid,)).fetchone():
            raise KeyError("Message not found")
        rows = db.execute(
            """WITH RECURSIVE ancestors(id,reply_to) AS (SELECT id,reply_to FROM messages WHERE id=? UNION SELECT m.id,m.reply_to FROM messages m JOIN ancestors a ON m.id=a.reply_to), roots(id) AS (SELECT id FROM ancestors WHERE reply_to IS NULL OR reply_to NOT IN (SELECT id FROM messages)), tree(id) AS (SELECT id FROM roots UNION SELECT m.id FROM messages m JOIN tree t ON m.reply_to=t.id) SELECT m.* FROM messages m JOIN tree ON tree.id=m.id ORDER BY m.ts,m.id LIMIT 1000""",
            (mid,),
        ).fetchall()
        return {"items": [message(db, r) for r in rows], "next_cursor": None}


@app.get("/api/v1/workspaces/{wid}/analytics/{view}")
def analytics_view(
    wid: str,
    view: Literal["overview", "reactions", "conversations", "recap"],
    filters=Depends(filter_params),
    minimum: int = Query(20, ge=1),
) -> dict[str, Any]:
    with workspace(wid) as db:
        if view == "reactions":
            return analytics.reactions(db, filters, minimum)
        return getattr(analytics, view)(db, filters)


@app.get("/api/v1/workspaces/{wid}/words")
def word_stats(
    wid: str,
    q: str = Query("", max_length=200),
    mode: Literal["word", "phrase", "substring", "variants"] = "word",
    filters=Depends(filter_params),
) -> dict[str, Any]:
    with workspace(wid) as db:
        result = analytics.word_explorer(db, filters, q, mode)
        result["messages"] = list_messages(db, filters, 60, ids=result.get("message_ids", []))["items"]
        return result


@app.get("/api/v1/workspaces/{wid}/people/{pid}")
def person(wid: str, pid: str, filters=Depends(filter_params)) -> dict[str, Any]:
    with workspace(wid) as db:
        if not db.execute("SELECT 1 FROM people WHERE id=?", (pid,)).fetchone():
            raise KeyError("Person not found")
        return analytics.person_profile(db, filters, pid)


@app.post("/api/v1/workspaces/{wid}/contacts/sync")
def sync_contacts(wid: str):
    with workspace(wid) as db:
        return contacts.sync_names(db, request_access=True)


@app.patch("/api/v1/workspaces/{wid}/people/{pid}")
def edit_person(wid: str, pid: str, body: PersonInput):
    with workspace(wid) as db:
        if not db.execute("SELECT 1 FROM people WHERE id=?", (pid,)).fetchone():
            raise KeyError("Person not found")
        if body.name:
            db.execute("UPDATE people SET name=? WHERE id=?", (body.name, pid))
            manual = meta(db, "manual_names", {})
            manual[pid] = body.name
            set_meta(db, "manual_names", manual)
        if body.merge_into:
            if (
                pid == body.merge_into
                or not db.execute("SELECT 1 FROM people WHERE id=?", (body.merge_into,)).fetchone()
            ):
                raise ValueError("Select a different existing member")
            mapping = meta(db, "identity_map", {})
            for key, value in list(mapping.items()):
                if value == pid:
                    mapping[key] = body.merge_into
            mapping[pid] = body.merge_into
            set_meta(db, "identity_map", mapping)
            db.execute("UPDATE messages SET person_id=? WHERE person_id=?", (body.merge_into, pid))
            db.execute("UPDATE reaction_events SET actor=? WHERE actor=?", (body.merge_into, pid))
            db.execute("DELETE FROM people WHERE id=?", (pid,))
            rebuild(db)
        set_meta(db, "revision", meta(db, "revision", 0) + 1)
        set_meta(db, "semantic_revision", -1)
        analysis.derive_local(db)
    return {"ok": True}


def decode_sources(row):
    r = dict(row)
    for field in ("sources", "terms", "people"):
        if field in r and isinstance(r[field], str):
            r[field] = json.loads(r[field])
    return r


@app.get("/api/v1/workspaces/{wid}/timeline")
def timeline(wid: str, filters=Depends(filter_params)) -> dict[str, Any]:
    with workspace(wid) as db:
        where, args = scope(db, **filters)
        span = db.execute(f"SELECT min(ts),max(ts) FROM messages m WHERE {where}", args).fetchone()
        if span[0] is None:
            return {"eras": [], "events": [], "activity": []}
        eras = [
            decode_sources(r)
            for r in db.execute(
                "SELECT * FROM eras WHERE end>=? AND start<=? ORDER BY start", (span[0], span[1])
            )
        ]
        event_start, event_end = filters.get("start"), filters.get("end")
        if filters.get("era"):
            era = db.execute("SELECT start,end FROM eras WHERE id=?", (filters["era"],)).fetchone()
            event_start = max(event_start, era[0]) if event_start is not None else era[0]
            event_end = min(event_end, era[1]) if event_end is not None else era[1]
        events = [
            decode_sources(r)
            for r in db.execute(
                "SELECT * FROM events WHERE (? IS NULL OR ts>=?) AND (? IS NULL OR ts<=?) ORDER BY ts",
                (event_start, event_start, event_end, event_end),
            )
        ]
        if filters.get("person") or filters.get("topic") or filters.get("session"):

            def matches(item):
                source_where, source_args = scope(db, **filters, kind="all")
                return any(
                    db.execute(
                        f"SELECT 1 FROM messages m WHERE {source_where} AND id=?", source_args + [sid]
                    ).fetchone()
                    for sid in item["sources"]
                )

            eras = [e for e in eras if matches(e)]
            events = [e for e in events if matches(e)]
        activity = [
            dict(r)
            for r in db.execute(
                f"SELECT substr(day,1,7) month,count(*) count FROM messages m WHERE {where} GROUP BY month ORDER BY month",
                args,
            )
        ]
        milestones = []
        count = sum(r["count"] for r in activity)
        for n in (1, 100, 1000, 10000, 100000, 1000000):
            if n > count:
                continue
            row = db.execute(
                f"SELECT id,ts FROM messages m WHERE {where} ORDER BY ts,id LIMIT 1 OFFSET ?", args + [n - 1]
            ).fetchone()
            if row:
                milestones.append(
                    {
                        "title": "First observed message" if n == 1 else f"Message #{n:,}",
                        "ts": row["ts"],
                        "sources": [row["id"]],
                    }
                )
        return {"eras": eras, "events": events, "activity": activity, "milestones": milestones}


def validate_sources(db, ids):
    for sid in ids:
        if not db.execute("SELECT 1 FROM messages WHERE id=?", (sid,)).fetchone():
            raise ValueError("A cited message does not exist in this workspace")


@app.post("/api/v1/workspaces/{wid}/eras")
@app.put("/api/v1/workspaces/{wid}/eras/{eid}")
def save_era(wid: str, body: EraInput, eid: str | None = None):
    if body.end < body.start:
        raise ValueError("Era end must be after its start")
    eid = eid or uuid.uuid4().hex
    with workspace(wid) as db:
        validate_sources(db, body.sources)
        db.execute(
            "INSERT OR REPLACE INTO eras VALUES(?,?,?,?,?,?,?,?)",
            (eid, body.name, body.start, body.end, body.summary, json.dumps(body.sources), 1, "manual-v1"),
        )
    return {"id": eid}


@app.delete("/api/v1/workspaces/{wid}/eras/{eid}")
def delete_era(wid: str, eid: str):
    with workspace(wid) as db:
        db.execute("DELETE FROM eras WHERE id=?", (eid,))
    return {"ok": True}


@app.post("/api/v1/workspaces/{wid}/events")
def save_event(wid: str, body: EventInput):
    eid = uuid.uuid4().hex
    with workspace(wid) as db:
        validate_sources(db, body.sources)
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
            (eid, body.title, body.ts, "pinned", body.summary, json.dumps(body.sources), 1, "manual-v1"),
        )
    return {"id": eid}


@app.get("/api/v1/workspaces/{wid}/lore")
def lore(wid: str, filters=Depends(filter_params)) -> list[dict[str, Any]]:
    with workspace(wid) as db:
        where, args = scope(db, **filters)
        items = [decode_sources(r) for r in db.execute("SELECT * FROM lore ORDER BY count DESC")]
        if not any(v is not None for v in filters.values()):
            return items
        selected = []
        for item in items:
            data = analytics.word_explorer(db, filters, item["title"], "phrase")
            if not data["matching_messages"]:
                continue
            item.update(
                count=data["matching_messages"],
                start=data["first"],
                end=data["last"],
                people=[p["id"] for p in data["people"]],
                sources=data["message_ids"],
            )
            selected.append(item)
        return selected


@app.get("/api/v1/workspaces/{wid}/lore/{lid}/journey")
def lore_journey(wid: str, lid: str, filters=Depends(filter_params)):
    with workspace(wid) as db:
        row = db.execute("SELECT * FROM lore WHERE id=?", (lid,)).fetchone()
        if not row:
            raise KeyError("Lore not found")
        data = analytics.word_explorer(db, filters, row["title"], "phrase")
        related = analysis.search(db, wid, filters, row["title"], "hybrid", 12)
        data["related"] = [
            message(db, db.execute("SELECT * FROM messages WHERE id=?", (sid,)).fetchone())
            for sid in related["ids"]
            if sid not in data["message_ids"][:10]
        ]
        data["title"] = row["title"]
        return data


@app.get("/api/v1/workspaces/{wid}/topics")
def topics(wid: str, filters=Depends(filter_params)) -> dict[str, Any]:
    with workspace(wid) as db:
        where, args = scope(db, **filters)
        rows = [
            decode_sources(r)
            for r in db.execute(
                f"SELECT t.id,t.label,t.terms,t.sources,t.version,count(*) count FROM messages m JOIN topics t ON t.id=m.topic_id WHERE {where} GROUP BY t.id ORDER BY count DESC",
                args,
            )
        ]
        trend = [
            dict(r)
            for r in db.execute(
                f"SELECT m.topic_id,substr(day,1,7) month,count(*) count FROM messages m WHERE {where} AND topic_id IS NOT NULL GROUP BY topic_id,month",
                args,
            )
        ]
        return {
            "topics": rows,
            "trend": trend,
            "ready": meta(db, "semantic_revision", -1) == meta(db, "revision", 0),
        }


@app.get("/api/v1/workspaces/{wid}/search")
def search(
    wid: str,
    q: str = Query(min_length=1, max_length=1000),
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
    filters=Depends(filter_params),
) -> dict[str, Any]:
    with workspace(wid) as db:
        result = analysis.search(db, wid, filters, q, mode)
        lookup = {r["id"]: r for r in list_messages(db, filters, 200, ids=result["ids"])["items"]}
        return {**result, "items": [lookup[sid] for sid in result["ids"] if sid in lookup]}


@app.get("/api/v1/workspaces/{wid}/media")
def media_items(
    wid: str, q: str = "", similar: str | None = None, filters=Depends(filter_params)
) -> dict[str, Any]:
    with workspace(wid) as db:
        return media.media_list(db, wid, filters, q, similar)


@app.get("/api/v1/workspaces/{wid}/attachments/{aid}")
def attachment(wid: str, aid: str):
    path, mime = media.preview_file(wid, aid)
    return FileResponse(
        path,
        media_type=mime,
        content_disposition_type="attachment" if mime == "application/octet-stream" else "inline",
        filename=path.name,
    )


@app.get("/api/v1/workspaces/{wid}/export.csv")
def export(wid: str, filters=Depends(filter_params)):
    with workspace(wid) as db:
        text = analytics.export_csv(db, filters)
    return Response(
        text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=group-chat-statistics.csv"},
    )


@app.get("/api/v1/workspaces/{wid}/games")
def game(
    wid: str, kind: Literal["who", "finish", "year"] = "who", filters=Depends(filter_params)
) -> dict[str, Any]:
    with workspace(wid) as db:
        where, args = scope(db, **filters)
        rows = db.execute(
            f"SELECT m.* FROM messages m WHERE {where} AND words>=6 AND words<=40 ORDER BY random() LIMIT 1",
            args,
        ).fetchall()
        if not rows:
            raise ValueError("No suitable messages in this selection; widen your filters")
        row = rows[0]
        if kind == "who":
            options = [dict(r) for r in db.execute("SELECT id,name FROM people")]
            answer = row["person_id"]
            question = row["text"]
        elif kind == "year":
            year = datetime.fromtimestamp(row["ts"], ZoneInfo(meta(db, "timezone", "UTC"))).year
            options = [{"id": str(n), "name": str(n)} for n in range(year - 2, year + 2)]
            answer = str(year)
            question = row["text"]
        else:
            tokens = row["text"].split()
            split = max(2, len(tokens) - 3)
            correct = " ".join(tokens[split:])
            distractors = [
                r[0]
                for r in db.execute(
                    f"SELECT text FROM messages m WHERE {where} AND words>=5 ORDER BY random() LIMIT 12", args
                )
            ]
            opts = list(dict.fromkeys([correct] + [" ".join(t.split()[-3:]) for t in distractors]))[:4]
            options = [{"id": text, "name": text} for text in opts]
            answer = correct
            question = " ".join(tokens[:split]) + " …"
        random.shuffle(options)
        gid = uuid.uuid4().hex
        db.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
            (
                gid,
                "game",
                kind,
                json.dumps({"answer": answer, "id": row["id"]}),
                json.dumps([row["id"]]),
                now(),
                "game-v1",
            ),
        )
        return {"id": gid, "kind": kind, "question": question, "options": options}


class GameAnswer(BaseModel):
    answer: str


@app.post("/api/v1/workspaces/{wid}/games/{gid}/answer")
def answer_game(wid: str, gid: str, body: GameAnswer):
    with workspace(wid) as db:
        row = db.execute("SELECT body FROM artifacts WHERE id=? AND kind='game'", (gid,)).fetchone()
        if not row:
            raise KeyError("Game not found")
        data = json.loads(row[0])
        return {"correct": body.answer == data["answer"], "answer": data["answer"], "message_id": data["id"]}


@app.get("/api/v1/workspaces/{wid}/awards")
def awards(wid: str):
    with workspace(wid) as db:
        return [
            {"id": r["id"], **json.loads(r["body"])}
            for r in db.execute("SELECT id,body FROM artifacts WHERE kind='award'")
        ]


@app.post("/api/v1/workspaces/{wid}/awards")
def award(wid: str, body: AwardInput):
    aid = uuid.uuid4().hex
    with workspace(wid) as db:
        if not db.execute("SELECT 1 FROM people WHERE id=?", (body.person,)).fetchone():
            raise ValueError("Member not found")
        db.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
            (aid, "award", body.title, json.dumps(body.model_dump()), "[]", now(), "manual-v1"),
        )
    return {"id": aid}


@app.put("/api/v1/workspaces/{wid}/awards/{aid}")
def edit_award(wid: str, aid: str, body: AwardInput):
    with workspace(wid) as db:
        if not db.execute("SELECT 1 FROM people WHERE id=?", (body.person,)).fetchone():
            raise ValueError("Member not found")
        if not db.execute("SELECT 1 FROM artifacts WHERE id=? AND kind='award'", (aid,)).fetchone():
            raise KeyError("Award not found")
        db.execute(
            "UPDATE artifacts SET title=?,body=? WHERE id=?", (body.title, json.dumps(body.model_dump()), aid)
        )
    return {"ok": True}


@app.delete("/api/v1/workspaces/{wid}/awards/{aid}")
def delete_award(wid: str, aid: str):
    with workspace(wid) as db:
        db.execute("DELETE FROM artifacts WHERE id=? AND kind='award'", (aid,))
    return {"ok": True}


@app.get("/api/v1/workspaces/{wid}/settings")
def settings(wid: str):
    with workspace(wid) as db:
        return {
            "timezone": meta(db, "timezone"),
            "session_gap": meta(db, "session_gap"),
            "contacts": meta(db, "contacts", {"status": "not_requested"}),
            "cloud_enabled": meta(db, "cloud_enabled", False),
            "cloud_model": meta(db, "cloud_model", ""),
            "has_key": cloud.has_key(wid),
            "coverage": {
                **meta(db, "coverage", {}),
                "missing_attachments": db.execute(
                    "SELECT count(*) FROM attachments WHERE exists_local=0"
                ).fetchone()[0],
                "unsupported_records": db.execute(
                    "SELECT count(*) FROM messages WHERE json_extract(raw,'$.variant') LIKE 'Unknown%'"
                ).fetchone()[0],
            },
            "semantic_ready": meta(db, "semantic_revision", -1) == meta(db, "revision", 0),
            "semantic_passages": meta(db, "semantic_passages", 0),
            "source": meta(db, "source"),
            "dependencies": {
                k: bool(importlib.util.find_spec(v))
                for k, v in {
                    "embeddings": "sentence_transformers",
                    "vectors": "hnswlib",
                    "clustering": "hdbscan",
                    "audio": "whisper",
                }.items()
            },
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "usage": [dict(r) for r in db.execute("SELECT * FROM usage ORDER BY created DESC LIMIT 30")],
        }


@app.put("/api/v1/workspaces/{wid}/settings")
def save_settings(wid: str, body: SettingsInput):
    if body.timezone:
        try:
            ZoneInfo(body.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Timezone must be an IANA name, such as America/Los_Angeles")
    if body.api_key:
        cloud.save_key(wid, body.api_key)
    with workspace(wid) as db:
        changed = False
        for k, v in body.model_dump(exclude_none=True, exclude={"api_key"}).items():
            if k in ("timezone", "session_gap") and meta(db, k) != v:
                changed = True
            set_meta(db, k, v)
        if changed:
            rebuild(db)
            analysis.derive_local(db)
            set_meta(db, "revision", meta(db, "revision", 0) + 1)
            set_meta(db, "semantic_revision", -1)
    return {"ok": True}


@app.post("/api/v1/workspaces/{wid}/cloud/preview")
def cloud_preview(wid: str, body: CloudInput):
    with workspace(wid) as db:
        return cloud.preview(db, wid, body.filters.model_dump(exclude_none=True), body.kind, body.question)


@app.post("/api/v1/workspaces/{wid}/cloud/generate")
def cloud_generate(wid: str, body: CloudInput):
    if not body.approved:
        raise ValueError("Review the scope preview before starting cloud generation")
    with workspace(wid) as db:
        if body.kind == "qa":
            answer = cloud.numerical_answer(db, body.filters.model_dump(exclude_none=True), body.question)
            if answer:
                return {"result": answer}
        if not meta(db, "cloud_enabled", False) or not cloud.has_key(wid) or not meta(db, "cloud_model", ""):
            raise ValueError("Configure and enable cloud generation in Settings first")
    return {"job_id": jobs.enqueue(wid, "cloud", body.model_dump())}


@app.get("/api/v1/workspaces/{wid}/artifacts")
def artifacts(wid: str, kind: str | None = None):
    with workspace(wid) as db:
        rows = db.execute(
            "SELECT * FROM artifacts WHERE kind IN ('eras','lore','recap') ORDER BY created DESC"
        ).fetchall()
        return [
            {**decode_sources(r), "body": json.loads(r["body"])}
            for r in rows
            if kind is None or r["kind"] == kind
        ]


@app.post("/api/v1/workspaces/{wid}/jobs")
def create_job(wid: str, body: AnalysisJob):
    workspace_dir(wid)
    return {"id": jobs.enqueue(wid, body.kind, body.model_dump(exclude={"kind"}))}


@app.get("/api/v1/jobs")
def all_jobs(wid: str | None = None):
    with registry() as db:
        return [
            decode_job(r)
            for r in db.execute(
                "SELECT * FROM jobs WHERE (? IS NULL OR workspace=?) ORDER BY created DESC LIMIT 30",
                (wid, wid),
            )
        ]


def decode_job(row):
    r = dict(row)
    payload = json.loads(r.pop("payload"))
    if "result" in payload:
        r["result"] = payload["result"]
    return r


@app.post("/api/v1/jobs/{jid}/cancel")
def cancel_job(jid: str):
    with registry() as db:
        db.execute(
            "UPDATE jobs SET cancel=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END WHERE id=?",
            (jid,),
        )
    return {"ok": True}


@app.post("/api/v1/jobs/{jid}/retry")
def retry_job(jid: str):
    with registry() as db:
        r = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            raise KeyError("Job not found")
        if r["status"] not in ("failed", "cancelled"):
            raise ValueError("Only failed or cancelled jobs can retry")
        if r["kind"] == "import":
            raise ValueError("Discover your source again to retry an import")
        db.execute(
            "UPDATE jobs SET status='queued',cancel=0,progress=0,message='Retrying' WHERE id=?", (jid,)
        )
    return {"ok": True}


@app.get("/api/v1/jobs/events")
async def job_events(request: Request, wid: str | None = None):
    async def stream():
        last = ""
        while not await request.is_disconnected():
            current = json.dumps(all_jobs(wid))
            if current != last:
                yield "data: " + current + "\n\n"
                last = current
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


if (PROJECT / "dist").is_dir():
    app.mount("/", StaticFiles(directory=PROJECT / "dist", html=True), name="frontend")
