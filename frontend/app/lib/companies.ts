export const COMPANY_LABELS: Record<string, string> = {
  A: "Company A",
  B: "Company B",
};

export function otherCompany(companyId: string): string {
  return companyId === "A" ? "B" : "A";
}
