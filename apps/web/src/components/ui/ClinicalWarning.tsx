import { AlertTriangle } from 'lucide-react';

export function ClinicalWarning() {
  return (
    <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
      <AlertTriangle className="mt-0.5 shrink-0" size={18} aria-hidden="true" />
      <p>Decision-support information. Review patient context before making treatment decisions.</p>
    </div>
  );
}
