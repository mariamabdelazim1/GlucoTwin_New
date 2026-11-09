import { useState } from 'react';
import type { FormEvent } from 'react';
import { Activity, HeartPulse, Stethoscope } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import heroImage from '../assets/clinical-hero.png';
import { DoctorDirectory } from '../components/doctors/DoctorDirectory';
import type { Account, DoctorProfileData, DoctorRating, PatientProfile } from '../types';

const emptyPatient: PatientProfile = {
  fullName: '', age: '', weight: '', height: '', diabetesType: '', insulinPlan: '',
  diagnosisYear: '', medications: '', allergies: '', emergencyContact: '', selectedDoctorId: '',
};
const emptyDoctor: DoctorProfileData = {
  fullName: '', specialty: '', yearsExperience: '', medicalSchool: '', qualifications: '', bio: '', certificates: [], papers: [],
};
const field = 'focus-ring mt-1 w-full rounded-md border border-clinical-border bg-white px-3 py-2 text-sm font-normal';

export function Login({ mode = 'doctor', accounts, ratings, onSignIn, onRegister }: { mode?: 'doctor' | 'patient'; accounts: Account[]; ratings: DoctorRating[]; onSignIn: (identifier: string, password: string, mode: 'doctor' | 'patient') => Promise<string | null>; onRegister: (account: Account) => Promise<string | null> }) {
  const [searchParams] = useSearchParams();
  const [role, setRole] = useState<'doctor' | 'patient'>(mode);
  const [action, setAction] = useState<'signin' | 'register'>(searchParams.get('action') === 'register' ? 'register' : 'signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [patient, setPatient] = useState<PatientProfile>({ ...emptyPatient, selectedDoctorId: searchParams.get('doctor') || '' });
  const [doctor, setDoctor] = useState(emptyDoctor);
  const [certificates, setCertificates] = useState('');
  const [papers, setPapers] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const doctors = accounts.filter((account) => account.role === 'doctor' && account.doctorProfile);
  const useSavedAccount = (savedRole: 'doctor' | 'patient') => {
    if (busy) return;
    setRole(savedRole);
    setEmail(savedRole === 'doctor' ? 'sarah.ahmed@clinic.example' : 'omar.hassan@example.com');
    setPassword('password');
    setError('');
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    if (action === 'signin') {
      setBusy(true);
      try { setError(await onSignIn(email.trim(), password, role) ?? ''); }
      catch { setError('Sign-in failed. Check that the care service is running.'); }
      finally { setBusy(false); }
      return;
    }
    if (role === 'patient' && !doctors.some((item) => item.id === patient.selectedDoctorId)) {
      setError('Choose a doctor before creating your account.');
      return;
    }
    const id = crypto.randomUUID();
    const patientPayload: Partial<PatientProfile> = { ...patient };
    if (!patientPayload.diagnosisYear?.trim()) delete patientPayload.diagnosisYear;
    const account: Account = role === 'patient'
      ? { id, role, email: email.trim().toLowerCase(), password, patientProfile: patientPayload as PatientProfile }
      : { id, role, email: email.trim().toLowerCase(), password, doctorProfile: { ...doctor, certificates: certificates.split('\n').map((item) => item.trim()).filter(Boolean), papers: papers.split('\n').map((item) => item.trim()).filter(Boolean) } };
    setError(await onRegister(account) ?? '');
  };

  const switchRole = (next: 'doctor' | 'patient') => { setRole(next); setError(''); };
  const switchAction = (next: 'signin' | 'register') => { setAction(next); setError(''); };

  return <main className="grid min-h-screen bg-clinical-bg lg:grid-cols-[minmax(360px,1fr)_minmax(460px,680px)]">
    <section className="relative flex min-h-[280px] items-end overflow-hidden px-6 py-10 text-white md:px-12 lg:sticky lg:top-0 lg:h-screen">
      <img src={heroImage} alt="Clinical workstation showing glucose dashboards" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-emerald-950/75" />
      <div className="relative max-w-lg"><Link to="/" className="mb-8 inline-flex items-center gap-3 text-xl font-bold"><Activity size={25} /> Diabetes Digital Twin</Link><h1 className="text-3xl font-bold md:text-5xl">Care starts with the right connection.</h1><p className="mt-4 max-w-md text-emerald-50">A shared place for patients and doctors to follow progress and stay in touch.</p></div>
    </section>
    <section className="flex justify-center bg-white px-5 py-8 md:px-10 md:py-12"><div className="w-full max-w-xl">
      <div className="flex gap-1 border-b border-clinical-border" role="tablist" aria-label="Account type">
        {(['patient', 'doctor'] as const).map((item) => <button key={item} role="tab" aria-selected={role === item} onClick={() => switchRole(item)} className={`focus-ring flex flex-1 items-center justify-center gap-2 border-b-2 px-4 py-3 font-semibold capitalize ${role === item ? 'border-clinical-primary text-clinical-primaryDark' : 'border-transparent text-clinical-muted'}`}>{item === 'patient' ? <HeartPulse size={18} /> : <Stethoscope size={18} />}{item}</button>)}
      </div>
      <div className="mt-7"><h2 className="text-2xl font-bold">{action === 'signin' ? 'Welcome back' : `Join as a ${role}`}</h2><p className="mt-1 text-sm text-clinical-muted">{action === 'signin' ? 'Sign in to continue to your dashboard.' : role === 'patient' ? 'Complete your health information and choose a doctor.' : 'Create the profile patients will review.'}</p></div>
      {role === 'patient' ? <Link to="/doctors" className="focus-ring mt-3 inline-flex text-sm font-semibold text-clinical-primary">Browse doctor profiles and rankings</Link> : null}
      <div className="mt-6 flex rounded-md bg-clinical-secondary p-1" role="tablist" aria-label="Account action">
        <button role="tab" aria-selected={action === 'signin'} onClick={() => switchAction('signin')} className={`focus-ring flex-1 rounded px-4 py-2 text-sm font-semibold ${action === 'signin' ? 'bg-white text-clinical-primaryDark shadow-sm' : 'text-clinical-muted'}`}>Sign in</button>
        <button role="tab" aria-selected={action === 'register'} onClick={() => switchAction('register')} className={`focus-ring flex-1 rounded px-4 py-2 text-sm font-semibold ${action === 'register' ? 'bg-white text-clinical-primaryDark shadow-sm' : 'text-clinical-muted'}`}>Create account</button>
      </div>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {action === 'register' && role === 'patient' ? <>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-semibold sm:col-span-2">Full name<input required value={patient.fullName} onChange={(event) => setPatient({ ...patient, fullName: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Age<input required type="number" min="1" max="120" value={patient.age} onChange={(event) => setPatient({ ...patient, age: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Weight (kg)<input required type="number" min="1" step="0.1" value={patient.weight} onChange={(event) => setPatient({ ...patient, weight: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Height (cm)<input required type="number" min="1" step="0.1" value={patient.height} onChange={(event) => setPatient({ ...patient, height: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Diagnosis year<input type="number" min="1900" max={new Date().getFullYear()} value={patient.diagnosisYear} onChange={(event) => setPatient({ ...patient, diagnosisYear: event.target.value })} className={field} /></label>
            <label className="text-sm font-semibold">Emergency contact<input value={patient.emergencyContact} onChange={(event) => setPatient({ ...patient, emergencyContact: event.target.value })} className={field} /></label>
          </div>
          <div className="border-t border-clinical-border pt-5"><h3 className="font-semibold">Choose your doctor</h3><p className="mb-4 text-sm text-clinical-muted">Compare profiles, ratings, and experience before choosing.</p><DoctorDirectory doctors={doctors} ratings={ratings} selectedId={patient.selectedDoctorId} onSelect={(id) => setPatient({ ...patient, selectedDoctorId: id })} /></div>
        </> : null}
        {action === 'register' && role === 'doctor' ? <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-semibold sm:col-span-2">Full name<input required value={doctor.fullName} onChange={(event) => setDoctor({ ...doctor, fullName: event.target.value })} className={field} placeholder="Dr. Full Name" /></label>
          <label className="text-sm font-semibold">Specialty<input required value={doctor.specialty} onChange={(event) => setDoctor({ ...doctor, specialty: event.target.value })} className={field} /></label>
          <label className="text-sm font-semibold">Years of experience<input required type="number" min="0" max="70" value={doctor.yearsExperience} onChange={(event) => setDoctor({ ...doctor, yearsExperience: event.target.value })} className={field} /></label>
          <label className="text-sm font-semibold sm:col-span-2">Medical college / university<input required value={doctor.medicalSchool} onChange={(event) => setDoctor({ ...doctor, medicalSchool: event.target.value })} className={field} /></label>
          <label className="text-sm font-semibold sm:col-span-2">Qualifications<input value={doctor.qualifications} onChange={(event) => setDoctor({ ...doctor, qualifications: event.target.value })} className={field} /></label>
          <label className="text-sm font-semibold sm:col-span-2">About your practice<textarea rows={3} value={doctor.bio} onChange={(event) => setDoctor({ ...doctor, bio: event.target.value })} className={field} /></label>
          <label className="text-sm font-semibold sm:col-span-2">Certificates (one per line)<textarea rows={3} value={certificates} onChange={(event) => setCertificates(event.target.value)} className={field} /></label>
          <label className="text-sm font-semibold sm:col-span-2">Papers (one per line)<textarea rows={3} value={papers} onChange={(event) => setPapers(event.target.value)} className={field} /></label>
        </div> : null}
        <label className="block text-sm font-semibold">{action === 'signin' ? 'Email or username' : 'Email'}<input required type={action === 'signin' ? 'text' : 'email'} autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} className={field} /></label>
        <label className="block text-sm font-semibold">Password<input required type="password" minLength={action === 'register' ? 8 : undefined} autoComplete={action === 'register' ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} className={field} /></label>
        {error ? <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
        <button disabled={busy} className="focus-ring w-full rounded-md bg-clinical-primary px-4 py-3 font-semibold text-white hover:bg-clinical-primaryDark disabled:opacity-50">{action === 'signin' ? 'Sign in' : 'Create account'}</button>
      </form>
      {action === 'signin' ? <section className="mt-6 border-t border-clinical-border pt-5">
        <h3 className="text-sm font-semibold">Saved accounts</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <button type="button" disabled={busy} onClick={() => useSavedAccount('doctor')} className="focus-ring flex items-center gap-3 rounded-md border border-clinical-border px-4 py-3 text-left hover:bg-clinical-secondary disabled:opacity-50"><Stethoscope size={20} className="shrink-0 text-clinical-primary" /><span className="min-w-0"><span className="block text-sm font-semibold">Dr. Sarah Ahmed</span><span className="block break-all text-xs text-clinical-muted">sarah.ahmed@clinic.example</span></span></button>
          <button type="button" disabled={busy} onClick={() => useSavedAccount('patient')} className="focus-ring flex items-center gap-3 rounded-md border border-clinical-border px-4 py-3 text-left hover:bg-clinical-secondary disabled:opacity-50"><HeartPulse size={20} className="shrink-0 text-clinical-primary" /><span className="min-w-0"><span className="block text-sm font-semibold">Omar Hassan</span><span className="block break-all text-xs text-clinical-muted">omar.hassan@example.com</span></span></button>
        </div>
      </section> : null}
    </div></section>
  </main>;
}
