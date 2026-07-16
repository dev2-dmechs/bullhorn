# Bullhorn POC — Findings & Decisions

A living record of what we've **verified** against the live Bullhorn tenants and what we've
**decided**. It exists so this knowledge lives in the repo, not only in chat or a scratch plan.

All "verified" facts were measured **read-only** against Goodall Brazier's two live production
tenants — **Company A** (source of vacancies) and **Company B** (candidates) — on the dates
shown. Numbers drift slightly between calls because the tenants are live.

---

## 1. Auth — built and working

The OAuth flow authenticates against **both** production tenants. It handles the EMEA
data-centre redirect, caches the `BhRestToken` + `restUrl` on the `companies` row, and
transparently re-logs-in on a 401. `restUrl` is read from the login response, never hardcoded.
All Bullhorn access goes through `app/bullhorn/live.py`; `_get` is the single choke point for
every read. See CLAUDE.md → Bullhorn auth.

---

## 2. Bullhorn search mechanics (verified 2026-07-15)

Bullhorn's `/search/Candidate` uses Apache Lucene. These rules were established by probing —
Bullhorn does not document them, and getting them wrong returns **nothing, with no error**.

- **Unprefixed clauses BOOST, they don't filter.** `+isDeleted:0 occupation:Superintendent`
  returns the same total as `+isDeleted:0` alone — the title only reorders. This is what makes
  the "hard filter vs ranking signal" design possible. Use `+` (required), plain (boost),
  `-` (exclude). **Never** `AND`/`OR` at the top level — it silently promotes a boost to a filter.
- **To-many associations filter by ID, not name.** `primarySkills.name:Concrete` → **0**;
  `primarySkills.id:1000003` → **537**. Same for `categories`, `businessSectors`. Resolve
  name → tenant-local ID via `query/Skill` (paginated; `options/Skill` returns only the enabled
  subset and is incomplete).
- **There is no default search field.** A bare term (`+Superintendent`) → **0**. Free-text
  keywords must target a field explicitly, e.g. `description:concrete`.
- **`_score` must NOT be listed in the `fields` param** — doing so silently empties the response.
  It is returned automatically.

---

## 3. Data coverage (verified 2026-07-14/15)

| field | Company A (~12,200) | Company B (~38,300) | notes |
|---|---|---|---|
| `occupation` (job title) | ~99% | ~99% | the reliable title field |
| `categories` | **100%** | **100%** | filter by ID; the near-universal signal |
| `businessSectors` | 81% | 74% | filter by ID, but **less reliable** (one A sector filtered to 0) |
| `primarySkills` | 80% | **42%** | filter by ID |
| `description` (free text) | 26% | 18% | the only searchable free-text field |
| `experience` | dead | dead | value is `1` on **all ~50,000** records — a default, not data |
| `secondarySkills` | 0% | 0% | empty |
| `clientCorporationBlackList` | 0% | 0% | empty — the "don't show me to this company" flag |
| CV file attachment | — | **~45%** (17,146) | type "Resume" |
| **reachable by a skill filter** (skills OR description) | **76%** | **43%** | ceiling of a skills-only search |

**The core problem this creates:** a must-have-**skills** hard filter on Company B can only ever
see ~43% of the database — the other ~22,000 candidates are untagged, not unqualified. Company A
is far cleaner (76%).

Skill vocabularies differ per tenant: A is clean construction (`Concrete`, `Piping`, `Bridges`,
`MEP`); B is a mixed construction/pharma set (`Oncology`, `Leadership`, alongside `Construction`).
Category values are the usable discipline signal, e.g. B: `Projects` (11,543), `Clinical` (5,366),
`Pre-Construction` (2,678).

A full corrected query validated live on Company A —
`+isDeleted:0 +(primarySkills.id:1000003 OR description:concrete) +(...piping...) occupation:"project manager"^4`
— returned **76 relevant candidates**, project-managers at the top.

---

## 4. CVs & résumé parsing (verified 2026-07-16)

