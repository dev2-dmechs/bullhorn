import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import BullhornAuthError, LiveBullhornClient
from app.database import SessionLocal, get_db
from app.models import VacancySeen
from app.routers.companies import to_job_schema
from app.schemas import JobOrderSchema, NewVacancyCheckResponse, VacancyFeedResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/vacancies", tags=["vacancies"])

POLL_COMPANY_ID = "A"
POLL_INTERVAL_SECONDS = 60
MAX_FEED_SIZE = 500

_feed: list[JobOrderSchema] = []
_last_checked_at: datetime | None = None


async def _check_and_record(db: AsyncSession) -> tuple[list[JobOrderSchema], int]:
    """Scan every JobOrder id in the tenant (not just the most recent N), diff the full
    set against vacancies_seen, and record whichever ones are unseen."""
    client = LiveBullhornClient(company_id=POLL_COMPANY_ID, db=db)
    all_ids = await client.list_all_job_order_ids()

    seen = await db.scalars(
        select(VacancySeen.bh_job_order_id).where(VacancySeen.company_id == POLL_COMPANY_ID)
    )
    seen_ids = set(seen.all())
    unseen_ids = [i for i in all_ids if i not in seen_ids]

    jobs = await client.list_job_orders_by_ids(unseen_ids)

    now = datetime.now(UTC)
    db.add_all(
        VacancySeen(company_id=POLL_COMPANY_ID, bh_job_order_id=job["id"], first_seen_at=now)
        for job in jobs
    )
    await db.commit()

    log.info(
        "Company %s: vacancy poll scanned %d job orders, %d unseen",
        POLL_COMPANY_ID,
        len(all_ids),
        len(jobs),
    )
    return [to_job_schema(job) for job in jobs], len(all_ids)


def _record_in_feed(new_jobs: list[JobOrderSchema]) -> None:
    if not new_jobs:
        return
    _feed.extend(new_jobs)
    del _feed[:-MAX_FEED_SIZE]


@router.post("/check-new", response_model=NewVacancyCheckResponse)
async def check_new_vacancies(db: AsyncSession = Depends(get_db)) -> NewVacancyCheckResponse:
    """On-demand poll — same detection logic the background poller runs on its own
    interval. Also feeds the accumulating feed served by GET /vacancies/new."""
    global _last_checked_at
    try:
        new_jobs, checked_count = await _check_and_record(db)
    except BullhornAuthError as exc:
        log.warning("Company %s: vacancy poll failed", POLL_COMPANY_ID)
        raise HTTPException(status_code=502, detail="Bullhorn vacancy poll failed") from exc

    _record_in_feed(new_jobs)
    _last_checked_at = datetime.now(UTC)
    return NewVacancyCheckResponse(
        company_id=POLL_COMPANY_ID, new_jobs=new_jobs, checked_count=checked_count
    )


@router.get("/new", response_model=VacancyFeedResponse)
async def get_new_vacancies() -> VacancyFeedResponse:
    """The accumulating feed the frontend polls to render a running list — populated by
    the background poller and by manual /check-new calls."""
    return VacancyFeedResponse(
        company_id=POLL_COMPANY_ID, jobs=list(_feed), last_checked_at=_last_checked_at
    )


async def poll_loop() -> None:
    """Background task started from FastAPI's lifespan: re-polls Company A on a fixed
    interval, independent of anyone viewing the page. Deliberate, explicit exception to
    the project's usual "no schedulers" rule — see CLAUDE.md, Domain section."""
    global _last_checked_at
    while True:
        try:
            async with SessionLocal() as db:
                new_jobs, _ = await _check_and_record(db)
            _record_in_feed(new_jobs)
            _last_checked_at = datetime.now(UTC)
        except BullhornAuthError:
            log.warning("Company %s: background vacancy poll failed", POLL_COMPANY_ID)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
