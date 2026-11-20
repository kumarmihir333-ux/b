# M11 AI

M11 AI is a public-facing prototype for Bihar development intelligence, designed for BRaiN Foundation. It provides a responsive workspace shell for research, source management, development data, policy analysis, monitoring, and report drafting.

## Run locally

Run the local app with Python 3.10 or newer. No third-party packages are required:

```powershell
python server.py
```

Then open <http://localhost:8000>. The first run creates `data/m11.db`, seeds Bihar's 38-district reference directory and a dated DES Data Lab state snapshot, and adds starter source records. In **B11 source monitor**, add public publisher homepages or RSS/Atom feed URLs, then run a scan to collect recent items. B11 tries RSS/Atom autodiscovery when given a homepage and checks only the sources you register. Connected feeds refresh every five minutes while that page is open. The SQLite archive persists on this computer.

The **Development data** page shows sourced state indicators and a district coverage grid. To add district measures, download an authorized CSV from a publisher, then use **Data catalog → Import a district dataset**. Required columns are `district`, `indicator`, and `value`; `unit`, `period`, `source_page`, `scheme`, `project`, and `department` can add metadata and relationships. Imported rows stay out of dashboards until a human approves them in **Review & alerts**. **Pattern engine** offers five selectable timeline scans: drop–consolidation–rise, spike and reversal, sustained trend, lasting level shift, and volatility change. The match window is highlighted and each result states the heuristic rule that triggered it. News mode counts keyword matches by week and is only a feed-coverage proxy, not social-media monitoring or evidence of causation. **Event analysis** provides a guided worksheet for feedback loops, system cycles, fragility and tail risks, competing hypotheses, source checks, assumptions, and confidence. Its versioned world-model JSON export separates event records, entities, evidence claims, relationships, hypotheses, and analyst notes; unverified items and malformed rows remain marked for review. The schema is published in `world-model-event.schema.json`. Draft saving stays in browser storage. **Ontology graph** shows approved relationships, and **Report studio** generates downloadable Markdown drafts from approved observations and captured headlines.

B11 reads registered public RSS/Atom feeds, including feeds discovered from publisher homepage metadata. It stores publisher-provided headlines, excerpts, publication dates, and source links. It does not crawl whole sites, bypass access controls, or scrape and copy full newspaper articles. The archive begins when you first capture a feed; it cannot recover older items the publisher has already removed from its feed.

## Deploy on GitHub Pages

**Opportunity & Risk Radar** scans approved district observations for robust deviations from the prior four-period median. Its transparent 8-point matrix scores magnitude, persistence, district breadth, and linked source coverage; scores of 6+ are pinned. Indicators default to neutral and only receive opportunity/concern labels when the dataset explicitly supplies `signal_direction`. These locally stored pins are review leads, not verified events, predictions, or public alerts.

The repository includes a GitHub Actions workflow that publishes the static site whenever you push to `main` or `master`. It publishes only the required HTML, CSS, and JavaScript assets.

1. Create a GitHub repository and push this project to its `main` or `master` branch.
2. In the repository, open **Settings → Pages** and set the build and deployment source to **GitHub Actions**.
3. Push a commit, or run **Deploy M11 AI to GitHub Pages** from the **Actions** tab.
4. Open the site URL shown in the workflow deployment summary or under **Settings → Pages**.

GitHub Pages publishes the static interface only. The live source registry and archive require the Python service and a persistent SQLite data folder; they will show a clear disconnected state on GitHub Pages alone. Do not expose the current unauthenticated local service to the public internet. A public deployment needs authentication, a persistent database, and additional operational security.

## Current scope

- Responsive English language workspace and module navigation.
- Cinematic dark interface, layered mesh artwork, restrained hover motion, pointer tilt, and reduced-motion support.
- Signals & archive: RSS/Atom refresh, source registry, search, recent coverage, older captures, and source-to-headline map.
- Bihar ontology, official district reference, dated DES state indicators, CSV dataset intake, review workflow, source-lineage graph, and evidence-linked Markdown drafts.
- Local SQLite history for datasets, reviewed indicator observations, publisher feed metadata, relationships, and report drafts.
- Local source list. File names and sizes are saved in browser local storage; document contents are not read or uploaded.
- Research assistant interaction that explains when the answer service is not connected. It does not invent findings or citations.
- District data remains empty until verified source rows are imported. No values are estimated or copied from state totals into districts.
- Private workspace remains unavailable until authentication and access controls exist.

## Not connected yet

There are no user accounts, private workspace, AI provider, document parsing, semantic search, policy-document comparison, live DES API connector, automated PDF/XLS ingestion, or full-page newspaper archive. State indicator values are a dated official snapshot; district values require sourced CSV import. B11 currently scans only registered RSS/Atom sources; a publisher homepage works only when it advertises a feed. The source service is local and is not a public production service.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the proposed production boundaries and [ROADMAP.md](ROADMAP.md) for staged implementation.
