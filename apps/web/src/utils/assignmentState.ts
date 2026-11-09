import type { CareAssignment } from '../types';

export class AssignmentDecisionError extends Error {
  assignments?: CareAssignment[];
  current?: CareAssignment;
  constructor(message: string, assignments?: CareAssignment[], current?: CareAssignment) {
    super(message); this.assignments = assignments; this.current = current;
  }
}

export async function confirmAssignmentDecision(
  patientId: string,
  doctorId: string,
  status: 'accepted' | 'declined',
  decide: () => Promise<{ assignment: CareAssignment }>,
  loadAssignments: () => Promise<CareAssignment[]>,
) {
  try {
    const result = await decide();
    return { assignment: result.assignment, reconciled: false };
  } catch (decisionError) {
    try {
      const assignments = await loadAssignments();
      const current = assignments.find((item) => item.patientId === patientId && item.doctorId === doctorId);
      if (current?.status === status) return { assignment: current, reconciled: true };
      const detail = decisionError instanceof Error ? decisionError.message : 'Decision failed';
      throw new AssignmentDecisionError(`${detail}. The request remains ${current?.status || 'unchanged'}.`, assignments, current);
    } catch (reconciliationError) {
      if (reconciliationError instanceof AssignmentDecisionError) throw reconciliationError;
      const detail = decisionError instanceof Error ? decisionError.message : 'Decision failed';
      throw new AssignmentDecisionError(`${detail}. The last confirmed request state is still shown.`);
    }
  }
}
