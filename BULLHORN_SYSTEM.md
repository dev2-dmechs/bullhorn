# Bullhorn Integration — System Reference

This document explains, end to end, how this codebase talks to Bullhorn: authentication,
every endpoint it calls, what data flows where, what's persisted, what's redacted, and the
known quirks/limitations discovered by testing against the live tenants. It reflects the
code as it stands today, not the original design — where the two differ, the code wins.

For product scope (what's in/out, why decisions were made, client-facing constraints), see
`.claude/CLAUDE.md` and `Bullhorn_POC_Scoping_Response_Revised.md`. This document is the
technical/implementation reference.

## 1. The big picture

Two Bullhorn tenants — **Company A** and **Company B** — belong to the same corporate group
but are separate Bullhorn instances with separate candidate pools. The system:

1. Lets a recruiter in one company search the **other** company's candidates by role
   criteria, and see a redacted result (no candidate PII) with an AI-generated match score.
2. Independently, polls both tenants for newly created job orders and surfaces them in the
   UI (detection only — no matching is wired to this yet).

All Bullhorn access is read-only except two explicitly sanctioned exceptions (résumé parsing,
event subscription create). Candidate PII is fetched and used internally but never persisted
to Postgres, never sent to the browser, and never sent to the AI vendor.

```
┌─────────────┐        ┌──────────────────────┐        ┌─────────────┐
│  Company A  │◄──────►│   FastAPI backend    │◄──────►│  Company B  │
│  Bullhorn   │  REST  │  (LiveBullhornClient) │  REST  │  Bullhorn   │
└─────────────┘        └──────────┬───────────┘        └─────────────┘
                                   │
                        ┌──────────┴───────────┐
                        │      PostgreSQL       │  (no candidate PII, ever)
                        │  companies, taxonomy  │
                        │  caches, job_orders*   │
                        └──────────┬───────────┘
                                   │
                        ┌──────────┴───────────┐
                        │   React frontend      │  (search + jobs pages)
                        └──────────────────────┘
```

## 2. Where the code lives

| Concern | File |
|---|---|
| All Bullhorn HTTP access | `backend/app/bullhorn/live.py` (`LiveBullhornClient`) |
| Candidate search endpoint | `backend/app/routers/candidates.py` |
| Job order polling/sync endpoints | `backend/app/routers/job_orders.py` |
| Taxonomy caches + job schema mapping | `backend/app/routers/companies.py` |
| SQLAlchemy models | `backend/app/models.py` |
| Pydantic request/response schemas | `backend/app/schemas.py` |
| Env/credentials | `backend/app/config.py` |
| AI match client (client construction only) | `backend/app/matching/client.py` |
| Frontend candidate search UI | `frontend/app/routes/search.tsx` |
| Frontend job orders UI | `frontend/app/routes/jobs.tsx` |

**`LiveBullhornClient` is the only thing that ever talks to Bullhorn.** There is no mock
client and no offline mode — every run of this app hits Goodall Brazier's real, live
production Bullhorn tenants.

## 3. Authentication

OAuth 2.0 **password grant**, once per tenant, implemented in `LiveBullhornClient._login()`:

1. `GET /oauth/authorize` (with `client_id`, `username`, `password`, `response_type=code`,
   `action=Login`) — follows Bullhorn's redirect chain (up to `MAX_AUTH_REDIRECTS = 5` hops,
   since it can bounce between regional hosts) until a `code` query param appears.
2. `POST /oauth/token` with that `code` → `access_token`.
3. `GET /rest-services/login?access_token=...` → `BhRestToken` + `restUrl` (the tenant's
   actual data-centre REST endpoint — **never hardcoded**, always taken from this response).

Credentials come from `backend/.env`: `BH_A_CLIENT_ID` / `BH_A_CLIENT_SECRET` /
`BH_A_USERNAME` / `BH_A_PASSWORD`, and the `BH_B_*` equivalents. `Settings.credentials_for()`
looks these up by tenant prefix.

**Token persistence**: `BhRestToken`, `restUrl`, and `token_updated_at` are written to the
`companies` table (`Company.bh_rest_token`, `Company.rest_url`) so a restart doesn't force a
fresh login — Bullhorn rate-limits logins. `_session()` reads the cached token first and
only calls `_login()` if none is cached; on a `401` from any request, `_get`/`_put` transparently
re-login once and retry. Tokens/credentials are never logged or returned in an API response.

