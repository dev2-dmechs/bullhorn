from datetime import datetime

from pydantic import BaseModel, Field


class ConnectionRead(BaseModel):
    company_id: str
    name: str
    configured: bool
    connected: bool
    rest_url_present: bool
    detail: str | None = None


class TaxonomyOption(BaseModel):
    id: int
    name: str


class BusinessSectorsOptions(BaseModel):
    id: int
    name: str
    date_added: str | datetime


class CandidateSearchRequest(BaseModel):
    category_ids: list[int] = Field(min_length=1)
    skill_ids: list[int] = Field(default_factory=list)
    business_sector_ids: list[int] = Field(default_factory=list)


class AnonymisedCandidate(BaseModel):
    external_id: str
    company_id: str
    category: str | None
    business_sector: str | None
    owner_name: str | None


class CandidateSearchResponse(BaseModel):
    company_id: str
    candidates: list[AnonymisedCandidate]
    total_count: int
    capped: bool
