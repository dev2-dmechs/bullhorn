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
from app.schemas import (
    AddressSchema,
    BusinessSectorsSchema,
    CategorySchema,
    ConnectionRead,
    JobOrderSchema,
    TaxonomyOption,
)

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


@router.get("/{company_id}/business-sectors", response_model=list[BusinessSectorsSchema])
async def list_business_sectors(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[BusinessSectorsSchema]:
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
    return [
        BusinessSectorsSchema(id=r.bh_business_sector_id, name=r.name, date_added=r.date_added)
        for r in records
    ]


@router.get("/{company_id}/categories")
async def list_categories(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[CategorySchema]:
    company = await _company(company_id, db)

    if refresh:
        client = LiveBullhornClient(company_id=company.id, db=db)
        try:
            categories = await client.list_categories()
            await _create_update_categories(db, company.id, categories)
        except BullhornAuthError as exc:
            log.warning("Company %s: category lookup failed", company.id)
            raise HTTPException(status_code=502, detail="Bullhorn category lookup failed") from exc

    records = await _get_categories(db, company.id)
    return [
        CategorySchema(
            id=r.bh_category_id,
            name=r.name,
            description=r.description,
            enabled=r.enabled,
            skills=r.skills or [],
            specialties=r.specialties or [],
            type=r.type,
            date_added=r.date_added,
            occupation=r.occupation,
        )
        for r in records
    ]


@router.get("/{company_id}/skills")
async def list_skills(
    company_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)
) -> list[TaxonomyOption]:
    company = await _company(company_id, db)

    if refresh:
        client = LiveBullhornClient(company_id=company.id, db=db)
        try:
            skills = await client.list_skills()
            await _create_update_skills(db, company.id, skills)
        except BullhornAuthError as exc:
            log.warning("Company %s: skill lookup failed", company.id)
            raise HTTPException(status_code=502, detail="Bullhorn skill lookup failed") from exc

    records = await _get_skills(db, company.id)
    return [TaxonomyOption(id=r.bh_skill_id, name=r.name) for r in records]


@router.get("/{company_id}/countries", response_model=list[TaxonomyOption])
async def list_countries(
    company_id: str, db: AsyncSession = Depends(get_db)
) -> list[TaxonomyOption]:
    company = await _company(company_id, db)

    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        options = await client.list_countries()
    except BullhornAuthError as exc:
        log.warning("Company %s: country lookup failed", company.id)
        raise HTTPException(status_code=502, detail="Bullhorn country lookup failed") from exc

    return [
        TaxonomyOption(id=o["value"], name=o["label"])
        for o in options
        if o.get("value") and o.get("label")
    ]


@router.get("/{company_id}/jobs", response_model=list[JobOrderSchema])
async def list_latest_jobs(
    company_id: str, db: AsyncSession = Depends(get_db)
) -> list[JobOrderSchema]:
    company = await _company(company_id, db)

    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        jobs = await client.list_latest_jobs(count=100)
    except BullhornAuthError as exc:
        raise HTTPException(status_code=502, detail="Bullhorn job order lookup failed") from exc

    return [to_job_schema(j) for j in jobs]


def _full_name(person: dict[str, Any] | None) -> str | None:
    if not person:
        return None
    return f"{person.get('firstName', '')} {person.get('lastName', '')}".strip() or None


def to_job_schema(raw: dict[str, Any]) -> JobOrderSchema:
    categories = raw.get("categories", {}).get("data", []) if raw.get("categories") else []
    business_sectors = (
        raw.get("businessSectors", {}).get("data", []) if raw.get("businessSectors") else []
    )
    published_category = raw.get("publishedCategory")
    address = raw.get("address")

    return JobOrderSchema(
        id=raw["id"],
        title=raw["title"],
        status=raw.get("status"),
        employment_type=raw.get("employmentType"),
        is_open=raw.get("isOpen"),
        is_public=raw.get("isPublic"),
        date_added=_parse_bh_timestamp(raw.get("dateAdded")),
        date_end=_parse_bh_timestamp(raw.get("dateEnd")),
        date_last_published=_parse_bh_timestamp(raw.get("dateLastPublished")),
        start_date=_parse_bh_timestamp(raw.get("startDate")),
        address=(
            AddressSchema(
                address1=address.get("address1"),
                address2=address.get("address2"),
                city=address.get("city"),
                state=address.get("state"),
                zip=address.get("zip"),
                country_id=address.get("countryID"),
            )
            if address
            else None
        ),
        benefits=raw.get("benefits"),
        bonus_package=raw.get("bonusPackage"),
        pay_rate=raw.get("payRate"),
        salary=raw.get("salary"),
        salary_unit=raw.get("salaryUnit"),
        public_description=raw.get("publicDescription"),
        published_zip=raw.get("publishedZip"),
        travel_requirements=raw.get("travelRequirements"),
        will_relocate=raw.get("willRelocate"),
        will_sponsor=raw.get("willSponsor"),
        years_required=raw.get("yearsRequired"),
        category=categories[0]["name"] if categories else None,
        business_sector=business_sectors[0]["name"] if business_sectors else None,
        owner_name=_full_name(raw.get("owner")),
        published_category=published_category.get("name") if published_category else None,
        response_user_name=_full_name(raw.get("responseUser")),
    )


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