**Concurrency note**: `LiveBullhornClient` holds an `asyncio.Lock` (`self._db_lock`) around
every place it touches the shared `AsyncSession` (`_company()`'s read, `_login()`'s commit).
This exists because `search_candidates` fans out concurrent per-candidate work
(`asyncio.gather` over `_redact()`) against one shared client instance — `AsyncSession`/asyncpg
is not safe for concurrent use from multiple coroutines, and this lock is what prevents
`cannot perform operation: another operation is in progress` crashes.

## 4. Read-only, with two narrow exceptions

Rule: **GET only.** Never POST/PUT/PATCH/DELETE against Bullhorn — these are live production
systems. Two explicitly approved, narrowly-scoped exceptions exist:

- **`POST /resume/parseToCandidate`** — résumé parsing. Parse-only; mutates nothing in
  Bullhorn. Used in `parse_resume()`.
- **`PUT /event/subscription/{id}`** — creates/keeps-alive the job-order-poller's entity
  event subscription. See §6.

Do not extend either exception, and do not add new write calls, without the same kind of
explicit sign-off this required.

## 5. Candidate search

### 5.1 Request shape

`CandidateSearchRequest` (`schemas.py`) accepts **both IDs and names** for category, skill,
and business sector filters:

```
category_ids:            list[int]
category_names:          list[str]
skill_ids:                list[int]
skill_names:              list[str]
business_sector_ids:     list[int]
business_sector_names:   list[str]
country_ids:              list[int]
title:                    str | None   # free text, matched against occupation
description:              str | None   # AI-scoring context only, never sent to Bullhorn
limit:                    Literal[10, 20, 30, 40, 50]
```

At least one filter is required (validated in `_at_least_one_filter`).

Two different callers use two different halves of this:

- **Manual search** (`search.tsx`) sends **IDs** — the recruiter picks from dropdowns backed
  by the cached taxonomy tables (§5.2), so the ID is already known.
- **Job-page "Check candidates"** (`jobs.tsx`) sends **names** — a stored `JobOrder` only
  carries category/sector/skill *names* (Bullhorn association `name` fields), never IDs, so
  there's nothing else to send.

`_resolve_taxonomy_ids()` in `candidates.py` merges the two: explicit IDs pass through
unchanged, and names are resolved against the tenant's cached table (case-insensitive exact
match) into IDs, deduped with `dict.fromkeys`. **Bullhorn's own search API only ever supports
filtering by ID** — filtering by name is not a thing Bullhorn does; the name→ID resolution
happens entirely in this codebase before a Bullhorn query is ever built. Names that don't
match any cached entry are logged and skipped (not a fatal error).

### 5.2 Taxonomy caches (why IDs, not names, at the Bullhorn layer)

Confirmed by testing against the live tenant: Bullhorn's candidate `skillSet` field is
populated on ~2% of candidates and is junk when present, and `experience` is `1` on every
record — neither is usable for filtering. **`category` and `businessSectors` are filterable,
but only by ID, not name** — the same trap applies to skills. So three tables cache each
tenant's taxonomy (id ↔ name), refreshed on demand (`?refresh=true` on their list endpoints):

- `business_sectors` — `bh_business_sector_id`, `name`, `date_added`
- `categories` — `bh_category_id`, `name`, `description`, `enabled`, `skills` (int[], the
  skill IDs associated with that category), `specialties` (int[]), `type`, `occupation`
- `skills` — `bh_skill_id`, `name`

These are populated from `GET /query/Category`, `GET /query/BusinessSector`,
`GET /query/Skill` (see `LiveBullhornClient.list_categories/list_business_sectors/list_skills`),
and fully replaced (`delete` then `add_all`) on each refresh — not incrementally merged.

**Specialties do not have an equivalent cache table, endpoint, or Bullhorn candidate-search
filter clause.** `JobOrder.specialties` (names) exists for display, and `Category.specialties`
(IDs) exists as an association on categories, but there is no standalone specialty catalog and
no `specialties.id:(...)` clause in `search_candidates()`. Building that out — a new cache
table, a `/specialties` endpoint, and confirming Bullhorn's `Candidate` entity even supports
filtering by specialty ID — is explicitly deferred, not implemented.

### 5.3 Building the Bullhorn query

`LiveBullhornClient.search_candidates()` builds a Lucene-style query against
`GET search/Candidate`, ANDing together whichever clauses apply:

