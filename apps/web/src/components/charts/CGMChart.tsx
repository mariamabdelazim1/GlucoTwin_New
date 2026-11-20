import type { ComponentType } from 'react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { CgmReading } from '../../types';

const Zone = ReferenceArea as unknown as ComponentType<Record<string, unknown>>;

export function CGMChart({ data, blue = false }: { data: CgmReading[]; blue?: boolean }) {
  const current = data[data.length - 1];
  const line = blue ? '#168DB9' : '#0891B2';
  const marker = blue ? '#237BB6' : '#1E40AF';
  const grid = blue ? '#D6E5F0' : '#E4E7EC';
  const muted = blue ? '#61788A' : '#667085';
  return (
    <div className="h-[300px] min-w-0 w-full sm:h-[340px]">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 14, right: 18, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} stroke={muted} />
          <YAxis domain={[40, 280]} tick={{ fontSize: 12 }} stroke={muted} unit=" mg/dL" width={78} />
          <Tooltip contentStyle={{ borderRadius: 8, borderColor: grid }} formatter={(value) => [`${value} mg/dL`, 'Glucose']} />
          <Zone y1={40} y2={70} fill="#FEE2E2" fillOpacity={0.75} />
          <Zone y1={70} y2={180} fill="#DCFCE7" fillOpacity={0.45} />
          <Zone y1={180} y2={280} fill="#FEF3C7" fillOpacity={0.55} />
          <ReferenceLine y={70} stroke="#DC2626" strokeDasharray="4 4" />
          <ReferenceLine y={180} stroke="#D97706" strokeDasharray="4 4" />
          <Area type="monotone" dataKey="glucose" fill={line} fillOpacity={blue ? 0.12 : 0.08} stroke="none" />
          <Line type="monotone" dataKey="glucose" stroke={line} strokeWidth={3} dot={false} activeDot={{ r: 5 }} />
          <ReferenceLine x={current.time} stroke={marker} label={{ value: `${current.glucose} mg/dL`, position: 'top', fill: marker, fontSize: 12 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
