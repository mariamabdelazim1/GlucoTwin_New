import { Bell } from 'lucide-react';
import type { Account, Role } from '../../types';
import { Avatar } from '../ui/Avatar';

export function TopHeader({ title, role, account }: { title: string; role: Role; account?: Account }) {
  const name = role === 'admin' ? 'Administrator' : role === 'patient' ? account?.patientProfile?.fullName : account?.doctorProfile?.fullName;
  return (
    <header className="sticky top-0 z-20 border-b border-clinical-border bg-white/95 backdrop-blur">
      <div className="flex min-h-16 items-center justify-between gap-4 px-4 pl-16 lg:pl-6">
        <p className="text-sm font-semibold text-clinical-muted">{title}</p>
        <div className="flex items-center gap-3">
          <button className="focus-ring rounded-md border border-clinical-border p-2 text-clinical-muted" aria-label="Notifications"><Bell size={18} /></button>
          <Avatar label={(name || 'User').split(/\s+/).map((part) => part[0]).slice(-2).join('').toUpperCase()} size="sm" />
        </div>
      </div>
    </header>
  );
}
