import { Link, NavLink } from 'react-router-dom';
import { Activity, Bell, LayoutDashboard, LogOut, Menu, MessageSquare, PanelLeftClose, Settings, Shield, Stethoscope, Utensils, UserRound, Users } from 'lucide-react';
import type { Account, Role } from '../../types';
import { Avatar } from '../ui/Avatar';

export function AppSidebar({ role, account, collapsed, mobileOpen, dashboardTheme = false, onToggle, onMobileClose, onSignOut }: { role: Role; account?: Account; collapsed: boolean; mobileOpen: boolean; dashboardTheme?: boolean; onToggle: () => void; onMobileClose: () => void; onSignOut: () => void }) {
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
      <button className={`focus-ring fixed left-4 top-4 z-40 rounded-md border p-2 lg:hidden ${dashboardTheme ? 'border-[#B9D7E9] bg-white text-[#0B3555]' : 'border-clinical-border bg-white text-clinical-text'}`} onClick={onToggle} aria-label="Open navigation">
        <Menu size={20} />
      </button>
      {mobileOpen ? <button className="fixed inset-0 z-30 bg-slate-900/30 lg:hidden" onClick={onMobileClose} aria-label="Close navigation overlay" /> : null}
      <aside className={`fixed inset-y-0 left-0 z-40 flex transition-transform lg:sticky lg:top-0 lg:h-screen ${collapsed ? 'lg:w-20' : 'lg:w-60'} ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'} w-72 border-r ${dashboardTheme ? 'border-[#16496C] bg-[#0B3555] text-white' : 'border-clinical-border bg-white'}`}>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className={`flex h-16 items-center gap-3 border-b px-4 ${dashboardTheme ? 'border-[#16496C]' : 'border-clinical-border'}`}>
            <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-md ${dashboardTheme ? 'bg-[#77C7ED] text-[#07263F]' : 'bg-clinical-primary text-white'}`}><Activity size={20} /></div>
            {!collapsed ? <Link to={homePath} className="font-bold leading-tight">Diabetes Digital Twin</Link> : null}
          </div>
          <nav className="flex-1 space-y-1 p-3" aria-label="Primary navigation">
            {items.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} onClick={onMobileClose} className={({ isActive }) => `focus-ring flex items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold ${to === '/profile' ? `mt-3 border-t pt-5 ${dashboardTheme ? 'border-[#16496C]' : 'border-clinical-border'}` : ''} ${dashboardTheme ? (isActive ? 'bg-[#A9D8F0] text-[#07263F]' : 'text-[#C8DFED] hover:bg-[#16496C] hover:text-white') : (isActive ? 'bg-emerald-50 text-clinical-primaryDark' : 'text-clinical-muted hover:bg-clinical-secondary hover:text-clinical-text')}`}>
                <Icon size={19} aria-hidden="true" />
                {!collapsed ? <span>{label}</span> : null}
              </NavLink>
            ))}
          </nav>
          <div className={`border-t p-3 ${dashboardTheme ? 'border-[#16496C]' : 'border-clinical-border'}`}>
            <div className={`mb-3 flex items-center gap-3 rounded-lg p-3 ${dashboardTheme ? 'bg-[#16496C]' : 'bg-clinical-secondary'}`}>
              <Avatar label={profileInitials} size="sm" />
              {!collapsed ? <div className="min-w-0"><p className="truncate text-sm font-semibold">{profileName}</p><p className={`text-xs ${dashboardTheme ? 'text-[#C8DFED]' : 'text-clinical-muted'}`}>{profileSub}</p></div> : null}
            </div>
            <button onClick={onSignOut} className={`focus-ring flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold ${dashboardTheme ? 'text-[#C8DFED] hover:bg-[#16496C] hover:text-white' : 'text-clinical-muted hover:bg-clinical-secondary'}`}>
              <LogOut size={18} /> {!collapsed ? 'Logout' : null}
            </button>
          </div>
        </div>
        <button className={`focus-ring absolute -right-4 top-20 hidden rounded-full border bg-white p-2 shadow-clinical lg:block ${dashboardTheme ? 'border-[#B9D7E9] text-[#237BB6]' : 'border-clinical-border text-clinical-muted'}`} onClick={onToggle} aria-label="Collapse sidebar">
          <PanelLeftClose size={16} />
        </button>
      </aside>
    </>
  );
}
