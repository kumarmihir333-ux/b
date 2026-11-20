# M11 AI Architecture

## Prototype

`index.html`, `styles.css`, `motion.css`, `signals.css`, and `app.js` form the browser interface. `server.py` is a dependency-free local HTTP service. SQLite stores the ontology records (`State`, `District`, `Source`, `Dataset`, `IndicatorObservation`, `NewsStory`, `Scheme`, `Project`, and `Department`), their source-backed relationships, observations, human review decisions, feed history, and report drafts.

The service seeds Bihar's official district directory and a dated DES Data Lab state-indicator snapshot. District-level values are not seeded; import a sourced CSV through **Data catalog**, then approve its rows in **Review & alerts** before they appear on district profiles. RSS/Atom feed metadata is captured into the same source model; the starter set includes a Hindustan Times Patna feed, the Bihar DES portal, the Government district directory, and Bihar Chief Minister press releases. RSS feeds refresh on page entry, by manual action, and every five minutes while **Signals & archive** is open.

The browser still stores only selected document-upload file names and approximate sizes in local storage; document contents are not read or transmitted. The source service stores publisher feed headlines and excerpts, not full article pages. History starts at first capture and is limited by each publisher's feed window. The service binds to `127.0.0.1` by default and has no user authentication. It is a local single-user MVP; GitHub Pages can host the static interface, but cannot run its Python API or retain its SQLite archive.

## World-model path

The Event Analysis workspace can export a versioned `m11.world_model.event_assessment` JSON record. It separates event scope, candidate entities, source-linked claims, typed relationships, analyst hypotheses, working notes, review status, and malformed rows requiring review. Unresolved entity identities and unverified claims are explicitly marked. The contract is published as `world-model-event.schema.json` and can evolve by schema version.

This export is a future integration boundary, not yet a shared or automatically updated world model. Draft worksheets stay in browser storage; the event JSON is user-downloaded. Pattern scans remain in local SQLite and are not yet linked to event records or graph entities. A production model should ingest only reviewed records, maintain stable entity identifiers with a human-reviewed resolution process, preserve time ranges and source lineage, version corrections instead of overwriting history, and keep observed claims separate from hypotheses and derived links. Add authenticated event APIs and an append-only audit trail before multi-user or public deployment.

## Proposed production shape

```text
Public web app ──> API ──> public document store / index
                       ├─> verified public data store
                       └─> AI orchestration and retrieval

Private web app ─> authenticated API ─> private document store / index
                                      └> role and project permissions
```

Use one server-side API as the trust boundary. Public retrieval must only query public collections. Private retrieval must require authenticated identity and an authorization check at every request. Never rely on a hidden menu or frontend filter to protect private data.

## Suggested implementation stack

- Frontend: maintainable responsive web app; the prototype can be migrated into React or another framework if the product needs richer routing.
- API: Python with FastAPI.
- Relational data: PostgreSQL for users, document metadata, source records, projects, and audit events.
- Retrieval: object storage for originals; an extraction and chunking pipeline with page metadata; PostgreSQL with pgvector for embeddings.
- AI: Gemini or OpenAI called only by the server using environment managed credentials.
- Hosting: Render or another managed host with private environment variables and managed PostgreSQL.

## Retrieval and citations

For each source, retain its title, publisher, publication date, URL or upload provenance, and reporting year where available. Extract text with page boundaries, store page numbers on chunks, and retrieve only from the caller's authorized collection. The answer API should return claims with document identifiers and page numbers. If retrieval finds no relevant evidence, the assistant should say so. Validate all citations against stored chunks before returning an answer.

Treat uploaded text as untrusted data, never as instructions to the assistant. Keep system instructions separate from retrieved content, limit tool access, and require explicit confirmation for external actions.

## Secrets and configuration

Copy `.env.example` to `.env` for local server development. Keep `.env` out of version control. Do not put AI provider keys in browser code. Before enabling private workspaces, add server-side authentication, role based authorization, separate public and private storage/index namespaces, upload validation, rate limits, and audit logging that excludes document contents and secrets.
