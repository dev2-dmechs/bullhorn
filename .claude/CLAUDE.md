# Bullhorn Cross-Company Search & Match — POC

Proves that candidates held in one company's Bullhorn tenant can be matched to vacancies
in another company in the group, with AI producing a ranked shortlist and a confidence
score per candidate — while candidate PII stays hidden across the company boundary.

Client: Goodall Brazier. Two Bullhorn tenants (Company A, Company B).
This is a focused demonstration, not a platform. Production is a separate, later phase.

## ⚠️ CURRENT SCOPE — read this before anything else
**Manual search, plus vacancy polling (detection only).** A recruiter picks a tenant, enters
role requirements, and gets back candidates from that tenant with their PII redacted.
Separately (added to scope 2026-07-21), a manually-triggered "check for new vacancies"
action polls Company A's Bullhorn for `JobOrder`s and reports which ones are new — it does
**not** run matching against them.

**In scope as of 2026-07-21:** the detection half of the simulated auto-match — `JobOrder`
fetched by `dateAdded`, dedup via the `vacancies_seen` table. Originally manual-trigger-only;
**reversed later the same day** to an in-process backend poller (see below) at the user's
explicit request, after being told this contradicts the "no schedulers" rule below.

**Out of scope right now — do not build, do not "prepare for":**
- Running AI matching/scoring against newly-detected vacancies
- AI matching and scoring generally (prompts, `score` / `reasons`, matching endpoints,
  `match_runs`, `match_results`)

The sections below still describe the full auto-match flow (detection *and* matching)
because that is the eventual target and the scoping document promises it. Only the
detection half is built now. If a task seems to need the matching half, it is out of
scope — stop and ask.

**One deliberate, narrow exception (2026-07-21):** `app/matching/client.py` exists —
`get_openai_client()`, client construction only. No prompts, no scoring, no endpoint calls
it. This is not "starting the matching phase early"; it's a single sanctioned building
block, added on explicit request. Do not extend it into prompts/scoring without the same
kind of explicit go-ahead.

Already deleted to keep this honest: Alembic, the test suite, the mock Bullhorn client, and
the entire matching pipeline. Do not reintroduce any of them unprompted.

### Two questions that are OPEN. Do not answer them by writing code.
1. **What does a manual search filter on?** The `RoleRequirements` shape below
   (title / skills / min_years / location) **does not work against the live tenant.**
   `skillSet` is populated on ~2% of Company B's 38,340 candidates and is junk when present;
   `experience` is `1` on every single record.
   **Correction (verified 2026-07-15): `category` and `businessSectors` ARE filterable — by
   ID, not name** (the same trap as skills). `category` is **~100% populated on both tenants**
   and searchable. That, plus CV parsing on the ~45% who have a CV on file, is the real answer
   to the weak-skills gap. The agreed direction (client, 2026-07-16): **category reaches
   everyone, skills sharpen the ranking, CVs recover what nobody typed in.** Bullhorn's own
   résumé parser (`/resume/parseToCandidate`, text input) is enabled and returns structured
   skills. This question is largely resolved; a full reconciliation of the matching design
   with these decisions is still pending — do that as a deliberate pass, not piecemeal.
2. **Does a search persist?** For now, no — it is stateless. `companies` is the only table.
   May change if history is wanted later.

## Source of truth for scope
The scoping document is `Bullhorn_POC_Scoping_Response_Revised.md` in the repo root.
It defines what we owe the client. Read it before any architectural decision.
If a request conflicts with it, say so before you build.

## What "PII" means here
**PII = Personally Identifiable Information**: anything that identifies a specific real
person. For a candidate that is their **name, email, phone, home address, date of birth,
and CV/resume text**.

Skills and experience are NOT PII. "8 years of Python", "aerospace sector", "senior
structural engineer" describe what someone can *do*, not who they *are*.

The entire POC rests on this line. Company A may see **that** a strong match exists in
Company B, **how strong** it is, and **who at Company B owns** that candidate — but never
**who the candidate is**.

## What the system holds vs what it shows  (confirmed with the client, 2026-07-16)
The system is **NOT blind, and was never meant to be.** Internally it holds the full
candidate record — name, contact, CV, skills — because it cannot match, parse a CV, or
support a placement otherwise. The guarantee is about the **display**, not the system's
knowledge:

