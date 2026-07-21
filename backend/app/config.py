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

    bh_b_client_id: str = ""
    bh_b_client_secret: str = ""
    bh_b_username: str = ""
    bh_b_password: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-sol"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
