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
    skill_ids: list[int] = Field(default_factory=list)
    business_sector_ids: list[int] = Field(default_factory=list)
    country_ids: list[int] = Field(default_factory=list)
    # Free-text match against the candidate's occupation (job title). Bullhorn has no
    # dedicated "title" field on Candidate — occupation is the closest equivalent and is
    # genuinely indexed for search, unlike skillSet/experience.
    title: str | None = None
    # Free-text role description. Never forwarded to Bullhorn, never persisted — only
    # used as scoring context for the AI match call.
    description: str | None = None
    # How many candidates to fetch/show, chosen by the recruiter. Capped at 50 per the
    # project's non-negotiable per-match-run fetch limit.
    limit: Literal[10, 20, 30, 40, 50] = 10

    @model_validator(mode="after")
    def _at_least_one_filter(self) -> "CandidateSearchRequest":
        has_filter = (
            self.category_ids
            or self.skill_ids
            or self.business_sector_ids
            or self.country_ids
            or (self.title and self.title.strip())
        )
        if not has_filter:
            raise ValueError(
                "At least one of category, skill, business sector, country or title is required"
            )
        return self


class CandidateResume(BaseModel):
    """The identity reveal. The candidate's CV is fetched and parsed live via Bullhorn's
    résumé parser as part of the search response, never persisted (rule 1) and never
    logged (rule 4). Deliberately its own nested type: this is the one point where PII is
    allowed to leave, as a business decision, not the default shape of a candidate
    response. `parsed` is Bullhorn's own structured-candidate output — shape is whatever
    their parser returns, not remodelled here, since exact fields vary by resume."""

    file_name: str
    parsed: dict[str, Any]


class CandidateMatch(BaseModel):
    """`MatchScore` minus `candidate_id` — already keyed onto its `AnonymisedCandidate`."""

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
    """One candidate's contribution to a batched AI match call. `resume` is the
    candidate's already-parsed CV (see CandidateResume.parsed), passed through as-is —
    a deliberate, explicit exception to rule 5 (PII does not leave for the AI vendor),
    confirmed for this call specifically. It may include name/contact/CV content."""

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
    """Structured output shape for one chunked OpenAI match call — one call scores up
    to MATCH_CHUNK_SIZE candidates against the same role at once."""

    results: list[MatchScore]


class NewJobOrderCheckResponse(BaseModel):
    """Result of one on-demand "check for new job orders" poll against one tenant.
    Detection only — these jobs are not matched/scored against candidates yet.
    `checked_count` is the number of INSERTED JobOrder events drained from Bullhorn's
    Entity Events subscription this call, not a tenant-wide total."""

    company_id: str
    new_jobs: list[JobOrderSchema]
    checked_count: int


class JobOrderFeedResponse(BaseModel):
    """The accumulating feed of newly-detected job orders for one tenant, populated by
    the background poller. In-memory only — see app/routers/job_orders.py."""

    company_id: str
    jobs: list[JobOrderSchema]
    last_checked_at: datetime | None


class JobOrderSyncResponse(BaseModel):
    company_id: str
    synced_count: int
    jobs: list[JobOrderSchema]
