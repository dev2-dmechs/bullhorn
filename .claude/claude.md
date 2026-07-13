# Bullhorn Cross-Company Search & Match — POC

Proves that candidates held in one company's Bullhorn tenant can be matched to vacancies
in another company in the group, with AI producing a ranked shortlist and a confidence
score per candidate — while candidate PII stays hidden across the company boundary.

Client: Goodall Brazier. Two Bullhorn tenants (Company A, Company B).
This is a focused demonstration, not a platform. Production is a separate, later phase.

## Source of truth for scope
The scoping document is `Bullhorn_POC_Scoping_Response_Revised.md` in the repo root.
It defines what we owe the client. Read it before any architectural decision.
If a request conflicts with it, say so before you build.

## Stack
- Backend: FastAPI + Pydantic v2, Python 3.12, uv
- DB: PostgreSQL running locally (NOT Docker). Databases: `bullhorn` (dev), `bullhorn_test` (tests)
- ORM: SQLAlchemy 2.0 async (asyncpg) + Alembic
- Frontend: React 19 + TypeScript + Vite, TanStack Query
- AI matching: Claude via the Anthropic API
- No auth on our own app. (Bullhorn OAuth is separate — see below.)

## Commands
- migrate:       `cd backend && uv run alembic upgrade head`
- new migration: `cd backend && uv run alembic revision --autogenerate -m "<msg>"`
- backend dev:   `cd backend && uv run fastapi dev app/main.py`      (:8000)
- tests:         `cd backend && uv run pytest -q`
- lint+types:    `cd backend && uv run ruff check --fix . && uv run mypy app`
- frontend:      `cd frontend && npm run dev`                        (:5173)
- typecheck:     `cd frontend && npx tsc --noEmit`
- gen types:     `cd frontend && npm run gen:api`

## Domain
- A **match run** = role requirements in → ranked, scored candidates from the *other*
  company out. One flow, two triggers:
  - **Manual search**: recruiter enters role requirements.
  - **Simulated auto-match**: a "check for new vacancies" action polls Company A's Bullhorn,
    finds unseen vacancies, and runs the same matching. Only the trigger differs.
    This is NOT real-time detection. Do not build webhooks or background schedulers.

## ⚠️ NON-NEGOTIABLE ARCHITECTURE RULES
These are the entire point of the POC. Violating them invalidates the deliverable.

1. **NO CANDIDATE STORE.** Postgres must NEVER contain candidate PII: no name, email,
   phone, address, CV/resume text, or free-text notes. Not in a table, not in a JSON
   column, not in a cache, not in a log file.
   Candidate data is fetched from Bullhorn, held in memory for one match run, scored,
   and discarded.
   Postgres holds ONLY:
     - `companies`       — tenant config and token state
     - `match_runs`      — role requirements, trigger type, timestamp
     - `match_results`   — candidate_external_id, owner_name, company_id, score, reasoning
     - `vacancies_seen`  — external vacancy IDs already processed
   If you believe you need to persist a candidate, STOP and ask me.

2. **REDACTION IS SERVER-SIDE.** Pydantic response schemas must not contain PII fields
   at all. Never send PII to the browser and hide it in the UI — the network tab is part
   of the demo surface.
   The frontend may show: that a match exists, the confidence score, the owner's name,
   and the owning company. Nothing else about the candidate.

3. **READ-ONLY.** The Bullhorn integration issues GET requests only. Never POST, PUT,
   PATCH or DELETE against any Bullhorn API. These are live client production systems.

4. **NO SECRETS OR PII IN LOGS.** Log candidate external IDs, never candidate content.
   Never log tokens or credentials.

## Bullhorn integration
- ALL Bullhorn access goes through `app/bullhorn/client.py`. Nothing else calls Bullhorn.
- `BullhornClient` is a Protocol with two implementations, selected by env var:
  - `MockBullhornClient` — reads JSON fixtures from `tests/fixtures/bullhorn/`. **This is
    the default for all development and all tests.**
  - `LiveBullhornClient` — real API. Used only for final verification and the demo.
- Everything must be buildable, testable and demoable against the mock. Never make live
  Bullhorn a prerequisite for running the app.
- Fixtures are real record shapes with PII replaced by fake values.
- Field alignment between tenants: map only the fields the matching prompt actually
  consumes. No general-purpose mapping layer, no config-driven schema translation.
  A dict of field names is sufficient.

### Bullhorn auth
- OAuth 2.0 password grant, per tenant. Credentials in `backend/.env` as `BH_A_*` / `BH_B_*`
  (CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD).
- Flow: `/oauth/authorize` → `/oauth/token` → `/rest-services/login` → BhRestToken + restUrl.
- `restUrl` is returned by login and varies per tenant/data centre. NEVER hardcode it.
- BhRestToken expires. On a 401, the client re-logs-in transparently once, retries, then
  surfaces the error.
- Tokens and credentials are never logged, never persisted to Postgres, never returned
  in an API response.

## AI matching
- Lives in `app/matching/`. The prompt lives in a versioned `.md` or `.txt` file — never
  inlined as a Python string literal.
- Input: role requirements + candidate fields. Output: score 0-100 + short reasoning.
- Scoring covers skills, experience and overall fit.
- Scores are cached by `(match_run_id, candidate_external_id)`. Re-rendering the results
  page must never re-bill the Anthropic API.
- Scoring is the slowest and most expensive operation in the app. Batch it.

## Rules
- API contract is the source of truth: `schemas.py` → `gen:api` → frontend imports from
  `src/api/schema.d.ts`. NEVER hand-write request/response types in the frontend.
- SQLAlchemy models in `app/models.py`, Pydantic schemas in `app/schemas.py`. Keep separate.
- Every model change gets an Alembic migration. Never use `create_all()`.
- Routers in `app/routers/`, one file per resource, async, DB session via `get_db`.
- Frontend data fetching only via TanStack Query hooks in `src/api/`. No fetch in components.
- Frontend API base URL comes from `import.meta.env.VITE_API_URL`. Never hardcode a URL.
- All config and connection strings come from `backend/.env`. Never hardcode them.
- Do NOT add Docker, CI, or infrastructure tooling. Ask first.
- POC discipline: smallest thing that works. No repository layer, no service layer, no
  custom exception middleware, no abstractions "for later."

## Tests exist as a verification target, not for coverage
- One happy path + one 422 per endpoint, in `backend/tests/`. Nothing else.
- No mocks of the DB. Real Postgres (`bullhorn_test`), transaction rollback per test.
- Bullhorn IS mocked — always `MockBullhornClient`. Tests never hit the live API.
- `tests/conftest.py` MUST assert `"test" in TEST_DATABASE_URL` before connecting.
- Add one test asserting that no PII field ever appears in a `match_results` row or in any
  API response. This rule is the deliverable; guard it.
- No frontend tests.
- Do NOT expand the suite unprompted. Do NOT test internal functions.

## Before reporting any work done
1. `uv run pytest -q` green
2. `ruff check` + `mypy app` clean
3. `alembic upgrade head` clean
4. `tsc --noEmit` clean if the API shape changed
Report the actual pytest output, not a description of it.
Do not report success on code you did not execute.

## Compact instructions
Preserve: the non-negotiable architecture rules, the API contract, current migration state,
and what's left to do.
Drop: file contents and command output.