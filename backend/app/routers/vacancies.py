import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import BullhornAuthError, LiveBullhornClient
from app.database import get_db
from app.models import VacancySeen
from app.routers.companies import to_job_schema
from app.schemas import NewVacancyCheckResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/vacancies", tags=["vacancies"])
POLL_COMPANY_ID = "A"
POLL_FETCH_COUNT = 200


@router.post("/check-new", response_model=NewVacancyCheckResponse)
async def check_new_vacancies(db: AsyncSession = Depends(get_db)) -> NewVacancyCheckResponse:
    client = LiveBullhornClient(company_id=POLL_COMPANY_ID, db=db)
    try:
        jobs = await client.list_latest_jobs(count=POLL_FETCH_COUNT)
    except BullhornAuthError as exc:
        log.warning("Company %s: vacancy poll failed", POLL_COMPANY_ID)
        raise HTTPException(status_code=502, detail="Bullhorn vacancy poll failed") from exc

    fetched_ids = [job["id"] for job in jobs]
    seen = await db.scalars(
        select(VacancySeen.bh_job_order_id).where(
            VacancySeen.company_id == POLL_COMPANY_ID,
            VacancySeen.bh_job_order_id.in_(fetched_ids),
        )
    )
    seen_ids = set(seen.all())
    new_jobs = [job for job in jobs if job["id"] not in seen_ids]

    now = datetime.now(UTC)
    db.add_all(
        VacancySeen(company_id=POLL_COMPANY_ID, bh_job_order_id=job["id"], first_seen_at=now)
        for job in new_jobs
    )
    await db.commit()

    log.info(
        "Company %s: vacancy poll checked %d jobs, %d new",
        POLL_COMPANY_ID,
        len(jobs),
        len(new_jobs),
    )
    return NewVacancyCheckResponse(
        company_id=POLL_COMPANY_ID,
        new_jobs=[to_job_schema(job) for job in new_jobs],
        checked_count=len(jobs),
    )
