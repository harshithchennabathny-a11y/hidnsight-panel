import React, { useState, useEffect } from 'react';
import { getBriefing } from '../api';
import ErrorMessage from './ErrorMessage';
import LoadingSpinner from './LoadingSpinner';

export default function BriefingPanel({ slug, forRound }) {
  const [briefing, setBriefing] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getBriefing(slug, forRound)
      .then(setBriefing)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [slug, forRound]);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;
  if (!briefing) return null;

  if (briefing.generic) {
    return (
      <div className="bg-white border rounded-xl p-5 mb-6">
        <h2 className="text-lg font-bold mb-3">Briefing for Round {forRound}</h2>
        <p className="text-gray-600">No prior rounds to summarize.</p>
      </div>
    );
  }

  return (
    <div className="bg-white border rounded-xl p-5 mb-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900">Briefing for Round {forRound}</h2>
        <span className="text-xs bg-gray-100 text-gray-500 px-2 py-1 rounded">Source: {briefing.synthesis_source}</span>
      </div>
      
      {briefing.overview && (
        <div className="mb-5">
          <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-2">Overview</h4>
          <p className="text-sm text-gray-800">{briefing.overview}</p>
        </div>
      )}

      {briefing.open_disagreements.length > 0 && (
        <div className="mb-5 bg-orange-50 border border-orange-100 p-4 rounded-lg">
          <h4 className="text-sm font-semibold text-orange-800 uppercase tracking-wider mb-3">Open Disagreements to Probe</h4>
          <ul className="space-y-3">
            {briefing.open_disagreements.map(d => (
              <li key={d.disagreement_id} className="text-sm text-orange-900">
                <span className="font-semibold capitalize">{d.competency.replace(/_/g, ' ')}:</span> {d.follow_up}
              </li>
            ))}
          </ul>
        </div>
      )}

      {briefing.earlier_findings.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">Earlier Findings</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {briefing.earlier_findings.map((f, i) => (
              <div key={i} className="border border-gray-100 rounded-lg p-3 bg-gray-50">
                <h5 className="font-medium text-gray-900 capitalize mb-2">{f.competency.replace(/_/g, ' ')}</h5>
                <ul className="list-disc pl-4 space-y-1">
                  {f.claims.map((c, j) => (
                    <li key={j} className="text-xs text-gray-600">
                      "{c.claim}" <span className="text-gray-400">({c.interviewer}, R{c.round})</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
