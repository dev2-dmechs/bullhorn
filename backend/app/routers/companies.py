from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.bullhorn.live import LiveBullhornClient
from app.config import get_settings
from app.database import get_db
from app.models import Company
from app.schemas import ConnectionRead

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/{company_id}/connection", response_model=ConnectionRead)
async def check_connection(
    company_id: str, db: AsyncSession = Depends(get_db)
) -> ConnectionRead:
    """Is the Bullhorn OAuth handshake for this tenant working?

    This is the verification surface for the auth integration. It performs a real
    authenticated read against the tenant's Bullhorn and reports whether it succeeded.

    It deliberately returns NO token and NO credential — only whether the handshake worked
    and whether we have a restUrl cached. Tokens are never returned in an API response.
    """
    company = await db.get(Company, company_id.upper())
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

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
