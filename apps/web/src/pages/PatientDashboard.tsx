import { useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { Activity, Apple, Plus, Syringe, TrendingUp } from 'lucide-react';
import { cgmReadings, digitalTwinForecast, forecastSnapshots } from '../data/cgm';
import { CGMChart } from '../components/charts/CGMChart';
import { DigitalTwinChart } from '../components/charts/DigitalTwinChart';
import { BolusSuggestionCard } from '../components/clinical/BolusSuggestionCard';
import { GlucoseValue } from '../components/clinical/GlucoseValue';
import { TrendIndicator } from '../components/clinical/TrendIndicator';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import type { BolusEntry, FoodEntry, Patient } from '../types';
import { updateMeal } from '../utils/sync';

const timestampValue = (instant?: string | null) => {
  if (!instant) return null;
  const value = Date.parse(instant);
  return Number.isNaN(value) ? null : value;
};

export const formatLocalDateTime = (instant?: string | null) => {
  const value = timestampValue(instant);
  if (value === null) return 'Date unavailable';
  const date = new Date(value);
  const day = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const time = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return `${day} · ${time}`;
};

const foodInstant = (entry: FoodEntry) => entry.status === 'eaten' ? entry.actualEatingAt : entry.plannedEatingAt;

const foodDateLabel = (entry: FoodEntry) => {
  const label = entry.status === 'eaten' ? 'Eaten' : 'Planned';
  return `${label}: ${formatLocalDateTime(foodInstant(entry))}`;
};

const descendingTimestamp = (left?: string | null, right?: string | null) => {
  const leftValue = timestampValue(left);
  const rightValue = timestampValue(right);
  if (leftValue === null) return rightValue === null ? 0 : 1;
  if (rightValue === null) return -1;
  return rightValue - leftValue;
};

const bolusDateTime = (entry: BolusEntry) => formatLocalDateTime(entry.administeredAt);

const recordedUnits = (entry: BolusEntry) => {
  if (entry.administeredUnits !== undefined) return `${entry.administeredUnits} U`;
  return entry.recorded;
};

const validCarbs = (value: string) => {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
};

const displayCarbs = (entry: FoodEntry) => {
  if (entry.announcedCarbsG !== undefined && entry.announcedCarbsG !== null) return `${entry.announcedCarbsG}g`;
  return entry.carbs || 'Not provided';
};

const currentLocalTime = (instant: string) => {
  const date = new Date(instant);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

export function PatientDashboard({
  focusFood = false,
  patient,
  doctorName,
  assignmentStatus,
  foodEntries,
  setFoodEntries,
  bolusEntries,
  setBolusEntries,
}: {
  focusFood?: boolean;
  patient: Patient;
  doctorName: string;
  assignmentStatus: 'pending' | 'accepted' | 'declined';
  foodEntries: FoodEntry[];
  setFoodEntries: Dispatch<SetStateAction<FoodEntry[]>>;
  bolusEntries: BolusEntry[];
  setBolusEntries: Dispatch<SetStateAction<BolusEntry[]>>;
}) {
  const patientFood = foodEntries
    .filter((entry) => entry.patientSlug === patient.slug)
    .sort((left, right) => descendingTimestamp(foodInstant(left), foodInstant(right)));
  const patientBolus = bolusEntries
    .filter((entry) => entry.patientSlug === patient.slug)
    .sort((left, right) => descendingTimestamp(left.administeredAt, right.administeredAt));
  const [mealForm, setMealForm] = useState({ meal: 'Lunch', items: '', carbs: '' });
  const [foodError, setFoodError] = useState('');
  const [bolusUnits, setBolusUnits] = useState('');
  const [bolusError, setBolusError] = useState('');

  const addFood = () => {
    const carbs = validCarbs(mealForm.carbs);
    if (!mealForm.items.trim()) {
      setFoodError('Enter the food items.');
      return;
    }
    if (carbs === null) {
      setFoodError('Carbohydrates must be a finite, non-negative number.');
      return;
    }
    const eventAt = new Date().toISOString();
    setFoodEntries((current) => [
      {
        id: crypto.randomUUID(),
        patientSlug: patient.slug,
        patient: patient.name,
        time: currentLocalTime(eventAt),
        meal: mealForm.meal,
        items: mealForm.items.trim(),
        carbs: `${carbs}g`,
        impact: 'Pending CGM impact',
        status: 'eaten',
        plannedEatingAt: eventAt,
        actualEatingAt: eventAt,
        announcedCarbsG: carbs,
        consumedCarbsG: carbs,
        confirmAnnouncedAmount: true,
        syncState: 'pending', syncAttempts: 0,
      },
      ...current,
    ]);
    setMealForm({ meal: 'Lunch', items: '', carbs: '' });
    setFoodError('');
  };

  const addBolus = () => {
    const units = Number(bolusUnits);
    if (!bolusUnits.trim() || !Number.isFinite(units) || units < 0) {
      setBolusError('Enter a finite, non-negative insulin dose.');
      return;
    }
    const administeredAt = new Date().toISOString();
    setBolusEntries((current) => [
      {
        id: crypto.randomUUID(),
        patientSlug: patient.slug,
        patient: patient.name,
        time: currentLocalTime(administeredAt),
        administeredUnits: units,
        recorded: `${units} U`,
        administeredAt,
        syncState: 'pending', syncAttempts: 0,
      },
      ...current,
    ]);
    setBolusUnits('');
    setBolusError('');
  };

  const changeMeal = async (entry: FoodEntry, status: 'eaten' | 'cancelled') => {
    if (!entry.version) return;
    const result = await updateMeal(entry.id, {
      expectedVersion: entry.version,
      mutationId: crypto.randomUUID(),
      status,
      ...(status === 'eaten' ? { actualEatingAt: new Date().toISOString(), confirmAnnouncedAmount: true } : {}),
    });
    setFoodEntries((current) => current.map((item) => item.id === entry.id ? result.meal : item));
  };

  return (
    <div className="patient-dashboard-content">
      <PageHeader title={`Welcome, ${patient.name}`} subtitle={patient.usesCgm ? 'Your glucose, forecast, food, and insulin records in one place.' : 'Your food and insulin records in one place.'} />
      {patient.slug === 'omar-hassan' ? <div role="status" className="mb-5 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Demo patient: sample CGM readings, forecasts, and historical logs. This is not a live sensor feed.</div> : null}
      {assignmentStatus !== 'accepted' ? <div className="surface mb-6 p-4 text-sm"><strong>Doctor request {assignmentStatus}</strong><p className="mt-1 text-clinical-muted">{doctorName} will appear here after accepting your request. You can still record food and insulin.</p></div> : null}
      {patient.usesCgm ? (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard blue label="Current Glucose" value={`${patient.currentGlucose} mg/dL`} sub={patient.status} />
        <MetricCard blue label="Trend" value={patient.trend} sub="Latest CGM direction" />
        <MetricCard blue label="Time in Range" value={`${patient.timeInRange}%`} sub="Today" />
        <MetricCard blue label="Last CGM Reading" value={patient.lastReading} sub="Sample sensor data" />
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
              <input aria-label="Carbohydrates in grams" value={mealForm.carbs} onChange={(event) => setMealForm({ ...mealForm, carbs: event.target.value })} inputMode="decimal" placeholder="Carbs g" className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm" />
              <button onClick={addFood} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-3 py-2 text-sm font-semibold text-white hover:bg-clinical-primaryDark"><Plus size={16} /> Add food</button>
            </div>
            {foodError ? <p role="alert" className="mt-2 text-sm text-red-700">{foodError}</p> : null}
          </div>
          <div className="mt-4 space-y-3">
            {patientFood.map((entry) => (
              <article key={entry.id} className="rounded-lg border border-clinical-border p-3">
                <div className="flex items-center justify-between gap-3">
                  <strong>{entry.meal}</strong>
                  <span className="text-right text-xs text-clinical-muted">{foodDateLabel(entry)}</span>
                </div>
                <p className="mt-1 text-sm text-clinical-muted">{entry.items}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
                  <span className="rounded-md bg-clinical-secondary px-2 py-1">{displayCarbs(entry)} carbs</span>
                  <span className="rounded-md bg-amber-50 px-2 py-1 text-clinical-warning">{entry.impact}</span>
                  <span className="rounded-md bg-emerald-50 px-2 py-1 text-clinical-success">{entry.status}</span>
                </div>
                {entry.status === 'planned' && entry.version ? <div className="mt-2 flex gap-2"><button onClick={() => void changeMeal(entry, 'eaten')} className="rounded bg-clinical-primary px-2 py-1 text-xs font-semibold text-white">Mark eaten</button><button onClick={() => void changeMeal(entry, 'cancelled')} className="rounded border border-clinical-border px-2 py-1 text-xs font-semibold">Cancel</button></div> : null}
              </article>
            ))}
          </div>
        </aside>

        <section className="space-y-6">
          <BolusSuggestionCard />
          <section className="surface min-w-0 overflow-hidden p-5">
            <h2 className="flex items-center gap-2 text-xl font-semibold"><Syringe size={20} /> Manual bolus log</h2>
            <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
              <input aria-label="Bolus units" value={bolusUnits} onChange={(event) => setBolusUnits(event.target.value)} inputMode="decimal" placeholder="Bolus units" className="focus-ring min-w-0 rounded-md border border-clinical-border px-3 py-2 text-sm" />
              <button onClick={addBolus} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white hover:bg-clinical-primaryDark"><Plus size={16} /> Log</button>
            </div>
            {bolusError ? <p role="alert" className="mt-2 text-sm text-red-700">{bolusError}</p> : null}
            <div className="mt-4 divide-y divide-clinical-border rounded-lg border border-clinical-border">
              {patientBolus.slice(0, 3).map((entry) => (
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 p-3 text-sm" key={entry.id}>
                  <strong>{recordedUnits(entry)}</strong>
                  <span className="text-clinical-muted">{bolusDateTime(entry)}</span>
                </div>
              ))}
            </div>
          </section>
          {patient.usesCgm ? <section className="surface min-w-0 overflow-hidden p-5">
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
            <CGMChart blue data={cgmReadings} />
          </section> : null}
          {patient.usesCgm ? <section className="surface min-w-0 overflow-hidden p-5">
            <h2 className="text-xl font-semibold">Digital Twin Forecast Graph</h2>
            <DigitalTwinChart blue data={digitalTwinForecast} />
          </section> : null}
        </section>
      </div>
    </div>
  );
}
