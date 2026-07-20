export function StatusDot({ loading, connected }: { loading: boolean; connected?: boolean }) {
  const color = loading ? "bg-slate-300" : connected ? "bg-emerald-500" : "bg-red-500";
  return (
    <span
      className={`h-2 w-2 rounded-full ${color}`}
      title={connected ? "Connected" : "Not connected"}
    />
  );
}
