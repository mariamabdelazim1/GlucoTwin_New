import type { Account } from '../../types';
import { PageHeader } from '../../components/ui/PageHeader';

export function AdminDoctors({ accounts }: { accounts: Account[] }) {
  const doctors = accounts.filter((account) => account.role === 'doctor' && account.doctorProfile);
  return <>
    <PageHeader title="Doctors" subtitle="Registered doctors and their professional profiles." />
    <section className="surface overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm">
      <thead className="bg-clinical-secondary text-xs uppercase text-clinical-muted"><tr><th className="px-4 py-3">Doctor</th><th className="px-4 py-3">Specialty</th><th className="px-4 py-3">Experience</th><th className="px-4 py-3">Medical school</th><th className="px-4 py-3">Credentials</th></tr></thead>
      <tbody className="divide-y divide-clinical-border">{doctors.map((doctor) => { const profile = doctor.doctorProfile!; return <tr key={doctor.id}><td className="px-4 py-3 font-semibold">{profile.fullName}<p className="font-normal text-clinical-muted">{doctor.email}</p></td><td className="px-4 py-3">{profile.specialty}</td><td className="px-4 py-3">{profile.yearsExperience} years</td><td className="px-4 py-3">{profile.medicalSchool}</td><td className="px-4 py-3">{profile.certificates.length + (profile.documents ?? []).filter((item) => item.kind === 'certificate').length} certificates, {profile.papers.length + (profile.documents ?? []).filter((item) => item.kind === 'paper').length} papers</td></tr>; })}</tbody>
    </table></section>
  </>;
}