```
  what the system knows      →  REDACTION  →   what the recruiter sees
  name, contact, CV, skills     HERE           match + score, discipline,
  (everything — it has to)      (one point)    owner + owning company, identity HIDDEN
```

The promise is that **Company A cannot harvest Company B's candidate list** — not that the
system never sees a name. A recruiter sees a 94% match, the owner is contacted, an intro is
made, commission agreed, placement happens. **The identity reveal is a business rule** agreed
with the client, not a technical wall — leave a seam, build nothing.

**So: hold full records internally, redact at the single point of display. Do NOT anonymise
early in the pipeline.** Stripping PII at the Bullhorn-fetch boundary produces something that
demos well and cannot do the job — no CV parsing, no placement, no reveal. This corrects an
earlier "the system never even fetches PII / a type with no PII fields" framing, which was
wrong.

## Stack
- Backend: FastAPI + Pydantic v2, Python 3.12, uv
- DB: PostgreSQL running locally (NOT Docker). Database: `bullhorn`
- ORM: SQLAlchemy 2.0 async (asyncpg). **No Alembic** — see Schema below.
- Frontend: React 19 + TypeScript + Vite, TanStack Query
- AI matching: OpenAI API (**changed 2026-07-21, was Anthropic/Claude** — client
  construction only exists so far, see AI matching section below)
- No auth on our own app. (Bullhorn OAuth is separate — see below.)

## Commands
- backend dev:   `cd backend && uv run fastapi dev app/main.py`      (:8000)
- lint+types:    `cd backend && uv run ruff check --fix . && uv run mypy app`
- frontend:      `cd frontend && npm run dev`                        (:5173)
- typecheck:     `cd frontend && npx tsc --noEmit`
- gen types:     `cd frontend && npm run gen:api`

## Domain
- **The candidate pool is chosen, not hardcoded.** A manual search selects the tenant to
  search — A or B — and gets back candidates from that tenant. The scoping doc (§1, §2)
  only ever says "the other company"; it never fixes which. An earlier version of this file
  forbade a tenant selector. That was our narrowing, not the client's requirement, and it
  was wrong.
- **Vacancy polling covers both tenants** (reversed 2026-07-22, explicit request). The
  scoping doc (§1) names Company A explicitly for the simulated auto-match, and the original
  build here started Company-A-only for that reason — but the user asked to extend detection
  to both tenants, so the poller, `vacancies_seen`, and the feed endpoints are now
  per-company (`{company_id}` path param), not hardcoded to `A`. Each tenant gets its own
  independent feed — not merged into one list.
  **UI scoping (2026-07-22):** the header shows only the *logged-in* company's vacancy
  feed/check button, not both at once — matches the existing "logged in as X, searching Y"
  pattern already used for candidate search. Both `/vacancies/{id}/...` endpoints still
  exist and both tenants are still polled by the backend regardless of who's logged in;
  only the UI's default view is scoped to one tenant at a time.
- **Redaction is symmetric.** Because either tenant can be the candidate pool, the redaction
  at the display boundary applies to *any* candidate from *either* tenant — never written as
  "hide Company B's candidates" specifically. (Redaction happens at display; the internal
  pipeline holds full records — see "What the system holds vs what it shows".)
