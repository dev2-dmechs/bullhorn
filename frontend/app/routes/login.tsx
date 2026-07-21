import { useNavigate } from "react-router";
import { useConnection } from "@/api/hooks";
import { StatusDot } from "@/components/StatusDot";
import { setStoredCompany } from "@/lib/storage";

const COMPANIES = [
  { id: "A", label: "Company A" },
  { id: "B", label: "Company B" },
] as const;

export default function Login() {
  const navigate = useNavigate();

  function selectCompany(companyId: string) {
    setStoredCompany(companyId);
    navigate("/search");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-navy px-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        <header className="mb-8 text-center">
          <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-teal text-lg font-bold text-white">
            B
          </div>
          <h1 className="text-2xl font-semibold text-brand-navy">
            Bullhorn Cross-Company Search
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Choose your company. You'll search the other tenant's candidates.
          </p>
        </header>

        <div className="space-y-3">
          {COMPANIES.map((company) => (
            <CompanyOption
              key={company.id}
              companyId={company.id}
              label={company.label}
              onSelect={() => selectCompany(company.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function CompanyOption({
  companyId,
  label,
  onSelect,
}: {
  companyId: string;
  label: string;
  onSelect: () => void;
}) {
  const { data: connection, isLoading } = useConnection(companyId);

  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-brand-navy transition hover:border-brand-teal hover:bg-brand-teal-light"
    >
      {label}
      <StatusDot loading={isLoading} connected={connection?.connected} />
    </button>
  );
}

