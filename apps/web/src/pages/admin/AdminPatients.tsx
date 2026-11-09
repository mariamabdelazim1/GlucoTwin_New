import { useState } from 'react';
import type { Account, CareAssignment, Patient } from '../../types';
import { PageHeader } from '../../components/ui/PageHeader';
import { Badge } from '../../components/ui/Badge';

export function AdminPatients({ accounts, assignments, patientRecords }: { accounts: Account[]; assignments: CareAssignment[]; patientRecords: Patient[] }) {
  const [query, setQuery] = useState('');
  const visible = patientRecords.filter((patient) => patient.name.toLowerCase().includes(query.toLowerCase()));
  return <>
    <PageHeader title="Admin Patients" subtitle="Patient accounts, selected doctors, and care status." />
    <section className="surface mb-5 p-4"><input value={query} onChange={(event) => setQuery(event.target.value)} className="focus-ring w-full max-w-sm rounded-md border border-clinical-border px-3 py-2" placeholder="Search patients" aria-label="Search patients" /></section>
    <section className="surface overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-clinical-secondary text-xs uppercase text-clinical-muted"><tr><th className="px-4 py-3">Patient</th><th className="px-4 py-3">Selected Doctor</th><th className="px-4 py-3">Diabetes Type</th><th className="px-4 py-3">CGM Status</th><th className="px-4 py-3">Care Status</th></tr></thead>
      <tbody className="divide-y divide-clinical-border">{visible.map((patient) => {
        const assignment = assignments.find((item) => item.patientId === patient.slug);
        const doctor = accounts.find((item) => item.id === assignment?.doctorId);
        return <tr key={patient.id}><td className="px-4 py-3 font-semibold">{patient.name}</td><td className="px-4 py-3">{doctor?.doctorProfile?.fullName || patient.doctor || 'Not selected'}</td><td className="px-4 py-3">{patient.diabetesType}</td><td className="px-4 py-3"><Badge>{patient.cgmStatus}</Badge></td><td className="px-4 py-3"><Badge>{assignment?.status || 'Unassigned'}</Badge></td></tr>;
      })}</tbody></table></section>
  </>;
}
