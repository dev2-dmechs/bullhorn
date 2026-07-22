import type { components } from "./schema.d.ts";

const BASE_URL = import.meta.env.VITE_API_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export type ConnectionRead = components["schemas"]["ConnectionRead"];
export type CategorySchema = components["schemas"]["CategorySchema"];
export type BusinessSectorsSchema = components["schemas"]["BusinessSectorsSchema"];
export type TaxonomyOption = components["schemas"]["TaxonomyOption"];
export type CandidateSearchRequest = components["schemas"]["CandidateSearchRequest"];
export type CandidateSearchResponse = components["schemas"]["CandidateSearchResponse"];
export type AnonymisedCandidate = components["schemas"]["AnonymisedCandidate"];
export type CandidateResume = components["schemas"]["CandidateResume"];
export type CandidateMatch = components["schemas"]["CandidateMatch"];
export type NewVacancyCheckResponse = components["schemas"]["NewVacancyCheckResponse"];
export type VacancyFeedResponse = components["schemas"]["VacancyFeedResponse"];
export type JobOrderSchema = components["schemas"]["JobOrderSchema"];

export function getConnection(companyId: string) {
  return request<ConnectionRead>(`/companies/${companyId}/connection`);
}

export function getCategories(companyId: string) {
  return request<CategorySchema[]>(`/companies/${companyId}/categories`);
}

export function getBusinessSectors(companyId: string) {
  return request<BusinessSectorsSchema[]>(`/companies/${companyId}/business-sectors`);
}

export function getSkills(companyId: string) {
  return request<TaxonomyOption[]>(`/companies/${companyId}/skills`);
}

export function getCountries(companyId: string) {
  return request<TaxonomyOption[]>(`/companies/${companyId}/countries`);
}

export function searchCandidates(companyId: string, body: CandidateSearchRequest) {
  return request<CandidateSearchResponse>(`/search/${companyId}/candidates/search`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function checkNewVacancies(companyId: string) {
  return request<NewVacancyCheckResponse>(`/vacancies/${companyId}/check-new`, {
    method: "POST",
  });
}

export function getNewVacancies(companyId: string) {
  return request<VacancyFeedResponse>(`/vacancies/${companyId}/new`);
}
