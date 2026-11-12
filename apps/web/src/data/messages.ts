import type { Message } from '../types';

export const initialMessages: Message[] = [
  { id: 'm1', patientSlug: 'omar-hassan', patient: 'Omar Hassan', avatar: 'OH', from: 'patient', text: 'My glucose has been higher than usual since lunch. Should I be concerned?', time: '2:12 PM', sentAt: '2026-01-01T14:12:00Z', unread: true },
  { id: 'm2', patientSlug: 'omar-hassan', patient: 'Omar Hassan', avatar: 'OH', from: 'doctor', text: "I can see the increase in your CGM readings. I will review today's readings and your meal information.", time: '2:16 PM', sentAt: '2026-01-01T14:16:00Z' },
  { id: 'm3', patientSlug: 'mariam-ali', patient: 'Mariam Ali', avatar: 'MA', from: 'patient', text: 'I had a low reading after my walk and took 15g of carbohydrates.', time: '1:44 PM', sentAt: '2026-01-01T13:44:00Z', unread: true },
  { id: 'm4', patientSlug: 'ahmed-samir', patient: 'Ahmed Samir', avatar: 'AS', from: 'patient', text: 'I uploaded my meals for today.', time: '12:08 PM', sentAt: '2026-01-01T12:08:00Z' },
  { id: 'm5', patientSlug: 'hana-mostafa', patient: 'Hana Mostafa', avatar: 'HM', from: 'patient', text: 'The app says I am falling quickly. I am checking again now.', time: '11:57 AM', sentAt: '2026-01-01T11:57:00Z', unread: true },
];
