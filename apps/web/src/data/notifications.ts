import type { NotificationItem } from '../types';

export const initialNotifications: NotificationItem[] = [
  { id: 'n1', recipientRole: 'doctor', recipientId: 'DR-001', patientSlug: 'mariam-ali', doctorId: 'DR-001', group: 'Today', type: 'Critical glucose', title: 'Mariam Ali below target', body: 'Glucose below 70 mg/dL with falling trend.', time: '1 min ago', read: false },
  { id: 'n3', recipientRole: 'patient', recipientId: 'omar-hassan', patientSlug: 'omar-hassan', doctorId: 'DR-001', group: 'Today', type: 'Digital twin alert', title: 'Predicted overnight elevation', body: 'Your forecast exceeds 180 mg/dL after 21:00.', time: '34 min ago', read: false },
  { id: 'n4', recipientRole: 'doctor', recipientId: 'DR-001', patientSlug: 'farah-adel', doctorId: 'DR-001', group: 'Yesterday', type: 'Patient assigned', title: 'New patient assigned', body: 'Farah Adel selected you as care provider in the mobile app.', time: 'Yesterday, 17:20', read: true },
  { id: 'n5', recipientRole: 'all', group: 'Earlier', type: 'System notice', title: 'CGM sync maintenance complete', body: 'All affected patient connections are reporting normally.', time: 'Aug 28, 09:00', read: true },
];
