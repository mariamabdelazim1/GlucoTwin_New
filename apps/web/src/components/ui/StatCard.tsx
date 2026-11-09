import type { LucideIcon } from 'lucide-react';

export function StatCard({ label, value, icon: Icon, detail }: { label: string; value: string; icon: LucideIcon; detail?: string }) {
  return (
    <article className="surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase text-clinical-muted">{label}</p>
          <p className="mt-2 text-2xl font-bold text-clinical-text">{value}</p>
          {detail ? <p className="mt-1 text-xs text-clinical-muted">{detail}</p> : null}
        </div>
        <div className="rounded-md border border-clinical-border bg-clinical-secondary p-2 text-clinical-primary">
          <Icon size={18} aria-hidden="true" />
        </div>
      </div>
    </article>
  );
}
