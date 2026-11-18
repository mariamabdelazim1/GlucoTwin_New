import { useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { Activity, Apple, Plus, Syringe, TrendingUp } from 'lucide-react';
import { cgmReadings, digitalTwinForecast, forecastSnapshots } from '../data/cgm';
import { CGMChart } from '../components/charts/CGMChart';
import { DigitalTwinChart } from '../components/charts/DigitalTwinChart';
import { GlucoseValue } from '../components/clinical/GlucoseValue';
import { TrendIndicator } from '../components/clinical/TrendIndicator';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import type { BolusEntry, FoodEntry, Patient } from '../types';
import { updateMeal } from '../utils/sync';

const mealCarbs = (entry: FoodEntry, field: 'announced' | 'consumed') => {
  const canonical = field === 'announced' ? entry.announcedCarbsG : entry.consumedCarbsG;
  if (canonical !== undefined && canonical !== null) return canonical;
  if (field === 'consumed' && entry.status === 'planned') return null;
  const parsed = Number.parseFloat(entry.carbs);
  return Number.isFinite(parsed) ? parsed : null;
};

const mealStatus = (entry: FoodEntry) => entry.status === 'planned' ? 'planned' : 'eaten';

const mealTimestamp = (entry: FoodEntry) => {
  const instant = entry.actualEatingAt || entry.plannedEatingAt;
  if (instant) return Date.parse(instant) || 0;
  const match = entry.time.match(/^(\d{1,2}):(\d{2})/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : 0;
};

const mealDateTime = (entry: FoodEntry) => {
  const instant = entry.actualEatingAt || entry.plannedEatingAt;
  if (!instant) return entry.time;
  const date = new Date(instant);
  return Number.isNaN(date.getTime()) ? entry.time : date.toLocaleString([], {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
};

const mealOptionLabel = (entry: FoodEntry) => {
  const carbs = mealCarbs(entry, 'announced');
  return `${entry.meal} · ${mealDateTime(entry)} · ${carbs === null ? 'carbs not provided' : `${carbs}g`} · ${mealStatus(entry)}`;
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
  const patientFood = foodEntries.filter((entry) => entry.patientSlug === patient.slug);
  const patientBolus = bolusEntries.filter((entry) => entry.patientSlug === patient.slug);
  const selectableMeals = patientFood.filter((entry) => entry.status !== 'cancelled').sort((a, b) => mealTimestamp(b) - mealTimestamp(a));
  const [mealForm, setMealForm] = useState({ meal: 'Lunch', items: '', carbs: '', glucose: '', status: 'planned' as 'planned' | 'eaten' });
  const [bolusForm, setBolusForm] = useState({ meal: 'Lunch', mealId: '', carbs: '', recorded: '' });
  const [bolusError, setBolusError] = useState('');
  const selectedMeal = selectableMeals.find((entry) => entry.id === bolusForm.mealId);

  const currentTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const addFood = () => {
    if (!mealForm.items.trim() || !mealForm.carbs.trim()) return;
    const eventAt = new Date().toISOString();
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
        status: mealForm.status,
        plannedEatingAt: eventAt,
        actualEatingAt: mealForm.status === 'eaten' ? eventAt : null,
        announcedCarbsG: Number(mealForm.carbs),
        consumedCarbsG: mealForm.status === 'eaten' ? Number(mealForm.carbs) : null,
        ...(mealForm.status === 'eaten' ? { confirmAnnouncedAmount: true } : {}),
        syncState: 'pending', syncAttempts: 0,
      },
      ...current,
    ]);
    setMealForm({ meal: 'Lunch', items: '', carbs: '', glucose: '', status: 'planned' });
  };

  const addBolus = () => {
    const units = Number(bolusForm.recorded);
    const carbsText = bolusForm.carbs.trim();
    const carbsG = selectedMeal || carbsText === '' ? null : Number(carbsText);
    if (!bolusForm.recorded.trim() || !Number.isFinite(units) || units < 0) {
      setBolusError('Enter a finite, non-negative insulin dose.');
      return;
    }
    if (carbsG !== null && (!Number.isFinite(carbsG) || carbsG < 0)) {
      setBolusError('Carbs must be a finite, non-negative number or left blank.');
      return;
    }
    setBolusEntries((current) => [
      {
        id: crypto.randomUUID(),
        patientSlug: patient.slug,
        patient: patient.name,
        time: currentTime(),
        meal: selectedMeal?.meal || bolusForm.meal,
        mealId: selectedMeal?.id || null,
        carbs: carbsG === null ? 'Not provided' : `${carbsG}g`,
        carbsG,
        recommended: 'Doctor review',
        administeredUnits: units,
        recorded: `${units} U`,
        administeredAt: new Date().toISOString(),
        syncState: 'pending', syncAttempts: 0,
      },
      ...current,
    ]);
    setBolusForm({ meal: 'Lunch', mealId: '', carbs: '', recorded: '' });
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
              <select value={mealForm.status} onChange={(event) => setMealForm({ ...mealForm, status: event.target.value as 'planned' | 'eaten' })} className="focus-ring rounded-md border border-clinical-border px-3 py-2 text-sm"><option value="planned">Plan for later</option><option value="eaten">Already eaten</option></select>
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
                {entry.status === 'planned' && entry.version ? <div className="mt-2 flex gap-2"><button onClick={() => void changeMeal(entry, 'eaten')} className="rounded bg-clinical-primary px-2 py-1 text-xs font-semibold text-white">Mark eaten</button><button onClick={() => void changeMeal(entry, 'cancelled')} className="rounded border border-clinical-border px-2 py-1 text-xs font-semibold">Cancel</button></div> : null}
              </article>
            ))}
          </div>
        </aside>

        <section className="space-y-6">
          <section className="surface min-w-0 overflow-hidden p-5">
            <h2 className="flex items-center gap-2 text-xl font-semibold"><Syringe size={20} /> Manual bolus log</h2>
            <div className="mt-4 grid min-w-0 gap-3">
              <label className="grid min-w-0 gap-1 text-sm font-semibold">
                Related meal <span className="font-normal text-clinical-muted">Optional</span>
                <select aria-label="Related meal" value={bolusForm.mealId} onChange={(event) => setBolusForm({ ...bolusForm, mealId: event.target.value, carbs: '' })} className="focus-ring min-w-0 rounded-md border border-clinical-border px-3 py-2 text-sm font-normal">
                  <option value="">No linked meal</option>
                  {selectableMeals.map((entry) => <option key={entry.id} value={entry.id}>{mealOptionLabel(entry)}</option>)}
                </select>
              </label>
              {selectedMeal ? <div role="status" className="rounded-lg border border-[#B9D7E9] bg-[#F1F8FC] p-3 text-sm">
                <p className="font-semibold">{selectedMeal.meal} · {mealStatus(selectedMeal)}</p>
                <p className="mt-1 text-clinical-muted">Planned carbohydrates: <strong className="text-clinical-text">{mealCarbs(selectedMeal, 'announced') ?? 'Not provided'}{mealCarbs(selectedMeal, 'announced') === null ? '' : 'g'}</strong></p>
                <p className="mt-1 text-clinical-muted">{mealStatus(selectedMeal) === 'eaten' ? <>Confirmed consumed carbohydrates: <strong className="text-clinical-text">{mealCarbs(selectedMeal, 'consumed') ?? 'Not provided'}{mealCarbs(selectedMeal, 'consumed') === null ? '' : 'g'}</strong></> : 'Consumption has not been confirmed.'}</p>
                <p className="mt-2 text-xs text-clinical-muted">Meal carbohydrates are read-only here and are counted only from the meal record.</p>
              </div> : null}
              <div className={`grid min-w-0 gap-3 ${selectedMeal ? 'sm:grid-cols-[1fr_auto]' : 'sm:grid-cols-[1fr_1fr_1fr_auto]'}`}>
                {!selectedMeal ? <select aria-label="Dose meal type" value={bolusForm.meal} onChange={(event) => setBolusForm({ ...bolusForm, meal: event.target.value })} className="focus-ring min-w-0 rounded-md border border-clinical-border px-3 py-2 text-sm">
                  <option>Breakfast</option><option>Lunch</option><option>Dinner</option><option>Snack</option>
                </select> : null}
                {!selectedMeal ? <input aria-label="Carbs (g, optional)" value={bolusForm.carbs} onChange={(event) => setBolusForm({ ...bolusForm, carbs: event.target.value })} inputMode="decimal" placeholder="Carbs (g, optional)" className="focus-ring min-w-0 rounded-md border border-clinical-border px-3 py-2 text-sm" /> : null}
                <input aria-label="Bolus units" value={bolusForm.recorded} onChange={(event) => setBolusForm({ ...bolusForm, recorded: event.target.value })} inputMode="decimal" placeholder="Bolus units" className="focus-ring min-w-0 rounded-md border border-clinical-border px-3 py-2 text-sm" />
                <button onClick={addBolus} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white hover:bg-clinical-primaryDark"><Plus size={16} /> Log</button>
              </div>
            </div>
            {bolusError ? <p role="alert" className="mt-2 text-sm text-red-700">{bolusError}</p> : null}
            <div className="mt-4 divide-y divide-clinical-border rounded-lg border border-clinical-border">
              {patientBolus.slice(0, 3).map((entry) => (
                <div className="grid min-w-0 gap-2 p-3 text-sm md:grid-cols-[auto_1fr_1.4fr_1fr]" key={entry.id}>
                  <strong>{entry.time}</strong><span>{entry.meal}</span>
                  {entry.mealId ? (() => {
                    const linked = patientFood.find((meal) => meal.id === entry.mealId);
                    return linked ? <span><span className="block font-semibold">Related meal: {linked.meal} · {mealStatus(linked)}</span><span className="block text-xs text-clinical-muted">Planned {mealCarbs(linked, 'announced') ?? 'unknown'}{mealCarbs(linked, 'announced') === null ? '' : 'g'}{mealStatus(linked) === 'eaten' ? ` · Confirmed ${mealCarbs(linked, 'consumed') ?? 'unknown'}${mealCarbs(linked, 'consumed') === null ? '' : 'g'}` : ' · Not yet consumed'}</span></span> : <span>Related meal unavailable</span>;
                  })() : <span>Carbs: {entry.carbs || 'Not provided'}</span>}
                  <span>Recorded: {entry.recorded}</span>
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
