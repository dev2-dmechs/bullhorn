import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import candidates, companies, job_orders

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    # The persistent asyncio poll loop only makes sense on a long-lived process. On
    # Vercel each invocation is a fresh, short-lived function — detection there runs
    # via Vercel Cron hitting GET /job-orders/cron/poll instead (see job_orders.py).
    poll_task = None if get_settings().vercel else asyncio.create_task(job_orders.poll_loop())
    try:
        yield
    finally:
        if poll_task is not None:
            poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await poll_task


app = FastAPI(title="Bullhorn Cross-Company Search & Match", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(candidates.router)
app.include_router(job_orders.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
