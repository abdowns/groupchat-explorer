import json
import threading
import uuid

from .store import now, registry, workspace


class Cancelled(Exception):
    pass


def enqueue(wid, kind, payload=None):
    jid = uuid.uuid4().hex
    with registry() as db:
        db.execute(
            "INSERT INTO jobs(id,workspace,kind,payload,status,created,updated) VALUES(?,?,?,?,?,?,?)",
            (jid, wid, kind, json.dumps(payload or {}), "queued", now(), now()),
        )
    return jid


def update(jid, progress, message):
    with registry() as db:
        r = db.execute("SELECT cancel FROM jobs WHERE id=?", (jid,)).fetchone()
        if r and r[0]:
            raise Cancelled()
        db.execute(
            "UPDATE jobs SET progress=?,message=?,updated=? WHERE id=?", (progress, message, now(), jid)
        )


def execute(row):
    from .analysis import build_semantics, derive_local
    from .cloud import generate
    from .ingestion import perform_import, refresh
    from .media import analyze_media

    payload = json.loads(row["payload"])
    wid = row["workspace"]

    def progress(n, m):
        update(row["id"], n, m)

    if row["kind"] == "import":
        perform_import(
            wid,
            payload["import_id"],
            payload["chat_ids"],
            payload.get("attachment_root"),
            lambda n: progress(min(0.85, n / (n + 10000)), f"Decoded {n:,} source records"),
        )
    elif row["kind"] == "refresh":
        refresh(wid, lambda n: progress(min(0.85, n / (n + 10000)), f"Reconciling {n:,} records"))
    elif row["kind"] == "semantic":
        build_semantics(wid, progress)
    elif row["kind"] == "local":
        with workspace(wid) as db:
            derive_local(db, progress)
    elif row["kind"] == "media":
        analyze_media(wid, payload, progress)
    elif row["kind"] == "cloud":
        result = generate(
            wid, payload["kind"], payload.get("filters", {}), payload.get("question", ""), progress
        )
        with registry() as db:
            payload["result"] = result
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), row["id"]))
    else:
        raise ValueError("Unknown analysis job")
    progress(1, "Finished")


def worker(stop):
    with registry() as db:
        db.execute("UPDATE jobs SET status='queued',message='Resuming after restart' WHERE status='running'")
    while not stop.is_set():
        with registry() as db:
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (now(), row["id"]))
        if not row:
            stop.wait(0.5)
            continue
        status = "complete"
        error = None
        try:
            execute(dict(row))
        except Cancelled:
            status = "cancelled"
            error = "Cancelled. Completed embeddings and media files remain cached."
        except Exception as e:
            status = "failed"
            error = str(e)[:500]
        with registry() as db:
            db.execute(
                "UPDATE jobs SET status=?,message=coalesce(?,message),updated=? WHERE id=?",
                (status, error, now(), row["id"]),
            )


def start_worker():
    stop = threading.Event()
    thread = threading.Thread(target=worker, args=(stop,), name="gc-analysis", daemon=True)
    thread.start()
    return stop, thread