```
categories.id:(1 OR 2 OR ...)
primarySkills.id:(...)
businessSectors.id:(...)
address.country.id:(...)
occupation:"<escaped title phrase>"
fileAttachments.id:[1 TO 99999999999]     # always appended — only candidates with a CV
```

The candidate must have **at least one filter clause** or the function raises — there is no
"browse all candidates" mode. `fileAttachments.id:[1 TO 99999999999]` is always appended: the
whole point of fetching a candidate is to parse their CV, so candidates without one are
excluded up front.

Fetch is capped at `MAX_CANDIDATES = 50` per match run (non-negotiable — never fetch-then-score
an unbounded set), paginated internally via `start`/`count` until either the cap or Bullhorn's
reported `total` is reached.

`CANDIDATE_SEARCH_FIELDS` requested: `id,categories,businessSectors,owner,status,occupation,
fileAttachments(id,type,name,contentType)`.

### 5.4 Résumé fetch + parse

For each candidate with a file attachment (`find_resume_attachment` prefers one whose `type`
contains "cv"/"resume", else falls back to the first attachment):

1. `GET /file/Candidate/{id}/{fileId}/raw` — the raw file bytes (`download_candidate_file`).
2. `POST /resume/parseToCandidate` (`?format=pdf|doc|docx|rtf|odt|text|html`, inferred from
   the file extension) with the file body — Bullhorn's own résumé parser, returning
   structured fields (skills, experience, etc.) as JSON.

These run concurrently across candidates (`asyncio.Semaphore(RESUME_CONCURRENCY=5)` in
`candidates.py`, so at most 5 in flight at once).

**A single candidate's résumé fetch/parse failure (bad file, Bullhorn 4xx/5xx, etc.) is
caught in `_redact()` and logged — that candidate is returned with `resume=None` rather than
failing the whole search.** This is deliberate: `asyncio.gather` doesn't cancel sibling tasks
when one raises, so letting a per-candidate failure propagate risked leaving other concurrent
`_redact()` calls still running against the request's `AsyncSession` after FastAPI had already
started tearing it down — the actual cause of an earlier `InterfaceError: cannot perform
operation: another operation is in progress` crash.

### 5.5 Redaction — the PII boundary

`_redact()` in `candidates.py` turns a raw Bullhorn candidate dict into an
`AnonymisedCandidate` — the **only** shape this endpoint ever returns. It carries:
`external_id`, `company_id`, `title` (occupation), `category`, `business_sector`,
`owner_name`, `resume` (parsed CV — see below), `match` (score, once AI matching populates it).

**No name, email, phone, address, or raw CV text is in this schema.** The full raw Bullhorn
record (including PII) exists only transiently, in memory, for the duration of one request —
it is never written to Postgres and never appears in any response body. This is the
system's core guarantee: it fetches and holds full records (it has to, to parse a CV and
score a match) but only ever *displays* the redacted shape.

