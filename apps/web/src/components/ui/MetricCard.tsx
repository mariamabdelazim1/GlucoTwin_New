export function MetricCard({ label, value, sub, blue = false }: { label: string; value: string; sub?: string; blue?: boolean }) {
  return (
    <div className={`rounded-lg border border-clinical-border bg-white p-4 ${blue ? 'border-t-[3px] border-t-[#70BFE8] shadow-[0_8px_24px_rgba(11,53,85,0.06)]' : ''}`}>
      <p className="text-xs font-semibold uppercase text-clinical-muted">{label}</p>
      <p className="mt-2 text-xl font-bold text-clinical-text">{value}</p>
      {sub ? <p className="mt-1 text-xs text-clinical-muted">{sub}</p> : null}
    </div>
  );
}
