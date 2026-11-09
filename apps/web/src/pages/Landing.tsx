import { Link } from 'react-router-dom';
import { Activity, Bell, HeartPulse, LineChart, LockKeyhole, ShieldCheck, Stethoscope, Users } from 'lucide-react';
import heroImage from '../assets/clinical-hero.png';

export function Landing() {
  return (
    <main className="min-h-screen bg-clinical-bg text-clinical-text">
      <section className="relative min-h-[92vh] overflow-hidden">
        <img src={heroImage} alt="Clinical workstation showing glucose monitoring dashboards" className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-r from-emerald-950/86 via-emerald-950/50 to-white/5" />
        <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-5 py-5 md:px-8">
          <Link to="/" className="focus-ring inline-flex items-center gap-3 rounded-md text-white">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-white/14 backdrop-blur"><Activity size={21} /></span>
            <span className="font-bold">Diabetes Digital Twin</span>
          </Link>
          <nav className="flex items-center gap-2">
            <Link to="/login" className="focus-ring rounded-md border border-white/35 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10">Sign in</Link>
            <Link to="/login/patient?action=register" className="focus-ring rounded-md bg-white px-4 py-2 text-sm font-semibold text-clinical-primaryDark hover:bg-emerald-50">Create account</Link>
            <Link to="/doctors" className="focus-ring hidden rounded-md border border-white/35 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 sm:inline-flex">Find a Doctor</Link>
          </nav>
        </header>
        <div className="relative z-10 mx-auto flex min-h-[calc(92vh-80px)] max-w-7xl items-center px-5 pb-16 pt-10 md:px-8">
          <div className="max-w-2xl text-white">
            <p className="inline-flex items-center gap-2 rounded-md border border-white/25 bg-white/10 px-3 py-1.5 text-xs font-semibold uppercase backdrop-blur">
              <ShieldCheck size={15} /> Clinical decision-support prototype
            </p>
            <h1 className="mt-5 text-4xl font-bold leading-tight md:text-6xl">Diabetes Digital Twin</h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-emerald-50 md:text-lg">
              A calm clinical workspace for doctors to review CGM readings, glucose trends, simulated digital-twin forecasts, insulin context, and patient messages.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/login/doctor" className="focus-ring inline-flex items-center gap-2 rounded-md bg-clinical-primary px-5 py-3 font-semibold text-white hover:bg-clinical-primaryDark">
                Doctor sign in <Stethoscope size={18} />
              </Link>
              <Link to="/login/patient" className="focus-ring inline-flex items-center gap-2 rounded-md bg-white px-5 py-3 font-semibold text-clinical-primaryDark hover:bg-emerald-50">
                Patient sign in <HeartPulse size={18} />
              </Link>
            </div>
          </div>
        </div>
        <div className="absolute bottom-8 right-5 z-10 hidden w-[360px] rounded-lg border border-white/25 bg-white/92 p-4 shadow-xl backdrop-blur lg:block">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase text-clinical-muted">Live CGM Snapshot</p>
              <p className="mt-1 text-2xl font-bold">142 mg/dL</p>
            </div>
            <LineChart className="text-clinical-cgm" size={28} />
          </div>
          <div className="mt-4 h-24 overflow-hidden rounded-md border border-clinical-border bg-white p-3">
            <div className="landing-wave h-full" aria-hidden="true" />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
            <span className="rounded-md bg-green-50 p-2 font-semibold text-clinical-success">74% TIR</span>
            <span className="rounded-md bg-emerald-50 p-2 font-semibold text-clinical-primaryDark">3 hr forecast</span>
            <span className="rounded-md bg-amber-50 p-2 font-semibold text-clinical-warning">23% high</span>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-12 md:px-8">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            { icon: Users, title: 'Doctor dashboards', text: 'Prioritize patients by CGM alerts, glucose status, and message urgency.' },
            { icon: Activity, title: 'CGM review', text: 'Scan current glucose, 24-hour trends, target ranges, and historical context.' },
            { icon: Stethoscope, title: 'Digital twin forecast', text: 'Preview simulated physiological-model projections as decision support.' },
            { icon: LockKeyhole, title: 'Clinical access', text: 'Separate workspaces for patients, doctors, and administrators.' },
          ].map(({ icon: Icon, title, text }) => (
            <article key={title} className="surface p-5">
              <div className="mb-4 grid h-10 w-10 place-items-center rounded-md bg-clinical-secondary text-clinical-primary">
                <Icon size={20} />
              </div>
              <h2 className="font-semibold">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-clinical-muted">{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-y border-clinical-border bg-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-12 md:px-8 lg:grid-cols-[1fr_420px] lg:items-center">
          <div>
            <h2 className="text-2xl font-bold md:text-3xl">Built for quick clinical scanning</h2>
            <p className="mt-3 max-w-2xl text-clinical-muted">
              The interface keeps data dense but readable: status labels never rely on color alone, charts resize cleanly, and patient details keep clinically relevant values close together.
            </p>
          </div>
          <div className="rounded-lg border border-clinical-border bg-clinical-bg p-4">
            <div className="flex items-center justify-between border-b border-clinical-border pb-3">
              <span className="font-semibold">Patients Needing Attention</span>
              <Bell className="text-clinical-warning" size={18} />
            </div>
            {['Omar Hassan - High', 'Mariam Ali - Low', 'Ahmed Samir - Above Range'].map((row) => (
              <div key={row} className="flex items-center justify-between border-b border-clinical-border py-3 last:border-b-0">
                <span className="text-sm">{row}</span>
                <span className="h-2 w-16 rounded-full bg-clinical-cgm/40"><span className="block h-2 w-10 rounded-full bg-clinical-cgm" /></span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
