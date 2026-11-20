import { useState } from 'react';
import { Calculator, ChevronDown } from 'lucide-react';

export type BolusSuggestionDemoState = 'meal' | 'high-glucose';

const suggestionStates = {
  meal: {
    switchLabel: 'Meal logged',
    badge: 'Meal logged',
    badgeClass: 'bg-clinical-secondary text-clinical-primaryDark',
    title: 'Lunch · 45 g carbs',
    context: 'Meal context ready for simulation',
    estimateLabel: 'Meal bolus estimate',
    details: [
      ['Meal', 'Lunch'],
      ['Carbohydrates', '45 g'],
      ['Meal status', 'Logged'],
    ],
  },
  'high-glucose': {
    switchLabel: 'High glucose',
    badge: 'High glucose',
    badgeClass: 'bg-amber-50 text-amber-800',
    title: 'Glucose above your target',
    context: '214 mg/dL · Sample reading at 23:00',
    estimateLabel: 'Correction bolus estimate',
    details: [
      ['Current glucose', '214 mg/dL'],
      ['Sample target range', '70–180 mg/dL'],
      ['Reading time', '23:00'],
    ],
  },
} as const;

export function BolusSuggestionCard({ initialState = 'meal' }: { initialState?: BolusSuggestionDemoState }) {
  const [demoState, setDemoState] = useState<BolusSuggestionDemoState>(initialState);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const suggestion = suggestionStates[demoState];

  return (
    <section className="surface min-w-0 overflow-hidden p-5" aria-labelledby="bolus-recommendation-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-clinical-border pb-3">
        <h2 id="bolus-recommendation-title" className="flex items-center gap-2 text-xl font-semibold">
          <Calculator size={20} aria-hidden="true" /> Bolus Recommendation
        </h2>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="text-xs font-semibold text-clinical-muted sm:text-sm">Simulation preview</span>
          <div className="flex rounded-md border border-clinical-border bg-clinical-bg p-0.5" role="group" aria-label="Bolus recommendation demo state">
            {(Object.keys(suggestionStates) as BolusSuggestionDemoState[]).map((state) => (
              <button
                key={state}
                type="button"
                aria-pressed={demoState === state}
                onClick={() => setDemoState(state)}
                className={`focus-ring rounded px-2 py-1 text-xs font-semibold ${demoState === state ? 'bg-white text-clinical-primaryDark shadow-sm' : 'text-clinical-muted hover:text-clinical-primaryDark'}`}
              >
                {suggestionStates[state].switchLabel}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 grid min-w-0 items-center gap-4 md:grid-cols-[minmax(0,1fr)_minmax(180px,0.72fr)_auto]">
        <div className="min-w-0">
          <span className={`inline-flex rounded-md px-2 py-1 text-xs font-bold uppercase tracking-wide ${suggestion.badgeClass}`}>
            {suggestion.badge}
          </span>
          <p className="mt-2 font-semibold text-clinical-primaryDark">{suggestion.title}</p>
          <p className="mt-0.5 text-sm text-clinical-muted">{suggestion.context}</p>
        </div>

        <div className="border-clinical-border md:border-l md:pl-5">
          <p className="text-sm text-clinical-muted">{suggestion.estimateLabel}</p>
          <p className="mt-1 text-2xl font-bold text-clinical-primaryDark" aria-label="Dose unavailable">— U</p>
        </div>

        <button
          type="button"
          aria-expanded={detailsOpen}
          aria-controls="bolus-suggestion-details"
          onClick={() => setDetailsOpen((open) => !open)}
          className="focus-ring inline-flex items-center justify-center gap-2 rounded-md border border-clinical-primary px-3 py-2 text-sm font-semibold text-clinical-primary hover:bg-clinical-secondary"
        >
          Review details
          <ChevronDown size={16} aria-hidden="true" className={`transition-transform ${detailsOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {detailsOpen ? (
        <div id="bolus-suggestion-details" className="mt-4 rounded-lg border border-clinical-border bg-clinical-bg p-4">
          <p className="text-xs font-bold uppercase tracking-wide text-clinical-muted">Sample inputs</p>
          <dl className="mt-3 grid gap-3 sm:grid-cols-3">
            {suggestion.details.map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-clinical-muted">{label}</dt>
                <dd className="mt-1 text-sm font-semibold text-clinical-primaryDark">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-clinical-muted">Visual prototype only. No dose is calculated or saved.</p>
        </div>
      ) : null}
    </section>
  );
}
