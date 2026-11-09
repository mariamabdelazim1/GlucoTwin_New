import type { Account, CareAssignment, Patient } from '../../types';
import { PageHeader } from '../../components/ui/PageHeader';
import { Badge } from '../../components/ui/Badge';

export function AdminAssignments({ accounts, assignments, patientRecords }: { accounts: Account[]; assignments: CareAssignment[]; patientRecords: Patient[] }) {
  return <>
    <PageHeader title="Doctor Assignments" subtitle="Patient doctor choices and request status." />
    <section className="surface overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead className="bg-clinical-secondary text-xs uppercase text-clinical-muted"><tr><th className="px-4 py-3">Patient</th><th className="px-4 py-3">Selected Doctor</th><th className="px-4 py-3">Status</th></tr></thead>
      <tbody className="divide-y divide-clinical-border">{assignments.map((assignment) => <tr key={`${assignment.patientId}-${assignment.doctorId}`}><td className="px-4 py-3 font-semibold">{patientRecords.find((patient) => patient.slug === assignment.patientId)?.name || 'Patient'}</td><td className="px-4 py-3">{accounts.find((account) => account.id === assignment.doctorId)?.doctorProfile?.fullName || 'Doctor'}</td><td className="px-4 py-3"><Badge>{assignment.status}</Badge></td></tr>)}</tbody>
    </table></section>
  </>;
}
