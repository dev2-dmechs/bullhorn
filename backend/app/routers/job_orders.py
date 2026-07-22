import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import BullhornAuthError, LiveBullhornClient
from app.database import SessionLocal, get_db
from app.models import JobOrder, JobOrderSeen
from app.routers.companies import to_job_schema
from app.schemas import (
    JobOrderFeedResponse,
    JobOrderSchema,
    JobOrderSyncResponse,
    NewJobOrderCheckResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/job-orders", tags=["job-orders"])

POLL_COMPANY_IDS = ("A", "B")
POLL_INTERVAL_SECONDS = 60
MAX_FEED_SIZE = 500


_feeds: dict[str, list[JobOrderSchema]] = {cid: [] for cid in POLL_COMPANY_IDS}
_last_checked_at: dict[str, datetime | None] = {cid: None for cid in POLL_COMPANY_IDS}


def _validate_company_id(company_id: str) -> str:
    company_id = company_id.upper()
    if company_id not in POLL_COMPANY_IDS:
        raise HTTPException(status_code=404, detail="Company not found")
    return company_id


async def _check_and_record(company_id: str, db: AsyncSession) -> tuple[list[JobOrderSchema], int]:
    client = LiveBullhornClient(company_id=company_id, db=db)
    await client.ensure_job_order_subscription()
    event_ids = await client.poll_job_order_events()

    print("_check_and_record: ")
    print(event_ids)

    if not event_ids:
        return [], 0

    seen = await db.scalars(
        select(JobOrderSeen.bh_job_order_id).where(
            JobOrderSeen.company_id == company_id,
            JobOrderSeen.bh_job_order_id.in_(event_ids),
        )
    )
    seen_ids = set(seen.all())
    unseen_ids = [i for i in event_ids if i not in seen_ids]

    jobs = await client.list_job_orders_by_ids(unseen_ids)

    now = datetime.now(UTC)
    db.add_all(
        JobOrderSeen(company_id=company_id, bh_job_order_id=job["id"], first_seen_at=now)
        for job in jobs
    )
    await db.commit()

    log.info(
        "Company %s: event poll drained %d INSERTED events, %d unseen",
        company_id,
        len(event_ids),
        len(jobs),
    )
    return [to_job_schema(job) for job in jobs], len(event_ids)


async def _store_job_orders(
    company_id: str, jobs_raw: list[dict[str, Any]], db: AsyncSession
) -> None:
    if not jobs_raw:
        return
    now = datetime.now(UTC)
    stmt = pg_insert(JobOrder).values(
        [
            {
                "company_id": company_id,
                "bh_job_order_id": job["id"],
                "data": job,
                "synced_at": now,
            }
            for job in jobs_raw
        ]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[JobOrder.company_id, JobOrder.bh_job_order_id],
        set_={"data": stmt.excluded.data, "synced_at": stmt.excluded.synced_at},
    )
    await db.execute(stmt)
    await db.commit()


def _record_in_feed(company_id: str, new_jobs: list[JobOrderSchema]) -> None:
    if not new_jobs:
        return
    feed = _feeds[company_id]
    feed.extend(new_jobs)
    del feed[:-MAX_FEED_SIZE]


@router.post("/{company_id}/check-new", response_model=NewJobOrderCheckResponse)
async def check_new_job_orders(
    company_id: str, db: AsyncSession = Depends(get_db)
) -> NewJobOrderCheckResponse:
    company_id = _validate_company_id(company_id)
    try:
        new_jobs, checked_count = await _check_and_record(company_id, db)
    except BullhornAuthError as exc:
        log.warning("Company %s: job order poll failed", company_id)
        raise HTTPException(status_code=502, detail="Bullhorn job order poll failed") from exc

    _record_in_feed(company_id, new_jobs)
    _last_checked_at[company_id] = datetime.now(UTC)
    return NewJobOrderCheckResponse(
        company_id=company_id, new_jobs=new_jobs, checked_count=checked_count
    )


@router.get("/{company_id}/new", response_model=JobOrderFeedResponse)
async def get_new_job_orders(company_id: str) -> JobOrderFeedResponse:
    company_id = _validate_company_id(company_id)
    return JobOrderFeedResponse(
        company_id=company_id,
        jobs=list(_feeds[company_id]),
        last_checked_at=_last_checked_at[company_id],
    )


@router.post("/{company_id}/sync", response_model=JobOrderSyncResponse)
async def sync_job_orders(
    company_id: str, db: AsyncSession = Depends(get_db)
) -> JobOrderSyncResponse:
    company_id = _validate_company_id(company_id)
    client = LiveBullhornClient(company_id=company_id, db=db)
    try:
        jobs_raw = await client.list_latest_jobs(count=100)
    except BullhornAuthError as exc:
        raise HTTPException(status_code=502, detail="Bullhorn job order fetch failed") from exc

    await _store_job_orders(company_id, jobs_raw, db)

    return JobOrderSyncResponse(
        company_id=company_id,
        synced_count=len(jobs_raw),
        jobs=[to_job_schema(job) for job in jobs_raw],
    )


@router.get("/{company_id}/stored", response_model=list[JobOrderSchema])
async def list_stored_job_orders(
    company_id: str, db: AsyncSession = Depends(get_db)
) -> list[JobOrderSchema]:
    company_id = _validate_company_id(company_id)
    rows = await db.scalars(
        select(JobOrder)
        .where(JobOrder.company_id == company_id)
        .order_by(JobOrder.synced_at.desc())
    )
    return [to_job_schema(row.data) for row in rows]


async def poll_loop() -> None:
    while True:
        for company_id in POLL_COMPANY_IDS:
            try:
                async with SessionLocal() as db:
                    new_jobs, _ = await _check_and_record(company_id, db)
                _record_in_feed(company_id, new_jobs)
                _last_checked_at[company_id] = datetime.now(UTC)
            except BullhornAuthError:
                log.warning("Company %s: background job order poll failed", company_id)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
