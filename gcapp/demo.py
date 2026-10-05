"""Deterministic fictional history; never generated from a real archive."""

import random
from datetime import datetime, timezone

from .store import create_workspace, import_records, set_meta, workspace, workspace_dir

NAMES = ["Alex", "Maya", "Theo", "Jules", "Sam", "Riley"]
CHAPTERS = [
    (
        "The apartment era",
        2019,
        ["apartment", "pizza", "roommate", "couch", "midterm"],
        [
            "who took my pizza from the fridge",
            "apartment movie night at 8?",
            "the couch has seen things",
            "midterm tomorrow wish me luck",
            "roommate meeting: pizza is not a personality",
        ],
    ),
    (
        "The sourdough arc",
        2020,
        ["sourdough", "zoom", "quarantine", "bread", "island"],
        [
            "my sourdough starter has a name now",
            "zoom trivia tonight?",
            "quarantine day 47: bread again",
            "animal crossing island tour anyone",
            "the sourdough is the seventh member of this chat",
        ],
    ),
    (
        "Outside again",
        2021,
        ["hike", "concert", "park", "picnic", "tickets"],
        [
            "picnic at the park on Saturday",
            "concert tickets secured!!",
            "hike was worth the sunrise",
            "outside again and immediately sunburned",
            "please bring snacks to the hike",
        ],
    ),
    (
        "The road trip",
        2022,
        ["roadtrip", "flight", "airport", "camping", "mountain"],
        [
            "roadtrip spreadsheet is ready",
            "we almost missed our flight at the airport",
            "camping under the stars was unreal",
            "mountain cabin booked for June",
            "who packed six bags for a weekend",
        ],
    ),
    (
        "Different cities, same chat",
        2023,
        ["city", "moving", "job", "reunion", "train"],
        [
            "new job starts Monday!",
            "moving to a new city is weird",
            "reunion in October let's make it happen",
            "train home and missing everyone",
            "different cities same questionable decisions",
        ],
    ),
    (
        "The reunion season",
        2024,
        ["reunion", "wedding", "dance", "hotel", "karaoke"],
        [
            "reunion photo just dropped",
            "wedding dance floor MVP was Theo",
            "karaoke rematch immediately",
            "hotel lobby breakfast is our new headquarters",
            "we are absolutely doing this again",
        ],
    ),
    (
        "The running club",
        2025,
        ["run", "marathon", "coffee", "training", "pace"],
        [
            "morning run followed by coffee?",
            "marathon training week 4 survived",
            "pace is temporary coffee is forever",
            "run club is just brunch with extra steps",
            "personal best today let's gooo",
        ],
    ),
    (
        "Still the same chaos",
        2026,
        ["dinner", "birthday", "game", "weekend", "chaos"],
        [
            "birthday dinner Friday everyone free?",
            "game night at mine this weekend",
            "seven years and still the same chaos",
            "dinner reservation confirmed for six",
            "weekend plans: absolutely no plans",
        ],
    ),
]


def create_demo():
    from .analysis import derive_local

    wid = create_workspace("The usual suspects")
    from PIL import Image, ImageDraw, ImageFont

    media_dir = workspace_dir(wid) / "demo-media"
    media_dir.mkdir(exist_ok=True)
    fontpath = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font = (
        ImageFont.truetype(fontpath, 44)
        if __import__("pathlib").Path(fontpath).is_file()
        else ImageFont.load_default(size=44)
    )
    for n, (title, color) in enumerate(
        [
            ("THE COUNCIL HAS SPOKEN", "#ead3a8"),
            ("REUNION • OCTOBER 2024", "#c6dacb"),
            ("COFFEE IS FOREVER", "#e6bbb0"),
        ]
    ):
        image = Image.new("RGB", (960, 640), color)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((35, 35, 925, 605), radius=32, outline="#493e35", width=4)
        draw.text((65, 180), title, font=font, fill="#493e35")
        draw.text(
            (65, 290),
            "A FICTIONAL GROUP CHAT MEMORY",
            font=font.font_variant(size=28) if hasattr(font, "font_variant") else font,
            fill="#493e35",
        )
        draw.ellipse((730, 420, 850, 540), fill="#d27453")
        image.save(media_dir / f"memory-{n}.png")
    rng = random.Random(174)
    records = []
    ts = datetime(2019, 4, 8, 17, 0, tzinfo=timezone.utc).timestamp()
    end = datetime(2026, 10, 3, 23, tzinfo=timezone.utc).timestamp()
    index = 0
    while ts < end:
        dt = datetime.fromtimestamp(ts, timezone.utc)
        chapter = CHAPTERS[dt.year - 2019]
        if rng.random() < 0.6:
            ts += rng.randint(1, 5) * 86400 + rng.randint(0, 3000)
            continue
        burst = rng.randint(6, 28)
        for j in range(burst):
            pid = rng.choices(NAMES, weights=[25, 24, 18, 15, 10, 8])[0]
            text = rng.choice(chapter[3])
            if j:
                text = rng.choice(
                    [
                        text,
                        "lmao",
                        "absolutely iconic",
                        "say less",
                        "no thoughts just vibes",
                        "the council has spoken",
                        "let's gooo",
                        "wait WHAT",
                        "I'm in",
                        "this is so us",
                        "😂😂",
                        text,
                    ]
                )
            if index % 79 == 0:
                text += " https://open.spotify.com/track/fictional-demo"
            mid = f"demo-{index:06d}"
            records.append(
                {
                    "schema_version": 1,
                    "record": "message",
                    "id": mid,
                    "chat_id": "demo",
                    "person": pid,
                    "person_name": pid,
                    "ts": ts,
                    "text": text,
                    "reply_to": f"demo-{index - 1:06d}" if j and rng.random() < 0.12 else None,
                }
            )
            if index % 1200 == 0:
                n = (index // 1200) % 3
                records[-1]["attachments"] = [
                    {
                        "id": f"demo-image-{index}",
                        "path": str(media_dir / f"memory-{n}.png"),
                        "name": f"memory-{n}.png",
                        "mime": "image/png",
                    }
                ]
            if index == 1201:
                records[-1]["attachments"] = [
                    {
                        "id": "demo-missing",
                        "path": str(media_dir / "undownloaded.jpg"),
                        "name": "undownloaded.jpg",
                        "mime": "image/jpeg",
                    }
                ]
            for k, actor in enumerate(
                rng.sample(
                    [p for p in NAMES if p != pid], rng.choices(range(6), weights=[50, 20, 15, 8, 5, 2])[0]
                )
            ):
                records.append(
                    {
                        "schema_version": 1,
                        "record": "reaction",
                        "id": f"reaction-{index}-{k}",
                        "person": actor,
                        "target": mid,
                        "ts": ts + rng.randint(20, 200),
                        "type": rng.choice(["heart", "laugh", "laugh", "like", "emphasize"]),
                        "action": "add",
                    }
                )
            index += 1
            ts += rng.randint(10, 100)
        ts += rng.randint(1, 3) * 86400
    with workspace(wid) as db:
        import_records(db, records)
        set_meta(db, "demo", True)
        derive_local(db)
    return wid
