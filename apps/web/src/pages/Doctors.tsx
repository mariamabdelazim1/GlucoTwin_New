import { useState } from 'react';
import { Activity, Star } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import type { Account, DoctorRating } from '../types';
import { DoctorDirectory } from '../components/doctors/DoctorDirectory';
import { PageHeader } from '../components/ui/PageHeader';

export function Doctors({ accounts, ratings, patientAccount, assignmentStatus, onChoose, onRate, publicView = false, error }: {
  accounts: Account[];
  ratings: DoctorRating[];
  patientAccount?: Account;
  assignmentStatus?: 'pending' | 'accepted' | 'declined';
  onChoose?: (id: string) => Promise<string | null>;
  onRate?: (score: number) => void;
  publicView?: boolean;
  error?: string | null;
}) {
  const navigate = useNavigate();
  const [score, setScore] = useState(0);
  const [requesting, setRequesting] = useState<string | null>(null);
  const [requestFeedback, setRequestFeedback] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);
  const doctors = accounts.filter((account) => account.role === 'doctor' && account.doctorProfile);
  const selectedId = patientAccount?.patientProfile?.selectedDoctorId;
  const existingRating = ratings.find((rating) => rating.patientId === patientAccount?.id && rating.doctorId === selectedId && rating.source === 'patient');
  const choose = async (id: string) => {
    if (publicView) { navigate(`/login/patient?action=register&doctor=${encodeURIComponent(id)}`); return; }
    if (!onChoose || requesting) return;
    setRequesting(id); setRequestFeedback(null);
    const failure = await onChoose(id);
    setRequesting(null);
    setRequestFeedback(failure ? { kind: 'error', text: failure } : { kind: 'success', text: 'Doctor request sent.' });
  };
  const content = <div className="mx-auto max-w-4xl">
    <PageHeader title="Find a Doctor" subtitle="Compare doctor profiles, patient ratings, and experience." />
    {error ? <p role="alert" className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{error}</p> : null}
    {patientAccount && assignmentStatus === 'accepted' && selectedId ? <section className="mb-6 border-b border-clinical-border pb-6">
      <h2 className="font-semibold">Rate your doctor</h2>
      <p className="mt-1 text-sm text-clinical-muted">{existingRating ? `Your current rating is ${existingRating.score} out of 5.` : 'Your rating will appear in the doctor directory.'}</p>
      <div className="mt-3 flex items-center gap-1" role="group" aria-label="Doctor rating">{[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" onClick={() => setScore(value)} aria-label={`Rate ${value} star${value === 1 ? '' : 's'}`} className="focus-ring rounded-md p-2 text-amber-600"><Star size={23} fill={value <= score ? 'currentColor' : 'none'} /></button>)}</div>
      <button disabled={!score} onClick={() => { onRate?.(score); setScore(0); }} className="focus-ring mt-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{existingRating ? 'Update rating' : 'Submit rating'}</button>
    </section> : null}
    {patientAccount ? <p className="mb-4 text-sm text-clinical-muted">Choosing a different doctor sends a new care request. Your current doctor remains selected until you choose another.</p> : null}
    {requestFeedback ? <p role={requestFeedback.kind === 'error' ? 'alert' : 'status'} className={`mb-4 rounded-md border p-3 text-sm ${requestFeedback.kind === 'error' ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>{requestFeedback.text}</p> : null}
    <DoctorDirectory doctors={doctors} ratings={ratings} selectedId={selectedId} onSelect={(id) => void choose(id)} selectLabel={requesting ? 'Sending request…' : patientAccount ? 'Request this doctor' : 'Choose this doctor'} selectedLabel={assignmentStatus === 'declined' ? 'Retry request to this doctor' : assignmentStatus === 'pending' ? 'Request pending' : 'Selected doctor'} disabled={Boolean(requesting)} />
  </div>;
  if (!publicView) return content;
  return <main className="min-h-screen bg-clinical-bg text-clinical-text"><header className="border-b border-clinical-border bg-white"><div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-5 py-4"><Link to="/" className="focus-ring inline-flex items-center gap-2 font-bold"><Activity size={21} className="text-clinical-primary" /> Diabetes Digital Twin</Link><Link to="/login/patient" className="focus-ring rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white">Sign in</Link></div></header><div className="px-5 py-8 md:py-12">{content}</div></main>;
}
