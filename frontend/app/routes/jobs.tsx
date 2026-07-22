import { useState } from "react";
import { Link, useParams } from "react-router";
import type { JobOrderSchema } from "@/api/client";
import { useNewJobOrdersFeed } from "@/api/hooks";
import { COMPANY_LABELS } from "@/lib/companies";

function formatFieldValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function JobFieldsTable({ job }: { job: JobOrderSchema }) {
  const entries = Object.entries(job) as [string, unknown][];
  return (
    <div className="max-h-[70vh] overflow-y-auto rounded border border-slate-100">
      <table className="w-full text-left text-xs">
        <tbody className="divide-y divide-slate-100">
          {entries.map(([field, value]) => (
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
        className="flex max-h-[90vh] w-full max-w-2xl flex-col animate-[panel-in_0.15s_ease-out] overflow-y-auto rounded-xl bg-white shadow-2xl"
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

export default function Jobs() {
  const { companyId } = useParams<{ companyId: string }>();
  const [selected, setSelected] = useState<JobOrderSchema | null>(null);
  const { data, isLoading } = useNewJobOrdersFeed(companyId ?? "");
  const jobs = data?.jobs ?? [];

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-brand-navy px-6 py-3 shadow-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="text-sm font-medium text-white/70 transition hover:text-white"
            >
              ← Back
            </Link>
            <h1 className="text-base font-semibold text-white">
              Job orders — {COMPANY_LABELS[companyId ?? ""] ?? companyId}
            </h1>
          </div>
          {data?.last_checked_at && (
            <span className="text-xs text-white/60">
              Last checked {new Date(data.last_checked_at).toLocaleString()}
            </span>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-8">
        {isLoading ? (
          <p className="text-sm text-slate-400">Loading job orders…</p>
        ) : jobs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
            <p className="text-sm font-medium text-brand-navy">
              No job orders detected yet
            </p>
            <p className="mt-1 text-sm text-slate-400">
              The backend polls Bullhorn every 60s — check back shortly, or
              trigger a manual check from the search page.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-brand-navy text-slate-200">
                  <tr>
                    <th className="px-4 py-2 font-medium">Job ID</th>
                    <th className="px-4 py-2 font-medium">Title</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Category</th>
                    <th className="px-4 py-2 font-medium">Business sector</th>
                    <th className="px-4 py-2 font-medium">Employment type</th>
                    <th className="px-4 py-2 font-medium">Owner</th>
                    <th className="px-4 py-2 font-medium">Date added</th>
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
                      <td className="px-4 py-2">{job.category ?? "—"}</td>
                      <td className="px-4 py-2">
                        {job.business_sector ?? "—"}
                      </td>
                      <td className="px-4 py-2">
                        {job.employment_type ?? "—"}
                      </td>
                      <td className="px-4 py-2">{job.owner_name ?? "—"}</td>
                      <td className="px-4 py-2">
                        {job.date_added
                          ? new Date(job.date_added).toLocaleString()
                          : "—"}
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
    </div>
  );
}
