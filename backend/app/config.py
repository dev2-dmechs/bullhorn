"""All environment access happens here. `os.getenv` anywhere else is a bug."""

from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class TenantCredentials:
    client_id: str
    client_secret: str
    username: str
    password: str
    auth_url: str
    login_url: str

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.username and self.password)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    bullhorn_auth_url: str = "https://auth.bullhornstaffing.com"
    bullhorn_login_url: str = "https://rest.bullhornstaffing.com/rest-services/login"
    bh_a_client_id: str = ""
    bh_a_client_secret: str = ""
    bh_a_username: str = ""
    bh_a_password: str = ""
    # Display name for tenant A — its real Bullhorn org name (e.g. "cmcpartners"), not
    # the generic "Company A" placeholder. Seeded into the `companies` table at startup.
    bh_a_name: str = "Company A"

    bh_b_client_id: str = ""
    bh_b_client_secret: str = ""
    bh_b_username: str = ""
    bh_b_password: str = ""
    bh_b_name: str = "Company B"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-sol"

    # Comma-separated list of allowed CORS origins. Defaults to local Vite dev only;
    # set to the deployed frontend origin(s) in the serverless environment.
    allowed_origins: str = "http://localhost:5173"

    # Vercel sets VERCEL=1 in every serverless function's environment. Used to skip
    # starting the in-process background poller, which cannot survive a serverless
    # function freezing/recycling between invocations — see app/main.py.
    vercel: bool = False

    # Shared secret checked against the `Authorization: Bearer <cron_secret>` header on
    # the cron-triggered poll endpoint, so it can't be hit by anyone who finds the URL.
    cron_secret: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def credentials_for(self, company_id: str) -> TenantCredentials:
        prefix = f"bh_{company_id.lower()}_"
        return TenantCredentials(
            client_id=getattr(self, f"{prefix}client_id"),
            client_secret=getattr(self, f"{prefix}client_secret"),
            username=getattr(self, f"{prefix}username"),
            password=getattr(self, f"{prefix}password"),
            auth_url=self.bullhorn_auth_url,
            login_url=self.bullhorn_login_url,
        )

    def company_name_for(self, company_id: str) -> str:
        return str(getattr(self, f"bh_{company_id.lower()}_name"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
