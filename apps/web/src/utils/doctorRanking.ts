import type { Account, DoctorRating } from '../types';

export function ratingSummary(doctorId: string, ratings: DoctorRating[]) {
  const all = ratings.filter((rating) => rating.doctorId === doctorId);
  const patientRatings = all.filter((rating) => rating.source === 'patient');
  const used = patientRatings.length ? patientRatings : all;
  return {
    average: used.length ? used.reduce((sum, rating) => sum + rating.score, 0) / used.length : null,
    count: used.length,
    sample: used.length > 0 && patientRatings.length === 0,
  };
}

export function rankingScore(doctor: Account, ratings: DoctorRating[]) {
  const average = ratingSummary(doctor.id, ratings).average;
  const years = Math.max(0, Math.min(20, Number(doctor.doctorProfile?.yearsExperience) || 0));
  return (average === null ? 0 : (average / 5) * 0.7) + (years / 20) * 0.3;
}
