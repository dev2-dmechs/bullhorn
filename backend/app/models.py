"""SQLAlchemy models.

ONE TABLE. The matching tables (`match_runs`, `match_results`, `vacancies_seen`) are
specified in `.claude/CLAUDE.md` and will land with the matching work. Nothing in this
application fetches a candidate today, so nothing needs storing.

NO CANDIDATE PII, ever — not as a column, not inside a JSONB column.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Company(Base):
    """Tenant config and Bullhorn token state.

    The BhRestToken is persisted deliberately: Bullhorn rate-limits logins, so a restart
    should not force a re-authentication. It is never logged and never returned by any
    response schema.
    """

    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(1), primary_key=True)  # 'A' | 'B'
    name: Mapped[str] = mapped_column(String(100))

    # Returned by /rest-services/login and varies per tenant/data centre. Never hardcoded.
    rest_url: Mapped[str | None] = mapped_column(String(255), default=None)
    bh_rest_token: Mapped[str | None] = mapped_column(String(255), default=None)
    token_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
