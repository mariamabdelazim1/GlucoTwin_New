import type { ComponentType } from 'react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { CgmReading } from '../../types';

const Zone = ReferenceArea as unknown as ComponentType<Record<string, unknown>>;

export function CGMChart({ data }: { data: CgmReading[] }) {
  const current = data[data.length - 1];
  return (
    <div className="h-[340px] w-full">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 14, right: 18, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#E4E7EC" vertical={false} />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} stroke="#667085" />
          <YAxis domain={[40, 280]} tick={{ fontSize: 12 }} stroke="#667085" unit=" mg/dL" width={78} />
          <Tooltip contentStyle={{ borderRadius: 8, borderColor: '#E4E7EC' }} formatter={(value) => [`${value} mg/dL`, 'Glucose']} />
          <Zone y1={40} y2={70} fill="#FEE2E2" fillOpacity={0.75} />
          <Zone y1={70} y2={180} fill="#DCFCE7" fillOpacity={0.45} />
          <Zone y1={180} y2={280} fill="#FEF3C7" fillOpacity={0.55} />
          <ReferenceLine y={70} stroke="#DC2626" strokeDasharray="4 4" />
          <ReferenceLine y={180} stroke="#D97706" strokeDasharray="4 4" />
          <Area type="monotone" dataKey="glucose" fill="#0891B2" fillOpacity={0.08} stroke="none" />
          <Line type="monotone" dataKey="glucose" stroke="#0891B2" strokeWidth={3} dot={false} activeDot={{ r: 5 }} />
          <ReferenceLine x={current.time} stroke="#1E40AF" label={{ value: `${current.glucose} mg/dL`, position: 'top', fill: '#1E40AF', fontSize: 12 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
