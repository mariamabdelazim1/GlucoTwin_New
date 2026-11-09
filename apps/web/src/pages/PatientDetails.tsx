import { useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { Apple, CalendarDays, CheckCircle2, ChevronLeft, Dumbbell, FileText, Info, MessageSquare, Plus, Utensils, Zap } from 'lucide-react';
import { getPatient } from '../data/patients';
import { basalSchedule, cgmReadings, digitalTwinForecast, forecastSnapshots } from '../data/cgm';
import { Avatar } from '../components/ui/Avatar';
import { MetricCard } from '../components/ui/MetricCard';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { ClinicalWarning } from '../components/ui/ClinicalWarning';
import { GlucoseValue } from '../components/clinical/GlucoseValue';
import { TrendIndicator } from '../components/clinical/TrendIndicator';
import { CGMChart } from '../components/charts/CGMChart';
import { DigitalTwinChart } from '../components/charts/DigitalTwinChart';
import type { BolusEntry, FoodEntry, Patient, PatientProfile } from '../types';
import type { GlucoseEntry } from '../utils/sync';

export function PatientDetails({ foodEntries, bolusEntries, glucoseEntries, acceptedPatientSlugs, patientRecords, patientProfiles }: { foodEntries: FoodEntry[]; bolusEntries: BolusEntry[]; glucoseEntries: GlucoseEntry[]; acceptedPatientSlugs: string[]; patientRecords: Patient[]; patientProfiles: Record<string, PatientProfile> }) {
  const { slug } = useParams();
  const patient = patientRecords.find((item) => item.slug === slug) ?? getPatient(slug);
  const profile = patientProfiles[patient.slug];
  const patientFood = foodEntries.filter((entry) => entry.patientSlug === patient.slug);
  const patientBolus = bolusEntries.filter((entry) => entry.patientSlug === patient.slug);
  const patientGlucose = glucoseEntries.filter((entry) => entry.patientSlug === patient.slug).sort((a, b) => b.recordedAt.localeCompare(a.recordedAt));
  const [range, setRange] = useState('24H');
  const [tab, setTab] = useState<'Basal' | 'Bolus'>('Basal');
  const [notes, setNotes] = useState(['Reviewed lunch-time elevation; asked patient to confirm carbohydrate estimate.', 'Nocturnal glucose stable across previous three nights.']);
  const [modalOpen, setModalOpen] = useState(false);
  const [basalConfirmed, setBasalConfirmed] = useState(false);
  const [note, setNote] = useState('');
  const activity = [
    { icon: Zap, text: 'CGM reading recorded at 142 mg/dL', time: '2 min ago' },
    { icon: Utensils, text: 'Meal recorded with 62g carbohydrates', time: '1 hr ago' },
    { icon: FileText, text: 'Bolus recorded: 5 U', time: '1 hr ago' },
    { icon: Dumbbell, text: 'Exercise logged: 25 minute walk', time: '3 hr ago' },
    { icon: MessageSquare, text: 'Patient message received', time: '4 hr ago' },
    { icon: CalendarDays, text: 'Digital twin prediction generated', time: '4 hr ago' },
  ];
  if (!slug || !acceptedPatientSlugs.includes(slug)) return <Navigate to="/patients" replace />;
  if (!patient.usesCgm) return <>
    <Link to="/patients" className="focus-ring mb-5 inline-flex items-center gap-2 text-sm font-semibold text-clinical-primary"><ChevronLeft size={17} /> Back to patients</Link>
    <PageHeader title={patient.name} subtitle="Patient registration and manually entered records." />
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="surface p-5"><h2 className="text-lg font-semibold">Health information</h2><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        {([['Age', profile?.age], ['Weight', profile?.weight ? `${profile.weight} kg` : ''], ['Height', profile?.height ? `${profile.height} cm` : ''], ['Diabetes type', profile?.diabetesType], ['Diagnosis year', profile?.diagnosisYear], ['Insulin plan', profile?.insulinPlan], ['Medications', profile?.medications], ['Allergies', profile?.allergies], ['Emergency contact', profile?.emergencyContact]] as const).map(([label, value]) => <div key={label}><dt className="text-clinical-muted">{label}</dt><dd className="font-semibold">{value || 'Not provided'}</dd></div>)}
      </dl><p className="mt-5 text-sm text-clinical-muted">No CGM readings are connected for this patient.</p><Link to={`/messages?patient=${patient.slug}`} className="focus-ring mt-4 inline-flex items-center gap-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white"><MessageSquare size={17} /> Message patient</Link></section>
      <section className="surface p-5"><h2 className="text-lg font-semibold">Food log</h2><div className="mt-4 space-y-3 text-sm">{patientFood.length ? patientFood.map((entry) => <div key={entry.id} className="border-b border-clinical-border pb-3"><strong>{entry.meal}</strong> · {entry.time}<p>{entry.items} · {entry.carbs} carbs</p></div>) : <p className="text-clinical-muted">No food logged yet.</p>}</div></section>
      <section className="surface p-5 lg:col-span-2"><h2 className="text-lg font-semibold">Manual bolus log</h2><div className="mt-4 space-y-3 text-sm">{patientBolus.length ? patientBolus.map((entry) => <div key={entry.id} className="border-b border-clinical-border pb-3"><strong>{entry.meal}</strong> · {entry.time}<p>{entry.recorded} · {entry.carbs} carbs · pre-meal {entry.preMeal}</p></div>) : <p className="text-clinical-muted">No bolus logged yet.</p>}</div></section>
      <section className="surface p-5 lg:col-span-2"><h2 className="text-lg font-semibold">Manual glucose readings</h2><div className="mt-4 flex flex-wrap gap-3 text-sm">{patientGlucose.length ? patientGlucose.map((entry) => <div key={entry.id} className="rounded-md border border-clinical-border px-3 py-2"><strong>{entry.value} mg/dL</strong><span className="ml-2 text-clinical-muted">{entry.time}</span></div>) : <p className="text-clinical-muted">No manual readings yet.</p>}</div></section>
    </div>
  </>;
  return (
    <>
      <div className="mb-5">
        <Link to="/patients" className="focus-ring inline-flex items-center gap-2 rounded-md text-sm font-semibold text-clinical-primary"><ChevronLeft size={17} /> Back to patients</Link>
      </div>
      <section className="surface p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <Avatar label={patient.avatar} size="lg" />
            <div>
              <h1 className="text-2xl font-bold md:text-3xl">{patient.name}</h1>
              <p className="mt-1 text-sm text-clinical-muted">Patient ID: {patient.id} · Age: {patient.age} · {patient.diabetesType} · {patient.usesCgm ? 'Uses CGM' : 'CGM optional'}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Link to={`/messages?patient=${patient.slug}`} className="focus-ring inline-flex items-center gap-2 rounded-md border border-clinical-border px-4 py-2 text-sm font-semibold text-clinical-primary"><MessageSquare size={17} /> Message Patient</Link>
            <button onClick={() => setModalOpen(true)} className="focus-ring inline-flex items-center gap-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white"><Plus size={17} /> Add Note</button>
          </div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <MetricCard label="Current Glucose" value={`${patient.currentGlucose} mg/dL`} />
          <MetricCard label="Trend" value={patient.trend} />
          <MetricCard label="Time in Range" value="74%" />
          <MetricCard label="Average Glucose" value="151 mg/dL" />
          <MetricCard label="HBA1C" value="6.9%" />
          <MetricCard label="Last CGM Update" value="2 min ago" />
        </div>
      </section>
      <section className="surface mt-6 p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div><h2 className="text-xl font-semibold">Continuous Glucose Monitoring</h2><p className="text-sm text-clinical-muted">24-hour glucose pattern with low, target, and high zones.</p></div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="CGM time range">
            {['3H', '6H', '12H', '24H', '7D', '14D'].map((item) => (
              <button key={item} onClick={() => setRange(item)} className={`focus-ring rounded-md border px-3 py-1.5 text-sm font-semibold ${range === item ? 'border-clinical-primary bg-emerald-50 text-clinical-primaryDark' : 'border-clinical-border text-clinical-muted'}`}>{item}</button>
            ))}
          </div>
        </div>
        <CGMChart data={cgmReadings} />
      </section>
      <div className="mt-6 grid gap-6 xl:grid-cols-[340px_1fr]">
        <aside className="surface p-5">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-xl font-semibold"><Apple size={20} /> Food View</h2>
            <span className="rounded-md bg-clinical-secondary px-2 py-1 text-xs font-semibold text-clinical-primaryDark">Live patient entries</span>
          </div>
          <div className="mt-4 space-y-3">
            {patientFood.map((entry) => (
              <article key={entry.id} className="rounded-lg border border-clinical-border p-3">
                <div className="flex items-center justify-between gap-3">
                  <strong>{entry.meal}</strong>
                  <span className="text-xs text-clinical-muted">{entry.time}</span>
                </div>
                <p className="mt-1 text-sm text-clinical-muted">{entry.items}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
                  <span className="rounded-md bg-clinical-secondary px-2 py-1">{entry.carbs} carbs</span>
                  <span className="rounded-md bg-amber-50 px-2 py-1 text-clinical-warning">{entry.impact}</span>
                  <span className="rounded-md bg-emerald-50 px-2 py-1 text-clinical-success">{entry.status}</span>
                </div>
              </article>
            ))}
          </div>
        </aside>
        <section className="surface p-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div><h2 className="text-xl font-semibold">Digital Twin Forecast</h2><p className="text-sm text-clinical-muted">Personalized physiological-model glucose projection. Simulated data for design prototype.</p></div>
            <div className="group relative"><Info className="text-clinical-muted" size={18} /><span className="absolute right-0 top-7 hidden w-72 rounded-md border border-clinical-border bg-white p-3 text-xs shadow-clinical group-hover:block">Forecast generated from the patient's personalized physiological model.</span></div>
          </div>
          <div className="mb-5 grid gap-3 md:grid-cols-3">
            {forecastSnapshots.map((snapshot) => (
              <article key={snapshot.horizon} className="rounded-lg border border-clinical-border bg-clinical-bg p-4">
                <p className="text-xs font-semibold uppercase text-clinical-muted">After {snapshot.horizon}</p>
                <p className="mt-2 text-2xl font-bold text-clinical-primaryDark">{snapshot.glucose} mg/dL</p>
                <p className="mt-1 text-sm font-semibold">{snapshot.trend}</p>
                <p className="mt-2 text-xs text-clinical-muted">{snapshot.note}</p>
              </article>
            ))}
          </div>
          <DigitalTwinChart data={digitalTwinForecast} />
          <p className="mt-3 text-sm font-semibold text-clinical-primaryDark">Prediction horizon: 3 hours</p>
        </section>
      </div>
      <section className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Time in Range" value="74%" /><MetricCard label="Time Below Range" value="3%" /><MetricCard label="Time Above Range" value="23%" />
        <MetricCard label="Glucose Variability" value="32%" /><MetricCard label="Average Glucose" value="151 mg/dL" /><MetricCard label="GMI" value="6.9%" />
      </section>
      <section className="surface mt-6 p-5">
        <div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-semibold">Insulin Overview</h2><div className="flex rounded-md border border-clinical-border p-1">{['Basal', 'Bolus'].map((item) => <button key={item} onClick={() => setTab(item as 'Basal' | 'Bolus')} className={`focus-ring rounded px-4 py-1.5 text-sm font-semibold ${tab === item ? 'bg-clinical-primary text-white' : 'text-clinical-muted'}`}>{item}</button>)}</div></div>
        {tab === 'Basal' ? (
          <div className="grid gap-5 lg:grid-cols-2">
            <div><h3 className="font-semibold">Current Basal Schedule</h3><div className="mt-3 divide-y divide-clinical-border rounded-lg border border-clinical-border">{basalSchedule.map((row) => <div className="flex justify-between p-3" key={row.period}><span>{row.period}</span><strong>{row.current}</strong></div>)}</div></div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4"><h3 className="font-semibold">Digital Twin Suggested Basal</h3><div className="mt-3 divide-y divide-emerald-100">{basalSchedule.map((row) => <div className="flex justify-between py-3" key={row.period}><span>{row.period}</span><strong>{row.suggested}</strong></div>)}</div><ClinicalWarning />{basalConfirmed ? <p className="mt-4 inline-flex items-center gap-2 rounded-md bg-white px-3 py-2 text-sm font-semibold text-clinical-success"><CheckCircle2 size={17} /> Confirmed by doctor</p> : <button onClick={() => setBasalConfirmed(true)} className="focus-ring mt-4 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white">Confirm Basal Schedule</button>}</div>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
            <div className="divide-y divide-clinical-border rounded-lg border border-clinical-border">{patientBolus.map((entry) => <div className="grid gap-2 p-4 md:grid-cols-5" key={entry.id}><strong>{entry.time}</strong><span>{entry.meal}</span><span>Carbs: {entry.carbs}</span><span>Pre-meal: {entry.preMeal}</span><span>Recorded: {entry.recorded}</span></div>)}</div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4"><h3 className="font-semibold">Suggested Bolus</h3><p className="mt-2 text-3xl font-bold text-clinical-primaryDark">5.5 U</p><p className="mt-3 text-sm"><strong>Reason:</strong><br />Meal carbohydrates: 62g<br />Current glucose: 184 mg/dL<br />Active insulin: 1.2 U</p><div className="mt-4"><ClinicalWarning /></div></div>
          </div>
        )}
      </section>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_420px]">
        <section className="surface p-5"><h2 className="text-xl font-semibold">Recent Activity</h2><div className="mt-4 space-y-3">{activity.map(({ icon: Icon, text, time }) => <div key={text} className="flex gap-3 rounded-lg border border-clinical-border p-3"><Icon className="text-clinical-primary" size={18} /><div><p className="text-sm font-medium">{text}</p><p className="text-xs text-clinical-muted">{time}</p></div></div>)}</div></section>
        <section className="surface p-5"><div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Clinical Notes</h2><button onClick={() => setModalOpen(true)} className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm font-semibold text-clinical-primary">Add Note</button></div><div className="mt-4 space-y-3">{notes.map((item, index) => <div key={item} className="rounded-lg border border-clinical-border p-3"><p className="text-sm">{item}</p><p className="mt-2 text-xs text-clinical-muted">Sep {7 - index}, 2026</p></div>)}</div></section>
      </div>
      {modalOpen ? <Modal title="Add Clinical Note" onClose={() => setModalOpen(false)}><label className="block text-sm font-semibold" htmlFor="note">Note</label><textarea id="note" value={note} onChange={(event) => setNote(event.target.value)} className="focus-ring mt-2 min-h-32 w-full rounded-md border border-clinical-border p-3" /><label className="mt-4 block text-sm font-semibold" htmlFor="date">Date</label><input id="date" type="date" defaultValue="2026-09-07" className="focus-ring mt-2 w-full rounded-md border border-clinical-border p-3" /><button onClick={() => { if (note.trim()) setNotes([note.trim(), ...notes]); setNote(''); setModalOpen(false); }} className="focus-ring mt-5 rounded-md bg-clinical-primary px-4 py-2 font-semibold text-white">Save Note</button></Modal> : null}
    </>
  );
}
