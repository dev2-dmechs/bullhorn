import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import BullhornAuthError, LiveBullhornClient
from app.config import get_settings
from app.database import get_db
from app.models import BusinessSector, Category, Company, Skill
from app.schemas import ConnectionRead

log = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["companies"])


def _parse_bh_timestamp(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


async def _company(company_id: str, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id.upper())
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("/{company_id}/connection", response_model=ConnectionRead)
async def check_connection(company_id: str, db: AsyncSession = Depends(get_db)) -> ConnectionRead:
    company = await _company(company_id, db)

    creds = get_settings().credentials_for(company.id)
    client = LiveBullhornClient(company_id=company.id, db=db)
    connected, detail = await client.check_connection()

    await db.refresh(company)
    return ConnectionRead(
        company_id=company.id,
        name=company.name,
        configured=creds.is_configured,
        connected=connected,
        rest_url_present=bool(company.rest_url),
        detail=detail,
    )


@router.get("/{company_id}/business-sectors")
async def list_business_sectors(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[BusinessSector]:
    company = await _company(company_id, db)

    if refresh:
        client = LiveBullhornClient(company_id=company.id, db=db)
        try:
            sectors = await client.list_business_sectors()
            await _create_update_business_sectors(db, company.id, sectors)
        except BullhornAuthError as exc:
            raise HTTPException(
                status_code=502, detail="Bullhorn business sector lookup failed"
            ) from exc

    records = await _get_business_sectors(db, company.id)
    return records


@router.get("/{company_id}/categories")
async def list_categories(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[Category]:
    company = await _company(company_id, db)

    if refresh:
        client = LiveBullhornClient(company_id=company.id, db=db)
        try:
            categories = await client.list_categories()
            await _create_update_categories(db, company.id, categories)
        except BullhornAuthError as exc:
            log.warning("Company %s: category lookup failed", company.id)
            raise HTTPException(status_code=502, detail="Bullhorn category lookup failed") from exc

    return await _get_categories(db, company.id)


@router.get("/{company_id}/skills")
async def list_skills(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[Skill]:
    company = await _company(company_id, db)

    if refresh:
        client = LiveBullhornClient(company_id=company.id, db=db)
        try:
            skills = await client.list_skills()
            await _create_update_skills(db, company.id, skills)
        except BullhornAuthError as exc:
            log.warning("Company %s: skill lookup failed", company.id)
            raise HTTPException(status_code=502, detail="Bullhorn skill lookup failed") from exc

    return await _get_skills(db, company.id)


async def _get_business_sectors(db: AsyncSession, company_id: str) -> list[BusinessSector]:
    cached = await db.scalars(select(BusinessSector).where(BusinessSector.company_id == company_id))
    return list(cached.all())


async def _create_update_business_sectors(
    db: AsyncSession, company_id: str, sectors: list[dict[str, Any]]
) -> None:
    await db.execute(delete(BusinessSector).where(BusinessSector.company_id == company_id))
    db.add_all(
        BusinessSector(
            company_id=company_id,
            bh_business_sector_id=s["id"],
            name=s["name"],
            date_added=_parse_bh_timestamp(s.get("dateAdded")),
        )
        for s in sectors
    )
    await db.commit()


def _bh_association_ids(association: dict[str, Any] | None) -> list[int]:
    if not association:
        return []
    return [item["id"] for item in association.get("data", [])]


async def _get_categories(db: AsyncSession, company_id: str) -> list[Category]:
    cached = await db.scalars(select(Category).where(Category.company_id == company_id))
    return list(cached.all())


async def _create_update_categories(
    db: AsyncSession, company_id: str, categories: list[dict[str, Any]]
) -> None:
    await db.execute(delete(Category).where(Category.company_id == company_id))
    db.add_all(
        Category(
            company_id=company_id,
            bh_category_id=c["id"],
            name=c["name"],
            description=c.get("description"),
            enabled=c.get("enabled", True),
            skills=_bh_association_ids(c.get("skills")),
            specialties=_bh_association_ids(c.get("specialties")),
            type=c.get("type"),
            date_added=_parse_bh_timestamp(c.get("dateAdded")),
            occupation=c.get("occupation"),
        )
        for c in categories
    )
    await db.commit()


async def _get_skills(db: AsyncSession, company_id: str) -> list[Skill]:
    cached = await db.scalars(select(Skill).where(Skill.company_id == company_id))
    return list(cached.all())


async def _create_update_skills(
    db: AsyncSession, company_id: str, skills: list[dict[str, Any]]
) -> None:
    await db.execute(delete(Skill).where(Skill.company_id == company_id))
    db.add_all(Skill(company_id=company_id, bh_skill_id=s["id"], name=s["name"]) for s in skills)
    await db.commit()
