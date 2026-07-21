# Known exceptions & open items

1. Some candidate records have a resume, some don't — both still appear in the search
   response based on the search filters (category/skill/business sector/country/title),
   not on resume presence.
2. This code was written entirely by Claude (an AI agent) and has not been proofread or
   reviewed by a human yet.
3. All documentation and reference material (Bullhorn API docs, OpenAI API docs, etc.)
   used to build this were read and interpreted by Claude itself, not independently
   verified by a human.
4. Resume/CV parsing is done via Bullhorn's own API (`/resume/parseToCandidate`) — not a
   custom parser.

## Open questions

- Do we need to filter search results to only candidates who have a resume? (This filter
  has been added, but needs confirmation — it may reduce/affect the response.)
- If no role description is provided, the AI will score based on whatever fields are
  available (title, filters, resume) rather than refusing to score.
