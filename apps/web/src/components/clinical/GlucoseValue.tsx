import { glucoseClass } from '../../utils/status';

export function GlucoseValue({ value }: { value: number }) {
  return <span className={`font-bold ${glucoseClass(value)}`}>{value} mg/dL</span>;
}
