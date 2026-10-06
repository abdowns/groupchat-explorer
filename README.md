# Group Chat Explorer

A local web app for the entire **available** history of one Messages group. Browse the original conversations, explore statistics, trace recurring jokes, search by meaning, and turn real messages into recaps and games. GPL-3.0-only.

## Start on macOS

Install Node.js 22+, Python 3.12, Rust, and Xcode Command Line Tools:

```sh
xcode-select --install
brew install node python@3.12 rust ffmpeg
npm start
```

Open **http://127.0.0.1:8765**. The launch command creates the Python environment, installs dependencies, compiles the Rust importer, and builds the frontend on first use. Choose **Explore the demo** to load a deterministic fictional group with eight years of messages and generated media cards. No personal database is read unless you choose an import.

Enable local semantic search, topics, image embeddings, and audio transcription by installing the analysis extra once:

```sh
.venv/bin/pip install -e '.[analysis]'
```

Then use **Settings & analysis → Build semantic index**, or select the media analysis jobs. First use downloads the selected public model weights; subsequent inference stays local. macOS Vision OCR uses Apple's installed framework. FFmpeg handles optional audio/video previews and Whisper input decoding. `.venv/bin/gcapp doctor` checks installation capabilities.

To install the exact Python versions used during validation instead of resolving the declared ranges, use Python 3.12 and `.venv/bin/pip install -r requirements-lock.txt`, then `.venv/bin/pip install -e . --no-deps`. Node and Rust dependencies have lockfiles. Some Python wheels and model licenses vary by host; see [NOTICE](NOTICE).

## Import your group

1. Choose **Import a chat**, then the local `~/Library/Messages/chat.db` or a supplied snapshot. For a copied database, optionally select the root of its `Attachments` directory.
2. Discover the available groups and select the thread. If Messages split your group (for example, two entries with the same name), compare the displayed date ranges, check both entries, and choose **Combine threads & import**. Their histories share one workspace, timeline, and analytics dashboard; shared message GUIDs are counted once, and refresh updates all selected threads. Participant equality never causes automatic merging.
3. Import. Progress and diagnostics appear under Settings. If Contacts access is already granted, saved names are applied automatically. Use **Settings & analysis → Use saved contact names** to grant Contacts access or update an existing archive. Rename members or explicitly merge their phone/email identities in People.
4. Use **Refresh archive** to reconcile new messages and changed historical edits/reactions. Reimporting the same records is idempotent.

If macOS denies access, grant the terminal running the app (or Codex, if launched here) **Full Disk Access** under System Settings → Privacy & Security, quit/reopen it, and retry. A source database is opened read-only and copied with SQLite's online backup API, including committed WAL state. Apple's database is never altered. The Rust importer uses `imessage-database` to decode structured bodies; it does not scrape HTML.

