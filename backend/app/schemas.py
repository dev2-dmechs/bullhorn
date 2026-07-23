from datetime import datetime
from typing import Any, Literal

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
    category_names: list[str] = Field(default_factory=list)
    skill_ids: list[int] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    business_sector_ids: list[int] = Field(default_factory=list)
    business_sector_names: list[str] = Field(default_factory=list)
    country_ids: list[int] = Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    limit: Literal[10, 20, 30, 40, 50] = 10

    @model_validator(mode="after")
    def _at_least_one_filter(self) -> "CandidateSearchRequest":
        has_filter = (
            self.category_ids
            or self.category_names
            or self.skill_ids
            or self.skill_names
            or self.business_sector_ids
            or self.business_sector_names
            or self.country_ids
            or (self.title and self.title.strip())
        )
        if not has_filter:
            raise ValueError(
                "At least one of category, skill, business sector, country or title is required"
            )
        return self


class CandidateResume(BaseModel):
    file_name: str
    parsed: dict[str, Any]


class CandidateMatch(BaseModel):
    score: int
    skills_score: int
    experience_score: int
    fit_score: int
    reasons: list[str]


class AnonymisedCandidate(BaseModel):
    external_id: str
    company_id: str
    title: str | None
    category: str | None
    business_sector: str | None
    owner_name: str | None
    resume: CandidateResume | None
    match: CandidateMatch | None = None


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
    country_name: str | None


class JobOrderSchema(BaseModel):
    id: int
    address: AddressSchema | None
    benefits: str | None
    bill_rate_category_id: int | None
    bonus_package: str | None
    branch_code: str | None
    certification_list: str | None
    client_bill_rate: float | None
    cost_center: str | None
    degree_list: str | None
    description: str | None
    duration_weeks: float | None
    education_degree: str | None
    employment_type: str | None
    estimated_end_date: str | None
    external_category_id: int | None
    external_id: str | None
    fee_arrangement: float | None
    hours_of_operation: str | None
    hours_per_week: float | None
    is_client_editable: bool | None
    is_deleted: bool | None
    is_interview_required: bool | None
    is_jobcast_published: bool | None
    is_open: bool | None
    is_public: int | None
    is_work_from_home: bool | None
    job_board_list: str | None
    job_order_rate_card_id: int | None
    job_posting_url: str | None
    mark_up_percentage: float | None
    num_openings: int | None
    on_site: str | None
    pay_rate: float | None
    public_description: str | None
    published_zip: str | None
    reason_closed: str | None
    report_to: str | None
    salary: float | None
    salary_unit: str | None
    screener_questions_status: int | None
    skill_list: str | None
    source: str | None
    status: str | None
    tax_rate: float | None
    tax_status: str | None
    title: str | None
    travel_requirements: str | None
    type: int | None
    will_relocate: bool | None
    will_relocate_int: int | None
    will_sponsor: bool | None
    years_required: int | None
    date_added: datetime | None
    date_closed: datetime | None
    date_end: datetime | None
    date_last_exported: datetime | None
    date_last_modified: datetime | None
    date_last_published: datetime | None
    start_date: datetime | None
    time_and_labor_enabled_date: datetime | None
    branch_id: int | None
    client_contact_id: int | None
    client_corporation_id: int | None
    location_id: int | None
    opportunity_id: int | None
    report_to_client_contact_id: int | None
    shift_id: int | None
    workers_comp_rate_id: int | None
    owner_name: str | None
    response_user_name: str | None
    published_category: str | None
    categories: list[str]
    business_sectors: list[str]
    skills: list[str]
    specialties: list[str]


class MatchCandidateInput(BaseModel):
    candidate_id: str
    resume: dict[str, Any] | None = None


class MatchScore(BaseModel):
    candidate_id: str
    score: int
    skills_score: int
    experience_score: int
    fit_score: int
    reasons: list[str]


class MatchScoreBatchResult(BaseModel):
    results: list[MatchScore]


class NewJobOrderCheckResponse(BaseModel):
    company_id: str
    new_jobs: list[JobOrderSchema]
    checked_count: int


class JobOrderFeedResponse(BaseModel):
    company_id: str
    jobs: list[JobOrderSchema]
    last_checked_at: datetime | None


class JobOrderSyncResponse(BaseModel):
    company_id: str
    synced_count: int
    jobs: list[JobOrderSchema]
