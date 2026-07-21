import { useMutation, useQuery } from "@tanstack/react-query";
import {
  type CandidateSearchRequest,
  getBusinessSectors,
  getCategories,
  getConnection,
  getCountries,
  getSkills,
  searchCandidates,
} from "./client";

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
