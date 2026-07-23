import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import type { AnonymisedCandidate } from "@/api/client";
import {
  useBusinessSectors,
  useCandidateSearch,
  useCategories,
  useCheckNewJobOrders,
  useCompanies,
  useConnection,
  useCountries,
  useNewJobOrdersFeed,
  useSkills,
} from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { CandidateDetailModal } from "@/components/CandidateDetailModal";
import { ScoreBadge } from "@/components/MatchScore";
import { StatusDot } from "@/components/StatusDot";
import { COMPANY_LABELS, otherCompany } from "@/lib/companies";
import {
  getSeenJobOrderIds,
  getStoredCompany,
  setStoredCompany,
} from "@/lib/storage";

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

function SearchIcon({ className = "h-4 w-4" }: { className?: string }) {
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

function FilterIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 5h14M6 10h8M9 15h2"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

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

const DEFAULT_COMPANY = "A";

export default function Search() {
  const [companyId, setCompanyId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const { data: companies } = useCompanies();
  const companyNames = useMemo(
    () => ({
      ...COMPANY_LABELS,
      ...Object.fromEntries((companies ?? []).map((c) => [c.id, c.name])),
    }),
    [companies],
  );

  useEffect(() => {
    setCompanyId(getStoredCompany() ?? DEFAULT_COMPANY);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  function switchTargetCompany(newTargetCompanyId: string) {
    const newLoggedInAs = otherCompany(newTargetCompanyId);
    setStoredCompany(newLoggedInAs);
    setCompanyId(newLoggedInAs);
    setToast(`Logged in as ${companyNames[newLoggedInAs] ?? newLoggedInAs}`);
  }

  if (!companyId) return null;

  const targetCompanyId = otherCompany(companyId);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-brand-navy px-6 py-3 shadow-md">
        <div className="mx-auto flex w-full max-w-360 items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-semibold text-white">
              Bullhorn Cross-Company Search
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <JobOrderPollingControls
              companyId={companyId}
              onResult={setToast}
            />
            <TenantBadge
              targetCompanyId={targetCompanyId}
              companyNames={companyNames}
              onSwitch={switchTargetCompany}
            />
          </div>
        </div>
      </header>

      <div className="w-full px-6 py-8">
        <SearchPanel companyId={targetCompanyId} />
      </div>

      {toast && <Toast message={toast} />}
    </div>
  );
}

function Toast({ message }: { message: string }) {
  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-[panel-in_0.15s_ease-out] rounded-full bg-brand-navy px-5 py-2.5 text-sm font-medium text-white shadow-xl shadow-brand-navy/30">
      {message}
    </div>
  );
}

function JobOrderPollingControls({
  companyId,
  onResult,
}: {
  companyId: string;
  onResult: (message: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      {/* <CheckJobOrdersButton companyId={companyId} onResult={onResult} /> */}
      <NewJobOrdersLink companyId={companyId} />
    </div>
  );
}

function NewJobOrdersLink({ companyId }: { companyId: string }) {
  const { data } = useNewJobOrdersFeed(companyId);
  const seenIds = getSeenJobOrderIds(companyId);
  const count = data?.jobs.filter((j) => !seenIds.has(j.id)).length ?? 0;

  return (
    <Link
      to={`/jobs/${companyId}`}
      className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20"
    >
      Job orders
      {count > 0 && (
        <Badge className="border-transparent bg-brand-teal text-white">
          {count}
        </Badge>
      )}
    </Link>
  );
}

function CheckJobOrdersButton({
  companyId,
  onResult,
}: {
  companyId: string;
  onResult: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const { mutateAsync, isPending } = useCheckNewJobOrders(companyId);

  async function handleClick() {
    try {
      const result = await mutateAsync();
      void queryClient.invalidateQueries({
        queryKey: ["new-job-orders", companyId],
      });
      const count = result.new_jobs.length;
      onResult(
        count === 0
          ? "No new job orders since last check"
          : `${count} new job order${count === 1 ? "" : "s"} found`,
      );
    } catch {
      onResult("Job order check failed");
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isPending}
      className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20 disabled:opacity-60"
    >
      {isPending && <Spinner className="h-3.5 w-3.5" />}
      Check for new job orders
    </button>
  );
}

function TenantBadge({
  targetCompanyId,
  companyNames,
  onSwitch,
}: {
  targetCompanyId: string;
  companyNames: Record<string, string>;
  onSwitch: (targetCompanyId: string) => void;
}) {
  const { data: connection, isLoading } = useConnection(targetCompanyId);

  return (
    <div className="inline-flex items-center gap-2.5 rounded-full bg-white/10 py-1 pl-3.5 pr-2.5 text-sm">
      <span className="text-white/60">Searching</span>
      <Select value={targetCompanyId} onValueChange={onSwitch}>
        <SelectTrigger
          size="sm"
          className="h-6 gap-1 rounded-md border-0 bg-transparent px-1.5 text-sm font-semibold text-white shadow-none hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:ring-offset-0 data-placeholder:text-white [&_svg]:text-white/70"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="end">
          {Object.entries(COMPANY_LABELS).map(([id]) => (
            <SelectItem key={id} value={id}>
              {companyNames[id] ?? id}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <span className="h-4 w-px bg-white/15" />
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
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [limit, setLimit] = useState<10 | 20 | 30 | 40 | 50>(10);
  const [filtersOpen, setFiltersOpen] = useState(true);
  const resultsRef = useRef<HTMLDivElement>(null);

  const search = useCandidateSearch(companyId);

  function toggleFilters() {
    setFiltersOpen((open) => !open);
  }

  useEffect(() => {
    if (!filtersOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setFiltersOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtersOpen]);

  useEffect(() => {
    if (search.data) {
      resultsRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  }, [search.data]);

  const activeFilterCount =
    (categoryIds.length > 0 ? 1 : 0) +
    (businessSectorIds.length > 0 ? 1 : 0) +
    (skillIds.length > 0 ? 1 : 0) +
    (countryIds.length > 0 ? 1 : 0) +
    (title.trim() ? 1 : 0);
  const hasAnyFilter = activeFilterCount > 0;
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
    search.mutate(
      {
        category_ids: categoryIds,
        business_sector_ids: businessSectorIds,
        skill_ids: skillIds,
        country_ids: countryIds,
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        limit,
      },
      { onSuccess: () => setFiltersOpen(false) },
    );
  }

  const activeFilterSummary = [
    title.trim() && `Title: ${title.trim()}`,
    categoryIds.length > 0 &&
      `${categoryIds.length} categor${categoryIds.length === 1 ? "y" : "ies"}`,
    businessSectorIds.length > 0 &&
      `${businessSectorIds.length} business sector${businessSectorIds.length === 1 ? "" : "s"}`,
    skillIds.length > 0 &&
      `${skillIds.length} skill${skillIds.length === 1 ? "" : "s"}`,
    countryIds.length > 0 &&
      `${countryIds.length} countr${countryIds.length === 1 ? "y" : "ies"}`,
  ]
    .filter(Boolean)
    .join(" · ");

  function clearFilters() {
    setCategoryIds([]);
    setBusinessSectorIds([]);
    setSkillIds([]);
    setCountryIds([]);
    setTitle("");
  }

  return (
    <div className="space-y-6">
      <div className="relative">
        {!filtersOpen && (
          <button
            type="button"
            onClick={toggleFilters}
            title={activeFilterSummary || "No filters applied"}
            className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-full bg-brand-teal px-5 py-3 text-sm font-medium text-white shadow-lg transition hover:bg-brand-teal-dark hover:shadow-xl"
          >
            <FilterIcon />
            Filters
            {activeFilterSummary && (
              <span className="max-w-[16rem] truncate text-white/80">
                {activeFilterSummary}
              </span>
            )}
            {activeFilterCount > 0 && (
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-brand-teal">
                {activeFilterCount}
              </span>
            )}
          </button>
        )}

        {filtersOpen && (
          <div className="absolute inset-x-0 top-0 z-20 mx-auto w-full max-w-360 animate-[panel-in_0.15s_ease-out] overflow-hidden rounded-xl bg-white shadow-2xl ring-1 ring-slate-200">
            <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-6 py-4">
              <span className="text-sm font-semibold text-brand-navy">
                Search filters
              </span>
              <div className="flex shrink-0 items-center gap-4">
                {hasAnyFilter && (
                  <button
                    type="button"
                    onClick={clearFilters}
                    className="text-xs font-medium text-slate-400 transition hover:text-brand-navy"
                  >
                    Clear all
                  </button>
                )}
                <button
                  type="button"
                  onClick={toggleFilters}
                  aria-label="Hide filters"
                  className="text-slate-400 transition hover:text-brand-navy"
                >
                  <CloseIcon />
                </button>
              </div>
            </div>

            <div className="max-h-[70vh] space-y-6 overflow-y-auto px-6 pb-6 pt-6">
              <div>
                <label className="mb-1 block text-sm font-medium text-brand-navy">
                  Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Software Engineer"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20"
                />
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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

              <div>
                <label className="mb-1 block text-sm font-medium text-brand-navy">
                  Role description
                </label>
                <AutoGrowTextarea
                  value={description}
                  onChange={setDescription}
                  placeholder="Optional notes about the role — not used to filter this search."
                />
              </div>

              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-brand-navy">
                    Results to show
                  </label>
                  <select
                    value={limit}
                    onChange={(e) =>
                      setLimit(Number(e.target.value) as 10 | 20 | 30 | 40 | 50)
                    }
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20"
                  >
                    {[10, 20, 30, 40, 50].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-1 flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={handleSearch}
                    disabled={!canSearch}
                    className="inline-flex items-center gap-2 rounded-lg bg-brand-teal px-5 py-2.5 text-sm font-medium text-white transition hover:bg-brand-teal-dark disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    {search.isPending ? <Spinner /> : <SearchIcon />}
                    {search.isPending ? "Searching…" : "Search candidates"}
                  </button>
                  {!hasAnyFilter && (
                    <p className="text-xs text-slate-400">
                      Pick at least one filter (title, category, business
                      sector, skill, or country) to search.
                    </p>
                  )}
                </div>
              </div>

              {search.isError && (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                  {(search.error as Error).message}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      <div ref={resultsRef} className="scroll-mt-20">
        {!search.data && !search.isPending && (
          <div className="mx-auto flex w-full max-w-360 flex-col items-center gap-4 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
            <p className="text-sm text-slate-400">
              Choose filters above, then search to see matching candidates.
            </p>
            {!filtersOpen && (
              <button
                type="button"
                onClick={toggleFilters}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-teal px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-teal-dark"
              >
                <FilterIcon />
                Open filters
              </button>
            )}
          </div>
        )}
        {search.isPending && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-400">
            <Spinner />
            Searching Bullhorn…
          </div>
        )}
        {search.data && <Results data={search.data} />}
      </div>
    </div>
  );
}

function AutoGrowTextarea({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={2}
      className="w-full resize-none overflow-hidden rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20"
    />
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
      <label className="mb-1 block text-sm font-medium text-brand-navy">
        {label}
      </label>

      <div className="relative">
        <input
          type="text"
          disabled={loading}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key === "Escape") e.currentTarget.blur();
          }}
          placeholder={loading ? "Loading…" : `Search ${label.toLowerCase()}…`}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 pr-8 text-sm outline-none transition focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20 disabled:opacity-50"
        />
        {loading && (
          <Spinner className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        )}

        {showDropdown && (
          <div className="absolute z-10 mt-1 max-h-56 w-full origin-top animate-[panel-in_0.12s_ease-out] overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
            {matches.length === 0 ? (
              <p className="px-3 py-2 text-xs text-slate-400">No matches</p>
            ) : (
              matches.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => addOption(o.id)}
                  className="block w-full px-3 py-2 text-left text-sm transition-colors hover:bg-brand-teal-light"
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
              className="inline-flex animate-[panel-in_0.15s_ease-out] items-center gap-1 rounded-full bg-brand-teal-light px-2.5 py-1 text-xs text-brand-navy"
            >
              {truncateLabel(o.name)}
              <button
                type="button"
                onClick={() => removeOption(o.id)}
                className="shrink-0 text-brand-navy/50 transition-colors hover:text-brand-navy"
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
  const [selected, setSelected] = useState<AnonymisedCandidate | null>(null);
  const [showExtraFields, setShowExtraFields] = useState(true);
  const { data: companies } = useCompanies();
  const companyNames = useMemo(
    () => Object.fromEntries((companies ?? []).map((c) => [c.id, c.name])),
    [companies],
  );

  function selectCandidate(c: AnonymisedCandidate | null) {
    setSelected(c);
  }

  const sortedCandidates = useMemo(
    () =>
      [...data.candidates].sort(
        (a, b) => (b.match?.score ?? -1) - (a.match?.score ?? -1),
      ),
    [data.candidates],
  );

  if (data.candidates.length === 0) {
    return (
      <div className="mx-auto w-full max-w-360 animate-[panel-in_0.15s_ease-out] rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
        <p className="text-sm font-medium text-brand-navy">
          No candidates matched
        </p>
        <p className="mt-1 text-sm text-slate-400">
          Try widening your filters — fewer categories/skills, or a broader
          title.
        </p>
      </div>
    );
  }

  return (
    <div className="animate-[panel-in_0.15s_ease-out]">
      <div className="mx-auto mb-3 flex w-full max-w-360 items-center justify-between">
        <p className="text-sm text-slate-500">
          <span className="font-semibold text-brand-navy">
            {data.total_count}
          </span>{" "}
          match
          {data.total_count === 1 ? "" : "es"} in Bullhorn
        </p>
        {data.capped && (
          <span className="rounded-full bg-brand-orange/10 px-2.5 py-1 text-xs font-medium text-brand-orange">
            Showing first {data.candidates.length}
          </span>
        )}
      </div>
      <div className="mx-auto mb-3 flex w-full max-w-360 items-center justify-end gap-2">
        <label
          htmlFor="toggle-extra-fields"
          className="text-sm text-slate-500"
        >
          Candidate ID / company
        </label>
        <Switch
          id="toggle-extra-fields"
          checked={showExtraFields}
          onCheckedChange={setShowExtraFields}
        />
      </div>
      <div className="mx-auto w-full max-w-360 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-brand-navy text-slate-200">
              <tr>
                {showExtraFields && (
                  <th className="px-4 py-2 font-medium">Candidate ID</th>
                )}
                <th className="px-4 py-2 font-medium">Score</th>
                <th className="px-4 py-2 font-medium">Title</th>
                <th className="px-4 py-2 font-medium">Category</th>
                <th className="px-4 py-2 font-medium">Business sector</th>
                <th className="px-4 py-2 font-medium">Owner</th>
                {showExtraFields && (
                  <th className="px-4 py-2 font-medium">Company</th>
                )}
                <th className="px-4 py-2 font-medium">CV on file</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sortedCandidates.map((c) => (
                <tr
                  key={c.external_id}
                  onClick={() => selectCandidate(c)}
                  className="cursor-pointer transition hover:bg-brand-teal-light/60"
                >
                  {showExtraFields && (
                    <td className="px-4 py-2 text-slate-400">
                      #{c.external_id}
                    </td>
                  )}
                  <td className="px-4 py-2">
                    <ScoreBadge score={c.match?.score ?? null} />
                  </td>
                  <td className="px-4 py-2">{c.title ?? "—"}</td>
                  <td className="px-4 py-2">{c.category ?? "—"}</td>
                  <td className="px-4 py-2">{c.business_sector ?? "—"}</td>
                  <td className="px-4 py-2">{c.owner_name ?? "Unassigned"}</td>
                  {showExtraFields && (
                    <td className="px-4 py-2">
                      {companyNames[c.company_id] ?? c.company_id}
                    </td>
                  )}
                  <td className="px-4 py-2">
                    {c.resume ? (
                      <span className="inline-flex items-center rounded-full bg-brand-teal-light px-2 py-0.5 text-xs font-medium text-brand-teal-dark">
                        Yes
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <CandidateDetailModal
          candidate={selected}
          onClose={() => selectCandidate(null)}
        />
      )}
    </div>
  );
}
