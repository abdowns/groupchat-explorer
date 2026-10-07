# Group Chat Explorer

A local macOS app to explore your Messages group history: conversations, timelines, member and reaction statistics, semantic search, lore, recaps, and games. Licensed under [GPL version 3](LICENSE).

## Setup

Requires Node.js 22+, Python 3.12, Rust, and Xcode Command Line Tools.

```sh
xcode-select --install
brew install node python@3.12 rust ffmpeg
npm start
```

Open **http://127.0.0.1:8765**. First launch builds the app and installs its Python dependencies. Try **Explore the demo** or import your own group.

## Import

Choose **Import a chat**, select `~/Library/Messages/chat.db` or a database snapshot, and select your group. Select multiple related threads to combine a split chat.

- If access is denied, grant the launching terminal/app **Full Disk Access** in macOS settings, then restart it.
- Use **Use saved contact names in Settings & analysis** to apply Contacts names.
- Use **Refresh archive** to update messages, edits, and reactions.

Apple's database is never modified. App data lives in `~/Library/Application Support/GroupChatExplorer`; back up this directory to preserve your archive. Missing messages and undownloaded attachments cannot be recovered.

## Optional analysis

```sh
.venv/bin/pip install -e '.[analysis]'
```

Then choose **Build semantic index in Settings & analysis** for semantic search, topics, eras, and semantic member rankings. Media analysis is also available. First use downloads model weights; inference runs locally.

Cloud narratives and Q&A require an OpenAI key and explicit permission for each workspace. API keys are stored in macOS Keychain.

## Development

```sh
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
npm run build
```

See [contributing](CONTRIBUTING.md), and [dependency notices](NOTICE)
