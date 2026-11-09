import { Link } from 'react-router-dom';
import type { Patient } from '../../types';
import { GlucoseValue } from '../clinical/GlucoseValue';
import { PatientStatusBadge } from '../clinical/PatientStatusBadge';
import { TrendIndicator } from '../clinical/TrendIndicator';

export function PatientTable({ patients, compact = false, showDiabetesType = true }: { patients: Patient[]; compact?: boolean; showDiabetesType?: boolean }) {
  return (
    <div className="table-scroll overflow-x-auto">
      <table className="w-full min-w-[860px] text-left text-sm">
        <thead className="bg-clinical-secondary text-xs uppercase text-clinical-muted">
          <tr>
            <th className="px-4 py-3">Patient</th>
            {!compact && showDiabetesType ? <th className="px-4 py-3">Diabetes Type</th> : null}
            <th className="px-4 py-3">Current Glucose</th>
            <th className="px-4 py-3">Trend</th>
            <th className="px-4 py-3">Time in Range</th>
            {!compact ? <th className="px-4 py-3">Average Glucose</th> : null}
            <th className="px-4 py-3">Last Reading</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-clinical-border bg-white">
          {patients.map((patient) => (
            <tr key={patient.id} className="hover:bg-emerald-50">
              <td className="px-4 py-3 font-semibold text-clinical-text">
                <Link className="focus-ring rounded-sm hover:text-clinical-primary" to={`/patients/${patient.slug}`}>{patient.name}</Link>
              </td>
              {!compact && showDiabetesType ? <td className="px-4 py-3 text-clinical-muted">{patient.diabetesType}</td> : null}
              <td className="px-4 py-3">{patient.usesCgm ? <GlucoseValue value={patient.currentGlucose} /> : <span className="text-clinical-muted">No CGM</span>}</td>
              <td className="px-4 py-3">{patient.usesCgm ? <TrendIndicator trend={patient.trend} /> : <span className="text-clinical-muted">--</span>}</td>
              <td className="px-4 py-3">{patient.usesCgm ? `${patient.timeInRange}%` : '--'}</td>
              {!compact ? <td className="px-4 py-3">{patient.usesCgm ? `${patient.averageGlucose} mg/dL` : '--'}</td> : null}
              <td className="px-4 py-3 text-clinical-muted">{patient.lastReading}</td>
              <td className="px-4 py-3"><PatientStatusBadge status={patient.status} /></td>
              <td className="px-4 py-3">
                <Link className="focus-ring rounded-md border border-clinical-border px-3 py-1.5 text-xs font-semibold text-clinical-primary hover:bg-clinical-secondary" to={`/patients/${patient.slug}`}>
                  View Patient
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
