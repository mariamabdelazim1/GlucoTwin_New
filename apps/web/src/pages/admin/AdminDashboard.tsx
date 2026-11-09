import { Activity, Radio, Stethoscope, Users } from 'lucide-react';
import type { Account, CareAssignment, Patient } from '../../types';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatCard } from '../../components/ui/StatCard';

export function AdminDashboard({ accounts, assignments, patientRecords }: { accounts: Account[]; assignments: CareAssignment[]; patientRecords: Patient[] }) {
  const doctors = accounts.filter((account) => account.role === 'doctor');
  const recentAccounts = accounts.filter((account) => account.id !== 'DR-001' && account.id !== 'omar-hassan').slice(-3).reverse();
  const recentAssignments = assignments.slice(-3).reverse();
  return <>
    <PageHeader title="Admin Overview" subtitle="Doctors, patients, assignments, and CGM connectivity." />
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="Registered Doctors" value={String(doctors.length)} icon={Stethoscope} />
      <StatCard label="Patient Records" value={String(patientRecords.length)} icon={Users} />
      <StatCard label="Accepted Patients" value={String(assignments.filter((item) => item.status === 'accepted').length)} icon={Activity} />
      <StatCard label="CGM Connections" value={String(patientRecords.filter((item) => item.usesCgm).length)} icon={Radio} />
    </div>
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <section className="surface p-4"><h2 className="text-lg font-semibold">Recent registrations</h2><div className="mt-4 space-y-3">{recentAccounts.length ? recentAccounts.map((item) => <p key={item.id} className="rounded-md border border-clinical-border p-3 text-sm">{item.role === 'doctor' ? item.doctorProfile?.fullName : item.patientProfile?.fullName} joined as a {item.role}</p>) : <p className="text-sm text-clinical-muted">No new registrations.</p>}</div></section>
      <section className="surface p-4"><h2 className="text-lg font-semibold">Recent assignments</h2><div className="mt-4 space-y-3">{recentAssignments.map((item) => <p key={`${item.patientId}-${item.doctorId}`} className="rounded-md border border-clinical-border p-3 text-sm">{patientRecords.find((patient) => patient.slug === item.patientId)?.name || 'Patient'} to {doctors.find((doctor) => doctor.id === item.doctorId)?.doctorProfile?.fullName || 'Doctor'} <span className="text-clinical-muted">({item.status})</span></p>)}</div></section>
    </div>
  </>;
}
