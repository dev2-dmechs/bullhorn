import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.bullhorn.live import BullhornAuthError, LiveBullhornClient, find_resume_attachment
from app.database import get_db
from app.matching.client import score_candidate_matches
from app.models import BusinessSector, Category, Company, Skill
from app.schemas import (
    AnonymisedCandidate,
    CandidateMatch,
    CandidateResume,
    CandidateSearchRequest,
    CandidateSearchResponse,
    MatchCandidateInput,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["candidates"])
RESUME_CONCURRENCY = 5


@router.post("/{company_id}/candidates/search", response_model=CandidateSearchResponse)
async def search_candidates(
    company_id: str, body: CandidateSearchRequest, db: AsyncSession = Depends(get_db)
) -> CandidateSearchResponse:
    company = await _company(company_id, db)
    category_ids = await _resolve_taxonomy_ids(
        company.id,
        body.category_ids,
        body.category_names,
        db,
        Category,
        Category.bh_category_id,
        "category",
    )
    business_sector_ids = await _resolve_taxonomy_ids(
        company.id,
        body.business_sector_ids,
        body.business_sector_names,
        db,
        BusinessSector,
        BusinessSector.bh_business_sector_id,
        "business sector",
    )
    skill_ids = await _resolve_taxonomy_ids(
        company.id, body.skill_ids, body.skill_names, db, Skill, Skill.bh_skill_id, "skill"
    )
    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        raw_candidates, total = await client.search_candidates(
            category_ids=category_ids,
            skill_ids=skill_ids,
            business_sector_ids=business_sector_ids,
            country_ids=body.country_ids,
            title=body.title,
            limit=body.limit,
        )
    except BullhornAuthError as exc:
        log.warning("Company %s: candidate search failed", company.id)
        raise HTTPException(status_code=502, detail="Bullhorn candidate search failed") from exc

    semaphore = asyncio.Semaphore(RESUME_CONCURRENCY)
    try:
        candidates = list(
            await asyncio.gather(
                *(_redact(company.id, client, raw, semaphore) for raw in raw_candidates)
            )
        )
    except BullhornAuthError as exc:
        log.warning("Company %s: resume fetch/parse failed during candidate search", company.id)
        raise HTTPException(status_code=502, detail="Bullhorn resume fetch/parse failed") from exc

    try:
        scores = await score_candidate_matches(
            category_ids=category_ids,
            business_sector_ids=business_sector_ids,
            skill_ids=skill_ids,
            country_ids=body.country_ids,
            title=body.title,
            description=body.description,
            candidates=[
                MatchCandidateInput(
                    candidate_id=c.external_id,
                    resume=c.resume.parsed if c.resume else None,
                )
                for c in candidates
            ],
        )
    except Exception as exc:
        log.warning(
            "Company %s: AI match scoring failed during candidate search: %s", company.id, exc
        )
        raise HTTPException(status_code=502, detail="AI match scoring failed") from exc

    scores_by_id = {s.candidate_id: s for s in scores}
    for candidate in candidates:
        score = scores_by_id.get(candidate.external_id)
        if score is not None:
            candidate.match = CandidateMatch(
                score=score.score,
                skills_score=score.skills_score,
                experience_score=score.experience_score,
                fit_score=score.fit_score,
                reasons=score.reasons,
            )

    return CandidateSearchResponse(
        company_id=company.id,
        candidates=candidates,
        total_count=total,
        capped=total > len(candidates),
    )


# **********************
# Helpers
# **********************


async def _company(company_id: str, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id.upper())
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def _resolve_taxonomy_ids(
    company_id: str,
    ids: list[int],
    names: list[str],
    db: AsyncSession,
    model: type[Category] | type[BusinessSector] | type[Skill],
    bh_id_column: InstrumentedAttribute[int],
    label: str,
) -> list[int]:

    resolved: list[int] = []
    if names:
        rows = await db.execute(
            select(model.name, bh_id_column).where(
                model.company_id == company_id,
                func.lower(model.name).in_([n.lower() for n in names]),
            )
        )
        by_lower_name = {name.lower(): bh_id for name, bh_id in rows.all()}
        for name in names:
            bh_id = by_lower_name.get(name.lower())
            if bh_id is None:
                log.warning(
                    "Company %s: %s name %r did not match any cached %s",
                    company_id,
                    label,
                    name,
                    label,
                )
                continue
            resolved.append(bh_id)

    return list(dict.fromkeys([*ids, *resolved]))


async def _redact(
    company_id: str, client: LiveBullhornClient, raw: dict[str, Any], semaphore: asyncio.Semaphore
) -> AnonymisedCandidate:
    categories = raw.get("categories", {}).get("data", []) if raw.get("categories") else []
    business_sectors = (
        raw.get("businessSectors", {}).get("data", []) if raw.get("businessSectors") else []
    )
    owner = raw.get("owner")
    attachments = (
        raw.get("fileAttachments", {}).get("data", []) if raw.get("fileAttachments") else []
    )
    candidate_id = str(raw["id"])

    resume = None
    attachment = find_resume_attachment(attachments)
    if attachment is not None:
        file_name = attachment.get("name") or f"resume-{candidate_id}"
        try:
            async with semaphore:
                content, content_type = await client.download_candidate_file(
                    candidate_id, attachment["id"]
                )
                parsed = await client.parse_resume(
                    content, file_name, attachment.get("contentType") or content_type
                )
            resume = CandidateResume(file_name=file_name, parsed=parsed)
        except BullhornAuthError:
            log.warning(
                "Company %s: resume fetch/parse failed for candidate %s, continuing without it",
                company_id,
                candidate_id,
            )

    return AnonymisedCandidate(
        external_id=candidate_id,
        company_id=company_id,
        title=raw.get("occupation") or None,
        category=categories[0]["name"] if categories else None,
        business_sector=business_sectors[0]["name"] if business_sectors else None,
        owner_name=(
            f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip() if owner else None
        ),
        resume=resume,
    )
