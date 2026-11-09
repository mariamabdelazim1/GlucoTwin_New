import type { PatientStatus } from '../../types';
import { Badge } from '../ui/Badge';

export function PatientStatusBadge({ status }: { status: PatientStatus }) {
  return <Badge>{status}</Badge>;
}
