export function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-clinical-border bg-white p-4">
      <p className="text-xs font-semibold uppercase text-clinical-muted">{label}</p>
      <p className="mt-2 text-xl font-bold text-clinical-text">{value}</p>
      {sub ? <p className="mt-1 text-xs text-clinical-muted">{sub}</p> : null}
    </div>
  );
}
