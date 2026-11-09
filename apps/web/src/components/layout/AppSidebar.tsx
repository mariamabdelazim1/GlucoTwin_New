import { Link, NavLink } from 'react-router-dom';
import { Activity, Bell, LayoutDashboard, LogOut, Menu, MessageSquare, PanelLeftClose, Settings, Shield, Stethoscope, Utensils, UserRound, Users } from 'lucide-react';
import type { Account, Role } from '../../types';
import { Avatar } from '../ui/Avatar';

export function AppSidebar({ role, account, collapsed, mobileOpen, onToggle, onMobileClose, onSignOut }: { role: Role; account?: Account; collapsed: boolean; mobileOpen: boolean; onToggle: () => void; onMobileClose: () => void; onSignOut: () => void }) {
  const doctorItems = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/patients', label: 'Patients', icon: Users },
    { to: '/messages', label: 'Messages', icon: MessageSquare },
    { to: '/notifications', label: 'Notifications', icon: Bell },
    { to: '/profile', label: 'Profile', icon: UserRound },
  ];
  const adminItems = [
    { to: '/admin', label: 'Overview', icon: LayoutDashboard },
    { to: '/admin/doctors', label: 'Doctors', icon: Stethoscope },
    { to: '/admin/patients', label: 'Patients', icon: Users },
    { to: '/admin/assignments', label: 'Doctor Assignments', icon: Shield },
    { to: '/admin/settings', label: 'Settings', icon: Settings },
  ];
  const patientItems = [
    { to: '/patient/dashboard', label: 'My Dashboard', icon: LayoutDashboard },
    { to: '/patient/food', label: 'Food Log', icon: Utensils },
    { to: '/patient/doctors', label: 'Find a Doctor', icon: Stethoscope },
    { to: '/messages', label: 'Messages', icon: MessageSquare },
    { to: '/notifications', label: 'Notifications', icon: Bell },
    { to: '/profile', label: 'Profile', icon: UserRound },
  ];
  const items = role === 'admin' ? adminItems : role === 'patient' ? patientItems : doctorItems;
  const homePath = role === 'patient' ? '/patient/dashboard' : role === 'admin' ? '/admin' : '/dashboard';
  const profileName = role === 'admin' ? 'Administrator' : role === 'patient' ? account?.patientProfile?.fullName || 'Patient' : account?.doctorProfile?.fullName || 'Doctor';
  const profileSub = role === 'patient' ? 'Patient account' : role === 'admin' ? 'System access' : account?.doctorProfile?.specialty || 'Doctor account';
  const profileInitials = profileName.split(/\s+/).map((part) => part[0]).slice(-2).join('').toUpperCase();
  return (
    <>
      <button className="focus-ring fixed left-4 top-4 z-40 rounded-md border border-clinical-border bg-white p-2 text-clinical-text lg:hidden" onClick={onToggle} aria-label="Open navigation">
        <Menu size={20} />
      </button>
      {mobileOpen ? <button className="fixed inset-0 z-30 bg-slate-900/30 lg:hidden" onClick={onMobileClose} aria-label="Close navigation overlay" /> : null}
      <aside className={`fixed inset-y-0 left-0 z-40 flex bg-white transition-transform lg:sticky lg:top-0 lg:h-screen ${collapsed ? 'lg:w-20' : 'lg:w-60'} ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'} w-72 border-r border-clinical-border`}>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-16 items-center gap-3 border-b border-clinical-border px-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-clinical-primary text-white"><Activity size={20} /></div>
            {!collapsed ? <Link to={homePath} className="font-bold leading-tight">Diabetes Digital Twin</Link> : null}
          </div>
          <nav className="flex-1 space-y-1 p-3" aria-label="Primary navigation">
            {items.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} onClick={onMobileClose} className={({ isActive }) => `focus-ring flex items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold ${to === '/profile' ? 'mt-3 border-t border-clinical-border pt-5' : ''} ${isActive ? 'bg-emerald-50 text-clinical-primaryDark' : 'text-clinical-muted hover:bg-clinical-secondary hover:text-clinical-text'}`}>
                <Icon size={19} aria-hidden="true" />
                {!collapsed ? <span>{label}</span> : null}
              </NavLink>
            ))}
          </nav>
          <div className="border-t border-clinical-border p-3">
            <div className="mb-3 flex items-center gap-3 rounded-lg bg-clinical-secondary p-3">
              <Avatar label={profileInitials} size="sm" />
              {!collapsed ? <div className="min-w-0"><p className="truncate text-sm font-semibold">{profileName}</p><p className="text-xs text-clinical-muted">{profileSub}</p></div> : null}
            </div>
            <button onClick={onSignOut} className="focus-ring flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold text-clinical-muted hover:bg-clinical-secondary">
              <LogOut size={18} /> {!collapsed ? 'Logout' : null}
            </button>
          </div>
        </div>
        <button className="focus-ring absolute -right-4 top-20 hidden rounded-full border border-clinical-border bg-white p-2 text-clinical-muted shadow-clinical lg:block" onClick={onToggle} aria-label="Collapse sidebar">
          <PanelLeftClose size={16} />
        </button>
      </aside>
    </>
  );
}
