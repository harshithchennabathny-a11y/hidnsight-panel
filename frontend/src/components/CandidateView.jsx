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
  const [forRound, setForRound] = useState(2); // Default to round 2 briefing

  useEffect(() => {
    setLoading(true);
    getEvaluation(slug)
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;
  if (!data) return null;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Candidate Evaluation</h2>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Simulate briefing for round:</label>
          <input type="number" min="1" max="10" value={forRound} onChange={e => setForRound(parseInt(e.target.value) || 1)}
            className="border border-gray-300 rounded px-2 py-1 w-16 text-sm" />
        </div>
      </div>
      
      <BriefingPanel slug={slug} forRound={forRound} />

      <h3 className="text-xl font-bold text-gray-900 mb-4 mt-8">Competency Analysis</h3>
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
