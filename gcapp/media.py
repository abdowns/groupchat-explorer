import json
import shutil
import subprocess
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image

from .analysis import embedding_model
from .store import ROOT, scope, stable_id, workspace, workspace_dir

PROJECT = Path(__file__).resolve().parent.parent


def analyze_media(wid, options, progress):
    model = None
    whisper = None
    with workspace(wid) as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM attachments WHERE exists_local=1")]
    directory = workspace_dir(wid)
    cache = directory / "image-vectors"
    cache.mkdir(exist_ok=True)
    vector_ids, vectors = [], []
    for i, row in enumerate(rows):
        progress(i / max(1, len(rows)), f"Analyzing {i + 1:,} / {len(rows):,} attachments")
        path = Path(row["path"])
        annotation = json.loads(row["annotation"])
        text = row["extracted"]
        phash = row["hash"]
        try:
            mime = row["mime"] or ""
            if mime.startswith("image/"):
                if mime in ("image/heic", "image/heif", "image/heics"):
                    converted, _ = preview_file(wid, row["id"])
                    image = Image.open(converted).convert("RGB")
                else:
                    image = Image.open(path).convert("RGB")
                phash = str(imagehash.phash(image))
                if options.get("ocr") and not annotation.get("ocr_complete"):
                    binary = ROOT / "bin/vision-ocr"
                    if not binary.is_file():
                        binary.parent.mkdir(parents=True, exist_ok=True)
                        subprocess.run(
                            [
                                "clang",
                                "-fobjc-arc",
                                "-framework",
                                "Foundation",
                                "-framework",
                                "Vision",
                                str(PROJECT / "helpers/ocr.m"),
                                "-o",
                                str(binary),
                            ],
                            check=True,
                            capture_output=True,
                            timeout=120,
                        )
                    output = subprocess.run(
                        [str(binary), str(path)], check=True, capture_output=True, text=True, timeout=60
                    )
                    text = json.loads(output.stdout)["text"]
                    annotation["ocr_complete"] = True
                    annotation["text_source"] = "macOS Vision OCR"
                if options.get("images"):
                    cached = cache / (stable_id(row["id"] + str(path.stat().st_mtime_ns)) + ".npy")
                    if cached.is_file():
                        vector = np.load(cached, allow_pickle=False)
                    else:
                        model = model or embedding_model("sentence-transformers/clip-ViT-B-32")
                        vector = model.encode(image, normalize_embeddings=True)
                        np.save(cached, vector)
                    vectors.append(vector)
                    vector_ids.append(row["id"])
                    annotation["image_embedding"] = True
            elif mime.startswith("audio/") and options.get("audio") and not text:
                if whisper is None:
                    import whisper as whisper_module

                    whisper = whisper_module.load_model("base.en")
                result = whisper.transcribe(str(path), fp16=False)
                text = result["text"]
                annotation["text_source"] = "Whisper base.en"
            annotation.pop("error", None)
        except Exception as e:
            annotation["error"] = str(e)[:300]
        with workspace(wid) as db:
            db.execute(
                "UPDATE attachments SET extracted=?,annotation=?,hash=? WHERE id=?",
                (text, json.dumps(annotation), phash, row["id"]),
            )
    if vector_ids:
        directory = workspace_dir(wid)
        np.savez(directory / "images.npz", ids=np.array(vector_ids), vectors=np.array(vectors))
    progress(1, "Media analysis finished; individual errors are shown on their files")


