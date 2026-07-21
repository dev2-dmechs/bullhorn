import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TenantCredentials, get_settings
from app.models import Company

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0)
# Résumé parsing is slower than a normal query/search call — give it more room.
PARSE_TIMEOUT = httpx.Timeout(60.0)
MAX_AUTH_REDIRECTS = 5
PING_PATH = "ping"
MAX_CANDIDATES = 50
CANDIDATE_SEARCH_FIELDS = (
    "id,categories,businessSectors,owner,status,occupation,"
    "fileAttachments(id,type,name,contentType)"
)
RESUME_TYPE_MARKERS = ("cv", "resume")
# Matches any candidate with at least one file attached — Bullhorn has no documented
# boolean "has resume" field on Candidate, but a range query against fileAttachments.id
# matches anything from id 1 upward.
HAS_FILE_ATTACHMENT_CLAUSE = "fileAttachments.id:[1 TO 99999999999]"
# Bullhorn's parseToCandidate `format` param accepts only this fixed set of values.
RESUME_FORMAT_BY_EXTENSION = {
    "pdf": "pdf",
    "doc": "doc",
    "docx": "docx",
    "rtf": "rtf",
    "odt": "odt",
    "txt": "text",
    "html": "html",
    "htm": "html",
}
JOB_ORDER_FIELDS = (
    "id,title,status,employmentType,isOpen,isPublic,dateAdded,dateEnd,dateLastPublished,"
    "startDate,benefits,bonusPackage,payRate,salary,salaryUnit,publicDescription,"
    "publishedZip,travelRequirements,willRelocate,willSponsor,yearsRequired,"
    "address(address1,address2,city,state,zip,countryID),"
    "categories(id,name),businessSectors(id,name),owner(id,firstName,lastName),"
    "publishedCategory(id,name),responseUser(id,firstName,lastName)"
)


class BullhornAuthError(RuntimeError):
    pass


