import { useState, useEffect } from "react";
import { getCalibration } from "../api";

export default function CalibrationPanel() {
  const [stats, setStats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCalibration()
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-4 text-slate-500">Loading calibration...</div>;
  if (error) return <div className="p-4 text-red-500">Error: {error}</div>;
  if (!stats.length) return <div className="p-4 text-slate-500">No calibration data available (requires at least 3 negative ratings for an interviewer on a competency).</div>;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="bg-slate-50 px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">Interviewer Calibration (Global)</h2>
          <p className="text-sm text-slate-500 mt-1">
            Historical outcomes for candidates who were hired. Rejected candidates have no outcomes.
          </p>
        </div>
        <div className="p-6">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 text-sm font-medium text-slate-500">
                <th className="pb-3 pl-2">Interviewer</th>
                <th className="pb-3">Competency</th>
                <th className="pb-3">Total Negative Ratings</th>
                <th className="pb-3">Hired Despite Negative Rating</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((row, idx) => (
                <tr key={idx} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="py-3 pl-2 text-slate-900">{row.interviewer_id}</td>
                  <td className="py-3 text-slate-600 font-mono text-sm">{row.competency}</td>
                  <td className="py-3 text-slate-900">{row.total_negative_ratings}</td>
                  <td className="py-3 text-amber-600 font-medium">
                    {row.positive_outcomes_when_rated_negative} ({Math.round(row.positive_outcomes_when_rated_negative / row.total_negative_ratings * 100)}%)
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4 text-xs text-slate-400">
            Note: Sample size is small. Synthetic data.
          </div>
        </div>
      </div>
    </div>
  );
}
