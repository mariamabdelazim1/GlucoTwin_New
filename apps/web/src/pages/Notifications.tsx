import { useMemo, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { CheckCheck } from 'lucide-react';
import { initialNotifications } from '../data/notifications';
import { PageHeader } from '../components/ui/PageHeader';
import { Badge } from '../components/ui/Badge';
import type { Message, NotificationItem, Role } from '../types';

type NotificationsProps = {
  role: Role;
  accountId: string;
  selectedDoctorId?: string;
  doctorName: string;
  visiblePatientIds: string[];
  messages: Message[];
  setMessages: Dispatch<SetStateAction<Message[]>>;
};

function messageGroup(sentAt?: string): NotificationItem['group'] {
  if (!sentAt) return 'Earlier';
  const sent = new Date(sentAt);
  if (Number.isNaN(sent.getTime())) return 'Earlier';
  const today = new Date();
  const sentDay = new Date(sent.getFullYear(), sent.getMonth(), sent.getDate()).getTime();
  const todayDay = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const dayDifference = Math.round((todayDay - sentDay) / 86_400_000);
  if (dayDifference === 0) return 'Today';
  if (dayDifference === 1) return 'Yesterday';
  return 'Earlier';
}

export function messageNotificationsForViewer({ role, accountId, selectedDoctorId, doctorName, visiblePatientIds, messages }: Omit<NotificationsProps, 'setMessages'>): NotificationItem[] {
  if (role === 'admin') return [];
  return messages.flatMap((message) => {
    const messageDoctorId = message.doctorId || 'DR-001';
    const isForPatient = role === 'patient'
      && message.from === 'doctor'
      && message.patientSlug === accountId
      && messageDoctorId === (selectedDoctorId || 'DR-001');
    const isForDoctor = role === 'doctor'
      && message.from === 'patient'
      && messageDoctorId === accountId
      && visiblePatientIds.includes(message.patientSlug);
    if (!isForPatient && !isForDoctor) return [];
    const senderName = message.from === 'patient' ? message.patient : doctorName;
    const unreadForViewer = message.unreadFor
      ? message.unreadFor === role && message.unread !== false
      : message.unread === true;
    return [{
      id: `message-${message.id}`,
      messageId: message.id,
      recipientRole: role,
      recipientId: accountId,
      patientSlug: message.patientSlug,
      doctorId: messageDoctorId,
      group: messageGroup(message.sentAt),
      type: message.from === 'patient' ? 'Patient message' : 'Doctor message',
      title: `New message from ${senderName}`,
      body: message.text,
      time: message.time,
      read: !unreadForViewer,
    } satisfies NotificationItem];
  });
}

export function Notifications({ role, accountId, selectedDoctorId, doctorName, visiblePatientIds, messages, setMessages }: NotificationsProps) {
  const [fixtureItems, setFixtureItems] = useState(initialNotifications);
  const fixtureNotifications = fixtureItems.filter((item) => item.recipientRole === 'all' || item.recipientRole === role && item.recipientId === accountId);
  const messageNotifications = useMemo(() => messageNotificationsForViewer({ role, accountId, selectedDoctorId, doctorName, visiblePatientIds, messages }), [accountId, doctorName, messages, role, selectedDoctorId, visiblePatientIds]);
  const visible = [...messageNotifications, ...fixtureNotifications];
  const groups = ['Today', 'Yesterday', 'Earlier'] as const;
  const hasUnread = visible.some((item) => !item.read);
  const markRead = (item: NotificationItem) => {
    if (item.messageId) {
      setMessages((current) => current.map((message) => message.id === item.messageId ? { ...message, unread: false } : message));
      return;
    }
    setFixtureItems((current) => current.map((candidate) => candidate.id === item.id ? { ...candidate, read: true } : candidate));
  };
  const markAllRead = () => {
    const messageIds = new Set(messageNotifications.map((item) => item.messageId));
    const fixtureIds = new Set(fixtureNotifications.map((item) => item.id));
    setMessages((current) => current.map((message) => messageIds.has(message.id) ? { ...message, unread: false } : message));
    setFixtureItems((current) => current.map((item) => fixtureIds.has(item.id) ? { ...item, read: true } : item));
  };

  return (
    <div className={role === 'patient' ? 'patient-notifications-page' : undefined}>
      <PageHeader title="Notifications" subtitle="Grouped clinical alerts and system notices." actions={<button disabled={!hasUnread} onClick={markAllRead} className="focus-ring inline-flex items-center justify-center gap-2 rounded-md bg-clinical-primary px-4 py-2 text-sm font-semibold text-white hover:bg-clinical-primaryDark disabled:cursor-not-allowed disabled:opacity-50"><CheckCheck size={17} /> Mark all as read</button>} />
      <div className="space-y-6">
        {groups.map((group) => (
          visible.some((item) => item.group === group) ? <section key={group} className="surface overflow-hidden">
            <h2 className="border-b border-clinical-border p-4 text-lg font-semibold">{group}</h2>
            <div className="divide-y divide-clinical-border">
              {visible.filter((item) => item.group === group).map((item) => (
                <article key={item.id} className={`notification-row flex min-w-0 flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between ${item.read ? 'bg-white' : 'bg-clinical-secondary'}`}>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><Badge tone={item.type === 'Critical glucose' ? 'border-red-200 bg-red-50 text-red-700' : undefined}>{item.type}</Badge><span className="text-xs text-clinical-muted">{item.time}</span></div>
                    <h3 className="mt-2 font-semibold">{item.title}</h3>
                    <p className="text-sm text-clinical-muted">{item.body}</p>
                  </div>
                  <button disabled={item.read} onClick={() => markRead(item)} className="focus-ring shrink-0 rounded-md border border-clinical-primary px-3 py-2 text-sm font-semibold text-clinical-primary hover:bg-clinical-secondary disabled:cursor-not-allowed disabled:opacity-50">Mark as read</button>
                </article>
              ))}
            </div>
          </section> : null
        ))}
      </div>
    </div>
  );
}
