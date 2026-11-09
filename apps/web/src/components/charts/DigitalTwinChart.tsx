import type { ComponentType } from 'react';
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ForecastPoint } from '../../types';

const PredictionArea = ReferenceArea as unknown as ComponentType<Record<string, unknown>>;

export function DigitalTwinChart({ data }: { data: ForecastPoint[] }) {
  return (
    <div className="h-[290px] w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 12, right: 18, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#E4E7EC" vertical={false} />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} stroke="#667085" />
          <YAxis domain={[80, 240]} tick={{ fontSize: 12 }} stroke="#667085" unit=" mg/dL" width={78} />
          <Tooltip contentStyle={{ borderRadius: 8, borderColor: '#E4E7EC' }} formatter={(value) => [`${value} mg/dL`, 'Glucose']} />
          <PredictionArea x1="20:00" x2="23:00" fill="#DBEAFE" fillOpacity={0.45} label={{ value: 'Predicted', fill: '#1E40AF', fontSize: 12 }} />
          <Line type="monotone" dataKey="historical" stroke="#0891B2" strokeWidth={3} dot={false} connectNulls={false} />
          <Line type="monotone" dataKey="predicted" stroke="#2563EB" strokeWidth={3} strokeDasharray="6 5" dot={false} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
