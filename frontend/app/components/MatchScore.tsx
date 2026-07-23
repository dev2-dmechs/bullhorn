import type { CandidateMatch } from "@/api/client";
import { Badge } from "@/components/ui/badge";

// Light background + dark text for every tier — reliable ~5-9:1 contrast regardless
// of hue, unlike solid-color-plus-white-text which measured as low as ~1.76:1 on the
// green-400 tier.
function scoreColorClasses(score: number): string {
  if (score >= 80) return "border-transparent bg-green-200 text-green-900";
  if (score >= 65) return "border-transparent bg-green-100 text-green-700";
  if (score >= 50) return "border-transparent bg-yellow-100 text-yellow-800";
  return "border-transparent bg-red-100 text-red-800";
}

export function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) {
    return <span className="text-slate-300">—</span>;
  }
  return (
    <Badge className={`font-bold ${scoreColorClasses(score)}`}>{score}</Badge>
  );
}

export function subScoresOf(match: CandidateMatch): [string, number][] {
  return [
    ["Skills", match.skills_score],
    ["Experience", match.experience_score],
    ["Fit", match.fit_score],
  ];
}

export function MatchBreakdown({ match }: { match: CandidateMatch }) {
  return (
    <div className="border-t border-slate-200 px-6 py-4">
      <div className="mb-3 flex items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          AI match score
        </span>
        <ScoreBadge score={match.score} />
      </div>
      {match.reasons.length > 0 && (
        <ul className="space-y-1 text-sm text-slate-600">
          {match.reasons.map((reason) => (
            <li key={reason} className="flex gap-2">
              <span className="text-brand-teal">•</span>
              {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
