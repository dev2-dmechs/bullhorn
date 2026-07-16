"""The live Bullhorn integration. Used only for final verification and the demo.

Auth: OAuth 2.0 password grant, per tenant.
    GET  {auth_url}/oauth/authorize   -> 302, `code` in the Location header
    POST {auth_url}/oauth/token       -> access_token
    GET  {login_url}                  -> BhRestToken + restUrl

`restUrl` is returned by login and varies per tenant and data centre. It is read from the
response and cached on the companies row. It is NEVER hardcoded.

READ-ONLY: every call against the Bullhorn REST *data* API is a GET.

    ⚠️  ONE EXCEPTION, and it needs a decision. The OAuth token exchange
        (POST {auth_url}/oauth/token) is a POST. Bullhorn's token endpoint requires it —
        there is no GET form. Rule 3 as written in CLAUDE.md says "Never POST ... against
        any Bullhorn API", which forbids the very handshake CLAUDE.md's own auth section
        mandates. The intent of rule 3 is plainly "never mutate client data", and a token
        exchange mutates nothing. Rule 3 should be narrowed to say so explicitly.

Tokens and credentials are never logged, never returned in an API response.
"""

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

# auth.bullhornstaffing.com bounces a tenant to its regional data centre (auth-emea,
# auth-west, ...) before it will issue an auth code. We walk that chain rather than
# hardcoding a regional host, so the same code works for either tenant on any data centre.
MAX_AUTH_REDIRECTS = 5

# Bullhorn's cheapest authenticated read. Returns {"sessionExpires": <epoch ms>} and touches
# no client data. Used to prove the BhRestToken can actually *read*, not merely that Bullhorn
# issued one.
PING_PATH = "ping"


class BullhornAuthError(RuntimeError):
    """Bullhorn authentication failed. Carries no credential or token."""


class LiveBullhornClient:
    def __init__(self, company_id: str, db: AsyncSession) -> None:
        self.company_id = company_id
        self.db = db
        self.creds: TenantCredentials = get_settings().credentials_for(company_id)

    # ---- auth -----------------------------------------------------------------

    async def _company(self) -> Company:
        company = await self.db.scalar(select(Company).where(Company.id == self.company_id))
        if company is None:
            raise BullhornAuthError(f"Company {self.company_id} is not seeded")
        return company

    async def _login(self) -> tuple[str, str]:
        """Run the full OAuth handshake. Returns (BhRestToken, restUrl) and caches both."""
        if not self.creds.is_configured:
            raise BullhornAuthError(
                f"Company {self.company_id} has no Bullhorn credentials configured"
            )

        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as http:
            # 1. Authorize. Bullhorn answers with a redirect carrying ?code=...
            #
            # We cannot simply follow redirects here: the auth code arrives in a Location
            # header, and httpx would follow it away and we would never see it. But we
            # cannot refuse redirects either — auth.bullhornstaffing.com 307s a tenant to
            # its regional data centre (Goodall Brazier is on auth-emea), and that hop has
            # no code on it. So we walk the chain by hand and stop at the first Location
            # that actually carries a code.
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

                # A data-centre bounce. Re-issue against the host Bullhorn sent us to.
                # The credentials ride along in `params`, so drop whatever it echoed back
                # in the query string rather than sending them twice.
                auth_endpoint = str(target.copy_with(query=None))
                log.info(
                    "Bullhorn redirected company %s to %s", self.company_id, target.host
                )
            else:
                raise BullhornAuthError(
                    f"Company {self.company_id}: authorize step never returned a code "
                    f"after {MAX_AUTH_REDIRECTS} redirects"
                )

            # The token endpoint lives on the same host that finally issued the code.
            token_host = str(httpx.URL(auth_endpoint).copy_with(path="/oauth/token", query=None))

            # 2. Exchange the code for an access token. See the POST carve-out above.
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

            # 3. Log in to the REST service. This is where restUrl comes from.
            # rest.bullhornstaffing.com bounces to the regional host the same way, and
            # here we want the final JSON rather than the redirect, so just follow it.
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
        """Cached (BhRestToken, restUrl), logging in only if we don't have one."""
        company = await self._company()
        if company.bh_rest_token and company.rest_url:
            return company.bh_rest_token, company.rest_url
        return await self._login()

    # ---- read-only data access -------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET against the Bullhorn REST API, re-authenticating once on a 401.

        This is the single choke point for every Bullhorn read. On failure we surface our
        own error — we never let an upstream Bullhorn error body reach the client or the
        log, because it can carry candidate data or token material.
        """
        token, rest_url = await self._session()

        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            response = await http.get(
                f"{rest_url.rstrip('/')}/{path}", params={**params, "BhRestToken": token}
            )

            if response.status_code == 401:
                log.info(
                    "Bullhorn token expired for company %s; re-authenticating", self.company_id
                )
                token, rest_url = await self._login()
                response = await http.get(
                    f"{rest_url.rstrip('/')}/{path}", params={**params, "BhRestToken": token}
                )

        if response.status_code != 200:
            raise BullhornAuthError(
                f"Company {self.company_id}: GET /{path} failed (HTTP {response.status_code})"
            )
        payload: dict[str, Any] = response.json()
        return payload

    async def check_connection(self) -> tuple[bool, str | None]:
        """Prove this tenant's token can actually read from Bullhorn.

        Deliberately an authenticated GET rather than a bare login. A successful login only
        proves Bullhorn *issued* a token; it does not prove the token, the restUrl or the
        cached-session path work. Going through `_get` exercises all three, plus the 401
        re-login — the whole flow, end to end.
        """
        if not self.creds.is_configured:
            return False, "no credentials configured for this tenant"
        try:
            await self._get(PING_PATH, {})
        except BullhornAuthError as exc:
            return False, str(exc)
        except httpx.HTTPError:
            return False, "could not reach Bullhorn"
        return True, None
