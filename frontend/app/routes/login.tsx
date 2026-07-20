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
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <header className="mb-8 text-center">
        <h1 className="text-2xl font-semibold text-slate-900">
          Bullhorn Cross-Company Search
        </h1>
        <p className="mt-1 text-sm text-slate-500">Choose the tenant to search as.</p>
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
      className="flex w-full items-center justify-between rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-400"
    >
      {label}
      <StatusDot loading={isLoading} connected={connection?.connected} />
    </button>
  );
}

