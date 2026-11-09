import type { PatientStatus, Trend } from '../types';

export const statusClass = (status: PatientStatus | string) => {
  if (status === 'High' || status === 'Low' || status === 'Needs Review') return 'border-red-200 bg-red-50 text-red-700';
  if (status === 'Above Range') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (status === 'Active' || status === 'Connected' || status === 'In Range') return 'border-green-200 bg-green-50 text-green-700';
  if (status === 'Intermittent' || status === 'Away') return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-slate-200 bg-slate-50 text-slate-700';
};

export const glucoseClass = (value: number) => {
  if (value < 70 || value > 240) return 'text-clinical-critical';
  if (value > 180) return 'text-clinical-warning';
  return 'text-clinical-cgm';
};

export const trendTone = (trend: Trend) => {
  if (trend.includes('rising')) return 'text-clinical-warning';
  if (trend.includes('falling')) return 'text-clinical-critical';
  return 'text-clinical-success';
};
