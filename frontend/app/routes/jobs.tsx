import { useQueryClient } from "@tanstack/react-query";
import { type MouseEvent, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import type {
  AnonymisedCandidate,
  CandidateSearchRequest,
  JobOrderSchema,
} from "@/api/client";
import {
  useCandidateSearch,
  useStoredJobOrders,
  useSyncJobOrders,
} from "@/api/hooks";
import { CandidateDetailModal } from "@/components/CandidateDetailModal";
import { ScoreBadge } from "@/components/MatchScore";
import { otherCompany } from "@/lib/companies";

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

function SearchIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.75" />
      <path
        d="M17 17L13.5 13.5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function formatFieldValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatAddress(address: JobOrderSchema["address"]): string {
  if (!address) return "—";
  const street = [address.address1, address.address2]
    .filter(Boolean)
    .join(", ");
  const cityLine = [address.city, address.state, address.zip]
    .filter(Boolean)
    .join(", ");
  const parts = [street, cityLine, address.country_name].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

// Fields most relevant to a recruiter skimming a job order — surfaced directly
// under address instead of wherever they happen to fall in the raw field dump.
const PRIORITY_FIELDS = [
  "description",
  "skills",
  "business_sectors",
  "specialties",
  "categories",
  "owner_name",
  "start_date",
  "date_last_modified",
  "date_added",
  "status",
  "on_site",
  "is_work_from_home",
  "is_open",
  "is_interview_required",
] as const;

function JobFieldsTable({ job }: { job: JobOrderSchema }) {
  const allEntries = Object.entries(job) as [string, unknown][];
  const priorityFields = new Set<string>(PRIORITY_FIELDS);
  const priorityEntries = PRIORITY_FIELDS.map(
    (field) => [field, (job as Record<string, unknown>)[field]] as const,
  );
  const restEntries = allEntries.filter(
    ([field]) => field !== "address" && !priorityFields.has(field),
  );

  return (
    <div className="max-h-[70vh] overflow-y-auto rounded border border-slate-100">
      <table className="w-full text-left text-xs">
        <tbody className="divide-y divide-slate-100">
          <tr>
            <td className="whitespace-nowrap bg-slate-50 px-2 py-1 font-medium text-slate-500">
              address
            </td>
            <td className="wrap-break-word px-2 py-1 text-slate-800">
              {formatAddress(job.address)}
            </td>
          </tr>
          {priorityEntries.map(([field, value]) => (
            <tr key={field} className="bg-brand-teal-light/30">
              <td className="whitespace-nowrap px-2 py-1 font-medium text-brand-teal-dark">
                {field}
              </td>
              <td className="break-all px-2 py-1 text-slate-800">
                {formatFieldValue(value)}
              </td>
            </tr>
          ))}
          {restEntries.map(([field, value]) => (
            <tr key={field}>
              <td className="whitespace-nowrap bg-slate-50 px-2 py-1 font-medium text-slate-500">
                {field}
              </td>
              <td className="break-all px-2 py-1 text-slate-800">
                {formatFieldValue(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobDetailModal({
  job,
  onClose,
}: {
  job: JobOrderSchema;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-brand-navy/30 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-7xl flex-col animate-[panel-in_0.15s_ease-out] overflow-y-auto rounded-xl bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-6 py-4">
          <span className="text-sm font-semibold text-brand-navy">
            {job.title ?? `Job #${job.id}`}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-slate-400 transition hover:text-brand-navy"
          >
            ✕
          </button>
        </div>
        <div className="px-6 py-6">
          <JobFieldsTable job={job} />
        </div>
      </div>
    </div>
  );
}

function buildCandidateSearchPayload(
  job: JobOrderSchema,
): CandidateSearchRequest {
  return {
    // The job order only carries names (not Bullhorn IDs) for these — the backend
    // resolves each against the tenant's cached taxonomy tables.
    category_names: job.categories,
    business_sector_names: job.business_sectors,
    skill_names: job.skills,
    country_ids: job.address?.country_id ? [job.address.country_id] : [],
    title: job.title,
    description: job.description,
    limit: 10,
  };
}

function CandidateResultsModal({
  job,
  candidates,
  onClose,
}: {
  job: JobOrderSchema;
  candidates: AnonymisedCandidate[];
  onClose: () => void;
}) {
  const [scoreDetail, setScoreDetail] = useState<AnonymisedCandidate | null>(
    null,
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-brand-navy/30 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-360 flex-col animate-[panel-in_0.15s_ease-out] overflow-y-auto rounded-xl bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-6 py-4">
          <span className="text-sm font-semibold text-brand-navy">
            Candidates for {job.title ?? `Job #${job.id}`}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-slate-400 transition hover:text-brand-navy"
          >
            ✕
          </button>
        </div>
        <div className="px-6 py-6">
          {candidates.length === 0 ? (
            <p className="text-sm text-slate-400">
              No candidates matched this job's category/skills/sector/title.
            </p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="bg-brand-navy text-slate-200">
                <tr>
                  <th className="px-4 py-2 font-medium">Candidate ID</th>
                  <th className="px-4 py-2 font-medium">AI score</th>
                  <th className="px-4 py-2 font-medium">Title</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                  <th className="px-4 py-2 font-medium">Business sector</th>
                  <th className="px-4 py-2 font-medium">Owner</th>
                  <th className="px-4 py-2 font-medium">Owning company</th>
                  <th className="px-4 py-2 font-medium">CV on file</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {candidates.map((c) => (
                  <tr
                    key={c.external_id}
                    onClick={() => setScoreDetail(c)}
                    className="cursor-pointer transition hover:bg-brand-teal-light/60"
                  >
                    <td className="px-4 py-2 text-slate-400">
                      #{c.external_id}
                    </td>
                    <td className="px-4 py-2">
                      <ScoreBadge score={c.match?.score ?? null} />
                    </td>
                    <td className="px-4 py-2">{c.title ?? "—"}</td>
                    <td className="px-4 py-2">{c.category ?? "—"}</td>
                    <td className="px-4 py-2">{c.business_sector ?? "—"}</td>
                    <td className="px-4 py-2">
                      {c.owner_name ?? "Unassigned"}
                    </td>
                    <td className="px-4 py-2">{c.company_id}</td>
                    <td className="px-4 py-2">{c.resume ? "Yes" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {scoreDetail && (
        <CandidateDetailModal
          candidate={scoreDetail}
          onClose={() => setScoreDetail(null)}
        />
      )}
    </div>
  );
}

function CheckCandidatesButton({
  job,
  candidatePoolCompanyId,
  disabledByOther,
  onStart,
  onSettled,
  onResults,
  onError,
}: {
  job: JobOrderSchema;
  candidatePoolCompanyId: string;
  disabledByOther: boolean;
  onStart: () => void;
  onSettled: () => void;
  onResults: (job: JobOrderSchema, candidates: AnonymisedCandidate[]) => void;
  onError: () => void;
}) {
  const { mutateAsync, isPending } = useCandidateSearch(candidatePoolCompanyId);

  async function handleClick(e: MouseEvent) {
    e.stopPropagation();
    onStart();
    try {
      const result = await mutateAsync(buildCandidateSearchPayload(job));
      onResults(job, result.candidates);
    } catch {
      onError();
    } finally {
      onSettled();
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isPending || disabledByOther}
      className="inline-flex items-center gap-1.5 rounded-full bg-brand-teal px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-brand-teal-dark hover:shadow disabled:cursor-not-allowed disabled:bg-brand-teal/50 disabled:shadow-none disabled:hover:shadow-none"
    >
      {isPending ? <Spinner className="h-3 w-3" /> : <SearchIcon />}
      {isPending ? "Checking…" : "Candidates"}
    </button>
  );
}

function SyncButton({ companyId }: { companyId: string }) {
  const queryClient = useQueryClient();
  const { mutateAsync, isPending } = useSyncJobOrders(companyId);

  async function handleClick() {
    await mutateAsync();
    void queryClient.invalidateQueries({
      queryKey: ["stored-job-orders", companyId],
    });
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isPending}
      className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20 disabled:opacity-60"
    >
      {isPending ? "Syncing…" : "Manual sync from Bullhorn"}
    </button>
  );
}

export default function Jobs() {
  const { companyId } = useParams<{ companyId: string }>();
  const [selected, setSelected] = useState<JobOrderSchema | null>(null);
  const [candidateResults, setCandidateResults] = useState<{
    job: JobOrderSchema;
    candidates: AnonymisedCandidate[];
  } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [activeCheckJobId, setActiveCheckJobId] = useState<number | null>(null);
  const { data, isLoading } = useStoredJobOrders(companyId ?? "");
  const jobs = useMemo(
    () => [...(data ?? [])].sort((a, b) => b.id - a.id),
    [data],
  );
  const candidatePoolCompanyId = otherCompany(companyId ?? "");

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-brand-navy px-6 py-3 shadow-md">
        <div className="mx-auto flex w-full max-w-360 items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="text-sm font-medium text-white/70 transition hover:text-white"
            >
              ← Back
            </Link>
            <h1 className="text-base font-semibold text-white">Job orders</h1>
          </div>
          <SyncButton companyId={companyId ?? ""} />
        </div>
      </header>

      <div className="w-full px-6 py-8">
        {isLoading ? (
          <p className="text-sm text-slate-400">Loading job orders…</p>
        ) : jobs.length === 0 ? (
          <div className="mx-auto w-full max-w-360 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
            <p className="text-sm font-medium text-brand-navy">
              No job orders stored yet
            </p>
            <p className="mt-1 text-sm text-slate-400">
              Click "Sync from Bullhorn" to fetch and store the latest job
              orders for this tenant.
            </p>
          </div>
        ) : (
          <div className="mx-auto w-full max-w-360 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-brand-navy text-slate-200">
                  <tr>
                    <th className="px-4 py-2 font-medium">Job ID</th>
                    <th className="px-4 py-2 font-medium">Title</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Category</th>
                    <th className="px-4 py-2 font-medium text-nowrap">
                      Business sector
                    </th>
                    <th className="px-4 py-2 font-medium">Skills</th>
                    <th className="px-4 py-2 font-medium">Country</th>
                    {/* <th className="px-4 py-2 font-medium">Employment type</th> */}
                    <th className="px-4 py-2 font-medium">Owner</th>
                    <th className="px-4 py-2 font-medium">Date added</th>
                    <th className="px-4 py-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {jobs.map((job) => (
                    <tr
                      key={job.id}
                      onClick={() => setSelected(job)}
                      className="cursor-pointer transition hover:bg-brand-teal-light/60"
                    >
                      <td className="px-4 py-2 text-slate-400">#{job.id}</td>
                      <td className="px-4 py-2">{job.title ?? "—"}</td>
                      <td className="px-4 py-2">{job.status ?? "—"}</td>
                      <td className="px-4 py-2">
                        {job.categories.length
                          ? job.categories.join(", ")
                          : "—"}
                      </td>
                      <td className="px-4 py-2">
                        {job.business_sectors.length
                          ? job.business_sectors.join(", ")
                          : "—"}
                      </td>
                      <td className="px-4 py-2">
                        {job.skills.length ? job.skills.join(", ") : "—"}
                      </td>
                      <td className="px-4 py-2">
                        {job.address?.country_name ?? "—"}
                      </td>
                      {/* <td className="px-4 py-2">
                        {job.employment_type ?? "—"}
                      </td> */}
                      <td className="px-4 py-2">{job.owner_name ?? "—"}</td>
                      <td className="px-4 py-2">
                        {job.date_added
                          ? new Date(job.date_added).toLocaleString()
                          : "—"}
                      </td>
                      <td className="px-4 py-2">
                        <CheckCandidatesButton
                          job={job}
                          candidatePoolCompanyId={candidatePoolCompanyId}
                          disabledByOther={
                            activeCheckJobId !== null &&
                            activeCheckJobId !== job.id
                          }
                          onStart={() => setActiveCheckJobId(job.id)}
                          onSettled={() => setActiveCheckJobId(null)}
                          onResults={(j, candidates) =>
                            setCandidateResults({ job: j, candidates })
                          }
                          onError={() => setToast("Candidate check failed")}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {selected && (
        <JobDetailModal job={selected} onClose={() => setSelected(null)} />
      )}

      {candidateResults && (
        <CandidateResultsModal
          job={candidateResults.job}
          candidates={candidateResults.candidates}
          onClose={() => setCandidateResults(null)}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-[panel-in_0.15s_ease-out] rounded-full bg-brand-navy px-5 py-2.5 text-sm font-medium text-white shadow-xl shadow-brand-navy/30">
          {toast}
        </div>
      )}
    </div>
  );
}
