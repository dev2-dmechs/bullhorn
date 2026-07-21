import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import type { AnonymisedCandidate } from "@/api/client";
import {
  useBusinessSectors,
  useCandidateSearch,
  useCategories,
  useConnection,
  useCountries,
  useSkills,
} from "@/api/hooks";
import { StatusDot } from "@/components/StatusDot";
import { clearStoredCompany, getStoredCompany } from "@/lib/storage";

const COMPANY_LABELS: Record<string, string> = {
  A: "Company A",
  B: "Company B",
};

function otherCompany(companyId: string): string {
  return companyId === "A" ? "B" : "A";
}

export default function Search() {
  const navigate = useNavigate();
  const [companyId, setCompanyId] = useState<string | null>(null);

  useEffect(() => {
    const stored = getStoredCompany();
    if (!stored) {
      navigate("/", { replace: true });
      return;
    }
    setCompanyId(stored);
  }, [navigate]);

  function logout() {
    clearStoredCompany();
    navigate("/", { replace: true });
  }

  if (!companyId) return null;

  const targetCompanyId = otherCompany(companyId);

  return (
    <div className="min-h-screen">
      <header className="bg-brand-navy px-6 py-3">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-teal text-sm font-bold text-white">
              B
            </div>
            <h1 className="text-base font-semibold text-white">
              Bullhorn Cross-Company Search
            </h1>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-lg border border-white/20 px-3 py-1 text-sm text-white transition hover:border-white/40 hover:bg-white/10"
          >
            Log out
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-6 py-8">
        <CurrentTenant
          companyId={companyId}
          targetCompanyId={targetCompanyId}
        />
        <SearchPanel companyId={targetCompanyId} />
      </div>
    </div>
  );
}

function CurrentTenant({
  companyId,
  targetCompanyId,
}: {
  companyId: string;
  targetCompanyId: string;
}) {
  const { data: connection, isLoading } = useConnection(targetCompanyId);

  return (
    <div className="mb-6 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-brand-navy shadow-sm">
      Logged in as {COMPANY_LABELS[companyId] ?? companyId} — searching{" "}
      {COMPANY_LABELS[targetCompanyId] ?? targetCompanyId}
      <StatusDot loading={isLoading} connected={connection?.connected} />
    </div>
  );
}

function SearchPanel({ companyId }: { companyId: string }) {
  const { data: categories, isLoading: categoriesLoading } =
    useCategories(companyId);
  const { data: businessSectors, isLoading: sectorsLoading } =
    useBusinessSectors(companyId);
  const { data: skills, isLoading: skillsLoading } = useSkills(companyId);
  const { data: countries, isLoading: countriesLoading } =
    useCountries(companyId);

  const [categoryIds, setCategoryIds] = useState<number[]>([]);
  const [businessSectorIds, setBusinessSectorIds] = useState<number[]>([]);
  const [skillIds, setSkillIds] = useState<number[]>([]);
  const [countryIds, setCountryIds] = useState<number[]>([]);

  const search = useCandidateSearch(companyId);

  const hasAnyFilter =
    categoryIds.length > 0 ||
    businessSectorIds.length > 0 ||
    skillIds.length > 0 ||
    countryIds.length > 0;
  const canSearch = hasAnyFilter && !search.isPending;

  const categoryOptions = useMemo(
    () => (categories ?? []).map((c) => ({ id: c.id, name: c.name })),
    [categories],
  );
  const sectorOptions = useMemo(
    () => (businessSectors ?? []).map((s) => ({ id: s.id, name: s.name })),
    [businessSectors],
  );
  const skillOptions = useMemo(
    () => (skills ?? []).map((s) => ({ id: s.id, name: s.name })),
    [skills],
  );
  const countryOptions = useMemo(
    () => (countries ?? []).map((c) => ({ id: c.id, name: c.name })),
    [countries],
  );

  function handleSearch() {
    if (!canSearch) return;
    search.mutate({
      category_ids: categoryIds,
      business_sector_ids: businessSectorIds,
      skill_ids: skillIds,
      country_ids: countryIds,
    });
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MultiSelect
          label="Category"
          loading={categoriesLoading}
          options={categoryOptions}
          selected={categoryIds}
          onChange={setCategoryIds}
        />
        <MultiSelect
          label="Business sector"
          loading={sectorsLoading}
          options={sectorOptions}
          selected={businessSectorIds}
          onChange={setBusinessSectorIds}
        />
        <MultiSelect
          label="Skill"
          loading={skillsLoading}
          options={skillOptions}
          selected={skillIds}
          onChange={setSkillIds}
        />
        <MultiSelect
          label="Country"
          loading={countriesLoading}
          options={countryOptions}
          selected={countryIds}
          onChange={setCountryIds}
        />
      </div>

      <button
        type="button"
        onClick={handleSearch}
        disabled={!canSearch}
        className="rounded-lg bg-brand-teal px-5 py-2.5 text-sm font-medium text-white transition hover:bg-brand-teal-dark disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {search.isPending ? "Searching…" : "Search candidates"}
      </button>
      {!hasAnyFilter && (
        <p className="text-xs text-slate-400">
          Pick at least one filter (category, business sector, skill, or country) to search.
        </p>
      )}

      {search.isError && (
        <p className="text-sm text-red-600">
          {(search.error as Error).message}
        </p>
      )}

      {search.data && <Results data={search.data} />}
    </div>
  );
}

