import { useLayoutEffect, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Paperclip, Send } from 'lucide-react';
import type { Message, Patient, Role } from '../../types';
import { Avatar } from '../ui/Avatar';
import { GlucoseValue } from '../clinical/GlucoseValue';
import { TrendIndicator } from '../clinical/TrendIndicator';
import { chronologicalMessages, latestConversations } from '../../utils/messages';

export function ConversationList({ messages, selected, onSelect }: { messages: Message[]; selected: string; onSelect: (slug: string) => void }) {
  const conversations = latestConversations(messages);
  return (
    <aside className="surface flex max-h-72 min-w-0 flex-col overflow-hidden xl:h-[clamp(30rem,calc(100dvh-12rem),56rem)] xl:max-h-[56rem]">
      <div className="shrink-0 border-b border-clinical-border p-4">
        <h2 className="font-semibold">Conversations</h2>
      </div>
      <div className="min-h-0 overflow-x-hidden overflow-y-auto divide-y divide-clinical-border">
        {conversations.map((message) => (
          <button key={message.patientSlug} onClick={() => onSelect(message.patientSlug)} className={`focus-ring flex w-full gap-3 p-4 text-left hover:bg-emerald-50 ${selected === message.patientSlug ? 'bg-emerald-50' : ''}`}>
            <Avatar label={message.avatar} />
            <span className="min-w-0 flex-1">
              <span className="flex items-center justify-between gap-2">
                <strong className="truncate text-sm">{message.patient}</strong>
                <span className="text-xs text-clinical-muted">{message.time}</span>
              </span>
              <span className="mt-1 line-clamp-2 text-xs text-clinical-muted">{message.text}</span>
            </span>
            {message.unread ? <span className="mt-1 h-2 w-2 rounded-full bg-clinical-primary" aria-label="Unread conversation" /> : null}
          </button>
        ))}
      </div>
    </aside>
  );
}

export function MessageThread({ patient, doctorName, messages, draft, setDraft, onSend, canOpenPatient = true, viewerRole }: { patient: Patient; doctorName: string; messages: Message[]; draft: string; setDraft: (value: string) => void; onSend: () => void; canOpenPatient?: boolean; viewerRole: Role }) {
  const ordered = useMemo(() => chronologicalMessages(messages), [messages]);
  const scroller = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const previousPatient = useRef<string | undefined>(undefined);
  const previousMessageIds = useRef<Set<string>>(new Set());
  const newest = ordered.length ? ordered[ordered.length - 1] : undefined;

  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element) return;
    const openedConversation = previousPatient.current !== patient.slug;
    const sentOutgoing = ordered.some((message) =>
      !previousMessageIds.current.has(message.id)
      && message.from === viewerRole
      && message.syncState === 'pending');
    previousPatient.current = patient.slug;
    previousMessageIds.current = new Set(ordered.map((message) => message.id));
    if (openedConversation || nearBottom.current || sentOutgoing) {
      element.scrollTop = element.scrollHeight;
      nearBottom.current = true;
    }
  }, [newest?.id, newest?.sentAt, ordered, patient.slug, viewerRole]);

  return (
    <section data-testid="message-thread" className="surface flex h-[clamp(30rem,calc(100dvh-12rem),56rem)] min-h-0 min-w-0 flex-col overflow-hidden">
      <header className="flex min-w-0 shrink-0 items-center justify-between gap-3 border-b border-clinical-border p-4">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar label={canOpenPatient ? patient.avatar : 'SA'} />
          <div className="min-w-0">
            <h2 className="truncate font-semibold">{canOpenPatient ? patient.name : doctorName}</h2>
            <p className="truncate text-xs text-clinical-muted">{canOpenPatient ? `Last active ${patient.lastActive}` : 'Your care team'}</p>
          </div>
        </div>
        {canOpenPatient ? <Link to={`/patients/${patient.slug}`} className="focus-ring shrink-0 rounded-md border border-clinical-border px-3 py-2 text-sm font-semibold text-clinical-primary">View patient</Link> : null}
      </header>
      <div ref={scroller} data-testid="message-scroll" onScroll={(event) => {
        const element = event.currentTarget;
        nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight <= 96;
      }} className="min-h-0 min-w-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto overscroll-contain bg-clinical-bg p-4">
        {ordered.map((message) => (
          <div key={message.id} className={`flex min-w-0 ${message.from === viewerRole ? 'justify-end' : 'justify-start'}`}>
            <div className={`min-w-0 max-w-[85%] rounded-lg border px-4 py-3 text-sm shadow-clinical sm:max-w-[78%] ${message.from === viewerRole ? 'border-emerald-200 bg-emerald-50' : 'border-clinical-border bg-white'}`}>
              <p className="break-words [overflow-wrap:anywhere]">{message.text}</p>
              <p className="mt-2 text-xs text-clinical-muted">{message.time}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="min-w-0 shrink-0 border-t border-clinical-border p-4">
        <label className="sr-only" htmlFor="message-input">Type a message</label>
        <div className="flex min-w-0 gap-2">
          <button className="focus-ring shrink-0 rounded-md border border-clinical-border p-3 text-clinical-muted" aria-label="Attach file"><Paperclip size={18} /></button>
          <input id="message-input" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && onSend()} placeholder="Type a message..." className="focus-ring min-w-0 flex-1 rounded-md border border-clinical-border px-3 py-2" />
          <button onClick={onSend} className="focus-ring inline-flex shrink-0 items-center gap-2 rounded-md bg-clinical-primary px-3 py-2 font-semibold text-white hover:bg-clinical-primaryDark sm:px-4"><Send size={17} /><span className="hidden sm:inline">Send</span></button>
        </div>
      </div>
    </section>
  );
}

export function PatientSnapshot({ patient, canOpenPatient = true }: { patient: Patient; canOpenPatient?: boolean }) {
  return (
    <aside className="surface min-w-0 p-4">
      <div className="flex items-center gap-3 border-b border-clinical-border pb-4">
        <Avatar label={patient.avatar} />
        <div>
          <h2 className="font-semibold">{patient.name}</h2>
          <p className="text-sm text-clinical-muted">{patient.diabetesType}</p>
        </div>
      </div>
      <dl className="mt-4 space-y-4 text-sm">
        <div><dt className="text-clinical-muted">Current glucose</dt><dd>{patient.usesCgm ? <GlucoseValue value={patient.currentGlucose} /> : 'No CGM connected'}</dd></div>
        <div><dt className="text-clinical-muted">Trend</dt><dd>{patient.usesCgm ? <TrendIndicator trend={patient.trend} /> : '--'}</dd></div>
        <div><dt className="text-clinical-muted">Time in Range</dt><dd className="font-semibold">{patient.usesCgm ? `${patient.timeInRange}%` : '--'}</dd></div>
        <div><dt className="text-clinical-muted">Last CGM</dt><dd className="font-semibold">{patient.lastReading}</dd></div>
      </dl>
      {canOpenPatient ? <Link to={`/patients/${patient.slug}`} className="focus-ring mt-5 block rounded-md bg-clinical-primary px-4 py-2 text-center text-sm font-semibold text-white hover:bg-clinical-primaryDark">
        Open Full Patient Dashboard
      </Link> : null}
    </aside>
  );
}
