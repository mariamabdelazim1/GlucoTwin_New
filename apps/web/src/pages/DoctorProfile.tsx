import { useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { Check, FilePlus2, Save, Trash2 } from 'lucide-react';
import type { Account, DoctorProfileData, DoctorRating, PatientProfile } from '../types';
import { Avatar } from '../components/ui/Avatar';
import { DoctorDirectory } from '../components/doctors/DoctorDirectory';
import { PageHeader } from '../components/ui/PageHeader';

const field = 'focus-ring mt-1 w-full rounded-md border border-clinical-border bg-white px-3 py-2 font-normal';
const lines = (value: string) => value.split('\n').map((item) => item.trim()).filter(Boolean);
const readFile = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result));
  reader.onerror = () => reject(new Error('Could not read file'));
  reader.readAsDataURL(file);
});

export function DoctorProfile({ account, accounts, ratings, onSave }: { account: Account; accounts: Account[]; ratings: DoctorRating[]; onSave: (account: Account) => void }) {
  const isDoctor = account.role === 'doctor';
  const [doctor, setDoctor] = useState<DoctorProfileData>(account.doctorProfile ?? { fullName: '', specialty: '', yearsExperience: '', medicalSchool: '', qualifications: '', bio: '', certificates: [], papers: [] });
  const [certificateText, setCertificateText] = useState(account.doctorProfile?.certificates.join('\n') ?? '');
  const [paperText, setPaperText] = useState(account.doctorProfile?.papers.join('\n') ?? '');
  const [patient, setPatient] = useState<PatientProfile>(account.patientProfile ?? { fullName: '', age: '', weight: '', height: '', diabetesType: '', insulinPlan: '', diagnosisYear: '', medications: '', allergies: '', emergencyContact: '', selectedDoctorId: '' });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const name = isDoctor ? doctor.fullName : patient.fullName;
  const upload = async (event: ChangeEvent<HTMLInputElement>, kind: 'photo' | 'certificate' | 'paper') => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (files.some((file) => file.size > 1_000_000)) { setError('Each file must be smaller than 1 MB for browser storage.'); return; }
    const storedBytes = (doctor.photo?.length ?? 0) + (doctor.documents ?? []).reduce((sum, document) => sum + document.dataUrl.length, 0);
    if (storedBytes + files.reduce((sum, file) => sum + file.size * 1.4, 0) > 2_000_000) { setError('Profile files are limited to 2 MB in this browser.'); return; }
    try {
      if (kind === 'photo' && files[0]) {
        const photo = await readFile(files[0]);
        setDoctor((current) => ({ ...current, photo }));
      } else if (kind !== 'photo') {
        const documents = await Promise.all(files.map(async (file) => ({ id: crypto.randomUUID(), name: file.name, kind, dataUrl: await readFile(file) })));
        setDoctor((current) => ({ ...current, documents: [...(current.documents ?? []), ...documents] }));
      }
      setError('');
    } catch { setError('The selected file could not be opened.'); }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSave(isDoctor ? { ...account, doctorProfile: { ...doctor, certificates: lines(certificateText), papers: lines(paperText) } } : { ...account, patientProfile: patient });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  };

  return <>
    <PageHeader title={isDoctor ? 'Doctor Profile' : 'Patient Profile'} subtitle={isDoctor ? 'Keep your public professional profile current.' : 'Keep your health information and care team current.'} />
    <div className="grid gap-6 xl:grid-cols-[280px_1fr]">
      <aside className="surface h-fit p-5 text-center">
        {isDoctor && doctor.photo ? <img src={doctor.photo} alt="Profile" className="mx-auto h-20 w-20 rounded-md object-cover" /> : <div className="flex justify-center"><Avatar label={name.split(/\s+/).map((part) => part[0]).slice(-2).join('').toUpperCase()} size="lg" /></div>}
        <h2 className="mt-4 text-lg font-bold">{name}</h2>
        <p className="text-sm text-clinical-muted">{isDoctor ? doctor.specialty : account.email}</p>
        {isDoctor ? <label className="focus-ring mt-5 block cursor-pointer rounded-md border border-clinical-border px-3 py-2 text-sm font-semibold text-clinical-primary">Change photo<input className="sr-only" type="file" accept="image/*" onChange={(event) => void upload(event, 'photo')} /></label> : null}
      </aside>
      <form onSubmit={submit} className="surface space-y-6 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-semibold sm:col-span-2">Full name<input required value={name} onChange={(event) => isDoctor ? setDoctor({ ...doctor, fullName: event.target.value }) : setPatient({ ...patient, fullName: event.target.value })} className={field} /></label>
          {isDoctor ? <>
            <label className="text-sm font-semibold">Specialty<input required value={doctor.specialty} onChange={(event) => setDoctor({ ...doctor, specialty: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Years of experience<input required type="number" min="0" max="70" value={doctor.yearsExperience} onChange={(event) => setDoctor({ ...doctor, yearsExperience: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold sm:col-span-2">Medical college / university<input required value={doctor.medicalSchool} onChange={(event) => setDoctor({ ...doctor, medicalSchool: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold sm:col-span-2">Qualifications<input value={doctor.qualifications} onChange={(event) => setDoctor({ ...doctor, qualifications: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold sm:col-span-2">About your practice<textarea rows={3} value={doctor.bio} onChange={(event) => setDoctor({ ...doctor, bio: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold sm:col-span-2">Certificates (one per line)<textarea rows={3} value={certificateText} onChange={(event) => setCertificateText(event.target.value)} className={field} /></label>
            <label className="text-sm font-semibold sm:col-span-2">Papers (one per line)<textarea rows={3} value={paperText} onChange={(event) => setPaperText(event.target.value)} className={field} /></label>
          </> : <>
            <label className="text-sm font-semibold">Age<input required type="number" min="1" max="120" value={patient.age} onChange={(event) => setPatient({ ...patient, age: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Weight (kg)<input required type="number" min="1" step="0.1" value={patient.weight} onChange={(event) => setPatient({ ...patient, weight: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Height (cm)<input required type="number" min="1" step="0.1" value={patient.height} onChange={(event) => setPatient({ ...patient, height: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Diabetes type<select value={patient.diabetesType} onChange={(event) => setPatient({ ...patient, diabetesType: event.target.value as PatientProfile['diabetesType'] })} className={field}><option value="">Not provided</option><option>Type 1 Diabetes</option><option>Type 2 Diabetes</option></select></label>
            <label className="text-sm font-semibold">Diagnosis year<input type="number" value={patient.diagnosisYear} onChange={(event) => setPatient({ ...patient, diagnosisYear: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Insulin plan<input value={patient.insulinPlan} onChange={(event) => setPatient({ ...patient, insulinPlan: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold sm:col-span-2">Medications<input value={patient.medications} onChange={(event) => setPatient({ ...patient, medications: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Allergies<input value={patient.allergies} onChange={(event) => setPatient({ ...patient, allergies: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Emergency contact<input value={patient.emergencyContact} onChange={(event) => setPatient({ ...patient, emergencyContact: event.target.value })} className={field} /></label>
          </>}
        </div>
        {isDoctor ? <div className="border-t border-clinical-border pt-5">
          <h3 className="font-semibold">Certificate and paper files</h3>
          <div className="mt-3 flex flex-wrap gap-2">{(['certificate', 'paper'] as const).map((kind) => <label key={kind} className="focus-ring inline-flex cursor-pointer items-center gap-2 rounded-md border border-clinical-border px-3 py-2 text-sm font-semibold text-clinical-primary"><FilePlus2 size={16} /> Add {kind}<input className="sr-only" type="file" accept=".pdf,image/*" multiple onChange={(event) => void upload(event, kind)} /></label>)}</div>
          <ul className="mt-4 space-y-2">{(doctor.documents ?? []).map((document) => <li key={document.id} className="flex items-center justify-between gap-3 rounded-md bg-clinical-bg px-3 py-2 text-sm"><a href={document.dataUrl} target="_blank" rel="noreferrer" className="min-w-0 truncate font-semibold text-clinical-primary">{document.name}</a><button type="button" onClick={() => setDoctor({ ...doctor, documents: doctor.documents?.filter((item) => item.id !== document.id) })} aria-label={`Remove ${document.name}`} className="focus-ring text-clinical-critical"><Trash2 size={17} /></button></li>)}</ul>
        </div> : <div className="border-t border-clinical-border pt-5"><h3 className="mb-3 font-semibold">Your doctor</h3><DoctorDirectory doctors={accounts.filter((item) => item.role === 'doctor' && item.doctorProfile)} ratings={ratings} selectedId={patient.selectedDoctorId} onSelect={(id) => setPatient({ ...patient, selectedDoctorId: id })} /></div>}
        {error ? <p role="alert" className="text-sm text-clinical-critical">{error}</p> : null}
        <button className="focus-ring inline-flex items-center gap-2 rounded-md bg-clinical-primary px-4 py-2 font-semibold text-white">{saved ? <Check size={18} /> : <Save size={18} />}{saved ? 'Saved' : 'Save profile'}</button>
      </form>
    </div>
  </>;
}
