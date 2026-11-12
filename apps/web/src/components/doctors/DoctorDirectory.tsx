import { useState } from 'react';
import { Award, BookOpen, GraduationCap, Search, Star, Stethoscope } from 'lucide-react';
import type { Account, DoctorRating } from '../../types';
import { rankingScore, ratingSummary } from '../../utils/doctorRanking';
import { Avatar } from '../ui/Avatar';

type Sort = 'rank' | 'rating' | 'experience';

export function DoctorDirectory({ doctors, ratings, selectedId, onSelect, selectLabel = 'Choose this doctor', selectedLabel = 'Selected doctor', disabled = false }: {
  doctors: Account[];
  ratings: DoctorRating[];
  selectedId?: string;
  onSelect?: (id: string) => void;
  selectLabel?: string;
  selectedLabel?: string;
  disabled?: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<Sort>('rank');
  const ordered = doctors.filter((doctor) => `${doctor.doctorProfile?.fullName} ${doctor.doctorProfile?.specialty}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => {
    const years = (doctor: Account) => Number(doctor.doctorProfile?.yearsExperience) || 0;
    const rating = (doctor: Account) => ratingSummary(doctor.id, ratings).average ?? -1;
    const difference = sort === 'experience' ? years(b) - years(a) : sort === 'rating' ? rating(b) - rating(a) : rankingScore(b, ratings) - rankingScore(a, ratings);
    return difference || (a.doctorProfile?.fullName || '').localeCompare(b.doctorProfile?.fullName || '');
  });

  return <div>
    <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_180px]">
      <label className="relative"><span className="sr-only">Search doctors</span><Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-clinical-muted" size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search doctors or specialty" className="focus-ring w-full rounded-md border border-clinical-border py-2 pl-9 pr-3 text-sm" /></label>
      <label><span className="sr-only">Sort doctors</span><select value={sort} onChange={(event) => setSort(event.target.value as Sort)} className="focus-ring w-full rounded-md border border-clinical-border bg-white px-3 py-2 text-sm"><option value="rank">Overall ranking</option><option value="rating">Highest rating</option><option value="experience">Most experience</option></select></label>
    </div>
    {sort === 'rank' ? <p className="mb-3 text-xs text-clinical-muted">Overall order uses 70% patient rating and 30% experience (up to 20 years). Sample ratings are labeled.</p> : null}
    <div className="space-y-3">
      {ordered.map((doctor, index) => {
        const profile = doctor.doctorProfile!;
        const expanded = openId === doctor.id;
        const summary = ratingSummary(doctor.id, ratings);
        return <article key={doctor.id} className={`rounded-md border p-4 ${selectedId === doctor.id ? 'border-clinical-primary bg-emerald-50' : 'border-clinical-border bg-white'}`}>
          <div className="flex items-start gap-3">
            {profile.photo ? <img src={profile.photo} alt="" className="h-11 w-11 shrink-0 rounded-md object-cover" /> : <Avatar label={profile.fullName.split(' ').map((part) => part[0]).slice(-2).join('')} />}
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="text-xs font-bold text-clinical-primaryDark">#{index + 1}</span><h3 className="font-semibold">{profile.fullName}</h3></div><p className="text-sm text-clinical-muted">{profile.specialty}</p><div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs"><span className="inline-flex items-center gap-1 font-semibold text-amber-700"><Star size={15} fill={summary.average === null ? 'none' : 'currentColor'} />{summary.average === null ? 'Not rated' : `${summary.average.toFixed(1)} / 5`}</span><span className="text-clinical-muted">{profile.yearsExperience || '0'} years experience</span>{summary.count ? <span className="text-clinical-muted">{summary.count} {summary.sample ? 'sample' : 'patient'} rating{summary.count === 1 ? '' : 's'}</span> : null}</div></div>
            <button type="button" onClick={() => setOpenId(expanded ? null : doctor.id)} className="focus-ring shrink-0 text-sm font-semibold text-clinical-primary">{expanded ? 'Less' : 'Profile'}</button>
          </div>
          {expanded ? <div className="mt-4 space-y-3 border-t border-clinical-border pt-4 text-sm">
            {profile.bio ? <p>{profile.bio}</p> : null}
            <p className="flex gap-2"><GraduationCap size={17} className="shrink-0 text-clinical-primary" /> {profile.medicalSchool || 'Medical school not added'}</p>
            <p className="flex gap-2"><Stethoscope size={17} className="shrink-0 text-clinical-primary" /> {profile.qualifications || 'Qualifications not added'}</p>
            <div className="flex gap-2"><Award size={17} className="shrink-0 text-clinical-primary" /><span>{profile.certificates.length ? profile.certificates.join(', ') : 'No certificates added'}</span></div>
            <div className="flex gap-2"><BookOpen size={17} className="shrink-0 text-clinical-primary" /><span>{profile.papers.length ? profile.papers.join(', ') : 'No papers added'}</span></div>
            {(profile.documents ?? []).map((document) => <a key={document.id} href={document.dataUrl} target="_blank" rel="noreferrer" className="block font-semibold text-clinical-primary">{document.kind === 'certificate' ? 'Certificate' : 'Paper'}: {document.name}</a>)}
          </div> : null}
          {onSelect ? <button type="button" disabled={disabled || selectedId === doctor.id && selectedLabel !== 'Retry request to this doctor'} onClick={() => onSelect(doctor.id)} className={`focus-ring mt-4 w-full rounded-md px-3 py-2 text-sm font-semibold disabled:opacity-50 ${selectedId === doctor.id ? 'bg-clinical-primary text-white' : 'border border-clinical-border text-clinical-primary'}`}>{selectedId === doctor.id ? selectedLabel : selectLabel}</button> : null}
        </article>;
      })}
      {ordered.length === 0 ? <p className="rounded-md border border-clinical-border p-4 text-sm text-clinical-muted">No doctors match this search.</p> : null}
    </div>
  </div>;
}
