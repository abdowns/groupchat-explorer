"""Read macOS Contacts through a permission-aware native helper; never write contacts."""

import json
import re
import subprocess
import sys
from pathlib import Path

from .store import meta, now, set_meta

PROJECT = Path(__file__).resolve().parent.parent


def address_key(value):
    value = value.strip().casefold()
    if "@" in value:
        return value
    if not re.fullmatch(r"[+0-9().\s-]+", value):
        return ""
    digits = re.sub(r"[^0-9]", "", value)
    if value.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and not value.startswith(("+", "00")):
        digits = "1" + digits
    return digits if len(digits) >= 7 else ""


def read_contacts(handles, request_access=False):
    if sys.platform != "darwin":
        return {"status": "unsupported", "contacts": []}
    helper = PROJECT / "native/contacts/target/gc-contacts"
    if not helper.is_file():
        return {
            "status": "unavailable",
            "contacts": [],
            "error": "Restart with npm start to build Contacts support.",
        }
    keys = sorted({"me" if h == "me" else address_key(h) for h in handles} - {""})
    try:
        result = subprocess.run(
            [str(helper)],
            input=json.dumps({"keys": keys, "request_access": request_access}),
            text=True,
            capture_output=True,
            timeout=120 if request_access else 30,
        )
        if result.returncode:
            raise ValueError("Contacts helper failed")
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {
            "status": "error",
            "contacts": [],
            "error": "Could not read Contacts. Check access in System Settings → Privacy & Security → Contacts, then retry.",
        }


def sync_names(db, request_access=False):
    people = [dict(row) for row in db.execute("SELECT id,name FROM people")]
    identities = meta(db, "identity_map", {})
    handles = {p["id"] for p in people} | set(identities)
    result = read_contacts(handles, request_access)
    summary = {"status": result["status"], "updated": 0, "matched": 0, "ambiguous": 0, "checked_at": now()}
    if result.get("error"):
        summary["error"] = result["error"]
    if result["status"] != "available":
        set_meta(db, "contacts", summary)
        return summary
    candidates = {}
    for contact in result.get("contacts", []):
        for key in contact["keys"] + (["me"] if contact.get("is_me") else []):
            candidates.setdefault(key, {})[contact["id"]] = contact["name"]
    previous = meta(db, "contact_names", {})
    manual = meta(db, "manual_names", {})
    for person in people:
        pid = person["id"]
        sources = [pid] + [key for key, target in identities.items() if target == pid]
        matches = {}
        for source in sources:
            matches.update(candidates.get("me" if source == "me" else address_key(source), {}))
        if len(matches) > 1:
            summary["ambiguous"] += 1
            continue
        if not matches:
            continue
        summary["matched"] += 1
        name = next(iter(matches.values()))
        # Preserve explicit renames, including custom names saved by older versions.
        if pid in manual or person["name"] not in (pid, previous.get(pid)):
            continue
        if person["name"] != name:
            db.execute("UPDATE people SET name=? WHERE id=?", (name, pid))
            summary["updated"] += 1
        previous[pid] = name
    set_meta(db, "contact_names", previous)
    set_meta(db, "contacts", summary)
    return summary