const MAX_SUGGESTIONS = 25;
const MAX_CHIP_LABEL_LENGTH = 35;

function truncateLabel(name: string): string {
  return name.length > MAX_CHIP_LABEL_LENGTH
    ? `${name.slice(0, MAX_CHIP_LABEL_LENGTH - 1)}…`
    : name;
}

function MultiSelect({
  label,
  loading,
  options,
  selected,
  onChange,
}: {
  label: string;
  loading: boolean;
  options: { id: number; name: string }[];
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);

  const selectedOptions = options.filter((o) => selected.includes(o.id));

  const matches = useMemo(() => {
    if (query.trim().length === 0) return [];
    const q = query.trim().toLowerCase();
    return options
      .filter(
        (o) => !selected.includes(o.id) && o.name.toLowerCase().includes(q),
      )
      .slice(0, MAX_SUGGESTIONS);
  }, [options, query, selected]);

  function addOption(id: number) {
    onChange([...selected, id]);
    setQuery("");
  }

  function removeOption(id: number) {
    onChange(selected.filter((x) => x !== id));
  }

  const showDropdown = focused && query.trim().length > 0;

  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-brand-navy">{label}</label>

      <div className="relative">
        <input
          type="text"
          disabled={loading}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={loading ? "Loading…" : `Search ${label.toLowerCase()}…`}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20 disabled:opacity-50"
        />

        {showDropdown && (
          <div className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
            {matches.length === 0 ? (
              <p className="px-3 py-2 text-xs text-slate-400">No matches</p>
            ) : (
              matches.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => addOption(o.id)}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-brand-teal-light"
                >
                  {o.name}
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {selectedOptions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {selectedOptions.map((o) => (
            <span
              key={o.id}
              title={o.name}
              className="inline-flex items-center gap-1 rounded-full bg-brand-teal-light px-2.5 py-1 text-xs text-brand-navy"
            >
              {truncateLabel(o.name)}
              <button
                type="button"
                onClick={() => removeOption(o.id)}
                className="shrink-0 text-brand-navy/50 hover:text-brand-navy"
                aria-label={`Remove ${o.name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Results({
  data,
}: {
  data: {
    candidates: AnonymisedCandidate[];
    total_count: number;
    capped: boolean;
  };
}) {
  if (data.candidates.length === 0) {
    return <p className="text-sm text-slate-500">No candidates matched.</p>;
  }

  return (
    <div>
      <p className="mb-3 text-sm text-slate-500">
        {data.total_count} match{data.total_count === 1 ? "" : "es"} in Bullhorn
        {data.capped && ` — showing first ${data.candidates.length}`}
      </p>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-brand-navy text-slate-200">
            <tr>
              <th className="px-4 py-2 font-medium">Candidate ID</th>
              <th className="px-4 py-2 font-medium">Category</th>
              <th className="px-4 py-2 font-medium">Business sector</th>
              <th className="px-4 py-2 font-medium">Owner</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.candidates.map((c) => (
              <tr key={c.external_id} className="hover:bg-brand-teal-light/60">
                <td className="px-4 py-2 text-slate-400">#{c.external_id}</td>
                <td className="px-4 py-2">{c.category ?? "—"}</td>
                <td className="px-4 py-2">{c.business_sector ?? "—"}</td>
                <td className="px-4 py-2">{c.owner_name ?? "Unassigned"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
