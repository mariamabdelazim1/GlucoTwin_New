import { useMemo, useState } from 'react';
import type { Patient } from '../types';
import { PageHeader } from '../components/ui/PageHeader';
import { PatientTable } from '../components/patients/PatientTable';

export function Patients({ acceptedPatientSlugs, patientRecords }: { acceptedPatientSlugs: string[]; patientRecords: Patient[] }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('All');
  const [sort, setSort] = useState<keyof Patient>('name');
  const [page, setPage] = useState(1);
  const pageSize = 6;
  const filtered = useMemo(() => patientRecords
    .filter((patient) => acceptedPatientSlugs.includes(patient.slug))
    .filter((patient) => patient.name.toLowerCase().includes(query.toLowerCase()))
    .filter((patient) => status === 'All' || patient.status === status)
    .sort((a, b) => String(a[sort]).localeCompare(String(b[sort]))), [acceptedPatientSlugs, patientRecords, query, status, sort]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize);
  return (
    <>
      <PageHeader title="My Patients" subtitle="Patients who have selected you as their care provider." />
      <section className="surface mb-5 p-4">
        <div className="grid gap-3 md:grid-cols-3">
          <input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" placeholder="Search patients" aria-label="Search patients" />
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" aria-label="Filter by status">
            {['All', 'In Range', 'High', 'Low', 'Above Range', 'Needs Review'].map((item) => <option key={item}>{item}</option>)}
          </select>
          <select value={sort} onChange={(event) => setSort(event.target.value as keyof Patient)} className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" aria-label="Sort patients">
            <option value="name">Sort by name</option>
            <option value="currentGlucose">Sort by glucose</option>
            <option value="timeInRange">Sort by time in range</option>
          </select>
        </div>
      </section>
      <section className="surface overflow-hidden"><PatientTable patients={visible} showDiabetesType={false} /></section>
      <div className="mt-4 flex items-center justify-between text-sm">
        <p className="text-clinical-muted">Page {page} of {pages}</p>
        <div className="flex gap-2">
          <button disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="focus-ring rounded-md border border-clinical-border px-3 py-2 disabled:opacity-40">Previous</button>
          <button disabled={page === pages} onClick={() => setPage((value) => Math.min(pages, value + 1))} className="focus-ring rounded-md border border-clinical-border px-3 py-2 disabled:opacity-40">Next</button>
        </div>
      </div>
    </>
  );
}
