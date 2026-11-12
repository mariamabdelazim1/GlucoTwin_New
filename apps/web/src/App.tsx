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
import { bridgeAccount, getSnapshot, loginAccount, mergeById, requestCareDoctor, SyncApiError, syncAssignment, syncItem, syncRating, updateAccountProfile } from './utils/sync';
import type { GlucoseEntry } from './utils/sync';
import { retryDecision } from './utils/syncState';
import { mergePublicDoctors } from './utils/accountState';
import { AssignmentDecisionError, confirmAssignmentDecision } from './utils/assignmentState';

type Session = { id: string; role: Role };
type AssignmentAction = { state: 'pending' | 'success' | 'error'; message: string };
const assignmentKey = (patientId: string, doctorId: string) => `${doctorId}:${patientId}`;

function RoleOnly({ role, allowed, children }: { role: Role; allowed: Role[]; children: ReactNode }) {
  const fallback = role === 'patient' ? '/patient/dashboard' : role === 'admin' ? '/admin' : '/dashboard';
  return allowed.includes(role) ? <>{children}</> : <Navigate to={fallback} replace />;
}

function Shell({ session, account, accounts, assignments, assignmentActions, onAssignmentDecision, onRequestDoctor, ratings, setRatings, allPatients, patientProfiles, messages, setMessages, foodEntries, setFoodEntries, bolusEntries, setBolusEntries, glucoseEntries, setGlucoseEntries, syncError, onUpdateAccount, onSignOut, directoryError }: {
  session: Session;
  account?: Account;
  accounts: Account[];
  assignments: CareAssignment[];
  assignmentActions: Record<string, AssignmentAction>;
  onAssignmentDecision: (patientId: string, status: 'accepted' | 'declined') => Promise<void>;
  onRequestDoctor: (doctorId: string) => Promise<string | null>;
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
  onUpdateAccount: (account: Account) => Promise<string | null>;
  onSignOut: () => void;
  directoryError: string | null;
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

  return <div className="min-h-screen bg-clinical-bg text-clinical-text lg:flex">
    <AppSidebar role={role} account={account} collapsed={collapsed} mobileOpen={mobileOpen} onSignOut={onSignOut} onToggle={() => { setMobileOpen((open) => !open); setCollapsed((value) => !value); }} onMobileClose={() => setMobileOpen(false)} />
    <div className="min-w-0 flex-1">
      <TopHeader title={title} role={role} account={account} />
      <main className="mx-auto max-w-[1500px] px-4 py-6 md:px-6">{syncError && role !== 'admin' ? <div role="alert" className="mb-5 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{syncError}</div> : null}{directoryError ? <div role="alert" className="mb-5 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{directoryError}</div> : null}<Routes>
        <Route path="/dashboard" element={<RoleOnly role={role} allowed={['doctor']}><Dashboard doctorId={session.id} doctorName={account?.doctorProfile?.fullName || 'Doctor'} patientRecords={allPatients} foodEntries={foodEntries} bolusEntries={bolusEntries} messages={messages} acceptedPatientSlugs={acceptedPatientSlugs} patientRequests={patientRequests} assignmentActions={assignmentActions} onAcceptPatient={(id) => onAssignmentDecision(id, 'accepted')} onDeclinePatient={(id) => onAssignmentDecision(id, 'declined')} /></RoleOnly>} />
        <Route path="/patient/dashboard" element={<RoleOnly role={role} allowed={['patient']}>{currentPatient && account?.patientProfile ? <PatientDashboard patient={currentPatient} doctorName={doctorName} assignmentStatus={currentAssignment?.status || 'pending'} setMessages={setMessages} foodEntries={foodEntries} setFoodEntries={setFoodEntries} bolusEntries={bolusEntries} setBolusEntries={setBolusEntries} glucoseEntries={glucoseEntries} setGlucoseEntries={setGlucoseEntries} patientProfile={account.patientProfile} /> : null}</RoleOnly>} />
        <Route path="/patient/food" element={<RoleOnly role={role} allowed={['patient']}>{currentPatient && account?.patientProfile ? <PatientDashboard focusFood patient={currentPatient} doctorName={doctorName} assignmentStatus={currentAssignment?.status || 'pending'} setMessages={setMessages} foodEntries={foodEntries} setFoodEntries={setFoodEntries} bolusEntries={bolusEntries} setBolusEntries={setBolusEntries} glucoseEntries={glucoseEntries} setGlucoseEntries={setGlucoseEntries} patientProfile={account.patientProfile} /> : null}</RoleOnly>} />
        <Route path="/patient/doctors" element={<RoleOnly role={role} allowed={['patient']}><Doctors accounts={accounts} ratings={ratings} patientAccount={account} assignmentStatus={currentAssignment?.status} onChoose={onRequestDoctor} onRate={(score) => {
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
  const [directoryError, setDirectoryError] = useState<string | null>(null);
  const [assignmentActions, setAssignmentActions] = useState<Record<string, AssignmentAction>>({});
  const inFlight = useRef(new Set<string>());
  const assignmentInFlight = useRef(new Set<string>());
  const [session, setSession] = useState<Session | null>(() => {
    try { return JSON.parse(sessionStorage.getItem('ddt.session.v1') || 'null') as Session | null; } catch { return null; }
  });
  const account = accounts.find((item) => item.id === session?.id);
  useEffect(() => { if (session) sessionStorage.setItem('ddt.session.v1', JSON.stringify(session)); else sessionStorage.removeItem('ddt.session.v1'); }, [session]);
  useEffect(() => {
    if (!session || session.role === 'admin' || !sessionStorage.getItem('ddt.sync.token')) return;
    let active = true;
    let polling = false;
    const refresh = async () => {
      if (polling) return;
      polling = true;
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
          const scoped = current.filter((item) => session.role === 'patient' ? item.patientId === session.id : item.doctorId === session.id);
          const preserved = scoped.filter((item) => assignmentInFlight.current.has(assignmentKey(item.patientId, item.doctorId)));
          const remote = snapshot.assignments.filter((item) => !assignmentInFlight.current.has(assignmentKey(item.patientId, item.doctorId)));
          const next = [...others, ...preserved, ...remote];
          return JSON.stringify(next) === JSON.stringify(current) ? current : next;
        });
        setFoodEntries((current) => mergeById(current, snapshot.food));
        setBolusEntries((current) => mergeById(current, snapshot.bolus));
        setGlucoseEntries((current) => mergeById(current, snapshot.glucose));
        setMessages((current) => mergeById(current, snapshot.messages));
        setRatings(snapshot.ratings);
        setSyncError(null);
      } catch (error) { console.error('Patient sync failed', error); setSyncError('Connection to the care sync service is unavailable. New entries may not yet be visible to your doctor or mobile app.'); }
      finally { polling = false; }
    };
    void refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => { active = false; window.clearInterval(timer); };
  }, [session, setAccounts, setAssignments, setFoodEntries, setBolusEntries, setGlucoseEntries, setMessages, setRatings]);
  useEffect(() => {
    if (!session || session.role === 'admin' || !sessionStorage.getItem('ddt.sync.token')) return;
    type Uploadable = { id: string; patientSlug: string; syncState?: string; syncAttempts?: number; syncNextAttemptAt?: number };
    const mark = (kind: 'food' | 'bolus' | 'glucose' | 'messages', id: string, patch: Record<string, unknown>) => {
      if (kind === 'food') setFoodEntries((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
      if (kind === 'bolus') setBolusEntries((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
      if (kind === 'glucose') setGlucoseEntries((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
      if (kind === 'messages') setMessages((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
    };
    const upload = <T extends Uploadable>(kind: 'food' | 'bolus' | 'glucose' | 'messages', entries: T[]) => {
      for (const item of entries) {
        if (item.syncState !== 'pending' || (item.syncNextAttemptAt ?? 0) > Date.now()) continue;
        const operation = `${kind}:${item.id}`;
        if (inFlight.current.has(operation)) continue;
        if (session.role === 'patient' && item.patientSlug !== session.id) continue;
        if (kind === 'messages' && (!('from' in item) || item.from !== session.role)) continue;
        if (kind === 'messages' && 'doctorId' in item && item.doctorId && item.doctorId !== (session.role === 'doctor' ? session.id : account?.patientProfile?.selectedDoctorId)) continue;
        if (session.role === 'doctor' && kind !== 'messages') continue;
        inFlight.current.add(operation);
        void syncItem(kind, item).then(() => {
          mark(kind, item.id, { syncState: 'synced', syncAttempts: 0, syncNextAttemptAt: undefined, syncError: undefined });
          setSyncError(null);
        }).catch((error) => {
          const decision = retryDecision(error instanceof SyncApiError ? error.status : undefined, item.syncAttempts ?? 0);
          if (decision.state === 'conflict') {
            mark(kind, item.id, { syncState: 'conflict', syncAttempts: decision.attempts, syncError: error.message });
            setSyncError('A local entry conflicts with a server record. It was not retried; review the entry before resolving it.');
          } else if (decision.state === 'failed') {
            mark(kind, item.id, { syncState: 'failed', syncAttempts: decision.attempts, syncError: error instanceof Error ? error.message : 'Upload failed' });
            setSyncError('An entry could not be synchronized and will not retry automatically. It remains saved on this device.');
          } else {
            mark(kind, item.id, { syncAttempts: decision.attempts, syncNextAttemptAt: decision.nextAttemptAt, syncError: error instanceof Error ? error.message : 'Upload failed' });
            setSyncError('An entry is waiting to sync. It remains saved on this device and will retry automatically.');
          }
        }).finally(() => inFlight.current.delete(operation));
      }
    };
    const uploadAll = () => {
      upload('food', foodEntries);
      upload('bolus', bolusEntries);
      upload('glucose', glucoseEntries);
      upload('messages', messages);
    };
    uploadAll();
    const timer = window.setInterval(uploadAll, 1000);
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
        if (!response.ok) throw new Error('Doctor directory request failed');
        const result = await response.json() as { doctors: Omit<Account, 'password'>[]; ratings: DoctorRating[] };
        setRatings(result.ratings);
        setAccounts((current) => mergePublicDoctors(current, result.doctors));
        setDirectoryError(null);
      } catch { setDirectoryError('The live doctor directory is unavailable. Showing saved profile information.'); }
    };
    void refreshDoctors();
  }, [setAccounts, setRatings]);
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
  const durableSyncIssue = [...foodEntries, ...bolusEntries, ...glucoseEntries, ...messages].find((item) => item.syncState === 'conflict' || item.syncState === 'failed');
  const displayedSyncError = durableSyncIssue
    ? durableSyncIssue.syncState === 'conflict' ? 'A local entry conflicts with a server record and will not be retried automatically.' : 'A local entry remains saved on this device because it could not be uploaded.'
    : syncError;
  const home = session?.role === 'patient' ? '/patient/dashboard' : session?.role === 'admin' ? '/admin' : '/dashboard';
  const applyConfirmedAssignment = (confirmed: CareAssignment) => {
    setAssignments((current) => [confirmed, ...current.filter((item) => {
      if (confirmed.id && item.id === confirmed.id) return false;
      return !(item.patientId === confirmed.patientId && item.doctorId === confirmed.doctorId && item.status === 'pending');
    })]);
  };
  const decideAssignment = async (patientId: string, status: 'accepted' | 'declined') => {
    if (!session || session.role !== 'doctor') return;
    const key = assignmentKey(patientId, session.id);
    if (assignmentInFlight.current.has(key)) return;
    assignmentInFlight.current.add(key);
    setAssignmentActions((current) => ({ ...current, [key]: { state: 'pending', message: `${status === 'accepted' ? 'Accepting' : 'Declining'} request…` } }));
    try {
      const result = await confirmAssignmentDecision(patientId, session.id, status,
        () => syncAssignment(patientId, status), async () => (await getSnapshot()).assignments);
      applyConfirmedAssignment(result.assignment);
      setAssignmentActions((current) => ({ ...current, [key]: { state: 'success', message: result.reconciled ? `Request ${status}; the server confirmed the decision after the response was lost.` : `Request ${status}.` } }));
    } catch (decisionError) {
      if (decisionError instanceof AssignmentDecisionError && decisionError.assignments) {
        setAssignments((current) => [...current.filter((item) => item.doctorId !== session.id), ...decisionError.assignments!]);
      }
      setAssignmentActions((current) => ({ ...current, [key]: { state: 'error', message: decisionError instanceof Error ? decisionError.message : 'Decision failed.' } }));
    } finally {
      assignmentInFlight.current.delete(key);
    }
  };
  const chooseDoctor = async (doctorId: string) => {
    if (!session || session.role !== 'patient' || !account?.patientProfile) return 'Patient access required.';
    const current = assignments.find((item) => item.patientId === session.id && item.doctorId === doctorId);
    if (doctorId === account.patientProfile.selectedDoctorId && current && current.status !== 'declined') {
      return current.status === 'accepted' ? 'This doctor is already connected.' : 'A request is already pending.';
    }
    try {
      const result = await requestCareDoctor(doctorId);
      setAssignments((items) => [result.assignment, ...items.filter((item) => {
        if (result.assignment.id && item.id === result.assignment.id) return false;
        if (item.patientId !== session.id) return true;
        if (item.status === 'declined') return true;
        return false;
      })]);
      setAccounts((items) => items.map((item) => item.id === session.id && item.patientProfile
        ? { ...item, patientProfile: { ...item.patientProfile, selectedDoctorId: doctorId } } : item));
      return null;
    } catch (error) { return error instanceof Error ? error.message : 'Could not send the doctor request.'; }
  };
  const signIn = async (identifier: string, password: string, mode: 'doctor' | 'patient') => {
    if (identifier.toLowerCase() === 'admin') {
      if (password !== 'admin123') return 'Incorrect email or password.';
      setSession({ id: 'admin', role: 'admin' });
      return null;
    }
    const found = accounts.find((item) => item.email.toLowerCase() === identifier.toLowerCase() && item.role === mode && item.password === password);
    if (found) {
      try {
        const remote = await loginAccount(found.email, password, mode);
        setAccounts((current) => current.map((item) => item.id === remote.id ? { ...remote, password } as Account : item));
        setSession({ id: remote.id, role: remote.role });
      } catch { return 'Incorrect email or password, or sync service unavailable.'; }
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
    try {
      const created = await bridgeAccount(newAccount);
      setAccounts((current) => [...current, { ...created.account, password: newAccount.password } as Account]);
      if (created.assignment) setAssignments((current) => [created.assignment!, ...current]);
      setSession({ id: created.account.id, role: created.account.role });
    } catch { return 'Sync service is unavailable. Start PostgreSQL and run npm run dev:api.'; }
    return null;
  };
  const loginProps = { accounts, ratings, onSignIn: signIn, onRegister: register };
  return <Routes>
    <Route path="/" element={session ? <Navigate to={home} replace /> : <Landing />} />
    <Route path="/doctors" element={session?.role === 'patient' ? <Navigate to="/patient/doctors" replace /> : <Doctors publicView accounts={accounts} ratings={ratings} error={directoryError} />} />
    <Route path="/mobile-preview" element={session?.role === 'doctor' || session?.role === 'admin' ? <Navigate to={home} replace /> : <MobilePreview existingPatient={account?.role === 'patient' ? account : undefined} />} />
    <Route path="/login" element={session ? <Navigate to={home} replace /> : <Login {...loginProps} />} />
    <Route path="/login/doctor" element={session ? <Navigate to={home} replace /> : <Login mode="doctor" {...loginProps} />} />
    <Route path="/login/patient" element={session ? <Navigate to={home} replace /> : <Login mode="patient" {...loginProps} />} />
    <Route path="/login/admin" element={<Navigate to="/login" replace />} />
    <Route path="/*" element={session && (session.role === 'admin' || account) ? <Shell session={session} account={account} accounts={accounts} assignments={assignments} assignmentActions={assignmentActions} onAssignmentDecision={decideAssignment} onRequestDoctor={chooseDoctor} ratings={ratings} setRatings={setRatings} allPatients={allPatients} patientProfiles={patientProfiles} messages={visibleMessages} setMessages={setMessages} foodEntries={visibleFood} setFoodEntries={setFoodEntries} bolusEntries={visibleBolus} setBolusEntries={setBolusEntries} glucoseEntries={glucoseEntries} setGlucoseEntries={setGlucoseEntries} syncError={displayedSyncError} directoryError={directoryError} onUpdateAccount={async (updated) => {
      try {
        const result = await updateAccountProfile(updated);
        setAccounts((current) => current.map((item) => item.id === updated.id ? { ...result.account, password: item.password } as Account : item));
        return null;
      } catch (error) { return error instanceof Error ? error.message : 'Could not save the profile.'; }
    }} onSignOut={() => { sessionStorage.removeItem('ddt.sync.token'); setSession(null); }} /> : <Navigate to="/login" replace />} />
  </Routes>;
}
