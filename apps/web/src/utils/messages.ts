import type { Message } from '../types';

export function messageTimestamp(message: Message): number {
  const timestamp = Date.parse(message.sentAt || '');
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function compareMessages(left: Message, right: Message): number {
  return messageTimestamp(left) - messageTimestamp(right)
    || left.id.localeCompare(right.id);
}

export function chronologicalMessages(messages: Message[]): Message[] {
  return [...messages].sort(compareMessages);
}

export function latestConversations(messages: Message[]): Message[] {
  const latestByPatient = new Map<string, Message>();
  for (const message of messages) {
    const previous = latestByPatient.get(message.patientSlug);
    if (!previous || compareMessages(previous, message) < 0) {
      latestByPatient.set(message.patientSlug, message);
    }
  }
  return [...latestByPatient.values()].sort((left, right) =>
    compareMessages(right, left) || left.patientSlug.localeCompare(right.patientSlug));
}
