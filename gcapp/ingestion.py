import json
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import ROOT, import_records, meta, now, registry, set_meta, workspace

PROJECT = Path(__file__).resolve().parent.parent


def importer():
    path = Path(os.environ.get("GCAPP_IMPORTER", PROJECT / "importer/target/release/gc-importer"))
    if not path.is_file():
        raise ValueError("Build the parser first: cargo build --release --manifest-path importer/Cargo.toml")
    return path


def snapshot(source):
    source = Path(source or "~/Library/Messages/chat.db").expanduser().resolve()
    if not source.is_file():
        raise ValueError(
            "Database not found. Select chat.db or grant your terminal Full Disk Access in System Settings → Privacy & Security, then restart it."
        )
    destdir = ROOT / "imports"
    destdir.mkdir(parents=True, exist_ok=True)
    with registry() as reg:
        for row in reg.execute(
            "SELECT id,path FROM imports WHERE created<?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),),
        ).fetchall():
            active = reg.execute(
                "SELECT 1 FROM jobs WHERE status IN ('queued','running') AND json_extract(payload,'$.import_id')=?",
                (row["id"],),
            ).fetchone()
            if not active:
                Path(row["path"]).unlink(missing_ok=True)
                reg.execute("DELETE FROM imports WHERE id=?", (row["id"],))
    iid = uuid.uuid4().hex
    dest = destdir / f"{iid}.sqlite"
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=15) as original:
            tables = {r[0] for r in original.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"message", "chat", "handle", "chat_message_join"}.issubset(tables):
                raise ValueError("This is not a supported Messages database")
            with sqlite3.connect(dest) as copied:
                original.backup(copied, pages=1000, sleep=0.05)
        os.chmod(dest, 0o600)
        with registry() as reg:
            reg.execute("INSERT INTO imports VALUES(?,?,?,?)", (iid, str(dest), str(source), now()))
        return iid
    except (PermissionError, sqlite3.OperationalError) as e:
        dest.unlink(missing_ok=True)
        raise ValueError(
            "Cannot read Messages. Grant your terminal Full Disk Access in System Settings → Privacy & Security, restart it, and retry."
        ) from e


def import_info(iid):
    with registry() as reg:
        row = reg.execute("SELECT * FROM imports WHERE id=?", (iid,)).fetchone()
    if not row:
        raise ValueError("Import snapshot not found; discover chats again")
    return dict(row)


def discover(iid):
    info = import_info(iid)
    result = subprocess.run(
        [str(importer()), "discover", info["path"]], text=True, capture_output=True, timeout=120
    )
    if result.returncode:
        raise ValueError(result.stderr.strip()[:1000])
    return [json.loads(line) for line in result.stdout.splitlines() if line]


def perform_import(wid, iid, chat_ids, attachment_root=None, progress=None):
    from .analysis import derive_local

    info = import_info(iid)
    process = subprocess.Popen(
        [str(importer()), "export", info["path"], ",".join(str(x) for x in chat_ids)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def records():
        for line in process.stdout:
            yield json.loads(line)
        error = process.stderr.read()
        if process.wait():
            raise ValueError(error.strip()[:1000])

    try:
        with workspace(wid) as db:
            count = import_records(db, records(), attachment_root, progress, full_snapshot=True)
            set_meta(
                db,
                "source",
                {"path": info["source"], "chat_ids": chat_ids, "attachment_root": attachment_root},
            )
            derive_local(db)
        return count
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
        Path(info["path"]).unlink(missing_ok=True)
        with registry() as reg:
            reg.execute("DELETE FROM imports WHERE id=?", (iid,))


def refresh(wid, progress=None):
    with workspace(wid) as db:
        source = meta(db, "source")
    if not source:
        raise ValueError("This workspace has no Messages source; demo archives cannot refresh")
    iid = snapshot(source["path"])
    return perform_import(wid, iid, source["chat_ids"], source.get("attachment_root"), progress)