- A **match run** = role requirements + a chosen tenant in → ranked, scored candidates from
  that tenant out. One flow, two triggers:
  - **Manual search**: recruiter picks the tenant to search and enters role requirements.
  - **Simulated auto-match**: a "check for new vacancies" action polls Bullhorn, finds
    unseen vacancies, and runs the same matching against the other tenant. Only the
    trigger differs.
    **As of 2026-07-21, only the detection half is in scope**: poll `JobOrder` by
    `dateAdded`, diff against `vacancies_seen`, report which ones are new. Do not wire up
    "runs the same matching" until the AI matching phase is separately greenlit.
    **As of 2026-07-22, detection covers both Company A and Company B** (originally
    Company-A-only per the scoping doc's fixed direction for this trigger — reversed at
    the user's explicit request). Each tenant is polled and reported independently.
    **Detection mechanism, reversed 2026-07-22 (explicit request):** originally a full
    `JobOrder` id scan (`/query/JobOrder`, paginated) diffed against `vacancies_seen`.
    Switched to Bullhorn's own Entity Events subscription API
    (https://bullhorn.github.io/REST-API-Event-Subscriptions/) instead — poll
    `GET /event/subscription/{id}` for `INSERTED` `JobOrder` events, one subscription
    per tenant. **`PUT` is create-once, not an idempotent upsert as the docs implied**
    — a repeat `PUT` 400s with `"already exists"`, which `ensure_job_order_subscription`
    treats as success rather than an error (discovered by testing against the live
    tenant, not documented). Regular `GET`-based draining is what actually keeps a
    subscription alive; `PUT` is only belt-and-braces recreation if one lapses. See
    rule 3's sanctioned exception above. Known, accepted tradeoffs of this model
    (confirmed against the docs, saved to memory as `bullhorn-entity-events-limitations`):
      - No history before the subscription was created — a fresh subscription reports
        nothing retroactively. (The old full-scan approach didn't have this gap; this is
        a deliberate tradeoff, not an oversight.)
      - Draining the queue (`GET`) consumes those events — a crash between draining and
        finishing `vacancies_seen` inserts loses that batch. `vacancies_seen` is still
        checked defensively per drained id as a second dedup layer, but it cannot recover
        events that were never drained.
      - Subscriptions silently expire if not polled often enough — mitigated by the
        60s poll interval itself; `ensure_job_order_subscription`'s create-if-missing
        behavior recovers automatically if a subscription does lapse.
      - Events carry no field-level detail — every `INSERTED` id still needs a full
        `JobOrder` fetch (`list_job_orders_by_ids`) to get displayable fields.
    **Reversed the same day (explicit request):** this is now backed by a real backend
    poller — an in-process `asyncio` task started in FastAPI's `lifespan`, sleeping and
    re-polling on a fixed interval, independent of anyone viewing the page. This is a
    deliberate reversal of "do not build webhooks or background schedulers" — but stay
    inside the spirit of the original rule: no webhooks (Bullhorn never pushes to us),
    no external scheduling infra (no APScheduler, no cron, no separate process/container —
    `CLAUDE.md`'s "no Docker/CI/infra tooling" rule still holds). One `asyncio.create_task`
    loop, cancelled on shutdown, polling both tenants each cycle. Found vacancies
    accumulate in an in-memory, per-company feed on the backend (not persisted beyond
    `vacancies_seen`'s IDs) and the frontend polls a GET endpoint per company to render
    them — this is still fetch-based polling end to end, not push.

### Role requirements — one shape for both triggers
This is the input to both flows, the payload stored on `match_runs`, and what the prompt
consumes. It is **structured, never free prose**:

```
title:      str
skills:     list[str]
min_years:  int
location:   str | None
```

> ⚠️ **This shape is aspirational, not agreed. It does not survive contact with the live
> tenant** — see open question 1 at the top of this file. `skills` and `min_years` have no
> data behind them and no way to filter on them. Do not implement this shape as written.

**The tenant being searched is NOT a role requirement.** It is a separate field on the
request and a separate column on `match_runs`. It never enters this shape and it never
reaches the prompt — which tenant a candidate sits in says nothing about whether they fit
the role, and letting the model see it invites it to score on the wrong thing.

A Bullhorn vacancy maps onto this shape. The manual search form collects **exactly these
fields** — it is not a free-text box. If the two triggers produce different shapes, the
prompt diverges and the scoping doc's "only the trigger differs" promise stops being true.

## ⚠️ NON-NEGOTIABLE ARCHITECTURE RULES
These are the entire point of the POC. Violating them invalidates the deliverable.

1. **NO CANDIDATE STORE.** Postgres must NEVER contain **candidate** PII: no candidate
   name, email, phone, address, date of birth, or CV/resume text. Not in a table, not in a
   JSON column, not in a cache, not in a log file.
   Candidate data is fetched from Bullhorn, held in memory for one match run, scored,
   and discarded.
   This rule is about **persistence and display, not knowledge.** Holding the full record
   in memory for the match is not just allowed — it is required (you cannot match, parse a
   CV, or place otherwise). What is forbidden is writing it to Postgres or sending it to the
   browser. The reveal re-reads from Bullhorn on demand; we never keep a copy of the other
   company's candidates, because a persisted copy would itself be the harvestable list the
   whole promise guards against.

   **Today Postgres holds TWO tables** (as of 2026-07-21, vacancy polling is in scope;
   candidate search itself is still stateless):
     - `companies`      — tenant config and Bullhorn token state (see Bullhorn auth)
     - `vacancies_seen` — external `JobOrder` IDs already reported by the poll, so a
                          repeat check doesn't re-report the same vacancy as new

   The two below are still the eventual target for the matching phase. They land with the
   AI/matching work, not before. Adding either now is out of scope.
     - `match_runs`     — role requirements, the tenant searched, trigger type, timestamp
     - `match_results`  — candidate_external_id, owner_name, company_id,
                          score, skills_score, experience_score, fit_score, reasons

   `owner_name` is the **recruiter** who owns the candidate record — it is not candidate
   PII, and the scoping doc (§1, §3) explicitly requires showing it. It is permitted.

   **Four is the ceiling.** If you believe you need a fifth table, or to persist a
   candidate, STOP and ask me.

2. **REDACTION IS SERVER-SIDE, AT THE DISPLAY BOUNDARY.** Redaction is a single
   transformation: the internal pipeline holds the full record (a `RawCandidate`), and the
   **response schema** is where PII is dropped (an `AnonymisedCandidate`). Pydantic response
   schemas must not contain candidate PII fields at all. It is NOT stripped at the
   Bullhorn-fetch boundary — see "What the system holds vs what it shows".
   Never send PII to the browser and hide it in the UI — the network tab is part of the demo
   surface.
   The frontend may show: that a match exists, the scores, the bounded `reasons`, the
   discipline/category, the owner's name, and the owning company. Nothing else about the
   candidate.

3. **READ-ONLY.** The Bullhorn integration issues GET requests only. Never POST, PUT,
   PATCH or DELETE against any Bullhorn API. These are live client production systems.
   **Two narrow, explicitly-approved exceptions exist, both scoped to one call each —
   see their own docstrings, and do not extend either without the same kind of explicit
   go-ahead:**
   - `POST /resume/parseToCandidate` (résumé parsing, parse-only, mutates nothing)
   - `PUT /event/subscription/{id}` (vacancy-poller subscription create/keep-alive,
     approved 2026-07-22 — see "Vacancy detection" below)

4. **NO SECRETS OR PII IN LOGS.** Log candidate external IDs, never candidate content.
   Never log tokens or credentials.

5. **PII DOES NOT LEAVE FOR THE AI VENDOR.** Rules 1, 2 and 4 cover Postgres, the browser
   and logs. This rule covers the OpenAI API.
   Only matching-relevant candidate fields may be sent to OpenAI:
   **skills, job titles, years of experience, sector.**
   Never name, email, phone, address, or raw CV text.
   Strip PII **server-side, before the API call** — not by asking the prompt nicely.

## Bullhorn integration
- ALL Bullhorn access goes through `app/bullhorn/live.py`. Nothing else calls Bullhorn.
- **There is no mock client, and no `BULLHORN_CLIENT` env var. `LiveBullhornClient` is the
  only implementation.** Every run of this app talks to Goodall Brazier's real, live
  production Bullhorn. This reverses the original "never make live Bullhorn a prerequisite"
  rule — deliberately, to cut the POC down to the auth flow.
  Know what it costs, and design around it: there is no way to develop, demo, or debug
  offline; anyone cloning the repo needs live client credentials to do anything; and every
  fetch is a real request against a production recruitment system.
  Rule 3 (READ-ONLY) therefore stops being a formality and becomes the only thing standing
  between a bug and the client's data. Hold it absolutely.
- Field alignment between tenants: map only the fields the matching prompt actually
  consumes. No general-purpose mapping layer, no config-driven schema translation.
  A dict of field names is sufficient.
- **Cap candidates fetched per match run at 50**, narrowed by a Bullhorn search query.
  Never fetch-then-score an unbounded candidate set.

### Bullhorn auth
- OAuth 2.0 password grant, per tenant. Credentials in `backend/.env` as `BH_A_*` / `BH_B_*`
  (CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD).
- Flow: `/oauth/authorize` → `/oauth/token` → `/rest-services/login` → BhRestToken + restUrl.
- `restUrl` is returned by login and varies per tenant/data centre. NEVER hardcode it.
- BhRestToken expires. On a 401, the client re-logs-in transparently once, retries, then
  surfaces the error.
- **Token state is persisted to the `companies` table** so it survives a restart (Bullhorn
  rate-limits logins). This is a deliberate decision.
  Tokens and credentials are **never logged and never returned in an API response**.

## AI matching
- Lives in `app/matching/`. `client.py` (`get_openai_client()`) exists — everything else
  below is still unbuilt, out of scope until asked for.
- The prompt lives in a versioned `.md` or `.txt` file — never inlined as a Python string
  literal.
- **Input**: role requirements (the structured shape above) + the rule-5 candidate field
  allowlist (skills, job titles, years of experience, sector). Nothing else.
- **Output is structured, never free prose:**
  ```
  score:            int   # 0-100, overall confidence
  skills_score:     int   # 0-100
  experience_score: int   # 0-100
  fit_score:        int   # 0-100
  reasons:          list[str]   # bounded, e.g. "required skills met: 7/9",
                                # "experience band: 5-10y vs 3+ required"
  ```
  `reasons` must NEVER be free prose generated from CV text. Free prose re-identifies the
  candidate ("led the Derby structures team at a tier-1 aerospace supplier") and punches a
  hole straight through rule 1 and the client's whole reason for running this POC.
- **Batching means: one OpenAI call per chunk of N candidates (start N=10).** It does
  NOT mean `asyncio.gather` over N single-candidate calls. Pick the chunked call.
- **Scores live in the `match_results` row, keyed `(match_run_id, candidate_external_id)`.
  That row IS the cache. There is no separate cache table.** Re-rendering the results page
  reads those rows back and must never re-bill the OpenAI API. Calling the model is the
  slowest and most expensive step in the app.

## Rules
- API contract is the source of truth: `schemas.py` → `gen:api` → frontend imports from
  `src/api/schema.d.ts`. NEVER hand-write request/response types in the frontend.
- SQLAlchemy models in `app/models.py`, Pydantic schemas in `app/schemas.py`. Keep separate.
- DB engine/session and the `get_db` dependency live in `app/database.py`.
- Config is a single Pydantic `BaseSettings` class in `app/config.py`, loaded from
  `backend/.env`. No scattered `os.environ` calls. Never hardcode a connection string.
- **Schema: `create_all()` at startup (`init_db` in `app/database.py`). There is no Alembic.**
  This is a deliberate reversal of the original rule, taken to cut ceremony from the POC.
  The cost, and you must design around it: `create_all()` only ever CREATES a missing table.
  It will never ALTER an existing one. Adding a new table (the matching tables, when they
  land) works fine. Adding or changing a **column** on a table that already exists will
  silently do nothing — the running database keeps the old shape and the app breaks at
  query time, not at startup. When that happens, drop the table and let startup rebuild it.
- Routers in `app/routers/`, one file per resource, async, DB session via `get_db`.
- Frontend data fetching only via TanStack Query hooks in `src/api/`. No fetch in components.
- Frontend API base URL comes from `import.meta.env.VITE_API_URL`. Never hardcode a URL.
- Do NOT add Docker, CI, or infrastructure tooling. Ask first.
- POC discipline: smallest thing that works. No repository layer, no service layer, no
  custom exception middleware, no abstractions "for later."

## There are no tests
Deliberate. pytest is not installed and `backend/tests/` does not exist. Do NOT add a test,
a test dependency, or a test directory unless asked.

Verification is by running the thing: `ruff`, `mypy`, and hitting the endpoints.

**Know what this costs, and say so rather than papering over it.** The PII rules are the
deliverable of this POC, and nothing now proves they hold. When the matching work lands and
candidate data flows again, remember the corrected model: the internal pipeline **does**
carry full records (name, CV) — it must, to match and to parse CVs. The guard is at the
**edges**, not the middle: no PII field in any response schema (the display), none persisted
to Postgres, none in a log. A `RawCandidate → AnonymisedCandidate` split makes the display
boundary explicit — `RawCandidate` must be unreturnable from the API layer. There is no test
proving any of this yet — raise the missing PII guard test before any client demo.

## Before reporting any work done
1. `ruff check` + `mypy app` clean
2. The app starts and the endpoint you changed actually returns what you claim
3. `tsc --noEmit` clean if the API shape changed
Report the actual command output, not a description of it.
Do not report success on code you did not execute.

## Compact instructions
Preserve: the non-negotiable architecture rules, the API contract, and what's left to do.
Drop: file contents and command output.
