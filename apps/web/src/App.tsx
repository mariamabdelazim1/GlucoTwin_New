import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, ReactNode, SetStateAction } from 'react';
import type { Account, BolusEntry, CareAssignment, DoctorRating, FoodEntry, Message, Patient, PatientProfile, Role } from './types';
import { AppSidebar } from './components/layout/AppSidebar';
import { TopHeader } from './components/layout/TopHeader';
import { Login } from './pages/Login';
import { Landing } from './pages/Landing';
import { DoctorProfile } from './pages/DoctorProfile';
import { Doctors } from './pages/Doctors';
import { PatientDashboard } from './pages/PatientDashboard';
import { MobilePreview } from './pages/MobilePreview';
import { Dashboard } from './pages/Dashboard';
import { Patients } from './pages/Patients';
import { PatientDetails } from './pages/PatientDetails';
import { Messages } from './pages/Messages';
import { Notifications } from './pages/Notifications';
import { AdminDashboard } from './pages/admin/AdminDashboard';
import { AdminDoctors } from './pages/admin/AdminDoctors';
import { AdminPatients } from './pages/admin/AdminPatients';
import { AdminAssignments } from './pages/admin/AdminAssignments';
import { seedAccounts, seedAssignments, patientRecord } from './data/accounts';
import { seedDoctorRatings } from './data/doctorRatings';
import { patients } from './data/patients';
import { initialMessages } from './data/messages';
import { bolusHistory, foodLog } from './data/cgm';
import { useStoredState } from './utils/storage';
import { bridgeAccount, getSnapshot, loginAccount, mergeById, syncAssignment, syncItem, syncRating } from './utils/sync';
import type { GlucoseEntry } from './utils/sync';

type Session = { id: string; role: Role };

function RoleOnly({ role, allowed, children }: { role: Role; allowed: Role[]; children: ReactNode }) {
  const fallback = role === 'patient' ? '/patient/dashboard' : role === 'admin' ? '/admin' : '/dashboard';
  return allowed.includes(role) ? <>{children}</> : <Navigate to={fallback} replace />;
}

