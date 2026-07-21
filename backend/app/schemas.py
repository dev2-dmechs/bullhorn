from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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
    category_ids: list[int] = Field(default_factory=list)
    skill_ids: list[int] = Field(default_factory=list)
    business_sector_ids: list[int] = Field(default_factory=list)
    country_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one_filter(self) -> "CandidateSearchRequest":
        has_filter = (
            self.category_ids or self.skill_ids or self.business_sector_ids or self.country_ids
        )
        if not has_filter:
            raise ValueError(
                "At least one of category, skill, business sector or country is required"
            )
        return self


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


class AddressSchema(BaseModel):
    address1: str | None
    address2: str | None
    city: str | None
    state: str | None
    zip: str | None
    country_id: int | None


class JobOrderSchema(BaseModel):
    id: int
    title: str
    status: str | None
    employment_type: str | None
    is_open: bool | None
    is_public: int | None
    date_added: datetime | None
    date_end: datetime | None
    date_last_published: datetime | None
    start_date: datetime | None
    address: AddressSchema | None
    benefits: str | None
    bonus_package: str | None
    pay_rate: float | None
    salary: float | None
    salary_unit: str | None
    public_description: str | None
    published_zip: str | None
    travel_requirements: str | None
    will_relocate: bool | None
    will_sponsor: bool | None
    years_required: int | None
    category: str | None
    business_sector: str | None
    owner_name: str | None
    published_category: str | None
    response_user_name: str | None