def find_resume_attachment(attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the attachment to treat as the candidate's résumé.

    Prefer one explicitly typed CV/résumé, but `type` is frequently null on this tenant
    even for what's clearly a résumé (e.g. a plain "Firstname Lastname.docx" upload) —
    Bullhorn's own `parsedResumeFile` field, which would normally disambiguate this, is
    unpopulated here too. Since candidate search now only returns candidates with at
    least one file attached (see HAS_FILE_ATTACHMENT_CLAUSE), falling back to "the first
    attachment" is a safe default rather than silently treating them as resume-less."""
    typed_match = next(
        (
            a
            for a in attachments
            if any(marker in (a.get("type") or "").lower() for marker in RESUME_TYPE_MARKERS)
        ),
        None,
    )
    if typed_match is not None:
        return typed_match
    return attachments[0] if attachments else None


def _escape_lucene_phrase(text: str) -> str:
    """Escape a value for embedding in a Lucene double-quoted phrase query."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


class LiveBullhornClient:
    def __init__(self, company_id: str, db: AsyncSession) -> None:
        self.company_id = company_id
        self.db = db
        self.creds: TenantCredentials = get_settings().credentials_for(company_id)

    async def _company(self) -> Company:
        company = await self.db.scalar(select(Company).where(Company.id == self.company_id))
        if company is None:
            raise BullhornAuthError(f"Company {self.company_id} is not seeded")
        return company

    async def _login(self) -> tuple[str, str]:
        if not self.creds.is_configured:
            raise BullhornAuthError(
                f"Company {self.company_id} has no Bullhorn credentials configured"
            )

        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as http:
            auth_endpoint = f"{self.creds.auth_url}/oauth/authorize"
            params = {
                "client_id": self.creds.client_id,
                "response_type": "code",
                "username": self.creds.username,
                "password": self.creds.password,
                "action": "Login",
            }
            code: str | None = None
            for _ in range(MAX_AUTH_REDIRECTS):
                authorize = await http.get(auth_endpoint, params=params)
                location = authorize.headers.get("location")
                if not location:
                    raise BullhornAuthError(
                        f"Company {self.company_id}: authorize step returned no redirect "
                        f"(HTTP {authorize.status_code}) — check the client_id and password"
                    )

                target = httpx.URL(location)
                code = target.params.get("code")
                if code:
                    break

                auth_endpoint = str(target.copy_with(query=None))
                log.info("Bullhorn redirected company %s to %s", self.company_id, target.host)
            else:
                raise BullhornAuthError(
                    f"Company {self.company_id}: authorize step never returned a code "
                    f"after {MAX_AUTH_REDIRECTS} redirects"
                )

            token_host = str(httpx.URL(auth_endpoint).copy_with(path="/oauth/token", query=None))

            token_response = await http.post(
                token_host,
                params={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.creds.client_id,
                    "client_secret": self.creds.client_secret,
                },
                follow_redirects=True,  # this one may also bounce to the regional host
            )
            if token_response.status_code != 200:
                raise BullhornAuthError(
                    f"Company {self.company_id}: token exchange failed "
                    f"(HTTP {token_response.status_code})"
                )
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise BullhornAuthError(f"Company {self.company_id}: no access_token returned")

            login = await http.get(
                self.creds.login_url,
                params={"version": "*", "access_token": access_token},
                follow_redirects=True,
            )
            if login.status_code != 200:
                raise BullhornAuthError(
                    f"Company {self.company_id}: rest login failed (HTTP {login.status_code})"
                )
            payload = login.json()
            bh_rest_token = payload.get("BhRestToken")
            rest_url = payload.get("restUrl")
            if not bh_rest_token or not rest_url:
                raise BullhornAuthError(
                    f"Company {self.company_id}: login response missing BhRestToken or restUrl"
                )

        company = await self._company()
        company.bh_rest_token = bh_rest_token
        company.rest_url = rest_url
        company.token_updated_at = datetime.now(UTC)
        await self.db.commit()

        log.info("Bullhorn login succeeded for company %s", self.company_id)
        return str(bh_rest_token), str(rest_url)

    async def _session(self) -> tuple[str, str]:
        company = await self._company()
        if company.bh_rest_token and company.rest_url:
            return company.bh_rest_token, company.rest_url
        return await self._login()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        token, rest_url = await self._session()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as http:
                response = await http.get(
                    f"{rest_url.rstrip('/')}/{path}", params={**params, "BhRestToken": token}
                )

                if response.status_code == 401:
                    log.info(
                        "Bullhorn token expired for company %s; re-authenticating",
                        self.company_id,
                    )
                    token, rest_url = await self._login()
                    response = await http.get(
                        f"{rest_url.rstrip('/')}/{path}", params={**params, "BhRestToken": token}
                    )
        except httpx.HTTPError as exc:
            raise BullhornAuthError(
                f"Company {self.company_id}: GET /{path} failed ({exc})"
            ) from exc

        if response.status_code != 200:
            raise BullhornAuthError(
                f"Company {self.company_id}: GET /{path} failed (HTTP {response.status_code})"
            )
        payload: dict[str, Any] = response.json()
        return payload

    async def check_connection(self) -> tuple[bool, str | None]:
        if not self.creds.is_configured:
            return False, "no credentials configured for this tenant"
        try:
            await self._get(PING_PATH, {})
        except BullhornAuthError as exc:
            return False, str(exc)
        except httpx.HTTPError:
            return False, "could not reach Bullhorn"
        return True, None

    async def list_categories(self) -> list[dict[str, Any]]:
        payload = await self._get(
            "query/Category",
            {
                "where": "enabled=true",
                "fields": "id,name,occupation,description,type,skills,specialties,enabled,dateAdded",  # noqa: E501
                "count": "500",
            },
        )
        data: list[dict[str, Any]] = payload.get("data", [])
        return data

    async def list_business_sectors(self) -> list[dict[str, Any]]:
        payload = await self._get(
            "query/BusinessSector",
            {"where": "id>0", "enabled": True, "fields": "id,name,dateAdded", "count": "500"},
        )
        data: list[dict[str, Any]] = payload.get("data", [])
        return data

    async def list_skills(self) -> list[dict[str, Any]]:
        payload = await self._get(
            "query/Skill",
            {"where": "id>0", "enabled": True, "fields": "id,name", "count": "500"},
        )
        data: list[dict[str, Any]] = payload.get("data", [])
        return data

    async def search_candidates(
        self,
        category_ids: list[int] | None = None,
        skill_ids: list[int] | None = None,
        business_sector_ids: list[int] | None = None,
        country_ids: list[int] | None = None,
        title: str | None = None,
        limit: int = MAX_CANDIDATES,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = min(limit, MAX_CANDIDATES)
        clauses = []
        if category_ids:
            clauses.append(f"categories.id:({' OR '.join(str(i) for i in category_ids)})")
        if skill_ids:
            clauses.append(f"primarySkills.id:({' OR '.join(str(i) for i in skill_ids)})")
        if business_sector_ids:
            clauses.append(
                f"businessSectors.id:({' OR '.join(str(i) for i in business_sector_ids)})"
            )
        if country_ids:
            clauses.append(f"address.country.id:({' OR '.join(str(i) for i in country_ids)})")
        if title and title.strip():
            clauses.append(f'occupation:"{_escape_lucene_phrase(title.strip())}"')
        if not clauses:
            raise ValueError("search_candidates requires at least one filter")

        clauses.append(HAS_FILE_ATTACHMENT_CLAUSE)
        query = " AND ".join(clauses)

        collected: list[dict[str, Any]] = []
        total = 0
        start = 0
        while len(collected) < limit:
            payload = await self._get(
                "search/Candidate",
                {
                    "query": query,
                    "fields": CANDIDATE_SEARCH_FIELDS,
                    "count": str(limit - len(collected)),
                    "start": str(start),
                    # Explicit, not just relying on Bullhorn's default: best-matching
                    # candidates first.
                    "orderBy": "-_score",
                },
            )
            data: list[dict[str, Any]] = payload.get("data", [])
            total = payload.get("total", len(data))
            if not data:
                break
            collected.extend(data)
            start += len(data)
            if start >= total:
                break

        return collected, total

    async def download_candidate_file(
        self, candidate_id: str, file_id: int | str
    ) -> tuple[bytes, str]:
        """Download raw file bytes for a candidate's attachment (e.g. their CV). Never
        persisted and never logged — the caller must only log `candidate_id`, never this
        content. Attachment id/name/type come from the caller (already fetched as part of
        the candidate search) — this issues one GET, not a second lookup."""
        token, rest_url = await self._session()
        path = f"file/Candidate/{candidate_id}/{file_id}/raw"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as http:
                response = await http.get(
                    f"{rest_url.rstrip('/')}/{path}", params={"BhRestToken": token}
                )
                if response.status_code == 401:
                    token, rest_url = await self._login()
                    response = await http.get(
                        f"{rest_url.rstrip('/')}/{path}", params={"BhRestToken": token}
                    )
        except httpx.HTTPError as exc:
            raise BullhornAuthError(
                f"Company {self.company_id}: file download failed ({exc})"
            ) from exc

        if response.status_code != 200:
            raise BullhornAuthError(
                f"Company {self.company_id}: file download failed (HTTP {response.status_code})"
            )

        content_type = response.headers.get("content-type", "application/octet-stream")
        return response.content, content_type

    async def parse_resume(
        self, content: bytes, file_name: str, content_type: str
    ) -> dict[str, Any]:
        """POST an already-downloaded CV to Bullhorn's résumé parser and return the
        structured candidate data it extracts.

        Deliberate, scoped exception to the read-only rule: every other method here issues
        GET only. This one POSTs, but `/resume/parseToCandidate` is parse-only — it reads
        the uploaded file and returns structured JSON, it does not create, update, or
        persist a Candidate (or any other entity) in Bullhorn. No entity id is referenced
        in the request; there is nothing in Bullhorn for this call to mutate.
        Never persisted and never logged — the caller must only log `candidate_id`, never
        this content.

        Per Bullhorn's docs, this is multipart/form-data with a `file` field — not a raw
        body — and `format` must be one of a fixed set of values, not an arbitrary
        extension."""
        token, rest_url = await self._session()
        extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        file_format = RESUME_FORMAT_BY_EXTENSION.get(extension, "pdf")
        path = "resume/parseToCandidate"

        async def _post(tok: str, url: str) -> httpx.Response:
            async with httpx.AsyncClient(timeout=PARSE_TIMEOUT) as http:
                return await http.post(
                    f"{url.rstrip('/')}/{path}",
                    params={"BhRestToken": tok, "format": file_format},
                    files={"file": (file_name, content, content_type)},
                )

        try:
            response = await _post(token, rest_url)
            if response.status_code == 401:
                token, rest_url = await self._login()
                response = await _post(token, rest_url)
        except httpx.HTTPError as exc:
            raise BullhornAuthError(
                f"Company {self.company_id}: resume parse failed ({exc})"
            ) from exc

        if response.status_code != 200:
            raise BullhornAuthError(
                f"Company {self.company_id}: resume parse failed (HTTP {response.status_code})"
            )
        payload: dict[str, Any] = response.json()
        return payload

    async def list_countries(self) -> list[dict[str, Any]]:
        payload = await self._get("options/Country", {"count": "500", "start": "0"})
        options: list[dict[str, Any]] = payload.get("data", [])
        if not options:
            log.warning("Company %s: no options returned for Country", self.company_id)
        return options

    async def list_latest_jobs(self, count: int = 10) -> list[dict[str, Any]]:
        payload = await self._get(
            "query/JobOrder",
            {
                "where": "id>0",
                "fields": JOB_ORDER_FIELDS,
                "orderBy": "-dateAdded",
                "count": str(count),
            },
        )
        data: list[dict[str, Any]] = payload.get("data", [])
        return data
