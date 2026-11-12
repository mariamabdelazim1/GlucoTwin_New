import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { Dispatch, SetStateAction } from 'react';
import type { Message, Patient, Role } from '../types';
import { PageHeader } from '../components/ui/PageHeader';
import { ConversationList, MessageThread, PatientSnapshot } from '../components/messaging/Messaging';

export function Messages({ role, doctorId, currentPatient, doctorName, patientRecords, messages, setMessages, acceptedPatientSlugs, assignmentStatus }: { role: Role; doctorId: string; currentPatient?: Patient; doctorName: string; patientRecords: Patient[]; messages: Message[]; setMessages: Dispatch<SetStateAction<Message[]>>; acceptedPatientSlugs: string[]; assignmentStatus?: 'pending' | 'accepted' | 'declined' }) {
  const isPatient = role === 'patient';
  const [searchParams, setSearchParams] = useSearchParams();
  const [selected, setSelected] = useState('');
  const visibleMessages = useMemo(() => messages.filter((message) => (message.doctorId || 'DR-001') === doctorId && (isPatient ? message.patientSlug === currentPatient?.slug : acceptedPatientSlugs.includes(message.patientSlug))), [acceptedPatientSlugs, currentPatient?.slug, doctorId, isPatient, messages]);
  const requestedSlug = searchParams.get('patient');
  const activeSlug = isPatient ? currentPatient?.slug : requestedSlug && acceptedPatientSlugs.includes(requestedSlug) ? requestedSlug : acceptedPatientSlugs.includes(selected) ? selected : acceptedPatientSlugs[0];
  const [draft, setDraft] = useState('');
  const patient = patientRecords.find((item) => item.slug === activeSlug);
  const thread = useMemo(() => visibleMessages.filter((message) => message.patientSlug === activeSlug), [activeSlug, visibleMessages]);
  const send = () => {
    if (!draft.trim() || !patient || !activeSlug || (isPatient && assignmentStatus !== 'accepted')) return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), doctorId, patientSlug: activeSlug, patient: patient.name, avatar: patient.avatar, from: isPatient ? 'patient' : 'doctor', text: draft.trim(), time: 'Now', sentAt: new Date().toISOString(), unread: isPatient, syncState: 'pending', syncAttempts: 0 }]);
    setDraft('');
  };
  return (
    <>
      <PageHeader title="Messages" subtitle={isPatient ? 'Private conversation between you and your doctor.' : 'Clinical patient conversations and quick patient context.'} />
      {isPatient && assignmentStatus !== 'accepted' ? <section className="surface p-5 text-sm text-clinical-muted">Your doctor request is {assignmentStatus || 'pending'}. Messaging will be available after your doctor accepts it.</section> : patient ? (
      <div data-testid="messages-layout" className={`grid min-w-0 items-start gap-5 ${isPatient ? 'xl:grid-cols-[minmax(0,1fr)_300px]' : 'xl:grid-cols-[320px_minmax(0,1fr)_300px]'}`}>
        {!isPatient ? <ConversationList messages={visibleMessages} selected={activeSlug || ''} onSelect={(slug) => { setSelected(slug); setSearchParams({ patient: slug }); }} /> : null}
        <MessageThread patient={patient} doctorName={doctorName} messages={thread} draft={draft} setDraft={setDraft} onSend={send} canOpenPatient={!isPatient} viewerRole={role} />
        <PatientSnapshot patient={patient} canOpenPatient={!isPatient} />
      </div>) : <section className="surface p-5 text-sm text-clinical-muted">No patient conversations yet.</section>}
    </>
  );
}
