# M11 AI Roadmap

## Stage 1 — Product preview (implemented)

- Establish the M11 AI visual identity and responsive public workspace.
- Lay out Research, Source Library, Development Data, Policy Studio, Monitor, Report Studio, and Private Workspace.
- Add the Signals & archive workspace with configurable RSS/Atom feeds, a SQLite metadata archive, search, and a source-to-headline map.
- Seed an official Bihar district reference and a dated, source-linked DES state-indicator snapshot.
- Add CSV district-data import, pending-review approvals, ontology relationships, workflow alerts, and evidence-linked Markdown drafts.
- Make source and data availability explicit; show no invented statistics or citations.
- Provide a local-only upload selection preview and clear connection status.

## Stage 2 — Secure shared data service (partially implemented)

- The local Python API, SQLite schema, health endpoint, and loopback default are implemented.
- Move multi-user deployments to PostgreSQL and persistent object storage.
- Add authenticated user, analyst, reviewer, and administrator roles before enabling private collections.
- Add backups, retention, and migration tooling.

## Stage 2 — Backend foundation

- Add API service, PostgreSQL schema, migrations, environment configuration, and health endpoint.
- Add validated uploads and separate public/private object storage paths.
- Add secure authentication and server-side role and project permissions before private content.

## Stage 3 — First working milestone

- Parse uploaded PDF and DOCX while preserving page references.
- Index document chunks and retrieve relevant passages for a question.
- Integrate one AI provider server-side and return answers with verified title and page citations.
- Add upload, retrieval, authorization, and citation tests.

## Stage 4 — Public research and data

- Add curated public source records with provenance and publication dates.
- Expand the manual CSV connector into scheduled, publisher-authorized connectors for Bihar district indicators.
- Add filters, comparisons, and clearly labeled visualizations.

## Stage 5 — Policy, monitoring, and reports

- Add policy comparison and evidence linked briefs.
- Add opt-in trusted feeds and scheduled monitoring with source URLs and dates.
- Add report editing, human review, and DOCX/PDF export.

## Stage 6 — Production readiness

- Complete security review, accessibility checks, Hindi localization, observability, backups, and deployment configuration.
- Confirm that public requests cannot retrieve private documents and that citations resolve to the right source pages.
