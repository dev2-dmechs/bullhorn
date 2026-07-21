"""OpenAI client and the batched candidate-vs-role scoring call."""

import asyncio
import json
from functools import lru_cache
from pathlib import Path

from openai import AsyncOpenAI

from app.config import get_settings
from app.schemas import MatchCandidateInput, MatchScore, MatchScoreBatchResult

PROMPT_PATH = Path(__file__).parent / "prompts" / "match_v2.md"
# One OpenAI call scores up to this many candidates at once — never one call per
# candidate. See CLAUDE.md's AI matching section.
MATCH_CHUNK_SIZE = 10


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


@lru_cache
def _system_prompt() -> str:
    return PROMPT_PATH.read_text()


async def _score_chunk(
    category_ids: list[int],
    business_sector_ids: list[int],
    skill_ids: list[int],
    country_ids: list[int],
    title: str | None,
    description: str | None,
    candidates: list[MatchCandidateInput],
) -> list[MatchScore]:
    payload = {
        "role_requirements": {
            "category_ids": category_ids,
            "business_sector_ids": business_sector_ids,
            "skill_ids": skill_ids,
            "country_ids": country_ids,
            "title": title,
            "description": description,
        },
        "candidates": [c.model_dump() for c in candidates],
    }

    client = get_openai_client()
    response = await client.responses.parse(
        model=get_settings().openai_model,
        instructions=_system_prompt(),
        input=json.dumps(payload),
        text_format=MatchScoreBatchResult,
    )
    result = response.output_parsed
    if result is None:
        raise ValueError("OpenAI match call returned no parsed output")
    return result.results


async def score_candidate_matches(
    category_ids: list[int],
    business_sector_ids: list[int],
    skill_ids: list[int],
    country_ids: list[int],
    title: str | None,
    description: str | None,
    candidates: list[MatchCandidateInput],
) -> list[MatchScore]:
    """Score every given candidate against one role.

    Chunked: one OpenAI call per MATCH_CHUNK_SIZE candidates, chunks run concurrently.
    This is NOT `asyncio.gather` over one call per candidate — chunking is the point.

    Each candidate's `resume` — its parsed CV — is sent to OpenAI as-is. This is a
    deliberate, explicit exception to rule 5 (PII does not leave for the AI vendor),
    confirmed for this call: unlike the rest of the matching design (skills/titles/
    experience/sector only), the full parsed resume — which can include name, email,
    phone — is passed through. Never log `candidates` or the resumes it carries."""
    if not candidates:
        return []

    chunks = [
        candidates[i : i + MATCH_CHUNK_SIZE] for i in range(0, len(candidates), MATCH_CHUNK_SIZE)
    ]
    chunk_results = await asyncio.gather(
        *(
            _score_chunk(
                category_ids,
                business_sector_ids,
                skill_ids,
                country_ids,
                title,
                description,
                chunk,
            )
            for chunk in chunks
        )
    )
    return [score for chunk in chunk_results for score in chunk]
