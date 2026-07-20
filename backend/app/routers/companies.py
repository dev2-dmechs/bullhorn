import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import BullhornAuthError, LiveBullhornClient
from app.config import get_settings
from app.database import get_db
from app.models import BusinessSector, Category, Company, Skill
from app.schemas import ConnectionRead, TaxonomyOption

log = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["companies"])


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


@router.get("/{company_id}/categories", response_model=list[TaxonomyOption])
async def list_categories(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[TaxonomyOption]:
    company = await _company(company_id, db)

    if not refresh:
        cached = await db.scalars(select(Category).where(Category.company_id == company.id))
        rows = cached.all()
        if rows:
            return [TaxonomyOption(id=row.bh_category_id, name=row.name) for row in rows]

    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        categories = await client.list_categories()
    except BullhornAuthError as exc:
        log.warning("Company %s: category lookup failed", company.id)
        raise HTTPException(status_code=502, detail="Bullhorn category lookup failed") from exc

    await db.execute(delete(Category).where(Category.company_id == company.id))
    db.add_all(
        Category(company_id=company.id, bh_category_id=c["id"], name=c["name"]) for c in categories
    )
    await db.commit()
    return [TaxonomyOption(id=c["id"], name=c["name"]) for c in categories]


@router.get("/{company_id}/business-sectors")
async def list_business_sectors(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[TaxonomyOption]:
    company = await _company(company_id, db)

    if not refresh:
        cached = await db.scalars(
            select(BusinessSector).where(BusinessSector.company_id == company.id)
        )
        rows = cached.all()
        if rows:
            return [TaxonomyOption(id=row.bh_business_sector_id, name=row.name) for row in rows]

    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        sectors = await client.list_business_sectors()
    except BullhornAuthError as exc:
        print(exc)
        log.warning("Company %s: business sector lookup failed", company.id)
        raise HTTPException(
            status_code=502, detail="Bullhorn business sector lookup failed"
        ) from exc

    await db.execute(delete(BusinessSector).where(BusinessSector.company_id == company.id))
    db.add_all(
        BusinessSector(company_id=company.id, bh_business_sector_id=s["id"], name=s["name"])
        for s in sectors
    )
    await db.commit()
    return [TaxonomyOption(id=s["id"], name=s["name"]) for s in sectors]


@router.get("/{company_id}/skills", response_model=list[TaxonomyOption])
async def list_skills(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[TaxonomyOption]:
    company = await _company(company_id, db)

    if not refresh:
        cached = await db.scalars(select(Skill).where(Skill.company_id == company.id))
        rows = cached.all()
        if rows:
            return [TaxonomyOption(id=row.bh_skill_id, name=row.name) for row in rows]

    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        skills = await client.list_skills()
    except BullhornAuthError as exc:
        log.warning("Company %s: skill lookup failed", company.id)
        raise HTTPException(status_code=502, detail="Bullhorn skill lookup failed") from exc

    await db.execute(delete(Skill).where(Skill.company_id == company.id))
    db.add_all(Skill(company_id=company.id, bh_skill_id=s["id"], name=s["name"]) for s in skills)
    await db.commit()
    return [TaxonomyOption(id=s["id"], name=s["name"]) for s in skills]
