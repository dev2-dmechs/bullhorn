import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import MAX_JOB_ORDERS, BullhornAuthError, LiveBullhornClient
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


@router.get("/{company_id}/jobs")
async def list_latest_jobs(
    company_id: str,
    count: int = Query(default=100, ge=1, le=MAX_JOB_ORDERS),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    company = await _company(company_id, db)

    client = LiveBullhornClient(company_id=company.id, db=db)
    try:
        jobs = await client.list_latest_jobs(count=count)
    except BullhornAuthError as exc:
        raise HTTPException(status_code=502, detail="Bullhorn job order lookup failed") from exc

    return jobs


# *******************
# Helpers
# *******************


def _full_name(person: dict[str, Any] | None) -> str | None:
    if not person:
        return None
    return f"{person.get('firstName', '')} {person.get('lastName', '')}".strip() or None


def _to_address(address: dict[str, Any] | None) -> AddressSchema | None:
    if not address:
        return None
    return AddressSchema(
        address1=address.get("address1"),
        address2=address.get("address2"),
        city=address.get("city"),
        state=address.get("state"),
        zip=address.get("zip"),
        country_id=address.get("countryID"),
        country_name=address.get("countryName"),
    )


def _association_ids(raw: dict[str, Any], field: str) -> list[int]:
    return [a["id"] for a in (raw.get(field, {}).get("data") or [])]


def _association_names(raw: dict[str, Any], field: str) -> list[str]:
    return [a["name"] for a in (raw.get(field, {}).get("data") or []) if a.get("name")]


def to_job_schema(raw: dict[str, Any]) -> JobOrderSchema:
    return JobOrderSchema(
        id=raw["id"],
        address=_to_address(raw.get("address")),
        benefits=raw.get("benefits"),
        bill_rate_category_id=raw.get("billRateCategoryID"),
        bonus_package=raw.get("bonusPackage"),
        branch_code=raw.get("branchCode"),
        certification_list=raw.get("certificationList"),
        client_bill_rate=raw.get("clientBillRate"),
        cost_center=raw.get("costCenter"),
        degree_list=raw.get("degreeList"),
        description=raw.get("description"),
        duration_weeks=raw.get("durationWeeks"),
        education_degree=raw.get("educationDegree"),
        employment_type=raw.get("employmentType"),
        estimated_end_date=raw.get("estimatedEndDate"),
        external_category_id=raw.get("externalCategoryID"),
        external_id=raw.get("externalID"),
        fee_arrangement=raw.get("feeArrangement"),
        hours_of_operation=raw.get("hoursOfOperation"),
        hours_per_week=raw.get("hoursPerWeek"),
        is_client_editable=raw.get("isClientEditable"),
        is_deleted=raw.get("isDeleted"),
        is_interview_required=raw.get("isInterviewRequired"),
        is_jobcast_published=raw.get("isJobcastPublished"),
        is_open=raw.get("isOpen"),
        is_public=raw.get("isPublic"),
        is_work_from_home=raw.get("isWorkFromHome"),
        job_board_list=raw.get("jobBoardList"),
        job_order_rate_card_id=raw.get("jobOrderRateCardID"),
        job_posting_url=raw.get("jobPostingURL"),
        mark_up_percentage=raw.get("markUpPercentage"),
        num_openings=raw.get("numOpenings"),
        on_site=raw.get("onSite"),
        pay_rate=raw.get("payRate"),
        public_description=raw.get("publicDescription"),
        published_zip=raw.get("publishedZip"),
        reason_closed=raw.get("reasonClosed"),
        report_to=raw.get("reportTo"),
        salary=raw.get("salary"),
        salary_unit=raw.get("salaryUnit"),
        screener_questions_status=raw.get("screenerQuestionsStatus"),
        skill_list=raw.get("skillList"),
        source=raw.get("source"),
        status=raw.get("status"),
        tax_rate=raw.get("taxRate"),
        tax_status=raw.get("taxStatus"),
        title=raw.get("title"),
        travel_requirements=raw.get("travelRequirements"),
        type=raw.get("type"),
        will_relocate=raw.get("willRelocate"),
        will_relocate_int=raw.get("willRelocateInt"),
        will_sponsor=raw.get("willSponsor"),
        years_required=raw.get("yearsRequired"),
        date_added=_parse_bh_timestamp(raw.get("dateAdded")),
        date_closed=_parse_bh_timestamp(raw.get("dateClosed")),
        date_end=_parse_bh_timestamp(raw.get("dateEnd")),
        date_last_exported=_parse_bh_timestamp(raw.get("dateLastExported")),
        date_last_modified=_parse_bh_timestamp(raw.get("dateLastModified")),
        date_last_published=_parse_bh_timestamp(raw.get("dateLastPublished")),
        start_date=_parse_bh_timestamp(raw.get("startDate")),
        time_and_labor_enabled_date=_parse_bh_timestamp(raw.get("timeAndLaborEnabledDate")),
        branch_id=(raw.get("branch") or {}).get("id"),
        client_contact_id=(raw.get("clientContact") or {}).get("id"),
        client_corporation_id=(raw.get("clientCorporation") or {}).get("id"),
        location_id=(raw.get("location") or {}).get("id"),
        opportunity_id=(raw.get("opportunity") or {}).get("id"),
        report_to_client_contact_id=(raw.get("reportToClientContact") or {}).get("id"),
        shift_id=(raw.get("shift") or {}).get("id"),
        workers_comp_rate_id=(raw.get("workersCompRate") or {}).get("id"),
        owner_name=_full_name(raw.get("owner")),
        response_user_name=_full_name(raw.get("responseUser")),
        published_category=(raw.get("publishedCategory") or {}).get("name"),
        categories=_association_names(raw, "categories"),
        business_sectors=_association_names(raw, "businessSectors"),
        appointments_ids=_association_ids(raw, "appointments"),
        approved_placements_ids=_association_ids(raw, "approvedPlacements"),
        assigned_users_ids=_association_ids(raw, "assignedUsers"),
        certification_groups_ids=_association_ids(raw, "certificationGroups"),
        certifications_ids=_association_ids(raw, "certifications"),
        file_attachments_ids=_association_ids(raw, "fileAttachments"),
        interviews_ids=_association_ids(raw, "interviews"),
        job_order_screener_questions_ids=_association_ids(raw, "jobOrderScreenerQuestions"),
        notes_ids=_association_ids(raw, "notes"),
        placements_ids=_association_ids(raw, "placements"),
        sendouts_ids=_association_ids(raw, "sendouts"),
        shifts_ids=_association_ids(raw, "shifts"),
        skills=_association_names(raw, "skills"),
        specialties=_association_names(raw, "specialties"),
        submissions_ids=_association_ids(raw, "submissions"),
        tasks_ids=_association_ids(raw, "tasks"),
        time_units_ids=_association_ids(raw, "timeUnits"),
        web_responses_ids=_association_ids(raw, "webResponses"),
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
