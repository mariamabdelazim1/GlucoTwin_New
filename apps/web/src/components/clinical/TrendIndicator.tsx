import { ArrowDown, ArrowRight, ArrowUp } from 'lucide-react';
import type { Trend } from '../../types';
import { trendTone } from '../../utils/status';

export function TrendIndicator({ trend }: { trend: Trend }) {
  const Icon = trend.includes('rising') ? ArrowUp : trend.includes('falling') ? ArrowDown : ArrowRight;
  return (
    <span className={`inline-flex items-center gap-1 font-medium ${trendTone(trend)}`}>
      <Icon size={15} aria-hidden="true" />
      {trend}
    </span>
  );
}
