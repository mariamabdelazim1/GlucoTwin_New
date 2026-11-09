import { useCallback, useEffect, useState } from 'react';
import { Activity, ArrowLeft, Droplets, LayoutDashboard, MessageSquare, Plus, RefreshCw, Send, Syringe, Utensils, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Account } from '../types';
import { getSnapshot, loginAccount, syncItem, updateMeal } from '../utils/sync';
import type { SyncSnapshot } from '../utils/sync';

type Tab = 'overview' | 'record' | 'care' | 'profile';
type RecordMode = 'glucose' | 'food' | 'bolus';
const input = 'w-full rounded-md border border-clinical-border bg-white px-3 py-2.5 text-sm outline-none focus:border-clinical-primary';
const panel = 'rounded-md border border-clinical-border bg-white p-4 shadow-clinical';
const now = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export function MobilePreview({ existingPatient }: { existingPatient?: Account }) {
  const [snapshot, setSnapshot] = useState<SyncSnapshot | null>(null);
  const [tab, setTab] = useState<Tab>('overview');
  const [mode, setMode] = useState<RecordMode>('glucose');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [value, setValue] = useState('');
  const [meal, setMeal] = useState('Lunch');
  const [items, setItems] = useState('');
  const [carbs, setCarbs] = useState('');
  const [preMeal, setPreMeal] = useState('');
  const [units, setUnits] = useState('');
  const [mealStatus, setMealStatus] = useState<'planned' | 'eaten'>('planned');
  const [draft, setDraft] = useState('');

  const refresh = useCallback(async () => {
    try { setSnapshot(await getSnapshot()); setError(''); }
    catch { setError('Connection to the sync service is unavailable.'); }
  }, []);
  useEffect(() => {
    if (!sessionStorage.getItem('ddt.sync.token')) return;
    void refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const signIn = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try { await loginAccount(email.trim(), password, 'patient'); await refresh(); }
    catch { setError('Incorrect email or password, or sync service unavailable.'); }
    setBusy(false);
  };
  const post = async (kind: 'glucose' | 'food' | 'bolus' | 'messages', item: Record<string, unknown>) => {
    if (!snapshot) return;
    setBusy(true);
    try {
      await syncItem(kind, { id: crypto.randomUUID(), patientSlug: snapshot.account.id, time: now(), ...item });
      await refresh();
    } catch { setError('Could not save. Please check the connection and try again.'); }
    setBusy(false);
  };
  const record = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!snapshot) return;
    if (mode === 'glucose') {
      const reading = Number(value);
      if (!Number.isFinite(reading) || reading < 20 || reading > 600) { setError('Enter a glucose value from 20 to 600 mg/dL.'); return; }
      await post('glucose', { value: reading, recordedAt: new Date().toISOString() });
      setValue('');
    } else if (mode === 'food') {
      if (!items.trim() || Number(carbs) < 0 || carbs === '') return;
      const eventAt = new Date().toISOString();
      await post('food', { patient: snapshot.account.patientProfile?.fullName, meal, items: items.trim(), carbs: `${carbs}g`, impact: 'Pending CGM impact', status: mealStatus, plannedEatingAt: eventAt,
        ...(mealStatus === 'eaten' ? { actualEatingAt: eventAt, confirmAnnouncedAmount: true } : {}) });
      setItems(''); setCarbs('');
    } else {
      if (carbs === '' || preMeal === '' || units === '' || Number(carbs) < 0 || Number(preMeal) < 20 || Number(units) < 0) return;
      await post('bolus', { patient: snapshot.account.patientProfile?.fullName, meal, carbs: `${carbs}g`, preMeal: `${preMeal} mg/dL`, recommended: 'Doctor review', recorded: `${units} U`, administeredAt: new Date().toISOString() });
      setCarbs(''); setPreMeal(''); setUnits('');
    }
  };
  const changeMeal = async (id: string, version: number, status: 'eaten' | 'cancelled') => {
    setBusy(true);
    try {
      await updateMeal(id, { expectedVersion: version, mutationId: crypto.randomUUID(), status,
        ...(status === 'eaten' ? { actualEatingAt: new Date().toISOString(), confirmAnnouncedAmount: true } : {}) });
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update meal.'); }
    setBusy(false);
  };

  if (!snapshot) return <main className="min-h-screen bg-clinical-bg px-4 py-10 text-clinical-text"><div className="mx-auto max-w-[420px]">
    <Link to={existingPatient ? '/patient/dashboard' : '/login/patient'} className="mb-10 inline-flex items-center gap-2 text-sm font-semibold text-clinical-primary"><ArrowLeft size={17} /> Back to website</Link>
    <div className="mb-8 flex items-center gap-3 text-clinical-primaryDark"><Activity size={32} /><span className="text-xl font-bold">Diabetes Digital Twin</span></div>
    <h1 className="text-2xl font-bold">Patient sign in</h1>
    <form onSubmit={signIn} className="mt-6 space-y-4">
      <label className="block text-sm font-semibold">Email<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className={`mt-1 ${input}`} /></label>
      <label className="block text-sm font-semibold">Password<input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className={`mt-1 ${input}`} /></label>
      {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
      <button disabled={busy} className="w-full rounded-md bg-clinical-primary px-4 py-3 font-semibold text-white disabled:opacity-50">Sign in</button>
    </form>
    <Link to="/login/patient?action=register" className="mt-5 inline-block text-sm font-semibold text-clinical-primary">Create a patient account</Link>
  </div></main>;

  const profile = snapshot.account.patientProfile;
  const doctor = snapshot.doctors.find((item) => item.id === profile?.selectedDoctorId);
  const assignment = snapshot.assignments.find((item) => item.patientId === snapshot.account.id && item.doctorId === profile?.selectedDoctorId);
  const readings = [...snapshot.glucose].sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
  const latest = readings[readings.length - 1];
  const chart = readings.slice(-12).map((item, index) => ({ index, value: item.value, time: item.time }));
  const records = mode === 'glucose' ? [...snapshot.glucose].reverse() : mode === 'food' ? snapshot.food : snapshot.bolus;
  const sendMessage = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.trim() || assignment?.status !== 'accepted') return;
    await post('messages', { patient: profile?.fullName, avatar: '', from: 'patient', text: draft.trim(), unread: true });
    setDraft('');
  };

  return <main className="min-h-screen bg-clinical-bg text-clinical-text sm:px-4 sm:py-6">
    <div className="mx-auto flex min-h-screen w-full max-w-[430px] flex-col bg-clinical-bg sm:min-h-[820px] sm:border sm:border-clinical-border sm:shadow-xl">
      <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-clinical-border bg-white px-4">
        <div className="flex items-center gap-2 text-clinical-primaryDark"><Activity size={23} /><strong className="text-sm">Diabetes Digital Twin</strong></div>
        <button onClick={refresh} aria-label="Refresh" title="Refresh" className="rounded-md p-2 text-clinical-muted hover:bg-clinical-secondary"><RefreshCw size={18} /></button>
      </header>
      <div className="flex-1 space-y-4 px-4 py-5 pb-24">
        {error ? <p role="alert" className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{error}</p> : null}
        {tab === 'overview' ? <>
          <div><h1 className="text-2xl font-bold text-clinical-primaryDark">Hello, {profile?.fullName?.split(' ')[0] || 'Patient'}</h1><p className="mt-1 text-sm text-clinical-muted">Your readings and care records</p></div>
          <section className={panel}><h2 className="text-sm font-semibold text-clinical-muted">Latest manual reading</h2>{latest ? <div className="mt-2 flex items-end justify-between"><div><strong className="text-4xl text-clinical-primaryDark">{latest.value}</strong><span className="ml-1 text-sm">mg/dL</span></div><span className="text-sm text-clinical-muted">{latest.time}</span></div> : <p className="mt-3 text-sm text-clinical-muted">No readings yet.</p>}</section>
          {chart.length > 1 ? <section className={panel}><h2 className="mb-3 font-semibold">Reading trend</h2><div className="h-44"><ResponsiveContainer width="100%" height="100%"><LineChart data={chart}><CartesianGrid vertical={false} stroke="#e4e7ec" /><XAxis dataKey="time" tick={{ fontSize: 10 }} /><YAxis width={36} tick={{ fontSize: 10 }} /><Tooltip /><Line type="linear" dataKey="value" stroke="#047857" strokeWidth={2.5} dot={{ r: 3 }} /></LineChart></ResponsiveContainer></div></section> : null}
          <section className={panel}><h2 className="font-semibold">Recorded totals</h2><div className="mt-3 space-y-3 text-sm"><p className="flex justify-between"><span className="flex items-center gap-2"><Droplets size={17} className="text-clinical-primary" /> Manual readings</span><strong>{snapshot.glucose.length}</strong></p><p className="flex justify-between"><span className="flex items-center gap-2"><Utensils size={17} className="text-clinical-primary" /> Food entries</span><strong>{snapshot.food.length}</strong></p><p className="flex justify-between"><span className="flex items-center gap-2"><Syringe size={17} className="text-clinical-primary" /> Bolus logs</span><strong>{snapshot.bolus.length}</strong></p></div></section>
          <section className={panel}><h2 className="font-semibold">Care status</h2><p className="mt-2 text-sm">{assignment?.status === 'accepted' ? `Connected to ${doctor?.doctorProfile?.fullName || 'your doctor'}` : `Doctor request ${assignment?.status || 'pending'}`}</p></section>
          <p className="text-xs leading-5 text-clinical-muted">No live CGM or validated prediction feed is connected. Manual entries are not treatment recommendations.</p>
        </> : null}
        {tab === 'record' ? <>
          <h1 className="text-xl font-bold">Record</h1>
          <div className="grid grid-cols-3 rounded-md bg-clinical-secondary p-1" role="tablist" aria-label="Record type">{(['glucose', 'food', 'bolus'] as const).map((item) => <button key={item} role="tab" aria-selected={mode === item} onClick={() => setMode(item)} className={`rounded px-2 py-2 text-sm font-semibold capitalize ${mode === item ? 'bg-white text-clinical-primaryDark shadow-sm' : 'text-clinical-muted'}`}>{item}</button>)}</div>
          <form onSubmit={record} className={`${panel} space-y-3`}>
            {mode !== 'glucose' ? <select value={meal} onChange={(event) => setMeal(event.target.value)} className={input} aria-label="Meal"><option>Breakfast</option><option>Lunch</option><option>Dinner</option><option>Snack</option></select> : null}
            {mode === 'glucose' ? <input type="number" min="20" max="600" value={value} onChange={(event) => setValue(event.target.value)} placeholder="Glucose mg/dL" aria-label="Glucose mg/dL" className={input} required /> : mode === 'food' ? <input value={items} onChange={(event) => setItems(event.target.value)} placeholder="Food items" aria-label="Food items" className={input} required /> : null}
            {mode === 'food' ? <select value={mealStatus} onChange={(event) => setMealStatus(event.target.value as 'planned' | 'eaten')} className={input} aria-label="Meal state"><option value="planned">Plan for later</option><option value="eaten">Already eaten</option></select> : null}
            {mode !== 'glucose' ? <input type="number" min="0" value={carbs} onChange={(event) => setCarbs(event.target.value)} placeholder="Carbs g" aria-label="Carbs g" className={input} required /> : null}
            {mode === 'bolus' ? <><input type="number" min="20" value={preMeal} onChange={(event) => setPreMeal(event.target.value)} placeholder="Pre-meal glucose mg/dL" aria-label="Pre-meal glucose mg/dL" className={input} required /><input type="number" min="0" step="0.1" value={units} onChange={(event) => setUnits(event.target.value)} placeholder="Bolus units" aria-label="Bolus units" className={input} required /></> : null}
            <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-md bg-clinical-primary px-4 py-2.5 font-semibold text-white disabled:opacity-50"><Plus size={17} /> Save</button>
          </form>
          <section className={panel}><h2 className="font-semibold">Recent {mode === 'glucose' ? 'readings' : mode === 'food' ? 'food' : 'bolus logs'}</h2><div className="mt-3 divide-y divide-clinical-border">{records.slice(0, 8).map((entry) => <div key={entry.id} className="flex justify-between gap-3 py-3 text-sm"><div><strong>{mode === 'glucose' ? `${'value' in entry ? entry.value : ''} mg/dL` : mode === 'food' ? `${'meal' in entry ? entry.meal : ''}: ${'items' in entry ? entry.items : ''}` : `${'recorded' in entry ? entry.recorded : ''} at ${'meal' in entry ? entry.meal : ''}`}</strong>{mode !== 'glucose' ? <p className="text-clinical-muted">{'carbs' in entry ? entry.carbs : ''} carbs</p> : null}{mode === 'food' && 'status' in entry ? <><p className="capitalize text-clinical-muted">{entry.status}</p>{entry.status === 'planned' && entry.version ? <div className="mt-1 flex gap-2"><button disabled={busy} onClick={() => void changeMeal(entry.id, entry.version!, 'eaten')} className="font-semibold text-clinical-primary">Mark eaten</button><button disabled={busy} onClick={() => void changeMeal(entry.id, entry.version!, 'cancelled')} className="font-semibold text-red-700">Cancel</button></div> : null}</> : null}</div><span className="shrink-0 text-clinical-muted">{entry.time}</span></div>)}{records.length === 0 ? <p className="py-3 text-sm text-clinical-muted">Nothing recorded yet.</p> : null}</div></section>
        </> : null}
        {tab === 'care' ? <><h1 className="text-xl font-bold">Care team</h1><section className={panel}><h2 className="font-semibold">Your doctor</h2><p className="mt-2 font-semibold">{doctor?.doctorProfile?.fullName || 'Doctor request pending'}</p><p className="text-sm text-clinical-muted">{doctor?.doctorProfile?.specialty} · {doctor?.doctorProfile?.yearsExperience} years experience</p><p className="mt-2 text-sm">Request: {assignment?.status || 'pending'}</p></section><section className={panel}><h2 className="font-semibold">Messages</h2>{assignment?.status === 'accepted' ? <><div className="mt-3 space-y-2">{[...snapshot.messages].reverse().map((message) => <div key={message.id} className={`max-w-[88%] rounded-md px-3 py-2 text-sm ${message.from === 'patient' ? 'ml-auto bg-clinical-secondary' : 'border border-clinical-border'}`}>{message.text}</div>)}{snapshot.messages.length === 0 ? <p className="text-sm text-clinical-muted">No messages yet.</p> : null}</div><form onSubmit={sendMessage} className="mt-4 flex gap-2"><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Message your doctor" aria-label="Message your doctor" className={input} /><button disabled={busy || !draft.trim()} aria-label="Send message" title="Send message" className="rounded-md bg-clinical-primary px-3 text-white disabled:opacity-50"><Send size={18} /></button></form></> : <p className="mt-2 text-sm text-clinical-muted">Messaging opens after your doctor accepts your request.</p>}</section></> : null}
        {tab === 'profile' ? <><h1 className="text-xl font-bold">Profile</h1><section className={panel}><h2 className="font-semibold">My information</h2><dl className="mt-3 space-y-3 text-sm">{[['Name', profile?.fullName], ['Email', snapshot.account.email], ['Age', profile?.age], ['Weight', profile?.weight ? `${profile.weight} kg` : ''], ['Height', profile?.height ? `${profile.height} cm` : ''], ['Diabetes type', profile?.diabetesType], ['Insulin plan', profile?.insulinPlan]].map(([label, detail]) => <div key={label} className="flex justify-between gap-4"><dt className="text-clinical-muted">{label}</dt><dd className="text-right font-semibold">{detail || 'Not provided'}</dd></div>)}</dl></section><section className={panel}><h2 className="font-semibold">Basal plan</h2><p className="mt-2 text-sm text-clinical-muted">An AI-suggested basal schedule requires confirmation by your doctor. No confirmed schedule is available here yet.</p></section><Link to="/patient/dashboard" className="inline-flex items-center gap-2 text-sm font-semibold text-clinical-primary"><ArrowLeft size={17} /> Return to website</Link></> : null}
      </div>
      <nav className="sticky bottom-0 z-10 grid grid-cols-4 border-t border-clinical-border bg-white px-2 py-2" aria-label="Patient app navigation">{([['overview', LayoutDashboard, 'Overview'], ['record', Plus, 'Record'], ['care', MessageSquare, 'Care'], ['profile', UserRound, 'Profile']] as const).map(([key, Icon, label]) => <button key={key} onClick={() => setTab(key)} aria-current={tab === key ? 'page' : undefined} className={`flex flex-col items-center gap-1 rounded-md px-1 py-2 text-xs font-semibold ${tab === key ? 'bg-clinical-secondary text-clinical-primaryDark' : 'text-clinical-muted'}`}><Icon size={20} /><span>{label}</span></button>)}</nav>
    </div>
  </main>;
}
