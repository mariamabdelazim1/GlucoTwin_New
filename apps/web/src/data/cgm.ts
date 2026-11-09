import type { BolusEntry, CgmReading, FoodEntry, ForecastPoint } from '../types';
import demoPatient from './demoPatient.json';

export const cgmReadings: CgmReading[] = demoPatient.cgm;

export const digitalTwinForecast: ForecastPoint[] = demoPatient.forecast;

export const forecastSnapshots = demoPatient.forecastSnapshots;

export const foodLog: FoodEntry[] = [
  { id: 'f1', patientSlug: 'omar-hassan', patient: 'Omar Hassan', time: '08:05', meal: 'Breakfast', items: 'Greek yogurt, oats, berries', carbs: '54g', impact: '+32 mg/dL', status: 'Reviewed' },
  { id: 'f2', patientSlug: 'omar-hassan', patient: 'Omar Hassan', time: '13:12', meal: 'Lunch', items: 'Chicken rice bowl, apple', carbs: '62g', impact: '+48 mg/dL', status: 'Needs review' },
  { id: 'f3', patientSlug: 'omar-hassan', patient: 'Omar Hassan', time: '16:20', meal: 'Snack', items: 'Protein bar', carbs: '18g', impact: '+12 mg/dL', status: 'Reviewed' },
  { id: 'f4', patientSlug: 'omar-hassan', patient: 'Omar Hassan', time: '19:30', meal: 'Dinner', items: 'Grilled fish, potatoes, salad', carbs: '71g', impact: '+39 mg/dL', status: 'Recorded' },
];

export const basalSchedule = [
  { period: '00:00 - 06:00', current: '0.8 U/hr', suggested: '0.75 U/hr' },
  { period: '06:00 - 12:00', current: '0.9 U/hr', suggested: '0.9 U/hr' },
  { period: '12:00 - 18:00', current: '0.85 U/hr', suggested: '0.8 U/hr' },
  { period: '18:00 - 00:00', current: '0.95 U/hr', suggested: '0.9 U/hr' },
];

export const bolusHistory: BolusEntry[] = [
  { id: 'b1', patientSlug: 'omar-hassan', patient: 'Omar Hassan', time: '08:05', meal: 'Breakfast', carbs: '54g', preMeal: '136 mg/dL', recommended: '5.5 U', recorded: '6 U' },
  { id: 'b2', patientSlug: 'omar-hassan', patient: 'Omar Hassan', time: '13:12', meal: 'Lunch', carbs: '62g', preMeal: '184 mg/dL', recommended: '5.5 U', recorded: '5 U' },
  { id: 'b3', patientSlug: 'omar-hassan', patient: 'Omar Hassan', time: '19:30', meal: 'Dinner', carbs: '71g', preMeal: '169 mg/dL', recommended: '7 U', recorded: '7 U' },
];
