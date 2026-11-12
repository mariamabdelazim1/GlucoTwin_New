import { AlertTriangle, Check, MessageSquare, Siren, Syringe, UserPlus, Utensils, Users, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/ui/PageHeader';
import { StatCard } from '../components/ui/StatCard';
import { PatientTable } from '../components/patients/PatientTable';
import { Avatar } from '../components/ui/Avatar';
import type { BolusEntry, FoodEntry, Message, Patient } from '../types';
import { chronologicalMessages } from '../utils/messages';

export function Dashboard({ doctorId, doctorName, patientRecords, foodEntries, bolusEntries, messages, acceptedPatientSlugs, patientRequests, assignmentActions, onAcceptPatient, onDeclinePatient }: { doctorId: string; doctorName: string; patientRecords: Patient[]; foodEntries: FoodEntry[]; bolusEntries: BolusEntry[]; messages: Message[]; acceptedPatientSlugs: string[]; patientRequests: string[]; assignmentActions: Record<string, { state: 'pending' | 'success' | 'error'; message: string }>; onAcceptPatient: (slug: string) => Promise<void>; onDeclinePatient: (slug: string) => Promise<void> }) {
  const assigned = patientRecords.filter((patient) => acceptedPatientSlugs.includes(patient.slug));
  const unstable = assigned.filter((patient) => patient.status !== 'In Range' || patient.trend === 'Rapidly rising' || patient.trend === 'Rapidly falling');
  const requests = patientRecords.filter((patient) => patientRequests.includes(patient.slug));
  const patientMessages = messages.filter((message) => message.from === 'patient' && (message.doctorId || 'DR-001') === doctorId && acceptedPatientSlugs.includes(message.patientSlug));
  const recentFood = foodEntries.filter((entry) => acceptedPatientSlugs.includes(entry.patientSlug)).slice(0, 3);
  const recentBolus = bolusEntries.filter((entry) => acceptedPatientSlugs.includes(entry.patientSlug)).slice(0, 3);
  const glucoseAlerts = assigned.filter((patient) => patient.usesCgm && ['High', 'Low', 'Above Range'].includes(patient.status));
  return (
    <>
      <PageHeader title={`Welcome, ${doctorName}`} subtitle="Here is an overview of your patients today." />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Assigned Patients" value={String(assigned.length)} icon={Users} />
        <StatCard label="Unstable Patients" value={String(unstable.length)} icon={AlertTriangle} />
        <StatCard label="Unread Messages" value={String(patientMessages.filter((message) => message.unread).length)} icon={MessageSquare} />
        <StatCard label="CGM Alerts Today" value={String(glucoseAlerts.length)} icon={Siren} />
      </div>
      <section className="surface mt-6 p-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold"><UserPlus size={19} /> New Patient Requests <span className="text-sm text-clinical-muted">({requests.length})</span></h2>
        {Object.entries(assignmentActions).filter(([key]) => key.startsWith(`${doctorId}:`)).map(([key, action]) => <p key={key} role={action.state === 'error' ? 'alert' : 'status'} className={`mt-3 rounded-md border p-3 text-sm ${action.state === 'error' ? 'border-red-200 bg-red-50 text-red-700' : action.state === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>{action.message}</p>)}
        <div className="mt-4 space-y-3">
          {requests.length === 0 ? <p className="text-sm text-clinical-muted">No pending requests.</p> : requests.map((patient) => (
            <div key={patient.slug} className="flex flex-wrap items-center justify-between gap-3 border-b border-clinical-border pb-3 last:border-0 last:pb-0">
              <div><strong>{patient.name}</strong><p className="text-sm text-clinical-muted">{patient.age} years · {patient.diabetesType}</p></div>
              <div className="flex gap-2">
                <button disabled={assignmentActions[`${doctorId}:${patient.slug}`]?.state === 'pending'} onClick={() => void onDeclinePatient(patient.slug)} className="focus-ring inline-flex items-center gap-1 rounded-md border border-clinical-border px-3 py-2 text-sm font-semibold disabled:opacity-50"><X size={16} /> Decline</button>
                <button disabled={assignmentActions[`${doctorId}:${patient.slug}`]?.state === 'pending'} onClick={() => void onAcceptPatient(patient.slug)} className="focus-ring inline-flex items-center gap-1 rounded-md bg-clinical-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"><Check size={16} /> Accept</button>
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="surface mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-clinical-border p-4"><h2 className="text-lg font-semibold">Unstable Patients</h2><Link to="/patients" className="text-sm font-semibold text-clinical-primary">View all patients</Link></div>
        <PatientTable patients={unstable} compact />
      </section>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_380px]">
        <section className="surface p-4">
          <h2 className="text-lg font-semibold">Recent Messages</h2>
          <div className="mt-4 space-y-3">
            {chronologicalMessages(patientMessages).reverse().slice(0, 3).map((message) => (
              <Link to={`/messages?patient=${message.patientSlug}`} key={message.id} className="focus-ring flex gap-3 rounded-lg border border-clinical-border p-3 hover:bg-emerald-50">
                <Avatar label={message.avatar} />
                <span className="min-w-0 flex-1"><strong className="text-sm">{message.patient}</strong><span className="ml-2 text-xs text-clinical-muted">{message.time}</span><p className="truncate text-sm text-clinical-muted">{message.text}</p></span>
                {message.unread ? <span className="h-2 w-2 rounded-full bg-clinical-primary" aria-label="Unread" /> : null}
              </Link>
            ))}
          </div>
        </section>
        <section className="surface p-4">
          <h2 className="text-lg font-semibold">Glucose Alerts</h2>
          <div className="mt-4 space-y-3 text-sm">
            {glucoseAlerts.length ? glucoseAlerts.map((patient) => <div key={patient.slug} className="rounded-lg border border-red-200 bg-red-50 p-3"><strong>{patient.name}</strong> - {patient.currentGlucose} mg/dL ({patient.status})</div>) : <p className="text-clinical-muted">No glucose alerts.</p>}
          </div>
        </section>
      </div>
      <section className="surface mt-6 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Latest Patient Logs</h2>
          {assigned[0] ? <Link to={`/patients/${assigned[0].slug}`} className="focus-ring rounded-md text-sm font-semibold text-clinical-primary">Open patient detail</Link> : null}
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-clinical-border p-4">
            <h3 className="flex items-center gap-2 font-semibold"><Utensils size={18} /> Food entered manually</h3>
            <div className="mt-3 space-y-2">
              {recentFood.map((entry) => (
                <div key={entry.id} className="rounded-md bg-clinical-bg p-3 text-sm">
                  <strong>{entry.patient}</strong> logged {entry.meal.toLowerCase()} at {entry.time}
                  <p className="mt-1 text-clinical-muted">{entry.items} · {entry.carbs} carbs</p>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-clinical-border p-4">
            <h3 className="flex items-center gap-2 font-semibold"><Syringe size={18} /> Manual bolus logs</h3>
            <div className="mt-3 space-y-2">
              {recentBolus.map((entry) => (
                <div key={entry.id} className="rounded-md bg-clinical-bg p-3 text-sm">
                  <strong>{entry.patient}</strong> recorded {entry.recorded} at {entry.time}
                  <p className="mt-1 text-clinical-muted">{entry.meal} · Carbs: {entry.carbs || 'Not provided'}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
