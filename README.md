# Recall Watch

Safety checks for baby gear, for parenting creators. Before you post, search a product and get a cited safety note
(CPSC recalls, CPSC warnings, lawsuits and complaints labeled as allegations). After you post, Recall Watch keeps checking
every product you linked and drafts the follow-up post when something gets flagged.

Flask + SQLite backend, React + TypeScript frontend, You.com for live web research, Claude for synthesis.
Full spec: `recall-watch-prd.md` (kept in the Creator Hackathon project).

## Run it (Replit or local)

1. Add secrets `YDC_API_KEY` and `ANTHROPIC_API_KEY` (Replit: Secrets tab). Without both keys the app runs in **demo mode**
   with a visible banner.
2. `bash start.sh` (installs and builds the frontend if `web/dist` is missing). Open the preview.
   Local dev: `pip install -r requirements.txt`, `cd web && npm install && npm run dev` (proxies `/api` to port 8000), and in
   another terminal `gunicorn -k gthread --threads 16 -b 127.0.0.1:8000 server.app:app`.

## Do this first: M0 smoke test (nothing here has been called live yet)

The build sandbox could not reach You.com or saferproducts.gov, so the integrations were written from You.com's published
OpenAPI specs and the CPSC web-services guide and tested only against fakes. Run:

```
python -m server.cli smoke
```

It makes one real call each to CPSC, You.com Search, Extract, Research and Claude and prints OK or FAIL per step.
**Unverified assumption to check first:** the CPSC JSON field names in `server/cpsc.py` (`RecallNumber`, `RecallDate`, `Title`,
`URL`, `Products[Name,Model]`, `Hazards`, `Remedies`...). If the CPSC call fails or returns different keys, fix `normalize()`.
Every failure degrades to a visible gap or an `unverified` verdict, never to a false "no issues found".

## Record real demo data (after smoke passes)

```
python -m server.cli record check "AirClub Convertible Bassinet"
python -m server.cli record check "CooCooBaby Baby Lounger"
python -m server.cli record followup "AirClub Convertible Bassinet"
python -m server.cli record search bassinet
```

Recorded checks are marked `_recorded: true`, which changes the demo banner to "Replaying a saved live run". The fixtures
shipped here are hand-assembled from public CPSC notices (labeled "Demo data: not a live check") so the demo works offline.
Also live-test your third demo product: the default `Graco Pack 'n Play Playard` is **not** confirmed clean. Set
`DEMO_CLEAN_PRODUCT` to whatever returns `no_issues_found` live.

## How You.com is used

| Endpoint | Used for | Where |
|---|---|---|
| `POST ydc-index.io/v1/search` | Product search for the Add flow (boosting retail domains); CPSC.gov search (`include_domains: ["cpsc.gov"]`) to catch recalls and unilateral warnings that are not in the recall database; web search for lawsuits and parent complaints (`freshness: year`) | `youcom.search`, `checks.run_check`, `products.search` |
| `POST ydc-index.io/v1/extract` | Reads a pasted product link so the brand/model can be identified | `checks.identify` |
| `POST api.you.com/v1/research` | Cited research summary per product (effort `lite`, 60 s cap) | `checks.run_check` |

Auth is the `X-API-Key` header. The CPSC recall database (public, no key) is queried alongside.

## Trust rules (enforced in code, covered by tests)

- The verdict is **computed in code** from validated evidence. Any verdict the model returns is ignored.
- Every citation must point at a URL that was actually retrieved; invented sources are dropped.
- Lawsuits and complaints are labeled **ALLEGATION** and can only raise a product to "Use caution".
- "Do not recommend" requires a confirmed official recall or CPSC warning. Possible matches are "Use caution".
- If both official sources (CPSC database and cpsc.gov search) are unreachable, the verdict is **"Couldn't complete the check"**,
  never "No recalls or warnings found", and that result is not cached.
- Flagged products get no review or pitch drafts. Caution and incomplete results need an explicit "I've read the safety note".
- Follow-up drafts say "recalled" only when backed by a confirmed official action. Retrieved web text is treated as untrusted data.

## Layout

```
server/   Flask app (app, jobs, checks, drafts, products, youcom, cpsc, llm, demo, store, db, cli), fixtures/, tests/
web/      Vite + React + TypeScript (src/pages: Search, List, Watching), prebuilt in web/dist
data/     SQLite database (created on first run)
```

Checks run on a background pool (3 at a time) with a separate inner pool for parallel source gathers; the UI polls
`GET /api/items` every 1.5 s while anything is queued, checking or drafting. Interrupted checks are re-queued on startup.

## Tests

```
python -m pytest server/tests -q     # 31 backend tests, all externals faked
cd web && npm run typecheck && npm run build
```

## Deploying on Replit

Use the workspace Run button and the dev URL for the demo (it stays up while the tab is open). Autoscale publishing works but
its filesystem is not durable, so the SQLite data can reset: use **Demo tools > Load demo list** to restore the demo state.
A Reserved VM keeps the database.

## Known gaps (P1/P2, not built)

Search results are cleaned titles from You.com (no Claude normalization into brand/model yet); the `pre_flag` chip comes from
fixtures only (no local recent-recall index); scheduled daily re-checks; sponsor-pitch brand lookup (pitches are generic,
no invented contacts); the app never emails or posts anything for you.
