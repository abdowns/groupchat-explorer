# Architecture and interfaces

React/TypeScript + Vite + Tailwind provide the local browser UI. TanStack Query handles requests/cache invalidation; TanStack Virtual renders large conversation lists. ECharts drives interactive SVG charts with data-table alternatives. Generated OpenAPI types cover messages, members, workspaces and typed request contracts in `src/api.generated.ts`.

FastAPI serves `/api/v1` and the built frontend on loopback port 8765. Mutations require the ephemeral local session token from `/api/v1/config`. Host/origin validation rejects foreign browser origins and cross-site requests. Attachment routes resolve validated workspace/attachment IDs from the application database; active HTML/SVG is served as a download. No arbitrary path endpoint is exposed.

The GPL Rust CLI reads only a consistent backup snapshot through `imessage-database` 4.3.0 and emits NDJSON `schema_version: 1` records for groups, messages, reactions, and diagnostics. Original GUIDs, source row/chat IDs, message parts, edit histories, replies, service metadata, and available rich payloads are retained. Group discovery precedes selected-thread analysis.

## Storage

The global `registry.sqlite` stores workspaces, transient import snapshots, and persistent jobs. Each workspace has its own `archive.sqlite` in WAL mode, including:

| Source layer | Derived layer |
|---|---|
| `people`, `messages`, `message_threads`, `attachments`, `links` | `sessions`, `daily`, `person_stats` |
| `reaction_events`, `reaction_observations`, `reaction_presence` | current `reactions`, message reaction counts |
| message GUID/source IDs/parts/edits/raw | `passages`, `topics`, `eras`, `events`, `lore` |
| FTS5 maintained by message triggers | `artifacts`, `usage`, versioned annotations |

SQLite schema migrations are applied through `PRAGMA user_version`. Source upserts compare stable GUID/raw content and reconcile reaction presence. Changes rebuild affected derived data, increment the archive revision, invalidate stale semantic retrieval and cloud caches, and preserve manual annotations. Cached analytics are keyed by workspace path, archive/semantic revision, timezone, current local day, and filters.

`semantic.hnsw` persists 384-dimensional normalized MiniLM embeddings with passage labels referencing SQLite. Substantive messages and eight-message context passages retain source message mappings and speaker/date information; chunks fit the model input limit. Batch vector files persist across cancellation. A bounded reservoir sample feeds HDBSCAN; topics use c-TF-IDF terms, and unsampled passages are assigned against topic centroids. Keyword/vector rankings combine with reciprocal-rank fusion.

Media caches include image vectors, perceptual hashes, extracted text, resumable annotations, and previews. Extracted text never contributes to authored word/message totals. Shared links are parsed locally without URL fetching.

## Query semantics

All analytical views accept workspace and applicable `start`/`end` (inclusive UTC seconds), `person`, `era`, `topic`, and `session` filters. Daily labels, streaks, and date-input bounds use the configured IANA timezone. Cursor pagination encodes `(timestamp, original GUID)` rather than using increasing offsets.

Ordinary multipart messages count once. System events and reaction records are separate. Reaction averages divide current reactions received by **all** matching target messages, including zeroes. Received reaction dates select target messages; given additions select observed event timestamps. Unresolved targets are visible. Exact replies and inferred sessions are separate relationships. Word normalizations divide by the same-filter authored word total; missing denominators produce null values.

## API map

Interactive OpenAPI documentation: `http://127.0.0.1:8765/docs`.

| Routes under `/api/v1` | Purpose |
|---|---|
| `config`, `workspaces`, `demo` | local configuration, workspace inventory, fictional fixture |
| `imports/discover`, `imports/select`, `workspaces/{id}/jobs (kind: refresh)` | snapshot discovery, explicit selected threads, reconciliation |
| `workspaces/{id}/messages`, `messages/{guid}/context`, `messages/{guid}/thread`, `reaction-targets` | paginated sources, surrounding context, explicit replies, exact reaction evidence |
| `analytics/{overview,reactions,conversations,recap}`, `people/{id}`, `words` | metrics and lexical explorer |
| `timeline`, `eras`, `eras/{id}`, `events`, `lore`, `topics`, `search` | source-linked derived history |
| `media`, `attachments/{id}`, `export.csv` | local attachment gallery/preview and filtered statistics |
| `awards`, `awards/{id}`, `games`, `games/{id}/answer` | custom awards and source-backed games |
| `settings`, `cloud/preview`, `cloud/generate`, `artifacts` | local/cloud controls, proposed evidence scope, validated outputs |
| `jobs`, `jobs/{id}/cancel`, `jobs/{id}/retry`, `jobs/events` | durable progress, cancellation/retry and SSE |

The worker serializes expensive jobs, recovering running jobs to queued on startup. Progress updates are cancellation checkpoints. Exceptions produce explicit failed jobs or per-file media errors. Clients subscribe to SSE for progress/cache invalidation. Cloud generation receives structured evidence, not executable commands; no model-returned SQL or tool actions are permitted.
