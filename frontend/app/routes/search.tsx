import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import type { AnonymisedCandidate } from "@/api/client";
import { useBusinessSectors, useCandidateSearch, useCategories, useConnection, useSkills } from "@/api/hooks";
import { StatusDot } from "@/components/StatusDot";
import { clearStoredCompany, getStoredCompany } from "@/lib/storage";

const COMPANY_LABELS: Record<string, string> = { A: "Company A", B: "Company B" };

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

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Bullhorn Cross-Company Search
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Search candidates in one tenant. Names and contact details stay hidden.
          </p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:border-slate-400"
        >
          Log out
        </button>
      </header>

      <CurrentTenant companyId={companyId} />
      <SearchPanel companyId={companyId} />
    </div>
  );
}

function CurrentTenant({ companyId }: { companyId: string }) {
  const { data: connection, isLoading } = useConnection(companyId);

  return (
    <div className="mb-6 inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700">
      {COMPANY_LABELS[companyId] ?? companyId}
      <StatusDot loading={isLoading} connected={connection?.connected} />
    </div>
  );
}

function SearchPanel({ companyId }: { companyId: string }) {
  const { data: categories, isLoading: categoriesLoading } = useCategories(companyId);
  const { data: businessSectors, isLoading: sectorsLoading } = useBusinessSectors(companyId);
  const { data: skills, isLoading: skillsLoading } = useSkills(companyId);

  const [categoryIds, setCategoryIds] = useState<number[]>([]);
  const [businessSectorIds, setBusinessSectorIds] = useState<number[]>([]);
  const [skillIds, setSkillIds] = useState<number[]>([]);

  const search = useCandidateSearch(companyId);

  const canSearch = categoryIds.length > 0 && !search.isPending;

  const categoryOptions = useMemo(
    () => (categories ?? []).map((c) => ({ id: c.id, name: c.name })),
    [categories],
  );
  const sectorOptions = useMemo(
    () => (businessSectors ?? []).map((s) => ({ id: s.id, name: s.name })),
    [businessSectors],
  );
  const skillOptions = useMemo(() => (skills ?? []).map((s) => ({ id: s.id, name: s.name })), [skills]);

  function handleSearch() {
    if (!canSearch) return;
    search.mutate({
      category_ids: categoryIds,
      business_sector_ids: businessSectorIds,
      skill_ids: skillIds,
    });
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MultiSelect
          label="Category"
          required
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
      </div>

      <button
        type="button"
        onClick={handleSearch}
        disabled={!canSearch}
        className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        {search.isPending ? "Searching…" : "Search candidates"}
      </button>
      {categoryIds.length === 0 && (
        <p className="text-xs text-slate-400">Pick at least one category to search.</p>
      )}

      {search.isError && (
        <p className="text-sm text-red-600">{(search.error as Error).message}</p>
      )}

      {search.data && <Results data={search.data} />}
    </div>
  );
}

const MAX_SUGGESTIONS = 25;

function MultiSelect({
  label,
  required,
  loading,
  options,
  selected,
  onChange,
}: {
  label: string;
  required?: boolean;
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
      .filter((o) => !selected.includes(o.id) && o.name.toLowerCase().includes(q))
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
      <label className="mb-1 block text-sm font-medium text-slate-700">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </label>

      <div className="relative">
        <input
          type="text"
          disabled={loading}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={loading ? "Loading…" : `Search ${label.toLowerCase()}…`}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-50"
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
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
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
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700"
            >
              {o.name}
              <button
                type="button"
                onClick={() => removeOption(o.id)}
                className="text-slate-400 hover:text-slate-700"
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
  data: { candidates: AnonymisedCandidate[]; total_count: number; capped: boolean };
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
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Candidate ID</th>
              <th className="px-4 py-2 font-medium">Category</th>
              <th className="px-4 py-2 font-medium">Business sector</th>
              <th className="px-4 py-2 font-medium">Owner</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.candidates.map((c) => (
              <tr key={c.external_id}>
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
