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

function seenJobOrdersKey(companyId: string): string {
  return `bullhorn:seen-job-orders:${companyId}`;
}

// The backend's "new job orders" feed is a simple in-memory list that only grows
// (capped, never cleared) — visiting the jobs page doesn't tell the backend anything.
// So "have I seen this one" is tracked client-side instead, keyed by job order id.
export function getSeenJobOrderIds(companyId: string): Set<number> {
  if (typeof window === "undefined") return new Set();
  const raw = window.localStorage.getItem(seenJobOrdersKey(companyId));
  if (!raw) return new Set();
  try {
    return new Set(JSON.parse(raw) as number[]);
  } catch {
    return new Set();
  }
}

export function markJobOrdersSeen(companyId: string, ids: number[]): void {
  if (typeof window === "undefined" || ids.length === 0) return;
  const seen = getSeenJobOrderIds(companyId);
  ids.forEach((id) => seen.add(id));
  window.localStorage.setItem(
    seenJobOrdersKey(companyId),
    JSON.stringify([...seen]),
  );
}
