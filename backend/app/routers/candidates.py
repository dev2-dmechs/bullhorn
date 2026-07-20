import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import MAX_CANDIDATES, BullhornAuthError, LiveBullhornClient
from app.database import get_db
from app.models import Company
from app.schemas import AnonymisedCandidate, CandidateSearchRequest, CandidateSearchResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["candidates"])


async def _company(company_id: str, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id.upper())
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _redact(company_id: str, raw: dict[str, Any]) -> AnonymisedCandidate:
    categories = raw.get("categories", {}).get("data", []) if raw.get("categories") else []
    business_sectors = (
        raw.get("businessSectors", {}).get("data", []) if raw.get("businessSectors") else []
    )
    owner = raw.get("owner")

    return AnonymisedCandidate(
        external_id=str(raw["id"]),
        company_id=company_id,
        category=categories[0]["name"] if categories else None,
        business_sector=business_sectors[0]["name"] if business_sectors else None,
        owner_name=(
            f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip() if owner else None
        ),
    )


@router.post("/{company_id}/candidates/search", response_model=CandidateSearchResponse)
async def search_candidates(
    company_id: str, body: CandidateSearchRequest, db: AsyncSession = Depends(get_db)
):
    company = await _company(company_id, db)
    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        raw_candidates, total = await client.search_candidates(
            category_ids=body.category_ids,
            skill_ids=body.skill_ids,
            business_sector_ids=body.business_sector_ids,
        )
    except BullhornAuthError as exc:
        log.warning("Company %s: candidate search failed", company.id)
        raise HTTPException(status_code=502, detail="Bullhorn candidate search failed") from exc

    candidates = [_redact(company.id, raw) for raw in raw_candidates]
    return CandidateSearchResponse(
        company_id=company.id,
        candidates=candidates,
        total_count=total,
        capped=total > MAX_CANDIDATES,
    )
