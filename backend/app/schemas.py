from datetime import datetime

from pydantic import BaseModel, Field


class ConnectionRead(BaseModel):
    company_id: str
    name: str
    configured: bool
    connected: bool
    rest_url_present: bool
    detail: str | None = None


class BaseOption(BaseModel):
    id: int
    name: str


class TaxonomyOption(BaseOption):
    pass


class CategorySchema(BaseOption):
    description: str | None
    enabled: bool
    skills: list[int]
    specialties: list[int]
    type: str | None
    date_added: datetime | None
    occupation: str | None


class BusinessSectorsSchema(BaseOption):
    date_added: datetime | None


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