function Shell({ session, account, accounts, assignments, ratings, setRatings, allPatients, patientProfiles, messages, setMessages, foodEntries, setFoodEntries, bolusEntries, setBolusEntries, glucoseEntries, setGlucoseEntries, syncError, setAssignments, onUpdateAccount, onSignOut }: {
  session: Session;
  account?: Account;
  accounts: Account[];
  assignments: CareAssignment[];
  ratings: DoctorRating[];
  setRatings: Dispatch<SetStateAction<DoctorRating[]>>;
  allPatients: Patient[];
  patientProfiles: Record<string, PatientProfile>;
  messages: Message[];
  setMessages: Dispatch<SetStateAction<Message[]>>;
  foodEntries: FoodEntry[];
  setFoodEntries: Dispatch<SetStateAction<FoodEntry[]>>;
  bolusEntries: BolusEntry[];
  setBolusEntries: Dispatch<SetStateAction<BolusEntry[]>>;
  glucoseEntries: GlucoseEntry[];
  setGlucoseEntries: Dispatch<SetStateAction<GlucoseEntry[]>>;
  syncError: string | null;
  setAssignments: Dispatch<SetStateAction<CareAssignment[]>>;
  onUpdateAccount: (account: Account) => void;
  onSignOut: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const role = session.role;
  const title = useMemo(() => {
    const part = location.pathname.split('/').filter(Boolean).join(' / ');
    return part ? `Clinical portal / ${part}` : 'Clinical portal';
  }, [location.pathname]);
  const acceptedPatientSlugs = assignments.filter((item) => item.doctorId === session.id && item.status === 'accepted').map((item) => item.patientId);
  const patientRequests = assignments.filter((item) => item.doctorId === session.id && item.status === 'pending').map((item) => item.patientId);
  const currentPatient = account?.role === 'patient' ? patientRecord(account.id, account.patientProfile) : undefined;
  const currentAssignment = assignments.find((item) => item.patientId === account?.id && item.doctorId === account?.patientProfile?.selectedDoctorId);
  const selectedDoctor = accounts.find((item) => item.id === account?.patientProfile?.selectedDoctorId);
  const doctorName = selectedDoctor?.doctorProfile?.fullName || 'your doctor';
  const changeAssignment = (patientId: string, status: CareAssignment['status']) => {
    setAssignments((current) => current.map((item) => item.patientId === patientId && item.doctorId === session.id ? { ...item, status } : item));
    if (status !== 'pending') void syncAssignment(patientId, status).catch(console.error);
  };

  return <div className="min-h-screen bg-clinical-bg text-clinical-text lg:flex">
    <AppSidebar role={role} account={account} collapsed={collapsed} mobileOpen={mobileOpen} onSignOut={onSignOut} onToggle={() => { setMobileOpen((open) => !open); setCollapsed((value) => !value); }} onMobileClose={() => setMobileOpen(false)} />
    <div className="min-w-0 flex-1">
      <TopHeader title={title} role={role} account={account} />
      <main className="mx-auto max-w-[1500px] px-4 py-6 md:px-6">{syncError && role !== 'admin' ? <div role="alert" className="mb-5 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{syncError}</div> : null}<Routes>
        <Route path="/dashboard" element={<RoleOnly role={role} allowed={['doctor']}><Dashboard doctorId={session.id} doctorName={account?.doctorProfile?.fullName || 'Doctor'} patientRecords={allPatients} foodEntries={foodEntries} bolusEntries={bolusEntries} messages={messages} acceptedPatientSlugs={acceptedPatientSlugs} patientRequests={patientRequests} onAcceptPatient={(id) => changeAssignment(id, 'accepted')} onDeclinePatient={(id) => changeAssignment(id, 'declined')} /></RoleOnly>} />
        <Route path="/patient/dashboard" element={<RoleOnly role={role} allowed={['patient']}>{currentPatient && account?.patientProfile ? <PatientDashboard patient={currentPatient} doctorName={doctorName} assignmentStatus={currentAssignment?.status || 'pending'} setMessages={setMessages} foodEntries={foodEntries} setFoodEntries={setFoodEntries} bolusEntries={bolusEntries} setBolusEntries={setBolusEntries} glucoseEntries={glucoseEntries} setGlucoseEntries={setGlucoseEntries} patientProfile={account.patientProfile} /> : null}</RoleOnly>} />
        <Route path="/patient/food" element={<RoleOnly role={role} allowed={['patient']}>{currentPatient && account?.patientProfile ? <PatientDashboard focusFood patient={currentPatient} doctorName={doctorName} assignmentStatus={currentAssignment?.status || 'pending'} setMessages={setMessages} foodEntries={foodEntries} setFoodEntries={setFoodEntries} bolusEntries={bolusEntries} setBolusEntries={setBolusEntries} glucoseEntries={glucoseEntries} setGlucoseEntries={setGlucoseEntries} patientProfile={account.patientProfile} /> : null}</RoleOnly>} />
        <Route path="/patient/doctors" element={<RoleOnly role={role} allowed={['patient']}><Doctors accounts={accounts} ratings={ratings} patientAccount={account} assignmentStatus={currentAssignment?.status} onChoose={(doctorId) => { if (account?.patientProfile && doctorId !== account.patientProfile.selectedDoctorId) onUpdateAccount({ ...account, patientProfile: { ...account.patientProfile, selectedDoctorId: doctorId } }); }} onRate={(score) => {
          if (!account?.patientProfile) return;
          const patientId = account.id;
          const doctorId = account.patientProfile.selectedDoctorId;
          setRatings((current) => [...current.filter((rating) => !(rating.patientId === patientId && rating.doctorId === doctorId && rating.source === 'patient')), { id: crypto.randomUUID(), doctorId, patientId, score, source: 'patient' }]);
          void syncRating(doctorId, score).then(({ ratings: remote }) => setRatings(remote)).catch(console.error);
        }} /></RoleOnly>} />
        <Route path="/patients" element={<RoleOnly role={role} allowed={['doctor']}><Patients acceptedPatientSlugs={acceptedPatientSlugs} patientRecords={allPatients} /></RoleOnly>} />
        <Route path="/patients/:slug" element={<RoleOnly role={role} allowed={['doctor']}><PatientDetails foodEntries={foodEntries} bolusEntries={bolusEntries} glucoseEntries={glucoseEntries} acceptedPatientSlugs={acceptedPatientSlugs} patientRecords={allPatients} patientProfiles={patientProfiles} /></RoleOnly>} />
        <Route path="/messages" element={<RoleOnly role={role} allowed={['doctor', 'patient']}><Messages role={role} doctorId={role === 'doctor' ? session.id : account?.patientProfile?.selectedDoctorId || ''} currentPatient={currentPatient} doctorName={doctorName} patientRecords={allPatients} messages={messages} setMessages={setMessages} acceptedPatientSlugs={acceptedPatientSlugs} assignmentStatus={currentAssignment?.status} /></RoleOnly>} />
        <Route path="/notifications" element={<RoleOnly role={role} allowed={['doctor', 'patient']}><Notifications role={role} patientId={currentPatient?.slug} doctorId={session.id} visiblePatientIds={[...acceptedPatientSlugs, ...patientRequests]} /></RoleOnly>} />
        <Route path="/admin" element={<RoleOnly role={role} allowed={['admin']}><AdminDashboard accounts={accounts} assignments={assignments} patientRecords={allPatients} /></RoleOnly>} />
        <Route path="/admin/doctors" element={<RoleOnly role={role} allowed={['admin']}><AdminDoctors accounts={accounts} /></RoleOnly>} />
        <Route path="/admin/patients" element={<RoleOnly role={role} allowed={['admin']}><AdminPatients accounts={accounts} assignments={assignments} patientRecords={allPatients} /></RoleOnly>} />
        <Route path="/admin/assignments" element={<RoleOnly role={role} allowed={['admin']}><AdminAssignments accounts={accounts} assignments={assignments} patientRecords={allPatients} /></RoleOnly>} />
        <Route path="/admin/settings" element={<RoleOnly role={role} allowed={['admin']}><AdminDashboard accounts={accounts} assignments={assignments} patientRecords={allPatients} /></RoleOnly>} />
        <Route path="/profile" element={<RoleOnly role={role} allowed={['doctor', 'patient']}>{account ? <DoctorProfile account={account} accounts={accounts} ratings={ratings} onSave={onUpdateAccount} /> : null}</RoleOnly>} />
        <Route path="*" element={<Navigate to={role === 'patient' ? '/patient/dashboard' : role === 'admin' ? '/admin' : '/dashboard'} replace />} />
      </Routes></main>
    </div>
  </div>;
}

export default function App() {
  const [accounts, setAccounts] = useStoredState('ddt.accounts.v1', seedAccounts);
  const [ratings, setRatings] = useStoredState('ddt.doctorRatings.v1', seedDoctorRatings);
  const [assignments, setAssignments] = useStoredState('ddt.assignments.v1', seedAssignments);
  const [messages, setMessages] = useStoredState('ddt.messages.v1', initialMessages);
  const [foodEntries, setFoodEntries] = useStoredState('ddt.food.v1', foodLog);
  const [bolusEntries, setBolusEntries] = useStoredState('ddt.bolus.v1', bolusHistory);
  const [glucoseEntries, setGlucoseEntries] = useStoredState<GlucoseEntry[]>('ddt.glucose.v1', []);
  const [syncError, setSyncError] = useState<string | null>(null);
  const sent = useRef({ food: new Set<string>(), bolus: new Set<string>(), glucose: new Set<string>(), messages: new Set<string>() });
  const [session, setSession] = useState<Session | null>(() => {
    try { return JSON.parse(sessionStorage.getItem('ddt.session.v1') || 'null') as Session | null; } catch { return null; }
  });
  const account = accounts.find((item) => item.id === session?.id);
  useEffect(() => { if (session) sessionStorage.setItem('ddt.session.v1', JSON.stringify(session)); else sessionStorage.removeItem('ddt.session.v1'); }, [session]);
  useEffect(() => {
    if (!session || session.role === 'admin' || !sessionStorage.getItem('ddt.sync.token')) return;
    let active = true;
    const refresh = async () => {
      try {
        const snapshot = await getSnapshot();
        if (!active) return;
        const remoteAccounts = [...snapshot.doctors, ...snapshot.patients];
        setAccounts((current) => {
          let changed = false;
          const result = current.map((local) => {
            const remote = remoteAccounts.find((item) => item.id === local.id);
            if (!remote || JSON.stringify(local.patientProfile) === JSON.stringify(remote.patientProfile) && JSON.stringify(local.doctorProfile) === JSON.stringify(remote.doctorProfile)) return local;
            changed = true;
            return { ...local, ...remote, password: local.password } as Account;
          });
          for (const remote of remoteAccounts) if (!result.some((local) => local.id === remote.id)) {
            result.push({ ...remote, password: '' } as Account);
            changed = true;
          }
          return changed ? result : current;
        });
        setAssignments((current) => {
          const others = current.filter((item) => session.role === 'patient' ? item.patientId !== session.id : item.doctorId !== session.id);
          const next = [...others, ...snapshot.assignments];
          return JSON.stringify(next) === JSON.stringify(current) ? current : next;
        });
        setFoodEntries((current) => mergeById(current, snapshot.food));
        setBolusEntries((current) => mergeById(current, snapshot.bolus));
        setGlucoseEntries((current) => mergeById(current, snapshot.glucose));
        setMessages((current) => mergeById(current, snapshot.messages));
        setRatings(snapshot.ratings);
        setSyncError(null);
      } catch (error) { console.error('Patient sync failed', error); setSyncError('Connection to the care sync service is unavailable. New entries may not yet be visible to your doctor or mobile app.'); }
    };
    void refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => { active = false; window.clearInterval(timer); };
  }, [session, setAccounts, setAssignments, setFoodEntries, setBolusEntries, setGlucoseEntries, setMessages, setRatings]);
  useEffect(() => {
    if (!session || session.role === 'admin' || !sessionStorage.getItem('ddt.sync.token')) return;
    const upload = <T extends { id: string; patientSlug: string }>(kind: 'food' | 'bolus' | 'glucose' | 'messages', entries: T[]) => {
      for (const item of entries) {
        if (sent.current[kind].has(item.id)) continue;
        if (['f1', 'f2', 'f3', 'f4', 'b1', 'b2', 'b3', 'm1', 'm2', 'm3', 'm4', 'm5'].includes(item.id)) continue;
        if (session.role === 'patient' && item.patientSlug !== session.id) continue;
        if (kind === 'messages' && (!('from' in item) || item.from !== session.role)) continue;
        if (kind === 'messages' && 'doctorId' in item && item.doctorId && item.doctorId !== (session.role === 'doctor' ? session.id : account?.patientProfile?.selectedDoctorId)) continue;
        if (session.role === 'doctor' && kind !== 'messages') continue;
        sent.current[kind].add(item.id);
        void syncItem(kind, item).catch((error) => {
          sent.current[kind].delete(item.id);
          setSyncError('An entry is waiting to sync. It may not yet be visible to your doctor or mobile app.');
          console.error('Patient sync upload failed', error);
        });
      }
    };
    const uploadAll = () => {
      upload('food', foodEntries);
      upload('bolus', bolusEntries);
      upload('glucose', glucoseEntries);
      upload('messages', messages);
    };
    uploadAll();
    const timer = window.setInterval(uploadAll, 4000);
    return () => window.clearInterval(timer);
  }, [session, account?.patientProfile?.selectedDoctorId, foodEntries, bolusEntries, glucoseEntries, messages]);
  useEffect(() => {
    setAccounts((current) => {
      const missing = seedAccounts.filter((seed) => seed.role === 'doctor' && !current.some((account) => account.id === seed.id));
      return missing.length ? [...current, ...missing] : current;
    });
  }, [setAccounts]);
  useEffect(() => {
    const refreshDoctors = async () => {
      try {
        const response = await fetch('/api/doctors');
        if (!response.ok) return;
        let result = await response.json() as { doctors: Omit<Account, 'password'>[]; ratings: DoctorRating[] };
        const remoteIds = new Set(result.doctors.map((doctor) => doctor.id));
        const localDoctors = accounts.filter((item) => item.role === 'doctor' && item.password && !remoteIds.has(item.id));
        for (const doctor of localDoctors) {
          const migrated = await fetch('/api/auth/bridge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account: doctor }) });
          if (!migrated.ok) console.warn(`Could not sync doctor profile ${doctor.id}`);
        }
        if (localDoctors.length) {
          const updated = await fetch('/api/doctors');
          if (updated.ok) result = await updated.json() as { doctors: Omit<Account, 'password'>[]; ratings: DoctorRating[] };
        }
        setRatings(result.ratings);
        setAccounts((current) => {
          const ids = new Set(current.map((item) => item.id));
          const missing = result.doctors.filter((item) => !ids.has(item.id)).map((item) => ({ ...item, password: '' } as Account));
          return missing.length ? [...current, ...missing] : current;
        });
      } catch { /* The public directory can still show locally available doctors. */ }
    };
    void refreshDoctors();
  }, [accounts, setAccounts, setRatings]);
  useEffect(() => {
    if (messages.some((message) => !message.doctorId)) {
      setMessages((current) => current.map((message) => message.doctorId ? message : { ...message, doctorId: accounts.find((item) => item.id === message.patientSlug)?.patientProfile?.selectedDoctorId || 'DR-001' }));
    }
  }, [accounts, messages, setMessages]);
  const allPatients = [
    ...patients.map((patient) => { const matching = accounts.find((item) => item.id === patient.slug && item.role === 'patient'); return matching ? patientRecord(matching.id, matching.patientProfile) : patient; }),
    ...accounts.filter((item) => item.role === 'patient' && !patients.some((patient) => patient.slug === item.id)).map((item) => patientRecord(item.id, item.patientProfile)),
  ];
  const patientProfiles = Object.fromEntries(accounts.filter((item) => item.patientProfile).map((item) => [item.id, item.patientProfile!])) as Record<string, PatientProfile>;
  const visibleMessages = messages.filter((message) => !['m1', 'm2'].includes(message.id)).map((message) => message.doctorId ? message : { ...message, doctorId: patientProfiles[message.patientSlug]?.selectedDoctorId || 'DR-001' });
  const visibleFood = foodEntries;
  const visibleBolus = bolusEntries;
  const home = session?.role === 'patient' ? '/patient/dashboard' : session?.role === 'admin' ? '/admin' : '/dashboard';
  const signIn = async (identifier: string, password: string, mode: 'doctor' | 'patient') => {
    if (identifier.toLowerCase() === 'admin') {
      if (password !== 'admin123') return 'Incorrect email or password.';
      setSession({ id: 'admin', role: 'admin' });
      return null;
    }
    const found = accounts.find((item) => item.email.toLowerCase() === identifier.toLowerCase() && item.role === mode && item.password === password);
    if (found) {
      try { await bridgeAccount(found); } catch { return 'Sync service is unavailable. Start it with npm run sync.'; }
      setSession({ id: found.id, role: found.role });
      return null;
    }
    try {
      const remote = await loginAccount(identifier, password, mode);
      setAccounts((current) => current.some((item) => item.id === remote.id) ? current.map((item) => item.id === remote.id ? { ...remote, password } as Account : item) : [...current, { ...remote, password } as Account]);
      setSession({ id: remote.id, role: mode });
    } catch { return 'Incorrect email or password, or sync service unavailable.'; }
    return null;
  };
  const register = async (newAccount: Account) => {
    if (newAccount.email.toLowerCase() === 'admin' || accounts.some((item) => item.email.toLowerCase() === newAccount.email.toLowerCase())) return 'An account with this email already exists.';
    try { await bridgeAccount(newAccount); } catch { return 'Sync service is unavailable. Start it with npm run sync.'; }
    setAccounts((current) => [...current, newAccount]);
    if (newAccount.patientProfile) setAssignments((current) => [...current, { patientId: newAccount.id, doctorId: newAccount.patientProfile!.selectedDoctorId, status: 'pending' }]);
    setSession({ id: newAccount.id, role: newAccount.role });
    return null;
  };
  const loginProps = { accounts, ratings, onSignIn: signIn, onRegister: register };
  return <Routes>
    <Route path="/" element={session ? <Navigate to={home} replace /> : <Landing />} />
    <Route path="/doctors" element={session?.role === 'patient' ? <Navigate to="/patient/doctors" replace /> : <Doctors publicView accounts={accounts} ratings={ratings} />} />
    <Route path="/mobile-preview" element={session?.role === 'doctor' || session?.role === 'admin' ? <Navigate to={home} replace /> : <MobilePreview existingPatient={account?.role === 'patient' ? account : undefined} />} />
    <Route path="/login" element={session ? <Navigate to={home} replace /> : <Login {...loginProps} />} />
    <Route path="/login/doctor" element={session ? <Navigate to={home} replace /> : <Login mode="doctor" {...loginProps} />} />
    <Route path="/login/patient" element={session ? <Navigate to={home} replace /> : <Login mode="patient" {...loginProps} />} />
    <Route path="/login/admin" element={<Navigate to="/login" replace />} />
    <Route path="/*" element={session && (session.role === 'admin' || account) ? <Shell session={session} account={account} accounts={accounts} assignments={assignments} ratings={ratings} setRatings={setRatings} allPatients={allPatients} patientProfiles={patientProfiles} messages={visibleMessages} setMessages={setMessages} foodEntries={visibleFood} setFoodEntries={setFoodEntries} bolusEntries={visibleBolus} setBolusEntries={setBolusEntries} glucoseEntries={glucoseEntries} setGlucoseEntries={setGlucoseEntries} syncError={syncError} setAssignments={setAssignments} onUpdateAccount={(updated) => {
      if (updated.patientProfile && updated.patientProfile.selectedDoctorId !== account?.patientProfile?.selectedDoctorId) {
        setAssignments((current) => [...current.filter((item) => item.patientId !== updated.id), { patientId: updated.id, doctorId: updated.patientProfile!.selectedDoctorId, status: 'pending' }]);
      }
      setAccounts((current) => current.map((item) => item.id === updated.id ? updated : item));
      void bridgeAccount(updated).catch(console.error);
    }} onSignOut={() => { sessionStorage.removeItem('ddt.sync.token'); setSession(null); }} /> : <Navigate to="/login" replace />} />
  </Routes>;
}
