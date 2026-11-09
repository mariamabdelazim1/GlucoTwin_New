import type { ReactNode } from 'react';
import { statusClass } from '../../utils/status';

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${tone ?? statusClass(String(children))}`}>
      {children}
    </span>
  );
}
