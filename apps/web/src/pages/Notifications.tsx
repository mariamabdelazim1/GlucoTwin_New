import { useState } from 'react';
import { CheckCheck } from 'lucide-react';
import { initialNotifications } from '../data/notifications';
import { PageHeader } from '../components/ui/PageHeader';
import { Badge } from '../components/ui/Badge';
import type { Role } from '../types';

export function Notifications({ role, patientId, doctorId, visiblePatientIds }: { role: Role; patientId?: string; doctorId: string; visiblePatientIds: string[] }) {
  const [items, setItems] = useState(initialNotifications);
  const visible = items.filter((item) => !item.patientSlug || (role === 'patient' ? item.patientSlug === patientId : item.doctorId === doctorId && visiblePatientIds.includes(item.patientSlug)));
  const groups = ['Today', 'Yesterday', 'Earlier'] as const;
  const hasUnread = visible.some((item) => !item.read);
  return (
    <div className={role === 'patient' ? 'patient-notifications-page' : undefined}>
      <PageHeader title="Notifications" subtitle="Grouped clinical alerts and system notices." actions={<button disabled={!hasUnread} onClick={() => setItems(items.map((item) => visible.some((shown) => shown.id === item.id) ? { ...item, read: true } : item))} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white hover:bg-clinical-primaryDark disabled:cursor-not-allowed disabled:opacity-50"><CheckCheck size={17} /> Mark all as read</button>} />
      <div className="space-y-6">
        {groups.map((group) => (
          visible.some((item) => item.group === group) ? <section key={group} className="surface overflow-hidden">
            <h2 className="border-b border-clinical-border p-4 text-lg font-semibold">{group}</h2>
            <div className="divide-y divide-clinical-border">
              {visible.filter((item) => item.group === group).map((item) => (
                <article key={item.id} className={`notification-row flex min-w-0 flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between ${item.read ? 'bg-white' : role === 'patient' ? 'bg-clinical-secondary' : 'bg-emerald-50'}`}>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><Badge tone={item.type === 'Critical glucose' ? 'border-red-200 bg-red-50 text-red-700' : undefined}>{item.type}</Badge><span className="text-xs text-clinical-muted">{item.time}</span></div>
                    <h3 className="mt-2 font-semibold">{item.title}</h3>
                    <p className="text-sm text-clinical-muted">{item.body}</p>
                  </div>
                  <button disabled={item.read} onClick={() => setItems(items.map((candidate) => candidate.id === item.id ? { ...candidate, read: true } : candidate))} className="focus-ring shrink-0 rounded-md border border-clinical-primary px-3 py-2 text-sm font-semibold text-clinical-primary hover:bg-clinical-secondary disabled:cursor-not-allowed disabled:opacity-50">Mark as read</button>
                </article>
              ))}
            </div>
          </section> : null
        ))}
      </div>
    </div>
  );
}
