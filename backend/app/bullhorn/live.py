import asyncio
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
PARSE_TIMEOUT = httpx.Timeout(60.0)
MAX_AUTH_REDIRECTS = 5
PING_PATH = "ping"
MAX_CANDIDATES = 50
MAX_JOB_ORDERS = 500
CANDIDATE_SEARCH_FIELDS = (
    "id,categories,businessSectors,owner,status,occupation,"
    "fileAttachments(id,type,name,contentType)"
)
RESUME_TYPE_MARKERS = ("cv", "resume")

HAS_FILE_ATTACHMENT_CLAUSE = "fileAttachments.id:[1 TO 99999999999]"
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
JOB_ORDER_ID_CHUNK = 200
EVENT_MAX_EVENTS = 100
JOB_ORDER_FIELDS = (
    "id,address(address1,address2,city,state,zip,countryID,countryName),benefits,"
    "billRateCategoryID,"
    "bonusPackage,branchCode,certificationList,clientBillRate,costCenter,degreeList,"
    "description,durationWeeks,educationDegree,employmentType,estimatedEndDate,"
    "externalCategoryID,externalID,feeArrangement,hoursOfOperation,hoursPerWeek,"
    "isClientEditable,isDeleted,isInterviewRequired,isJobcastPublished,isOpen,isPublic,"
    "isWorkFromHome,jobBoardList,jobOrderRateCardID,jobPostingURL,markUpPercentage,"
    "numOpenings,onSite,payRate,publicDescription,publishedZip,reasonClosed,reportTo,"
    "salary,salaryUnit,screenerQuestionsStatus,skillList,source,status,taxRate,taxStatus,"
    "title,travelRequirements,type,willRelocate,willRelocateInt,willSponsor,yearsRequired,"
    "dateAdded,dateClosed,dateEnd,dateLastExported,dateLastModified,dateLastPublished,"
    "startDate,timeAndLaborEnabledDate,"
    "branch(id),clientContact(id),clientCorporation(id),location(id),opportunity(id),"
    "reportToClientContact(id),shift(id),workersCompRate(id),"
    "owner(id,firstName,lastName),responseUser(id,firstName,lastName),"
    "publishedCategory(id,name),categories(id,name),businessSectors(id,name),"
    "skills(id,name),specialties(id,name)"
)


class BullhornAuthError(RuntimeError):
    pass


def find_resume_attachment(attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
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
    return text.replace("\\", "\\\\").replace('"', '\\"')


class LiveBullhornClient:
    def __init__(self, company_id: str, db: AsyncSession) -> None:
        self.company_id = company_id
        self.db = db
        self._db_lock = asyncio.Lock()
        self.creds: TenantCredentials = get_settings().credentials_for(company_id)

    async def _company(self) -> Company:
        async with self._db_lock:
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
        async with self._db_lock:
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
        if not response.text.strip():
            return {}
        payload: dict[str, Any] = response.json()
        return payload

    async def _put(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        token, rest_url = await self._session()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as http:
                response = await http.put(
                    f"{rest_url.rstrip('/')}/{path}", params={**params, "BhRestToken": token}
                )
                if response.status_code == 401:
                    token, rest_url = await self._login()
                    response = await http.put(
                        f"{rest_url.rstrip('/')}/{path}", params={**params, "BhRestToken": token}
                    )
        except httpx.HTTPError as exc:
            raise BullhornAuthError(
                f"Company {self.company_id}: PUT /{path} failed ({exc})"
            ) from exc

        if response.status_code != 200:
            raise BullhornAuthError(
                f"Company {self.company_id}: PUT /{path} failed "
                f"(HTTP {response.status_code}): {response.text}"
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

        print("category_ids *************** : ", category_ids)
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

    def _job_order_subscription_id(self) -> str:
        return f"job-order-poller-{self.company_id}"

    async def ensure_job_order_subscription(self) -> None:

        try:
            await self._put(
                f"event/subscription/{self._job_order_subscription_id()}",
                {"type": "entity", "names": "JobOrder", "eventTypes": "INSERTED"},
            )
        except BullhornAuthError as exc:
            if "already exists" not in str(exc):
                raise

    async def poll_job_order_events(self) -> list[Any]:
        payload = await self._get(
            f"event/subscription/{self._job_order_subscription_id()}",
            {"maxEvents": str(EVENT_MAX_EVENTS)},
        )
        events: list[dict[str, Any]] = payload.get("events", [])
        print("poll_job_order_events:")
        print(events)

        return [
            int(e["entityId"])
            for e in events
            if e.get("entityName") == "JobOrder" and e.get("entityEventType") == "INSERTED"
        ]

    async def list_job_orders_by_ids(self, ids: list[int]) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for i in range(0, len(ids), JOB_ORDER_ID_CHUNK):
            chunk = ids[i : i + JOB_ORDER_ID_CHUNK]
            payload = await self._get(
                "query/JobOrder",
                {
                    "where": f"id IN ({','.join(str(i) for i in chunk)})",
                    "fields": JOB_ORDER_FIELDS,
                    "count": str(len(chunk)),
                },
            )
            collected.extend(payload.get("data", []))
        return collected
