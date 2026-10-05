import argparse
import importlib.util
import json
import shutil


def main():
    parser = argparse.ArgumentParser(description="Group Chat Explorer")
    parser.add_argument("command", choices=["serve", "demo", "doctor"], nargs="?", default="serve")
    args = parser.parse_args()
    if args.command == "demo":
        from .demo import create_demo

        print(create_demo())
    elif args.command == "doctor":
        from .ingestion import PROJECT

        print(
            json.dumps(
                {
                    "rust_parser": (PROJECT / "importer/target/release/gc-importer").is_file(),
                    "frontend": (PROJECT / "dist").is_dir(),
                    "contacts_helper": (PROJECT / "native/contacts/target/gc-contacts").is_file(),
                    "ffmpeg": bool(shutil.which("ffmpeg")),
                    "analysis": bool(importlib.util.find_spec("sentence_transformers")),
                },
                indent=2,
            )
        )
    else:
        import uvicorn

        uvicorn.run("gcapp.api:app", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
