"""The API contract. This file is the source of truth the frontend generates types from.

REDACTION IS SERVER-SIDE. No response schema here declares a candidate PII field, so no
candidate PII can reach the browser — the network tab is part of the demo surface, and
hiding a field in the UI would not count. That constraint holds trivially today (nothing
fetches a candidate) and must survive the matching work.
"""

from pydantic import BaseModel


class ConnectionRead(BaseModel):
    """Bullhorn auth health for one tenant.

    Deliberately carries no token and no credential — only whether the handshake worked.
    """

    company_id: str
    name: str
    configured: bool
    connected: bool
    rest_url_present: bool
    detail: str | None = None
