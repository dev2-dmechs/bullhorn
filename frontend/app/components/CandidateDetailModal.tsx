import type { AnonymisedCandidate } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { MatchBreakdown, subScoresOf } from "@/components/MatchScore";

function CloseIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M5 5L15 15M15 5L5 15"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-brand-navy">{value ?? "—"}</dd>
    </div>
  );
}

export function CandidateDetailModal({
  candidate,
  onClose,
}: {
  candidate: AnonymisedCandidate;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-brand-navy/30 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col animate-[panel-in_0.15s_ease-out] overflow-y-auto rounded-xl bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-6 py-4">
          <span className="text-sm font-semibold text-brand-navy">
            Candidate #{candidate.external_id}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-slate-400 transition hover:text-brand-navy"
          >
            <CloseIcon />
          </button>
        </div>

        <dl className="space-y-4 px-6 py-6 text-sm">
          <DetailRow label="Title" value={candidate.title} />
          <DetailRow label="Category" value={candidate.category} />
          <DetailRow
            label="Business sector"
            value={candidate.business_sector}
          />
          <DetailRow
            label="Owner"
            value={candidate.owner_name ?? "Unassigned"}
          />
          <DetailRow label="Owning company" value={candidate.company_id} />
          <DetailRow
            label="CV on file"
            value={candidate.resume ? "Yes" : "No"}
          />
          {candidate.match && (
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-500">Match breakdown</dt>
              <dd className="flex gap-2">
                {subScoresOf(candidate.match).map(([label, value]) => (
                  <Badge key={label} className="gap-1 font-bold">
                    {label} {value}
                  </Badge>
                ))}
              </dd>
            </div>
          )}
        </dl>

        {candidate.match && <MatchBreakdown match={candidate.match} />}
      </div>
    </div>
  );
}
