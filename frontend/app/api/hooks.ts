import { useMutation, useQuery } from "@tanstack/react-query";
import {
  type CandidateSearchRequest,
  checkNewVacancies,
  getBusinessSectors,
  getCategories,
  getConnection,
  getCountries,
  getNewVacancies,
  getSkills,
  searchCandidates,
} from "./client";

// The backend re-polls Bullhorn every 60s (see POLL_INTERVAL_SECONDS in
// app/routers/vacancies.py) — poll a bit more often so the UI picks up a fresh feed
// shortly after the backend does, without hammering our own API.
const VACANCY_FEED_REFETCH_MS = 15_000;

export function useConnection(companyId: string) {
  return useQuery({
    queryKey: ["connection", companyId],
    queryFn: () => getConnection(companyId),
  });
}

export function useCategories(companyId: string) {
  return useQuery({
    queryKey: ["categories", companyId],
    queryFn: () => getCategories(companyId),
  });
}

export function useBusinessSectors(companyId: string) {
  return useQuery({
    queryKey: ["business-sectors", companyId],
    queryFn: () => getBusinessSectors(companyId),
  });
}

export function useSkills(companyId: string) {
  return useQuery({
    queryKey: ["skills", companyId],
    queryFn: () => getSkills(companyId),
  });
}

export function useCountries(companyId: string) {
  return useQuery({
    queryKey: ["countries", companyId],
    queryFn: () => getCountries(companyId),
  });
}

export function useCandidateSearch(companyId: string) {
  return useMutation({
    mutationFn: (body: CandidateSearchRequest) => searchCandidates(companyId, body),
  });
}

export function useCheckNewVacancies(companyId: string) {
  return useMutation({
    mutationFn: () => checkNewVacancies(companyId),
  });
}

export function useNewVacanciesFeed(companyId: string) {
  return useQuery({
    queryKey: ["new-vacancies", companyId],
    queryFn: () => getNewVacancies(companyId),
    refetchInterval: VACANCY_FEED_REFETCH_MS,
  });
}