- **CV files ARE retrievable** via `file/Candidate/{id}/{fileId}` — returns the real document
  (a PDF, base64). ~45% of Company B candidates have one on file.
- **Parsed text is NOT a stored field.** Bullhorn hands back the binary file, not extracted text.
  To use the content we'd extract text from the PDF ourselves.
- **Bullhorn's own résumé parser is ENABLED** (`POST /resume/parseToCandidate`). It returns
  structured `skillList`, `primarySkills` (mapped, with IDs), work-history titles, education, and
  a `confidenceScore`. From a rich synthetic CV it extracted 11 skills + 3 mapped skills + titles.
  Caveats:
  - It accepts **text/html only, not the PDF** on this tenant (binary/Daxtra file-parse appears
    not provisioned). Flow would be: download PDF → we extract text → POST text to the parser.
  - Extraction quality scales with how detailed the CV is.
  - Powered by **Daxtra** (third party). It's a `POST`, but **non-mutating** — it returns data and
    writes nothing unless you follow with separate `PUT`s (we would not).
  - Testing was done with **synthetic data only** — no real candidate CV was parsed.

---

## 5. Decisions

Made with Rizwan / the client. These override or narrow the aspirational spec in CLAUDE.md.

- **Scope: manual search only.** Simulated auto-match and AI (Anthropic) scoring are **out of
  scope for now** — a later phase.
- **Skills EXCLUDE (hard filter). Title RANKS (never excludes).** Titles are non-standardised, so
  filtering on them would delete true matches.
- **Category is a primary match signal.** Client's framing: **category reaches everyone, skills
  sharpen the ranking, CVs recover what nobody typed in.** This is the answer to the ~22,000
  unreachable candidates.
- **Production data** — no sandbox is available; the POC runs against the live tenants (read-only).
- **The `description` free-text field is IN**, used server-side as a hidden filter to catch
  untagged candidates (text never leaves Bullhorn / is never displayed).
- **Blacklist ("don't show me to this company") is OUT** for the POC (and the field is empty anyway).
- **Titles:** the client has no standard-title list, so we handle normalisation ourselves.
- **Title matching:** fuzzy token-overlap (no embedding model; fits the "no AI" scope).
- **Experience/seniority is dropped** from results — the field is dead data.

---

## 6. Privacy model — confirmed with the client (2026-07-16)

The system is **NOT blind, and was never meant to be.** It holds the full record internally
because it cannot match, parse a CV, or support a placement otherwise. The guarantee is about
the **display**:

```
  what the system knows      →  REDACTION  →   what the recruiter sees
  name, contact, CV, skills     HERE           match + score, discipline (category),
  (everything — it has to)      (one point)     owner + owning company, identity HIDDEN
```

- The promise is **"Company A cannot harvest Company B's candidate list"** — not that the system
  never sees a name.
- **Hold full records internally; redact at the single point of display.** Do NOT anonymise at
  the Bullhorn-fetch boundary (an earlier "type with no PII fields" framing — that was wrong;
  it would break CV parsing, placement, and the reveal).
- Implementation shape: `RawCandidate` (full, broker-only, unreturnable from the API) →
  `AnonymisedCandidate` (the only thing the endpoint returns).
- **The identity reveal is a business rule** (owner contacted → intro → commission → placement),
  agreed with the client — leave a seam, build nothing.
- **Persistence:** hold the full record in memory for the match; persist only the non-identifying
  result (score, owner, company, an internal reference); re-read from Bullhorn for a reveal. A
  persisted copy of the other company's candidates would itself be the harvestable list the
  promise guards against.

---

## 7. Open / pending

- **Awaiting the client's confirmation on two points** (asked 2026-07-16): (a) the persistence
  approach above (in-memory + non-PII results, vs retaining full records); (b) whether skills are
  shown on the recruiter's card or kept internal (the diagram shows discipline, not skills).
- **CLAUDE.md still needs a full reconciliation pass** with §5's decisions — it currently carries
  the old aspirational `RoleRequirements` shape and AI-matching section. Do that deliberately,
  once the two pending confirmations land.
