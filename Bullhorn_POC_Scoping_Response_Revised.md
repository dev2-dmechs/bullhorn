# Bullhorn Cross-Company Search & Match

**POC Scope & Estimate**

**Prepared for:** Goodall Brazier

---

## Overview

This proof of concept demonstrates that candidates held in one company's Bullhorn system can be matched to vacancies in another company within the group, with AI producing a ranked shortlist and a confidence score for each match. It runs across two of the group's companies and is delivered as a focused demonstration; extending it into a full production platform would be a separate, subsequent phase.

## 1. What the POC will demonstrate

The POC demonstrates cross-company candidate matching across two chosen companies (Bullhorn tenants), through two scenarios:

- **Manual search.** A recruiter enters the requirements for a role and gets back a ranked list of suitable candidates held in the other company, each with an AI confidence score.
- **Simulated automatic match.** A vacancy is posted in Company A's Bullhorn; on a refresh or a "check for new vacancies" action, the platform picks it up and has already produced the ranked, scored matches from the other company — so to the viewer it appears automatic. The matching is identical to the manual search; only the trigger differs.

In both scenarios, **visibility controls** apply: the user sees that a match exists, its confidence score, and who owns the candidate and which company they sit in — while the candidate's personal details stay hidden. This shows how cross-company matching can work while protecting each company's data.

## 2. How it works

A single, lightweight service connects to the companies' Bullhorn systems through the Bullhorn API and retrieves what it needs to match against. Because each company's Bullhorn is a separate system, the service performs the matching itself:

- The role to match against comes either from the recruiter entering its requirements (manual search) or from a vacancy the service picks up in Company A's Bullhorn via a "check for new vacancies" action (simulated automatic match).
- The service retrieves candidate records from the other company via the Bullhorn API.
- Align the key fields between the systems, to the level needed for the demonstration.
- Use AI to score each candidate against the role's requirements on skills, experience and overall fit, returning a confidence score per candidate.
- Present the ranked results in a simple interface, including the visibility controls.

## 3. Scope and assumptions

- The POC covers two of the group's companies, with API access authorised for both.
- It is read-only — the service reads candidate and vacancy data and writes nothing back.
- The automatic match is simulated — the vacancy is picked up via a manual "check for new vacancies" action, not real-time detection (which is production work).
- Matching is AI ranking with confidence scoring over the retrieved candidates.
- Field alignment between the two systems is done at the level needed for the demonstration.
- Candidate personal details are never exposed in the demo; only the match, confidence score and ownership are shown.

## 4. What we need to begin

- The two companies to include, with a technical contact for each.
- Authorisation for API access to both companies' Bullhorn systems, plus a Bullhorn partner/developer API key.


