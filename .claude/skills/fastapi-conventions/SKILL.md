---
name: fastapi-conventions
description: FastAPI, Pydantic v2, and async SQLAlchemy 2.0 conventions for this project. Use when writing or reviewing any backend code — routers, schemas, models, dependencies, migrations, or error handling.
---

# FastAPI conventions

The non-negotiable rules live in CLAUDE.md and outrank everything here. In backend code
they mean: no candidate PII in `models.py`, no candidate PII in any response schema,
GET-only against Bullhorn, and PII stripped server-side before the Anthropic call.

## Layout
```
app/
├── main.py       # app factory, middleware, router registration. No business logic.
├── config.py     # pydantic-settings. ALL env access happens here, nowhere else.
├── database.py   # async engine, sessionmaker, get_db dependency
├── models.py     # SQLAlchemy ORM models
├── schemas.py    # Pydantic request/response models
├── bullhorn/     # client.py — the ONLY module that talks to Bullhorn
├── matching/     # scorer + the versioned prompt file (never a Python string literal)
└── routers/      # one file per resource
```
No `deps.py` and no `services/`. `get_db` lives in `database.py`; there is no second shared
dependency yet. Adding either is the "abstraction for later" that CLAUDE.md bans — if you
think you need one, ask first.

## Routers
- `async def` everywhere. A sync def blocks the event loop.
- Declare `response_model` on every route. See the redaction note under Pydantic — it is a
  backstop, not the mechanism.
- Use the right status: 201 on create, 404 via HTTPException. Nothing in this POC deletes
  anything, so there is no 204.
  ("Create" means a row in *our* Postgres — a match run. Rule 3's read-only ban is about
  the Bullhorn API, not our own.)
- Routers are thin: validate → call → return. No SQL string building, no HTTP calls.
  The "call" is into `app/matching/` or `app/bullhorn/` — those are the only non-router
  modules that carry logic. Do NOT introduce a service layer to make routers look thinner.
- `APIRouter(prefix="/match-runs", tags=["match-runs"])`, registered in main.py.

## Pydantic v2
- Separate `XCreate` (input) and `XRead` (output) models. Never reuse one for both.
- `model_config = ConfigDict(from_attributes=True)` on read models.
- v2 syntax only: `field_validator`, `model_validator`, `Field(...)`.
  NOT v1: no `@validator`, no `class Config`, no `.dict()`, no `parse_obj`.

### `response_model` is a backstop, not redaction
A field absent from the response model cannot leak — rely on that. But `response_model`
drops only *undeclared* fields. It does nothing about PII smuggled **inside** a declared
one: a `reasons: list[str]` holding `"8 years at a Derby aerospace supplier"` serializes
straight through it and out to the browser.

Redaction is enforced by two things, and `response_model` is the weaker:
1. PII fields are **absent from the schema**.
2. PII is **stripped server-side before it ever reaches a schema** — at the Bullhorn client
   boundary, not in the router and not by asking the prompt nicely.

Declaring `response_model` and stopping there is false confidence, and it is how a candidate
gets identified in the demo.

## Async SQLAlchemy 2.0
- 2.0 style only: `select(Model).where(...)`, then `await session.execute(stmt)`.
  NOT legacy: no `session.query(...)`.
- Session comes from the `get_db` dependency. Never a module-level session.
- Lazy loading raises in async. Eager-load explicitly with `selectinload()`.
- `await session.commit()` in the router, not buried in a helper.
- `mapped_column` / `Mapped[...]` typed models, not the old Column style.

### Router commits vs rollback-per-test
The router commits, but tests roll back per test against real Postgres (CLAUDE.md). Those
fight by default: a session bound to the test's outer transaction that calls `commit()`
commits the *outer* transaction, the rollback undoes nothing, and state leaks between tests.

Bind the test session with `join_transaction_mode="create_savepoint"` so router commits land
on a savepoint and the outer rollback still wipes them:

```python
async with engine.connect() as conn:
    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    await session.close()
    await trans.rollback()
```

## Config
- One `Settings(BaseSettings)` class in config.py, cached with `@lru_cache`.
- `os.getenv` anywhere outside config.py is a bug.

## Errors
- `raise HTTPException(status_code=..., detail=...)`. Nothing custom.
- **Never leak an upstream API's error body to the client — and never log it either.**
  A Bullhorn 4xx body can contain candidate data or token material. Catch it, log the status
  code and the candidate/vacancy external ID, and raise your own HTTPException.

## Python
- Type-hint every signature. mypy must pass.
- `httpx.AsyncClient` for outbound HTTP, never `requests`.
- Never a bare `except:`.