`resume.parsed` — the parsed CV structure — **is** included in `AnonymisedCandidate.resume`
and does flow to the frontend today. Whether that's consistent with "no CV text to the
browser" depends on how much PII the Bullhorn parser's structured output actually retains;
this is worth reviewing against the PII rules before a client demo (see CLAUDE.md's "There
are no tests" section — this exact boundary has no automated check yet).

### 5.6 AI match scoring

`score_candidate_matches()` (`app/matching/client.py`) — despite CLAUDE.md's framing that
"only client construction exists," **this is fully implemented**: it batches candidates
(`MATCH_CHUNK_SIZE = 10` per OpenAI call, chunks run concurrently, never one call per
candidate), sends `role_requirements` (category/business_sector/skill/country IDs, title,
description — never PII) plus each candidate's `resume.parsed` and `candidate_id`, and gets
back structured `MatchScore` (`score`, `skills_score`, `experience_score`, `fit_score`,
`reasons: list[str]`) via `client.responses.parse(text_format=MatchScoreBatchResult)`.

**Note**: each candidate's full parsed résumé is sent to OpenAI as-is — an explicit, narrow
exception to "PII does not leave for the AI vendor," confirmed for this call specifically
(see the docstring on `score_candidate_matches`). This is a deliberate deviation from the
rule-5 allowlist (skills/titles/experience/sector only) that governs everything else.

Scores are **not cached anywhere** — every search re-runs the AI call. (CLAUDE.md describes a
`match_results` cache-by-row design; that table does not exist in `models.py` today — this is
a gap between the documented target and current code.)

## 6. Job order detection (simulated auto-match, detection half only)

**Only detects new job orders — does not run matching against them.** Wiring detection to
matching is explicitly out of scope until separately greenlit.

### 6.1 Mechanism: Bullhorn Entity Events, not polling by scan

Originally a full `JobOrder` id scan diffed against a "seen" table. Now uses Bullhorn's
Entity Events subscription API instead — one subscription per tenant, named
`job-order-poller-{company_id}`:

- `ensure_job_order_subscription()` — `PUT /event/subscription/{id}?type=entity&names=
  JobOrder&eventTypes=INSERTED`. **`PUT` is create-once, not an idempotent upsert** (undocumented,
  discovered by testing): a repeat `PUT` returns `400 "already exists"`, which this method
  treats as success, not an error.
- `poll_job_order_events()` — `GET /event/subscription/{id}?maxEvents=100`, draining the
  queue. Filters for `entityName == "JobOrder"` and **`entityEventType == "INSERTED"`**
  (not `eventType` — that field is always `"ENTITY"` for entity events; the INSERTED/
  UPDATED/DELETED value lives in `entityEventType`. A previous version of this filter checked
  the wrong field and silently always returned nothing).

Known, accepted tradeoffs of this model:
- **No history before subscription creation** — a fresh subscription reports nothing
  retroactively (the old full-scan approach didn't have this gap).
- **Draining consumes the queue** — a crash between draining and finishing `job_orders_seen`
  inserts loses that batch. `job_orders_seen` is still checked defensively per drained id as a
  second dedup layer, but can't recover events that were never drained.
- **Subscriptions silently expire** if not polled often enough — mitigated by the 60s poll
  interval and `ensure_job_order_subscription`'s create-if-missing recovery.
- **Events carry no field-level detail** — every `INSERTED` id still needs a full `JobOrder`
  fetch (`list_job_orders_by_ids`) to get displayable fields.

### 6.2 The poller loop

`app/main.py`'s `lifespan` starts one `asyncio.create_task(job_orders.poll_loop())` — an
in-process loop, cancelled cleanly on shutdown. **No webhooks** (Bullhorn never pushes to this
app), **no external scheduler** (no APScheduler/cron/separate process — deliberately, per the
"no infra tooling" rule). `poll_loop()` iterates both `POLL_COMPANY_IDS = ("A", "B")` every
`POLL_INTERVAL_SECONDS = 60`, calling `_check_and_record()` for each, independently — job
orders from A and B are never merged into one feed.

`_check_and_record()`:
1. `ensure_job_order_subscription()`
2. `poll_job_order_events()` → list of `JobOrder` ids
3. Diff against `job_orders_seen` (per-tenant dedup table: `company_id`, `bh_job_order_id`,
   `first_seen_at`)
4. `list_job_orders_by_ids()` for the unseen ones → `_store_job_orders()` (upsert into
   `job_orders`) → insert into `job_orders_seen` → commit.

Results accumulate in an **in-memory, per-company feed** (`_feeds: dict[str, list[JobOrderSchema]]`,
capped at `MAX_FEED_SIZE = 500`, oldest dropped) — this is not the same as the `job_orders`
table; it's what `GET /job-orders/{company_id}/new` returns for the frontend's "new since I
last looked" badge. It resets on backend restart; the `job_orders` table does not.

### 6.3 Persistence

`job_orders` table (JSONB `data` column, keyed `(company_id, bh_job_order_id)`) holds the
**full raw Bullhorn `JobOrder` dict** — upserted both by the poller and by
`POST /job-orders/{company_id}/sync` (a manual "fetch the latest N now" action, using
`list_latest_jobs()` instead of the event feed). `GET /job-orders/{company_id}/stored` reads
this back through `to_job_schema()`. Job orders are **not candidate PII** (rule 1 doesn't
apply to them), so persisting the full record here is fine.

### 6.4 The `/query/JobOrder` count-cap quirk

Confirmed live, undocumented: **Bullhorn silently caps `count` on `/query/JobOrder` based on
how many to-many associations are in `fields`** — roughly `floor(200 / num_to_many_associations)`.
Requesting `count=100` with ~20 to-many associations actually returned only 10 rows, no error.
`JOB_ORDER_FIELDS` only requests four (`categories`, `businessSectors`, `skills`,
`specialties` — the ones the app displays), giving a real ceiling of ~50
(`floor(200/4)`). **`MAX_JOB_ORDERS` (this app's own upper bound on the `count` query param)
does not reflect this** — a caller can request `count=100` and still only get 50 back. Adding
a fifth to-many association would lower the real ceiling further.

## 7. Database schema (six tables, no Alembic)

`create_all()` runs at startup (`init_db` in `database.py`) — **there is no migration
tool.** This only ever *creates a missing table*; it will never *alter* an existing one. If a
column changes on a table that already exists, the running database silently keeps the old
shape and the app breaks at query time, not startup. Fix: drop the table, let startup rebuild
it (fine here — nothing in these six tables is candidate PII, so there's nothing irreplaceable
to lose by dropping and re-syncing).

| Table | Purpose |
|---|---|
| `companies` | Tenant config + persisted OAuth token state |
| `business_sectors`, `categories`, `skills` | Per-tenant taxonomy caches (id ↔ name), §5.2 |
| `job_orders_seen` | External `JobOrder` ids already reported, dedup for the poller |
| `job_orders` | Full raw `JobOrder` JSONB per tenant, from sync/poll |

**None of these hold candidate PII.** The two tables the matching phase will eventually need
(`match_runs`, `match_results` — role requirements + trigger type, and per-candidate scores/
reasons) do not exist yet.

## 8. API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/companies/{id}/connection` | Bullhorn connectivity/token status check |
| `GET` | `/companies/{id}/business-sectors?refresh=` | Cached (or refreshed) business sectors |
| `GET` | `/companies/{id}/categories?refresh=` | Cached (or refreshed) categories |
| `GET` | `/companies/{id}/skills?refresh=` | Cached (or refreshed) skills |
| `GET` | `/companies/{id}/countries` | Live country options (not cached) |
| `GET` | `/companies/{id}/jobs?count=` | Ad-hoc live job order fetch (not persisted) |
| `POST` | `/search/{id}/candidates/search` | The manual/job-page candidate search + AI scoring |
| `POST` | `/job-orders/{id}/check-new` | Manually trigger one poll cycle for a tenant |
| `GET` | `/job-orders/{id}/new` | In-memory "new since last checked" feed |
| `POST` | `/job-orders/{id}/sync` | Fetch latest N job orders now, upsert into `job_orders` |
| `GET` | `/job-orders/{id}/stored` | Read back everything persisted in `job_orders` |
| `GET` | `/health` | Liveness |

All `{id}` path params are `"A"` or `"B"`, validated/uppercased per-router.

## 9. Frontend integration points

- `search.tsx` — manual search: recruiter picks a tenant to search (`otherCompany()` of
  whoever's "logged in"), builds `CandidateSearchRequest` with **IDs** from
  category/business-sector/skill multi-selects (backed by `useCategories`/
  `useBusinessSectors`/`useSkills`, which hit the cached-taxonomy endpoints above).
- `jobs.tsx` — per-tenant job order table + "Check candidates" per row, which builds a
  `CandidateSearchRequest` from the job's stored **names** (`category_names`,
  `business_sector_names`, `skill_names`, plus `country_ids` from the job's address and
  `title`/`description` for AI-scoring context).
- Both search results and the job-page candidate popup share one `CandidateDetailModal`
  component (`app/components/CandidateDetailModal.tsx`) for the redacted candidate detail view.
- API types are generated (`npm run gen:api` → `openapi-typescript` against the running
  backend's `/openapi.json` → `app/api/schema.d.ts`) — never hand-written.

## 10. Known gaps / things not to assume are done

- No automated test proving the PII boundary holds (no test suite exists at all — see
  CLAUDE.md's "There are no tests" section).
- `AnonymisedCandidate.resume.parsed` reaches the frontend; whether the Bullhorn-parsed CV
  structure itself can carry re-identifying content hasn't been explicitly audited.
- No match-score cache (`match_runs`/`match_results` tables don't exist) — every search
  re-bills the OpenAI call, including re-renders.
- Specialties have no cache table, endpoint, or Bullhorn-side filter — deferred.
- Stray `print()` debug statements remain in `live.py` (`poll_job_order_events`,
  `search_candidates`) and `job_orders.py` (`_check_and_record`) — noisy but harmless; not yet
  cleaned up.
