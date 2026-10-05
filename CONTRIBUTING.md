# Contributing

Contributions are licensed GPL-3.0-only. Keep fixtures entirely fictional. Do not add Messages databases, attachments from real conversations, API keys, generated personal recaps, or vector indexes to the repository. Runtime workspaces belong outside the checkout.

Use Python 3.12, Node 22+, and current stable Rust. Follow the setup and validation commands in README. Changes to metrics need independently hand-calculated fixtures, including zero counts and shared filters. Import changes need idempotent refresh coverage and provenance checks. API schema changes require regenerating `src/api.generated.ts`. Browser workflows should open actual supporting messages and exercise empty/error states.

Model changes should document model/version, input limits, download size/licensing, invalidation behavior, and bounded memory. Cite source message IDs in all generated claims; preserve manual annotations. Avoid network access to stored shared URLs and keep cloud processing disabled by default.

The `tests/fixtures/attributed-body.bin` archive was generated from fictional text by `tests/fixtures/make-body.m`; it is safe to publish. Benchmark fixtures are created temporarily and removed by the benchmark script. New macOS schema variants should be tested against synthetic database rows rather than committing private archives.
