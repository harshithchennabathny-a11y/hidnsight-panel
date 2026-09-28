import React, { useState, useEffect } from 'react';
import { getEvaluation } from '../api';
import ErrorMessage from './ErrorMessage';
import LoadingSpinner from './LoadingSpinner';
import CompetencyCard from './CompetencyCard';
import BriefingPanel from './BriefingPanel';

export default function CandidateView({ slug }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [forRound, setForRound] = useState(2);

  useEffect(() => {
    setLoading(true);
    setData(null);
    getEvaluation(slug)
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;
  if (!data) return null;

  const status = data.candidate_slug ? (data.status || 'open') : 'open';
  const displayName = data.display_name || slug;

  return (
    <div>
      {/* Header: candidate name and status chip */}
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-2xl font-bold text-gray-900">{displayName}</h2>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide ${
          status === 'finalized' ? 'bg-gray-200 text-gray-600' : 'bg-green-100 text-green-700'
        }`}>
          {status === 'finalized' ? 'Finalized' : 'Open'}
        </span>
      </div>

      {/* Briefing for round selector */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-3">
          <label className="text-sm font-medium text-gray-700">Briefing for round:</label>
          <input
            type="number" min="1" max="10" value={forRound}
            onChange={e => setForRound(parseInt(e.target.value) || 1)}
            className="border border-gray-300 rounded px-2 py-1 w-16 text-sm"
          />
        </div>
        <BriefingPanel slug={slug} forRound={forRound} />
      </div>

      <h3 className="text-lg font-bold text-gray-900 mb-4 mt-8 border-t border-gray-200 pt-6">
        Competency Analysis
      </h3>
      {data.competency_analyses && data.competency_analyses.length > 0 ? (
        data.competency_analyses.map((c, i) => (
          <CompetencyCard key={i} analysis={c} />
        ))
      ) : (
        <p className="text-gray-500 italic">No competencies evaluated yet.</p>
      )}
    </div>
  );
}