def media_list(db, wid, filters, query="", similar=None):
    where, args = scope(db, **filters)
    condition = ""
    if query:
        condition = (
            " AND (instr(lower(a.extracted),?)>0 OR instr(lower(a.name),?)>0 OR instr(lower(m.text),?)>0)"
        )
        args += [query.casefold()] * 3
    rows = [
        dict(r)
        for r in db.execute(
            f"SELECT a.*,m.ts,m.person_id,m.text FROM attachments a JOIN messages m ON m.id=a.message_id WHERE {where}{condition} ORDER BY m.ts DESC LIMIT 300",
            args,
        )
    ]
    if similar:
        original = db.execute("SELECT hash FROM attachments WHERE id=?", (similar,)).fetchone()
        if original and original[0]:
            rows.sort(
                key=lambda r: (
                    imagehash.hex_to_hash(r["hash"]) - imagehash.hex_to_hash(original[0])
                    if r["hash"]
                    else 999
                )
            )
    vector_path = workspace_dir(wid) / "images.npz"
    if query and vector_path.is_file():
        # Union semantic image matches with OCR/name matches under the same source filters.
        vs = np.load(vector_path, allow_pickle=False)
        vector = embedding_model("sentence-transformers/clip-ViT-B-32").encode(
            [query], normalize_embeddings=True
        )[0]
        scores = vs["vectors"] @ vector
        existing = {r["id"] for r in rows}
        sw, sa = scope(db, **filters)
        for idx in scores.argsort()[-30:][::-1]:
            aid = str(vs["ids"][idx])
            if aid in existing:
                continue
            row = db.execute(
                f"SELECT a.*,m.ts,m.person_id,m.text FROM attachments a JOIN messages m ON m.id=a.message_id WHERE {sw} AND a.id=?",
                sa + [aid],
            ).fetchone()
            if row:
                rows.append({**dict(row), "similarity": float(scores[idx])})
    for r in rows:
        r.pop("path", None)
        r["annotation"] = json.loads(r["annotation"])
    sw, sa = scope(db, **filters)
    links = [
        dict(r)
        for r in db.execute(
            f"SELECT l.*,m.ts,m.person_id FROM links l JOIN messages m ON m.id=l.message_id WHERE {sw} ORDER BY m.ts DESC LIMIT 100",
            sa,
        )
    ]
    domains = [
        dict(r)
        for r in db.execute(
            f"SELECT l.domain,count(*) count FROM links l JOIN messages m ON m.id=l.message_id WHERE {sw} GROUP BY l.domain ORDER BY count DESC LIMIT 20",
            sa,
        )
    ]
    duplicates = [
        dict(r)
        for r in db.execute(
            f"SELECT a.hash,count(*) count,min(a.id) example FROM attachments a JOIN messages m ON m.id=a.message_id WHERE {sw} AND a.hash IS NOT NULL GROUP BY a.hash HAVING count(*)>1 ORDER BY count DESC",
            sa,
        )
    ]
    return {"attachments": rows, "links": links, "domains": domains, "duplicates": duplicates}


def preview_file(wid, aid):
    with workspace(wid) as db:
        row = db.execute("SELECT * FROM attachments WHERE id=?", (aid,)).fetchone()
    if not row:
        raise KeyError("Attachment not found")
    path = Path(row["path"])
    if not path.is_file():
        raise ValueError("Attachment is missing from this Mac")
    mime = row["mime"] or "application/octet-stream"
    if mime in ("image/heic", "image/heif", "image/heics"):
        out = workspace_dir(wid) / "previews" / (stable_id(aid) + ".jpg")
        out.parent.mkdir(exist_ok=True)
        if not out.is_file():
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(path), "--out", str(out)],
                check=True,
                capture_output=True,
                timeout=60,
            )
        return out, "image/jpeg"
    if (
        mime.startswith("audio/")
        and mime not in ("audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav")
        or mime in ("video/quicktime",)
    ):
        if not shutil.which("ffmpeg"):
            raise ValueError("Install FFmpeg to preview this file")
        directory = workspace_dir(wid) / "previews"
        directory.mkdir(exist_ok=True)
        out = directory / (stable_id(aid) + ".mp4")
        if not out.is_file():
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-i", str(path), "-c:v", "libx264", "-c:a", "aac", str(out)],
                check=True,
                capture_output=True,
                timeout=180,
            )
        return out, "video/mp4" if mime.startswith("video") else "audio/mp4"
    # Never serve HTML/SVG actively in the app's origin.
    if mime not in (
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "audio/mpeg",
        "audio/mp4",
        "audio/ogg",
        "audio/wav",
    ):
        return path, "application/octet-stream"
    return path, mime