Saved names come from the read-only [macOS Contacts framework](https://developer.apple.com/documentation/contacts/accessing-the-contact-store), not the Messages database. The launch command builds a small native helper with a Contacts permission description. Allow access when prompted; if denied, enable Contacts access for the helper or launching terminal/app under System Settings → Privacy & Security → Contacts. Only names matched to workspace members are saved locally; no address-book export is stored. Phone punctuation and country prefixes are normalized (unprefixed ten-digit numbers default to North America); emails match without case sensitivity. Ambiguous matches stay unchanged. Your outgoing identity uses the Contacts **My Card** when available. Manual renames take priority, and contact matching never merges identities. Refresh also updates matched names after contact edits.

App-owned workspaces, snapshots, annotations, vector indexes, cached previews, and job state live at `~/Library/Application Support/GroupChatExplorer`, outside this repository. Set `GCAPP_DATA_DIR` to choose another location. API keys are stored in macOS Keychain under `GroupChatExplorer`, indexed by workspace ID. Temporary import snapshots are removed after the import; abandoned discovery snapshots expire after a day when another discovery runs. Back up the data directory to preserve imported history and annotations. Deleting that directory removes the local archive.

## Explore

- **Overview:** totals, participation charts, activity calendar, most-reacted messages, and on-this-day memories.
- **Timeline:** zoomable activity, suggested eras, bursts, quiet-period revivals, recorded changes, and pinned events. Rename, split, combine, and edit era boundaries.
- **People:** participation, word counts, active days, streaks, length, activity hours, vocabulary, phrases, emoji, and topic interests. Stable colors follow each identity.
- **Reactions:** current received reactions, zero-inclusive per-message averages, reacted-message percentage, observed additions given, type breakdowns, giver/recipient matrix, and supporting messages. Minimum sample size defaults to 20.
- **Words & phrases:** case-insensitive whole-word matching, exact phrases, substring mode, or English Porter variants. Compare occurrences, matching messages, and uses per 1,000 authored words; see first/last observed use and trends. Matching archives paginate beyond previews. Choose **Semantic meaning** to rank who talks about a concept using MiniLM similarity, by matching messages or matches per 1,000 authored messages. Adjust the cutoff and minimum sample size, inspect matching conversations, and compare monthly trends.
- **Conversations:** session starters, co-participation network, explicit reply partners/trees, and chronological replay. Inferred sessions default to a 30-minute inactivity gap and remain distinct from explicit replies.
- **Topics & search:** FTS5 keyword retrieval, MiniLM semantic retrieval, reciprocal-rank hybrid fusion, speaker-free conversation embeddings, UMAP/HDBSCAN themes with distinctive phrase labels, monthly counts/share, significant conversations, and source-linked archive questions.
- **Lore:** recurring phrase candidates, adoption across members, observed origins, contextual sources, and optional generated narratives. Treat suggested lore as interpretations you can inspect.
- **Media & links:** attachment gallery, missing-file placeholders, local Vision OCR, existing/Whisper transcripts, repeated-image hashes, CLIP image search, URLs and domains. Shared URLs are never automatically fetched.
- **Recaps & games:** selected-period statistics, era comparison, computed and editable awards, downloadable PNG recap cards, statistics CSV, who-said-it, finish-the-quote, and guess-the-year. Games reveal the actual archived conversation after each answer.

Date, member, and era filters are shared. Click charts/cards to open evidence with nearby context. Conversations use a virtualized, cursor-paginated list. Light/dark themes, reduced-motion styles, keyboard navigation, and tabular chart alternatives are available. Use ⌘K/Ctrl+K to open search.

## Discovered topics and group arcs

Rebuild **Settings & analysis → Build semantic index** after this update to replace earlier filler-word clusters. The new pipeline separates topic discovery from general search: it strips names/handles, English stopwords, chat filler, URLs, and ubiquitous short archive terms; samples substantive conversation passages; and clusters their MiniLM embeddings using UMAP and HDBSCAN. Labels combine document inverse frequency, sublinear term frequency, semantic relevance, and actual contiguous phrases. It does not contain a predefined list of subjects. Ambiguous, sparse, and filler-only messages remain unclassified instead of being forced into the nearest topic.

**Topics & search** shows discovered themes across the full date range, as monthly message counts or share of all authored messages under the same filters. Select a theme for significant conversations ranked by topic-linked messages, participant variety, replies, and reactions, then open the original exchange. Charts show up to 20 leading themes; every discovered theme has its own conversation list.

**Timeline** shows suggested and manual eras as date intervals in a zoomable arc timeline. Suggestions follow changes in weekly topic mix and distinctive vocabulary, including short busy periods, and retain supporting message IDs. Sparse weeks and long gaps do not receive invented chapters. Suggestions use descriptive theme labels rather than claiming to know real-world events absent from the messages; the existing optional cloud narrative workflow can provide reviewed, cited descriptions. Add/edit/split/merge/delete eras as before. Manual edits survive rebuilding, and dismissed automatic suggestions stay dismissed for the same observed boundary.

The representation follows [BERTopic's embedding/clustering and weighting approach](https://maartengr.github.io/BERTopic/algorithm/algorithm.html), with extra filtering for chat data. Automatically inferred topics, assignments, and boundaries are interpretations to inspect, not guaranteed classifications. Full-archive clustering and embedding can take longer than browsing; progress, cancellation, and retry remain available in Settings.

## Semantic topic rankings

1. Build (or rebuild) the local semantic index under **Settings & analysis**. Ranking requires the newer index that embeds every nonempty authored message individually, including short messages; conversation passages remain available for ordinary semantic search.
2. In **Words & phrases**, choose **Semantic meaning**, enter a topic such as `girls` or a more specific description like `dating, crushes, and romantic relationships`, and click **Explore**, then **Analyze meaning**.
3. Compare **Per 1,000 messages** or **Matching messages**. The default minimum is 20 authored messages per member, adjustable down to one. Date/member/era filters apply equally to matches and denominators; matching counts in the summary include members below the leaderboard's sample threshold.

A background job compares the query against every individual-message embedding, not just the nearest search hits. Long-message chunks count once using their highest similarity; surrounding speakers get no inferred credit. All ordinary messages, including attachment-only messages, count in the denominator. Reactions, system events, OCR, and transcripts do not. Empty filtered selections display no rate. Cosine similarity is an approximate relevance measure, not a probability or a guaranteed topic classification; inspect the matches and adjust the default 0.35 cutoff to suit your topic.

Results are cached per query, cutoff, and archive revision in the workspace. Changing shared filters or minimum sample size reuses the cache; changing the topic or cutoff requires a new comparison. Jobs support progress, cancellation, retry, and restart recovery in Settings. An archive refresh invalidates the index and cached rankings until the index is rebuilt. This works locally without cloud credentials.

## Optional cloud narratives

In Settings, choose your Responses-compatible OpenAI model, save a key, and explicitly enable cloud processing for that workspace. Each generated era/lore/recap/answer shows its proposed scope and approximate input/output token allowance before you submit it. Only selected message excerpts, display names, statistics, and candidate annotations are sent. Model outputs are validated structured JSON with resolvable message IDs, cached by archive revision, and recorded with token usage.

Common numerical questions use approved local SQL aggregates. Other answers use retrieved evidence; insufficient evidence is an explicit result. The provider has no tools, file access, generated SQL execution, or external actions. Text within messages is treated as untrusted data. The cloud adapter has been validated with mock Responses payloads; live provider behavior and account/model availability depend on your configuration.

## Development and validation

```sh
.venv/bin/pip install -e '.[dev,analysis]'
GCAPP_DATA_DIR=/tmp/gcapp-dev .venv/bin/python -m gcapp.cli serve
# In a second terminal:
npm run dev
# Regenerate the client contract from the running API:
npm run types

.venv/bin/pytest -q
.venv/bin/ruff check gcapp tests scripts
cargo test --locked --manifest-path importer/Cargo.toml
npm run build
npx playwright install chromium
npm test
```

Browser tests create/use a synthetic demo. The test servers use `/tmp/gcapp-e2e` when no server already exists; a running development server is reused, so point it at synthetic data. No fixtures contain real chat history or credentials. The Rust integration test constructs Apple's schema and uses a fictional typedstream body fixture.

The million-message fixture benchmark is reproducible with:

```sh
.venv/bin/python scripts/benchmark.py --report docs/benchmark.json
```

On the available Apple Silicon Mac, a million messages used a 383 MB SQLite archive; overview took 99 ms cold / 3 ms warm, filtered member overview 23 ms / 1 ms, and keyword search 392 ms / 178 ms. Uncached whole-history word counting took 416 ms, with revision-cached repeats below 1 ms. Peak benchmark process memory was 38 MB. See [the measured report](docs/benchmark.json). This measures indexed text/analytics, not million-message model inference, media throughput, or total frontend/browser memory. Actual semantic paraphrase retrieval is separately validated on the 6,947-message demo: 1.3 seconds for the first search after model loading and 17 ms warm. A cached index rebuild made zero embedding inference calls. Vision OCR, CLIP, and Whisper were also exercised on fictional media; see [model validation](docs/model-validation.json).

See [architecture and API notes](docs/architecture.md) and [contributing](CONTRIBUTING.md).

## Capability boundaries

“Entire history” means the records available in your supplied database. Deleted/absent messages, unavailable reaction history, and undownloaded attachments cannot be recovered. Tapback current state is reconstructed from observed add/remove/change records; complete historical giver activity may not exist in Apple's archive. Retained old messages are not silently deleted when absent from a later source snapshot.

macOS is the initial host. Original Unicode is retained; language models and word variants are English-first. Local era/lore labels are heuristic suggestions, not factual event classifications or diagnoses. Topic clustering is bounded to a reproducible reservoir of up to 20,000 passages, then assigns other passages to learned centroids. Some rich app payloads remain preserved raw rather than fully decoded into dedicated UI widgets. Reply-tree display is capped at 1,000 records; gallery results at 300 per selection. Media analysis records per-file errors so unsupported formats do not disappear.

Jobs persist and retry after restart. Completed embedding batches and media files are cached; cancelled/restarted semantic jobs reconstruct their index from those caches. A cancelled initial import requires discovering the source again because its temporary full database snapshot is removed. Browsing can continue during analysis through SQLite WAL; annotation writes may wait for an active analysis transaction. First inference/model download and a full archive analysis can take much longer than interactive searches. Live cloud calls and a million-message semantic/media run have not been performance-qualified.
