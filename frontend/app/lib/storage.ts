const COMPANY_KEY = "bullhorn:company";

export function getStoredCompany(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(COMPANY_KEY);
}

export function setStoredCompany(companyId: string): void {
  window.localStorage.setItem(COMPANY_KEY, companyId);
}

export function clearStoredCompany(): void {
  window.localStorage.removeItem(COMPANY_KEY);
}
