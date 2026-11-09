import { useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { Activity, Apple, Bot, Droplets, MessageSquare, Plus, Send, Syringe, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cgmReadings, digitalTwinForecast, forecastSnapshots } from '../data/cgm';
import { CGMChart } from '../components/charts/CGMChart';
import { DigitalTwinChart } from '../components/charts/DigitalTwinChart';
import { GlucoseValue } from '../components/clinical/GlucoseValue';
import { TrendIndicator } from '../components/clinical/TrendIndicator';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import type { BolusEntry, FoodEntry, Message, Patient, PatientProfile } from '../types';
import type { GlucoseEntry } from '../utils/sync';

export function PatientDashboard({
  focusFood = false,
  patient,
  doctorName,
  assignmentStatus,
  setMessages,
  foodEntries,
  setFoodEntries,
  bolusEntries,
  setBolusEntries,
  glucoseEntries,
  setGlucoseEntries,
  patientProfile,
}: {
  focusFood?: boolean;
  patient: Patient;
  doctorName: string;
  assignmentStatus: 'pending' | 'accepted' | 'declined';
  setMessages: Dispatch<SetStateAction<Message[]>>;
  foodEntries: FoodEntry[];
  setFoodEntries: Dispatch<SetStateAction<FoodEntry[]>>;
  bolusEntries: BolusEntry[];
  setBolusEntries: Dispatch<SetStateAction<BolusEntry[]>>;
  glucoseEntries: GlucoseEntry[];
  setGlucoseEntries: Dispatch<SetStateAction<GlucoseEntry[]>>;
  patientProfile: PatientProfile;
}) {
  const patientFood = foodEntries.filter((entry) => entry.patientSlug === patient.slug);
  const patientBolus = bolusEntries.filter((entry) => entry.patientSlug === patient.slug);
  const patientGlucose = glucoseEntries.filter((entry) => entry.patientSlug === patient.slug).sort((a, b) => b.recordedAt.localeCompare(a.recordedAt));
  const [draft, setDraft] = useState('');
  const [botReply, setBotReply] = useState(`Ask a question here. Your message will also be sent to ${doctorName}.`);
  const [mealForm, setMealForm] = useState({ meal: 'Lunch', items: '', carbs: '', glucose: '' });
  const [bolusForm, setBolusForm] = useState({ meal: 'Lunch', carbs: '', preMeal: '', recorded: '' });
  const [glucoseValue, setGlucoseValue] = useState('');

  const sendToDoctor = () => {
    if (!draft.trim() || assignmentStatus !== 'accepted') return;
    const text = draft.trim();
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        doctorId: patientProfile.selectedDoctorId,
        patientSlug: patient.slug,
        patient: patient.name,
        avatar: patient.avatar,
        from: 'patient',
        text,
        time: 'Now',
        unread: true,
      },
    ]);
    setBotReply(`Your message was recorded for ${doctorName}.`);
    setDraft('');
  };

  const currentTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const addFood = () => {
    if (!mealForm.items.trim() || !mealForm.carbs.trim()) return;
    setFoodEntries((current) => [
      {
        id: crypto.randomUUID(),
        patientSlug: patient.slug,
        patient: patient.name,
        time: currentTime(),
        meal: mealForm.meal,
        items: mealForm.items.trim(),
        carbs: `${mealForm.carbs.trim()}g`,
        impact: mealForm.glucose.trim() ? `${mealForm.glucose.trim()} mg/dL noted` : 'Pending CGM impact',
        status: 'Recorded',
      },
      ...current,
    ]);
    setMealForm({ meal: 'Lunch', items: '', carbs: '', glucose: '' });
  };

  const addBolus = () => {
    if (!bolusForm.carbs.trim() || !bolusForm.preMeal.trim() || !bolusForm.recorded.trim()) return;
    setBolusEntries((current) => [
      {
        id: crypto.randomUUID(),
        patientSlug: patient.slug,
        patient: patient.name,
        time: currentTime(),
        meal: bolusForm.meal,
        carbs: `${bolusForm.carbs.trim()}g`,
        preMeal: `${bolusForm.preMeal.trim()} mg/dL`,
        recommended: 'Doctor review',
        recorded: `${bolusForm.recorded.trim()} U`,
      },
      ...current,
    ]);
    setBolusForm({ meal: 'Lunch', carbs: '', preMeal: '', recorded: '' });
  };

  const addGlucose = () => {
    const value = Number(glucoseValue);
    if (!Number.isFinite(value) || value < 20 || value > 600) return;
    const now = new Date();
    setGlucoseEntries((current) => [{ id: crypto.randomUUID(), patientSlug: patient.slug, value, time: currentTime(), recordedAt: now.toISOString() }, ...current]);
    setGlucoseValue('');
  };

  return (
    <>
      <PageHeader title={`Welcome, ${patient.name}`} subtitle={patient.usesCgm ? 'Your glucose, forecast, food, and care-team messages in one place.' : 'Your manual readings, food, insulin, and care-team messages in one place.'} />
      {patient.slug === 'omar-hassan' ? <div role="status" className="mb-5 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Demo patient: sample CGM readings, forecasts, and historical logs. This is not a live sensor feed.</div> : null}
      {assignmentStatus !== 'accepted' ? <div className="surface mb-6 p-4 text-sm"><strong>Doctor request {assignmentStatus}</strong><p className="mt-1 text-clinical-muted">{doctorName} will appear here after accepting your request. You can still record food and insulin.</p></div> : null}
      <section className="surface mb-6 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="flex items-center gap-2 text-lg font-semibold"><Droplets size={20} /> Manual glucose readings</h2><span className="text-xs text-clinical-muted">Shared with your assigned doctor</span></div>
        <div className="mt-4 flex flex-wrap gap-2"><input aria-label="Glucose reading in mg/dL" type="number" min="20" max="600" value={glucoseValue} onChange={(event) => setGlucoseValue(event.target.value)} placeholder="mg/dL" className="focus-ring w-40 rounded-md border border-clinical-border px-3 py-2" /><button onClick={addGlucose} className="focus-ring inline-flex items-center gap-2 rounded-md bg-clinical-primary px-4 py-2 font-semibold text-white"><Plus size={16} /> Record</button></div>
        {patientGlucose.length ? <div className="mt-4 flex flex-wrap gap-2">{patientGlucose.slice(0, 6).map((entry) => <div key={entry.id} className="rounded-md border border-clinical-border px-3 py-2 text-sm"><strong>{entry.value} mg/dL</strong><span className="ml-2 text-clinical-muted">{entry.time}</span></div>)}</div> : <p className="mt-3 text-sm text-clinical-muted">No manual readings yet.</p>}
      </section>
      {patient.usesCgm ? (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Current Glucose" value={`${patient.currentGlucose} mg/dL`} sub={patient.status} />
        <MetricCard label="Trend" value={patient.trend} sub="Latest CGM direction" />
        <MetricCard label="Time in Range" value={`${patient.timeInRange}%`} sub="Today" />
        <MetricCard label="Last CGM Reading" value={patient.lastReading} sub="Sample sensor data" />
      </div>
      ) : <section className="surface p-5"><h2 className="font-semibold">No CGM connected yet</h2><p className="mt-1 text-sm text-clinical-muted">Glucose charts and forecasts will appear when CGM data is available.</p></section>}

      <div className="mt-6 grid gap-6 xl:grid-cols-[340px_1fr]">
        <aside className={`surface p-5 ${focusFood ? 'ring-2 ring-clinical-primary' : ''}`}>
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-xl font-semibold"><Apple size={20} /> Food</h2>
            <span className="rounded-md bg-clinical-secondary px-2 py-1 text-xs font-semibold text-clinical-primaryDark">Shared with assigned doctor</span>
          </div>
          <div className="mt-4 rounded-lg border border-clinical-border bg-clinical-bg p-3">
            <div className="grid gap-2">
              <select value={mealForm.meal} onChange={(event) => setMealForm({ ...mealForm, meal: event.target.value })} className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm">
                <option>Breakfast</option><option>Lunch</option><option>Dinner</option><option>Snack</option>
              </select>
              <input value={mealForm.items} onChange={(event) => setMealForm({ ...mealForm, items: event.target.value })} placeholder="Food items" className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" />
              <div className="grid grid-cols-2 gap-2">
                <input value={mealForm.carbs} onChange={(event) => setMealForm({ ...mealForm, carbs: event.target.value })} inputMode="numeric" placeholder="Carbs g" className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" />
                <input value={mealForm.glucose} onChange={(event) => setMealForm({ ...mealForm, glucose: event.target.value })} inputMode="numeric" placeholder="Glucose" className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" />
              </div>
              <button onClick={addFood} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-3 py-2 text-sm font-semibold text-white hover:bg-clinical-primaryDark"><Plus size={16} /> Add food</button>
            </div>
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

        <section className="space-y-6">
          <section className="surface p-5">
            <h2 className="flex items-center gap-2 text-xl font-semibold"><Syringe size={20} /> Manual bolus log</h2>
            <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr_1fr_1fr_auto]">
              <select value={bolusForm.meal} onChange={(event) => setBolusForm({ ...bolusForm, meal: event.target.value })} className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm">
                <option>Breakfast</option><option>Lunch</option><option>Dinner</option><option>Snack</option>
              </select>
              <input value={bolusForm.carbs} onChange={(event) => setBolusForm({ ...bolusForm, carbs: event.target.value })} inputMode="numeric" placeholder="Carbs g" className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" />
              <input value={bolusForm.preMeal} onChange={(event) => setBolusForm({ ...bolusForm, preMeal: event.target.value })} inputMode="numeric" placeholder="Pre-meal glucose" className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" />
              <input value={bolusForm.recorded} onChange={(event) => setBolusForm({ ...bolusForm, recorded: event.target.value })} inputMode="decimal" placeholder="Bolus units" className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" />
              <button onClick={addBolus} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white hover:bg-clinical-primaryDark"><Plus size={16} /> Log</button>
            </div>
            <div className="mt-4 divide-y divide-clinical-border rounded-lg border border-clinical-border">
              {patientBolus.slice(0, 3).map((entry) => (
                <div className="grid gap-2 p-3 text-sm md:grid-cols-5" key={entry.id}><strong>{entry.time}</strong><span>{entry.meal}</span><span>Carbs: {entry.carbs}</span><span>Pre-meal: {entry.preMeal}</span><span>Recorded: {entry.recorded}</span></div>
              ))}
            </div>
          </section>
          <section className="surface p-5">
            <h2 className="text-xl font-semibold">My medical info</h2>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div><dt className="text-xs font-semibold uppercase text-clinical-muted">Age</dt><dd className="font-semibold">{patientProfile.age}</dd></div>
              <div><dt className="text-xs font-semibold uppercase text-clinical-muted">Weight</dt><dd className="font-semibold">{patientProfile.weight} kg</dd></div>
              <div><dt className="text-xs font-semibold uppercase text-clinical-muted">Height</dt><dd className="font-semibold">{patientProfile.height} cm</dd></div>
              <div><dt className="text-xs font-semibold uppercase text-clinical-muted">Type</dt><dd className="font-semibold">{patientProfile.diabetesType || 'Not provided'}</dd></div>
              <div><dt className="text-xs font-semibold uppercase text-clinical-muted">Insulin</dt><dd className="font-semibold">{patientProfile.insulinPlan}</dd></div>
            </dl>
          </section>
          {patient.usesCgm ? <section className="surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-xl font-semibold"><TrendingUp size={20} /> Predicted Glucose</h2>
              <span className="text-sm font-semibold text-clinical-muted">Simulated digital twin</span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {forecastSnapshots.map((snapshot) => (
                <article key={snapshot.horizon} className="rounded-lg border border-clinical-border bg-white p-4">
                  <p className="text-xs font-semibold uppercase text-clinical-muted">After {snapshot.horizon}</p>
                  <p className="mt-2 text-2xl font-bold text-clinical-primaryDark">{snapshot.glucose} mg/dL</p>
                  <p className="mt-1 text-sm font-semibold">{snapshot.trend}</p>
                  <p className="mt-2 text-xs text-clinical-muted">{snapshot.note}</p>
                </article>
              ))}
            </div>
          </section> : null}
          {patient.usesCgm ? <section className="surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-xl font-semibold"><Activity size={20} /> CGM Graph</h2>
              <div className="text-sm"><GlucoseValue value={patient.currentGlucose} /> <span className="ml-2"><TrendIndicator trend={patient.trend} /></span></div>
            </div>
            <CGMChart data={cgmReadings} />
          </section> : null}
          {patient.usesCgm ? <section className="surface p-5">
            <h2 className="text-xl font-semibold">Digital Twin Forecast Graph</h2>
            <DigitalTwinChart data={digitalTwinForecast} />
          </section> : null}
          <section className="surface p-5">
            <div className="flex items-center gap-2">
              <Bot className="text-clinical-primary" size={20} />
              <h2 className="text-xl font-semibold">Care-team messages</h2>
            </div>
            <p className="mt-2 rounded-lg border border-emerald-100 bg-emerald-50 p-3 text-sm text-clinical-primaryDark">{assignmentStatus === 'accepted' ? botReply : 'Messaging opens after your doctor accepts your request.'}</p>
            {assignmentStatus === 'accepted' ? <>
            <label className="mt-4 block text-sm font-semibold" htmlFor="patient-chat">Message or question</label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <input
                id="patient-chat"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && sendToDoctor()}
                placeholder="Example: My glucose is rising after lunch. What should I do?"
                className="focus-ring min-w-0 flex-1 rounded-md border border-clinical-border px-3 py-2"
              />
              <button onClick={sendToDoctor} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-4 py-2 font-semibold text-white hover:bg-clinical-primaryDark">
                <Send size={18} /> Send to doctor
              </button>
            </div>
            <Link to="/messages" className="focus-ring mt-4 inline-flex items-center gap-2 rounded-md border border-clinical-border px-4 py-2 font-semibold text-clinical-primary hover:bg-clinical-secondary">
              <MessageSquare size={18} /> Open full messages
            </Link>
            </> : null}
          </section>
        </section>
      </div>
    </>
  );
}
